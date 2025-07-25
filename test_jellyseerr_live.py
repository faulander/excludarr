#!/usr/bin/env python3
"""Test script for Jellyseerr live integration."""

import sys
from typing import Optional

from excludarr.jellyseerr import JellyseerrClient, JellyseerrError
from excludarr.models import JellyseerrConfig


def test_jellyseerr_connection(url: str, api_key: str) -> bool:
    """Test Jellyseerr connection."""
    print(f"Testing connection to {url}...")
    
    try:
        config = JellyseerrConfig(url=url, api_key=api_key)
        
        with JellyseerrClient(config) as client:
            result = client.test_connection()
            if result:
                print("✅ Connection successful!")
                return True
            else:
                print("❌ Connection failed")
                return False
                
    except JellyseerrError as e:
        print(f"❌ Jellyseerr error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_series_lookup(url: str, api_key: str, tvdb_id: Optional[int] = None, imdb_id: Optional[str] = None) -> None:
    """Test series availability lookup."""
    if not tvdb_id and not imdb_id:
        # Default to Breaking Bad for testing
        tvdb_id = 81189
        imdb_id = "tt0903747"
    
    print(f"\nTesting series lookup (TVDB: {tvdb_id}, IMDB: {imdb_id})...")
    
    try:
        config = JellyseerrConfig(url=url, api_key=api_key)
        
        with JellyseerrClient(config) as client:
            availability = client.get_series_availability(tvdb_id=tvdb_id, imdb_id=imdb_id)
            
            if availability:
                print(f"✅ Found series: {availability['series_name']}")
                print(f"   TVDB ID: {availability.get('tvdb_id')}")
                print(f"   IMDB ID: {availability.get('imdb_id')}")
                print(f"   Providers found: {len(availability['providers'])}")
                
                for provider in availability['providers']:
                    print(f"   - {provider['provider_name']} ({provider['country']}) - {provider['provider_type']}")
            else:
                print("❌ Series not found in Jellyseerr")
                
    except JellyseerrError as e:
        print(f"❌ Jellyseerr error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


def main():
    """Main test function."""
    print("Jellyseerr Live Integration Test")
    print("=" * 40)
    
    # Get connection details from user
    url = input("Enter Jellyseerr URL (e.g., http://localhost:5055): ").strip()
    if not url:
        print("❌ URL is required")
        sys.exit(1)
    
    api_key = input("Enter Jellyseerr API key: ").strip()
    if not api_key:
        print("❌ API key is required")
        sys.exit(1)
    
    # Test connection
    if not test_jellyseerr_connection(url, api_key):
        print("\n❌ Connection test failed. Please check your URL and API key.")
        sys.exit(1)
    
    # Test series lookup
    print("\nTesting with Breaking Bad (default)...")
    test_series_lookup(url, api_key)
    
    # Allow custom series testing
    while True:
        custom_test = input("\nTest another series? (y/n): ").lower().strip()
        if custom_test != 'y':
            break
            
        tvdb_input = input("Enter TVDB ID (optional): ").strip()
        imdb_input = input("Enter IMDB ID (optional, e.g., tt0903747): ").strip()
        
        tvdb_id = int(tvdb_input) if tvdb_input.isdigit() else None
        imdb_id = imdb_input if imdb_input else None
        
        if not tvdb_id and not imdb_id:
            print("❌ At least one ID is required")
            continue
            
        test_series_lookup(url, api_key, tvdb_id, imdb_id)
    
    print("\n✅ Jellyseerr testing complete!")


if __name__ == "__main__":
    main()