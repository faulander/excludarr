"""Tests for Sonarr API integration."""

import pytest
import responses

from excludarr.sonarr import SonarrClient, SonarrError, SonarrConnectionError
from excludarr.models import SonarrConfig


class TestSonarrClient:
    """Test Sonarr API client."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = SonarrConfig(
            url="http://localhost:8989",
            api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        )
        self.client = SonarrClient(self.config)

    def test_client_initialization(self):
        """Test client initialization."""
        assert self.client.config == self.config
        assert str(self.client.base_url) == "http://localhost:8989/"
        assert self.client.api_key == "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"

    @responses.activate
    def test_test_connection_success(self):
        """Test successful connection test."""
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/system/status",
            json={"version": "3.0.9.1549"},
            status=200
        )
        
        result = self.client.test_connection()
        assert result is True

    @responses.activate
    def test_test_connection_invalid_api_key(self):
        """Test connection with invalid API key."""
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/system/status",
            json={"error": "Unauthorized"},
            status=401
        )
        
        with pytest.raises(SonarrConnectionError, match="Authentication failed"):
            self.client.test_connection()

    @responses.activate
    def test_test_connection_server_error(self):
        """Test connection with server error."""
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/system/status",
            json={"error": "Internal server error"},
            status=500
        )
        
        with pytest.raises(SonarrConnectionError, match="Server error"):
            self.client.test_connection()

    @responses.activate
    def test_get_series_success(self):
        """Test successful series retrieval."""
        mock_series = [
            {
                "id": 1,
                "title": "Breaking Bad",
                "monitored": True,
                "seasons": [
                    {"seasonNumber": 1, "monitored": True},
                    {"seasonNumber": 2, "monitored": True}
                ]
            },
            {
                "id": 2,
                "title": "Better Call Saul",
                "monitored": False,
                "seasons": [
                    {"seasonNumber": 1, "monitored": False}
                ]
            }
        ]
        
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/series",
            json=mock_series,
            status=200
        )
        
        series = self.client.get_series()
        assert len(series) == 2
        assert series[0]["title"] == "Breaking Bad"
        assert series[1]["title"] == "Better Call Saul"

    @responses.activate
    def test_get_series_by_id_success(self):
        """Test successful single series retrieval."""
        mock_series = {
            "id": 1,
            "title": "Breaking Bad",
            "monitored": True,
            "seasons": [
                {"seasonNumber": 1, "monitored": True},
                {"seasonNumber": 2, "monitored": True}
            ]
        }
        
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/series/1",
            json=mock_series,
            status=200
        )
        
        series = self.client.get_series_by_id(1)
        assert series["title"] == "Breaking Bad"
        assert series["monitored"] is True

    @responses.activate
    def test_get_series_by_id_not_found(self):
        """Test series not found."""
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/series/999",
            json={"error": "Series not found"},
            status=404
        )
        
        with pytest.raises(SonarrError, match="Resource not found"):
            self.client.get_series_by_id(999)

    @responses.activate
    def test_unmonitor_series_success(self):
        """Test successful series unmonitoring."""
        mock_series = {
            "id": 1,
            "title": "Breaking Bad",
            "monitored": True,
            "seasons": [
                {"seasonNumber": 1, "monitored": True},
                {"seasonNumber": 2, "monitored": True}
            ]
        }
        
        # Mock getting series data first
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/series/1",
            json=mock_series,
            status=200
        )
        
        # Mock updating series
        updated_series = mock_series.copy()
        updated_series["monitored"] = False
        updated_series["seasons"] = [
            {"seasonNumber": 1, "monitored": False},
            {"seasonNumber": 2, "monitored": False}
        ]
        
        responses.add(
            responses.PUT,
            "http://localhost:8989/api/v3/series/1",
            json=updated_series,
            status=200
        )
        
        result = self.client.unmonitor_series(1)
        assert result is True
        
        # Verify the request body
        request = responses.calls[1].request  # Second call is the PUT
        import json
        body = json.loads(request.body)
        assert body["monitored"] is False

    @responses.activate
    def test_unmonitor_season_success(self):
        """Test successful season unmonitoring."""
        mock_series = {
            "id": 1,
            "title": "Breaking Bad",
            "monitored": True,
            "seasons": [
                {"seasonNumber": 1, "monitored": True},
                {"seasonNumber": 2, "monitored": True}
            ]
        }
        
        # Mock getting series data first
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/series/1",
            json=mock_series,
            status=200
        )
        
        # Mock updating series
        updated_series = mock_series.copy()
        updated_series["seasons"] = [
            {"seasonNumber": 1, "monitored": False},
            {"seasonNumber": 2, "monitored": True}
        ]
        
        responses.add(
            responses.PUT,
            "http://localhost:8989/api/v3/series/1",
            json=updated_series,
            status=200
        )
        
        result = self.client.unmonitor_season(1, 1)
        assert result is True

    @responses.activate
    def test_delete_series_success(self):
        """Test successful series deletion."""
        # Mock getting series data first (for logging)
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/series/1",
            json={
                "id": 1,
                "title": "Test Series",
                "monitored": True
            },
            status=200
        )
        
        responses.add(
            responses.DELETE,
            "http://localhost:8989/api/v3/series/1?deleteFiles=false",
            status=200
        )
        
        result = self.client.delete_series(1, delete_files=False)
        assert result is True
        
        # Verify the DELETE request was made with correct parameters
        delete_request = responses.calls[1].request  # Second call is DELETE
        assert "deleteFiles=false" in delete_request.url

    @responses.activate
    def test_delete_series_with_files(self):
        """Test series deletion with files."""
        # Mock getting series data first (for logging)
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/series/1",
            json={
                "id": 1,
                "title": "Test Series",
                "monitored": True
            },
            status=200
        )
        
        responses.add(
            responses.DELETE,
            "http://localhost:8989/api/v3/series/1?deleteFiles=true",
            status=200
        )
        
        result = self.client.delete_series(1, delete_files=True)
        assert result is True
        
        # Verify the DELETE request was made with correct parameters
        delete_request = responses.calls[1].request  # Second call is DELETE
        assert "deleteFiles=true" in delete_request.url

    @responses.activate
    def test_api_request_retry_on_failure(self):
        """Test API request retry logic."""
        # First request fails, second succeeds
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/system/status",
            json={"error": "Temporary error"},
            status=503
        )
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/system/status",
            json={"version": "3.0.9.1549"},
            status=200
        )
        
        result = self.client.test_connection()
        assert result is True
        assert len(responses.calls) == 2

    @responses.activate
    def test_api_request_max_retries_exceeded(self):
        """Test API request when max retries exceeded."""
        # All requests fail
        for _ in range(4):  # max_retries + 1
            responses.add(
                responses.GET,
                "http://localhost:8989/api/v3/system/status",
                json={"error": "Persistent error"},
                status=503
            )
        
        with pytest.raises(SonarrConnectionError, match="Max retries exceeded"):
            self.client.test_connection()
        
        assert len(responses.calls) == 4

    def test_empty_api_key_in_config(self):
        """Test client with empty API key."""
        config = SonarrConfig(
            url="http://localhost:8989",
            api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        )
        # Manually set empty API key to bypass Pydantic validation
        config.api_key = ""
        
        with pytest.raises(ValueError, match="API key cannot be empty"):
            SonarrClient(config)


class TestSonarrIntegration:
    """Integration tests for Sonarr operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = SonarrConfig(
            url="http://localhost:8989",
            api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        )
        self.client = SonarrClient(self.config)

    @responses.activate
    def test_full_series_workflow(self):
        """Test complete series management workflow."""
        # Mock getting series list
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/series",
            json=[{
                "id": 1,
                "title": "Test Series",
                "monitored": True,
                "seasons": [
                    {"seasonNumber": 1, "monitored": True},
                    {"seasonNumber": 2, "monitored": True}
                ]
            }],
            status=200
        )
        
        # Mock getting single series for unmonitor operation
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/series/1",
            json={
                "id": 1,
                "title": "Test Series",
                "monitored": True,
                "seasons": [
                    {"seasonNumber": 1, "monitored": True},
                    {"seasonNumber": 2, "monitored": True}
                ]
            },
            status=200
        )
        
        # Mock unmonitoring series
        responses.add(
            responses.PUT,
            "http://localhost:8989/api/v3/series/1",
            json={
                "id": 1,
                "title": "Test Series",
                "monitored": False,
                "seasons": [
                    {"seasonNumber": 1, "monitored": False},
                    {"seasonNumber": 2, "monitored": False}
                ]
            },
            status=200
        )
        
        # Get series
        series_list = self.client.get_series()
        assert len(series_list) == 1
        
        test_series = series_list[0]
        assert test_series["monitored"] is True
        
        # Unmonitor series
        result = self.client.unmonitor_series(test_series["id"])
        assert result is True


class TestSonarrSeasonDeletion:
    """Test season-level deletion functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = SonarrConfig(
            url="http://localhost:8989",
            api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        )
        self.client = SonarrClient(self.config)

    @responses.activate
    def test_get_season_episodes_success(self):
        """Test successful retrieval of season episodes."""
        mock_episodes = [
            {
                "id": 1,
                "episodeNumber": 1,
                "seasonNumber": 1,
                "seriesId": 1,
                "title": "Episode 1",
                "hasFile": True,
                "episodeFile": {
                    "id": 10,
                    "path": "/tv/series/Season 01/Episode 01.mkv"
                }
            },
            {
                "id": 2,
                "episodeNumber": 2,
                "seasonNumber": 1,
                "seriesId": 1,
                "title": "Episode 2",
                "hasFile": True,
                "episodeFile": {
                    "id": 11,
                    "path": "/tv/series/Season 01/Episode 02.mkv"
                }
            }
        ]
        
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/episode?seriesId=1",
            json=mock_episodes,
            status=200
        )
        
        episodes = self.client.get_season_episodes(1, 1)
        assert len(episodes) == 2
        assert all(ep["seasonNumber"] == 1 for ep in episodes)
        assert episodes[0]["hasFile"] is True
        assert episodes[1]["hasFile"] is True

    @responses.activate
    def test_get_season_episodes_no_files(self):
        """Test getting season episodes when no files exist."""
        mock_episodes = [
            {
                "id": 1,
                "episodeNumber": 1,
                "seasonNumber": 1,
                "seriesId": 1,
                "title": "Episode 1",
                "hasFile": False,
                "episodeFile": None
            }
        ]
        
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/episode?seriesId=1",
            json=mock_episodes,
            status=200
        )
        
        episodes = self.client.get_season_episodes(1, 1)
        assert len(episodes) == 1
        assert episodes[0]["hasFile"] is False
        assert episodes[0]["episodeFile"] is None

    @responses.activate
    def test_get_season_episodes_empty_season(self):
        """Test getting episodes from season with no episodes."""
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/episode?seriesId=1",
            json=[],  # No episodes for this series/season
            status=200
        )
        
        episodes = self.client.get_season_episodes(1, 5)
        assert len(episodes) == 0

    @responses.activate
    def test_delete_season_files_success(self):
        """Test successful deletion of season files."""
        # Mock getting episodes
        mock_episodes = [
            {
                "id": 1,
                "episodeNumber": 1,
                "seasonNumber": 1,
                "seriesId": 1,
                "hasFile": True,
                "episodeFile": {"id": 10}
            },
            {
                "id": 2,
                "episodeNumber": 2,
                "seasonNumber": 1,
                "seriesId": 1,
                "hasFile": True,
                "episodeFile": {"id": 11}
            }
        ]
        
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/episode?seriesId=1",
            json=mock_episodes,
            status=200
        )
        
        # Mock deleting episode files
        responses.add(
            responses.DELETE,
            "http://localhost:8989/api/v3/episodefile/10",
            status=200
        )
        responses.add(
            responses.DELETE,
            "http://localhost:8989/api/v3/episodefile/11",
            status=200
        )
        
        result = self.client.delete_season_files(1, 1)
        assert result is True
        
        # Verify both episode files were deleted
        delete_calls = [call for call in responses.calls if call.request.method == 'DELETE']
        assert len(delete_calls) == 2

    @responses.activate
    def test_delete_season_files_no_files(self):
        """Test deleting season files when no files exist."""
        mock_episodes = [
            {
                "id": 1,
                "episodeNumber": 1,
                "seasonNumber": 1,
                "seriesId": 1,
                "hasFile": False,
                "episodeFile": None
            }
        ]
        
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/episode?seriesId=1",
            json=mock_episodes,
            status=200
        )
        
        result = self.client.delete_season_files(1, 1)
        assert result is True  # Should succeed even with no files
        
        # Verify no DELETE calls were made
        delete_calls = [call for call in responses.calls if call.request.method == 'DELETE']
        assert len(delete_calls) == 0

    @responses.activate
    def test_delete_season_files_partial_failure(self):
        """Test deleting season files with some failures."""
        mock_episodes = [
            {
                "id": 1,
                "episodeNumber": 1,
                "seasonNumber": 1,
                "seriesId": 1,
                "hasFile": True,
                "episodeFile": {"id": 10}
            },
            {
                "id": 2,
                "episodeNumber": 2,
                "seasonNumber": 1,
                "seriesId": 1,
                "hasFile": True,
                "episodeFile": {"id": 11}
            }
        ]
        
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/episode?seriesId=1",
            json=mock_episodes,
            status=200
        )
        
        # First delete succeeds, second fails
        responses.add(
            responses.DELETE,
            "http://localhost:8989/api/v3/episodefile/10",
            status=200
        )
        responses.add(
            responses.DELETE,
            "http://localhost:8989/api/v3/episodefile/11",
            json={"error": "File not found"},
            status=404
        )
        
        # Should succeed if at least one file is deleted
        result = self.client.delete_season_files(1, 1)
        assert result is True

    @responses.activate
    def test_unmonitor_and_delete_season_success(self):
        """Test successful unmonitor and delete season operation."""
        # Mock getting series data for unmonitor
        mock_series = {
            "id": 1,
            "title": "Test Series",
            "seasons": [
                {"seasonNumber": 1, "monitored": True},
                {"seasonNumber": 2, "monitored": True}
            ]
        }
        
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/series/1",
            json=mock_series,
            status=200
        )
        
        # Mock updating series (unmonitor)
        updated_series = mock_series.copy()
        updated_series["seasons"] = [
            {"seasonNumber": 1, "monitored": False},
            {"seasonNumber": 2, "monitored": True}
        ]
        
        responses.add(
            responses.PUT,
            "http://localhost:8989/api/v3/series/1",
            json=updated_series,
            status=200
        )
        
        # Mock getting episodes for deletion
        mock_episodes = [
            {
                "id": 1,
                "episodeNumber": 1,
                "seasonNumber": 1,
                "seriesId": 1,
                "hasFile": True,
                "episodeFile": {"id": 10}
            }
        ]
        
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/episode?seriesId=1",
            json=mock_episodes,
            status=200
        )
        
        # Mock deleting episode file
        responses.add(
            responses.DELETE,
            "http://localhost:8989/api/v3/episodefile/10",
            status=200
        )
        
        result = self.client.unmonitor_and_delete_season(1, 1)
        assert result is True
        
        # Verify the sequence: GET series, PUT series (unmonitor), GET episodes, DELETE file
        assert len(responses.calls) == 4
        assert responses.calls[0].request.method == 'GET'  # Get series
        assert responses.calls[1].request.method == 'PUT'  # Unmonitor
        assert responses.calls[2].request.method == 'GET'  # Get episodes
        assert responses.calls[3].request.method == 'DELETE'  # Delete file

    @responses.activate
    def test_unmonitor_and_delete_season_unmonitor_fails(self):
        """Test unmonitor and delete when unmonitor fails."""
        # Mock getting series data
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/series/1",
            json={"error": "Series not found"},
            status=404
        )
        
        with pytest.raises(SonarrError, match="Resource not found"):
            self.client.unmonitor_and_delete_season(1, 1)

    @responses.activate
    def test_unmonitor_and_delete_season_delete_fails(self):
        """Test unmonitor and delete when delete fails but unmonitor succeeded."""
        # Mock successful unmonitor
        mock_series = {
            "id": 1,
            "title": "Test Series",
            "seasons": [
                {"seasonNumber": 1, "monitored": True}
            ]
        }
        
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/series/1",
            json=mock_series,
            status=200
        )
        
        updated_series = mock_series.copy()
        updated_series["seasons"] = [
            {"seasonNumber": 1, "monitored": False}
        ]
        
        responses.add(
            responses.PUT,
            "http://localhost:8989/api/v3/series/1",
            json=updated_series,
            status=200
        )
        
        # Mock failed episode retrieval
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/episode?seriesId=1",
            json={"error": "Internal error"},
            status=500
        )
        
        # Should still return True because unmonitor succeeded (preventing re-download)
        result = self.client.unmonitor_and_delete_season(1, 1)
        assert result is True

    @responses.activate  
    def test_delete_season_special_episodes(self):
        """Test handling of season 0 (specials) deletion."""
        mock_episodes = [
            {
                "id": 1,
                "episodeNumber": 1,
                "seasonNumber": 0,  # Special season
                "seriesId": 1,
                "hasFile": True,
                "episodeFile": {"id": 10}
            }
        ]
        
        responses.add(
            responses.GET,
            "http://localhost:8989/api/v3/episode?seriesId=1",
            json=mock_episodes,
            status=200
        )
        
        responses.add(
            responses.DELETE,
            "http://localhost:8989/api/v3/episodefile/10",
            status=200
        )
        
        result = self.client.delete_season_files(1, 0)
        assert result is True