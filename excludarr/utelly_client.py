"""Utelly API client for pricing and rental data."""

from datetime import datetime
from typing import Dict, List, Any, Optional

import httpx
from loguru import logger

from excludarr.models import UtellyConfig


class UtellyError(Exception):
    """Base exception for Utelly API errors."""
    pass


class RateLimitError(UtellyError):
    """Exception raised when API rate limit is exceeded."""
    pass


class UtellyClient:
    """Client for interacting with Utelly API."""
    
    def __init__(self, config: UtellyConfig):
        """Initialize Utelly client.
        
        Args:
            config: Utelly configuration
            
        Raises:
            UtellyError: If client is disabled or API key is missing
        """
        if not config.enabled:
            raise UtellyError("Utelly client is disabled in configuration")
        
        if not config.rapidapi_key:
            raise UtellyError("RapidAPI key is required for Utelly API")
        
        self.config = config
        self.rapidapi_key = config.rapidapi_key
        self.base_url = "https://utelly-tv-shows-and-movies-availability-v1.p.rapidapi.com"
        self.monthly_quota = config.monthly_quota
        self.cache_ttl = config.cache_ttl
        
        # Track monthly usage
        self._request_count = 0
        self._request_month = datetime.now().strftime("%Y-%m")
        
        logger.info(f"Utelly client initialized with monthly quota: {self.monthly_quota}")
    
    async def search_by_imdb_id(self, imdb_id: str, country: str = "de") -> Dict[str, Any]:
        """Search for content by IMDb ID.
        
        Args:
            imdb_id: IMDb ID (format: tt1234567)
            country: 2-letter country code (default: de for Germany)
            
        Returns:
            Search results with pricing data
            
        Raises:
            RateLimitError: If monthly quota exceeded
            UtellyError: If API request fails
        """
        # Check monthly quota
        self._check_quota()
        
        logger.debug(f"Searching Utelly for IMDb ID {imdb_id} in {country}")
        
        # Utelly uses search endpoint with IMDb ID
        endpoint = "lookup"
        params = {
            "term": imdb_id,
            "country": country.lower()
        }
        
        response = await self._make_request(endpoint, params)
        
        # Track request
        self._request_count += 1
        
        return response
    
    async def get_id_lookup(self, source_id: str, source: str = "imdb", country: str = "de") -> Dict[str, Any]:
        """Get content by external ID.
        
        Args:
            source_id: External ID value
            source: ID source type (imdb, tmdb, etc.)
            country: 2-letter country code
            
        Returns:
            Content data with availability
        """
        # Check monthly quota
        self._check_quota()
        
        logger.debug(f"Looking up {source} ID {source_id} in {country}")
        
        endpoint = "idlookup"
        params = {
            "source_id": source_id,
            "source": source,
            "country": country.lower()
        }
        
        response = await self._make_request(endpoint, params)
        
        # Track request
        self._request_count += 1
        
        return response
    
    def extract_provider_info(self, response: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """Extract provider information from Utelly response.
        
        Args:
            response: API response data
            
        Returns:
            Dict mapping provider names to their details (including pricing)
        """
        providers = {}
        
        results = response.get("results", [])
        
        for result in results:
            locations = result.get("locations", [])
            
            for location in locations:
                # Extract provider name
                display_name = location.get("display_name", "")
                if not display_name:
                    continue
                
                # Normalize provider name
                normalized_name = self._normalize_provider_name(display_name)
                
                if normalized_name not in providers:
                    providers[normalized_name] = []
                
                # Extract provider details
                provider_info = {
                    "name": location.get("name", ""),
                    "icon": location.get("icon", ""),
                    "url": location.get("url", ""),
                    "type": self._determine_type_from_url(location.get("url", ""))
                }
                
                providers[normalized_name].append(provider_info)
        
        return providers
    
    async def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make HTTP request to Utelly API.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            
        Returns:
            JSON response data
            
        Raises:
            UtellyError: If API request fails
        """
        url = f"{self.base_url}/{endpoint}"
        
        headers = {
            "X-RapidAPI-Key": self.rapidapi_key,
            "X-RapidAPI-Host": "utelly-tv-shows-and-movies-availability-v1.p.rapidapi.com",
            "Accept": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.debug(f"Making Utelly request: {endpoint}")
                response = await client.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    raise UtellyError("Invalid RapidAPI key")
                elif response.status_code == 404:
                    # Return empty result for not found
                    return {"results": []}
                elif response.status_code == 429:
                    raise RateLimitError("API rate limit exceeded")
                else:
                    raise UtellyError(f"API error: HTTP {response.status_code}")
                    
        except httpx.RequestError as e:
            raise UtellyError(f"API request failed: {str(e)}")
    
    def _check_quota(self):
        """Check if monthly quota is exceeded.
        
        Raises:
            RateLimitError: If monthly quota exceeded
        """
        # Reset counter if it's a new month
        current_month = datetime.now().strftime("%Y-%m")
        if current_month != self._request_month:
            self._request_count = 0
            self._request_month = current_month
        
        if self._request_count >= self.monthly_quota:
            raise RateLimitError(
                f"Monthly quota ({self.monthly_quota}) exceeded. "
                f"Resets on the 1st of next month."
            )
    
    def _normalize_provider_name(self, provider_name: str) -> str:
        """Normalize provider name for consistent matching.
        
        Args:
            provider_name: Original provider name from API
            
        Returns:
            Normalized provider name
        """
        # Map common variations
        name_mapping = {
            'netflix': 'netflix',
            'amazon prime video': 'amazon-prime',
            'amazon instant video': 'amazon-prime',
            'prime video': 'amazon-prime',
            'disney plus': 'disney-plus',
            'disney+': 'disney-plus',
            'hbo max': 'hbo-max',
            'apple tv plus': 'apple-tv',
            'apple tv+': 'apple-tv',
            'itunes': 'apple-itunes',
            'paramount plus': 'paramount-plus',
            'paramount+': 'paramount-plus',
            'hulu': 'hulu',
            'peacock': 'peacock',
            'sky go': 'sky-go',
            'wow': 'wow',
            'google play': 'google-play',
            'microsoft store': 'microsoft-store',
            'vudu': 'vudu',
            'youtube': 'youtube'
        }
        
        clean_name = provider_name.lower().strip()
        return name_mapping.get(clean_name, clean_name.replace(' ', '-'))
    
    def _determine_type_from_url(self, url: str) -> str:
        """Determine monetization type from URL patterns.
        
        Args:
            url: Provider URL
            
        Returns:
            Type (subscription, rent, buy, or unknown)
        """
        if not url:
            return "unknown"
        
        url_lower = url.lower()
        
        # Check for rental/purchase patterns
        if any(term in url_lower for term in ["rent", "rental", "verleih"]):
            return "rent"
        elif any(term in url_lower for term in ["buy", "purchase", "kaufen"]):
            return "buy"
        elif any(term in url_lower for term in ["itunes", "play.google", "microsoft.com"]):
            # Digital stores typically offer both rent and buy
            return "rent/buy"
        else:
            # Assume subscription for streaming services
            return "subscription"
    
    @property
    def remaining_quota(self) -> int:
        """Get remaining monthly quota."""
        # Reset counter if it's a new month
        current_month = datetime.now().strftime("%Y-%m")
        if current_month != self._request_month:
            self._request_count = 0
            self._request_month = current_month
        
        return max(0, self.monthly_quota - self._request_count)