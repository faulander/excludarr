"""Pydantic models for configuration validation."""

from typing import List, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class SonarrConfig(BaseModel):
    """Sonarr connection configuration."""
    
    url: HttpUrl = Field(
        ...,
        description="Sonarr instance URL (e.g., http://localhost:8989)"
    )
    api_key: str = Field(
        ...,
        min_length=32,
        max_length=32,
        description="Sonarr API key (32 characters)"
    )
    
    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate API key format."""
        if not v.isalnum():
            raise ValueError('API key must contain only alphanumeric characters')
        return v


class StreamingProvider(BaseModel):
    """Streaming service provider configuration."""
    
    name: str = Field(
        ...,
        description="Provider name (e.g., netflix, amazon-prime, hulu)"
    )
    country: str = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Two-letter country code (e.g., US, DE, UK)"
    )
    
    @field_validator('country')
    @classmethod
    def validate_country_code(cls, v: str) -> str:
        """Validate country code format."""
        return v.upper()
    
    @field_validator('name')
    @classmethod
    def validate_provider_name(cls, v: str) -> str:
        """Validate and normalize provider name."""
        return v.lower().strip()


class SyncConfig(BaseModel):
    """Sync operation configuration."""
    
    action: Literal["unmonitor", "delete"] = Field(
        default="unmonitor",
        description="Action to take: 'unmonitor' or 'delete'"
    )
    dry_run: bool = Field(
        default=True,
        description="Preview changes without applying them"
    )
    exclude_recent_days: int = Field(
        default=7,
        ge=0,
        description="Don't process shows added within this many days"
    )


class Config(BaseModel):
    """Main configuration model."""
    
    sonarr: SonarrConfig = Field(
        ...,
        description="Sonarr connection settings"
    )
    streaming_providers: List[StreamingProvider] = Field(
        ...,
        min_length=1,
        description="List of subscribed streaming providers"
    )
    sync: SyncConfig = Field(
        default_factory=SyncConfig,
        description="Sync operation settings"
    )
    
    @field_validator('streaming_providers')
    @classmethod
    def validate_unique_providers(cls, v: List[StreamingProvider]) -> List[StreamingProvider]:
        """Ensure provider/country combinations are unique."""
        seen = set()
        for provider in v:
            key = (provider.name, provider.country)
            if key in seen:
                raise ValueError(f'Duplicate provider: {provider.name} ({provider.country})')
            seen.add(key)
        return v
    
    model_config = {
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "extra": "forbid"
    }