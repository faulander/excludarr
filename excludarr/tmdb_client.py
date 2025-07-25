"""TMDB API client for streaming availability checking."""

import re
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from urllib.parse import urlencode

import httpx
from loguru import logger

from excludarr.models import TMDBConfig


class TMDBError(Exception):
    """Base exception for TMDB API errors."""
    pass


class RateLimitError(TMDBError):
    """Exception raised when TMDB rate limit is exceeded."""
    pass


class TMDBNotFoundException(TMDBError):
    """Exception raised when TMDB resource is not found."""
    pass


class TMDBClient:
    """Client for interacting with TMDB API."""
    
    def __init__(self, config: TMDBConfig):
        """Initialize TMDB client.
        
        Args:
            config: TMDB configuration
            
        Raises:
            TMDBError: If client is disabled or API key is missing
        """
        if not config.enabled:
            raise TMDBError("TMDB client is disabled in configuration")
        
        if not config.api_key:
            raise TMDBError("TMDB API key is required")
        
        self.config = config
        self.api_key = config.api_key
        self.base_url = "https://api.themoviedb.org/3"
        self.rate_limit = config.rate_limit
        self.cache_ttl = config.cache_ttl
        
        # Rate limiting tracking
        self._request_times: List[datetime] = []
        self._rate_limit_window = timedelta(seconds=10)  # 40 requests per 10 seconds
        
        logger.info(f"TMDB client initialized with rate limit: {self.rate_limit} req/10s")
    
    async def find_series_by_imdb_id(self, imdb_id: str) -> int:
        """Find TMDB series ID using IMDb ID.
        
        Args:
            imdb_id: IMDb ID (format: tt1234567)
            
        Returns:
            TMDB series ID
            
        Raises:
            TMDBError: If IMDb ID format is invalid
            TMDBNotFoundException: If no series found for IMDb ID
        """
        self._validate_imdb_id(imdb_id)
        
        logger.debug(f"Finding TMDB ID for IMDb ID: {imdb_id}")
        
        response = await self._make_request(
            f"find/{imdb_id}",
            params={"external_source": "imdb_id"}
        )
        
        tv_results = response.get("tv_results", [])
        if not tv_results:
            raise TMDBNotFoundException(f"No TV series found for IMDb ID: {imdb_id}")
        
        tmdb_id = tv_results[0]["id"]
        logger.debug(f"Found TMDB ID {tmdb_id} for IMDb ID {imdb_id}")
        
        return tmdb_id
    
    async def get_watch_providers(self, tmdb_id: int) -> Dict[str, Any]:
        """Get watch providers for a series.
        
        Args:
            tmdb_id: TMDB series ID
            
        Returns:
            Watch providers response from TMDB
        """
        logger.debug(f"Getting watch providers for TMDB ID: {tmdb_id}")
        
        response = await self._make_request(f"tv/{tmdb_id}/watch/providers")
        
        logger.debug(f"Retrieved providers for TMDB ID {tmdb_id}: {len(response.get('results', {}))} countries")
        
        return response
    
    async def get_series_availability(self, imdb_id: str) -> Dict[str, Any]:
        """Get complete series availability data.
        
        Args:
            imdb_id: IMDb ID for the series
            
        Returns:
            Complete availability data including TMDB ID and providers
        """
        logger.debug(f"Getting complete availability for IMDb ID: {imdb_id}")
        
        # Get TMDB ID
        tmdb_id = await self.find_series_by_imdb_id(imdb_id)
        
        # Get watch providers
        providers_response = await self.get_watch_providers(tmdb_id)
        
        result = {
            "tmdb_id": tmdb_id,
            "providers": providers_response.get("results", {})
        }
        
        logger.debug(f"Complete availability retrieved for {imdb_id}")
        
        return result
    
    async def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make rate-limited request to TMDB API.
        
        Args:
            endpoint: API endpoint (without base URL)
            params: Query parameters
            
        Returns:
            JSON response data
            
        Raises:
            RateLimitError: If rate limit exceeded
            TMDBError: If API request fails
            TMDBNotFoundException: If resource not found
        """
        # Enforce rate limiting
        await self._enforce_rate_limit()
        
        # Track this request
        self._request_times.append(datetime.now())
        
        # Make the actual HTTP request
        return await self._make_http_request(endpoint, params)
    
    async def _make_http_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make HTTP request to TMDB API.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            
        Returns:
            JSON response data
        """
        url = self._build_url(endpoint, params)
        headers = self._headers
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.debug(f"Making TMDB request: {endpoint}")
                response = await client.get(url, headers=headers)
                
                # Handle different response codes
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    raise TMDBError("TMDB API authentication failed - check your API key")
                elif response.status_code == 404:
                    raise TMDBNotFoundException("TMDB resource not found")
                elif response.status_code == 429:
                    raise RateLimitError("TMDB API rate limit exceeded")
                else:
                    try:
                        content_type = response.headers.get("content-type", "")
                        if content_type.startswith("application/json"):
                            error_data = response.json()
                            error_message = error_data.get("status_message", f"HTTP {response.status_code}")
                        else:
                            error_message = f"HTTP {response.status_code}"
                    except:
                        error_message = f"HTTP {response.status_code}"
                    raise TMDBError(f"TMDB API error: {error_message}")
                    
        except httpx.RequestError as e:
            raise TMDBError(f"TMDB API request failed: {str(e)}")
    
    async def _enforce_rate_limit(self):
        """Enforce rate limiting by waiting if necessary."""
        now = datetime.now()
        
        # Remove old requests outside the window
        cutoff_time = now - self._rate_limit_window
        self._request_times = [
            req_time for req_time in self._request_times 
            if req_time > cutoff_time
        ]
        
        # Check if we need to wait
        if len(self._request_times) >= self.rate_limit:
            oldest_request = min(self._request_times)
            wait_until = oldest_request + self._rate_limit_window
            
            if now < wait_until:
                wait_time = (wait_until - now).total_seconds()
                logger.debug(f"Rate limit reached, waiting {wait_time:.1f} seconds")
                await asyncio.sleep(wait_time)
    
    def _validate_imdb_id(self, imdb_id: str) -> None:
        """Validate IMDb ID format.
        
        Args:
            imdb_id: IMDb ID to validate
            
        Raises:
            TMDBError: If IMDb ID format is invalid
        """
        if not imdb_id or not isinstance(imdb_id, str):
            raise TMDBError("Invalid IMDb ID format - must be a non-empty string")
        
        # IMDb title IDs follow pattern: tt followed by 7 digits
        pattern = r'^tt\d{7}$'
        if not re.match(pattern, imdb_id):
            raise TMDBError(
                "Invalid IMDb ID format - must be 'tt' followed by 7 digits (e.g., tt1234567)"
            )
    
    def _build_url(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Build complete URL for API request.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            
        Returns:
            Complete URL with API key (v3) or without (v4 uses Bearer token)
        """
        # Remove leading slash from endpoint if present
        endpoint = endpoint.lstrip('/')
        url = f"{self.base_url}/{endpoint}"
        
        # For v4 Bearer tokens, don't add API key to query params
        if self.api_key.startswith("eyJ"):  # JWT token
            all_params = params or {}
        else:
            # For v3 API keys, add to query parameters
            all_params = {"api_key": self.api_key}
            if params:
                all_params.update(params)
        
        if all_params:
            url += "?" + urlencode(all_params)
        
        return url
    
    @property
    def _headers(self) -> Dict[str, str]:
        """Get HTTP headers for requests."""
        headers = {
            "User-Agent": "excludarr/1.0.0 (https://github.com/user/excludarr)",
            "Accept": "application/json"
        }
        
        # Check if this is a v4 Bearer token (JWT) or v3 API key
        if self.api_key.startswith("eyJ"):  # JWT tokens start with "eyJ"
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        return headers
    
    def _normalize_provider_name(self, provider_name: str) -> str:
        """Normalize provider name for consistent matching.
        
        Args:
            provider_name: Original provider name from TMDB
            
        Returns:
            Normalized provider name (lowercase, hyphen-separated)
        """
        # Handle special cases first (before normalization)
        special_cases = {
            'Amazon Prime Video': 'amazon-prime',
            'Apple TV+': 'apple-tv',
            'Disney Plus': 'disney-plus',
            'HBO Max': 'hbo-max',
            'Paramount+': 'paramount-plus',
            'Apple iTunes': 'apple-itunes'
        }
        
        if provider_name in special_cases:
            return special_cases[provider_name]
        
        # Convert to lowercase and replace spaces/special chars with hyphens
        normalized = re.sub(r'[^a-zA-Z0-9]+', '-', provider_name.lower())
        
        # Remove leading/trailing hyphens and multiple consecutive hyphens
        normalized = re.sub(r'-+', '-', normalized).strip('-')
        
        return normalized
    
    def _extract_providers_from_response(self, tmdb_response: Dict[str, Any]) -> Dict[str, List[str]]:
        """Extract and normalize provider names from TMDB response.
        
        Args:
            tmdb_response: Response from TMDB watch providers endpoint
            
        Returns:
            Dict mapping country codes to lists of normalized provider names
        """
        results = tmdb_response.get("results", {})
        extracted = {}
        
        for country, country_data in results.items():
            providers = set()
            
            # Extract from all availability types (flatrate, buy, rent, etc.)
            for availability_type, provider_list in country_data.items():
                # Skip non-provider fields like "link"
                if availability_type == "link" or not isinstance(provider_list, list):
                    continue
                
                for provider in provider_list:
                    # Ensure provider is a dict with the expected structure
                    if isinstance(provider, dict):
                        provider_name = provider.get("provider_name", "")
                        if provider_name:
                            normalized_name = self._normalize_provider_name(provider_name)
                            providers.add(normalized_name)
            
            if providers:
                extracted[country] = sorted(list(providers))
        
        return extracted