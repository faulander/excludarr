#!/usr/bin/env python3
"""Tests for enhanced AvailabilityChecker with Jellyseerr integration."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import tempfile
from pathlib import Path

from excludarr.availability import AvailabilityChecker, AvailabilityError
from excludarr.availability_cache import AvailabilityCache, CircuitBreakerError
from excludarr.jellyseerr import JellyseerrClient, JellyseerrError
from excludarr.models import StreamingProvider, JellyseerrConfig
from excludarr.providers import ProviderManager


class TestEnhancedAvailabilityChecker:
    """Test enhanced AvailabilityChecker with Jellyseerr integration."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        yield temp_file.name
        Path(temp_file.name).unlink(missing_ok=True)
    
    @pytest.fixture
    def mock_provider_manager(self):
        """Create mock provider manager."""
        manager = Mock(spec=ProviderManager)
        manager.validate_provider.return_value = (True, None)
        manager.get_provider_display_name.side_effect = lambda name: name.title().replace('-', ' ')
        manager.get_all_providers.return_value = ["netflix", "amazon-prime", "disney-plus"]
        return manager
    
    @pytest.fixture
    def streaming_providers(self):
        """Create test streaming providers."""
        return [
            StreamingProvider(name="netflix", country="US"),
            StreamingProvider(name="amazon-prime", country="DE"),
            StreamingProvider(name="disney-plus", country="US")
        ]
    
    @pytest.fixture
    def jellyseerr_config(self):
        """Create test Jellyseerr config."""
        return JellyseerrConfig(
            url="http://localhost:5055",
            api_key="test_api_key_1234567890",
            timeout=30,
            cache_ttl=300
        )
    
    @pytest.fixture
    def mock_jellyseerr_client(self):
        """Create mock Jellyseerr client."""
        client = Mock(spec=JellyseerrClient)
        client.test_connection.return_value = True
        client.get_series_availability.return_value = {
            "series_name": "Breaking Bad",
            "tvdb_id": 81189,
            "imdb_id": "tt0903747",
            "providers": [
                {
                    "country": "US",
                    "provider_name": "Netflix",
                    "provider_type": "flatrate",
                    "mapped_name": "netflix"
                },
                {
                    "country": "DE", 
                    "provider_name": "Amazon Prime Video",
                    "provider_type": "flatrate",
                    "mapped_name": "amazon-prime"
                }
            ]
        }
        return client
    
    @pytest.fixture
    def availability_cache(self, temp_db):
        """Create availability cache instance."""
        return AvailabilityCache(db_path=temp_db, default_ttl=300)
    
    @pytest.fixture
    def enhanced_checker(self, mock_provider_manager, streaming_providers, mock_jellyseerr_client, availability_cache):
        """Create enhanced availability checker."""
        checker = AvailabilityChecker(mock_provider_manager, streaming_providers)
        checker.jellyseerr_client = mock_jellyseerr_client
        checker.cache = availability_cache
        return checker
    
    def test_enhanced_checker_initialization_with_jellyseerr(self, mock_provider_manager, streaming_providers, jellyseerr_config, temp_db):
        """Test enhanced checker initialization with Jellyseerr."""
        with patch('excludarr.availability.JellyseerrClient') as mock_client_class, \
             patch('excludarr.availability.AvailabilityCache') as mock_cache_class:
            
            mock_client = Mock()
            mock_client.test_connection.return_value = True
            mock_client_class.return_value = mock_client
            
            mock_cache = Mock()
            mock_cache_class.return_value = mock_cache
            
            checker = AvailabilityChecker(
                provider_manager=mock_provider_manager,
                streaming_providers=streaming_providers,
                jellyseerr_config=jellyseerr_config,
                cache_db_path=temp_db
            )
            
            # Verify Jellyseerr client was created and tested
            mock_client_class.assert_called_once_with(jellyseerr_config)
            mock_client.test_connection.assert_called_once()
            
            # Verify cache was initialized
            mock_cache_class.assert_called_once_with(
                db_path=temp_db, 
                default_ttl=300, 
                cleanup_interval=3600, 
                blacklist_threshold=1
            )
            
            assert checker.jellyseerr_client == mock_client
            assert checker.cache == mock_cache
    
    def test_enhanced_checker_initialization_jellyseerr_failure(self, mock_provider_manager, streaming_providers, jellyseerr_config, temp_db):
        """Test initialization when Jellyseerr connection fails."""
        with patch('excludarr.availability.JellyseerrClient') as mock_client_class:
            mock_client = Mock()
            mock_client.test_connection.side_effect = JellyseerrError("Connection failed")
            mock_client_class.return_value = mock_client
            
            # Should log warning but not fail initialization
            checker = AvailabilityChecker(
                provider_manager=mock_provider_manager,
                streaming_providers=streaming_providers,
                jellyseerr_config=jellyseerr_config,
                cache_db_path=temp_db
            )
            
            # Jellyseerr client should be None after failed connection
            assert checker.jellyseerr_client is None
    
    def test_check_series_availability_with_jellyseerr_success(self, enhanced_checker):
        """Test series availability check using Jellyseerr successfully."""
        series = {
            "title": "Breaking Bad",
            "tvdbId": 81189,
            "imdbId": "tt0903747",
            "seasons": [
                {"seasonNumber": 1, "monitored": True},
                {"seasonNumber": 2, "monitored": True}
            ]
        }
        
        result = enhanced_checker.check_series_availability(series)
        
        # Should find matches for netflix (US) and amazon-prime (DE)
        assert "netflix" in result
        assert "amazon-prime" in result
        assert "disney-plus" in result  # No match but should be present
        
        # Netflix should be available (US match)
        assert result["netflix"]["available"] is True
        assert result["netflix"]["jellyseerr_data"] is not None
        
        # Amazon Prime should be available (DE match)
        assert result["amazon-prime"]["available"] is True
        
        # Disney+ should not be available (no match)
        assert result["disney-plus"]["available"] is False
    
    def test_check_series_availability_with_cache_hit(self, enhanced_checker):
        """Test series availability check with cache hit."""
        series = {
            "title": "Breaking Bad",
            "tvdbId": 81189,
            "imdbId": "tt0903747"
        }
        
        # Pre-populate cache
        cached_data = {
            "series_name": "Breaking Bad",
            "providers": [
                {"country": "US", "provider_name": "Netflix", "mapped_name": "netflix"}
            ],
            "source": "jellyseerr_tvdb",
            "timestamp": "2025-07-25 10:00:00"
        }
        cache_key = enhanced_checker.cache._generate_key(
            tvdb_id=81189,
            imdb_id="tt0903747",
            providers=enhanced_checker.streaming_providers
        )
        enhanced_checker.cache.set(cache_key, cached_data, ttl=300)
        
        result = enhanced_checker.check_series_availability(series)
        
        # Should use cached data, not call Jellyseerr
        enhanced_checker.jellyseerr_client.get_series_availability.assert_not_called()
        
        assert "netflix" in result
        assert result["netflix"]["available"] is True
        assert result["netflix"]["source"] == "cache"
    
    def test_check_series_availability_with_cache_miss(self, enhanced_checker):
        """Test series availability check with cache miss."""
        series = {
            "title": "Breaking Bad", 
            "tvdbId": 81189,
            "imdbId": "tt0903747"
        }
        
        result = enhanced_checker.check_series_availability(series)
        
        # Should call Jellyseerr API
        enhanced_checker.jellyseerr_client.get_series_availability.assert_called_once_with(
            tvdb_id=81189
        )
        
        # Should cache the result
        cache_key = enhanced_checker.cache._generate_key(
            tvdb_id=81189,
            imdb_id="tt0903747",
            providers=enhanced_checker.streaming_providers
        )
        cached_result = enhanced_checker.cache.get(cache_key)
        assert cached_result is not None
    
    def test_check_series_availability_jellyseerr_error(self, enhanced_checker):
        """Test series availability check when Jellyseerr fails."""
        enhanced_checker.jellyseerr_client.get_series_availability.side_effect = JellyseerrError("API Error")
        
        series = {
            "title": "Breaking Bad",  # This will match in mock Netflix data
            "tvdbId": 81189
        }
        
        result = enhanced_checker.check_series_availability(series)
        
        # Should fallback to mock provider and still work
        # Netflix should be available from mock data
        assert result["netflix"]["available"] is True
        assert result["netflix"]["source"] == "mock"
        
        # TVDB ID should be blacklisted after failure
        assert enhanced_checker.cache.is_blacklisted(81189)
    
    def test_check_series_availability_circuit_breaker_open(self, enhanced_checker):
        """Test series availability when circuit breaker is open."""
        # Configure circuit breaker to be open
        circuit_breaker = enhanced_checker.cache.get_circuit_breaker()
        circuit_breaker.state = "open"
        
        series = {
            "title": "Breaking Bad",
            "tvdbId": 81189
        }
        
        result = enhanced_checker.check_series_availability(series)
        
        # Should not call Jellyseerr API
        enhanced_checker.jellyseerr_client.get_series_availability.assert_not_called()
        
        # Should have circuit breaker information
        for provider_result in result.values():
            assert "circuit_breaker_open" in provider_result
            assert provider_result["circuit_breaker_open"] is True
    
    def test_check_series_availability_blacklisted_tvdb_id(self, enhanced_checker):
        """Test series availability with blacklisted TVDB ID."""
        # Add TVDB ID to blacklist
        enhanced_checker.cache.add_to_blacklist(81189, "Consistently failing")
        
        series = {
            "title": "Breaking Bad",
            "tvdbId": 81189
        }
        
        result = enhanced_checker.check_series_availability(series)
        
        # Should not call Jellyseerr API
        enhanced_checker.jellyseerr_client.get_series_availability.assert_not_called()
        
        # Should have blacklist information
        for provider_result in result.values():
            assert "blacklisted" in provider_result
            assert provider_result["blacklisted"] is True
    
    def test_provider_filtering_with_jellyseerr_data(self, enhanced_checker):
        """Test provider filtering with Jellyseerr data."""
        # Mock Jellyseerr to return providers in multiple countries
        enhanced_checker.jellyseerr_client.get_series_availability.return_value = {
            "series_name": "Breaking Bad",
            "providers": [
                {"country": "US", "provider_name": "Netflix", "mapped_name": "netflix"},
                {"country": "DE", "provider_name": "Netflix", "mapped_name": "netflix"},
                {"country": "UK", "provider_name": "Netflix", "mapped_name": "netflix"},
                {"country": "US", "provider_name": "Hulu", "mapped_name": "hulu"},
                {"country": "DE", "provider_name": "Amazon Prime Video", "mapped_name": "amazon-prime"}
            ]
        }
        
        series = {"title": "Breaking Bad", "tvdbId": 81189}
        result = enhanced_checker.check_series_availability(series)
        
        # Should only match configured provider/country combinations
        assert result["netflix"]["available"] is True  # US match
        assert result["netflix"]["country"] == "US"
        
        assert result["amazon-prime"]["available"] is True  # DE match
        assert result["amazon-prime"]["country"] == "DE"
        
        assert result["disney-plus"]["available"] is False  # No match
    
    def test_fallback_to_mock_provider(self, enhanced_checker):
        """Test fallback to mock provider when Jellyseerr is unavailable."""
        enhanced_checker.jellyseerr_client = None  # Simulate no Jellyseerr
        
        series = {
            "title": "Breaking Bad",  # Should be in mock Netflix data
            "tvdbId": 81189,
            "seasons": [{"seasonNumber": 1, "monitored": True}]
        }
        
        result = enhanced_checker.check_series_availability(series)
        
        # Should use mock provider logic
        assert result["netflix"]["available"] is True
        assert result["netflix"]["source"] == "mock"
        assert result["netflix"]["seasons"] == [1]
    
    def test_cache_statistics_integration(self, enhanced_checker):
        """Test integration with cache statistics."""
        series = {"title": "Breaking Bad", "tvdbId": 81189}
        
        # Make multiple requests to generate cache stats
        enhanced_checker.check_series_availability(series)  # Cache miss
        enhanced_checker.check_series_availability(series)  # Cache hit
        enhanced_checker.check_series_availability(series)  # Cache hit
        
        stats = enhanced_checker.get_cache_statistics()
        
        assert "hit_count" in stats
        assert "miss_count" in stats
        assert "hit_rate" in stats
        assert stats["hit_count"] >= 2  # At least 2 hits
        assert stats["miss_count"] >= 1  # At least 1 miss
    
    def test_availability_with_imdb_fallback(self, enhanced_checker):
        """Test availability check with IMDB fallback when TVDB fails."""
        # Configure Jellyseerr to fail for TVDB but succeed for IMDB
        def mock_get_availability(tvdb_id=None, imdb_id=None):
            if tvdb_id:
                raise JellyseerrError("TVDB lookup failed")
            if imdb_id:
                return {
                    "series_name": "Breaking Bad",
                    "providers": [
                        {"country": "US", "provider_name": "Netflix", "mapped_name": "netflix"}
                    ]
                }
            return None
        
        enhanced_checker.jellyseerr_client.get_series_availability.side_effect = mock_get_availability
        
        series = {
            "title": "Breaking Bad",
            "tvdbId": 81189,
            "imdbId": "tt0903747"
        }
        
        result = enhanced_checker.check_series_availability(series)
        
        # Should have tried TVDB first, then IMDB
        assert enhanced_checker.jellyseerr_client.get_series_availability.call_count == 2
        
        # Should have successful result from IMDB fallback
        assert result["netflix"]["available"] is True
        assert result["netflix"]["source"] == "jellyseerr_imdb"
    
    def test_test_availability_sources_enhanced(self, enhanced_checker):
        """Test enhanced availability sources testing."""
        result = enhanced_checker.test_availability_sources()
        
        assert "provider_manager" in result
        assert "jellyseerr" in result
        assert "cache" in result
        assert "circuit_breaker" in result
        
        # Jellyseerr should be available in enhanced version
        assert result["jellyseerr"]["available"] is True
        
        # Cache should be available
        assert result["cache"]["available"] is True
        
        # Circuit breaker should be in closed state
        assert result["circuit_breaker"]["state"] == "closed"
    
    def test_jellyseerr_provider_data_sanitization(self, enhanced_checker):
        """Test that Jellyseerr provider data is properly sanitized."""
        # Mock Jellyseerr to return some invalid provider data
        enhanced_checker.jellyseerr_client.get_series_availability.return_value = {
            "series_name": "Breaking Bad",
            "providers": [
                {"country": "US", "provider_name": "Netflix", "mapped_name": "netflix"},
                {"country": "DE", "provider_name": None, "mapped_name": ""},  # Invalid
                {"country": "", "provider_name": "Amazon Prime", "mapped_name": "amazon-prime"},  # Invalid
                {"country": "UK", "provider_name": "Disney+", "mapped_name": "disney-plus"}
            ]
        }
        
        series = {"title": "Breaking Bad", "tvdbId": 81189}
        result = enhanced_checker.check_series_availability(series)
        
        # Should only process valid provider data
        # Invalid providers should be filtered out during processing
        # Netflix (US) should be available
        assert result["netflix"]["available"] is True
        
        # Amazon Prime (DE) and Disney+ should not match due to invalid data or no config match
        assert result["amazon-prime"]["available"] is False
        assert result["disney-plus"]["available"] is False
    
    def test_concurrent_availability_checks(self, enhanced_checker):
        """Test concurrent availability checks are handled safely."""
        import threading
        import queue
        
        series = {"title": "Breaking Bad", "tvdbId": 81189}
        results = queue.Queue()
        
        def worker():
            try:
                result = enhanced_checker.check_series_availability(series)
                results.put(("success", result))
            except Exception as e:
                results.put(("error", str(e)))
        
        # Start multiple threads
        threads = []
        for _ in range(3):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Check results
        success_count = 0
        while not results.empty():
            status, result = results.get()
            if status == "success":
                success_count += 1
                assert "netflix" in result
        
        # All operations should succeed
        assert success_count == 3