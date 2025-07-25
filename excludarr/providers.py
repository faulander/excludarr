"""Streaming provider management for excludarr."""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

from loguru import logger


class ProviderError(Exception):
    """Exception for provider-related errors."""
    pass


class ProviderManager:
    """Manages streaming provider data and operations."""
    
    def __init__(self, providers_file: Optional[str] = None):
        """Initialize provider manager.
        
        Args:
            providers_file: Path to providers data file (optional)
        """
        if providers_file is None:
            # Use default providers file
            current_dir = Path(__file__).parent
            providers_file = current_dir / "data" / "providers.json"
        
        self.providers_file = Path(providers_file)
        self._providers_data = None
        self._load_providers()
    
    def _load_providers(self) -> None:
        """Load provider data from file."""
        try:
            if not self.providers_file.exists():
                raise ProviderError(f"Providers file not found: {self.providers_file}")
            
            with open(self.providers_file, 'r', encoding='utf-8') as f:
                self._providers_data = json.load(f)
            
            logger.debug(f"Loaded {len(self._providers_data)} providers from {self.providers_file}")
            
        except json.JSONDecodeError as e:
            raise ProviderError(f"Invalid JSON in providers file: {e}")
        except Exception as e:
            raise ProviderError(f"Failed to load providers: {e}")
    
    def get_all_providers(self) -> Dict[str, Any]:
        """Get all provider data.
        
        Returns:
            Dictionary of all providers
        """
        return self._providers_data.copy()
    
    def get_provider_info(self, provider_name: str) -> Dict[str, Any]:
        """Get information for a specific provider.
        
        Args:
            provider_name: Name of the provider
            
        Returns:
            Provider information dictionary
            
        Raises:
            ProviderError: If provider not found
        """
        normalized_name = provider_name.lower().strip()
        
        if normalized_name not in self._providers_data:
            raise ProviderError(f"Provider '{provider_name}' not found in provider list")
        
        return self._providers_data[normalized_name].copy()
    
    def get_providers_by_country(self, country_code: str) -> List[str]:
        """Get providers available in a specific country.
        
        Args:
            country_code: 2-letter country code (e.g., 'US', 'DE')
            
        Returns:
            List of provider names available in the country
        """
        country_code = country_code.upper().strip()
        available_providers = []
        
        for provider_name, provider_data in self._providers_data.items():
            if country_code in provider_data.get("countries", []):
                available_providers.append(provider_name)
        
        return sorted(available_providers)
    
    def validate_provider(self, provider_name: str, country_code: str) -> Tuple[bool, Optional[str]]:
        """Validate a provider and country combination.
        
        Args:
            provider_name: Name of the provider
            country_code: 2-letter country code
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        normalized_name = provider_name.lower().strip()
        country_code = country_code.upper().strip()
        
        # Check if provider exists
        if normalized_name not in self._providers_data:
            return False, f"Provider '{provider_name}' not found in provider list"
        
        # Check if provider is available in country
        provider_data = self._providers_data[normalized_name]
        if country_code not in provider_data.get("countries", []):
            return False, f"Provider '{provider_name}' not available in country {country_code}"
        
        return True, None
    
    def get_supported_countries(self) -> Set[str]:
        """Get set of all supported country codes.
        
        Returns:
            Set of 2-letter country codes
        """
        countries = set()
        
        for provider_data in self._providers_data.values():
            countries.update(provider_data.get("countries", []))
        
        return countries
    
    def get_provider_countries(self, provider_name: str) -> List[str]:
        """Get countries where a provider is available.
        
        Args:
            provider_name: Name of the provider
            
        Returns:
            List of 2-letter country codes
            
        Raises:
            ProviderError: If provider not found
        """
        provider_info = self.get_provider_info(provider_name)
        return sorted(provider_info.get("countries", []))
    
    def search_providers(self, search_term: str) -> List[str]:
        """Search providers by name or display name.
        
        Args:
            search_term: Term to search for
            
        Returns:
            List of matching provider names
        """
        search_term = search_term.lower().strip()
        matches = []
        
        for provider_name, provider_data in self._providers_data.items():
            # Search in provider name
            if search_term in provider_name.lower():
                matches.append(provider_name)
                continue
            
            # Search in display name
            display_name = provider_data.get("display_name", "").lower()
            if search_term in display_name:
                matches.append(provider_name)
        
        return sorted(matches)
    
    def get_provider_display_name(self, provider_name: str) -> str:
        """Get display name for a provider.
        
        Args:
            provider_name: Name of the provider
            
        Returns:
            Display name of the provider
            
        Raises:
            ProviderError: If provider not found
        """
        provider_info = self.get_provider_info(provider_name)
        return provider_info.get("display_name", provider_name.title())
    
    def validate_multiple_providers(self, providers: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Validate multiple provider configurations.
        
        Args:
            providers: List of provider dictionaries with 'name' and 'country' keys
            
        Returns:
            List of validation results with 'provider', 'valid', and 'error' keys
        """
        results = []
        
        for provider_config in providers:
            provider_name = provider_config.get("name", "")
            country_code = provider_config.get("country", "")
            
            is_valid, error = self.validate_provider(provider_name, country_code)
            
            results.append({
                "provider": provider_name,
                "country": country_code,
                "valid": is_valid,
                "error": error
            })
        
        return results
    
    def get_provider_stats(self) -> Dict[str, Any]:
        """Get statistics about providers.
        
        Returns:
            Dictionary with provider statistics
        """
        all_countries = self.get_supported_countries()
        providers_by_country = {}
        
        for country in sorted(all_countries):
            providers_by_country[country] = len(self.get_providers_by_country(country))
        
        return {
            "total_providers": len(self._providers_data),
            "total_countries": len(all_countries),
            "providers_by_country": providers_by_country
        }
    
    def get_popular_providers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most popular providers based on country availability.
        
        Args:
            limit: Maximum number of providers to return
            
        Returns:
            List of provider info dictionaries sorted by popularity
        """
        provider_popularity = []
        
        for provider_name, provider_data in self._providers_data.items():
            country_count = len(provider_data.get("countries", []))
            provider_popularity.append({
                "name": provider_name,
                "display_name": provider_data.get("display_name", provider_name.title()),
                "country_count": country_count,
                "countries": provider_data.get("countries", [])
            })
        
        # Sort by country count (popularity) descending
        provider_popularity.sort(key=lambda x: x["country_count"], reverse=True)
        
        return provider_popularity[:limit]
    
    def get_regional_providers(self, region: str) -> List[str]:
        """Get providers that are region-specific.
        
        Args:
            region: Region identifier ('US', 'EU', 'ASIA', etc.)
            
        Returns:
            List of provider names for the region
        """
        region_mappings = {
            "US": ["US"],
            "EU": [
                "GB", "IE", "DE", "AT", "CH", "FR", "BE", "NL", "LU", "IT", "ES", "PT",
                "SE", "NO", "DK", "FI", "IS", "PL", "CZ", "SK", "HU", "RO", "BG", "HR",
                "SI", "EE", "LV", "LT", "GR", "CY", "MT"
            ],
            "ASIA": [
                "JP", "KR", "TW", "HK", "SG", "MY", "TH", "PH", "ID", "VN", "IN", "CN"
            ],
            "OCEANIA": ["AU", "NZ"],
            "AMERICAS": [
                "US", "CA", "BR", "MX", "AR", "CL", "CO", "PE", "UY", "PY", "BO", "EC",
                "VE", "CR", "PA", "GT", "HN", "SV", "NI", "DO", "JM", "TT", "BB", "BS", "BZ"
            ]
        }
        
        region_countries = region_mappings.get(region.upper(), [])
        if not region_countries:
            return []
        
        regional_providers = []
        for provider_name, provider_data in self._providers_data.items():
            provider_countries = set(provider_data.get("countries", []))
            region_countries_set = set(region_countries)
            
            # Provider is regional if it's only available in this region
            if provider_countries.issubset(region_countries_set):
                regional_providers.append(provider_name)
        
        return sorted(regional_providers)
    
    def reload_providers(self) -> None:
        """Reload provider data from file."""
        self._providers_data = None
        self._load_providers()
        logger.info("Provider data reloaded")