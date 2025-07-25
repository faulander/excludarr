#!/usr/bin/env python3
"""Tests for mock Jellyseerr server."""

import pytest
import requests
import time
from unittest.mock import patch

from tests.mock_jellyseerr_server import MockJellyseerrServer
from excludarr.jellyseerr import JellyseerrClient
from excludarr.models import JellyseerrConfig


class TestMockJellyseerrServer:
    """Test mock Jellyseerr server functionality."""
    
    def test_server_startup_and_shutdown(self):
        """Test server can start and stop cleanly."""
        server = MockJellyseerrServer()
        assert not server._started
        
        server.start()
        assert server._started
        assert server.port > 0
        
        # Test basic connectivity
        response = requests.get(f"{server.base_url}/api/v1/auth/me", 
                              headers={"X-Api-Key": "test_key_1234567890"})
        assert response.status_code == 200
        
        server.stop()
        assert not server._started
    
    def test_context_manager(self):
        """Test server as context manager."""
        with MockJellyseerrServer() as server:
            assert server._started
            response = requests.get(f"{server.base_url}/api/v1/auth/me",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 200
        
        assert not server._started
    
    def test_authentication_endpoint(self):
        """Test authentication endpoint behavior."""
        with MockJellyseerrServer() as server:
            base_url = server.base_url
            
            # Test successful authentication
            response = requests.get(f"{base_url}/api/v1/auth/me",
                                  headers={"X-Api-Key": "valid_key"})
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == 1
            assert data["displayName"] == "Test User"
            
            # Test missing API key
            response = requests.get(f"{base_url}/api/v1/auth/me")
            assert response.status_code == 401
            
            # Test invalid API key
            response = requests.get(f"{base_url}/api/v1/auth/me",
                                  headers={"X-Api-Key": "invalid_key"})
            assert response.status_code == 403
    
    def test_series_lookup_success(self):
        """Test successful series lookup."""
        with MockJellyseerrServer() as server:
            base_url = server.base_url
            
            # Test Breaking Bad lookup
            response = requests.get(f"{base_url}/api/v1/tv/81189",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Breaking Bad"
            assert data["externalIds"]["tvdbId"] == 81189
            assert data["externalIds"]["imdbId"] == "tt0903747"
            assert len(data["watchProviders"]) == 2  # US and DE
            
            # Test Friends lookup
            response = requests.get(f"{base_url}/api/v1/tv/79168",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Friends"
    
    def test_series_lookup_not_found(self):
        """Test series lookup for non-existent series."""
        with MockJellyseerrServer() as server:
            base_url = server.base_url
            
            response = requests.get(f"{base_url}/api/v1/tv/999999",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 404
    
    def test_series_lookup_server_error(self):
        """Test series lookup that returns server error."""
        with MockJellyseerrServer() as server:
            base_url = server.base_url
            
            # The Office is configured to return HTTP 500
            response = requests.get(f"{base_url}/api/v1/tv/73244",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 500
    
    def test_series_lookup_timeout(self):
        """Test series lookup that times out."""
        with MockJellyseerrServer() as server:
            base_url = server.base_url
            
            # Stranger Things is configured to timeout
            # Use short timeout to avoid long test runtime
            with pytest.raises(requests.exceptions.Timeout):
                requests.get(f"{base_url}/api/v1/tv/305288",
                           headers={"X-Api-Key": "test_key_1234567890"},
                           timeout=5)
    
    def test_search_endpoint(self):
        """Test search endpoint functionality."""
        with MockJellyseerrServer() as server:
            base_url = server.base_url
            
            # Search by IMDB ID
            response = requests.get(f"{base_url}/api/v1/search?query=tt0903747",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) == 1
            result = data["results"][0]
            assert result["media_type"] == "tv"
            assert result["external_ids"]["tvdb_id"] == 81189
            assert result["external_ids"]["imdb_id"] == "tt0903747"
            
            # Search for non-existent IMDB ID
            response = requests.get(f"{base_url}/api/v1/search?query=tt9999999",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) == 0
    
    def test_custom_data_manipulation(self):
        """Test adding and modifying server data."""
        with MockJellyseerrServer() as server:
            base_url = server.base_url
            
            # Add custom series
            custom_series = {
                "name": "Custom Show",
                "externalIds": {"tvdbId": 555555, "imdbId": "tt5555555"},
                "watchProviders": [
                    {
                        "iso_3166_1": "US",
                        "flatrate": [
                            {"provider_id": 337, "provider_name": "Disney Plus"}
                        ]
                    }
                ]
            }
            
            server.add_series(555555, custom_series)
            server.add_imdb_mapping("tt5555555", 555555)
            
            # Test lookup of custom series
            response = requests.get(f"{base_url}/api/v1/tv/555555",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Custom Show"
            
            # Test search for custom series
            response = requests.get(f"{base_url}/api/v1/search?query=tt5555555",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 200
            data = response.json()
            assert len(data["results"]) == 1
    
    def test_data_reset(self):
        """Test data clearing and resetting."""
        with MockJellyseerrServer() as server:
            base_url = server.base_url
            
            # Add custom data
            server.add_series(777777, {"name": "Temp Show"})
            
            # Verify it exists
            response = requests.get(f"{base_url}/api/v1/tv/777777",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 200
            
            # Clear all data
            server.clear_data()
            
            # Verify custom data is gone
            response = requests.get(f"{base_url}/api/v1/tv/777777",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 404
            
            # Verify default data is also gone
            response = requests.get(f"{base_url}/api/v1/tv/81189",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 404
            
            # Reset to defaults
            server.reset_to_defaults()
            
            # Verify default data is back
            response = requests.get(f"{base_url}/api/v1/tv/81189",
                                  headers={"X-Api-Key": "test_key_1234567890"})
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Breaking Bad"


class TestJellyseerrClientWithMockServer:
    """Test JellyseerrClient integration with mock server."""
    
    def test_jellyseerr_client_with_mock_server(self):
        """Test JellyseerrClient works with mock server."""
        with MockJellyseerrServer() as server:
            config = JellyseerrConfig(
                url=server.base_url,
                api_key="test_key_1234567890"
            )
            
            with JellyseerrClient(config) as client:
                # Test connection
                assert client.test_connection() is True
                
                # Test series lookup
                result = client.get_series_availability(tvdb_id=81189)
                assert result is not None
                assert result["series_name"] == "Breaking Bad"
                assert len(result["providers"]) > 0
                
                # Check provider mapping
                providers = result["providers"]
                us_netflix = None
                de_amazon = None
                
                for provider in providers:
                    if (provider["country"] == "US" and 
                        provider["mapped_name"] == "netflix"):
                        us_netflix = provider
                    elif (provider["country"] == "DE" and 
                          provider["mapped_name"] == "amazon-prime"):
                        de_amazon = provider
                
                assert us_netflix is not None
                assert de_amazon is not None
                assert us_netflix["provider_name"] == "Netflix"
                assert de_amazon["provider_name"] == "Amazon Prime Video"
    
    def test_jellyseerr_client_error_handling_with_mock(self):
        """Test JellyseerrClient error handling with mock server."""
        with MockJellyseerrServer() as server:
            config = JellyseerrConfig(
                url=server.base_url,
                api_key="test_key_1234567890"
            )
            
            with JellyseerrClient(config) as client:
                # Test series that returns HTTP 500
                result = client.get_series_availability(tvdb_id=73244)
                assert result is None  # Should handle error gracefully
                
                # Test non-existent series
                result = client.get_series_availability(tvdb_id=999999)
                assert result is None
    
    def test_jellyseerr_client_imdb_fallback_with_mock(self):
        """Test JellyseerrClient IMDB fallback with mock server."""
        with MockJellyseerrServer() as server:
            config = JellyseerrConfig(
                url=server.base_url,
                api_key="test_key_1234567890"
            )
            
            with JellyseerrClient(config) as client:
                # Test IMDB lookup
                result = client.get_series_availability(imdb_id="tt0903747")
                assert result is not None
                assert result["series_name"] == "Breaking Bad"
    
    def test_jellyseerr_client_timeout_handling_with_mock(self):
        """Test JellyseerrClient timeout handling with mock server."""
        with MockJellyseerrServer() as server:
            config = JellyseerrConfig(
                url=server.base_url,
                api_key="test_key_1234567890",
                timeout=5  # Minimum timeout for validation
            )
            
            with JellyseerrClient(config) as client:
                # Test series that times out (Stranger Things)
                result = client.get_series_availability(tvdb_id=305288)
                assert result is None  # Should handle timeout gracefully