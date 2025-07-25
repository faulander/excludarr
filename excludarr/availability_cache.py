#!/usr/bin/env python3
"""Availability caching system with reliability features."""

import sqlite3
import json
import hashlib
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from dataclasses import dataclass
from loguru import logger

from .models import StreamingProvider


@dataclass
class CacheEntry:
    """Cache entry with expiration."""
    key: str
    data: Dict[str, Any]
    expires_at: datetime
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return datetime.now() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize cache entry for storage."""
        return {
            "key": self.key,
            "data": self.data,
            "expires_at": self.expires_at.isoformat(),
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheEntry":
        """Deserialize cache entry from storage."""
        return cls(
            key=data["key"],
            data=data["data"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
        )


class CircuitBreakerError(Exception):
    """Circuit breaker is open, blocking calls."""
    pass


class CircuitBreaker:
    """Circuit breaker pattern implementation for API calls."""
    
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
        self._lock = threading.Lock()
    
    def record_failure(self):
        """Record an API failure."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
    
    def record_success(self):
        """Record an API success."""
        with self._lock:
            self.failure_count = 0
            self.last_failure_time = None
            self.state = "closed"
            logger.info("Circuit breaker reset after successful call")
    
    def can_attempt_call(self) -> bool:
        """Check if we can attempt an API call."""
        with self._lock:
            if self.state == "closed":
                return True
            
            if self.state == "open":
                # Check if recovery timeout has passed
                if (self.last_failure_time and 
                    datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout)):
                    self.state = "half-open"
                    logger.info("Circuit breaker entering half-open state")
                    return True
                return False
            
            if self.state == "half-open":
                return True
            
            return False
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        if not self.can_attempt_call():
            raise CircuitBreakerError("Circuit breaker is open")
        
        try:
            result = func(*args, **kwargs)
            if self.state == "half-open":
                self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise


class AvailabilityCache:
    """TTL-based caching system for streaming availability data."""
    
    def __init__(
        self, 
        db_path: str = "availability_cache.db",
        default_ttl: int = 300,
        cleanup_interval: int = 3600,
        blacklist_threshold: int = 1
    ):
        self.db_path = db_path
        self.default_ttl = default_ttl
        self.cleanup_interval = cleanup_interval
        self.blacklist_threshold = blacklist_threshold
        self._lock = threading.Lock()
        self._circuit_breaker = CircuitBreaker()
        self._last_cleanup = datetime.now()
        
        # Statistics
        self._hit_count = 0
        self._miss_count = 0
        
        # Initialize database
        self._init_database()
        
        logger.info(f"Initialized availability cache with {default_ttl}s TTL")
    
    def _init_database(self):
        """Initialize SQLite database for caching."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS availability_cache (
                        key TEXT PRIMARY KEY,
                        data TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tvdb_blacklist (
                        tvdb_id INTEGER PRIMARY KEY,
                        reason TEXT NOT NULL,
                        failure_count INTEGER DEFAULT 1,
                        first_failure TEXT NOT NULL,
                        last_failure TEXT NOT NULL
                    )
                """)
                
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_expires_at ON availability_cache(expires_at)
                """)
                
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize cache database: {e}")
    
    def _generate_key(
        self, 
        tvdb_id: Optional[int] = None, 
        imdb_id: Optional[str] = None,
        providers: Optional[List[StreamingProvider]] = None
    ) -> str:
        """Generate cache key from parameters."""
        key_parts = []
        
        if tvdb_id:
            key_parts.append(f"tvdb_{tvdb_id}")
        
        if imdb_id:
            key_parts.append(f"imdb_{imdb_id}")
        
        if providers:
            # Create deterministic hash of providers
            provider_data = sorted([
                f"{p.name}_{p.country}" for p in providers
            ])
            provider_hash = hashlib.md5(
                "|".join(provider_data).encode()
            ).hexdigest()[:8]
            key_parts.append(f"providers_{provider_hash}")
        
        return "_".join(key_parts)
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached data by key."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT data, expires_at FROM availability_cache WHERE key = ?",
                    (key,)
                )
                row = cursor.fetchone()
                
                if row:
                    data_json, expires_at_str = row
                    expires_at = datetime.fromisoformat(expires_at_str)
                    
                    if datetime.now() <= expires_at:
                        self._hit_count += 1
                        return json.loads(data_json)
                    else:
                        # Entry is expired, remove it
                        cursor.execute("DELETE FROM availability_cache WHERE key = ?", (key,))
                        conn.commit()
                
                self._miss_count += 1
                return None
                
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self._miss_count += 1
            return None
    
    def set(self, key: str, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set cached data with TTL."""
        if ttl is None:
            ttl = self.default_ttl
        
        try:
            # Validate and sanitize data
            sanitized_data = self._sanitize_data(data)
            
            expires_at = datetime.now() + timedelta(seconds=ttl)
            created_at = datetime.now()
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO availability_cache 
                    (key, data, expires_at, created_at) 
                    VALUES (?, ?, ?, ?)
                    """,
                    (key, json.dumps(sanitized_data), expires_at.isoformat(), created_at.isoformat())
                )
                conn.commit()
            
            logger.debug(f"Cached data for key '{key}' with {ttl}s TTL")
            
            # Opportunistic cleanup
            self._maybe_cleanup()
            
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    def _sanitize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize data before caching to ensure quality."""
        if not isinstance(data, dict):
            return data
        
        sanitized = data.copy()
        
        # Sanitize providers list
        if "providers" in sanitized and isinstance(sanitized["providers"], list):
            clean_providers = []
            for provider in sanitized["providers"]:
                if (isinstance(provider, dict) and 
                    provider.get("provider_name") is not None and
                    provider.get("provider_name") != "" and
                    provider.get("country") is not None and
                    provider.get("country") != ""):
                    
                    # Normalize provider name
                    provider["provider_name"] = str(provider["provider_name"]).strip()
                    provider["country"] = str(provider["country"]).strip().upper()
                    clean_providers.append(provider)
            
            sanitized["providers"] = clean_providers
            logger.debug(f"Sanitized providers: {len(data.get('providers', []))} -> {len(clean_providers)}")
        
        return sanitized
    
    def cleanup_expired(self) -> int:
        """Remove expired cache entries."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                
                # Count expired entries
                cursor.execute(
                    "SELECT COUNT(*) FROM availability_cache WHERE expires_at <= ?",
                    (now,)
                )
                expired_count = cursor.fetchone()[0]
                
                # Remove expired entries
                cursor.execute(
                    "DELETE FROM availability_cache WHERE expires_at <= ?",
                    (now,)
                )
                conn.commit()
                
                logger.info(f"Cleaned up {expired_count} expired cache entries")
                return expired_count
                
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")
            return 0
    
    def _maybe_cleanup(self):
        """Perform cleanup if interval has passed."""
        now = datetime.now()
        if now - self._last_cleanup > timedelta(seconds=self.cleanup_interval):
            self._last_cleanup = now
            self.cleanup_expired()
    
    def add_to_blacklist(self, tvdb_id: int, reason: str):
        """Add TVDB ID to blacklist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                now = datetime.now().isoformat()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tvdb_blacklist 
                    (tvdb_id, reason, failure_count, first_failure, last_failure) 
                    VALUES (
                        ?, ?, 
                        COALESCE((SELECT failure_count + 1 FROM tvdb_blacklist WHERE tvdb_id = ?), 1),
                        COALESCE((SELECT first_failure FROM tvdb_blacklist WHERE tvdb_id = ?), ?),
                        ?
                    )
                    """,
                    (tvdb_id, reason, tvdb_id, tvdb_id, now, now)
                )
                conn.commit()
            
            logger.warning(f"Added TVDB ID {tvdb_id} to blacklist: {reason}")
            
        except Exception as e:
            logger.error(f"Blacklist add error: {e}")
    
    def is_blacklisted(self, tvdb_id: int) -> bool:
        """Check if TVDB ID is blacklisted."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT failure_count FROM tvdb_blacklist WHERE tvdb_id = ?",
                    (tvdb_id,)
                )
                row = cursor.fetchone()
                return row is not None and row[0] >= self.blacklist_threshold
                
        except Exception as e:
            logger.error(f"Blacklist check error: {e}")
            return False
    
    def get_blacklist_entry(self, tvdb_id: int) -> Optional[Dict[str, Any]]:
        """Get blacklist entry details."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT reason, failure_count, first_failure, last_failure 
                    FROM tvdb_blacklist WHERE tvdb_id = ?
                    """,
                    (tvdb_id,)
                )
                row = cursor.fetchone()
                
                if row:
                    return {
                        "reason": row[0],
                        "failure_count": row[1],
                        "first_failure": row[2],
                        "last_failure": row[3]
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"Blacklist entry get error: {e}")
            return None
    
    def record_failure(self, tvdb_id: int, reason: str):
        """Record API failure for TVDB ID."""
        self.add_to_blacklist(tvdb_id, reason)
        
        # Check if should be blacklisted
        if self.is_blacklisted(tvdb_id):
            logger.warning(f"TVDB ID {tvdb_id} exceeded failure threshold and is now blacklisted")
    
    def get_circuit_breaker(self) -> CircuitBreaker:
        """Get circuit breaker instance."""
        return self._circuit_breaker
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Total entries
                cursor.execute("SELECT COUNT(*) FROM availability_cache")
                total_entries = cursor.fetchone()[0]
                
                # Expired entries
                now = datetime.now().isoformat()
                cursor.execute(
                    "SELECT COUNT(*) FROM availability_cache WHERE expires_at <= ?",
                    (now,)
                )
                expired_entries = cursor.fetchone()[0]
                
                # Blacklisted IDs
                cursor.execute("SELECT COUNT(*) FROM tvdb_blacklist")
                blacklisted_count = cursor.fetchone()[0]
                
                # Calculate hit rate
                total_requests = self._hit_count + self._miss_count
                hit_rate = (self._hit_count / total_requests * 100) if total_requests > 0 else 0
                
                return {
                    "total_entries": total_entries,
                    "active_entries": total_entries - expired_entries,
                    "expired_entries": expired_entries,
                    "blacklisted_count": blacklisted_count,
                    "hit_count": self._hit_count,
                    "miss_count": self._miss_count,
                    "hit_rate": round(hit_rate, 2),
                    "circuit_breaker_state": self._circuit_breaker.state,
                    "circuit_breaker_failures": self._circuit_breaker.failure_count
                }
                
        except Exception as e:
            logger.error(f"Statistics error: {e}")
            return {
                "error": str(e),
                "hit_count": self._hit_count,
                "miss_count": self._miss_count
            }
    
    def clear_cache(self):
        """Clear all cache entries."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM availability_cache")
                conn.commit()
            
            logger.info("Cleared all cache entries")
            
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
    
    def clear_blacklist(self):
        """Clear blacklist entries."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM tvdb_blacklist")
                conn.commit()
            
            logger.info("Cleared blacklist entries")
            
        except Exception as e:
            logger.error(f"Blacklist clear error: {e}")
    
    def _close_connection(self):
        """Close database connection (for testing)."""
        # This method is primarily for testing error conditions
        # Invalidate the database path to simulate connection issues
        self.db_path = "/invalid/path/test.db"