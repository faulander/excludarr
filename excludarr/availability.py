"""Streaming availability checking with extensible provider APIs."""

from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger

from excludarr.models import StreamingProvider, ProviderAPIsConfig
from excludarr.providers import ProviderManager


class AvailabilityError(Exception):
    """Exception for availability checking errors."""
    pass


class AvailabilityChecker:
    """Checks streaming availability using extensible provider APIs."""
    
    def __init__(
        self, 
        provider_manager: ProviderManager, 
        streaming_providers: List[StreamingProvider],
        provider_apis_config: ProviderAPIsConfig,
        cache_db_path: str = "availability_cache.db"
    ):
        """Initialize availability checker.
        
        Args:
            provider_manager: Provider management instance
            streaming_providers: User's configured streaming providers
            provider_apis_config: Provider APIs configuration
            cache_db_path: Path to SQLite cache database
        """
        self.provider_manager = provider_manager
        self.streaming_providers = streaming_providers
        self.provider_apis_config = provider_apis_config
        self.cache_db_path = cache_db_path
        
        # Initialize provider API clients
        self._init_provider_clients()
        
        logger.info(f"AvailabilityChecker initialized with {len(streaming_providers)} providers")
    
    def _init_provider_clients(self):
        """Initialize provider API clients based on configuration."""
        self.provider_clients = {}
        
        # TODO: Initialize TMDB client
        if self.provider_apis_config.tmdb.enabled:
            logger.info("TMDB provider enabled - will initialize TMDBClient")
            # self.provider_clients['tmdb'] = TMDBClient(self.provider_apis_config.tmdb)
        
        # TODO: Initialize Streaming Availability client if enabled
        if self.provider_apis_config.streaming_availability.enabled:
            logger.info("Streaming Availability provider enabled - will initialize when implemented")
        
        # TODO: Initialize Utelly client if enabled
        if self.provider_apis_config.utelly.enabled:
            logger.info("Utelly provider enabled - will initialize when implemented")
    
    def check_series_availability(self, series: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Check if a series is available on configured streaming providers.
        
        Args:
            series: Series data from Sonarr (must include tvdbId or imdbId)
            
        Returns:
            Dict mapping provider names to availability info:
            {
                "netflix": {
                    "available": True/False,
                    "country": "US", 
                    "source": "tmdb",
                    "seasons": [1, 2, 3] or [],
                    "timestamp": unix_timestamp
                }
            }
        """
        logger.debug(f"Checking availability for series: {series.get('title', 'Unknown')}")
        
        # Extract series identifiers
        tvdb_id = series.get("tvdbId")
        imdb_id = series.get("imdbId") 
        series_title = series.get("title", "Unknown")
        
        if not tvdb_id and not imdb_id:
            logger.warning(f"Series '{series_title}' has no TVDB or IMDB ID")
            return self._create_unavailable_response("Missing series identifiers")
        
        # Build result dictionary for all configured providers
        result = {}
        
        for provider in self.streaming_providers:
            provider_key = provider.name
            
            # TODO: Implement actual API lookup
            # For now, return mock unavailable response
            result[provider_key] = {
                "available": False,
                "country": provider.country,
                "source": "mock",
                "seasons": [],
                "timestamp": datetime.now().timestamp(),
                "error": "Provider API not yet implemented"
            }
        
        logger.debug(f"Availability check completed for '{series_title}'")
        return result
    
    def _create_unavailable_response(self, reason: str) -> Dict[str, Dict[str, Any]]:
        """Create unavailable response for all configured providers."""
        result = {}
        
        for provider in self.streaming_providers:
            result[provider.name] = {
                "available": False,
                "country": provider.country,
                "source": "error",
                "seasons": [],
                "timestamp": datetime.now().timestamp(),
                "error": reason
            }
        
        return result
    
    def test_availability_sources(self) -> Dict[str, Any]:
        """Test all configured availability sources.
        
        Returns:
            Dict with status of each provider API
        """
        result = {
            "provider_manager": {
                "available": True,
                "provider_count": len(self.provider_manager.get_all_providers()) if hasattr(self.provider_manager, 'get_all_providers') else 0
            }
        }
        
        # Test each enabled provider API
        if self.provider_apis_config.tmdb.enabled:
            result["tmdb"] = {
                "available": False,  # TODO: Implement actual test
                "status": "Not yet implemented"
            }
        
        if self.provider_apis_config.streaming_availability.enabled:
            result["streaming_availability"] = {
                "available": False,  # TODO: Implement actual test
                "status": "Not yet implemented"
            }
        
        if self.provider_apis_config.utelly.enabled:
            result["utelly"] = {
                "available": False,  # TODO: Implement actual test
                "status": "Not yet implemented"
            }
        
        return result
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dict with cache stats (placeholder for now)
        """
        return {
            "hit_count": 0,
            "miss_count": 0,
            "hit_rate": 0.0,
            "cache_size": 0,
            "status": "Cache system not yet implemented"
        }