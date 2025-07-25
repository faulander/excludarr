"""Jellyseerr API client for streaming availability checking."""

import time
import re
from typing import Dict, List, Any, Optional, Union
from urllib.parse import urljoin
from difflib import SequenceMatcher

import httpx
from loguru import logger

from excludarr.models import StreamingProvider, JellyseerrConfig


class JellyseerrError(Exception):
    """Exception for Jellyseerr-related errors."""
    pass


class JellyseerrClient:
    """Jellyseerr API client for streaming availability checking."""
    
    def __init__(self, config: JellyseerrConfig):
        """Initialize Jellyseerr client.
        
        Args:
            config: Jellyseerr configuration
        """
        self.config = config
        self.base_url = f"{str(config.url).rstrip('/')}/api/v1"
        
        # Initialize HTTP client
        self.session = httpx.Client(
            timeout=config.timeout,
            headers={
                "X-Api-Key": config.api_key,
                "Content-Type": "application/json",
                "User-Agent": "excludarr/1.0.0"
            }
        )
        
        logger.info(f"Jellyseerr client initialized for {config.url}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.session.close()

    def test_connection(self) -> bool:
        """Test connection to Jellyseerr instance.
        
        Returns:
            True if connection successful
            
        Raises:
            JellyseerrError: If connection fails
        """
        try:
            response = self._api_request("GET", "/auth/me")
            
            if response.get("id"):
                logger.info(f"Jellyseerr connection successful, user: {response.get('displayName', 'Unknown')}")
                return True
            else:
                raise JellyseerrError("Invalid response from Jellyseerr auth endpoint")
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise JellyseerrError("Jellyseerr authentication failed - check API key")
            else:
                raise JellyseerrError(f"Jellyseerr connection failed: HTTP {e.response.status_code}")
        except Exception as e:
            raise JellyseerrError(f"Jellyseerr connection failed: {e}")

    def get_series_availability(
        self, 
        tvdb_id: Optional[int] = None, 
        imdb_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get streaming availability for a TV series.
        
        Args:
            tvdb_id: TVDB ID of the series
            imdb_id: IMDB ID of the series
            
        Returns:
            Availability data or None if not found
            
        Raises:
            ValueError: If no identifiers provided
            JellyseerrError: If API request fails
        """
        if not tvdb_id and not imdb_id:
            raise ValueError("At least one identifier (tvdb_id or imdb_id) must be provided")
        
        try:
            # If we have TVDB ID, use it directly
            if tvdb_id:
                return self._get_series_by_tvdb(tvdb_id)
            
            # Otherwise, search by IMDB ID first
            if imdb_id:
                tvdb_id = self._find_tvdb_by_imdb(imdb_id)
                if tvdb_id:
                    result = self._get_series_by_tvdb(tvdb_id)
                    if result:
                        result["imdb_id"] = imdb_id
                    return result
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get availability for series (TVDB: {tvdb_id}, IMDB: {imdb_id}): {e}")
            return None

    def _get_series_by_tvdb(self, tvdb_id: int) -> Optional[Dict[str, Any]]:
        """Get series data by TVDB ID.
        
        Args:
            tvdb_id: TVDB ID of the series
            
        Returns:
            Series availability data or None if not found
        """
        try:
            response = self._api_request("GET", f"/tv/{tvdb_id}")
            
            series_name = response.get("name", "Unknown")
            imdb_id = response.get("externalIds", {}).get("imdbId")
            watch_providers = response.get("watchProviders", [])
            
            # Parse provider data
            providers = []
            for region_data in watch_providers:
                country = region_data.get("iso_3166_1", "").upper()
                
                # Check different provider types (flatrate, buy, rent)
                for provider_type in ["flatrate", "buy", "rent"]:
                    provider_list = region_data.get(provider_type, [])
                    for provider in provider_list:
                        providers.append({
                            "country": country,
                            "provider_id": provider.get("provider_id"),
                            "provider_name": provider.get("provider_name"),
                            "provider_type": provider_type,
                            "mapped_name": self._map_provider_name(provider.get("provider_name", ""), country)
                        })
            
            return self._build_availability_result(
                series_name=series_name,
                tvdb_id=tvdb_id,
                imdb_id=imdb_id,
                providers=providers
            )
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"Series not found in Jellyseerr: TVDB {tvdb_id}")
                return None
            else:
                raise JellyseerrError(f"Failed to get series {tvdb_id}: HTTP {e.response.status_code}")

    def _find_tvdb_by_imdb(self, imdb_id: str) -> Optional[int]:
        """Find TVDB ID by searching with IMDB ID.
        
        Args:
            imdb_id: IMDB ID to search for
            
        Returns:
            TVDB ID if found, None otherwise
        """
        try:
            response = self._api_request("GET", "/search", params={"query": imdb_id})
            
            results = response.get("results", [])
            for result in results:
                if result.get("media_type") == "tv":
                    external_ids = result.get("external_ids", {})
                    if external_ids.get("imdb_id") == imdb_id:
                        return external_ids.get("tvdb_id")
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to search for IMDB ID {imdb_id}: {e}")
            return None

    def _build_availability_result(
        self,
        series_name: str,
        tvdb_id: Optional[int] = None,
        imdb_id: Optional[str] = None,
        providers: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Build standardized availability result.
        
        Args:
            series_name: Name of the series
            tvdb_id: TVDB ID
            imdb_id: IMDB ID
            providers: List of provider data
            
        Returns:
            Standardized availability result
        """
        return {
            "series_name": series_name,
            "tvdb_id": tvdb_id,
            "imdb_id": imdb_id,
            "providers": providers or [],
            "timestamp": time.time()
        }

    def _map_provider_name(self, jellyseerr_name: str, country: str = "") -> str:
        """Map Jellyseerr provider name to standardized name with regional awareness.
        
        Args:
            jellyseerr_name: Provider name from Jellyseerr
            country: Country code for regional mapping
            
        Returns:
            Mapped provider name
        """
        if not jellyseerr_name:
            return ""
        
        # Comprehensive regional mapping
        regional_mappings = {
            # Netflix variants
            "Netflix": "netflix",
            "Netflix Deutschland": "netflix",
            "Netflix Germany": "netflix",
            "Netflix UK": "netflix",
            "Netflix US": "netflix",
            "Netflix France": "netflix",
            "Netflix España": "netflix",
            "Netflix Italia": "netflix",
            
            # Amazon Prime variants
            "Amazon Prime Video": "amazon-prime",
            "Amazon Prime": "amazon-prime",
            "Prime Video": "amazon-prime",
            "Amazon Prime Video Deutschland": "amazon-prime",
            "Amazon Prime Video Germany": "amazon-prime",
            "Amazon Prime Video UK": "amazon-prime",
            "Amazon Prime Video US": "amazon-prime",
            "Amazon Prime Video France": "amazon-prime",
            "Prime Video Deutschland": "amazon-prime",
            "Prime Video Germany": "amazon-prime",
            
            # Disney variants
            "Disney Plus": "disney-plus",
            "Disney+": "disney-plus",
            "Disney+ Deutschland": "disney-plus",
            "Disney+ Germany": "disney-plus",
            "Disney+ UK": "disney-plus",
            "Disney+ US": "disney-plus",
            "Disney+ France": "disney-plus",
            
            # HBO variants
            "HBO Max": "hbo-max",
            "HBO": "hbo-max",
            "HBO Deutschland": "hbo-max",
            "HBO Germany": "hbo-max",
            
            # Sky variants (important for Germany)
            "Sky Deutschland": "sky",
            "Sky Germany": "sky",
            "Sky Go Deutschland": "sky",
            "Sky Go Germany": "sky",
            "Sky UK": "sky",
            "Sky": "sky",
            
            # Other German providers
            "RTL+": "rtl-plus",
            "RTL Plus": "rtl-plus",
            "Joyn": "joyn",
            "Joyn Plus": "joyn-plus",
            "TVNOW": "tvnow",
            "MagentaTV": "magenta-tv",
            "Magenta TV": "magenta-tv",
            "WOW": "wow",
            "WOW Deutschland": "wow",
            
            # Other global providers
            "Hulu": "hulu",
            "Apple TV Plus": "apple-tv-plus",
            "Apple TV+": "apple-tv-plus",
            "Paramount Plus": "paramount-plus",
            "Paramount+": "paramount-plus",
            "Peacock": "peacock",
            "Discovery Plus": "discovery-plus",
            "Discovery+": "discovery-plus",
            "Crunchyroll": "crunchyroll",
            "Funimation": "funimation",
            
            # UK-specific
            "BBC iPlayer": "bbc-iplayer",
            "BBC": "bbc-iplayer",
            "ITV Hub": "itv-hub",
            "All 4": "all-4",
            "Channel 4": "all-4",
            "My5": "my5",
            "Channel 5": "my5",
            
            # French providers
            "Canal+": "canal-plus",
            "Canal Plus": "canal-plus",
            "France.tv": "france-tv",
            "OCS": "ocs",
            "Salto": "salto",
            
            # Spanish providers
            "Movistar+": "movistar-plus",
            "Movistar Plus": "movistar-plus",
            "HBO Max España": "hbo-max",
            "Atresplayer": "atresplayer",
            
            # Italian providers
            "RaiPlay": "rai-play",
            "Mediaset Infinity": "mediaset-infinity",
            "TIMvision": "tim-vision"
        }
        
        # Try exact match first
        if jellyseerr_name in regional_mappings:
            return regional_mappings[jellyseerr_name]
        
        # Try fuzzy matching for similar names
        best_match = self._fuzzy_match_provider(jellyseerr_name, regional_mappings)
        if best_match:
            return best_match
        
        # Fallback: normalize name
        normalized = re.sub(r'[^a-zA-Z0-9\s]', '', jellyseerr_name.lower())
        normalized = re.sub(r'\s+', '-', normalized.strip())
        
        logger.debug(f"No mapping found for provider '{jellyseerr_name}', using normalized: '{normalized}'")
        return normalized
    
    def _fuzzy_match_provider(self, jellyseerr_name: str, mappings: Dict[str, str], threshold: float = 0.8) -> Optional[str]:
        """Find best fuzzy match for provider name.
        
        Args:
            jellyseerr_name: Provider name to match
            mappings: Provider mapping dictionary
            threshold: Minimum similarity threshold (0.0-1.0)
            
        Returns:
            Mapped provider name if match found above threshold, None otherwise
        """
        best_similarity = 0.0
        best_match = None
        
        for known_provider, mapped_name in mappings.items():
            similarity = SequenceMatcher(None, jellyseerr_name.lower(), known_provider.lower()).ratio()
            
            if similarity > best_similarity and similarity >= threshold:
                best_similarity = similarity
                best_match = mapped_name
        
        if best_match:
            logger.debug(f"Fuzzy matched '{jellyseerr_name}' to '{best_match}' (similarity: {best_similarity:.2f})")
        
        return best_match

    def _filter_providers_by_region(
        self, 
        providers: List[Dict[str, Any]], 
        configured_providers: List[StreamingProvider]
    ) -> List[Dict[str, Any]]:
        """Filter providers by configured regions with enhanced logging.
        
        Args:
            providers: All available providers
            configured_providers: User-configured providers
            
        Returns:
            Filtered providers matching configured regions
        """
        # Create lookup for configured provider/country combinations
        configured_lookup = set()
        for provider in configured_providers:
            configured_lookup.add((provider.name, provider.country))
        
        logger.debug(f"Configured providers: {configured_lookup}")
        
        # Filter providers with detailed logging
        filtered = []
        unmatched_providers = []
        
        for provider in providers:
            mapped_name = provider.get("mapped_name", "")
            country = provider.get("country", "")
            original_name = provider.get("provider_name", "")
            
            if (mapped_name, country) in configured_lookup:
                filtered.append(provider)
                logger.debug(f"✅ Matched provider: '{original_name}' -> '{mapped_name}' ({country})")
            else:
                unmatched_providers.append((original_name, mapped_name, country))
        
        # Log unmatched providers for debugging
        if unmatched_providers:
            logger.debug(f"❌ Unmatched providers ({len(unmatched_providers)}):")
            for original, mapped, country in unmatched_providers[:5]:  # Show first 5
                logger.debug(f"   - '{original}' -> '{mapped}' ({country})")
            if len(unmatched_providers) > 5:
                logger.debug(f"   ... and {len(unmatched_providers) - 5} more")
        
        logger.info(f"Provider filtering: {len(filtered)} matches out of {len(providers)} total providers")
        
        return filtered

    def _api_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """Make API request with retry logic.
        
        Args:
            method: HTTP method
            endpoint: API endpoint (relative to base_url)
            params: Query parameters
            json_data: JSON request body
            max_retries: Maximum number of retries
            
        Returns:
            Response JSON data
            
        Raises:
            JellyseerrError: If request fails after retries
        """
        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        
        for attempt in range(max_retries + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data
                )
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # Rate limiting
                    retry_after = int(e.response.headers.get("Retry-After", 60))
                    raise JellyseerrError(f"Rate limit exceeded, retry after {retry_after} seconds")
                elif e.response.status_code in (500, 502, 503, 504) and attempt < max_retries:
                    # Server errors - retry
                    wait_time = 2 ** attempt
                    logger.warning(f"Jellyseerr API error {e.response.status_code}, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    # Other HTTP errors or max retries exceeded
                    raise
                    
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"Jellyseerr connection error, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    raise JellyseerrError(f"Jellyseerr connection failed after {max_retries} retries: {e}")
            
        raise JellyseerrError(f"Max retries exceeded for {method} {endpoint}")

    def close(self):
        """Close the HTTP client."""
        self.session.close()