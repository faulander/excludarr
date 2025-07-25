#!/usr/bin/env python3
"""Extended Jellyseerr testing with multiple series."""

from excludarr.config import ConfigManager
from excludarr.jellyseerr import JellyseerrClient, JellyseerrError


def test_multiple_series():
    """Test multiple series to find one with provider data."""
    config_manager = ConfigManager("excludarr.yml")
    config = config_manager.load_config()
    
    if not config.jellyseerr:
        print("❌ Jellyseerr not configured")
        return
    
    # Test series that are commonly on streaming platforms
    test_series = [
        {"name": "Breaking Bad", "tvdb_id": 81189, "imdb_id": "tt0903747"},
        {"name": "The Office", "tvdb_id": 73244, "imdb_id": "tt0386676"},
        {"name": "Friends", "tvdb_id": 79168, "imdb_id": "tt0108778"},
        {"name": "Stranger Things", "tvdb_id": 305288, "imdb_id": "tt4574334"},
        {"name": "House of Cards", "tvdb_id": 262980, "imdb_id": "tt1856010"},
    ]
    
    print("Testing Multiple Series for Provider Data")
    print("=" * 45)
    
    with JellyseerrClient(config.jellyseerr) as client:
        for series in test_series:
            print(f"\nTesting: {series['name']}")
            print("-" * 30)
            
            try:
                availability = client.get_series_availability(tvdb_id=series["tvdb_id"])
                
                if availability:
                    print(f"✅ Found: {availability['series_name']}")
                    print(f"   Providers: {len(availability['providers'])}")
                    
                    if availability['providers']:
                        print("   Available on:")
                        for provider in availability['providers'][:5]:  # Show first 5
                            print(f"   - {provider['provider_name']} ({provider['country']}) [{provider['provider_type']}]")
                        
                        if len(availability['providers']) > 5:
                            print(f"   ... and {len(availability['providers']) - 5} more")
                            
                        # Test regional filtering
                        filtered = client._filter_providers_by_region(
                            availability['providers'], 
                            config.streaming_providers
                        )
                        if filtered:
                            print(f"   ✅ Matches your providers ({len(filtered)}):")
                            for provider in filtered:
                                print(f"      - {provider['provider_name']} ({provider['country']})")
                        else:
                            print("   ❌ No matches with your configured providers")
                    else:
                        print("   No streaming providers found")
                else:
                    print("❌ Not found in Jellyseerr")
                    
            except Exception as e:
                print(f"❌ Error: {e}")


if __name__ == "__main__":
    test_multiple_series()