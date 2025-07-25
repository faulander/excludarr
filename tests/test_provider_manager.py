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