"""Tests for multi-provider fallback system."""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime

from excludarr.provider_manager import ProviderManager
from excludarr.models import ProviderAPIsConfig, TMDBConfig, StreamingAvailabilityConfig, UtellyConfig
from excludarr.tmdb_client import TMDBNotFoundException
from excludarr.streaming_availability_client import RateLimitError as SARateLimitError
from excludarr.utelly_client import RateLimitError as UtellyRateLimitError


class TestProviderManager:
    """Test provider manager functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = ProviderAPIsConfig(
            tmdb=TMDBConfig(
                api_key="test_tmdb_key",
                enabled=True
            ),
            streaming_availability=StreamingAvailabilityConfig(
                enabled=True,
                rapidapi_key="test_sa_key"
            ),
            utelly=UtellyConfig(
                enabled=True,
                rapidapi_key="test_utelly_key"
            )
        )
    
    def test_provider_manager_initialization(self):
        """Test provider manager initialization with all providers."""
        with patch('excludarr.provider_manager.TMDBClient') as mock_tmdb:
            with patch('excludarr.provider_manager.StreamingAvailabilityClient') as mock_sa:
                with patch('excludarr.provider_manager.UtellyClient') as mock_utelly:
                    manager = ProviderManager(self.config)
                    
                    assert len(manager.providers) == 3
                    assert 'tmdb' in manager.providers
                    assert 'streaming_availability' in manager.providers
                    assert 'utelly' in manager.providers
    
    def test_provider_manager_tmdb_only(self):
        """Test provider manager with only TMDB enabled."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="test_key", enabled=True),
            streaming_availability=StreamingAvailabilityConfig(enabled=False),
            utelly=UtellyConfig(enabled=False)
        )
        
        with patch('excludarr.provider_manager.TMDBClient') as mock_tmdb:
            manager = ProviderManager(config)
            assert len(manager.providers) == 1
            assert 'tmdb' in manager.providers
    
    def test_provider_manager_no_providers_error(self):
        """Test provider manager fails when no providers enabled."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="test_key", enabled=False),
            streaming_availability=StreamingAvailabilityConfig(enabled=False),
            utelly=UtellyConfig(enabled=False)
        )
        
        with pytest.raises(ValueError, match="No provider APIs are enabled"):
            ProviderManager(config)
    
    @pytest.mark.asyncio
    async def test_get_series_availability_tmdb_only(self):
        """Test getting availability with only TMDB data."""
        with patch('excludarr.provider_manager.TMDBClient') as mock_tmdb_class:
            with patch('excludarr.provider_manager.StreamingAvailabilityClient'):
                with patch('excludarr.provider_manager.UtellyClient'):
                    # Create manager with a mock cache
                    with patch('excludarr.provider_manager.TMDBCache') as mock_cache_class:
                        mock_cache = mock_cache_class.return_value
                        mock_cache.get_id_mapping = Mock(return_value=None)  # No cached ID
                        mock_cache.get_provider_data = Mock(return_value=None)  # No cached data
                        mock_cache.set_id_mapping = Mock()
                        mock_cache.set_provider_data = Mock()
                        
                        manager = ProviderManager(self.config, cache=mock_cache)
                        
                        # Mock TMDB client instance
                        mock_tmdb = mock_tmdb_class.return_value
                        manager.providers['tmdb'] = mock_tmdb
                        
                        # Mock TMDB methods
                        mock_tmdb.find_series_by_imdb_id = AsyncMock(return_value=12345)
                        mock_tmdb.get_watch_providers = AsyncMock(return_value={
                            "results": {
                                "DE": {
                                    "flatrate": [
                                        {"provider_name": "Netflix"},
                                        {"provider_name": "Amazon Prime Video"}
                                    ]
                                }
                            }
                        })
                        mock_tmdb._extract_providers_from_response = Mock(return_value={
                            "DE": ["netflix", "amazon-prime"]
                        })
                        
                        # Remove other providers to test TMDB only
                        manager.providers = {'tmdb': mock_tmdb}
                        
                        result = await manager.get_series_availability("tt0944947", ["DE"])
                        
                        assert result["imdb_id"] == "tt0944947"
                        assert result["tmdb_id"] == 12345
                        assert "DE" in result["countries"]
                        assert "netflix" in result["countries"]["DE"]
                        assert result["countries"]["DE"]["netflix"]["available"] is True
                        assert result["metadata"]["sources"] == ["tmdb"]
    
    @pytest.mark.asyncio
    async def test_get_series_availability_with_fallback(self):
        """Test that fallback APIs are used conservatively only when TMDB has no data."""
        with patch('excludarr.provider_manager.TMDBClient') as mock_tmdb_class:
            with patch('excludarr.provider_manager.StreamingAvailabilityClient') as mock_sa_class:
                with patch('excludarr.provider_manager.UtellyClient'):
                    # Create manager with a mock cache to avoid real cache interference
                    with patch('excludarr.provider_manager.TMDBCache') as mock_cache_class:
                        mock_cache = mock_cache_class.return_value
                        mock_cache.get_id_mapping = Mock(return_value=None)
                        mock_cache.get_provider_data = Mock(return_value=None)
                        mock_cache.set_id_mapping = Mock()
                        mock_cache.set_provider_data = Mock()
                        
                        manager = ProviderManager(self.config, cache=mock_cache)
                        
                        # Mock TMDB client to return NO providers
                        mock_tmdb = mock_tmdb_class.return_value
                        mock_tmdb.find_series_by_imdb_id = AsyncMock(return_value=12345)
                        mock_tmdb.get_watch_providers = AsyncMock(return_value={
                            "results": {}  # Completely empty - no data for any country
                        })
                        mock_tmdb._extract_providers_from_response = Mock(return_value={})
                        
                        # Mock Streaming Availability client
                        mock_sa = mock_sa_class.return_value
                        mock_sa.get_series_availability = AsyncMock(return_value={
                            "streamingOptions": [{
                                "service": "netflix",
                                "type": "subscription",
                                "link": "https://netflix.com/123"
                            }]
                        })
                        mock_sa.extract_provider_info = Mock(return_value={
                            "netflix": [{
                                "type": "subscription",
                                "link": "https://netflix.com/123"
                            }]
                        })
                        
                        manager.providers = {'tmdb': mock_tmdb, 'streaming_availability': mock_sa}
                        
                        result = await manager.get_series_availability("tt0944947", ["DE"])
                        
                        # With conservative approach: only fallback when NO data from TMDB
                        assert "DE" in result["countries"]
                        assert "netflix" in result["countries"]["DE"]
                        assert result["countries"]["DE"]["netflix"]["link"] == "https://netflix.com/123"
                        assert "streaming_availability" in result["metadata"]["sources"]
    
    @pytest.mark.asyncio
    async def test_get_series_availability_rate_limit_handling(self):
        """Test handling of rate limits in secondary providers."""
        with patch('excludarr.provider_manager.TMDBClient') as mock_tmdb_class:
            with patch('excludarr.provider_manager.StreamingAvailabilityClient') as mock_sa_class:
                # Create manager with a mock cache
                with patch('excludarr.provider_manager.TMDBCache') as mock_cache_class:
                    mock_cache = mock_cache_class.return_value
                    mock_cache.get_id_mapping = Mock(return_value=None)
                    mock_cache.get_provider_data = Mock(return_value=None)
                    mock_cache.set_id_mapping = Mock()
                    mock_cache.set_provider_data = Mock()
                    
                    manager = ProviderManager(self.config, cache=mock_cache)
                    
                    # Mock TMDB client
                    mock_tmdb = mock_tmdb_class.return_value
                    mock_tmdb.find_series_by_imdb_id = AsyncMock(return_value=12345)
                    mock_tmdb.get_watch_providers = AsyncMock(return_value={"results": {}})
                    mock_tmdb._extract_providers_from_response = Mock(return_value={})
                    
                    # Mock Streaming Availability client with rate limit error
                    mock_sa = mock_sa_class.return_value
                    mock_sa.get_series_availability = AsyncMock(side_effect=SARateLimitError("Daily quota exceeded"))
                    
                    manager.providers = {'tmdb': mock_tmdb, 'streaming_availability': mock_sa}
                    
                    # Should not raise, just skip SA and return TMDB data
                    result = await manager.get_series_availability("tt0944947", ["DE", "US"])
                    
                    assert result["tmdb_id"] == 12345
                    assert result["metadata"]["sources"] == ["tmdb"]  # Only TMDB used
    
    def test_filter_by_user_providers(self):
        """Test filtering availability by user's subscribed providers."""
        with patch('excludarr.provider_manager.TMDBClient'):
            manager = ProviderManager(self.config)
            
            availability_data = {
                "countries": {
                    "DE": {
                        "netflix": {"available": True},
                        "amazon-prime": {"available": True},
                        "disney-plus": {"available": True}
                    },
                    "US": {
                        "hulu": {"available": True},
                        "peacock": {"available": True}
                    }
                }
            }
            
            user_providers = ["netflix", "amazon-prime"]
            
            result = manager.filter_by_user_providers(availability_data, user_providers)
            
            assert result["DE"] is True  # Has Netflix and Amazon
            assert result["US"] is False  # No user providers
    
    def test_normalize_provider_name(self):
        """Test provider name normalization."""
        with patch('excludarr.provider_manager.TMDBClient'):
            manager = ProviderManager(self.config)
            
            # Test exact normalization behavior
            assert manager._normalize_provider_name('Netflix') == 'netflix'
            assert manager._normalize_provider_name('Amazon Prime Video') == 'amazon-prime'  # Special mapping
            assert manager._normalize_provider_name('Disney+') == 'disney-plus'
            assert manager._normalize_provider_name('Disney Plus') == 'disney-plus'  # No special mapping needed
            assert manager._normalize_provider_name('HBO Max') == 'hbo-max'
            assert manager._normalize_provider_name('Apple TV+') == 'apple-tv'  # Maps apple-tv-plus -> apple-tv
            assert manager._normalize_provider_name('Apple TV Plus') == 'apple-tv'  # Maps apple-tv-plus -> apple-tv
            assert manager._normalize_provider_name('Paramount+') == 'paramount-plus'
            assert manager._normalize_provider_name('Paramount Plus') == 'paramount-plus'  # No special mapping needed
            assert manager._normalize_provider_name('Unknown Service') == 'unknown-service'
    
    def test_get_quota_status(self):
        """Test getting quota status for all providers."""
        with patch('excludarr.provider_manager.TMDBClient') as mock_tmdb_class:
            with patch('excludarr.provider_manager.StreamingAvailabilityClient') as mock_sa_class:
                with patch('excludarr.provider_manager.UtellyClient') as mock_utelly_class:
                    manager = ProviderManager(self.config)
                    
                    # Mock quota properties
                    mock_sa = mock_sa_class.return_value
                    mock_sa.daily_quota = 100
                    mock_sa._request_count = 25
                    mock_sa.remaining_quota = 75
                    
                    mock_utelly = mock_utelly_class.return_value
                    mock_utelly.monthly_quota = 1000
                    mock_utelly._request_count = 100
                    mock_utelly.remaining_quota = 900
                    
                    manager.providers['streaming_availability'] = mock_sa
                    manager.providers['utelly'] = mock_utelly
                    
                    status = manager.get_quota_status()
                    
                    assert 'tmdb' in status
                    assert status['tmdb']['type'] == 'rate_limit'
                    
                    assert 'streaming_availability' in status
                    assert status['streaming_availability']['remaining'] == 75
                    
                    assert 'utelly' in status
                    assert status['utelly']['remaining'] == 900
    
    def test_should_use_streaming_availability(self):
        """Test logic for determining when to use Streaming Availability API."""
        with patch('excludarr.provider_manager.TMDBClient'):
            manager = ProviderManager(self.config)
            
            # Should use when country has no data
            result = {"countries": {}}
            assert manager._should_use_streaming_availability(result, ["DE"]) is True
            
            # Should NOT use when we have any provider data (conservative approach)
            result = {
                "countries": {
                    "DE": {
                        "netflix": {"available": True}  # Any data means no fallback needed
                    }
                }
            }
            assert manager._should_use_streaming_availability(result, ["DE"]) is False
            
            # Should not use when we have complete data
            result = {
                "countries": {
                    "DE": {
                        "netflix": {"available": True, "link": "https://netflix.com"}
                    }
                }
            }
            assert manager._should_use_streaming_availability(result, ["DE"]) is False
    
    def test_should_use_utelly(self):
        """Test logic for determining when to use Utelly API."""
        with patch('excludarr.provider_manager.TMDBClient'):
            manager = ProviderManager(self.config)
            
            # Should use when country has no data
            result = {"countries": {}}
            assert manager._should_use_utelly(result, ["DE"]) is True
            
            # Should NOT use when we have any provider data (conservative approach)
            result = {
                "countries": {
                    "DE": {
                        "netflix": {"type": "subscription"},
                        "amazon-prime": {"type": "subscription"}
                    }
                }
            }
            assert manager._should_use_utelly(result, ["DE"]) is False
            
            # Should not use when we have any data (conservative approach)
            result = {
                "countries": {
                    "DE": {
                        "netflix": {"type": "subscription"},
                        "apple-itunes": {"type": "rent/buy"}
                    }
                }
            }
            assert manager._should_use_utelly(result, ["DE"]) is False


class TestProviderManagerErrorHandling:
    """Test error handling in provider manager."""
    
    def test_initialization_with_tmdb_failure(self):
        """Test initialization when TMDB client fails to initialize."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="invalid_key", enabled=True),
            streaming_availability=StreamingAvailabilityConfig(enabled=False),
            utelly=UtellyConfig(enabled=False)
        )
        
        with patch('excludarr.provider_manager.TMDBClient', side_effect=Exception("TMDB init failed")):
            # Should fail since no providers will be available
            with pytest.raises(ValueError, match="No provider APIs are enabled"):
                ProviderManager(config)
    
    def test_initialization_with_streaming_availability_failure(self):
        """Test initialization when Streaming Availability client fails."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="test_key", enabled=True),
            streaming_availability=StreamingAvailabilityConfig(
                enabled=True,
                rapidapi_key="invalid_key"
            ),
            utelly=UtellyConfig(enabled=False)
        )
        
        with patch('excludarr.provider_manager.TMDBClient'):
            with patch('excludarr.provider_manager.StreamingAvailabilityClient', side_effect=Exception("SA init failed")):
                manager = ProviderManager(config)
                assert 'tmdb' in manager.providers
                assert 'streaming_availability' not in manager.providers
    
    def test_initialization_with_utelly_failure(self):
        """Test initialization when Utelly client fails."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="test_key", enabled=True),
            streaming_availability=StreamingAvailabilityConfig(enabled=False),
            utelly=UtellyConfig(
                enabled=True,
                rapidapi_key="invalid_key"
            )
        )
        
        with patch('excludarr.provider_manager.TMDBClient'):
            with patch('excludarr.provider_manager.UtellyClient', side_effect=Exception("Utelly init failed")):
                manager = ProviderManager(config)
                assert 'tmdb' in manager.providers
                assert 'utelly' not in manager.providers

    async def test_get_tmdb_data_no_tmdb_provider(self):
        """Test _get_tmdb_data when TMDB provider is not available."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="test_key", enabled=False),
            streaming_availability=StreamingAvailabilityConfig(enabled=False),
            utelly=UtellyConfig(enabled=False)
        )
        
        # This should raise error since no providers are enabled
        with pytest.raises(ValueError, match="No provider APIs are enabled"):
            ProviderManager(config)

    async def test_get_streaming_availability_data_no_provider(self):
        """Test _get_streaming_availability_data when SA provider is not available."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="test_key", enabled=True),
            streaming_availability=StreamingAvailabilityConfig(enabled=False),
            utelly=UtellyConfig(enabled=False)
        )
        
        with patch('excludarr.provider_manager.TMDBClient'):
            manager = ProviderManager(config)
            
            # Should raise KeyError when provider not available
            with pytest.raises(KeyError):
                await manager._get_streaming_availability_data("tt1234567", ["US"])

    async def test_get_utelly_data_no_provider(self):
        """Test _get_utelly_data when Utelly provider is not available."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="test_key", enabled=True),
            streaming_availability=StreamingAvailabilityConfig(enabled=False),
            utelly=UtellyConfig(enabled=False)
        )
        
        with patch('excludarr.provider_manager.TMDBClient'):
            manager = ProviderManager(config)
            
            # Should raise KeyError when provider not available
            with pytest.raises(KeyError):
                await manager._get_utelly_data("tt1234567", ["US"])

    async def test_get_series_availability_with_tmdb_exception(self):
        """Test get_series_availability when TMDB raises an exception."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="test_key", enabled=True),
            streaming_availability=StreamingAvailabilityConfig(enabled=False),
            utelly=UtellyConfig(enabled=False)
        )
        
        with patch('excludarr.provider_manager.TMDBClient') as mock_tmdb_class:
            manager = ProviderManager(config)
            
            # Mock TMDB to raise an exception
            mock_tmdb = mock_tmdb_class.return_value
            mock_tmdb.get_streaming_availability = AsyncMock(side_effect=Exception("TMDB API error"))
            
            with patch.object(manager, '_get_from_cache', return_value=None):
                with patch.object(manager, '_save_to_cache'):
                    result = await manager.get_series_availability("tt1234567", ["US"])
                    
                    # Should return empty result structure when all providers fail
                    assert "countries" in result
                    assert "metadata" in result
                    assert result["metadata"]["sources"] == []

    async def test_merge_streaming_availability_data_edge_cases(self):
        """Test _merge_streaming_availability_data with edge cases."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="test_key", enabled=True),
            streaming_availability=StreamingAvailabilityConfig(enabled=True, rapidapi_key="test_key"),
            utelly=UtellyConfig(enabled=False)
        )
        
        with patch('excludarr.provider_manager.TMDBClient'):
            with patch('excludarr.provider_manager.StreamingAvailabilityClient'):
                manager = ProviderManager(config)
                
                # Test with empty SA data
                result = {"countries": {"US": {}}}
                sa_data = {}
                manager._merge_streaming_availability_data(result, sa_data, ["US"])
                
                # Should not crash and result should be unchanged
                assert result["countries"]["US"] == {}

    async def test_merge_utelly_data_edge_cases(self):
        """Test _merge_utelly_data with edge cases."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="test_key", enabled=True),
            streaming_availability=StreamingAvailabilityConfig(enabled=False),
            utelly=UtellyConfig(enabled=True, rapidapi_key="test_key")
        )
        
        with patch('excludarr.provider_manager.TMDBClient'):
            with patch('excludarr.provider_manager.UtellyClient'):
                manager = ProviderManager(config)
                
                # Test with empty Utelly data
                result = {"countries": {"US": {}}}
                utelly_data = {}
                manager._merge_utelly_data(result, utelly_data, ["US"])
                
                # Should not crash and result should be unchanged
                assert result["countries"]["US"] == {}

    def test_normalize_provider_name_edge_cases(self):
        """Test normalize_provider_name with edge cases."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="test_key", enabled=True),
            streaming_availability=StreamingAvailabilityConfig(enabled=False),
            utelly=UtellyConfig(enabled=False)
        )
        
        with patch('excludarr.provider_manager.TMDBClient'):
            manager = ProviderManager(config)
            
            # Test edge cases (method is private, so use _ prefix)
            assert manager._normalize_provider_name("") == ""
            assert manager._normalize_provider_name("Netflix") == "netflix"
            assert manager._normalize_provider_name("AMAZON PRIME VIDEO") == "amazon-prime"
            assert manager._normalize_provider_name("Disney+") == "disney-plus"
            assert manager._normalize_provider_name("HBO Max") == "hbo-max"