"""Tests for TMDB client implementation."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import httpx
from datetime import datetime, timedelta

from excludarr.tmdb_client import TMDBClient, TMDBError, RateLimitError, TMDBNotFoundException
from excludarr.models import TMDBConfig


class TestTMDBClient:
    """Test TMDB client functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = TMDBConfig(
            api_key="test_tmdb_api_key",
            enabled=True,
            rate_limit=40,
            cache_ttl=86400
        )
        self.client = TMDBClient(self.config)
    
    def test_tmdb_client_initialization(self):
        """Test TMDB client initialization."""
        assert self.client.config == self.config
        assert self.client.api_key == "test_tmdb_api_key"
        assert self.client.base_url == "https://api.themoviedb.org/3"
        assert self.client.rate_limit == 40
        assert self.client.cache_ttl == 86400
    
    def test_tmdb_client_disabled_config(self):
        """Test TMDB client with disabled configuration."""
        disabled_config = TMDBConfig(
            api_key="test_key",
            enabled=False
        )
        with pytest.raises(TMDBError, match="TMDB client is disabled"):
            TMDBClient(disabled_config)
    
    def test_tmdb_client_missing_api_key(self):
        """Test TMDB client with empty API key."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TMDBConfig(api_key="")
    
    @pytest.mark.asyncio
    async def test_find_series_by_imdb_id_success(self):
        """Test successful series lookup by IMDb ID."""
        mock_response = {
            "tv_results": [
                {
                    "id": 12345,
                    "name": "Test Series",
                    "original_name": "Test Series"
                }
            ]
        }
        
        with patch.object(self.client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await self.client.find_series_by_imdb_id("tt1234567")
            
            assert result == 12345
            mock_request.assert_called_once_with(
                "find/tt1234567",
                params={"external_source": "imdb_id"}
            )
    
    @pytest.mark.asyncio
    async def test_find_series_by_imdb_id_not_found(self):
        """Test series lookup when no results found."""
        mock_response = {"tv_results": []}
        
        with patch.object(self.client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            with pytest.raises(TMDBNotFoundException, match="No TV series found for IMDb ID"):
                await self.client.find_series_by_imdb_id("tt9999999")
    
    @pytest.mark.asyncio
    async def test_find_series_by_imdb_id_invalid_id(self):
        """Test series lookup with invalid IMDb ID format."""
        with pytest.raises(TMDBError, match="Invalid IMDb ID format"):
            await self.client.find_series_by_imdb_id("invalid_id")
    
    @pytest.mark.asyncio
    async def test_get_watch_providers_success(self):
        """Test successful watch providers lookup."""
        mock_response = {
            "id": 12345,
            "results": {
                "US": {
                    "flatrate": [
                        {"provider_id": 8, "provider_name": "Netflix"},
                        {"provider_id": 119, "provider_name": "Amazon Prime Video"}
                    ],
                    "buy": [
                        {"provider_id": 2, "provider_name": "Apple iTunes"}
                    ]
                },
                "DE": {
                    "flatrate": [
                        {"provider_id": 119, "provider_name": "Amazon Prime Video"}
                    ]
                }
            }
        }
        
        with patch.object(self.client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await self.client.get_watch_providers(12345)
            
            assert result == mock_response
            mock_request.assert_called_once_with("tv/12345/watch/providers")
    
    @pytest.mark.asyncio
    async def test_get_watch_providers_no_data(self):
        """Test watch providers lookup when no data available."""
        mock_response = {"id": 12345, "results": {}}
        
        with patch.object(self.client, '_make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await self.client.get_watch_providers(12345)
            
            assert result == mock_response
    
    @pytest.mark.asyncio
    async def test_get_series_availability_success(self):
        """Test complete series availability check."""
        # Mock the find_series_by_imdb_id call
        with patch.object(self.client, 'find_series_by_imdb_id', new_callable=AsyncMock) as mock_find:
            mock_find.return_value = 12345
            
            # Mock the get_watch_providers call
            with patch.object(self.client, 'get_watch_providers', new_callable=AsyncMock) as mock_providers:
                mock_providers.return_value = {
                    "id": 12345,
                    "results": {
                        "US": {
                            "flatrate": [
                                {"provider_id": 8, "provider_name": "Netflix"}
                            ]
                        }
                    }
                }
                
                result = await self.client.get_series_availability("tt1234567")
                
                assert result == {
                    "tmdb_id": 12345,
                    "providers": {
                        "US": {
                            "flatrate": [
                                {"provider_id": 8, "provider_name": "Netflix"}
                            ]
                        }
                    }
                }
                
                mock_find.assert_called_once_with("tt1234567")
                mock_providers.assert_called_once_with(12345)
    
    @pytest.mark.asyncio
    async def test_get_series_availability_not_found(self):
        """Test series availability when series not found."""
        with patch.object(self.client, 'find_series_by_imdb_id', new_callable=AsyncMock) as mock_find:
            mock_find.side_effect = TMDBNotFoundException("No TV series found")
            
            with pytest.raises(TMDBNotFoundException):
                await self.client.get_series_availability("tt9999999")
    
    @pytest.mark.asyncio
    async def test_make_request_success(self):
        """Test successful API request."""
        mock_response = {"success": True, "data": "test"}
        
        mock_http_response = Mock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_response
        
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_http_response
            
            result = await self.client._make_request("test/endpoint")
            
            assert result == mock_response
            mock_get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_make_request_rate_limited(self):
        """Test API request when rate limited."""
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_get.return_value.status_code = 429
            mock_get.return_value.json.return_value = {
                "status_message": "Request limit exceeded"
            }
            
            with pytest.raises(RateLimitError, match="TMDB API rate limit exceeded"):
                await self.client._make_request("test/endpoint")
    
    @pytest.mark.asyncio
    async def test_make_request_unauthorized(self):
        """Test API request with invalid API key."""
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_get.return_value.status_code = 401
            mock_get.return_value.json.return_value = {
                "status_message": "Invalid API key"
            }
            
            with pytest.raises(TMDBError, match="TMDB API authentication failed"):
                await self.client._make_request("test/endpoint")
    
    @pytest.mark.asyncio
    async def test_make_request_not_found(self):
        """Test API request for non-existent resource."""
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_get.return_value.status_code = 404
            mock_get.return_value.json.return_value = {
                "status_message": "The resource you requested could not be found."
            }
            
            with pytest.raises(TMDBNotFoundException, match="TMDB resource not found"):
                await self.client._make_request("test/endpoint")
    
    @pytest.mark.asyncio
    async def test_make_request_server_error(self):
        """Test API request with server error."""
        mock_http_response = Mock()
        mock_http_response.status_code = 500
        mock_http_response.headers = {"content-type": "application/json"}
        mock_http_response.json.return_value = {
            "status_message": "Internal server error"
        }
        
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_http_response
            
            with pytest.raises(TMDBError, match="TMDB API error"):
                await self.client._make_request("test/endpoint")
    
    @pytest.mark.asyncio
    async def test_make_request_network_error(self):
        """Test API request with network error."""
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_get.side_effect = httpx.RequestError("Connection failed")
            
            with pytest.raises(TMDBError, match="TMDB API request failed"):
                await self.client._make_request("test/endpoint")
    
    def test_validate_imdb_id_valid(self):
        """Test IMDb ID validation with valid IDs."""
        valid_ids = ["tt1234567", "tt0123456", "tt9999999", "tt12345678", "tt123456789"]
        
        for imdb_id in valid_ids:
            # Should not raise exception
            self.client._validate_imdb_id(imdb_id)
    
    def test_validate_imdb_id_invalid(self):
        """Test IMDb ID validation with invalid IDs."""
        invalid_ids = [
            "1234567",      # Missing 'tt' prefix
            "tt123",        # Too short
            "tt123456a",    # Contains letter
            "TT1234567",    # Wrong case
            "",             # Empty
            "nm1234567"     # Name ID instead of title ID
        ]
        
        for imdb_id in invalid_ids:
            with pytest.raises(TMDBError, match="Invalid IMDb ID format"):
                self.client._validate_imdb_id(imdb_id)
    
    def test_build_url_basic_v3_api_key(self):
        """Test URL building with basic endpoint for v3 API key."""
        url = self.client._build_url("test/endpoint")
        assert url == "https://api.themoviedb.org/3/test/endpoint?api_key=test_tmdb_api_key"
    
    def test_build_url_basic_v4_bearer_token(self):
        """Test URL building with basic endpoint for v4 Bearer token."""
        # Create client with Bearer token (JWT)
        bearer_config = TMDBConfig(
            api_key="eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJ0ZXN0IiwibmJmIjowLCJzdWIiOiJ0ZXN0Iiwic2NvcGVzIjpbImFwaV9yZWFkIl0sInZlcnNpb24iOjF9.test",
            enabled=True
        )
        bearer_client = TMDBClient(bearer_config)
        
        url = bearer_client._build_url("test/endpoint")
        # v4 Bearer token should NOT include api_key in URL
        assert url == "https://api.themoviedb.org/3/test/endpoint"
    
    def test_build_url_with_params_v3_api_key(self):
        """Test URL building with query parameters for v3 API key."""
        params = {"param1": "value1", "param2": "value2"}
        url = self.client._build_url("test/endpoint", params)
        
        assert "https://api.themoviedb.org/3/test/endpoint" in url
        assert "param1=value1" in url
        assert "param2=value2" in url
        assert "api_key=test_tmdb_api_key" in url
    
    def test_build_url_with_params_v4_bearer_token(self):
        """Test URL building with query parameters for v4 Bearer token."""
        # Create client with Bearer token (JWT)
        bearer_config = TMDBConfig(
            api_key="eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJ0ZXN0IiwibmJmIjowLCJzdWIiOiJ0ZXN0Iiwic2NvcGVzIjpbImFwaV9yZWFkIl0sInZlcnNpb24iOjF9.test",
            enabled=True
        )
        bearer_client = TMDBClient(bearer_config)
        
        params = {"param1": "value1", "param2": "value2"}
        url = bearer_client._build_url("test/endpoint", params)
        
        assert "https://api.themoviedb.org/3/test/endpoint" in url
        assert "param1=value1" in url
        assert "param2=value2" in url
        # v4 Bearer token should NOT include api_key in URL
        assert "api_key=" not in url
    
    def test_headers_property_v3_api_key(self):
        """Test HTTP headers for v3 API key requests."""
        headers = self.client._headers
        
        assert "User-Agent" in headers
        assert "excludarr" in headers["User-Agent"]
        assert "Accept" in headers
        assert headers["Accept"] == "application/json"
        # v3 API key should not add Authorization header
        assert "Authorization" not in headers
    
    def test_headers_property_v4_bearer_token(self):
        """Test HTTP headers for v4 Bearer token requests."""
        # Create client with Bearer token (JWT)
        bearer_config = TMDBConfig(
            api_key="eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJ0ZXN0IiwibmJmIjowLCJzdWIiOiJ0ZXN0Iiwic2NvcGVzIjpbImFwaV9yZWFkIl0sInZlcnNpb24iOjF9.test",
            enabled=True
        )
        bearer_client = TMDBClient(bearer_config)
        
        headers = bearer_client._headers
        
        assert "User-Agent" in headers
        assert "excludarr" in headers["User-Agent"]
        assert "Accept" in headers
        assert headers["Accept"] == "application/json"
        # v4 Bearer token should add Authorization header
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer eyJ")


class TestTMDBClientRateLimiting:
    """Test TMDB client rate limiting functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = TMDBConfig(
            api_key="test_api_key", 
            rate_limit=2  # Low limit for testing
        )
        self.client = TMDBClient(self.config)
    
    @pytest.mark.asyncio
    async def test_rate_limiting_tracks_requests(self):
        """Test that rate limiting tracks request timestamps."""
        # Initially no requests tracked
        assert len(self.client._request_times) == 0
        
        with patch.object(self.client, '_make_http_request', new_callable=AsyncMock) as mock_http:
            mock_http.return_value = {"test": "data"}
            
            # Make a request
            await self.client._make_request("test")
            
            # Should have one timestamp tracked
            assert len(self.client._request_times) == 1
    
    @pytest.mark.asyncio
    async def test_rate_limiting_enforces_limit(self):
        """Test that rate limiting enforces the request limit."""
        with patch.object(self.client, '_make_http_request', new_callable=AsyncMock) as mock_http:
            mock_http.return_value = {"test": "data"}
            
            # Fill up the rate limit
            await self.client._make_request("test1")
            await self.client._make_request("test2")
            
            # Next request should trigger rate limiting
            with patch('asyncio.sleep') as mock_sleep:
                await self.client._make_request("test3")
                mock_sleep.assert_called_once()
    
    @pytest.mark.asyncio 
    async def test_rate_limiting_clears_old_requests(self):
        """Test that old request timestamps are cleaned up."""
        # Mock datetime to control time
        with patch('excludarr.tmdb_client.datetime') as mock_datetime:
            start_time = datetime.now()
            mock_datetime.now.return_value = start_time
            
            with patch.object(self.client, '_make_http_request', new_callable=AsyncMock) as mock_http:
                mock_http.return_value = {"test": "data"}
                
                # Make initial requests
                await self.client._make_request("test1")
                await self.client._make_request("test2")
                
                # Advance time beyond rate limit window
                mock_datetime.now.return_value = start_time + timedelta(seconds=15)
                
                # Make another request - should clear old timestamps
                await self.client._make_request("test3")
                
                # Should only have the latest request
                assert len(self.client._request_times) == 1


class TestTMDBClientProviderMapping:
    """Test TMDB provider mapping functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = TMDBConfig(api_key="test_key")
        self.client = TMDBClient(self.config)
    
    def test_normalize_provider_name(self):
        """Test provider name normalization."""
        test_cases = [
            ("Netflix", "netflix"),
            ("Amazon Prime Video", "amazon-prime"),
            ("Disney Plus", "disney-plus"),
            ("HBO Max", "hbo-max"),
            ("Apple TV+", "apple-tv"),
            ("Paramount+", "paramount-plus"),
            ("Test Provider Name", "test-provider-name")
        ]
        
        for input_name, expected in test_cases:
            result = self.client._normalize_provider_name(input_name)
            assert result == expected
    
    def test_extract_providers_from_response(self):
        """Test extracting and normalizing providers from TMDB response."""
        tmdb_response = {
            "results": {
                "US": {
                    "flatrate": [
                        {"provider_id": 8, "provider_name": "Netflix"},
                        {"provider_id": 119, "provider_name": "Amazon Prime Video"}
                    ],
                    "buy": [
                        {"provider_id": 2, "provider_name": "Apple iTunes"}
                    ]
                },
                "DE": {
                    "flatrate": [
                        {"provider_id": 119, "provider_name": "Amazon Prime Video"}
                    ]
                }
            }
        }
        
        result = self.client._extract_providers_from_response(tmdb_response)
        
        expected = {
            "US": ["amazon-prime", "apple-itunes", "netflix"],  # Sorted alphabetically
            "DE": ["amazon-prime"]
        }
        
        assert result == expected
    
    def test_extract_providers_empty_response(self):
        """Test extracting providers from empty response."""
        empty_response = {"results": {}}
        
        result = self.client._extract_providers_from_response(empty_response)
        
        assert result == {}
    
    def test_extract_providers_missing_countries(self):
        """Test extracting providers when specific countries missing."""
        partial_response = {
            "results": {
                "US": {
                    "flatrate": [
                        {"provider_id": 8, "provider_name": "Netflix"}
                    ]
                }
                # DE missing
            }
        }
        
        result = self.client._extract_providers_from_response(partial_response)
        
        expected = {
            "US": ["netflix"]
        }
        
        assert result == expected