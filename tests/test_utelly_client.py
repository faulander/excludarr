"""Tests for Utelly API client."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from excludarr.utelly_client import UtellyClient, UtellyError, RateLimitError
from excludarr.models import UtellyConfig


class TestUtellyClient:
    """Test Utelly client functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = UtellyConfig(
            enabled=True,
            rapidapi_key="test_rapidapi_key",
            monthly_quota=1000,
            cache_ttl=604800
        )
        self.client = UtellyClient(self.config)
    
    def test_client_initialization(self):
        """Test client initialization."""
        assert self.client.config == self.config
        assert self.client.rapidapi_key == "test_rapidapi_key"
        assert self.client.base_url == "https://utelly-tv-shows-and-movies-availability-v1.p.rapidapi.com"
        assert self.client.monthly_quota == 1000
        assert self.client.cache_ttl == 604800
    
    def test_client_disabled_config(self):
        """Test client with disabled configuration."""
        disabled_config = UtellyConfig(
            enabled=False,
            rapidapi_key="test_key"
        )
        with pytest.raises(UtellyError, match="client is disabled"):
            UtellyClient(disabled_config)
    
    def test_client_missing_api_key(self):
        """Test client without RapidAPI key."""
        config = UtellyConfig(
            enabled=True,
            rapidapi_key=None
        )
        with pytest.raises(UtellyError, match="RapidAPI key is required"):
            UtellyClient(config)
    
    @pytest.mark.asyncio
    async def test_search_by_imdb_id_success(self):
        """Test successful IMDb ID search."""
        mock_response = {
            "results": [
                {
                    "id": 12345,
                    "name": "Game of Thrones",
                    "locations": [
                        {
                            "display_name": "Netflix",
                            "name": "NetflixDE",
                            "url": "https://www.netflix.com/title/70305903",
                            "icon": "https://utelly.com/icons/netflix.png"
                        },
                        {
                            "display_name": "Amazon Prime Video",
                            "name": "AmazonPrimeVideoDE",
                            "url": "https://www.amazon.de/gp/video/detail/B00KF",
                            "icon": "https://utelly.com/icons/amazon.png"
                        }
                    ]
                }
            ]
        }
        
        with patch.object(self.client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await self.client.search_by_imdb_id("tt0944947", "de")
            
            assert result == mock_response
            mock_request.assert_called_once_with(
                "lookup",
                {"term": "tt0944947", "country": "de"}
            )
            assert self.client._request_count == 1
    
    @pytest.mark.asyncio
    async def test_search_by_imdb_id_not_found(self):
        """Test search when content not found."""
        mock_response = {"results": []}
        
        with patch.object(self.client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await self.client.search_by_imdb_id("tt9999999", "de")
            
            assert result == mock_response
            assert self.client._request_count == 1
    
    @pytest.mark.asyncio
    async def test_get_id_lookup(self):
        """Test ID lookup functionality."""
        mock_response = {
            "id": "tt0944947",
            "results": [{"name": "Game of Thrones"}]
        }
        
        with patch.object(self.client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await self.client.get_id_lookup("tt0944947", "imdb", "de")
            
            assert result == mock_response
            mock_request.assert_called_once_with(
                "idlookup",
                {
                    "source_id": "tt0944947",
                    "source": "imdb",
                    "country": "de"
                }
            )
    
    @pytest.mark.asyncio
    async def test_monthly_quota_enforcement(self):
        """Test monthly quota enforcement."""
        # Set request count to quota limit
        self.client._request_count = 1000
        self.client._request_month = datetime.now().strftime("%Y-%m")
        
        with pytest.raises(RateLimitError, match="Monthly quota.*exceeded"):
            await self.client.search_by_imdb_id("tt0944947")
    
    @pytest.mark.asyncio
    async def test_monthly_quota_reset(self):
        """Test monthly quota resets on new month."""
        # Set request count to quota limit last month
        self.client._request_count = 1000
        # Simulate last month
        if datetime.now().month == 1:
            self.client._request_month = f"{datetime.now().year - 1}-12"
        else:
            self.client._request_month = f"{datetime.now().year}-{datetime.now().month - 1:02d}"
        
        mock_response = {"results": []}
        
        with patch.object(self.client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            # Should succeed because it's a new month
            result = await self.client.search_by_imdb_id("tt0944947")
            
            assert result == mock_response
            assert self.client._request_count == 1
            assert self.client._request_month == datetime.now().strftime("%Y-%m")
    
    def test_extract_provider_info(self):
        """Test extracting provider information from response."""
        response = {
            "results": [
                {
                    "locations": [
                        {
                            "display_name": "Netflix",
                            "name": "NetflixDE",
                            "url": "https://www.netflix.com/title/70305903",
                            "icon": "https://utelly.com/icons/netflix.png"
                        },
                        {
                            "display_name": "iTunes",
                            "name": "iTunesDE",
                            "url": "https://itunes.apple.com/de/tv-show/id123",
                            "icon": "https://utelly.com/icons/itunes.png"
                        },
                        {
                            "display_name": "Amazon Prime Video",
                            "name": "AmazonPrimeVideoDE", 
                            "url": "https://www.amazon.de/gp/video/detail/B00KF",
                            "icon": "https://utelly.com/icons/amazon.png"
                        }
                    ]
                }
            ]
        }
        
        providers = self.client.extract_provider_info(response)
        
        assert "netflix" in providers
        assert "apple-itunes" in providers
        assert "amazon-prime" in providers
        
        netflix_info = providers["netflix"][0]
        assert netflix_info["name"] == "NetflixDE"
        assert netflix_info["url"] == "https://www.netflix.com/title/70305903"
        assert netflix_info["type"] == "subscription"
        
        itunes_info = providers["apple-itunes"][0]
        assert itunes_info["type"] == "rent/buy"
    
    def test_normalize_provider_name(self):
        """Test provider name normalization."""
        test_cases = {
            'Netflix': 'netflix',
            'Amazon Prime Video': 'amazon-prime',
            'Prime Video': 'amazon-prime',
            'Disney Plus': 'disney-plus',
            'Disney+': 'disney-plus',
            'HBO Max': 'hbo-max',
            'Apple TV Plus': 'apple-tv',
            'Apple TV+': 'apple-tv',
            'iTunes': 'apple-itunes',
            'Paramount Plus': 'paramount-plus',
            'Sky Go': 'sky-go',
            'Google Play': 'google-play',
            'Microsoft Store': 'microsoft-store',
            'Unknown Service': 'unknown-service'
        }
        
        for input_name, expected in test_cases.items():
            assert self.client._normalize_provider_name(input_name) == expected
    
    def test_determine_type_from_url(self):
        """Test determining monetization type from URL."""
        test_cases = {
            'https://www.netflix.com/title/123': 'subscription',
            'https://itunes.apple.com/de/movie/123': 'rent/buy',
            'https://play.google.com/store/movies/123': 'rent/buy',
            'https://www.amazon.de/gp/video/detail/B00KF': 'subscription',
            'https://www.amazon.de/gp/video/rental/123': 'rent',
            'https://www.microsoft.com/store/movies/123': 'rent/buy',
            'https://example.com/kaufen/123': 'buy',
            '': 'unknown'
        }
        
        for url, expected_type in test_cases.items():
            assert self.client._determine_type_from_url(url) == expected_type
    
    @pytest.mark.asyncio
    async def test_make_request_errors(self):
        """Test various API request errors."""
        # Test 401 Unauthorized
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Mock(status_code=401, json=Mock(return_value={}))
            
            with pytest.raises(UtellyError, match="Invalid RapidAPI key"):
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
            assert result == {"results": []}
    
    def test_remaining_quota(self):
        """Test remaining quota calculation."""
        assert self.client.remaining_quota == 1000
        
        self.client._request_count = 250
        assert self.client.remaining_quota == 750
        
        self.client._request_count = 1000
        assert self.client.remaining_quota == 0
        
        self.client._request_count = 1500
        assert self.client.remaining_quota == 0