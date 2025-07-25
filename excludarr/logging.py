"""Logging configuration for excludarr."""

import sys
from loguru import logger


def get_log_level(verbosity: int) -> str:
    """Get log level based on verbosity count.
    
    Args:
        verbosity: Number of -v flags passed
        
    Returns:
        Log level string for loguru
    """
    levels = {
        0: "WARNING",  # Default
        1: "INFO",     # -v
        2: "DEBUG",    # -vv
        3: "TRACE",    # -vvv
    }
    return levels.get(verbosity, "TRACE")


def setup_logging(verbosity: int) -> None:
    """Set up logging configuration.
    
    Args:
        verbosity: Number of -v flags passed
    """
    # Remove default handler
    logger.remove()
    
    log_level = get_log_level(verbosity)
    
    # Add new handler with appropriate level and format
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )