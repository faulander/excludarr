"""Tests for the logging configuration."""

import pytest
from loguru import logger

from excludarr.logging import setup_logging, get_log_level


class TestLogging:
    """Test logging configuration."""

    def test_get_log_level(self):
        """Test log level determination based on verbosity."""
        assert get_log_level(0) == "WARNING"
        assert get_log_level(1) == "INFO"
        assert get_log_level(2) == "DEBUG"
        assert get_log_level(3) == "TRACE"
        assert get_log_level(10) == "TRACE"  # Max out at TRACE

    def test_setup_logging_default(self, capsys):
        """Test default logging setup."""
        # Remove any existing handlers
        logger.remove()
        
        setup_logging(0)
        logger.warning("Test warning")
        logger.info("Test info")  # Should not appear
        
        captured = capsys.readouterr()
        assert "Test warning" in captured.err
        assert "Test info" not in captured.err

    def test_setup_logging_verbose(self, capsys):
        """Test verbose logging setup."""
        # Remove any existing handlers
        logger.remove()
        
        setup_logging(1)
        logger.info("Test info")
        logger.debug("Test debug")  # Should not appear
        
        captured = capsys.readouterr()
        assert "Test info" in captured.err
        assert "Test debug" not in captured.err

    def test_setup_logging_debug(self, capsys):
        """Test debug logging setup."""
        # Remove any existing handlers
        logger.remove()
        
        setup_logging(2)
        logger.debug("Test debug")
        logger.trace("Test trace")  # Should not appear
        
        captured = capsys.readouterr()
        assert "Test debug" in captured.err
        assert "Test trace" not in captured.err

    def test_setup_logging_trace(self, capsys):
        """Test trace logging setup."""
        # Remove any existing handlers
        logger.remove()
        
        setup_logging(3)
        logger.trace("Test trace")
        
        captured = capsys.readouterr()
        assert "Test trace" in captured.err