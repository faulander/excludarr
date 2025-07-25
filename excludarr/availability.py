"""Streaming availability checking for excludarr."""

from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger

from excludarr.models import StreamingProvider, JellyseerrConfig
from excludarr.providers import ProviderManager
from excludarr.jellyseerr import JellyseerrClient, JellyseerrError
from excludarr.availability_cache import AvailabilityCache, CircuitBreakerError


class AvailabilityError(Exception):
    """Exception for availability checking errors."""
    pass


class AvailabilityChecker:
    """Checks streaming availability for TV series with Jellyseerr integration."""
    
    def __init__(
        self, 
        provider_manager: ProviderManager, 
        streaming_providers: List[StreamingProvider],
        jellyseerr_config: Optional[JellyseerrConfig] = None,
        cache_db_path: str = "availability_cache.db"
    ):
        """Initialize availability checker.
        
        Args:
            provider_manager: Provider manager instance
            streaming_providers: List of configured streaming providers
            jellyseerr_config: Optional Jellyseerr configuration
            cache_db_path: Path to cache database
        """
        self.provider_manager = provider_manager
        self.streaming_providers = streaming_providers
        self.jellyseerr_client = None
        self.cache = None
        
        # Initialize cache system
        self._init_cache(cache_db_path, jellyseerr_config)
        
        # Initialize Jellyseerr client if configured
        self._init_jellyseerr(jellyseerr_config)
        
        # Validate all configured providers
        self._validate_providers()
        
        logger.info(f"Availability checker initialized with {len(streaming_providers)} providers")
        if self.jellyseerr_client:
            logger.info("Jellyseerr integration enabled")
        if self.cache:
            logger.info("Availability caching enabled")

    def _init_cache(self, cache_db_path: str, jellyseerr_config: Optional[JellyseerrConfig]):
        """Initialize availability cache system."""
        try:
            cache_ttl = jellyseerr_config.cache_ttl if jellyseerr_config else 300
            self.cache = AvailabilityCache(
                db_path=cache_db_path,
                default_ttl=cache_ttl,
                cleanup_interval=3600,
                blacklist_threshold=1
            )
            logger.debug(f"Cache initialized with {cache_ttl}s TTL")
        except Exception as e:
            logger.error(f"Failed to initialize cache: {e}")
            self.cache = None
    
    def _init_jellyseerr(self, jellyseerr_config: Optional[JellyseerrConfig]):
        """Initialize Jellyseerr client if configured."""
        if not jellyseerr_config:
            logger.debug("No Jellyseerr configuration provided")
            return
        
        try:
            self.jellyseerr_client = JellyseerrClient(jellyseerr_config)
            
            # Test connection
            if self.jellyseerr_client.test_connection():
                logger.info(f"Jellyseerr connection successful: {jellyseerr_config.url}")
            else:
                logger.warning("Jellyseerr connection test failed")
                self.jellyseerr_client = None
                
        except Exception as e:
            logger.warning(f"Failed to initialize Jellyseerr client: {e}")
            self.jellyseerr_client = None
    
    def _validate_providers(self) -> None:
        """Validate that all configured providers are valid."""
        for provider in self.streaming_providers:
            is_valid, error = self.provider_manager.validate_provider(provider.name, provider.country)
            if not is_valid:
                raise AvailabilityError(f"Invalid provider configuration: {error}")

    def check_series_availability(self, series: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Check if a series is available on configured streaming providers with Jellyseerr integration.
        
        Args:
            series: Series data from Sonarr
            
        Returns:
            Dictionary mapping provider names to availability data
        """
        series_title = series.get("title", "Unknown")
        tvdb_id = series.get("tvdbId")
        imdb_id = series.get("imdbId")
        
        logger.debug(f"Checking availability for '{series_title}' (TVDB: {tvdb_id}, IMDB: {imdb_id})")
        
        # Initialize results for all configured providers
        availability_results = {}
        for provider in self.streaming_providers:
            availability_results[provider.name] = {
                "available": False,
                "seasons": [],
                "country": provider.country,
                "provider_display_name": self.provider_manager.get_provider_display_name(provider.name),
                "source": "unknown",
                "jellyseerr_data": None,
                "timestamp": None
            }
        
        # Try to get availability data from Jellyseerr
        jellyseerr_data = self._get_jellyseerr_availability(tvdb_id, imdb_id)
        
        if jellyseerr_data:
            # Process Jellyseerr data for each provider
            for provider in self.streaming_providers:
                availability = self._process_jellyseerr_data(
                    jellyseerr_data, provider, series
                )
                availability_results[provider.name].update(availability)
                
                if availability["available"]:
                    logger.debug(f"'{series_title}' available on {provider.name} in {provider.country} via Jellyseerr")
        else:
            # Fallback to mock provider logic
            logger.debug(f"Using fallback availability check for '{series_title}'")
            for provider in self.streaming_providers:
                try:
                    availability = self._check_provider_availability_fallback(
                        provider, series, tvdb_id, imdb_id
                    )
                    availability_results[provider.name].update(availability)
                    
                except Exception as e:
                    logger.warning(f"Failed to check {provider.name} availability for '{series_title}': {e}")
                    availability_results[provider.name].update({
                        "error": str(e),
                        "source": "error"
                    })
        
        return availability_results

    def _get_jellyseerr_availability(self, tvdb_id: Optional[int], imdb_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Get availability data from Jellyseerr with caching and reliability features.
        
        Args:
            tvdb_id: TVDB ID of the series
            imdb_id: IMDB ID of the series
            
        Returns:
            Jellyseerr availability data or None if unavailable
        """
        if not self.jellyseerr_client or not self.cache:
            return None
        
        # Check if TVDB ID is blacklisted
        if tvdb_id and self.cache.is_blacklisted(tvdb_id):
            logger.debug(f"TVDB ID {tvdb_id} is blacklisted, skipping Jellyseerr lookup")
            return {"blacklisted": True, "tvdb_id": tvdb_id}
        
        # Check circuit breaker
        circuit_breaker = self.cache.get_circuit_breaker()
        if not circuit_breaker.can_attempt_call():
            logger.debug("Circuit breaker is open, skipping Jellyseerr lookup")
            return {"circuit_breaker_open": True}
        
        # Generate cache key
        cache_key = self.cache._generate_key(
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
            providers=self.streaming_providers
        )
        
        # Check cache first
        cached_data = self.cache.get(cache_key)
        if cached_data:
            logger.debug(f"Cache hit for key: {cache_key}")
            cached_data["source"] = "cache"
            return cached_data
        
        # Try Jellyseerr API
        try:
            logger.debug(f"Cache miss, querying Jellyseerr for TVDB: {tvdb_id}, IMDB: {imdb_id}")
            
            # Try TVDB first, then IMDB fallback
            jellyseerr_data = None
            source = None
            
            if tvdb_id:
                try:
                    jellyseerr_data = circuit_breaker.call(
                        self.jellyseerr_client.get_series_availability,
                        tvdb_id=tvdb_id
                    )
                    source = "jellyseerr_tvdb"
                except Exception as e:
                    logger.debug(f"TVDB lookup failed: {e}")
                    if self.cache:
                        self.cache.record_failure(tvdb_id, str(e))
            
            # Fallback to IMDB if TVDB failed
            if not jellyseerr_data and imdb_id:
                try:
                    jellyseerr_data = circuit_breaker.call(
                        self.jellyseerr_client.get_series_availability,
                        imdb_id=imdb_id
                    )
                    source = "jellyseerr_imdb"
                except Exception as e:
                    logger.debug(f"IMDB lookup failed: {e}")
            
            if jellyseerr_data:
                jellyseerr_data["source"] = source
                jellyseerr_data["timestamp"] = str(datetime.now())
                
                # Cache the successful result
                self.cache.set(cache_key, jellyseerr_data)
                
                logger.debug(f"Successfully retrieved data from {source}")
                return jellyseerr_data
            else:
                logger.debug("No data found in Jellyseerr")
                return None
                
        except CircuitBreakerError:
            logger.warning("Circuit breaker prevented Jellyseerr call")
            return {"circuit_breaker_open": True}
        except Exception as e:
            logger.warning(f"Jellyseerr availability check failed: {e}")
            return {"jellyseerr_error": str(e)}
    
    def _process_jellyseerr_data(
        self, 
        jellyseerr_data: Dict[str, Any], 
        provider: StreamingProvider, 
        series: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process Jellyseerr data for a specific provider.
        
        Args:
            jellyseerr_data: Data from Jellyseerr
            provider: Streaming provider to check
            series: Series data from Sonarr
            
        Returns:
            Availability data for the provider
        """
        result = {
            "jellyseerr_data": jellyseerr_data,
            "timestamp": jellyseerr_data.get("timestamp"),
            "source": jellyseerr_data.get("source", "jellyseerr")
        }
        
        # Handle special cases
        if jellyseerr_data.get("blacklisted"):
            result.update({
                "available": False,
                "blacklisted": True
            })
            return result
        
        if jellyseerr_data.get("circuit_breaker_open"):
            result.update({
                "available": False,
                "circuit_breaker_open": True
            })
            return result
        
        if jellyseerr_data.get("jellyseerr_error"):
            result.update({
                "available": False,
                "jellyseerr_error": jellyseerr_data["jellyseerr_error"]
            })
            return result
        
        # Process provider data
        providers = jellyseerr_data.get("providers", [])
        
        # Filter providers for this specific provider/country combination
        matching_providers = []
        for p in providers:
            if (p.get("mapped_name") == provider.name and 
                p.get("country") == provider.country):
                matching_providers.append(p)
        
        if matching_providers:
            # Provider is available in this region
            seasons = [s["seasonNumber"] for s in series.get("seasons", []) 
                      if s.get("monitored", False)]
            
            result.update({
                "available": True,
                "seasons": seasons,
                "matching_providers": matching_providers
            })
        else:
            result.update({
                "available": False
            })
        
        return result

    def _check_provider_availability_fallback(
        self, 
        provider: StreamingProvider, 
        series: Dict[str, Any],
        tvdb_id: Optional[int],
        imdb_id: Optional[str]
    ) -> Dict[str, Any]:
        """Fallback availability check using mock data.
        
        Args:
            provider: Streaming provider configuration
            series: Series data from Sonarr
            tvdb_id: TVDB ID of the series
            imdb_id: IMDB ID of the series
            
        Returns:
            Availability data for the provider
        """
        return {
            **self._check_provider_availability(provider, series, tvdb_id, imdb_id),
            "source": "mock"
        }

    def _check_provider_availability(
        self, 
        provider: StreamingProvider, 
        series: Dict[str, Any],
        tvdb_id: Optional[int],
        imdb_id: Optional[str]
    ) -> Dict[str, Any]:
        """Check availability on a specific provider.
        
        Args:
            provider: Streaming provider configuration
            series: Series data from Sonarr
            tvdb_id: TVDB ID of the series
            imdb_id: IMDB ID of the series
            
        Returns:
            Availability data for the provider
        """
        # For now, this is a placeholder implementation
        # In a real implementation, this would:
        # 1. Query Jellyseerr API if available
        # 2. Use other streaming availability APIs
        # 3. Implement provider-specific logic
        
        series_title = series.get("title", "").lower()
        
        # Mock implementation for demonstration
        # This would be replaced with actual API calls
        mock_available_shows = {
            "netflix": [
                "breaking bad", "better call saul", "stranger things", "the office",
                "friends", "the crown", "house of cards", "orange is the new black"
            ],
            "amazon-prime": [
                "the boys", "marvelous mrs maisel", "jack ryan", "the expanse",
                "bosch", "good omens", "fleabag", "the man in the high castle"
            ],
            "disney-plus": [
                "the mandalorian", "wandavision", "loki", "falcon and winter soldier",
                "hawkeye", "moon knight", "she-hulk", "ms marvel"
            ],
            "hulu": [
                "handmaids tale", "only murders in the building", "the bear",
                "atlanta", "fargo", "american horror story", "this is us"
            ]
        }
        
        provider_shows = mock_available_shows.get(provider.name, [])
        
        # Simple string matching for demo
        is_available = any(show in series_title for show in provider_shows)
        
        if is_available:
            # Mock: assume all seasons are available
            seasons = [s["seasonNumber"] for s in series.get("seasons", []) 
                      if s.get("monitored", False)]
            return {
                "available": True,
                "seasons": seasons,
                "country": provider.country,
                "provider_display_name": self.provider_manager.get_provider_display_name(provider.name)
            }
        else:
            return {
                "available": False,
                "seasons": [],
                "country": provider.country,
                "provider_display_name": self.provider_manager.get_provider_display_name(provider.name)
            }

    def get_supported_providers(self) -> List[Dict[str, str]]:
        """Get list of supported streaming providers.
        
        Returns:
            List of provider information dictionaries
        """
        return [
            {
                "name": provider.name,
                "country": provider.country,
                "display_name": self.provider_manager.get_provider_display_name(provider.name)
            }
            for provider in self.streaming_providers
        ]

    def test_availability_sources(self) -> Dict[str, Any]:
        """Test availability of data sources with enhanced integration.
        
        Returns:
            Dictionary with test results
        """
        results = {
            "provider_manager": {"available": False, "error": None},
            "jellyseerr": {"available": False, "error": None},
            "cache": {"available": False, "error": None},
            "circuit_breaker": {"state": "unknown", "failures": 0}
        }
        
        # Test provider manager
        try:
            providers = self.provider_manager.get_all_providers()
            results["provider_manager"]["available"] = len(providers) > 0
        except Exception as e:
            results["provider_manager"]["error"] = str(e)
        
        # Test Jellyseerr connectivity
        if self.jellyseerr_client:
            try:
                connection_test = self.jellyseerr_client.test_connection()
                results["jellyseerr"]["available"] = connection_test
                if not connection_test:
                    results["jellyseerr"]["error"] = "Connection test failed"
            except Exception as e:
                results["jellyseerr"]["error"] = str(e)
        else:
            results["jellyseerr"]["note"] = "Not configured"
        
        # Test cache system
        if self.cache:
            try:
                stats = self.cache.get_statistics()
                results["cache"]["available"] = True
                results["cache"]["stats"] = stats
            except Exception as e:
                results["cache"]["error"] = str(e)
        else:
            results["cache"]["note"] = "Not configured"
        
        # Test circuit breaker state
        if self.cache:
            try:
                circuit_breaker = self.cache.get_circuit_breaker()
                results["circuit_breaker"]["state"] = circuit_breaker.state
                results["circuit_breaker"]["failures"] = circuit_breaker.failure_count
            except Exception as e:
                results["circuit_breaker"]["error"] = str(e)
        
        return results

    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Cache statistics dictionary
        """
        if self.cache:
            return self.cache.get_statistics()
        else:
            return {"error": "Cache not available"}