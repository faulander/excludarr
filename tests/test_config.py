"""Tests for configuration system with provider APIs."""

import tempfile
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest
import yaml
from pydantic import ValidationError

from excludarr.config import ConfigManager
from excludarr.models import (
    Config, SonarrConfig, StreamingProvider, SyncConfig,
    TMDBConfig, StreamingAvailabilityConfig, UtellyConfig, ProviderAPIsConfig
)


class TestConfigModels:
    """Test Pydantic configuration models."""

    def test_sonarr_config_valid(self):
        """Test valid Sonarr configuration."""
        config = SonarrConfig(
            url="http://localhost:8989",
            api_key="abcdefghijklmnopqrstuvwxyz123456"
        )
        assert str(config.url) == "http://localhost:8989/"
        assert config.api_key == "abcdefghijklmnopqrstuvwxyz123456"

    def test_sonarr_config_invalid_url(self):
        """Test invalid Sonarr URL."""
        with pytest.raises(ValidationError):
            SonarrConfig(
                url="not-a-valid-url",
                api_key="validkey1234567890abcdef123456"
            )

    def test_sonarr_config_short_api_key(self):
        """Test too short API key for Sonarr."""
        with pytest.raises(ValidationError):
            SonarrConfig(
                url="http://localhost:8989",
                api_key="short"
            )

    def test_tmdb_config_valid(self):
        """Test valid TMDB configuration."""
        config = TMDBConfig(
            api_key="valid_tmdb_api_key"
        )
        assert config.api_key == "valid_tmdb_api_key"
        assert config.enabled is True
        assert config.rate_limit == 40
        assert config.cache_ttl == 86400

    def test_tmdb_config_custom_values(self):
        """Test TMDB config with custom values."""
        config = TMDBConfig(
            api_key="custom_key",
            enabled=False,
            rate_limit=20,
            cache_ttl=43200
        )
        assert config.enabled is False
        assert config.rate_limit == 20
        assert config.cache_ttl == 43200

    def test_streaming_availability_config_defaults(self):
        """Test StreamingAvailabilityConfig defaults."""
        config = StreamingAvailabilityConfig()
        assert config.enabled is False
        assert config.rapidapi_key is None
        assert config.daily_quota == 100
        assert config.cache_ttl == 43200

    def test_utelly_config_defaults(self):
        """Test UtellyConfig defaults."""
        config = UtellyConfig()
        assert config.enabled is False
        assert config.rapidapi_key is None
        assert config.monthly_quota == 1000
        assert config.cache_ttl == 604800

    def test_provider_apis_config_complete(self):
        """Test complete ProviderAPIsConfig."""
        config = ProviderAPIsConfig(
            tmdb=TMDBConfig(api_key="tmdb_key"),
            streaming_availability=StreamingAvailabilityConfig(
                enabled=True,
                rapidapi_key="rapidapi_key"
            ),
            utelly=UtellyConfig(
                enabled=True,
                rapidapi_key="rapidapi_key"
            )
        )
        assert config.tmdb.api_key == "tmdb_key"
        assert config.streaming_availability.enabled is True
        assert config.utelly.enabled is True

    def test_streaming_provider_valid(self):
        """Test valid streaming provider."""
        provider = StreamingProvider(name="Netflix", country="us")
        assert provider.name == "netflix"  # Should be lowercased
        assert provider.country == "US"    # Should be uppercased

    def test_sync_config_defaults(self):
        """Test default values in sync configuration."""
        config = SyncConfig()
        assert config.action == "unmonitor"
        assert config.dry_run is True
        assert config.exclude_recent_days == 7

    def test_config_minimal_valid(self):
        """Test minimal valid configuration."""
        config_data = {
            "sonarr": {
                "url": "http://localhost:8989",
                "api_key": "validapikey1234567890abcdef12345"
            },
            "provider_apis": {
                "tmdb": {
                    "api_key": "tmdb_api_key"
                }
            },
            "streaming_providers": [
                {"name": "netflix", "country": "US"}
            ]
        }
        
        config = Config(**config_data)
        assert config.sonarr.api_key == "validapikey1234567890abcdef12345"
        assert config.provider_apis.tmdb.api_key == "tmdb_api_key"
        assert len(config.streaming_providers) == 1
        assert config.sync.dry_run is True  # Default

    def test_full_config_valid_with_all_providers(self):
        """Test complete valid configuration with all provider APIs."""
        config_data = {
            "sonarr": {
                "url": "http://localhost:8989",
                "api_key": "validapikey1234567890abcdef12345"
            },
            "provider_apis": {
                "tmdb": {
                    "api_key": "tmdb_key",
                    "enabled": True,
                    "rate_limit": 40,
                    "cache_ttl": 86400
                },
                "streaming_availability": {
                    "enabled": True,
                    "rapidapi_key": "rapidapi_key",
                    "daily_quota": 100,
                    "cache_ttl": 43200
                },
                "utelly": {
                    "enabled": True,
                    "rapidapi_key": "rapidapi_key",
                    "monthly_quota": 1000,
                    "cache_ttl": 604800
                }
            },
            "streaming_providers": [
                {"name": "netflix", "country": "US"},
                {"name": "amazon-prime", "country": "DE"}
            ],
            "sync": {
                "action": "delete",
                "dry_run": False,
                "exclude_recent_days": 14
            }
        }
        
        config = Config(**config_data)
        assert config.provider_apis.tmdb.enabled is True
        assert config.provider_apis.streaming_availability.enabled is True
        assert config.provider_apis.utelly.enabled is True
        assert len(config.streaming_providers) == 2
        assert config.sync.action == "delete"
        assert config.sync.dry_run is False

    def test_config_invalid_provider_apis_missing_tmdb_key(self):
        """Test config with missing TMDB API key."""
        config_data = {
            "sonarr": {
                "url": "http://localhost:8989",
                "api_key": "validapikey1234567890abcdef12345"
            },
            "provider_apis": {
                "tmdb": {
                    # Missing api_key
                }
            },
            "streaming_providers": [
                {"name": "netflix", "country": "US"}
            ]
        }
        
        with pytest.raises(ValidationError):
            Config(**config_data)


class TestConfigManager:
    """Test ConfigManager functionality."""

    def test_load_config_file_not_found(self):
        """Test loading non-existent config file."""
        manager = ConfigManager("non_existent.yml")
        
        with pytest.raises(FileNotFoundError):
            manager.load_config()

    def test_load_config_invalid_yaml(self):
        """Test loading invalid YAML."""
        invalid_yaml = "invalid: yaml: content: ["
        
        with patch("builtins.open", mock_open(read_data=invalid_yaml)):
            with patch("pathlib.Path.exists", return_value=True):
                manager = ConfigManager("test.yml")
                
                with pytest.raises(yaml.YAMLError):
                    manager.load_config()

    def test_load_config_valid(self):
        """Test loading valid configuration."""
        valid_config = """
sonarr:
  url: "http://localhost:8989"
  api_key: "validapikey1234567890abcdef12345"

provider_apis:
  tmdb:
    api_key: "tmdb_key"

streaming_providers:
  - name: "netflix"
    country: "US"
"""
        
        with patch("builtins.open", mock_open(read_data=valid_config)):
            with patch("pathlib.Path.exists", return_value=True):
                manager = ConfigManager("test.yml")
                config = manager.load_config()
                
                assert isinstance(config, Config)
                assert config.sonarr.api_key == "validapikey1234567890abcdef12345"
                assert config.provider_apis.tmdb.api_key == "tmdb_key"

    def test_validate_config_valid(self):
        """Test validation of valid config."""
        valid_config = """
sonarr:
  url: "http://localhost:8989"
  api_key: "validapikey1234567890abcdef12345"

provider_apis:
  tmdb:
    api_key: "tmdb_key"

streaming_providers:
  - name: "netflix"
    country: "US"
"""
        
        with patch("builtins.open", mock_open(read_data=valid_config)):
            with patch("pathlib.Path.exists", return_value=True):
                manager = ConfigManager("test.yml")
                is_valid, errors = manager.validate_config()
                
                assert is_valid is True
                assert errors is None

    def test_validate_config_invalid(self):
        """Test validation of invalid config."""
        invalid_config = """
sonarr:
  url: "invalid-url"
  api_key: "short"

provider_apis:
  tmdb:
    api_key: ""

streaming_providers: []
"""
        
        with patch("builtins.open", mock_open(read_data=invalid_config)):
            with patch("pathlib.Path.exists", return_value=True):
                manager = ConfigManager("test.yml")
                is_valid, errors = manager.validate_config()
                
                assert is_valid is False
                assert isinstance(errors, list)
                assert len(errors) > 0

    def test_create_example_config(self):
        """Test creating example configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_config.yml"
            manager = ConfigManager(str(config_path))
            
            manager.create_example_config()
            
            assert config_path.exists()
            
            # Verify the created config can be loaded
            config = manager.load_config()
            assert isinstance(config, Config)
            assert config.provider_apis.tmdb.api_key == "your-tmdb-api-key-here"


class TestConfigManagerErrors:
    """Test error conditions in config manager."""
    
    def test_load_config_empty_file(self):
        """Test loading empty configuration file."""
        empty_config = ""
        
        with patch("builtins.open", mock_open(read_data=empty_config)):
            with patch("pathlib.Path.exists", return_value=True):
                manager = ConfigManager("test.yml")
                
                with pytest.raises(ValidationError):
                    manager.load_config()
    
    def test_load_config_yaml_null(self):
        """Test loading YAML file that parses to None."""
        yaml_null = "# Just a comment"
        
        with patch("builtins.open", mock_open(read_data=yaml_null)):
            with patch("pathlib.Path.exists", return_value=True):
                manager = ConfigManager("test.yml")
                
                with pytest.raises(ValidationError):
                    manager.load_config()
    
    def test_validate_config_pydantic_error_without_fields(self):
        """Test validation error handling when Pydantic error has no field info."""
        with patch("builtins.open", mock_open(read_data="invalid: yaml: content:")):
            with patch("pathlib.Path.exists", return_value=True):
                manager = ConfigManager("test.yml")
                
                # This should cover the generic error handling path (line 82)
                is_valid, errors = manager.validate_config()
                assert is_valid is False
                assert len(errors) > 0
    
    def test_create_example_config_file_exists(self):
        """Test creating example config when file already exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "existing_config.yml"
            
            # Create an existing file
            config_path.write_text("existing content")
            
            manager = ConfigManager(str(config_path))
            
            with pytest.raises(FileExistsError, match="Configuration file already exists"):
                manager.create_example_config()
    

class TestConfigManagerInfo:
    """Test get_config_info method with various scenarios."""
    
    def test_get_config_info_file_not_exists(self):
        """Test get_config_info when file doesn't exist."""
        manager = ConfigManager("nonexistent.yml")
        
        info = manager.get_config_info()
        
        assert info["config_path"] == "nonexistent.yml"
        assert info["exists"] is False
        assert info["readable"] is False
        assert info["valid"] is False
        assert info["providers_count"] == 0
        assert info["errors"] == []
    
    def test_get_config_info_file_exists_but_not_readable(self):
        """Test get_config_info when file exists but is not readable (e.g., directory)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a directory with the same name as config file
            config_path = Path(temp_dir) / "config"
            config_path.mkdir()
            
            manager = ConfigManager(str(config_path))
            
            info = manager.get_config_info()
            
            assert info["exists"] is True
            assert info["readable"] is False
            assert info["valid"] is False
    
    def test_get_config_info_valid_config(self):
        """Test get_config_info with valid configuration."""
        valid_config = """
sonarr:
  url: "http://localhost:8989"
  api_key: "validkey1234567890abcdef12345678"

provider_apis:
  tmdb:
    api_key: "valid_tmdb_key"

streaming_providers:
  - name: "netflix"
    country: "US"
  - name: "amazon-prime" 
    country: "DE"

sync:
  action: "unmonitor"
  dry_run: true
  exclude_recent_days: 7
"""
        
        with patch("builtins.open", mock_open(read_data=valid_config)):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.is_file", return_value=True):
                    manager = ConfigManager("test.yml")
                    
                    info = manager.get_config_info()
                    
                    assert info["exists"] is True
                    assert info["readable"] is True
                    assert info["valid"] is True
                    assert info["providers_count"] == 2
                    assert info["action"] == "unmonitor"
                    assert info["dry_run"] is True
                    assert info["errors"] == []
    
    def test_get_config_info_invalid_config(self):
        """Test get_config_info with invalid configuration."""
        invalid_config = """
sonarr:
  url: "invalid-url"
  api_key: "short"
"""
        
        with patch("builtins.open", mock_open(read_data=invalid_config)):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.is_file", return_value=True):
                    manager = ConfigManager("test.yml")
                    
                    info = manager.get_config_info()
                    
                    assert info["exists"] is True
                    assert info["readable"] is True
                    assert info["valid"] is False
                    assert len(info["errors"]) > 0
    
    def test_get_config_info_load_config_exception(self):
        """Test get_config_info when load_config raises exception during info gathering."""
        valid_basic_config = """
sonarr:
  url: "http://localhost:8989"
  api_key: "validkey1234567890abcdef12345678"

provider_apis:
  tmdb:
    api_key: "valid_tmdb_key"

streaming_providers:
  - name: "netflix"
    country: "US"
"""
        
        with patch("builtins.open", mock_open(read_data=valid_basic_config)):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.is_file", return_value=True):
                    manager = ConfigManager("test.yml")
                    
                    # Mock load_config to raise exception during info gathering
                    original_load_config = manager.load_config
                    call_count = 0
                    
                    def mock_load_config():
                        nonlocal call_count
                        call_count += 1
                        if call_count == 1:
                            # First call for validation - should succeed
                            return original_load_config()
                        else:
                            # Second call for info gathering - should fail
                            raise Exception("Mock exception during info gathering")
                    
                    with patch.object(manager, 'load_config', side_effect=mock_load_config):
                        info = manager.get_config_info()
                        
                        assert info["valid"] is True  # Validation succeeded
                        # But providers_count etc. should use defaults due to exception
                        assert "providers_count" in info
                        assert "action" not in info or info.get("action") is None