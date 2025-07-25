"""Tests for Jellyseerr API client functionality."""

import pytest
import httpx
import respx
from unittest.mock import Mock, patch
from pydantic import ValidationError

from excludarr.jellyseerr import JellyseerrClient, JellyseerrError
from excludarr.models import StreamingProvider, JellyseerrConfig


class TestJellyseerrConfig:
    """Test Jellyseerr configuration model."""
    
    def test_jellyseerr_config_valid(self):
        """Test valid Jellyseerr configuration."""
        config = JellyseerrConfig(
            url="http://localhost:5055",
            api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
            timeout=30,
            cache_ttl=300
        )
        
        assert str(config.url) == "http://localhost:5055/"
        assert config.api_key == "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        assert config.timeout == 30
        assert config.cache_ttl == 300

    def test_jellyseerr_config_invalid_url(self):
        """Test invalid URL in Jellyseerr configuration."""
        with pytest.raises(ValidationError):
            JellyseerrConfig(
                url="not-a-valid-url",
                api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
            )

    def test_jellyseerr_config_short_api_key(self):
        """Test API key too short."""
        with pytest.raises(ValidationError):
            JellyseerrConfig(
                url="http://localhost:5055",
                api_key="short"
            )

    def test_jellyseerr_config_defaults(self):
        """Test default values in Jellyseerr configuration."""
        config = JellyseerrConfig(
            url="http://localhost:5055",
            api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        )
        
        assert config.timeout == 30
        assert config.cache_ttl == 300


class TestJellyseerrClient:
    """Test Jellyseerr API client."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = JellyseerrConfig(
            url="http://localhost:5055",
            api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        )
        self.client = JellyseerrClient(self.config)

    def test_client_initialization(self):
        """Test client initialization."""
        assert self.client.config == self.config
        assert self.client.base_url == "http://localhost:5055/api/v1"
        assert "X-Api-Key" in self.client.session.headers
        assert self.client.session.headers["X-Api-Key"] == self.config.api_key

    @respx.mock
    def test_test_connection_success(self):
        """Test successful connection test."""
        respx.get("http://localhost:5055/api/v1/auth/me").mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "displayName": "Test User", "permissions": 2}
            )
        )
        
        result = self.client.test_connection()
        assert result is True

    @respx.mock
    def test_test_connection_invalid_api_key(self):
        """Test connection test with invalid API key."""
        respx.get("http://localhost:5055/api/v1/auth/me").mock(
            return_value=httpx.Response(
                403,
                json={"message": "Access denied"}
            )
        )
        
        with pytest.raises(JellyseerrError) as exc_info:
            self.client.test_connection()
        assert "authentication failed" in str(exc_info.value).lower()

    @respx.mock
    def test_test_connection_server_error(self):
        """Test connection test with server error."""
        respx.get("http://localhost:5055/api/v1/auth/me").mock(
            return_value=httpx.Response(
                500,
                json={"message": "Internal server error"}
            )
        )
        
        with pytest.raises(JellyseerrError) as exc_info:
            self.client.test_connection()
        assert "500" in str(exc_info.value)

    @respx.mock
    def test_get_series_availability_by_tvdb_success(self):
        """Test successful series availability lookup by TVDB ID."""
        tvdb_id = 81189  # Breaking Bad
        
        # Mock the series endpoint
        respx.get(f"http://localhost:5055/api/v1/tv/{tvdb_id}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1396,
                    "name": "Breaking Bad",
                    "externalIds": {"tvdbId": tvdb_id},
                    "watchProviders": [
                        {
                            "iso_3166_1": "US",
                            "link": "https://www.netflix.com/title/70143836",
                            "flatrate": [
                                {
                                    "logo_path": "/netflix.jpg",
                                    "provider_id": 8,
                                    "provider_name": "Netflix"
                                }
                            ]
                        },
                        {
                            "iso_3166_1": "DE", 
                            "link": "https://www.netflix.com/title/70143836",
                            "flatrate": [
                                {
                                    "logo_path": "/netflix.jpg",
                                    "provider_id": 8,
                                    "provider_name": "Netflix"
                                }
                            ]
                        }
                    ]
                }
            )
        )
        
        availability = self.client.get_series_availability(tvdb_id=tvdb_id)
        
        assert availability is not None
        assert availability["series_name"] == "Breaking Bad"
        assert availability["tvdb_id"] == tvdb_id
        assert len(availability["providers"]) == 2
        
        # Check US provider
        us_provider = next(p for p in availability["providers"] if p["country"] == "US")
        assert us_provider["provider_name"] == "Netflix"
        assert us_provider["provider_id"] == 8
        
        # Check DE provider
        de_provider = next(p for p in availability["providers"] if p["country"] == "DE")
        assert de_provider["provider_name"] == "Netflix"
        assert de_provider["provider_id"] == 8

    @respx.mock
    def test_get_series_availability_not_found(self):
        """Test series availability lookup for non-existent series."""
        tvdb_id = 99999
        
        respx.get(f"http://localhost:5055/api/v1/tv/{tvdb_id}").mock(
            return_value=httpx.Response(
                404,
                json={"message": "Not Found"}
            )
        )
        
        availability = self.client.get_series_availability(tvdb_id=tvdb_id)
        assert availability is None

    @respx.mock
    def test_get_series_availability_by_imdb_success(self):
        """Test successful series availability lookup by IMDB ID."""
        imdb_id = "tt0903747"  # Breaking Bad
        tvdb_id = 81189
        
        # Mock the search endpoint to find by IMDB
        respx.get("http://localhost:5055/api/v1/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 1396,
                            "name": "Breaking Bad",
                            "media_type": "tv",
                            "external_ids": {"imdb_id": imdb_id, "tvdb_id": tvdb_id}
                        }
                    ]
                }
            )
        )
        
        # Mock the detailed lookup
        respx.get(f"http://localhost:5055/api/v1/tv/{tvdb_id}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1396,
                    "name": "Breaking Bad",
                    "externalIds": {"tvdbId": tvdb_id, "imdbId": imdb_id},
                    "watchProviders": [
                        {
                            "iso_3166_1": "US",
                            "flatrate": [
                                {
                                    "provider_id": 8,
                                    "provider_name": "Netflix"
                                }
                            ]
                        }
                    ]
                }
            )
        )
        
        availability = self.client.get_series_availability(imdb_id=imdb_id)
        
        assert availability is not None
        assert availability["series_name"] == "Breaking Bad"
        assert availability["imdb_id"] == imdb_id
        assert availability["tvdb_id"] == tvdb_id

    def test_get_series_availability_no_identifiers(self):
        """Test series availability lookup without identifiers."""
        with pytest.raises(ValueError) as exc_info:
            self.client.get_series_availability()
        assert "at least one identifier" in str(exc_info.value).lower()

    @respx.mock 
    def test_api_request_retry_on_failure(self):
        """Test API request retry mechanism."""
        # First call fails, second succeeds
        respx.get("http://localhost:5055/api/v1/auth/me").mock(
            side_effect=[
                httpx.Response(503, json={"message": "Service unavailable"}),
                httpx.Response(200, json={"id": 1, "displayName": "Test User"})
            ]
        )
        
        result = self.client.test_connection()
        assert result is True

    @respx.mock
    def test_api_request_max_retries_exceeded(self):
        """Test API request when max retries are exceeded."""
        # All calls fail
        respx.get("http://localhost:5055/api/v1/auth/me").mock(
            return_value=httpx.Response(503, json={"message": "Service unavailable"})
        )
        
        with pytest.raises(JellyseerrError) as exc_info:
            self.client.test_connection()
        assert "500" in str(exc_info.value) or "503" in str(exc_info.value)

    @respx.mock
    def test_rate_limiting_handling(self):
        """Test handling of rate limiting responses."""
        respx.get("http://localhost:5055/api/v1/auth/me").mock(
            return_value=httpx.Response(
                429, 
                json={"message": "Rate limit exceeded"},
                headers={"Retry-After": "60"}
            )
        )
        
        with pytest.raises(JellyseerrError) as exc_info:
            self.client.test_connection()
        assert "rate limit" in str(exc_info.value).lower()

    def test_provider_mapping(self):
        """Test provider name mapping between Jellyseerr and internal names."""
        # Test mapping common provider names
        assert self.client._map_provider_name("Netflix") == "netflix"
        assert self.client._map_provider_name("Amazon Prime Video") == "amazon-prime"
        assert self.client._map_provider_name("Disney Plus") == "disney-plus"
        assert self.client._map_provider_name("HBO Max") == "hbo-max"
        assert self.client._map_provider_name("Hulu") == "hulu"
        
        # Test unknown provider
        assert self.client._map_provider_name("Unknown Service") == "unknown-service"

    def test_filter_providers_by_region(self):
        """Test filtering providers by configured regions."""
        providers = [
            {
                "country": "US",
                "provider_name": "Netflix",
                "provider_id": 8,
                "mapped_name": "netflix"
            },
            {
                "country": "DE", 
                "provider_name": "Netflix",
                "provider_id": 8,
                "mapped_name": "netflix"
            },
            {
                "country": "UK",
                "provider_name": "Netflix", 
                "provider_id": 8,
                "mapped_name": "netflix"
            }
        ]
        
        configured_providers = [
            StreamingProvider(name="netflix", country="US"),
            StreamingProvider(name="netflix", country="DE")
        ]
        
        filtered = self.client._filter_providers_by_region(providers, configured_providers)
        
        assert len(filtered) == 2
        countries = [p["country"] for p in filtered]
        assert "US" in countries
        assert "DE" in countries
        assert "UK" not in countries

    @respx.mock
    def test_connection_timeout(self):
        """Test connection timeout handling."""
        respx.get("http://localhost:5055/api/v1/auth/me").mock(
            side_effect=httpx.ConnectError("Connection timeout")
        )
        
        with pytest.raises(JellyseerrError) as exc_info:
            self.client.test_connection()
        assert "connection" in str(exc_info.value).lower()


class TestJellyseerrIntegration:
    """Test Jellyseerr integration scenarios."""
    
    def test_availability_result_structure(self):
        """Test structure of availability results."""
        config = JellyseerrConfig(
            url="http://localhost:5055",
            api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        )
        client = JellyseerrClient(config)
        
        # Test empty result structure
        result = client._build_availability_result(
            series_name="Test Series",
            tvdb_id=12345,
            imdb_id="tt1234567",
            providers=[]
        )
        
        expected_keys = ["series_name", "tvdb_id", "imdb_id", "providers", "timestamp"]
        for key in expected_keys:
            assert key in result
        
        assert result["series_name"] == "Test Series"
        assert result["tvdb_id"] == 12345
        assert result["imdb_id"] == "tt1234567"
        assert result["providers"] == []
        assert isinstance(result["timestamp"], float)