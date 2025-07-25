"""Multi-provider fallback system for streaming availability data."""

import asyncio
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta

from loguru import logger

from excludarr.models import ProviderAPIsConfig
from excludarr.tmdb_client import TMDBClient, TMDBError, TMDBNotFoundException
from excludarr.streaming_availability_client import StreamingAvailabilityClient, StreamingAvailabilityError, RateLimitError as SARateLimitError
from excludarr.utelly_client import UtellyClient, UtellyError, RateLimitError as UtellyRateLimitError
from excludarr.simple_cache import TMDBCache


class ProviderManager:
    """Manages multiple provider APIs with intelligent fallback."""
    
    def __init__(self, config: ProviderAPIsConfig, cache: Optional[TMDBCache] = None):
        """Initialize provider manager with all configured APIs.
        
        Args:
            config: Provider APIs configuration
            cache: Optional cache instance for sharing between providers
        """
        self.config = config
        self.cache = cache or TMDBCache(provider_data_ttl=86400)  # 24 hours default
        
        # Initialize enabled providers
        self.providers = {}
        
        # TMDB is always primary
        if config.tmdb.enabled:
            try:
                self.providers['tmdb'] = TMDBClient(config.tmdb)
                logger.info("TMDB provider initialized")
            except Exception as e:
                logger.error(f"Failed to initialize TMDB: {e}")
        
        # Streaming Availability as secondary
        if config.streaming_availability.enabled:
            try:
                self.providers['streaming_availability'] = StreamingAvailabilityClient(config.streaming_availability)
                logger.info("Streaming Availability provider initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Streaming Availability: {e}")
        
        # Utelly as tertiary
        if config.utelly.enabled:
            try:
                self.providers['utelly'] = UtellyClient(config.utelly)
                logger.info("Utelly provider initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Utelly: {e}")
        
        if not self.providers:
            raise ValueError("No provider APIs are enabled. At least TMDB must be enabled.")
        
        logger.info(f"Provider manager initialized with {len(self.providers)} providers")
    
    async def get_series_availability(self, imdb_id: str, countries: List[str]) -> Dict[str, Any]:
        """Get series availability across multiple countries using all available providers.
        
        Args:
            imdb_id: IMDb ID of the series
            countries: List of 2-letter country codes to check
            
        Returns:
            Combined availability data from all providers
        """
        logger.info(f"Checking availability for {imdb_id} in {len(countries)} countries")
        
        # Check cache first
        cache_key = f"{imdb_id}:{'_'.join(sorted(countries))}"
        cached_data = self._get_from_cache(cache_key)
        if cached_data:
            logger.debug(f"Cache hit for {cache_key}")
            return cached_data
        
        # Prepare result structure
        result = {
            "imdb_id": imdb_id,
            "tmdb_id": None,
            "countries": {},
            "metadata": {
                "sources": [],
                "checked_at": datetime.now().isoformat()
            }
        }
        
        # Step 1: Try to get TMDB ID and basic providers
        tmdb_data = await self._get_tmdb_data(imdb_id)
        if tmdb_data:
            result["tmdb_id"] = tmdb_data.get("tmdb_id")
            result["metadata"]["sources"].append("tmdb")
            
            # Extract providers by country from TMDB
            tmdb_providers = tmdb_data.get("providers", {})
            for country in countries:
                if country.upper() in tmdb_providers:
                    country_data = tmdb_providers[country.upper()]
                    result["countries"][country] = self._extract_tmdb_providers(country_data)
        
        # Step 2: Enhance with Streaming Availability data if available
        if 'streaming_availability' in self.providers and self._should_use_streaming_availability(result, countries):
            sa_data = await self._get_streaming_availability_data(imdb_id, countries)
            if sa_data:
                result["metadata"]["sources"].append("streaming_availability")
                self._merge_streaming_availability_data(result, sa_data, countries)
        
        # Step 3: Add pricing data from Utelly if available
        if 'utelly' in self.providers and self._should_use_utelly(result, countries):
            utelly_data = await self._get_utelly_data(imdb_id, countries)
            if utelly_data:
                result["metadata"]["sources"].append("utelly")
                self._merge_utelly_data(result, utelly_data, countries)
        
        # Cache the combined result
        self._save_to_cache(cache_key, result)
        
        return result
    
    async def _get_tmdb_data(self, imdb_id: str) -> Optional[Dict[str, Any]]:
        """Get data from TMDB API."""
        if 'tmdb' not in self.providers:
            return None
        
        try:
            tmdb_client = self.providers['tmdb']
            
            # Check cache for TMDB ID mapping
            tmdb_id = self.cache.get_id_mapping(imdb_id)
            if not tmdb_id:
                tmdb_id = await tmdb_client.find_series_by_imdb_id(imdb_id)
                self.cache.set_id_mapping(imdb_id, tmdb_id)
            
            # Get providers data
            providers_data = self.cache.get_provider_data(tmdb_id)
            if not providers_data:
                providers_response = await tmdb_client.get_watch_providers(tmdb_id)
                providers_data = tmdb_client._extract_providers_from_response(providers_response)
                self.cache.set_provider_data(tmdb_id, providers_data)
            
            return {
                "tmdb_id": tmdb_id,
                "providers": providers_response.get("results", {}) if 'providers_response' in locals() else self._reconstruct_tmdb_response(providers_data)
            }
            
        except TMDBNotFoundException:
            logger.warning(f"Series {imdb_id} not found on TMDB")
            return None
        except Exception as e:
            logger.error(f"Error getting TMDB data for IMDb ID '{imdb_id}': {e}")
            return None
    
    async def _get_streaming_availability_data(self, imdb_id: str, countries: List[str]) -> Dict[str, Dict]:
        """Get data from Streaming Availability API."""
        sa_client = self.providers['streaming_availability']
        results = {}
        
        for country in countries:
            try:
                response = await sa_client.get_series_availability(imdb_id, country)
                providers = sa_client.extract_provider_info(response)
                if providers:
                    results[country] = providers
            except SARateLimitError:
                logger.warning("Streaming Availability daily quota exceeded")
                break
            except Exception as e:
                logger.error(f"Error getting Streaming Availability data for {country}: {e}")
        
        return results
    
    async def _get_utelly_data(self, imdb_id: str, countries: List[str]) -> Dict[str, Dict]:
        """Get data from Utelly API."""
        utelly_client = self.providers['utelly']
        results = {}
        
        for country in countries:
            try:
                response = await utelly_client.search_by_imdb_id(imdb_id, country)
                providers = utelly_client.extract_provider_info(response)
                if providers:
                    results[country] = providers
            except UtellyRateLimitError:
                logger.warning("Utelly monthly quota exceeded")
                break
            except Exception as e:
                logger.error(f"Error getting Utelly data for {country}: {e}")
        
        return results
    
    def _extract_tmdb_providers(self, country_data: Dict) -> Dict[str, Any]:
        """Extract provider information from TMDB country data."""
        providers = {}
        
        for availability_type in ["flatrate", "free", "ads"]:
            if availability_type in country_data and isinstance(country_data[availability_type], list):
                for provider in country_data[availability_type]:
                    provider_name = self._normalize_provider_name(provider.get("provider_name", ""))
                    if provider_name:
                        providers[provider_name] = {
                            "available": True,
                            "type": "subscription",
                            "source": "tmdb"
                        }
        
        return providers
    
    def _merge_streaming_availability_data(self, result: Dict, sa_data: Dict[str, Dict], countries: List[str]):
        """Merge Streaming Availability data into result."""
        for country in countries:
            if country in sa_data:
                if country not in result["countries"]:
                    result["countries"][country] = {}
                
                for provider_name, provider_details in sa_data[country].items():
                    if provider_name not in result["countries"][country]:
                        result["countries"][country][provider_name] = {
                            "available": True,
                            "source": "streaming_availability"
                        }
                    
                    # Add enhanced details
                    for detail in provider_details:
                        result["countries"][country][provider_name].update({
                            "type": detail.get("type", "subscription"),
                            "link": detail.get("link", ""),
                            "quality": detail.get("quality", ""),
                            "expiry_date": detail.get("expiry_date"),
                            "source": "streaming_availability"
                        })
    
    def _merge_utelly_data(self, result: Dict, utelly_data: Dict[str, Dict], countries: List[str]):
        """Merge Utelly data into result."""
        for country in countries:
            if country in utelly_data:
                if country not in result["countries"]:
                    result["countries"][country] = {}
                
                for provider_name, provider_details in utelly_data[country].items():
                    if provider_name not in result["countries"][country]:
                        result["countries"][country][provider_name] = {
                            "available": True,
                            "source": "utelly"
                        }
                    
                    # Add pricing details
                    for detail in provider_details:
                        if "link" not in result["countries"][country][provider_name]:
                            result["countries"][country][provider_name]["link"] = detail.get("url", "")
                        
                        result["countries"][country][provider_name].update({
                            "type": detail.get("type", "subscription"),
                            "icon": detail.get("icon", ""),
                            "source": "utelly"
                        })
    
    def _should_use_streaming_availability(self, result: Dict, countries: List[str]) -> bool:
        """Determine if Streaming Availability API should be used."""
        # Only use if TMDB has no data at all for the requested countries
        for country in countries:
            if country not in result["countries"] or not result["countries"][country]:
                return True
        
        # Don't use for deep links - TMDB data is sufficient for our needs
        return False
    
    def _should_use_utelly(self, result: Dict, countries: List[str]) -> bool:
        """Determine if Utelly API should be used."""
        # Only use if TMDB has absolutely no data and we need pricing information
        # Since we only care about streaming (not rental/purchase), rarely needed
        for country in countries:
            if country not in result["countries"] or not result["countries"][country]:
                # Only if Streaming Availability also failed
                return "streaming_availability" not in result["metadata"]["sources"]
        
        # Don't use for pricing data - we only care about streaming availability
        return False
    
    def _normalize_provider_name(self, name: str) -> str:
        """Normalize provider name across all APIs."""
        if not name:
            return ""
        
        # Common normalization
        normalized = name.lower().strip()
        normalized = normalized.replace(' ', '-').replace('+', '-plus')
        
        # Apply common mappings
        mappings = {
            'amazon-prime-video': 'amazon-prime',
            'disney-plus': 'disney-plus',
            'hbo-max': 'hbo-max',
            'apple-tv-plus': 'apple-tv',
            'paramount-plus': 'paramount-plus'
        }
        
        return mappings.get(normalized, normalized)
    
    def _reconstruct_tmdb_response(self, providers_data: Dict[str, List[str]]) -> Dict:
        """Reconstruct TMDB response format from cached provider data."""
        results = {}
        
        for country, providers in providers_data.items():
            results[country] = {
                "flatrate": [{"provider_name": p} for p in providers]
            }
        
        return results
    
    def _get_from_cache(self, key: str) -> Optional[Dict]:
        """Get combined data from cache."""
        # For now, we'll implement a simple in-memory cache
        # This could be extended to use the SQLite cache
        return None
    
    def _save_to_cache(self, key: str, data: Dict):
        """Save combined data to cache."""
        # For now, we'll implement a simple in-memory cache
        # This could be extended to use the SQLite cache
        pass
    
    def filter_by_user_providers(self, availability_data: Dict, user_providers: List[str]) -> Dict[str, bool]:
        """Filter availability data to only show user's subscribed providers.
        
        Args:
            availability_data: Complete availability data from get_series_availability
            user_providers: List of provider names user subscribes to
            
        Returns:
            Dict mapping country codes to availability boolean
        """
        result = {}
        
        normalized_user_providers = {self._normalize_provider_name(p) for p in user_providers}
        
        for country, providers in availability_data.get("countries", {}).items():
            available_providers = set(providers.keys())
            has_match = bool(available_providers & normalized_user_providers)
            result[country] = has_match
        
        return result
    
    def get_quota_status(self) -> Dict[str, Dict]:
        """Get current quota status for all providers.
        
        Returns:
            Dict with quota information for each provider
        """
        status = {}
        
        if 'tmdb' in self.providers:
            status['tmdb'] = {
                "type": "rate_limit",
                "limit": "40 requests/10 seconds",
                "status": "No quota limits"
            }
        
        if 'streaming_availability' in self.providers:
            sa_client = self.providers['streaming_availability']
            status['streaming_availability'] = {
                "type": "daily_quota",
                "limit": sa_client.daily_quota,
                "used": sa_client._request_count,
                "remaining": sa_client.remaining_quota,
                "resets": "midnight"
            }
        
        if 'utelly' in self.providers:
            utelly_client = self.providers['utelly']
            status['utelly'] = {
                "type": "monthly_quota",
                "limit": utelly_client.monthly_quota,
                "used": utelly_client._request_count,
                "remaining": utelly_client.remaining_quota,
                "resets": "1st of month"
            }
        
        return status