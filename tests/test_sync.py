"""Tests for sync engine functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import asyncio

from excludarr.sync import SyncEngine, SyncResult, SyncDecision, SyncError
from excludarr.models import Config, SonarrConfig, StreamingProvider, SyncConfig, TMDBConfig, ProviderAPIsConfig


class TestSyncEngine:
    """Test sync engine functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config(
            sonarr=SonarrConfig(
                url="http://localhost:8989",
                api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
            ),
            provider_apis=ProviderAPIsConfig(
                tmdb=TMDBConfig(api_key="test_tmdb_key")
            ),
            streaming_providers=[
                StreamingProvider(name="netflix", country="US"),
                StreamingProvider(name="amazon-prime", country="DE")
            ],
            sync=SyncConfig(
                action="unmonitor",
                dry_run=True,
                exclude_recent_days=7
            )
        )
        
        # Mock dependencies
        self.mock_sonarr_client = Mock()
        self.mock_provider_manager = Mock()
        self.mock_cache = Mock()
        
        self.sync_engine = SyncEngine(
            config=self.config,
            sonarr_client=self.mock_sonarr_client,
            provider_manager=self.mock_provider_manager,
            cache=self.mock_cache
        )

    def test_sync_engine_initialization(self):
        """Test sync engine initialization."""
        assert self.sync_engine.config == self.config
        assert self.sync_engine.sonarr_client == self.mock_sonarr_client
        assert self.sync_engine.provider_manager == self.mock_provider_manager
        assert self.sync_engine.cache == self.mock_cache
        assert self.sync_engine.user_providers == ["netflix", "amazon-prime"]
        assert set(self.sync_engine.user_countries) == {"US", "DE"}

    def test_get_eligible_series(self):
        """Test getting series eligible for sync."""
        # Mock Sonarr series data
        mock_series = [
            {
                "id": 1,
                "title": "Breaking Bad",
                "monitored": True,
                "added": "2024-01-01T00:00:00Z",
                "seasons": [
                    {"seasonNumber": 1, "monitored": True},
                    {"seasonNumber": 2, "monitored": True}
                ]
            },
            {
                "id": 2,
                "title": "Better Call Saul", 
                "monitored": False,
                "added": "2024-01-01T00:00:00Z",
                "seasons": [
                    {"seasonNumber": 1, "monitored": False}
                ]
            },
            {
                "id": 3,
                "title": "New Show",
                "monitored": True,
                "added": "2025-07-24T00:00:00Z",  # Recently added
                "seasons": [
                    {"seasonNumber": 1, "monitored": True}
                ]
            }
        ]
        
        self.mock_sonarr_client.get_monitored_series.return_value = mock_series
        
        eligible_series = self.sync_engine._get_eligible_series()
        
        # Should only return monitored series that are not recently added
        assert len(eligible_series) == 1
        assert eligible_series[0]["id"] == 1
        assert eligible_series[0]["title"] == "Breaking Bad"

    async def test_check_series_availability(self):
        """Test checking series availability on streaming providers."""
        series = {
            "id": 1,
            "title": "Breaking Bad",
            "imdbId": "tt0903747",
            "seasons": [
                {"seasonNumber": 1, "monitored": True},
                {"seasonNumber": 2, "monitored": True}
            ]
        }
        
        # Mock provider manager as async
        async def mock_get_series_availability(imdb_id, countries):
            return {
                "US": {"netflix": True},
                "DE": {"amazon-prime": False}
            }
        
        self.mock_provider_manager.get_series_availability = mock_get_series_availability
        self.mock_provider_manager.filter_by_user_providers.return_value = {
            "US": True,
            "DE": False
        }
        
        availability = await self.sync_engine._check_series_availability(series)
        
        assert availability["netflix"]["available"] is True
        assert availability["amazon-prime"]["available"] is False

    def test_make_sync_decision_series_available(self):
        """Test sync decision when series is available on streaming."""
        series = {
            "id": 1,
            "title": "Breaking Bad",
            "monitored": True,
            "seasons": [
                {"seasonNumber": 1, "monitored": True},
                {"seasonNumber": 2, "monitored": True}
            ]
        }
        
        availability = {
            "netflix": {"available": True, "seasons": [1, 2]},
            "amazon-prime": {"available": False, "seasons": []}
        }
        
        decision = self.sync_engine._make_sync_decision(series, availability)
        
        assert decision.action == "unmonitor"  # From config
        assert decision.reason == "All seasons available on netflix"
        assert decision.should_process is True
        assert decision.provider == "netflix"

    def test_make_sync_decision_series_not_available(self):
        """Test sync decision when series is not available on streaming."""
        series = {
            "id": 1,
            "title": "Breaking Bad",
            "monitored": True,
            "seasons": [
                {"seasonNumber": 1, "monitored": True},
                {"seasonNumber": 2, "monitored": True}
            ]
        }
        
        availability = {
            "netflix": {"available": False, "seasons": []},
            "amazon-prime": {"available": False, "seasons": []}
        }
        
        decision = self.sync_engine._make_sync_decision(series, availability)
        
        assert decision.should_process is False
        assert decision.reason == "Not available on any configured streaming providers"

    def test_make_sync_decision_partial_availability(self):
        """Test sync decision when series is partially available."""
        series = {
            "id": 1,
            "title": "Breaking Bad",
            "monitored": True,
            "seasons": [
                {"seasonNumber": 1, "monitored": True},
                {"seasonNumber": 2, "monitored": True},
                {"seasonNumber": 3, "monitored": True}
            ]
        }
        
        availability = {
            "netflix": {"available": True, "seasons": [1, 2]},  # Missing season 3
            "amazon-prime": {"available": False, "seasons": []}
        }
        
        decision = self.sync_engine._make_sync_decision(series, availability)
        
        # With season-level granularity, partial availability now triggers action
        assert decision.should_process is True
        assert decision.reason == "Seasons 1, 2 available on netflix"
        assert decision.scope == "seasons"
        assert decision.affected_seasons == [1, 2]

    def test_execute_sync_decision_dry_run(self):
        """Test executing sync decision in dry-run mode."""
        decision = SyncDecision(
            series_id=1,
            series_title="Breaking Bad",
            action="unmonitor",
            should_process=True,
            reason="Available on netflix",
            provider="netflix",
            affected_seasons=[1, 2]
        )
        
        # Dry run mode (from config)
        result = self.sync_engine._execute_sync_decision(decision)
        
        assert result.success is True
        assert result.action_taken == "unmonitor"
        assert "would unmonitor" in result.message.lower()
        
        # Verify no actual actions were taken
        self.mock_sonarr_client.unmonitor_series.assert_not_called()
        self.mock_sonarr_client.delete_series.assert_not_called()

    def test_execute_sync_decision_unmonitor_action(self):
        """Test executing unmonitor action."""
        # Set dry_run to False for this test
        self.sync_engine.config.sync.dry_run = False
        
        decision = SyncDecision(
            series_id=1,
            series_title="Breaking Bad",
            action="unmonitor",
            should_process=True,
            reason="Available on netflix",
            provider="netflix",
            affected_seasons=[1, 2]
        )
        
        self.mock_sonarr_client.unmonitor_series.return_value = True
        
        result = self.sync_engine._execute_sync_decision(decision)
        
        assert result.success is True
        assert result.action_taken == "unmonitor"
        assert "unmonitored series" in result.message.lower()
        
        self.mock_sonarr_client.unmonitor_series.assert_called_once_with(1)

    def test_execute_sync_decision_delete_action(self):
        """Test executing delete action."""
        # Set action to delete and dry_run to False
        self.sync_engine.config.sync.action = "delete"
        self.sync_engine.config.sync.dry_run = False
        
        decision = SyncDecision(
            series_id=1,
            series_title="Breaking Bad",
            action="delete",
            should_process=True,
            reason="Available on netflix",
            provider="netflix",
            affected_seasons=[1, 2]
        )
        
        self.mock_sonarr_client.delete_series.return_value = True
        
        result = self.sync_engine._execute_sync_decision(decision)
        
        assert result.success is True
        assert result.action_taken == "delete"
        assert "deleted series" in result.message.lower()
        
        self.mock_sonarr_client.delete_series.assert_called_once_with(1, delete_files=True)

    def test_execute_sync_decision_delete_seasons(self):
        """Test executing delete action on specific seasons."""
        # Set action to delete and dry_run to False
        self.sync_engine.config.sync.action = "delete"
        self.sync_engine.config.sync.dry_run = False

        decision = SyncDecision(
            series_id=1,
            series_title="Breaking Bad",
            action="delete",
            should_process=True,
            reason="Seasons 1, 2 available on netflix",
            provider="netflix",
            affected_seasons=[1, 2],
            scope="seasons"
        )

        self.mock_sonarr_client.unmonitor_and_delete_season.return_value = True

        result = self.sync_engine._execute_sync_decision(decision)

        assert result.success is True
        assert result.action_taken == "delete"
        assert "Deleted seasons 1, 2" in result.message
        
        # Verify both seasons were deleted
        assert self.mock_sonarr_client.unmonitor_and_delete_season.call_count == 2
        self.mock_sonarr_client.unmonitor_and_delete_season.assert_any_call(1, 1)
        self.mock_sonarr_client.unmonitor_and_delete_season.assert_any_call(1, 2)

    def test_execute_sync_decision_failure(self):
        """Test handling sync decision execution failure."""
        # Set dry_run to False for this test
        self.sync_engine.config.sync.dry_run = False
        
        decision = SyncDecision(
            series_id=1,
            series_title="Breaking Bad",
            action="unmonitor",
            should_process=True,
            reason="Available on netflix",
            provider="netflix",
            affected_seasons=[1, 2]
        )
        
        # Mock failure
        self.mock_sonarr_client.unmonitor_series.side_effect = Exception("API Error")
        
        result = self.sync_engine._execute_sync_decision(decision)
        
        assert result.success is False
        assert "failed" in result.message.lower()
        assert "API Error" in result.message

    async def test_run_sync_complete_workflow(self):
        """Test complete sync workflow."""
        # Mock eligible series
        mock_series = [
            {
                "id": 1,
                "title": "Breaking Bad",
                "monitored": True,
                "added": "2024-01-01T00:00:00Z",
                "imdbId": "tt0903747",
                "seasons": [
                    {"seasonNumber": 1, "monitored": True},
                    {"seasonNumber": 2, "monitored": True}
                ]
            }
        ]
        
        self.mock_sonarr_client.get_monitored_series.return_value = mock_series
        
        # Mock provider manager as async
        async def mock_get_series_availability(imdb_id, countries):
            return {
                "US": {"netflix": True},
                "DE": {"amazon-prime": False}
            }
        
        self.mock_provider_manager.get_series_availability = mock_get_series_availability
        self.mock_provider_manager.filter_by_user_providers.return_value = {
            "US": True,
            "DE": False
        }
        
        # Run sync
        sync_results = await self.sync_engine.run_sync()
        
        assert isinstance(sync_results, list)
        assert len(sync_results) == 1
        
        result = sync_results[0]
        assert result.series_id == 1
        assert result.series_title == "Breaking Bad"
        assert result.success is True
        assert result.action_taken == "none"  # No streaming availability

    async def test_run_sync_no_eligible_series(self):
        """Test sync when no series are eligible."""
        # Mock no eligible series
        self.mock_sonarr_client.get_monitored_series.return_value = []
        
        sync_results = await self.sync_engine.run_sync()
        
        assert isinstance(sync_results, list)
        assert len(sync_results) == 0

    def test_get_sync_summary(self):
        """Test generating sync summary."""
        mock_results = [
            SyncResult(
                series_id=1,
                series_title="Breaking Bad",
                success=True,
                action_taken="unmonitor",
                message="Unmonitored series",
                provider="netflix"
            ),
            SyncResult(
                series_id=2,
                series_title="Better Call Saul",
                success=False,
                action_taken="unmonitor",
                message="Failed to unmonitor",
                provider="netflix"
            ),
            SyncResult(
                series_id=3,
                series_title="The Office",
                success=True,
                action_taken="dry-run",
                message="Would unmonitor series",
                provider="amazon-prime"
            )
        ]
        
        summary = self.sync_engine._get_sync_summary(mock_results)
        
        assert summary["total_processed"] == 3
        assert summary["successful"] == 2
        assert summary["failed"] == 1
        assert summary["actions"]["unmonitor"] == 2  # Two results with unmonitor action
        assert summary["actions"]["dry-run"] == 1
        assert summary["providers"]["netflix"] == 2
        assert summary["providers"]["amazon-prime"] == 1


class TestSyncDecision:
    """Test SyncDecision data structure."""
    
    def test_sync_decision_creation(self):
        """Test creating sync decision."""
        decision = SyncDecision(
            series_id=1,
            series_title="Test Series",
            action="unmonitor",
            should_process=True,
            reason="Available on netflix",
            provider="netflix",
            affected_seasons=[1, 2]
        )
        
        assert decision.series_id == 1
        assert decision.series_title == "Test Series"
        assert decision.action == "unmonitor"
        assert decision.should_process is True
        assert decision.reason == "Available on netflix"
        assert decision.provider == "netflix"
        assert decision.affected_seasons == [1, 2]


class TestSyncResult:
    """Test SyncResult data structure."""
    
    def test_sync_result_creation(self):
        """Test creating sync result."""
        result = SyncResult(
            series_id=1,
            series_title="Test Series",
            success=True,
            action_taken="unmonitor",
            message="Successfully unmonitored",
            provider="netflix"
        )
        
        assert result.series_id == 1
        assert result.series_title == "Test Series"
        assert result.success is True
        assert result.action_taken == "unmonitor"
        assert result.message == "Successfully unmonitored"
        assert result.provider == "netflix"


class TestSyncEngineErrorHandling:
    """Test error handling scenarios in sync engine."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config(
            sonarr=SonarrConfig(
                url="http://localhost:8989",
                api_key="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
            ),
            provider_apis=ProviderAPIsConfig(
                tmdb=TMDBConfig(api_key="test_tmdb_key")
            ),
            streaming_providers=[
                StreamingProvider(name="netflix", country="US")
            ],
            sync=SyncConfig(
                action="unmonitor",
                dry_run=True,
                exclude_recent_days=7
            )
        )
        
        self.mock_sonarr_client = Mock()
        self.mock_provider_manager = Mock()
        self.mock_cache = Mock()
        
        self.sync_engine = SyncEngine(
            config=self.config,
            sonarr_client=self.mock_sonarr_client,
            provider_manager=self.mock_provider_manager,
            cache=self.mock_cache
        )

    async def test_run_sync_with_progress_callback(self):
        """Test run_sync with progress callback."""
        # Mock series data
        mock_series = [
            {
                "id": 1,
                "title": "Breaking Bad",
                "monitored": True,
                "added": "2024-01-01T00:00:00Z",
                "seasons": [{"seasonNumber": 1, "monitored": True}],
                "imdbId": "tt0903747"
            }
        ]
        
        self.mock_sonarr_client.get_monitored_series.return_value = mock_series
        
        # Mock the _process_series method to return a result
        mock_result = SyncResult(
            series_id=1,
            series_title="Breaking Bad",
            success=True,
            action_taken="unmonitor",
            message="Would unmonitor series",
            provider="netflix"
        )
        
        with patch.object(self.sync_engine, '_process_series', return_value=mock_result):
            # Mock progress callback
            progress_callback = Mock()
            
            results = await self.sync_engine.run_sync(progress_callback=progress_callback)
            
            # Verify progress callback was called (index starts at 1, not 0)
            progress_callback.assert_called_with(1, 1, "Breaking Bad")
            assert len(results) == 1

    async def test_run_sync_with_exception_in_process_series(self):
        """Test run_sync when _process_series raises an exception."""
        # Mock series data
        mock_series = [
            {
                "id": 1,
                "title": "Breaking Bad",
                "monitored": True,
                "added": "2024-01-01T00:00:00Z",
                "seasons": [{"seasonNumber": 1, "monitored": True}],
                "imdbId": "tt0903747"
            }
        ]
        
        self.mock_sonarr_client.get_monitored_series.return_value = mock_series
        
        # Mock _process_series to raise an exception
        with patch.object(self.sync_engine, '_process_series', side_effect=Exception("Processing failed")):
            results = await self.sync_engine.run_sync()
            
            # Should return a failed result
            assert len(results) == 1
            assert results[0].success is False
            assert "Processing failed" in results[0].message

    async def test_run_sync_with_sync_engine_exception(self):
        """Test run_sync when a SyncError is raised."""
        # Mock get_monitored_series to raise an exception
        self.mock_sonarr_client.get_monitored_series.side_effect = Exception("Sonarr connection failed")
        
        with pytest.raises(SyncError, match="Sync operation failed"):
            await self.sync_engine.run_sync()

    def test_test_connectivity_all_successful(self):
        """Test connectivity when all services are working."""
        # Mock successful connections
        self.mock_sonarr_client.test_connection.return_value = None
        self.mock_provider_manager.get_quota_status.return_value = {"tmdb": {"available": True}}
        self.mock_cache.get_statistics.return_value = {"total_entries": 100}
        
        results = self.sync_engine.test_connectivity()
        
        assert results["sonarr"]["connected"] is True
        assert results["sonarr"]["error"] is None
        assert results["provider_manager"]["initialized"] is True
        assert results["provider_manager"]["providers"] == 1
        assert results["provider_manager"]["error"] is None
        assert results["cache"]["initialized"] is True
        assert results["cache"]["error"] is None

    def test_test_connectivity_sonarr_failure(self):
        """Test connectivity when Sonarr connection fails."""
        # Mock failed Sonarr connection
        self.mock_sonarr_client.test_connection.side_effect = Exception("Connection refused")
        self.mock_provider_manager.get_quota_status.return_value = {"tmdb": {"available": True}}
        self.mock_cache.get_statistics.return_value = {"total_entries": 100}
        
        results = self.sync_engine.test_connectivity()
        
        assert results["sonarr"]["connected"] is False
        assert results["sonarr"]["error"] == "Connection refused"
        assert results["provider_manager"]["initialized"] is True
        assert results["cache"]["initialized"] is True

    def test_test_connectivity_provider_manager_failure(self):
        """Test connectivity when provider manager fails."""
        # Mock successful Sonarr but failed provider manager
        self.mock_sonarr_client.test_connection.return_value = None
        self.mock_provider_manager.get_quota_status.side_effect = Exception("API key invalid")
        self.mock_cache.get_statistics.return_value = {"total_entries": 100}
        
        results = self.sync_engine.test_connectivity()
        
        assert results["sonarr"]["connected"] is True
        assert results["provider_manager"]["initialized"] is False
        assert results["provider_manager"]["error"] == "API key invalid"
        assert results["cache"]["initialized"] is True

    def test_test_connectivity_cache_failure(self):
        """Test connectivity when cache fails."""
        # Mock successful connections but failed cache
        self.mock_sonarr_client.test_connection.return_value = None
        self.mock_provider_manager.get_quota_status.return_value = {"tmdb": {"available": True}}
        self.mock_cache.get_statistics.side_effect = Exception("Database locked")
        
        results = self.sync_engine.test_connectivity()
        
        assert results["sonarr"]["connected"] is True
        assert results["provider_manager"]["initialized"] is True
        assert results["cache"]["initialized"] is False
        assert results["cache"]["error"] == "Database locked"

    def test_get_eligible_series_sonarr_error(self):
        """Test _get_eligible_series when Sonarr call fails."""
        # Mock Sonarr to raise an exception
        self.mock_sonarr_client.get_monitored_series.side_effect = Exception("Sonarr API error")
        
        # The method doesn't actually raise SyncError for this case - it just raises the exception
        with pytest.raises(Exception, match="Sonarr API error"):
            self.sync_engine._get_eligible_series()

    async def test_process_series_missing_imdb_id(self):
        """Test _process_series when series lacks IMDb ID."""
        series = {
            "id": 1,
            "title": "Test Series",
            "seasons": [{"seasonNumber": 1, "monitored": True}]
            # Missing imdbId
        }
        
        result = await self.sync_engine._process_series(series)
        
        # Series without IMDb ID just get no availability data, but still return success
        assert result.success is True
        assert result.action_taken == "none" 
        assert "Not available on any configured streaming providers" in result.message

    async def test_process_series_availability_check_error(self):
        """Test _process_series when availability check fails."""
        series = {
            "id": 1,
            "title": "Test Series",
            "imdbId": "tt1234567",
            "seasons": [{"seasonNumber": 1, "monitored": True}]
        }
        
        # Mock availability check to raise an exception
        with patch.object(self.sync_engine, '_check_series_availability', side_effect=Exception("API error")):
            result = await self.sync_engine._process_series(series)
            
            assert result.success is False
            assert "API error" in result.message
            assert result.action_taken == "none"