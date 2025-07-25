"""Tests for configuration system."""

import tempfile
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest
import yaml
from pydantic import ValidationError

from excludarr.config import ConfigManager
from excludarr.models import Config, SonarrConfig, JellyseerrConfig, StreamingProvider, SyncConfig


class TestConfigModels:
    """Test Pydantic configuration models."""

    def test_sonarr_config_valid(self):
        """Test valid Sonarr configuration."""
        config = SonarrConfig(
            url="http://localhost:8989",
            api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        )
        assert str(config.url) == "http://localhost:8989/"
        assert config.api_key == "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"

    def test_sonarr_config_invalid_url(self):
        """Test invalid Sonarr URL."""
        with pytest.raises(ValidationError):
            SonarrConfig(url="invalid_url", api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")

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
        """Test invalid Jellyseerr URL."""
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

    def test_streaming_provider_valid(self):
        """Test valid streaming provider."""
        provider = StreamingProvider(
            name="netflix",
            country="US"
        )
        assert provider.name == "netflix"
        assert provider.country == "US"

    def test_streaming_provider_invalid_country(self):
        """Test invalid country code."""
        with pytest.raises(ValidationError):
            StreamingProvider(name="netflix", country="USA")  # Should be 2-letter

    def test_sync_config_valid(self):
        """Test valid sync configuration."""
        config = SyncConfig(
            action="unmonitor",
            dry_run=True
        )
        assert config.action == "unmonitor"
        assert config.dry_run is True

    def test_sync_config_invalid_action(self):
        """Test invalid sync action."""
        with pytest.raises(ValidationError):
            SyncConfig(action="invalid", dry_run=False)

    def test_full_config_valid(self):
        """Test complete valid configuration."""
        config_data = {
            "sonarr": {
                "url": "http://localhost:8989",
                "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
            },
            "streaming_providers": [
                {"name": "netflix", "country": "US"},
                {"name": "amazon-prime", "country": "DE"}
            ],
            "sync": {
                "action": "unmonitor",
                "dry_run": False
            }
        }
        config = Config(**config_data)
        assert len(config.streaming_providers) == 2
        assert config.sync.action == "unmonitor"
        assert config.jellyseerr is None  # Optional field

    def test_full_config_valid_with_jellyseerr(self):
        """Test complete valid configuration with Jellyseerr."""
        config_data = {
            "sonarr": {
                "url": "http://localhost:8989",
                "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
            },
            "jellyseerr": {
                "url": "http://localhost:5055",
                "api_key": "b1c2d3e4f5g6h7i8j9k0l1m2n3o4p5q6",
                "timeout": 45,
                "cache_ttl": 600
            },
            "streaming_providers": [
                {"name": "netflix", "country": "US"},
                {"name": "amazon-prime", "country": "DE"}
            ],
            "sync": {
                "action": "unmonitor",
                "dry_run": False
            }
        }
        config = Config(**config_data)
        assert len(config.streaming_providers) == 2
        assert config.sync.action == "unmonitor"
        assert config.jellyseerr is not None
        assert str(config.jellyseerr.url) == "http://localhost:5055/"
        assert config.jellyseerr.timeout == 45
        assert config.jellyseerr.cache_ttl == 600


class TestConfigManager:
    """Test configuration manager."""

    def test_load_config_valid_file(self):
        """Test loading valid configuration file."""
        config_data = {
            "sonarr": {
                "url": "http://localhost:8989",
                "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
            },
            "streaming_providers": [
                {"name": "netflix", "country": "US"}
            ],
            "sync": {
                "action": "unmonitor",
                "dry_run": False
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump(config_data, f)
            config_file = f.name
        
        try:
            manager = ConfigManager(config_file)
            config = manager.load_config()
            assert str(config.sonarr.url) == "http://localhost:8989/"
            assert len(config.streaming_providers) == 1
        finally:
            Path(config_file).unlink()

    def test_load_config_file_not_found(self):
        """Test loading non-existent configuration file."""
        manager = ConfigManager("nonexistent.yml")
        with pytest.raises(FileNotFoundError):
            manager.load_config()

    def test_load_config_invalid_yaml(self):
        """Test loading invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            config_file = f.name
        
        try:
            manager = ConfigManager(config_file)
            with pytest.raises(yaml.YAMLError):
                manager.load_config()
        finally:
            Path(config_file).unlink()

    def test_load_config_validation_error(self):
        """Test loading configuration with validation errors."""
        config_data = {
            "sonarr": {
                "url": "invalid_url",  # Invalid URL
                "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
            },
            "streaming_providers": [],
            "sync": {
                "action": "unmonitor",
                "dry_run": False
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump(config_data, f)
            config_file = f.name
        
        try:
            manager = ConfigManager(config_file)
            with pytest.raises(ValidationError):
                manager.load_config()
        finally:
            Path(config_file).unlink()

    def test_validate_config_valid(self):
        """Test configuration validation with valid config."""
        config_data = {
            "sonarr": {
                "url": "http://localhost:8989",
                "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
            },
            "streaming_providers": [
                {"name": "netflix", "country": "US"}
            ],
            "sync": {
                "action": "unmonitor",
                "dry_run": False
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump(config_data, f)
            config_file = f.name
        
        try:
            manager = ConfigManager(config_file)
            is_valid, errors = manager.validate_config()
            assert is_valid is True
            assert errors is None
        finally:
            Path(config_file).unlink()

    def test_validate_config_invalid(self):
        """Test configuration validation with invalid config."""
        config_data = {
            "sonarr": {
                "url": "invalid_url",
                "api_key": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
            },
            "streaming_providers": [],
            "sync": {
                "action": "invalid_action",
                "dry_run": False
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump(config_data, f)
            config_file = f.name
        
        try:
            manager = ConfigManager(config_file)
            is_valid, errors = manager.validate_config()
            assert is_valid is False
            assert errors is not None
            assert len(errors) >= 1
        finally:
            Path(config_file).unlink()

    def test_create_example_config(self):
        """Test creating example configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            config_file = f.name
        
        try:
            # Remove the temp file so we can test creation
            Path(config_file).unlink()
            
            manager = ConfigManager(config_file)
            manager.create_example_config()
            
            # Verify file was created and is valid
            assert Path(config_file).exists()
            created_config = manager.load_config()
            assert created_config.sonarr.url is not None
            assert len(created_config.streaming_providers) >= 1
        finally:
            if Path(config_file).exists():
                Path(config_file).unlink()