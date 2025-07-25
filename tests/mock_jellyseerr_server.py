#!/usr/bin/env python3
"""Mock Jellyseerr server for testing purposes."""

import json
import time
from typing import Dict, Any, Optional
from unittest.mock import Mock
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import socketserver


class MockJellyseerrHandler(BaseHTTPRequestHandler):
    """HTTP request handler for mock Jellyseerr server."""
    
    # Class-level storage for mock data
    mock_data = {
        "auth_user": {
            "id": 1,
            "displayName": "Test User",
            "email": "test@example.com"
        },
        "series": {
            81189: {  # Breaking Bad
                "name": "Breaking Bad",
                "externalIds": {"tvdbId": 81189, "imdbId": "tt0903747"},
                "watchProviders": [
                    {
                        "iso_3166_1": "US",
                        "flatrate": [
                            {"provider_id": 8, "provider_name": "Netflix"}
                        ]
                    },
                    {
                        "iso_3166_1": "DE",
                        "flatrate": [
                            {"provider_id": 119, "provider_name": "Amazon Prime Video"}
                        ]
                    }
                ]
            },
            73244: {  # The Office - returns HTTP 500 to simulate API issues
                "error": "HTTP 500 Internal Server Error"
            },
            79168: {  # Friends
                "name": "Friends",
                "externalIds": {"tvdbId": 79168, "imdbId": "tt0108778"},
                "watchProviders": [
                    {
                        "iso_3166_1": "US",
                        "flatrate": [
                            {"provider_id": 8, "provider_name": "Netflix"},
                            {"provider_id": 15, "provider_name": "Hulu"}
                        ]
                    },
                    {
                        "iso_3166_1": "UK",
                        "flatrate": [
                            {"provider_id": 8, "provider_name": "Netflix"}
                        ]
                    }
                ]
            },
            305288: {  # Stranger Things - simulates timeout
                "timeout": True
            },
            121361: {  # Game of Thrones
                "name": "Game of Thrones",
                "externalIds": {"tvdbId": 121361, "imdbId": "tt0944947"},
                "watchProviders": [
                    {
                        "iso_3166_1": "US",
                        "flatrate": [
                            {"provider_id": 384, "provider_name": "HBO Max"}
                        ]
                    },
                    {
                        "iso_3166_1": "DE",
                        "flatrate": [
                            {"provider_id": 300, "provider_name": "Sky Deutschland"}
                        ]
                    }
                ]
            }
        },
        "imdb_series": {
            "tt0903747": 81189,  # Breaking Bad
            "tt0108778": 79168,  # Friends
            "tt4574334": 305288, # Stranger Things
            "tt0944947": 121361  # Game of Thrones
        }
    }
    
    def do_GET(self):
        """Handle GET requests."""
        path = urlparse(self.path).path
        query_params = parse_qs(urlparse(self.path).query)
        
        if path == "/api/v1/auth/me":
            self._handle_auth()
        elif path.startswith("/api/v1/tv/"):
            tvdb_id = int(path.split("/")[-1])
            self._handle_series_lookup(tvdb_id)
        elif path == "/api/v1/search":
            query = query_params.get("query", [""])[0]
            self._handle_search(query)
        else:
            self._send_error(404, "Not Found")
    
    def _handle_auth(self):
        """Handle authentication endpoint."""
        api_key = self.headers.get("X-Api-Key")
        if not api_key:
            self._send_error(401, "Unauthorized")
            return
        
        if api_key == "invalid_key":
            self._send_error(403, "Forbidden")
            return
        
        self._send_json_response(200, self.mock_data["auth_user"])
    
    def _handle_series_lookup(self, tvdb_id: int):
        """Handle series lookup by TVDB ID."""
        if tvdb_id not in self.mock_data["series"]:
            self._send_error(404, "Series not found")
            return
        
        series_data = self.mock_data["series"][tvdb_id]
        
        # Simulate server error
        if "error" in series_data:
            self._send_error(500, "Internal Server Error")
            return
        
        # Simulate timeout
        if series_data.get("timeout"):
            time.sleep(35)  # Longer than typical timeout
            self._send_error(408, "Request Timeout")
            return
        
        self._send_json_response(200, series_data)
    
    def _handle_search(self, query: str):
        """Handle search endpoint."""
        results = []
        
        # Search by IMDB ID
        if query.startswith("tt"):
            if query in self.mock_data["imdb_series"]:
                tvdb_id = self.mock_data["imdb_series"][query]
                if tvdb_id in self.mock_data["series"]:
                    series_data = self.mock_data["series"][tvdb_id]
                    if "error" not in series_data and not series_data.get("timeout"):
                        results.append({
                            "media_type": "tv",
                            "external_ids": {
                                "tvdb_id": tvdb_id,
                                "imdb_id": query
                            },
                            "name": series_data["name"]
                        })
        
        self._send_json_response(200, {"results": results})
    
    def _send_json_response(self, status_code: int, data: Dict[str, Any]):
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def _send_error(self, status_code: int, message: str):
        """Send error response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        error_data = {"error": message, "status": status_code}
        self.wfile.write(json.dumps(error_data).encode())
    
    def log_message(self, format, *args):
        """Override to suppress request logging."""
        pass  # Suppress logs


class MockJellyseerrServer:
    """Mock Jellyseerr server for testing."""
    
    def __init__(self, host: str = "localhost", port: int = 0):
        """Initialize mock server.
        
        Args:
            host: Server host
            port: Server port (0 for random available port)
        """
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
        self._started = False
    
    def start(self):
        """Start the mock server."""
        if self._started:
            return
        
        self.server = HTTPServer((self.host, self.port), MockJellyseerrHandler)
        if self.port == 0:
            self.port = self.server.server_port
        
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self._started = True
        
        print(f"Mock Jellyseerr server started at http://{self.host}:{self.port}")
    
    def stop(self):
        """Stop the mock server."""
        if self.server and self._started:
            self.server.shutdown()
            self.server.server_close()
            if self.thread:
                self.thread.join(timeout=1)
            self._started = False
            print("Mock Jellyseerr server stopped")
    
    @property
    def base_url(self) -> str:
        """Get the base URL of the server."""
        return f"http://{self.host}:{self.port}"
    
    def add_series(self, tvdb_id: int, series_data: Dict[str, Any]):
        """Add series data to mock server.
        
        Args:
            tvdb_id: TVDB ID of the series
            series_data: Series data dictionary
        """
        MockJellyseerrHandler.mock_data["series"][tvdb_id] = series_data
    
    def add_imdb_mapping(self, imdb_id: str, tvdb_id: int):
        """Add IMDB to TVDB mapping.
        
        Args:
            imdb_id: IMDB ID
            tvdb_id: TVDB ID
        """
        MockJellyseerrHandler.mock_data["imdb_series"][imdb_id] = tvdb_id
    
    def clear_data(self):
        """Clear all mock data."""
        MockJellyseerrHandler.mock_data["series"].clear()
        MockJellyseerrHandler.mock_data["imdb_series"].clear()
    
    def reset_to_defaults(self):
        """Reset mock data to default values."""
        MockJellyseerrHandler.mock_data = {
            "auth_user": {
                "id": 1,
                "displayName": "Test User",
                "email": "test@example.com"
            },
            "series": {
                81189: {  # Breaking Bad
                    "name": "Breaking Bad",
                    "externalIds": {"tvdbId": 81189, "imdbId": "tt0903747"},
                    "watchProviders": [
                        {
                            "iso_3166_1": "US",
                            "flatrate": [
                                {"provider_id": 8, "provider_name": "Netflix"}
                            ]
                        },
                        {
                            "iso_3166_1": "DE",
                            "flatrate": [
                                {"provider_id": 119, "provider_name": "Amazon Prime Video"}
                            ]
                        }
                    ]
                },
                73244: {  # The Office - returns HTTP 500
                    "error": "HTTP 500 Internal Server Error"
                },
                79168: {  # Friends
                    "name": "Friends",
                    "externalIds": {"tvdbId": 79168, "imdbId": "tt0108778"},
                    "watchProviders": [
                        {
                            "iso_3166_1": "US",
                            "flatrate": [
                                {"provider_id": 8, "provider_name": "Netflix"},
                                {"provider_id": 15, "provider_name": "Hulu"}
                            ]
                        }
                    ]
                },
                305288: {  # Stranger Things - timeout
                    "timeout": True
                },
                121361: {  # Game of Thrones
                    "name": "Game of Thrones",
                    "externalIds": {"tvdbId": 121361, "imdbId": "tt0944947"},
                    "watchProviders": [
                        {
                            "iso_3166_1": "US",
                            "flatrate": [
                                {"provider_id": 384, "provider_name": "HBO Max"}
                            ]
                        }
                    ]
                }
            },
            "imdb_series": {
                "tt0903747": 81189,  # Breaking Bad
                "tt0108778": 79168,  # Friends
                "tt4574334": 305288, # Stranger Things
                "tt0944947": 121361  # Game of Thrones
            }
        }
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


def create_test_server(port: int = 0) -> MockJellyseerrServer:
    """Create a test server instance.
    
    Args:
        port: Port to bind to (0 for random)
        
    Returns:
        MockJellyseerrServer instance
    """
    return MockJellyseerrServer(port=port)


if __name__ == "__main__":
    # Run standalone for manual testing
    import sys
    
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5055
    
    server = MockJellyseerrServer(port=port)
    try:
        server.start()
        print(f"Mock Jellyseerr server running at {server.base_url}")
        print("Press Ctrl+C to stop")
        
        # Keep server running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.stop()