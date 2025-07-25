"""Tests for the CLI interface."""

import json
import pytest
from unittest.mock import patch, Mock, mock_open
from click.testing import CliRunner
from pathlib import Path
import tempfile
import os

from excludarr import __version__
from excludarr.cli import cli
from excludarr.config import ConfigManager
from excludarr.providers import ProviderError
from excludarr.sync import SyncError


class TestCLI:
    """Test the main CLI interface."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_cli_without_args_shows_help(self):
        """Test that running CLI without arguments shows help."""
        result = self.runner.invoke(cli, [])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "Commands:" in result.output

    def test_cli_help_flag(self):
        """Test that --help flag works."""
        result = self.runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "Options:" in result.output
        assert "Commands:" in result.output

    def test_version_command(self):
        """Test the version command."""
        result = self.runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_version_flag(self):
        """Test the --version flag."""
        result = self.runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert f"excludarr, version {__version__}" in result.output

    def test_verbose_flag(self):
        """Test verbose logging flags."""
        # Test single -v
        result = self.runner.invoke(cli, ["-v", "version"])
        assert result.exit_code == 0
        
        # Test double -vv
        result = self.runner.invoke(cli, ["-vv", "version"])
        assert result.exit_code == 0
        
        # Test triple -vvv
        result = self.runner.invoke(cli, ["-vvv", "version"])
        assert result.exit_code == 0

    def test_config_option(self):
        """Test the --config option."""
        result = self.runner.invoke(cli, ["--config", "test.yml", "version"])
        assert result.exit_code == 0


class TestConfigCommands:
    """Test config management commands."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch('excludarr.cli.ConfigManager')
    def test_config_init_success(self, mock_config_manager):
        """Test successful config initialization."""
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_manager.config_path = Path("test.yml")
        
        result = self.runner.invoke(cli, ["config", "init"])
        
        assert result.exit_code == 0
        assert "✓ Example configuration created" in result.output
        assert "Next steps:" in result.output
        mock_manager.create_example_config.assert_called_once()

    @patch('excludarr.cli.ConfigManager')
    def test_config_init_force(self, mock_config_manager):
        """Test config initialization with --force flag."""
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_manager.config_path = mock_path
        
        result = self.runner.invoke(cli, ["config", "init", "--force"])
        
        assert result.exit_code == 0
        assert "Removed existing config" in result.output
        mock_path.unlink.assert_called_once()

    @patch('excludarr.cli.ConfigManager')
    def test_config_init_file_exists_error(self, mock_config_manager):
        """Test config initialization when file exists without force."""
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_manager.create_example_config.side_effect = FileExistsError("Config already exists")
        
        result = self.runner.invoke(cli, ["config", "init"])
        
        assert result.exit_code == 1
        assert "Config already exists" in result.output
        assert "Use --force to overwrite" in result.output

    @patch('excludarr.cli.ConfigManager')
    def test_config_validate_success(self, mock_config_manager):
        """Test successful config validation."""
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_manager.validate_config.return_value = (True, [])
        
        # Mock config loading for summary
        mock_config = Mock()
        mock_config.sonarr.url = "http://localhost:8989"
        mock_config.streaming_providers = [Mock(), Mock()]
        mock_config.sync.action = "unmonitor"
        mock_config.sync.dry_run = True
        mock_manager.load_config.return_value = mock_config
        
        result = self.runner.invoke(cli, ["config", "validate"])
        
        assert result.exit_code == 0
        assert "✓ Configuration is valid" in result.output
        assert "Configuration Summary" in result.output

    @patch('excludarr.cli.ConfigManager')
    def test_config_validate_failure(self, mock_config_manager):
        """Test config validation failure."""
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_manager.validate_config.return_value = (False, ["Invalid API key", "Missing provider"])
        
        result = self.runner.invoke(cli, ["config", "validate"])
        
        assert result.exit_code == 1
        assert "✗ Configuration validation failed" in result.output
        assert "Invalid API key" in result.output
        assert "Missing provider" in result.output

    @patch('excludarr.cli.ConfigManager')
    def test_config_info(self, mock_config_manager):
        """Test config info command."""
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_manager.get_config_info.return_value = {
            "config_path": "/path/to/config.yml",
            "exists": True,
            "readable": True,
            "valid": True,
            "providers_count": 3,
            "action": "unmonitor",
            "dry_run": True,
            "errors": []
        }
        
        result = self.runner.invoke(cli, ["config", "info"])
        
        assert result.exit_code == 0
        assert "Configuration Information" in result.output
        assert "/path/to/config.yml" in result.output
        assert "unmonitor" in result.output

    @patch('excludarr.cli.ConfigManager')
    def test_config_info_with_errors(self, mock_config_manager):
        """Test config info command with configuration errors."""
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_manager.get_config_info.return_value = {
            "config_path": "/path/to/config.yml",
            "exists": True,
            "readable": False,
            "valid": False,
            "errors": ["Permission denied", "Invalid YAML syntax"]
        }
        
        result = self.runner.invoke(cli, ["config", "info"])
        
        assert result.exit_code == 0
        assert "Configuration Errors:" in result.output
        assert "Permission denied" in result.output
        assert "Invalid YAML syntax" in result.output


class TestProviderCommands:
    """Test provider management commands."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch('excludarr.cli.ProviderManager')
    def test_providers_list_all(self, mock_provider_manager):
        """Test listing all providers."""
        mock_manager = Mock()
        mock_provider_manager.return_value = mock_manager
        mock_manager.get_all_providers.return_value = {
            "netflix": {"display_name": "Netflix", "countries": ["US", "DE", "UK"]},
            "amazon-prime": {"display_name": "Amazon Prime Video", "countries": ["US", "DE"]}
        }
        
        result = self.runner.invoke(cli, ["providers", "list"])
        
        assert result.exit_code == 0
        assert "All Streaming Providers" in result.output
        assert "Netflix" in result.output
        assert "Amazon Prime Video" in result.output

    @patch('excludarr.cli.ProviderManager')
    def test_providers_list_popular(self, mock_provider_manager):
        """Test listing popular providers."""
        mock_manager = Mock()
        mock_provider_manager.return_value = mock_manager
        mock_manager.get_popular_providers.return_value = [
            {"name": "netflix", "display_name": "Netflix", "country_count": 190},
            {"name": "amazon-prime", "display_name": "Amazon Prime Video", "country_count": 150}
        ]
        
        result = self.runner.invoke(cli, ["providers", "list", "--popular"])
        
        assert result.exit_code == 0
        assert "Most Popular Streaming Providers" in result.output
        assert "Netflix" in result.output
        mock_manager.get_popular_providers.assert_called_once_with(limit=15)

    @patch('excludarr.cli.ProviderManager')
    def test_providers_list_by_country(self, mock_provider_manager):
        """Test listing providers by country."""
        mock_manager = Mock()
        mock_provider_manager.return_value = mock_manager
        mock_manager.get_providers_by_country.return_value = ["netflix", "amazon-prime"]
        mock_manager.get_provider_info.side_effect = [
            {"display_name": "Netflix"},
            {"display_name": "Amazon Prime Video"}
        ]
        
        result = self.runner.invoke(cli, ["providers", "list", "--country", "US"])
        
        assert result.exit_code == 0
        assert "Providers Available in US" in result.output
        assert "Netflix" in result.output
        mock_manager.get_providers_by_country.assert_called_once_with("US")

    @patch('excludarr.cli.ProviderManager')
    def test_providers_list_search(self, mock_provider_manager):
        """Test searching providers."""
        mock_manager = Mock()
        mock_provider_manager.return_value = mock_manager
        mock_manager.search_providers.return_value = ["netflix", "netflix-kids"]
        mock_manager.get_provider_info.side_effect = [
            {"display_name": "Netflix", "countries": ["US", "DE"]},
            {"display_name": "Netflix Kids", "countries": ["US"]}
        ]
        
        result = self.runner.invoke(cli, ["providers", "list", "--search", "netflix"])
        
        assert result.exit_code == 0
        assert "Search Results: 'netflix'" in result.output
        assert "Netflix" in result.output
        mock_manager.search_providers.assert_called_once_with("netflix")

    @patch('excludarr.cli.ProviderManager')
    def test_providers_info(self, mock_provider_manager):
        """Test provider info command."""
        mock_manager = Mock()
        mock_provider_manager.return_value = mock_manager
        mock_manager.get_provider_info.return_value = {
            "name": "netflix",
            "display_name": "Netflix",
            "countries": ["US", "DE", "UK", "CA", "AU"]
        }
        
        result = self.runner.invoke(cli, ["providers", "info", "netflix"])
        
        assert result.exit_code == 0
        assert "Provider Information: Netflix" in result.output
        assert "Available Countries" in result.output
        mock_manager.get_provider_info.assert_called_once_with("netflix")

    @patch('excludarr.cli.ProviderManager')
    def test_providers_stats(self, mock_provider_manager):
        """Test provider statistics command."""
        mock_manager = Mock()
        mock_provider_manager.return_value = mock_manager
        mock_manager.get_provider_stats.return_value = {
            "total_providers": 500,
            "total_countries": 180,
            "providers_by_country": {"US": 50, "DE": 30, "UK": 40}
        }
        
        result = self.runner.invoke(cli, ["providers", "stats"])
        
        assert result.exit_code == 0
        assert "Provider Statistics" in result.output
        assert "500" in result.output  # total providers
        assert "Top Countries by" in result.output  # Handle line wrapping
        assert "Provider Count" in result.output

    @patch('excludarr.cli.ProviderManager')
    def test_providers_validate(self, mock_provider_manager):
        """Test provider validation command."""
        mock_manager = Mock()
        mock_provider_manager.return_value = mock_manager
        mock_manager.validate_provider.return_value = (True, None)
        mock_manager.get_provider_info.return_value = {"display_name": "Netflix"}
        
        result = self.runner.invoke(cli, ["providers", "validate", "netflix", "US"])
        
        assert result.exit_code == 0
        assert "✓ Valid: Netflix is available in US" in result.output
        mock_manager.validate_provider.assert_called_once_with("netflix", "US")

    @patch('excludarr.cli.ProviderManager')
    def test_providers_validate_invalid(self, mock_provider_manager):
        """Test provider validation with invalid combination."""
        mock_manager = Mock()
        mock_provider_manager.return_value = mock_manager
        mock_manager.validate_provider.return_value = (False, "Provider not available in country")
        
        result = self.runner.invoke(cli, ["providers", "validate", "netflix", "XX"])
        
        assert result.exit_code == 0
        assert "✗ Invalid: Provider not available in country" in result.output

    @patch('excludarr.cli.ProviderManager')
    def test_providers_error_handling(self, mock_provider_manager):
        """Test provider command error handling."""
        mock_provider_manager.side_effect = ProviderError("Provider API error")
        
        result = self.runner.invoke(cli, ["providers", "list"])
        
        assert result.exit_code == 0
        assert "Provider error: Provider API error" in result.output


class TestSyncCommand:
    """Test sync command functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        
        # Create a temporary config file for testing
        self.test_config = {
            "sonarr": {
                "url": "http://localhost:8989",
                "api_key": "test_api_key_12345678901234567890123456789012"
            },
            "provider_apis": {
                "tmdb": {
                    "api_key": "test_tmdb_key",
                    "enabled": True
                }
            },
            "streaming_providers": [
                {"name": "netflix", "country": "US"}
            ],
            "sync": {
                "action": "unmonitor",
                "dry_run": True,
                "exclude_recent_days": 7
            }
        }

    def create_temp_config(self):
        """Create a temporary config file."""
        import tempfile
        import yaml
        
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False)
        yaml.dump(self.test_config, temp_file)
        temp_file.close()
        return temp_file.name

    @patch('excludarr.cli.ConfigManager')
    @patch('excludarr.cli.SyncEngine')
    @patch('excludarr.cli.asyncio.run')
    def test_sync_dry_run_success(self, mock_asyncio_run, mock_sync_engine, mock_config_manager):
        """Test successful dry run sync."""
        # Mock configuration
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.sonarr.url = "http://localhost:8989"
        mock_config.sync.action = "unmonitor"
        mock_config.sync.dry_run = True
        mock_config.sync.exclude_recent_days = 7
        mock_provider = Mock()
        mock_provider.name = "netflix"
        mock_provider.country = "US"
        mock_config.streaming_providers = [mock_provider]
        mock_manager.load_config.return_value = mock_config
        
        # Mock sync engine
        mock_engine = Mock()
        mock_sync_engine.return_value = mock_engine
        mock_engine.test_connectivity.return_value = {
            "sonarr": {"connected": True},
            "provider_manager": {"initialized": True},
            "cache": {"initialized": True}
        }
        
        # Mock sync results
        mock_result = Mock()
        mock_result.series_title = "Test Series"
        mock_result.action_taken = "unmonitor"
        mock_result.success = True
        mock_result.provider = "netflix"
        mock_result.message = "Would unmonitor series 'Test Series' (Available on netflix)"
        mock_asyncio_run.return_value = [mock_result]
        
        # Mock summary
        mock_engine._get_sync_summary.return_value = {
            "total_processed": 1,
            "successful": 1,
            "failed": 0,
            "actions": {"unmonitor": 1},
            "providers": {"netflix": 1}
        }
        
        result = self.runner.invoke(cli, ["sync", "--dry-run"])
        
        assert result.exit_code == 0
        assert "Sync Configuration:" in result.output
        assert "✓ All connectivity checks passed" in result.output
        assert "✓ Sync completed!" in result.output

    @patch('excludarr.cli.ConfigManager')
    def test_sync_config_not_found(self, mock_config_manager):
        """Test sync with configuration file not found."""
        mock_config_manager.side_effect = FileNotFoundError("Config not found")
        
        result = self.runner.invoke(cli, ["sync"])
        
        assert result.exit_code == 1
        assert "Configuration file not found" in result.output
        assert "Run 'excludarr config init'" in result.output

    @patch('excludarr.cli.ConfigManager')
    @patch('excludarr.cli.SyncEngine')
    def test_sync_sonarr_connection_failed(self, mock_sync_engine, mock_config_manager):
        """Test sync when Sonarr connection fails."""
        # Mock configuration
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.sonarr.url = "http://localhost:8989"
        mock_config.sync.action = "unmonitor"
        mock_config.sync.dry_run = True
        mock_config.sync.exclude_recent_days = 7
        mock_config.streaming_providers = []
        mock_manager.load_config.return_value = mock_config
        
        # Mock sync engine with failed connectivity
        mock_engine = Mock()
        mock_sync_engine.return_value = mock_engine
        mock_engine.test_connectivity.return_value = {
            "sonarr": {"connected": False, "error": "Connection refused"},
            "provider_manager": {"initialized": True},
            "cache": {"initialized": True}
        }
        
        result = self.runner.invoke(cli, ["sync"])
        
        assert result.exit_code == 1
        assert "✗ Sonarr connection failed: Connection refused" in result.output

    @patch('excludarr.cli.ConfigManager')
    @patch('excludarr.cli.SyncEngine')
    @patch('excludarr.cli.click.confirm')
    @patch('excludarr.cli.asyncio.run')
    def test_sync_with_confirmation(self, mock_asyncio_run, mock_confirm, mock_sync_engine, mock_config_manager):
        """Test sync with user confirmation."""
        # Mock configuration for non-dry-run
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.sync.dry_run = False
        mock_config.sync.action = "unmonitor"
        mock_config.streaming_providers = []
        mock_manager.load_config.return_value = mock_config
        
        # Mock sync engine
        mock_engine = Mock()
        mock_sync_engine.return_value = mock_engine
        mock_engine.test_connectivity.return_value = {
            "sonarr": {"connected": True},
            "provider_manager": {"initialized": True},
            "cache": {"initialized": True}
        }
        
        # User confirms
        mock_confirm.return_value = True
        mock_asyncio_run.return_value = []
        mock_engine._get_sync_summary.return_value = {"total_processed": 0, "successful": 0, "failed": 0, "actions": {}, "providers": {}}
        
        result = self.runner.invoke(cli, ["sync"])
        
        assert result.exit_code == 0
        mock_confirm.assert_called_once()

    @patch('excludarr.cli.ConfigManager')
    @patch('excludarr.cli.SyncEngine')
    @patch('excludarr.cli.click.confirm')
    def test_sync_user_cancels(self, mock_confirm, mock_sync_engine, mock_config_manager):
        """Test sync when user cancels confirmation."""
        # Mock configuration for non-dry-run
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.sync.dry_run = False
        mock_config.sync.action = "delete"
        mock_config.streaming_providers = []
        mock_manager.load_config.return_value = mock_config
        
        # Mock sync engine
        mock_engine = Mock()
        mock_sync_engine.return_value = mock_engine
        mock_engine.test_connectivity.return_value = {
            "sonarr": {"connected": True},
            "provider_manager": {"initialized": True},
            "cache": {"initialized": True}
        }
        
        # User cancels
        mock_confirm.return_value = False
        
        result = self.runner.invoke(cli, ["sync"])
        
        assert result.exit_code == 0
        assert "Sync cancelled by user" in result.output

    @patch('excludarr.cli.ConfigManager')
    @patch('excludarr.cli.SyncEngine')
    @patch('excludarr.cli.asyncio.run')
    def test_sync_json_output(self, mock_asyncio_run, mock_sync_engine, mock_config_manager):
        """Test sync with JSON output."""
        # Mock configuration
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.sync.dry_run = True
        mock_config.sync.action = "unmonitor"
        mock_manager.load_config.return_value = mock_config
        
        # Mock sync engine
        mock_engine = Mock()
        mock_sync_engine.return_value = mock_engine
        mock_engine.test_connectivity.return_value = {
            "sonarr": {"connected": True},
            "provider_manager": {"initialized": True},
            "cache": {"initialized": True}
        }
        
        # Mock sync results
        mock_result = Mock()
        mock_result.series_id = 1
        mock_result.series_title = "Test Series"
        mock_result.success = True
        mock_result.action_taken = "unmonitor"
        mock_result.message = "Test message"
        mock_result.provider = "netflix"
        mock_result.error = None
        mock_asyncio_run.return_value = [mock_result]
        
        mock_engine._get_sync_summary.return_value = {
            "total_processed": 1,
            "successful": 1,
            "failed": 0,
            "actions": {"unmonitor": 1},
            "providers": {"netflix": 1}
        }
        
        result = self.runner.invoke(cli, ["sync", "--json"])
        
        assert result.exit_code == 0
        # Should contain JSON output
        import json
        try:
            output_data = json.loads(result.output)
            assert "timestamp" in output_data
            assert "dry_run" in output_data
            assert "results" in output_data
        except json.JSONDecodeError:
            pytest.fail("Output should be valid JSON")

    @patch('excludarr.cli.ConfigManager')
    @patch('excludarr.cli.SyncEngine')
    def test_sync_error_handling(self, mock_sync_engine, mock_config_manager):
        """Test sync error handling."""
        # Mock configuration
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.sonarr.url = "http://localhost:8989"
        mock_config.sync.action = "unmonitor"
        mock_config.sync.dry_run = True
        mock_config.sync.exclude_recent_days = 7
        mock_config.streaming_providers = []
        mock_manager.load_config.return_value = mock_config
        
        # Mock sync engine with error
        mock_sync_engine.side_effect = SyncError("Sync failed")
        
        result = self.runner.invoke(cli, ["sync"])
        
        assert result.exit_code == 1
        assert "Sync failed" in result.output

    @patch('excludarr.cli.ConfigManager')
    @patch('excludarr.cli.SyncEngine')
    @patch('excludarr.cli.asyncio.run')
    def test_sync_no_results(self, mock_asyncio_run, mock_sync_engine, mock_config_manager):
        """Test sync with no results."""
        # Mock configuration
        mock_manager = Mock()
        mock_config_manager.return_value = mock_manager
        mock_config = Mock()
        mock_config.sonarr.url = "http://localhost:8989"
        mock_config.sync.dry_run = True
        mock_config.sync.action = "unmonitor"
        mock_config.sync.exclude_recent_days = 7
        mock_config.streaming_providers = []
        mock_manager.load_config.return_value = mock_config
        
        # Mock sync engine
        mock_engine = Mock()
        mock_sync_engine.return_value = mock_engine
        mock_engine.test_connectivity.return_value = {
            "sonarr": {"connected": True},
            "provider_manager": {"initialized": True},
            "cache": {"initialized": True}
        }
        
        # No results
        mock_asyncio_run.return_value = []
        
        result = self.runner.invoke(cli, ["sync"])
        
        assert result.exit_code == 0
        assert "No series processed during sync" in result.output

    def test_sync_command_options(self):
        """Test sync command options parsing."""
        # Test that the command accepts all expected options
        result = self.runner.invoke(cli, ["sync", "--help"])
        
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--action" in result.output
        assert "--confirm" in result.output
        assert "--json" in result.output