#!/usr/bin/env python3
"""Integration tests for complete Jellyseerr workflow."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import time

from excludarr.availability import AvailabilityChecker
from excludarr.availability_cache import AvailabilityCache
from excludarr.jellyseerr import JellyseerrClient
from excludarr.models import StreamingProvider, JellyseerrConfig
from excludarr.providers import ProviderManager
from excludarr.config import ConfigManager


class TestJellyseerrIntegration:
    """Integration tests for complete Jellyseerr workflow."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        yield temp_file.name
        Path(temp_file.name).unlink(missing_ok=True)
    
    @pytest.fixture
    def temp_config_file(self):
        """Create temporary config file."""
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yml')
        config_content = """
sonarr:
  url: "http://localhost:8989"
  api_key: "testapikey1234567890abcdef123456"

jellyseerr:
  url: "http://localhost:5055"
  api_key: "test_api_key_jellyseerr_1234567890"
  timeout: 30
  cache_ttl: 300

streaming_providers:
  - name: "netflix"
    country: "US"
  - name: "amazon-prime"
    country: "DE"
  - name: "disney-plus"
    country: "US"

sync:
  action: "unmonitor"
  dry_run: true
  exclude_recent_days: 7
"""
        temp_file.write(config_content)
        temp_file.close()
        yield temp_file.name
        Path(temp_file.name).unlink(missing_ok=True)
    
    @pytest.fixture
    def mock_jellyseerr_responses(self):
        """Mock Jellyseerr API responses for different scenarios."""
        return {
            "auth_success": {"id": 1, "displayName": "Test User", "email": "test@example.com"},
            "series_breaking_bad": {
                "name": "Breaking Bad",
                "externalIds": {"tvdbId": 81189, "imdbId": "tt0903747"},
                "watchProviders": [
                    {
                        "iso_3166_1": "US",
                        "flatrate": [
                            {"provider_id": 8, "provider_name": "Netflix"}
                        ]
                    },
                    {
                        "iso_3166_1": "DE", 
                        "flatrate": [
                            {"provider_id": 119, "provider_name": "Amazon Prime Video"}
                        ]
                    }
                ]
            },
            "series_office": {
                "name": "The Office",
                "externalIds": {"tvdbId": 73244, "imdbId": "tt0386676"},
                "watchProviders": [
                    {
                        "iso_3166_1": "US",
                        "flatrate": [
                            {"provider_id": 8, "provider_name": "Netflix"},
                            {"provider_id": 15, "provider_name": "Hulu"}
                        ]
                    }
                ]
            },
            "series_not_found": None
        }
    
    def test_end_to_end_config_loading_and_initialization(self, temp_config_file, temp_db):
        """Test complete workflow from config loading to availability checker initialization."""
        
        # Load configuration
        config_manager = ConfigManager(temp_config_file)
        config = config_manager.load_config()
        
        # Verify configuration loaded correctly
        assert config.jellyseerr is not None
        assert str(config.jellyseerr.url).rstrip('/') == "http://localhost:5055"
        assert len(config.streaming_providers) == 3
        
        # Create mock provider manager
        provider_manager = Mock(spec=ProviderManager)
        provider_manager.validate_provider.return_value = (True, None)
        provider_manager.get_provider_display_name.side_effect = lambda name: name.title().replace('-', ' ')
        
        # Test AvailabilityChecker initialization with real config
        with patch('excludarr.availability.JellyseerrClient') as mock_jellyseerr:
            mock_client = Mock()
            mock_client.test_connection.return_value = True
            mock_jellyseerr.return_value = mock_client
            
            checker = AvailabilityChecker(
                provider_manager=provider_manager,
                streaming_providers=config.streaming_providers,
                jellyseerr_config=config.jellyseerr,
                cache_db_path=temp_db
            )
            
            # Verify all components initialized
            assert checker.jellyseerr_client is not None
            assert checker.cache is not None
            assert len(checker.streaming_providers) == 3
            
            # Verify Jellyseerr client was created with correct config
            mock_jellyseerr.assert_called_once_with(config.jellyseerr)
            mock_client.test_connection.assert_called_once()
    
    def test_complete_series_availability_workflow(self, temp_db, mock_jellyseerr_responses):
        """Test complete workflow from series lookup to availability results."""
        
        # Create components
        jellyseerr_config = JellyseerrConfig(
            url="http://localhost:5055",
            api_key="test_api_key",
            timeout=30,
            cache_ttl=300
        )
        
        streaming_providers = [
            StreamingProvider(name="netflix", country="US"),
            StreamingProvider(name="amazon-prime", country="DE"),
            StreamingProvider(name="disney-plus", country="US")
        ]
        
        provider_manager = Mock(spec=ProviderManager)
        provider_manager.validate_provider.return_value = (True, None)
        provider_manager.get_provider_display_name.side_effect = lambda name: name.title().replace('-', ' ')
        
        # Create mock Jellyseerr client
        mock_jellyseerr_client = Mock(spec=JellyseerrClient)
        mock_jellyseerr_client.test_connection.return_value = True
        
        # Mock series lookup to return Breaking Bad data
        mock_jellyseerr_client.get_series_availability.return_value = {
            "series_name": "Breaking Bad",
            "tvdb_id": 81189,
            "imdb_id": "tt0903747",
            "providers": [
                {
                    "country": "US",
                    "provider_id": 8,
                    "provider_name": "Netflix",
                    "provider_type": "flatrate",
                    "mapped_name": "netflix"
                },
                {
                    "country": "DE",
                    "provider_id": 119,
                    "provider_name": "Amazon Prime Video", 
                    "provider_type": "flatrate",
                    "mapped_name": "amazon-prime"
                }
            ],
            "timestamp": time.time()
        }
        
        # Initialize availability checker
        with patch('excludarr.availability.JellyseerrClient', return_value=mock_jellyseerr_client):
            checker = AvailabilityChecker(
                provider_manager=provider_manager,
                streaming_providers=streaming_providers,
                jellyseerr_config=jellyseerr_config,
                cache_db_path=temp_db
            )
        
        # Test series availability check
        series = {
            "title": "Breaking Bad",
            "tvdbId": 81189,
            "imdbId": "tt0903747",
            "seasons": [
                {"seasonNumber": 1, "monitored": True},
                {"seasonNumber": 2, "monitored": True}
            ]
        }
        
        result = checker.check_series_availability(series)
        
        # Verify results
        assert "netflix" in result
        assert "amazon-prime" in result
        assert "disney-plus" in result
        
        # Netflix should be available (US match)
        netflix_result = result["netflix"]
        assert netflix_result["available"] is True
        assert netflix_result["country"] == "US"
        assert netflix_result["source"] in ["jellyseerr_tvdb", "cache"]
        assert netflix_result["seasons"] == [1, 2]
        
        # Amazon Prime should be available (DE match)
        amazon_result = result["amazon-prime"]
        assert amazon_result["available"] is True
        assert amazon_result["country"] == "DE"
        
        # Disney+ should not be available (no match)
        disney_result = result["disney-plus"]
        assert disney_result["available"] is False
        
        # Verify API was called
        mock_jellyseerr_client.get_series_availability.assert_called_once_with(tvdb_id=81189)
    
    def test_caching_workflow_integration(self, temp_db):
        """Test that caching works correctly in the complete workflow."""
        
        jellyseerr_config = JellyseerrConfig(
            url="http://localhost:5055",
            api_key="test_api_key",
            timeout=30,
            cache_ttl=300
        )
        
        streaming_providers = [
            StreamingProvider(name="netflix", country="US")
        ]
        
        provider_manager = Mock(spec=ProviderManager)
        provider_manager.validate_provider.return_value = (True, None)
        provider_manager.get_provider_display_name.return_value = "Netflix"
        
        # Create mock Jellyseerr client
        mock_jellyseerr_client = Mock(spec=JellyseerrClient)
        mock_jellyseerr_client.test_connection.return_value = True
        mock_jellyseerr_client.get_series_availability.return_value = {
            "series_name": "Breaking Bad",
            "providers": [
                {"country": "US", "provider_name": "Netflix", "mapped_name": "netflix"}
            ],
            "timestamp": time.time()
        }
        
        # Initialize checker
        with patch('excludarr.availability.JellyseerrClient', return_value=mock_jellyseerr_client):
            checker = AvailabilityChecker(
                provider_manager=provider_manager,
                streaming_providers=streaming_providers,
                jellyseerr_config=jellyseerr_config,
                cache_db_path=temp_db
            )
        
        series = {"title": "Breaking Bad", "tvdbId": 81189, "seasons": []}
        
        # First call - should hit API and cache result
        result1 = checker.check_series_availability(series)
        assert result1["netflix"]["available"] is True
        assert mock_jellyseerr_client.get_series_availability.call_count == 1
        
        # Second call - should hit cache
        result2 = checker.check_series_availability(series)
        assert result2["netflix"]["available"] is True
        assert result2["netflix"]["source"] == "cache"
        # API should not be called again
        assert mock_jellyseerr_client.get_series_availability.call_count == 1
        
        # Verify cache statistics
        stats = checker.get_cache_statistics()
        assert stats["hit_count"] >= 1
        assert stats["miss_count"] >= 1
        assert stats["hit_rate"] > 0
    
    def test_circuit_breaker_integration_workflow(self, temp_db):
        """Test circuit breaker integration in the complete workflow."""
        
        jellyseerr_config = JellyseerrConfig(
            url="http://localhost:5055",
            api_key="test_api_key",
            timeout=30,
            cache_ttl=300
        )
        
        streaming_providers = [
            StreamingProvider(name="netflix", country="US")
        ]
        
        provider_manager = Mock(spec=ProviderManager)
        provider_manager.validate_provider.return_value = (True, None)
        provider_manager.get_provider_display_name.return_value = "Netflix"
        
        # Create mock Jellyseerr client that always fails
        mock_jellyseerr_client = Mock(spec=JellyseerrClient)
        mock_jellyseerr_client.test_connection.return_value = True
        mock_jellyseerr_client.get_series_availability.side_effect = Exception("API Error")
        
        # Initialize checker
        with patch('excludarr.availability.JellyseerrClient', return_value=mock_jellyseerr_client):
            checker = AvailabilityChecker(
                provider_manager=provider_manager,
                streaming_providers=streaming_providers,
                jellyseerr_config=jellyseerr_config,
                cache_db_path=temp_db
            )
        
        # Trigger multiple failures with different TVDB IDs to open circuit breaker
        tvdb_ids = [81189, 73244, 79168, 305288]  # Different IDs to avoid blacklisting
        
        for i, tvdb_id in enumerate(tvdb_ids):
            series = {"title": f"Test Series {i}", "tvdbId": tvdb_id, "seasons": []}
            result = checker.check_series_availability(series)
            
            # After circuit breaker opens (on 4th call), should detect circuit breaker
            if i == 3:  # 4th call (0-indexed)
                assert result["netflix"]["circuit_breaker_open"] is True
            else:
                # First 3 calls should fallback to mock data
                assert result["netflix"]["source"] == "mock"
        
        # Verify circuit breaker is open
        circuit_breaker = checker.cache.get_circuit_breaker()
        assert circuit_breaker.state == "open"
        
        # Next call should not hit API due to circuit breaker
        mock_jellyseerr_client.get_series_availability.reset_mock()
        result = checker.check_series_availability(series)
        
        # Should not call API when circuit breaker is open
        mock_jellyseerr_client.get_series_availability.assert_not_called()
        assert result["netflix"]["circuit_breaker_open"] is True
    
    def test_blacklist_integration_workflow(self, temp_db):
        """Test blacklist integration in the complete workflow."""
        
        jellyseerr_config = JellyseerrConfig(
            url="http://localhost:5055",
            api_key="test_api_key", 
            timeout=30,
            cache_ttl=300
        )
        
        streaming_providers = [
            StreamingProvider(name="netflix", country="US")
        ]
        
        provider_manager = Mock(spec=ProviderManager)
        provider_manager.validate_provider.return_value = (True, None)
        provider_manager.get_provider_display_name.return_value = "Netflix"
        
        # Create mock Jellyseerr client that fails for specific TVDB ID
        mock_jellyseerr_client = Mock(spec=JellyseerrClient)
        mock_jellyseerr_client.test_connection.return_value = True
        mock_jellyseerr_client.get_series_availability.side_effect = Exception("HTTP 500")
        
        # Initialize checker
        with patch('excludarr.availability.JellyseerrClient', return_value=mock_jellyseerr_client):
            checker = AvailabilityChecker(
                provider_manager=provider_manager,
                streaming_providers=streaming_providers,
                jellyseerr_config=jellyseerr_config,
                cache_db_path=temp_db
            )
        
        series = {"title": "Breaking Bad", "tvdbId": 81189, "seasons": []}
        
        # First call should fail and blacklist the TVDB ID
        result1 = checker.check_series_availability(series)
        assert result1["netflix"]["source"] == "mock"  # Fallback to mock
        
        # Verify TVDB ID is blacklisted
        assert checker.cache.is_blacklisted(81189)
        
        # Reset mock to track next calls
        mock_jellyseerr_client.get_series_availability.reset_mock()
        
        # Second call should skip API due to blacklist
        result2 = checker.check_series_availability(series)
        mock_jellyseerr_client.get_series_availability.assert_not_called()
        assert result2["netflix"]["blacklisted"] is True
    
    def test_availability_sources_integration(self, temp_db):
        """Test availability sources testing integration."""
        
        jellyseerr_config = JellyseerrConfig(
            url="http://localhost:5055",
            api_key="test_api_key",
            timeout=30,
            cache_ttl=300
        )
        
        streaming_providers = [
            StreamingProvider(name="netflix", country="US")
        ]
        
        provider_manager = Mock(spec=ProviderManager)
        provider_manager.validate_provider.return_value = (True, None)
        provider_manager.get_provider_display_name.return_value = "Netflix"
        provider_manager.get_all_providers.return_value = ["netflix", "amazon-prime"]
        
        mock_jellyseerr_client = Mock(spec=JellyseerrClient)
        mock_jellyseerr_client.test_connection.return_value = True
        
        # Initialize checker
        with patch('excludarr.availability.JellyseerrClient', return_value=mock_jellyseerr_client):
            checker = AvailabilityChecker(
                provider_manager=provider_manager,
                streaming_providers=streaming_providers,
                jellyseerr_config=jellyseerr_config,
                cache_db_path=temp_db
            )
        
        # Test availability sources
        sources_result = checker.test_availability_sources()
        
        # Verify all components are tested
        assert "provider_manager" in sources_result
        assert "jellyseerr" in sources_result
        assert "cache" in sources_result
        assert "circuit_breaker" in sources_result
        
        # All should be available
        assert sources_result["provider_manager"]["available"] is True
        assert sources_result["jellyseerr"]["available"] is True
        assert sources_result["cache"]["available"] is True
        assert sources_result["circuit_breaker"]["state"] == "closed"
    
    def test_provider_filtering_edge_cases(self, temp_db):
        """Test provider filtering with various edge cases."""
        
        jellyseerr_config = JellyseerrConfig(
            url="http://localhost:5055",
            api_key="test_api_key",
            timeout=30,
            cache_ttl=300
        )
        
        streaming_providers = [
            StreamingProvider(name="netflix", country="US"),
            StreamingProvider(name="amazon-prime", country="DE")
        ]
        
        provider_manager = Mock(spec=ProviderManager)
        provider_manager.validate_provider.return_value = (True, None)
        provider_manager.get_provider_display_name.side_effect = lambda name: name.title().replace('-', ' ')
        
        # Mock Jellyseerr client with edge case data
        mock_jellyseerr_client = Mock(spec=JellyseerrClient)
        mock_jellyseerr_client.test_connection.return_value = True
        mock_jellyseerr_client.get_series_availability.return_value = {
            "series_name": "Test Series",
            "providers": [
                # Valid provider
                {"country": "US", "provider_name": "Netflix", "mapped_name": "netflix"},
                # Wrong country
                {"country": "UK", "provider_name": "Netflix", "mapped_name": "netflix"},
                # Invalid data (None name)
                {"country": "US", "provider_name": None, "mapped_name": ""},
                # Empty country
                {"country": "", "provider_name": "Amazon Prime", "mapped_name": "amazon-prime"},
                # Different provider not in config
                {"country": "US", "provider_name": "Hulu", "mapped_name": "hulu"}
            ],
            "timestamp": time.time()
        }
        
        # Initialize checker
        with patch('excludarr.availability.JellyseerrClient', return_value=mock_jellyseerr_client):
            checker = AvailabilityChecker(
                provider_manager=provider_manager,
                streaming_providers=streaming_providers,
                jellyseerr_config=jellyseerr_config,
                cache_db_path=temp_db
            )
        
        series = {"title": "Test Series", "tvdbId": 12345, "seasons": []}
        result = checker.check_series_availability(series)
        
        # Only valid matches should be available
        assert result["netflix"]["available"] is True  # US match
        assert result["netflix"]["country"] == "US"
        
        assert result["amazon-prime"]["available"] is False  # No valid match
        assert result["amazon-prime"]["country"] == "DE"
    
    def test_concurrent_requests_integration(self, temp_db):
        """Test concurrent requests in integrated workflow."""
        import threading
        import queue
        
        jellyseerr_config = JellyseerrConfig(
            url="http://localhost:5055",
            api_key="test_api_key",
            timeout=30,
            cache_ttl=300
        )
        
        streaming_providers = [
            StreamingProvider(name="netflix", country="US")
        ]
        
        provider_manager = Mock(spec=ProviderManager)
        provider_manager.validate_provider.return_value = (True, None)
        provider_manager.get_provider_display_name.return_value = "Netflix"
        
        mock_jellyseerr_client = Mock(spec=JellyseerrClient)
        mock_jellyseerr_client.test_connection.return_value = True
        mock_jellyseerr_client.get_series_availability.return_value = {
            "series_name": "Breaking Bad",
            "providers": [
                {"country": "US", "provider_name": "Netflix", "mapped_name": "netflix"}
            ],
            "timestamp": time.time()
        }
        
        # Initialize checker
        with patch('excludarr.availability.JellyseerrClient', return_value=mock_jellyseerr_client):
            checker = AvailabilityChecker(
                provider_manager=provider_manager,
                streaming_providers=streaming_providers,
                jellyseerr_config=jellyseerr_config,
                cache_db_path=temp_db
            )
        
        results = queue.Queue()
        series = {"title": "Breaking Bad", "tvdbId": 81189, "seasons": []}
        
        def worker():
            try:
                result = checker.check_series_availability(series)
                results.put(("success", result))
            except Exception as e:
                results.put(("error", str(e)))
        
        # Start multiple concurrent threads
        threads = []
        for _ in range(5):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Verify all succeeded
        success_count = 0
        while not results.empty():
            status, result = results.get()
            if status == "success":
                success_count += 1
                assert result["netflix"]["available"] is True
        
        assert success_count == 5