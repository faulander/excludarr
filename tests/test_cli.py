"""Tests for the CLI interface."""

import pytest
from click.testing import CliRunner

from excludarr import __version__
from excludarr.cli import cli


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