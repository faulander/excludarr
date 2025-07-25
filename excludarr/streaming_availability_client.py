"""Streaming Availability API client for enhanced streaming data."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from urllib.parse import urlencode

import httpx
from loguru import logger

from excludarr.models import StreamingAvailabilityConfig


class StreamingAvailabilityError(Exception):
    """Base exception for Streaming Availability API errors."""
    pass


class RateLimitError(StreamingAvailabilityError):
    """Exception raised when API rate limit is exceeded."""
    pass


class StreamingAvailabilityClient:
    """Client for interacting with Streaming Availability API."""
    
    def __init__(self, config: StreamingAvailabilityConfig):
        """Initialize Streaming Availability client.
        
        Args:
            config: Streaming Availability configuration
            
        Raises:
            StreamingAvailabilityError: If client is disabled or API key is missing
        """
        if not config.enabled:
            raise StreamingAvailabilityError("Streaming Availability client is disabled in configuration")
        
        if not config.rapidapi_key:
            raise StreamingAvailabilityError("RapidAPI key is required for Streaming Availability API")
        
        self.config = config
        self.rapidapi_key = config.rapidapi_key
        self.base_url = "https://streaming-availability.p.rapidapi.com"
        self.daily_quota = config.daily_quota
        self.cache_ttl = config.cache_ttl
        
        # Track daily usage
        self._request_count = 0
        self._request_date = datetime.now().date()
        
        logger.info(f"Streaming Availability client initialized with daily quota: {self.daily_quota}")
    
    async def get_series_availability(self, imdb_id: str, country: str = "de") -> Dict[str, Any]:
        """Get series availability with deep links and metadata.
        
        Args:
            imdb_id: IMDb ID (format: tt1234567)
            country: 2-letter country code (default: de for Germany)
            
        Returns:
            Complete availability data with deep links
            
        Raises:
            RateLimitError: If daily quota exceeded
            StreamingAvailabilityError: If API request fails
        """
        # Check daily quota
        self._check_quota()
        
        logger.debug(f"Getting availability for IMDb ID {imdb_id} in {country}")
        
        endpoint = f"shows/{imdb_id}"
        params = {"country": country.lower()}
        
        try:
            response = await self._make_request(endpoint, params)
            
            # Track successful request
            self._request_count += 1
            
            return response
        except RateLimitError as e:
            # Mark quota as exhausted when we hit rate limits
            self._request_count = self.daily_quota
            raise e
    
    async def get_changes(self, country: str = "de", since: Optional[datetime] = None) -> Dict[str, Any]:
        """Get changes in availability since a specific date.
        
        Args:
            country: 2-letter country code
            since: Get changes since this date (default: 24h ago)
            
        Returns:
            Changed availability data
        """
        # Check daily quota
        self._check_quota()
        
        if since is None:
            since = datetime.now() - timedelta(days=1)
        
        logger.debug(f"Getting availability changes for {country} since {since}")
        
        endpoint = "changes"
        params = {
            "country": country.lower(),
            "since": int(since.timestamp())
        }
        
        try:
            response = await self._make_request(endpoint, params)
            
            # Track successful request
            self._request_count += 1
            
            return response
        except RateLimitError as e:
            # Mark quota as exhausted when we hit rate limits
            self._request_count = self.daily_quota
            raise e
    
    def extract_provider_info(self, response: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """Extract provider information from API response.
        
        Args:
            response: API response data
            
        Returns:
            Dict mapping provider names to their details (including deep links)
        """
        providers = {}
        
        streaming_options = response.get("streamingOptions", [])
        
        for option in streaming_options:
            service = option.get("service", "").lower()
            if not service:
                continue
            
            # Normalize provider name to match our format
            normalized_name = self._normalize_provider_name(service)
            
            if normalized_name not in providers:
                providers[normalized_name] = []
            
            # Extract relevant details
            provider_info = {
                "type": option.get("type", "unknown"),  # subscription, rent, buy
                "link": option.get("link", ""),
                "quality": option.get("quality", ""),
                "audio_languages": option.get("audioLanguages", []),
                "subtitle_languages": option.get("subtitleLanguages", []),
                "expiry_date": option.get("expiringOn"),
                "price": option.get("price", {})
            }
            
            providers[normalized_name].append(provider_info)
        
        return providers
    
    async def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make HTTP request to Streaming Availability API.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            
        Returns:
            JSON response data
            
        Raises:
            StreamingAvailabilityError: If API request fails
        """
        url = f"{self.base_url}/{endpoint}"
        if params:
            url += "?" + urlencode(params)
        
        headers = {
            "X-RapidAPI-Key": self.rapidapi_key,
            "X-RapidAPI-Host": "streaming-availability.p.rapidapi.com",
            "Accept": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.debug(f"Making Streaming Availability request: {endpoint}")
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    raise StreamingAvailabilityError("Invalid RapidAPI key")
                elif response.status_code == 403:
                    # HTTP 403 typically indicates quota exceeded for this API
                    raise RateLimitError("Daily quota exceeded (HTTP 403)")
                elif response.status_code == 404:
                    # Return empty result for not found
                    return {"streamingOptions": []}
                elif response.status_code == 429:
                    raise RateLimitError("API rate limit exceeded")
                else:
                    raise StreamingAvailabilityError(f"API error: HTTP {response.status_code}")
                    
        except httpx.RequestError as e:
            raise StreamingAvailabilityError(f"API request failed: {str(e)}")
    
    def _check_quota(self):
        """Check if daily quota is exceeded.
        
        Raises:
            RateLimitError: If daily quota exceeded
        """
        # Reset counter if it's a new day
        today = datetime.now().date()
        if today != self._request_date:
            self._request_count = 0
            self._request_date = today
        
        if self._request_count >= self.daily_quota:
            raise RateLimitError(
                f"Daily quota ({self.daily_quota}) exceeded. "
                f"Resets at midnight."
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
            'prime': 'amazon-prime',
            'amazon': 'amazon-prime',
            'amazonprime': 'amazon-prime',
            'disney': 'disney-plus',
            'disneyplus': 'disney-plus',
            'hbo': 'hbo-max',
            'hbomax': 'hbo-max',
            'apple': 'apple-tv',
            'appletv': 'apple-tv',
            'appletvplus': 'apple-tv',
            'paramount': 'paramount-plus',
            'paramountplus': 'paramount-plus',
            'hulu': 'hulu',
            'peacock': 'peacock',
            'skygo': 'sky-go',
            'sky': 'sky-go',
            'wow': 'wow'
        }
        
        clean_name = provider_name.lower().replace(' ', '').replace('+', 'plus').replace('-', '')
        return name_mapping.get(clean_name, provider_name.lower().replace(' ', '-'))
    
    @property
    def remaining_quota(self) -> int:
        """Get remaining daily quota."""
        # Reset counter if it's a new day
        today = datetime.now().date()
        if today != self._request_date:
            self._request_count = 0
            self._request_date = today
        
        return max(0, self.daily_quota - self._request_count)