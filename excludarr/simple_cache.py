"""Simplified TTL-based caching system for TMDB data."""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from dataclasses import dataclass
from loguru import logger


@dataclass
class TMDBCacheEntry:
    """Simple cache entry for TMDB data."""
    key: str
    data: Dict[str, Any]
    expires_at: datetime
    created_at: datetime
    cache_type: str  # 'provider_data' or 'id_mapping'
    
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return datetime.now() > self.expires_at
    
    def is_permanent(self) -> bool:
        """Check if this is a permanent cache entry (ID mappings)."""
        return self.cache_type == 'id_mapping'
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize cache entry for storage."""
        return {
            "key": self.key,
            "data": self.data,
            "expires_at": self.expires_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "cache_type": self.cache_type
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TMDBCacheEntry":
        """Deserialize cache entry from storage."""
        return cls(
            key=data["key"],
            data=data["data"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            cache_type=data.get("cache_type", "provider_data")
        )


class TMDBCache:
    """Simplified TTL-based caching system for TMDB data."""
    
    def __init__(
        self, 
        db_path: str = "tmdb_cache.db",
        provider_data_ttl: int = 86400,  # 24 hours for provider data
        cleanup_interval: int = 3600     # 1 hour cleanup interval
    ):
        """Initialize TMDB cache.
        
        Args:
            db_path: Path to SQLite database file
            provider_data_ttl: TTL for provider data in seconds (default: 24h)
            cleanup_interval: How often to cleanup expired entries in seconds
        """
        self.db_path = db_path
        self.provider_data_ttl = provider_data_ttl
        self.cleanup_interval = cleanup_interval
        self._last_cleanup = datetime.now()
        
        # Statistics
        self._hit_count = 0
        self._miss_count = 0
        self._id_mapping_hits = 0
        self._provider_data_hits = 0
        
        # Initialize database
        self._init_database()
        
        logger.info(f"Initialized TMDB cache with {provider_data_ttl}s TTL for provider data")
    
    def _init_database(self):
        """Initialize SQLite database schema."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tmdb_cache (
                        key TEXT PRIMARY KEY,
                        data TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        cache_type TEXT NOT NULL DEFAULT 'provider_data'
                    )
                """)
                
                # Create index for efficient lookups
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_type ON tmdb_cache(cache_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_expires_at ON tmdb_cache(expires_at)")
                
                conn.commit()
            
            logger.debug(f"TMDB cache database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize cache database at {self.db_path}: {e}")
            # Don't raise exception, just log error
    
    def _generate_key(self, prefix: str, identifier: str, country: Optional[str] = None) -> str:
        """Generate cache key.
        
        Args:
            prefix: Key prefix ('id_mapping', 'providers')
            identifier: Main identifier (IMDb ID, TMDB ID)
            country: Country code for provider data
            
        Returns:
            Generated cache key
        """
        if country:
            return f"{prefix}:{identifier}:{country}"
        return f"{prefix}:{identifier}"
    
    def get_id_mapping(self, imdb_id: str) -> Optional[int]:
        """Get TMDB ID for IMDb ID from cache.
        
        Args:
            imdb_id: IMDb ID (e.g., 'tt1234567')
            
        Returns:
            TMDB ID if found in cache, None otherwise
        """
        key = self._generate_key("id_mapping", imdb_id)
        entry = self._get_entry(key)
        
        if entry and not entry.is_expired():
            self._id_mapping_hits += 1
            logger.debug(f"Cache hit for ID mapping: {imdb_id} -> {entry.data.get('tmdb_id')}")
            return entry.data.get("tmdb_id")
        
        return None
    
    def set_id_mapping(self, imdb_id: str, tmdb_id: int):
        """Store IMDb to TMDB ID mapping (permanent cache).
        
        Args:
            imdb_id: IMDb ID (e.g., 'tt1234567')
            tmdb_id: TMDB series ID
        """
        key = self._generate_key("id_mapping", imdb_id)
        
        # ID mappings are permanent (far future expiry)
        expires_at = datetime.now() + timedelta(days=365 * 10)  # 10 years
        
        entry = TMDBCacheEntry(
            key=key,
            data={"tmdb_id": tmdb_id, "imdb_id": imdb_id},
            expires_at=expires_at,
            created_at=datetime.now(),
            cache_type="id_mapping"
        )
        
        self._set_entry(entry)
        logger.debug(f"Cached ID mapping: {imdb_id} -> {tmdb_id}")
    
    def get_provider_data(self, tmdb_id: int, country: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get provider data from cache.
        
        Args:
            tmdb_id: TMDB series ID
            country: Optional country filter
            
        Returns:
            Provider data if found and not expired, None otherwise
        """
        key = self._generate_key("providers", str(tmdb_id), country)
        entry = self._get_entry(key)
        
        if entry and not entry.is_expired():
            self._provider_data_hits += 1
            logger.debug(f"Cache hit for provider data: TMDB {tmdb_id} ({country or 'all'})")
            return entry.data
        
        return None
    
    def set_provider_data(self, tmdb_id: int, data: Dict[str, Any], country: Optional[str] = None):
        """Store provider data in cache.
        
        Args:
            tmdb_id: TMDB series ID
            data: Provider availability data
            country: Optional country filter
        """
        key = self._generate_key("providers", str(tmdb_id), country)
        
        expires_at = datetime.now() + timedelta(seconds=self.provider_data_ttl)
        
        entry = TMDBCacheEntry(
            key=key,
            data=data,
            expires_at=expires_at,
            created_at=datetime.now(),
            cache_type="provider_data"
        )
        
        self._set_entry(entry)
        logger.debug(f"Cached provider data: TMDB {tmdb_id} ({country or 'all'}) - expires {expires_at}")
    
    def _get_entry(self, key: str) -> Optional[TMDBCacheEntry]:
        """Get cache entry from database.
        
        Args:
            key: Cache key
            
        Returns:
            Cache entry if found, None otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT key, data, expires_at, created_at, cache_type FROM tmdb_cache WHERE key = ?",
                    (key,)
                )
                row = cursor.fetchone()
                
                if row:
                    self._hit_count += 1
                    return TMDBCacheEntry(
                        key=row[0],
                        data=json.loads(row[1]),
                        expires_at=datetime.fromisoformat(row[2]),
                        created_at=datetime.fromisoformat(row[3]),
                        cache_type=row[4]
                    )
                else:
                    self._miss_count += 1
                    return None
                    
        except Exception as e:
            logger.error(f"Error reading from cache: {e}")
            self._miss_count += 1
            return None
    
    def _set_entry(self, entry: TMDBCacheEntry):
        """Store cache entry in database.
        
        Args:
            entry: Cache entry to store
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO tmdb_cache 
                       (key, data, expires_at, created_at, cache_type) 
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        entry.key,
                        json.dumps(entry.data),
                        entry.expires_at.isoformat(),
                        entry.created_at.isoformat(),
                        entry.cache_type
                    )
                )
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error writing to cache: {e}")
    
    def cleanup_expired(self) -> int:
        """Remove expired entries from cache.
        
        Returns:
            Number of entries removed
        """
        try:
            current_time = datetime.now().isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                # Only remove expired provider data, keep permanent ID mappings
                cursor = conn.execute(
                    "DELETE FROM tmdb_cache WHERE expires_at < ? AND cache_type = 'provider_data'",
                    (current_time,)
                )
                removed_count = cursor.rowcount
                conn.commit()
                
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} expired cache entries")
            
            self._last_cleanup = datetime.now()
            return removed_count
            
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")
            return 0
    
    def cleanup_if_needed(self):
        """Cleanup expired entries if cleanup interval has passed."""
        if datetime.now() - self._last_cleanup > timedelta(seconds=self.cleanup_interval):
            self.cleanup_expired()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        total_requests = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total_requests * 100) if total_requests > 0 else 0
        
        # Get database statistics
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM tmdb_cache WHERE cache_type = 'id_mapping'")
                id_mapping_count = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(*) FROM tmdb_cache WHERE cache_type = 'provider_data'")
                provider_data_count = cursor.fetchone()[0]
                
        except Exception:
            id_mapping_count = 0
            provider_data_count = 0
        
        return {
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": round(hit_rate, 2),
            "id_mapping_hits": self._id_mapping_hits,
            "provider_data_hits": self._provider_data_hits,
            "cached_id_mappings": id_mapping_count,
            "cached_provider_data": provider_data_count,
            "total_cached_entries": id_mapping_count + provider_data_count,
            "provider_data_ttl": self.provider_data_ttl,
            "last_cleanup": self._last_cleanup.isoformat()
        }
    
    def clear_cache(self, cache_type: Optional[str] = None):
        """Clear cache entries.
        
        Args:
            cache_type: Type of cache to clear ('id_mapping', 'provider_data'), or None for all
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                if cache_type:
                    cursor = conn.execute("DELETE FROM tmdb_cache WHERE cache_type = ?", (cache_type,))
                else:
                    cursor = conn.execute("DELETE FROM tmdb_cache")
                
                removed_count = cursor.rowcount
                conn.commit()
                
            logger.info(f"Cleared {removed_count} cache entries{f' of type {cache_type}' if cache_type else ''}")
            
            # Reset statistics
            if not cache_type or cache_type == 'provider_data':
                self._provider_data_hits = 0
            if not cache_type or cache_type == 'id_mapping':
                self._id_mapping_hits = 0
            
            if not cache_type:
                self._hit_count = 0
                self._miss_count = 0
                
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
    
    def invalidate_provider_data(self, tmdb_id: int, country: Optional[str] = None):
        """Invalidate cached provider data for a specific TMDB ID.
        
        Args:
            tmdb_id: TMDB series ID
            country: Optional country filter
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                if country:
                    key_pattern = f"providers:{tmdb_id}:{country}"
                    cursor = conn.execute("DELETE FROM tmdb_cache WHERE key = ?", (key_pattern,))
                else:
                    key_pattern = f"providers:{tmdb_id}%"
                    cursor = conn.execute("DELETE FROM tmdb_cache WHERE key LIKE ?", (key_pattern,))
                
                removed_count = cursor.rowcount
                conn.commit()
                
            if removed_count > 0:
                logger.debug(f"Invalidated {removed_count} provider data entries for TMDB {tmdb_id}")
                
        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")