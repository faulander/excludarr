"""Tests for simplified TMDB cache system."""

import pytest
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from excludarr.simple_cache import TMDBCache, TMDBCacheEntry


class TestTMDBCacheEntry:
    """Test TMDBCacheEntry functionality."""
    
    def test_cache_entry_creation(self):
        """Test cache entry creation and basic properties."""
        now = datetime.now()
        expires_at = now + timedelta(hours=1)
        
        entry = TMDBCacheEntry(
            key="test_key",
            data={"test": "data"},
            expires_at=expires_at,
            created_at=now,
            cache_type="provider_data"
        )
        
        assert entry.key == "test_key"
        assert entry.data == {"test": "data"}
        assert entry.expires_at == expires_at
        assert entry.created_at == now
        assert entry.cache_type == "provider_data"
    
    def test_cache_entry_expiration(self):
        """Test cache entry expiration logic."""
        # Non-expired entry
        future = datetime.now() + timedelta(hours=1)
        entry = TMDBCacheEntry(
            key="test", 
            data={}, 
            expires_at=future, 
            created_at=datetime.now(),
            cache_type="provider_data"
        )
        assert not entry.is_expired()
        
        # Expired entry
        past = datetime.now() - timedelta(hours=1)
        entry_expired = TMDBCacheEntry(
            key="test", 
            data={}, 
            expires_at=past, 
            created_at=datetime.now(),
            cache_type="provider_data"
        )
        assert entry_expired.is_expired()
    
    def test_cache_entry_permanent(self):
        """Test permanent cache entry detection."""
        id_mapping_entry = TMDBCacheEntry(
            key="id_mapping:tt1234567",
            data={"tmdb_id": 12345},
            expires_at=datetime.now() + timedelta(days=365),
            created_at=datetime.now(),
            cache_type="id_mapping"
        )
        assert id_mapping_entry.is_permanent()
        
        provider_entry = TMDBCacheEntry(
            key="providers:12345",
            data={"providers": []},
            expires_at=datetime.now() + timedelta(hours=24),
            created_at=datetime.now(),
            cache_type="provider_data"
        )
        assert not provider_entry.is_permanent()
    
    def test_cache_entry_serialization(self):
        """Test cache entry serialization and deserialization."""
        now = datetime.now()
        expires_at = now + timedelta(hours=1)
        
        original = TMDBCacheEntry(
            key="test_key",
            data={"test": "data", "number": 123},
            expires_at=expires_at,
            created_at=now,
            cache_type="provider_data"
        )
        
        # Serialize
        serialized = original.to_dict()
        
        # Deserialize
        restored = TMDBCacheEntry.from_dict(serialized)
        
        assert restored.key == original.key
        assert restored.data == original.data
        assert restored.expires_at == original.expires_at
        assert restored.created_at == original.created_at
        assert restored.cache_type == original.cache_type


class TestTMDBCache:
    """Test TMDBCache functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Use temporary database for each test
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_file.close()
        
        self.cache = TMDBCache(
            db_path=self.temp_file.name,
            provider_data_ttl=3600,  # 1 hour for tests
            cleanup_interval=1800    # 30 minutes
        )
    
    def teardown_method(self):
        """Clean up test fixtures."""
        Path(self.temp_file.name).unlink(missing_ok=True)
    
    def test_cache_initialization(self):
        """Test cache initialization."""
        assert self.cache.db_path == self.temp_file.name
        assert self.cache.provider_data_ttl == 3600
        assert self.cache.cleanup_interval == 1800
        
        # Check database file was created
        assert Path(self.temp_file.name).exists()
    
    def test_id_mapping_cache(self):
        """Test IMDb to TMDB ID mapping cache."""
        imdb_id = "tt1234567"
        tmdb_id = 12345
        
        # Initially no mapping cached
        assert self.cache.get_id_mapping(imdb_id) is None
        
        # Store mapping
        self.cache.set_id_mapping(imdb_id, tmdb_id)
        
        # Retrieve mapping
        cached_id = self.cache.get_id_mapping(imdb_id)
        assert cached_id == tmdb_id
        
        # Verify statistics
        stats = self.cache.get_statistics()
        assert stats["id_mapping_hits"] == 1
        assert stats["cached_id_mappings"] == 1
    
    def test_provider_data_cache(self):
        """Test provider data caching."""
        tmdb_id = 12345
        provider_data = {
            "US": ["netflix", "amazon-prime"],
            "DE": ["amazon-prime"]
        }
        
        # Initially no data cached
        assert self.cache.get_provider_data(tmdb_id) is None
        assert self.cache.get_provider_data(tmdb_id, "US") is None
        
        # Store provider data
        self.cache.set_provider_data(tmdb_id, provider_data)
        self.cache.set_provider_data(tmdb_id, {"US": ["netflix"]}, "US")
        
        # Retrieve provider data
        cached_data = self.cache.get_provider_data(tmdb_id)
        assert cached_data == provider_data
        
        us_data = self.cache.get_provider_data(tmdb_id, "US")
        assert us_data == {"US": ["netflix"]}
        
        # Verify statistics
        stats = self.cache.get_statistics()
        assert stats["provider_data_hits"] == 2
        assert stats["cached_provider_data"] == 2
    
    def test_cache_expiration(self):
        """Test cache entry expiration."""
        # Create cache with very short TTL
        short_ttl_cache = TMDBCache(
            db_path=self.temp_file.name,
            provider_data_ttl=1  # 1 second TTL
        )
        
        tmdb_id = 12345
        provider_data = {"US": ["netflix"]}
        
        # Store data
        short_ttl_cache.set_provider_data(tmdb_id, provider_data)
        
        # Immediately retrieve - should work
        cached_data = short_ttl_cache.get_provider_data(tmdb_id)
        assert cached_data == provider_data
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Should be expired now
        expired_data = short_ttl_cache.get_provider_data(tmdb_id)
        assert expired_data is None
    
    def test_permanent_id_mapping_cache(self):
        """Test that ID mappings are cached permanently."""
        imdb_id = "tt1234567"
        tmdb_id = 12345
        
        # Store ID mapping
        self.cache.set_id_mapping(imdb_id, tmdb_id)
        
        # Should still be available even after a long time
        # (we can't actually wait 10 years, but we can check the expiry date)
        entry = self.cache._get_entry(f"id_mapping:{imdb_id}")
        assert entry is not None
        assert entry.is_permanent()
        
        # Should be valid for a very long time
        assert entry.expires_at > datetime.now() + timedelta(days=365)
    
    def test_cache_key_generation(self):
        """Test cache key generation."""
        # ID mapping keys
        key1 = self.cache._generate_key("id_mapping", "tt1234567")
        assert key1 == "id_mapping:tt1234567"
        
        # Provider data keys
        key2 = self.cache._generate_key("providers", "12345")
        assert key2 == "providers:12345"
        
        key3 = self.cache._generate_key("providers", "12345", "US")
        assert key3 == "providers:12345:US"
    
    def test_cache_cleanup(self):
        """Test cache cleanup functionality."""
        # Create cache with very short TTL
        short_ttl_cache = TMDBCache(
            db_path=self.temp_file.name,
            provider_data_ttl=1  # 1 second TTL
        )
        
        # Add some data
        short_ttl_cache.set_provider_data(12345, {"US": ["netflix"]})
        short_ttl_cache.set_provider_data(67890, {"DE": ["amazon-prime"]})
        short_ttl_cache.set_id_mapping("tt1234567", 12345)  # Permanent
        
        # Verify data is there
        stats_before = short_ttl_cache.get_statistics()
        assert stats_before["cached_provider_data"] == 2
        assert stats_before["cached_id_mappings"] == 1
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Run cleanup
        removed_count = short_ttl_cache.cleanup_expired()
        assert removed_count == 2  # Only provider data should be removed
        
        # Verify cleanup results
        stats_after = short_ttl_cache.get_statistics()
        assert stats_after["cached_provider_data"] == 0
        assert stats_after["cached_id_mappings"] == 1  # ID mapping should remain
    
    def test_cache_statistics(self):
        """Test cache statistics tracking."""
        # Initial statistics
        stats = self.cache.get_statistics()
        assert stats["hit_count"] == 0
        assert stats["miss_count"] == 0
        assert stats["hit_rate"] == 0
        
        # Add some data and access it
        self.cache.set_id_mapping("tt1234567", 12345)
        self.cache.set_provider_data(12345, {"US": ["netflix"]})
        
        # Generate some hits and misses
        self.cache.get_id_mapping("tt1234567")  # Hit
        self.cache.get_id_mapping("tt9999999")  # Miss
        self.cache.get_provider_data(12345)     # Hit
        self.cache.get_provider_data(99999)     # Miss
        
        stats = self.cache.get_statistics()
        assert stats["hit_count"] == 2
        assert stats["miss_count"] == 2
        assert stats["hit_rate"] == 50.0
        assert stats["id_mapping_hits"] == 1
        assert stats["provider_data_hits"] == 1
    
    def test_cache_clear(self):
        """Test cache clearing functionality."""
        # Add test data
        self.cache.set_id_mapping("tt1234567", 12345)
        self.cache.set_provider_data(12345, {"US": ["netflix"]})
        
        # Verify data is there
        stats_before = self.cache.get_statistics()
        assert stats_before["cached_id_mappings"] == 1
        assert stats_before["cached_provider_data"] == 1
        
        # Clear only provider data
        self.cache.clear_cache("provider_data")
        
        stats_after_partial = self.cache.get_statistics()
        assert stats_after_partial["cached_id_mappings"] == 1
        assert stats_after_partial["cached_provider_data"] == 0
        
        # Clear all cache
        self.cache.clear_cache()
        
        stats_after_full = self.cache.get_statistics()
        assert stats_after_full["cached_id_mappings"] == 0
        assert stats_after_full["cached_provider_data"] == 0
    
    def test_cache_invalidation(self):
        """Test cache invalidation functionality."""
        tmdb_id = 12345
        
        # Add data for multiple countries
        self.cache.set_provider_data(tmdb_id, {"US": ["netflix"]}, "US")
        self.cache.set_provider_data(tmdb_id, {"DE": ["amazon-prime"]}, "DE")
        self.cache.set_provider_data(tmdb_id, {"ALL": ["global"]})
        
        # Verify data is there
        assert self.cache.get_provider_data(tmdb_id, "US") is not None
        assert self.cache.get_provider_data(tmdb_id, "DE") is not None
        assert self.cache.get_provider_data(tmdb_id) is not None
        
        # Invalidate specific country
        self.cache.invalidate_provider_data(tmdb_id, "US")
        
        assert self.cache.get_provider_data(tmdb_id, "US") is None
        assert self.cache.get_provider_data(tmdb_id, "DE") is not None
        assert self.cache.get_provider_data(tmdb_id) is not None
        
        # Invalidate all data for this TMDB ID
        self.cache.invalidate_provider_data(tmdb_id)
        
        assert self.cache.get_provider_data(tmdb_id, "DE") is None
        assert self.cache.get_provider_data(tmdb_id) is None
    
    def test_cleanup_if_needed(self):
        """Test automatic cleanup based on interval."""
        # Create cache with very short cleanup interval
        auto_cleanup_cache = TMDBCache(
            db_path=self.temp_file.name,
            provider_data_ttl=1,  # 1 second TTL
            cleanup_interval=1    # 1 second cleanup interval
        )
        
        # Add expired data
        auto_cleanup_cache.set_provider_data(12345, {"US": ["netflix"]})
        time.sleep(1.1)  # Wait for expiration
        
        # Simulate passage of time for cleanup interval
        auto_cleanup_cache._last_cleanup = datetime.now() - timedelta(seconds=2)
        
        # This should trigger cleanup
        auto_cleanup_cache.cleanup_if_needed()
        
        # Verify cleanup happened
        stats = auto_cleanup_cache.get_statistics()
        assert stats["cached_provider_data"] == 0
    
    def test_error_handling(self):
        """Test error handling in cache operations."""
        # Test with invalid database path (should not crash during initialization)
        invalid_cache = TMDBCache(db_path="/invalid/path/cache.db")
        
        # Operations should not crash, but also not succeed
        result = invalid_cache.get_id_mapping("tt1234567")
        assert result is None
        
        # Setting data should not crash (but will fail silently due to invalid path)
        try:
            invalid_cache.set_id_mapping("tt1234567", 12345)
            invalid_cache.set_provider_data(12345, {"US": ["netflix"]})
            # Operations should complete without raising exceptions
        except Exception:
            pytest.fail("Cache operations should not raise exceptions")
    
    def test_concurrent_access(self):
        """Test basic concurrent access (simplified test)."""
        import threading
        
        results = []
        
        def worker():
            try:
                # Each thread does some cache operations
                self.cache.set_id_mapping(f"tt{threading.current_thread().ident}", 12345)
                result = self.cache.get_id_mapping(f"tt{threading.current_thread().ident}")
                results.append(result)
            except Exception as e:
                results.append(e)
        
        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all operations succeeded
        assert len(results) == 5
        for result in results:
            assert result == 12345  # All should have succeeded