"""Pydantic models for configuration validation."""

from typing import List, Literal, Optional

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


class TMDBConfig(BaseModel):
    """TMDB API configuration."""
    
    api_key: str = Field(
        ...,
        min_length=1,
        description="TMDB API key from themoviedb.org"
    )
    enabled: bool = Field(
        default=True,
        description="Enable TMDB provider"
    )
    rate_limit: int = Field(
        default=40,
        ge=1,
        le=100,
        description="Rate limit: requests per 10 seconds"
    )
    cache_ttl: int = Field(
        default=86400,
        ge=3600,
        le=604800,
        description="Cache TTL in seconds (1 hour to 1 week)"
    )


class StreamingAvailabilityConfig(BaseModel):
    """Streaming Availability API configuration."""
    
    rapidapi_key: Optional[str] = Field(
        default=None,
        description="RapidAPI key for Streaming Availability API"
    )
    enabled: bool = Field(
        default=False,
        description="Enable Streaming Availability API as fallback"
    )
    daily_quota: int = Field(
        default=100,
        ge=1,
        description="Daily request quota for free tier"
    )
    cache_ttl: int = Field(
        default=43200,
        ge=3600,
        le=86400,
        description="Cache TTL in seconds (1-24 hours)"
    )


class UtellyConfig(BaseModel):
    """Utelly API configuration."""
    
    rapidapi_key: Optional[str] = Field(
        default=None,
        description="RapidAPI key for Utelly API"
    )
    enabled: bool = Field(
        default=False,
        description="Enable Utelly API for price data"
    )
    monthly_quota: int = Field(
        default=1000,
        ge=1,
        description="Monthly request quota for free tier"
    )
    cache_ttl: int = Field(
        default=604800,
        ge=86400,
        le=2592000,
        description="Cache TTL in seconds (1-30 days)"
    )


class ProviderAPIsConfig(BaseModel):
    """Provider APIs configuration."""
    
    tmdb: TMDBConfig = Field(
        ...,
        description="TMDB configuration (primary provider)"
    )
    streaming_availability: StreamingAvailabilityConfig = Field(
        default_factory=StreamingAvailabilityConfig,
        description="Streaming Availability API configuration (fallback)"
    )
    utelly: UtellyConfig = Field(
        default_factory=UtellyConfig,
        description="Utelly API configuration (price data)"
    )



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
    provider_apis: ProviderAPIsConfig = Field(
        ...,
        description="Provider APIs configuration"
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