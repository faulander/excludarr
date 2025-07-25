#!/usr/bin/env python3
"""Test Jellyseerr integration using existing configuration."""

import sys
from pathlib import Path

from excludarr.config import ConfigManager
from excludarr.jellyseerr import JellyseerrClient, JellyseerrError


def test_jellyseerr_from_config(config_path: str = "excludarr.yml"):
    """Test Jellyseerr using configuration file."""
    print("Testing Jellyseerr Integration from Configuration")
    print("=" * 50)
    
    # Load configuration
    try:
        config_manager = ConfigManager(config_path)
        config = config_manager.load_config()
        print(f"✅ Configuration loaded from {config_path}")
    except FileNotFoundError:
        print(f"❌ Configuration file not found: {config_path}")
        print("Run 'uv run excludarr config init' to create an example configuration")
        return False
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return False
    
    # Check if Jellyseerr is configured
    if not config.jellyseerr:
        print("❌ Jellyseerr not configured in config file")
        print("Please add a jellyseerr section to your configuration:")
        print("""
jellyseerr:
  url: "http://localhost:5055"
  api_key: "your-jellyseerr-api-key"
  timeout: 30
  cache_ttl: 300
""")
        return False
    
    print(f"✅ Jellyseerr configured: {config.jellyseerr.url}")
    
    # Test connection
    print("\nTesting Jellyseerr connection...")
    try:
        with JellyseerrClient(config.jellyseerr) as client:
            result = client.test_connection()
            if result:
                print("✅ Jellyseerr connection successful!")
            else:
                print("❌ Jellyseerr connection failed")
                return False
    except JellyseerrError as e:
        print(f"❌ Jellyseerr error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    # Test series lookup with Breaking Bad (known series)
    print("\nTesting series lookup with Breaking Bad...")
    try:
        with JellyseerrClient(config.jellyseerr) as client:
            availability = client.get_series_availability(tvdb_id=81189)
            
            if availability:
                print(f"✅ Found series: {availability['series_name']}")
                print(f"   TVDB ID: {availability.get('tvdb_id')}")
                print(f"   IMDB ID: {availability.get('imdb_id')}")
                print(f"   Providers found: {len(availability['providers'])}")
                
                # Show detailed provider information
                if availability['providers']:
                    print("\n   Provider Details:")
                    for provider in availability['providers']:
                        mapped_name = provider.get('mapped_name', 'unknown')
                        provider_type = provider.get('provider_type', 'unknown')
                        print(f"   - {provider['provider_name']} ({provider['country']}) -> {mapped_name} [{provider_type}]")
                    
                    # Test regional filtering
                    print(f"\n   Testing regional filtering with configured providers...")
                    filtered = client._filter_providers_by_region(
                        availability['providers'], 
                        config.streaming_providers
                    )
                    print(f"   Matches user's configured providers: {len(filtered)}")
                    for provider in filtered:
                        print(f"   - ✅ {provider['provider_name']} ({provider['country']})")
                else:
                    print("   No streaming providers found for this series")
            else:
                print("❌ Series not found in Jellyseerr")
                
    except JellyseerrError as e:
        print(f"❌ Series lookup error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during series lookup: {e}")
        return False
    
    print("\n✅ Jellyseerr integration test completed successfully!")
    print("\nNext steps:")
    print("1. Verify that the provider mappings look correct")
    print("2. Test with a few more series to ensure reliability")
    print("3. Check that regional filtering works with your streaming providers")
    
    return True


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "excludarr.yml"
    
    if not Path(config_path).exists():
        print(f"❌ Configuration file not found: {config_path}")
        print("\nTo create a configuration file:")
        print("  uv run excludarr config init")
        print("\nThen edit the jellyseerr section with your details.")
        sys.exit(1)
    
    success = test_jellyseerr_from_config(config_path)
    sys.exit(0 if success else 1)