"""Tests for Streaming Availability API client."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

from excludarr.streaming_availability_client import (
    StreamingAvailabilityClient,
    StreamingAvailabilityError,
    RateLimitError
)
from excludarr.models import StreamingAvailabilityConfig


class TestStreamingAvailabilityClient:
    """Test Streaming Availability client functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = StreamingAvailabilityConfig(
            enabled=True,
            rapidapi_key="test_rapidapi_key",
            daily_quota=100,
            cache_ttl=43200
        )
        self.client = StreamingAvailabilityClient(self.config)
    
    def test_client_initialization(self):
        """Test client initialization."""
        assert self.client.config == self.config
        assert self.client.rapidapi_key == "test_rapidapi_key"
        assert self.client.base_url == "https://streaming-availability.p.rapidapi.com"
        assert self.client.daily_quota == 100
        assert self.client.cache_ttl == 43200
    
    def test_client_disabled_config(self):
        """Test client with disabled configuration."""
        disabled_config = StreamingAvailabilityConfig(
            enabled=False,
            rapidapi_key="test_key"
        )
        with pytest.raises(StreamingAvailabilityError, match="client is disabled"):
            StreamingAvailabilityClient(disabled_config)
    
    def test_client_missing_api_key(self):
        """Test client without RapidAPI key."""
        config = StreamingAvailabilityConfig(
            enabled=True,
            rapidapi_key=None
        )
        with pytest.raises(StreamingAvailabilityError, match="RapidAPI key is required"):
            StreamingAvailabilityClient(config)
    
    @pytest.mark.asyncio
    async def test_get_series_availability_success(self):
        """Test successful series availability lookup."""
        mock_response = {
            "imdbId": "tt0944947",
            "title": "Game of Thrones",
            "streamingOptions": [
                {
                    "service": "netflix",
                    "type": "subscription",
                    "link": "https://www.netflix.com/de/title/70305903",
                    "quality": "HD",
                    "audioLanguages": ["de", "en"],
                    "subtitleLanguages": ["de", "en"]
                }
            ]
        }
        
        with patch.object(self.client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await self.client.get_series_availability("tt0944947", "de")
            
            assert result == mock_response
            mock_request.assert_called_once_with(
                "shows/tt0944947",
                {"country": "de"}
            )
            assert self.client._request_count == 1
    
    @pytest.mark.asyncio
    async def test_get_series_availability_not_found(self):
        """Test series availability when not found."""
        mock_response = {"streamingOptions": []}
        
        with patch.object(self.client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await self.client.get_series_availability("tt9999999", "de")
            
            assert result == mock_response
            assert self.client._request_count == 1
    
    @pytest.mark.asyncio
    async def test_daily_quota_enforcement(self):
        """Test daily quota enforcement."""
        # Set request count to quota limit
        self.client._request_count = 100
        self.client._request_date = datetime.now().date()
        
        with pytest.raises(RateLimitError, match="Daily quota.*exceeded"):
            await self.client.get_series_availability("tt0944947")
    
    @pytest.mark.asyncio
    async def test_daily_quota_reset(self):
        """Test daily quota resets on new day."""
        # Set request count to quota limit yesterday
        self.client._request_count = 100
        self.client._request_date = (datetime.now() - timedelta(days=1)).date()
        
        mock_response = {"streamingOptions": []}
        
        with patch.object(self.client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            # Should succeed because it's a new day
            result = await self.client.get_series_availability("tt0944947")
            
            assert result == mock_response
            assert self.client._request_count == 1
            assert self.client._request_date == datetime.now().date()
    
    @pytest.mark.asyncio
    async def test_get_changes(self):
        """Test getting availability changes."""
        mock_response = {
            "changes": [
                {
                    "imdbId": "tt0944947",
                    "changeType": "added",
                    "service": "netflix"
                }
            ]
        }
        
        since_date = datetime.now() - timedelta(hours=12)
        
        with patch.object(self.client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await self.client.get_changes("de", since_date)
            
            assert result == mock_response
            mock_request.assert_called_once_with(
                "changes",
                {
                    "country": "de",
                    "since": int(since_date.timestamp())
                }
            )
    
    def test_extract_provider_info(self):
        """Test extracting provider information from response."""
        response = {
            "streamingOptions": [
                {
                    "service": "netflix",
                    "type": "subscription",
                    "link": "https://www.netflix.com/de/title/70305903",
                    "quality": "HD",
                    "audioLanguages": ["de", "en"],
                    "subtitleLanguages": ["de", "en"],
                    "expiringOn": "2024-12-31"
                },
                {
                    "service": "amazon",
                    "type": "rent",
                    "link": "https://www.amazon.de/dp/B00KFPN",
                    "quality": "4K",
                    "price": {"amount": 3.99, "currency": "EUR"}
                }
            ]
        }
        
        providers = self.client.extract_provider_info(response)
        
        assert "netflix" in providers
        assert "amazon-prime" in providers
        
        netflix_info = providers["netflix"][0]
        assert netflix_info["type"] == "subscription"
        assert netflix_info["link"] == "https://www.netflix.com/de/title/70305903"
        assert netflix_info["quality"] == "HD"
        assert netflix_info["expiry_date"] == "2024-12-31"
        
        amazon_info = providers["amazon-prime"][0]
        assert amazon_info["type"] == "rent"
        assert amazon_info["price"]["amount"] == 3.99
    
    def test_normalize_provider_name(self):
        """Test provider name normalization."""
        test_cases = {
            'netflix': 'netflix',
            'Netflix': 'netflix',
            'amazon': 'amazon-prime',
            'Amazon Prime': 'amazon-prime',
            'amazonprime': 'amazon-prime',
            'disney': 'disney-plus',
            'Disney+': 'disney-plus',
            'disneyplus': 'disney-plus',
            'HBO Max': 'hbo-max',
            'hbomax': 'hbo-max',
            'Apple TV+': 'apple-tv',
            'appletv': 'apple-tv',
            'Paramount+': 'paramount-plus',
            'Sky Go': 'sky-go',
            'skygo': 'sky-go',
            'wow': 'wow',
            'Unknown Service': 'unknown-service'
        }
        
        for input_name, expected in test_cases.items():
            assert self.client._normalize_provider_name(input_name) == expected
    
    @pytest.mark.asyncio
    async def test_make_request_errors(self):
        """Test various API request errors."""
        # Test 401 Unauthorized
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Mock(status_code=401, json=Mock(return_value={}))
            
            with pytest.raises(StreamingAvailabilityError, match="Invalid RapidAPI key"):
                await self.client._make_request("test")
        
        # Test 429 Rate Limit
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Mock(status_code=429, json=Mock(return_value={}))
            
            with pytest.raises(RateLimitError, match="rate limit exceeded"):
                await self.client._make_request("test")
        
        # Test 404 Not Found (should return empty result)
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Mock(status_code=404, json=Mock(return_value={}))
            
            result = await self.client._make_request("test")
            assert result == {"streamingOptions": []}
    
    def test_remaining_quota(self):
        """Test remaining quota calculation."""
        assert self.client.remaining_quota == 100
        
        self.client._request_count = 25
        assert self.client.remaining_quota == 75
        
        self.client._request_count = 100
        assert self.client.remaining_quota == 0
        
        self.client._request_count = 150
        assert self.client.remaining_quota == 0
    
    def test_remaining_quota_new_day(self):
        """Test remaining quota resets on new day."""
        self.client._request_count = 50
        self.client._request_date = (datetime.now() - timedelta(days=1)).date()
        
        # Should reset to full quota
        assert self.client.remaining_quota == 100
        assert self.client._request_count == 0