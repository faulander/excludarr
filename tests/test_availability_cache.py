#!/usr/bin/env python3
"""Tests for AvailabilityCache with reliability features."""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import tempfile
import sqlite3
from pathlib import Path

from excludarr.availability_cache import (
    AvailabilityCache, 
    CacheEntry, 
    CircuitBreaker,
    CircuitBreakerError
)
from excludarr.models import StreamingProvider


class TestCacheEntry:
    """Test CacheEntry model."""
    
    def test_cache_entry_creation(self):
        """Test creating a cache entry."""
        entry = CacheEntry(
            key="test_key",
            data={"test": "data"},
            expires_at=datetime.now() + timedelta(minutes=5)
        )
        assert entry.key == "test_key"
        assert entry.data == {"test": "data"}
        assert not entry.is_expired()
    
    def test_cache_entry_expiration(self):
        """Test cache entry expiration."""
        # Create expired entry
        entry = CacheEntry(
            key="test_key",
            data={"test": "data"},
            expires_at=datetime.now() - timedelta(minutes=1)
        )
        assert entry.is_expired()
    
    def test_cache_entry_serialization(self):
        """Test cache entry serialization for database storage."""
        entry = CacheEntry(
            key="test_key",
            data={"series_name": "Test Series", "providers": []},
            expires_at=datetime.now() + timedelta(minutes=5)
        )
        serialized = entry.to_dict()
        assert "key" in serialized
        assert "data" in serialized
        assert "expires_at" in serialized
        
        # Test reconstruction
        new_entry = CacheEntry.from_dict(serialized)
        assert new_entry.key == entry.key
        assert new_entry.data == entry.data


class TestCircuitBreaker:
    """Test CircuitBreaker implementation."""
    
    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker starts in closed state."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        assert cb.state == "closed"
        assert cb.failure_count == 0
    
    def test_circuit_breaker_failure_tracking(self):
        """Test circuit breaker tracks failures."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        
        # Record failures
        cb.record_failure()
        assert cb.failure_count == 1
        assert cb.state == "closed"
        
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 3
        assert cb.state == "open"
    
    def test_circuit_breaker_success_reset(self):
        """Test circuit breaker resets on success."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        
        # Record some failures
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        
        # Record success - should reset
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == "closed"
    
    def test_circuit_breaker_open_state_blocks_calls(self):
        """Test circuit breaker blocks calls when open."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        
        # Trip the circuit breaker
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        
        # Should block calls
        with pytest.raises(CircuitBreakerError):
            cb.call(lambda: "test")
    
    def test_circuit_breaker_half_open_recovery(self):
        """Test circuit breaker half-open state and recovery."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        
        # Trip the circuit breaker
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        
        # Wait for recovery timeout
        time.sleep(1.1)
        
        # Should be half-open and allow one call
        result = cb.call(lambda: "success")
        assert result == "success"
        assert cb.state == "closed"
        assert cb.failure_count == 0


class TestAvailabilityCache:
    """Test AvailabilityCache implementation."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        yield temp_file.name
        Path(temp_file.name).unlink(missing_ok=True)
    
    @pytest.fixture
    def cache(self, temp_db):
        """Create cache instance for testing."""
        return AvailabilityCache(
            db_path=temp_db,
            default_ttl=300,
            cleanup_interval=60
        )
    
    def test_cache_initialization(self, temp_db):
        """Test cache initialization creates database."""
        cache = AvailabilityCache(db_path=temp_db)
        
        # Check database exists and has correct table
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='availability_cache'")
        result = cursor.fetchone()
        conn.close()
        
        assert result is not None
    
    def test_cache_key_generation(self, cache):
        """Test cache key generation for different parameters."""
        # Test TVDB ID key
        key1 = cache._generate_key(tvdb_id=12345)
        assert "tvdb_12345" in key1
        
        # Test IMDB ID key
        key2 = cache._generate_key(imdb_id="tt1234567")
        assert "imdb_tt1234567" in key2
        
        # Test provider filtering key
        providers = [
            StreamingProvider(name="netflix", country="US"),
            StreamingProvider(name="amazon-prime", country="DE")
        ]
        key3 = cache._generate_key(tvdb_id=12345, providers=providers)
        assert "providers_" in key3
        assert len(key3) > len(key1)  # Should be longer with provider hash
    
    def test_cache_set_and_get(self, cache):
        """Test setting and getting cache entries."""
        test_data = {
            "series_name": "Test Series",
            "providers": [
                {"provider_name": "Netflix", "country": "US"}
            ]
        }
        
        # Set cache entry
        cache.set("test_key", test_data, ttl=300)
        
        # Get cache entry
        result = cache.get("test_key")
        assert result is not None
        assert result["series_name"] == "Test Series"
        assert len(result["providers"]) == 1
    
    def test_cache_expiration(self, cache):
        """Test cache entry expiration."""
        test_data = {"test": "data"}
        
        # Set entry with short TTL
        cache.set("test_key", test_data, ttl=1)
        
        # Should be available immediately
        result = cache.get("test_key")
        assert result is not None
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Should be expired
        result = cache.get("test_key")
        assert result is None
    
    def test_cache_cleanup(self, cache):
        """Test cleanup of expired entries."""
        # Add expired entry
        cache.set("expired_key", {"test": "data"}, ttl=1)
        time.sleep(1.1)
        
        # Add valid entry
        cache.set("valid_key", {"test": "data"}, ttl=300)
        
        # Run cleanup
        removed_count = cache.cleanup_expired()
        
        # Should have removed expired entry
        assert removed_count >= 1
        assert cache.get("expired_key") is None
        assert cache.get("valid_key") is not None
    
    def test_cache_blacklist_functionality(self, cache):
        """Test TVDB ID blacklist functionality."""
        # Add to blacklist
        cache.add_to_blacklist(12345, "HTTP 500 error")
        
        # Check if blacklisted
        assert cache.is_blacklisted(12345)
        
        # Get blacklist entry
        entry = cache.get_blacklist_entry(12345)
        assert entry is not None
        assert entry["reason"] == "HTTP 500 error"
        assert entry["failure_count"] == 1
    
    def test_cache_blacklist_failure_threshold(self, cache):
        """Test blacklist based on failure threshold."""
        # Create cache with higher threshold for this test
        cache.blacklist_threshold = 3
        tvdb_id = 12345
        
        # Record multiple failures (below threshold)
        cache.record_failure(tvdb_id, "Error 1")
        cache.record_failure(tvdb_id, "Error 2")
        
        # Should not be blacklisted yet (failure count = 2, threshold = 3)
        assert not cache.is_blacklisted(tvdb_id)
        
        # Record third failure (hits threshold)
        cache.record_failure(tvdb_id, "Error 3")
        
        # Should now be blacklisted
        assert cache.is_blacklisted(tvdb_id)
    
    def test_cache_with_circuit_breaker_integration(self, cache):
        """Test cache integration with circuit breaker."""
        # Get circuit breaker
        cb = cache.get_circuit_breaker()
        
        # Should start in closed state
        assert cb.state == "closed"
        
        # Simulate API failures
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        
        # Circuit breaker should be open
        assert cb.state == "open"
        
        # Cache should handle circuit breaker state
        with pytest.raises(CircuitBreakerError):
            cb.call(lambda: "test")
    
    def test_cache_provider_filtering(self, cache):
        """Test caching with provider filtering."""
        providers = [
            StreamingProvider(name="netflix", country="US"),
            StreamingProvider(name="amazon-prime", country="DE")
        ]
        
        test_data = {
            "series_name": "Test Series",
            "providers": [
                {"provider_name": "Netflix", "country": "US"},
                {"provider_name": "Amazon Prime", "country": "DE"},
                {"provider_name": "Hulu", "country": "US"}
            ]
        }
        
        # Cache with provider filtering
        key = cache._generate_key(tvdb_id=12345, providers=providers)
        cache.set(key, test_data, ttl=300)
        
        # Retrieve and verify
        result = cache.get(key)
        assert result is not None
        assert result["series_name"] == "Test Series"
    
    def test_cache_statistics(self, cache):
        """Test cache statistics collection."""
        # Perform cache operations
        cache.set("key1", {"test": "data1"}, ttl=300)
        cache.set("key2", {"test": "data2"}, ttl=300)
        
        # Cache hits
        cache.get("key1")
        cache.get("key1")
        
        # Cache miss
        cache.get("nonexistent")
        
        # Get statistics
        stats = cache.get_statistics()
        
        assert "total_entries" in stats
        assert "hit_count" in stats
        assert "miss_count" in stats
        assert "hit_rate" in stats
        
        assert stats["total_entries"] >= 2
        assert stats["hit_count"] >= 2
        assert stats["miss_count"] >= 1
    
    def test_cache_data_validation(self, cache):
        """Test data validation before caching."""
        # Valid data
        valid_data = {
            "series_name": "Test Series",
            "providers": [
                {"provider_name": "Netflix", "country": "US"}
            ]
        }
        
        # Should cache successfully
        result = cache.set("valid_key", valid_data, ttl=300)
        assert result is True
        
        # Invalid data (None provider name)
        invalid_data = {
            "series_name": "Test Series",
            "providers": [
                {"provider_name": None, "country": "US"}
            ]
        }
        
        # Should handle gracefully (sanitize data)
        cache.set("invalid_key", invalid_data, ttl=300)
        result = cache.get("invalid_key")
        
        # Should have filtered out invalid provider
        assert result is not None
        assert len(result["providers"]) == 0  # Invalid provider removed
    
    def test_cache_concurrent_access(self, cache):
        """Test cache handles concurrent access safely."""
        import threading
        import queue
        
        results = queue.Queue()
        
        def worker():
            try:
                # Set data
                cache.set("concurrent_key", {"worker": "data"}, ttl=300)
                
                # Get data
                result = cache.get("concurrent_key")
                results.put(("success", result))
            except Exception as e:
                results.put(("error", str(e)))
        
        # Start multiple threads
        threads = []
        for _ in range(5):
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
        
        # All operations should succeed
        assert success_count == 5
    
    def test_cache_error_handling(self, cache):
        """Test cache error handling for database issues."""
        # Close the database connection to simulate error
        cache._close_connection()
        
        # Operations should handle errors gracefully
        result = cache.get("test_key")
        assert result is None  # Should return None on error
        
        success = cache.set("test_key", {"test": "data"}, ttl=300)
        assert success is False  # Should return False on error