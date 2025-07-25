"""Configuration management for excludarr."""

from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

import yaml
from loguru import logger
from pydantic import ValidationError

from excludarr.models import Config


class ConfigManager:
    """Manages configuration file loading and validation."""
    
    def __init__(self, config_path: str):
        """Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = Path(config_path)
    
    def load_config(self) -> Config:
        """Load and validate configuration from file.
        
        Returns:
            Validated configuration object
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML is malformed
            ValidationError: If configuration is invalid
        """
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Run 'excludarr config init' to create an example configuration."
            )
        
        logger.debug(f"Loading configuration from {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in configuration file: {e}")
            raise
        
        if not config_data:
            raise ValidationError.from_exception_data(
                "Config",
                [{"type": "missing", "loc": (), "msg": "Configuration file is empty"}]
            )
        
        try:
            config = Config(**config_data)
            logger.info(f"Configuration loaded successfully from {self.config_path}")
            return config
        except ValidationError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise
    
    def validate_config(self) -> Tuple[bool, Optional[List[str]]]:
        """Validate configuration file without loading.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        try:
            self.load_config()
            return True, None
        except (FileNotFoundError, yaml.YAMLError, ValidationError) as e:
            error_messages = []
            
            if isinstance(e, ValidationError):
                for error in e.errors():
                    field = " -> ".join(str(loc) for loc in error['loc'])
                    message = error['msg']
                    error_messages.append(f"{field}: {message}")
            else:
                error_messages.append(str(e))
            
            return False, error_messages
    
    def create_example_config(self) -> None:
        """Create an example configuration file.
        
        Raises:
            FileExistsError: If config file already exists
        """
        if self.config_path.exists():
            raise FileExistsError(
                f"Configuration file already exists: {self.config_path}\n"
                f"Remove it first or use a different path."
            )
        
        example_config = {
            "sonarr": {
                "url": "http://localhost:8989",
                "api_key": "abcdefghijklmnopqrstuvwxyz123456"
            },
            "jellyseerr": {
                "url": "http://localhost:5055",
                "api_key": "your-jellyseerr-api-key-here",
                "timeout": 30,
                "cache_ttl": 300
            },
            "streaming_providers": [
                {
                    "name": "netflix",
                    "country": "US"
                },
                {
                    "name": "amazon-prime", 
                    "country": "US"
                },
                {
                    "name": "hulu",
                    "country": "US"
                }
            ],
            "sync": {
                "action": "unmonitor",
                "dry_run": True,
                "exclude_recent_days": 7
            }
        }
        
        # Create directory if it doesn't exist
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            f.write(self._get_config_template())
            yaml.dump(example_config, f, default_flow_style=False, indent=2)
        
        logger.info(f"Example configuration created at {self.config_path}")
    
    def _get_config_template(self) -> str:
        """Get configuration file header with documentation."""
        return """# Excludarr Configuration File
#
# This file configures excludarr to sync your Sonarr instance with
# streaming services you subscribe to.

# Sonarr connection settings
# Get your API key from Sonarr -> Settings -> General -> Security
# sonarr:
#   url: "http://localhost:8989"      # Your Sonarr URL
#   api_key: "your_32_character_api_key"

# Streaming providers you subscribe to
# Each provider needs a name and 2-letter country code
# Common providers: netflix, amazon-prime, hulu, disney-plus, hbo-max
# streaming_providers:
#   - name: "netflix"
#     country: "US"
#   - name: "amazon-prime"
#     country: "DE"

# Sync operation settings
# sync:
#   action: "unmonitor"           # "unmonitor" or "delete"
#   dry_run: true                 # Preview changes without applying
#   exclude_recent_days: 7        # Don't process recently added shows

# Configuration:
"""
    
    def get_config_info(self) -> Dict[str, Any]:
        """Get information about the current configuration.
        
        Returns:
            Dictionary with config file information
        """
        info = {
            "config_path": str(self.config_path),
            "exists": self.config_path.exists(),
            "readable": False,
            "valid": False,
            "providers_count": 0,
            "errors": []
        }
        
        if info["exists"]:
            info["readable"] = self.config_path.is_file()
            
            if info["readable"]:
                is_valid, errors = self.validate_config()
                info["valid"] = is_valid
                
                if errors:
                    info["errors"] = errors
                
                if is_valid:
                    try:
                        config = self.load_config()
                        info["providers_count"] = len(config.streaming_providers)
                        info["action"] = config.sync.action
                        info["dry_run"] = config.sync.dry_run
                    except Exception:
                        pass
        
        return info