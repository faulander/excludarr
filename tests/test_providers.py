"""Tests for streaming provider management."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from excludarr.providers import ProviderManager, ProviderError


class TestProviderManager:
    """Test provider management functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = ProviderManager()

    def test_load_providers_data(self):
        """Test loading provider data from file."""
        providers = self.manager.get_all_providers()
        assert isinstance(providers, dict)
        assert len(providers) > 0
        
        # Check that major providers exist
        assert "netflix" in providers
        assert "amazon-prime" in providers
        assert "disney-plus" in providers

    def test_get_provider_info(self):
        """Test getting specific provider information."""
        netflix_info = self.manager.get_provider_info("netflix")
        assert netflix_info is not None
        assert netflix_info["name"] == "netflix"
        assert "countries" in netflix_info
        assert "US" in netflix_info["countries"]

    def test_get_provider_info_not_found(self):
        """Test getting non-existent provider."""
        with pytest.raises(ProviderError, match="Provider 'nonexistent' not found"):
            self.manager.get_provider_info("nonexistent")

    def test_get_providers_by_country(self):
        """Test filtering providers by country."""
        us_providers = self.manager.get_providers_by_country("US")
        assert isinstance(us_providers, list)
        assert len(us_providers) > 0
        
        # Check that all returned providers support US
        for provider_name in us_providers:
            provider_info = self.manager.get_provider_info(provider_name)
            assert "US" in provider_info["countries"]

    def test_get_providers_by_invalid_country(self):
        """Test filtering by invalid country code."""
        providers = self.manager.get_providers_by_country("XX")
        assert providers == []

    def test_validate_provider_valid(self):
        """Test validating valid provider configuration."""
        is_valid, error = self.manager.validate_provider("netflix", "US")
        assert is_valid is True
        assert error is None

    def test_validate_provider_invalid_name(self):
        """Test validating invalid provider name."""
        is_valid, error = self.manager.validate_provider("invalid-provider", "US")
        assert is_valid is False
        assert "not found in provider list" in error

    def test_validate_provider_invalid_country(self):
        """Test validating invalid country for provider."""
        is_valid, error = self.manager.validate_provider("netflix", "XX")
        assert is_valid is False
        assert "not available in country XX" in error

    def test_get_supported_countries(self):
        """Test getting all supported countries."""
        countries = self.manager.get_supported_countries()
        assert isinstance(countries, set)
        assert len(countries) > 0
        assert "US" in countries
        assert "DE" in countries
        assert "GB" in countries

    def test_get_provider_countries(self):
        """Test getting countries for specific provider."""
        netflix_countries = self.manager.get_provider_countries("netflix")
        assert isinstance(netflix_countries, list)
        assert len(netflix_countries) > 0
        assert "US" in netflix_countries

    def test_get_provider_countries_invalid(self):
        """Test getting countries for invalid provider."""
        with pytest.raises(ProviderError):
            self.manager.get_provider_countries("invalid-provider")

    def test_search_providers(self):
        """Test searching providers by name."""
        results = self.manager.search_providers("net")
        assert isinstance(results, list)
        assert len(results) > 0
        
        # Should find netflix
        netflix_found = any("netflix" in result for result in results)
        assert netflix_found

    def test_search_providers_no_results(self):
        """Test searching with no results."""
        results = self.manager.search_providers("nonexistent")
        assert results == []

    def test_get_provider_display_name(self):
        """Test getting provider display name."""
        display_name = self.manager.get_provider_display_name("netflix")
        assert display_name == "Netflix"
        
        display_name = self.manager.get_provider_display_name("amazon-prime")
        assert display_name == "Amazon Prime Video"

    def test_provider_normalization(self):
        """Test provider name normalization."""
        # Test case insensitive lookup
        netflix_info = self.manager.get_provider_info("NETFLIX")
        assert netflix_info["name"] == "netflix"
        
        netflix_info = self.manager.get_provider_info("Netflix")
        assert netflix_info["name"] == "netflix"

    def test_validate_multiple_providers(self):
        """Test validating multiple provider configurations."""
        providers = [
            {"name": "netflix", "country": "US"},
            {"name": "amazon-prime", "country": "DE"},
            {"name": "disney-plus", "country": "GB"}
        ]
        
        results = self.manager.validate_multiple_providers(providers)
        assert len(results) == 3
        
        for result in results:
            assert result["valid"] is True
            assert result["error"] is None

    def test_validate_multiple_providers_with_errors(self):
        """Test validating multiple providers with some invalid."""
        providers = [
            {"name": "netflix", "country": "US"},
            {"name": "invalid-provider", "country": "US"},
            {"name": "netflix", "country": "XX"}
        ]
        
        results = self.manager.validate_multiple_providers(providers)
        assert len(results) == 3
        
        # First should be valid
        assert results[0]["valid"] is True
        
        # Second should be invalid (bad provider)
        assert results[1]["valid"] is False
        assert "not found" in results[1]["error"]
        
        # Third should be invalid (bad country)
        assert results[2]["valid"] is False
        assert "not available" in results[2]["error"]

    def test_get_provider_stats(self):
        """Test getting provider statistics."""
        stats = self.manager.get_provider_stats()
        assert isinstance(stats, dict)
        assert "total_providers" in stats
        assert "total_countries" in stats
        assert "providers_by_country" in stats
        
        assert stats["total_providers"] > 0
        assert stats["total_countries"] > 0
        assert isinstance(stats["providers_by_country"], dict)


class TestProviderDataStructure:
    """Test provider data structure and format."""
    
    def test_provider_data_structure(self):
        """Test that provider data has correct structure."""
        manager = ProviderManager()
        providers = manager.get_all_providers()
        
        # Test that each provider has required fields
        for provider_name, provider_data in providers.items():
            assert "name" in provider_data
            assert "display_name" in provider_data
            assert "countries" in provider_data
            assert isinstance(provider_data["countries"], list)
            assert len(provider_data["countries"]) > 0
            
            # Test country codes are 2 characters
            for country in provider_data["countries"]:
                assert len(country) == 2
                assert country.isupper()

    def test_no_duplicate_providers(self):
        """Test that there are no duplicate provider entries."""
        manager = ProviderManager()
        providers = manager.get_all_providers()
        
        provider_names = list(providers.keys())
        assert len(provider_names) == len(set(provider_names))

    def test_consistent_naming(self):
        """Test consistent provider naming conventions."""
        manager = ProviderManager()
        providers = manager.get_all_providers()
        
        for provider_name in providers.keys():
            # Should be lowercase
            assert provider_name == provider_name.lower()
            
            # Should not have spaces
            assert " " not in provider_name
            
            # Should use hyphens for multi-word names
            if "-" in provider_name:
                parts = provider_name.split("-")
                for part in parts:
                    assert len(part) > 0