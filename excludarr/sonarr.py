"""Sonarr API client for excludarr."""

import time
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin

import requests
from loguru import logger
from pydantic import ValidationError

from excludarr.models import SonarrConfig


class SonarrError(Exception):
    """Base exception for Sonarr API errors."""
    pass


class SonarrConnectionError(SonarrError):
    """Exception for Sonarr connection errors."""
    pass


class SonarrClient:
    """Client for interacting with Sonarr API."""
    
    def __init__(self, config: SonarrConfig):
        """Initialize Sonarr client.
        
        Args:
            config: Sonarr configuration
            
        Raises:
            ValueError: If configuration is invalid
        """
        if not config.api_key:
            raise ValueError("API key cannot be empty")
            
        try:
            self.base_url = config.url
            self.api_key = config.api_key
            self.config = config
        except (AttributeError, ValidationError) as e:
            raise ValueError(f"Invalid Sonarr URL: {e}")
        
        self.session = requests.Session()
        self.session.headers.update({
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        })
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 1  # seconds
        self.timeout = 30  # seconds
        
        logger.debug(f"Initialized Sonarr client for {self.base_url}")

    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        retries: int = 0
    ) -> requests.Response:
        """Make HTTP request to Sonarr API with retry logic.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            params: URL parameters
            json_data: JSON payload for POST/PUT requests
            retries: Current retry count
            
        Returns:
            Response object
            
        Raises:
            SonarrConnectionError: If connection fails after retries
            SonarrError: If API returns an error
        """
        url = urljoin(str(self.base_url), f"/api/v3/{endpoint}")
        
        try:
            logger.debug(f"Making {method} request to {url}")
            
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=self.timeout
            )
            
            # Handle authentication errors
            if response.status_code == 401:
                raise SonarrConnectionError("Authentication failed. Check your API key.")
            
            # Handle server errors with retry logic
            if response.status_code >= 500 and retries < self.max_retries:
                logger.warning(f"Server error {response.status_code}, retrying in {self.retry_delay}s...")
                time.sleep(self.retry_delay * (retries + 1))  # Exponential backoff
                return self._make_request(method, endpoint, params, json_data, retries + 1)
            
            # Handle server errors after max retries
            if response.status_code >= 500:
                raise SonarrConnectionError(f"Max retries exceeded. Server error: {response.status_code}")
            
            # Handle other client errors
            if response.status_code >= 400:
                try:
                    error_msg = response.json().get("message", "Unknown error")
                except:
                    error_msg = f"HTTP {response.status_code}"
                
                if response.status_code == 404:
                    raise SonarrError(f"Resource not found: {error_msg}")
                else:
                    raise SonarrError(f"API error: {error_msg}")
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.ConnectionError as e:
            if retries < self.max_retries:
                logger.warning(f"Connection error, retrying in {self.retry_delay}s...")
                time.sleep(self.retry_delay * (retries + 1))
                return self._make_request(method, endpoint, params, json_data, retries + 1)
            else:
                raise SonarrConnectionError(f"Max retries exceeded. Connection error: {e}")
                
        except requests.exceptions.Timeout as e:
            if retries < self.max_retries:
                logger.warning(f"Request timeout, retrying in {self.retry_delay}s...")
                time.sleep(self.retry_delay * (retries + 1))
                return self._make_request(method, endpoint, params, json_data, retries + 1)
            else:
                raise SonarrConnectionError(f"Max retries exceeded. Timeout: {e}")
        
        except requests.exceptions.RequestException as e:
            raise SonarrConnectionError(f"Request failed: {e}")

    def test_connection(self) -> bool:
        """Test connection to Sonarr API.
        
        Returns:
            True if connection successful
            
        Raises:
            SonarrConnectionError: If connection fails
        """
        try:
            response = self._make_request("GET", "system/status")
            
            if response.status_code == 200:
                status_data = response.json()
                version = status_data.get("version", "unknown")
                logger.info(f"Successfully connected to Sonarr v{version}")
                return True
            else:
                raise SonarrConnectionError(f"Unexpected response: {response.status_code}")
                
        except SonarrError:
            raise
        except Exception as e:
            raise SonarrConnectionError(f"Connection test failed: {e}")

    def get_series(self) -> List[Dict[str, Any]]:
        """Get all series from Sonarr.
        
        Returns:
            List of series data
            
        Raises:
            SonarrError: If API request fails
        """
        try:
            response = self._make_request("GET", "series")
            series_data = response.json()
            
            logger.debug(f"Retrieved {len(series_data)} series from Sonarr")
            return series_data
            
        except SonarrError:
            raise
        except Exception as e:
            raise SonarrError(f"Failed to get series: {e}")

    def get_series_by_id(self, series_id: int) -> Dict[str, Any]:
        """Get specific series by ID.
        
        Args:
            series_id: Sonarr series ID
            
        Returns:
            Series data
            
        Raises:
            SonarrError: If series not found or API request fails
        """
        try:
            response = self._make_request("GET", f"series/{series_id}")
            
            if response.status_code == 404:
                raise SonarrError(f"Series with ID {series_id} not found")
            
            series_data = response.json()
            logger.debug(f"Retrieved series: {series_data.get('title', 'Unknown')}")
            return series_data
            
        except SonarrError:
            raise
        except Exception as e:
            raise SonarrError(f"Failed to get series {series_id}: {e}")

    def unmonitor_series(self, series_id: int) -> bool:
        """Unmonitor a series and all its seasons.
        
        Args:
            series_id: Sonarr series ID
            
        Returns:
            True if successful
            
        Raises:
            SonarrError: If operation fails
        """
        try:
            # Get current series data
            series_data = self.get_series_by_id(series_id)
            
            # Update monitoring status
            series_data["monitored"] = False
            
            # Unmonitor all seasons
            for season in series_data.get("seasons", []):
                season["monitored"] = False
            
            # Send update request
            response = self._make_request("PUT", f"series/{series_id}", json_data=series_data)
            
            if response.status_code in [200, 202]:
                logger.info(f"Successfully unmonitored series: {series_data.get('title', series_id)}")
                return True
            else:
                raise SonarrError(f"Unexpected response: {response.status_code}")
                
        except SonarrError:
            raise
        except Exception as e:
            raise SonarrError(f"Failed to unmonitor series {series_id}: {e}")

    def unmonitor_season(self, series_id: int, season_number: int) -> bool:
        """Unmonitor a specific season.
        
        Args:
            series_id: Sonarr series ID
            season_number: Season number to unmonitor
            
        Returns:
            True if successful
            
        Raises:
            SonarrError: If operation fails
        """
        try:
            # Get current series data
            series_data = self.get_series_by_id(series_id)
            
            # Find and update the specific season
            season_found = False
            for season in series_data.get("seasons", []):
                if season.get("seasonNumber") == season_number:
                    season["monitored"] = False
                    season_found = True
                    break
            
            if not season_found:
                raise SonarrError(f"Season {season_number} not found in series {series_id}")
            
            # Send update request
            response = self._make_request("PUT", f"series/{series_id}", json_data=series_data)
            
            if response.status_code in [200, 202]:
                logger.info(f"Successfully unmonitored season {season_number} of series: {series_data.get('title', series_id)}")
                return True
            else:
                raise SonarrError(f"Unexpected response: {response.status_code}")
                
        except SonarrError:
            raise
        except Exception as e:
            raise SonarrError(f"Failed to unmonitor season {season_number} of series {series_id}: {e}")

    def delete_series(self, series_id: int, delete_files: bool = False) -> bool:
        """Delete a series from Sonarr.
        
        Args:
            series_id: Sonarr series ID
            delete_files: Whether to delete files from disk
            
        Returns:
            True if successful
            
        Raises:
            SonarrError: If operation fails
        """
        try:
            # Get series info for logging
            try:
                series_data = self.get_series_by_id(series_id)
                series_title = series_data.get("title", f"Series {series_id}")
            except SonarrError:
                series_title = f"Series {series_id}"
            
            # Prepare delete parameters
            params = {
                "deleteFiles": str(delete_files).lower()
            }
            
            # Send delete request
            response = self._make_request("DELETE", f"series/{series_id}", params=params)
            
            if response.status_code in [200, 202, 204]:
                action = "and files" if delete_files else "without files"
                logger.info(f"Successfully deleted series: {series_title} ({action})")
                return True
            else:
                raise SonarrError(f"Unexpected response: {response.status_code}")
                
        except SonarrError:
            raise
        except Exception as e:
            raise SonarrError(f"Failed to delete series {series_id}: {e}")

    def get_series_count(self) -> int:
        """Get total number of series in Sonarr.
        
        Returns:
            Number of series
            
        Raises:
            SonarrError: If API request fails
        """
        try:
            series_data = self.get_series()
            return len(series_data)
        except SonarrError:
            raise
        except Exception as e:
            raise SonarrError(f"Failed to get series count: {e}")

    def get_monitored_series(self) -> List[Dict[str, Any]]:
        """Get only monitored series from Sonarr.
        
        Returns:
            List of monitored series data
            
        Raises:
            SonarrError: If API request fails
        """
        try:
            all_series = self.get_series()
            monitored_series = [series for series in all_series if series.get("monitored", False)]
            
            logger.debug(f"Found {len(monitored_series)} monitored series out of {len(all_series)} total")
            return monitored_series
            
        except SonarrError:
            raise
        except Exception as e:
            raise SonarrError(f"Failed to get monitored series: {e}")

    def get_season_episodes(self, series_id: int, season_number: int) -> List[Dict[str, Any]]:
        """Get all episodes for a specific season.
        
        Args:
            series_id: Sonarr series ID
            season_number: Season number to get episodes for
            
        Returns:
            List of episode data for the season
            
        Raises:
            SonarrError: If API request fails
        """
        try:
            # Get all episodes for the series
            response = self._make_request("GET", "episode", params={"seriesId": series_id})
            all_episodes = response.json()
            
            # Filter to only episodes from the requested season
            season_episodes = [
                episode for episode in all_episodes 
                if episode.get("seasonNumber") == season_number
            ]
            
            logger.debug(f"Found {len(season_episodes)} episodes in season {season_number} of series {series_id}")
            return season_episodes
            
        except SonarrError:
            raise
        except Exception as e:
            raise SonarrError(f"Failed to get season {season_number} episodes for series {series_id}: {e}")

    def delete_season_files(self, series_id: int, season_number: int) -> bool:
        """Delete all episode files for a specific season.
        
        Args:
            series_id: Sonarr series ID
            season_number: Season number to delete files for
            
        Returns:
            True if successful (even if no files existed)
            
        Raises:
            SonarrError: If operation fails
        """
        try:
            # Get episodes for the season
            episodes = self.get_season_episodes(series_id, season_number)
            
            # Track deletion results
            deleted_count = 0
            total_files = 0
            
            for episode in episodes:
                if episode.get("hasFile", False) and episode.get("episodeFile"):
                    total_files += 1
                    episode_file_id = episode["episodeFile"]["id"]
                    
                    try:
                        # Delete the episode file
                        response = self._make_request("DELETE", f"episodefile/{episode_file_id}")
                        
                        if response.status_code == 200:
                            deleted_count += 1
                            logger.debug(f"Deleted episode file {episode_file_id} for season {season_number}")
                        else:
                            logger.warning(f"Failed to delete episode file {episode_file_id}: HTTP {response.status_code}")
                            
                    except Exception as e:
                        logger.warning(f"Failed to delete episode file {episode_file_id}: {e}")
                        continue
            
            if total_files == 0:
                logger.info(f"No files found for season {season_number} of series {series_id}")
            else:
                logger.info(f"Deleted {deleted_count}/{total_files} episode files for season {season_number} of series {series_id}")
            
            return True
            
        except SonarrError:
            raise
        except Exception as e:
            raise SonarrError(f"Failed to delete season {season_number} files for series {series_id}: {e}")

    def unmonitor_and_delete_season(self, series_id: int, season_number: int) -> bool:
        """Unmonitor a season and delete its files atomically.
        
        This method ensures the season is unmonitored first to prevent Sonarr
        from re-downloading the deleted episodes.
        
        Args:
            series_id: Sonarr series ID
            season_number: Season number to unmonitor and delete
            
        Returns:
            True if successful (unmonitor must succeed, file deletion can partially fail)
            
        Raises:
            SonarrError: If unmonitor operation fails
        """
        try:
            # Step 1: Unmonitor the season (critical - prevents re-download)
            unmonitor_success = self.unmonitor_season(series_id, season_number)
            if not unmonitor_success:
                raise SonarrError(f"Failed to unmonitor season {season_number} - aborting delete operation")
            
            logger.info(f"Successfully unmonitored season {season_number} of series {series_id}")
            
            # Step 2: Delete the files (best effort - unmonitor already prevents re-download)
            try:
                delete_success = self.delete_season_files(series_id, season_number)
                if delete_success:
                    logger.info(f"Successfully deleted files for season {season_number} of series {series_id}")
                else:
                    logger.warning(f"File deletion had issues for season {season_number}, but season is unmonitored")
                    
            except Exception as e:
                logger.warning(f"File deletion failed for season {season_number}, but season is unmonitored: {e}")
            
            # Return True because unmonitor succeeded (the critical operation)
            return True
            
        except SonarrError:
            raise
        except Exception as e:
            raise SonarrError(f"Failed to unmonitor and delete season {season_number} for series {series_id}: {e}")