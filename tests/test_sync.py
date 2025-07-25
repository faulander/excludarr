"""Tests for sync engine functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock

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
        self.mock_availability_checker = Mock()
        
        self.sync_engine = SyncEngine(
            config=self.config,
            sonarr_client=self.mock_sonarr_client,
            provider_manager=self.mock_provider_manager,
            availability_checker=self.mock_availability_checker
        )

    def test_sync_engine_initialization(self):
        """Test sync engine initialization."""
        assert self.sync_engine.config == self.config
        assert self.sync_engine.sonarr_client == self.mock_sonarr_client
        assert self.sync_engine.provider_manager == self.mock_provider_manager
        assert self.sync_engine.availability_checker == self.mock_availability_checker

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

    def test_check_series_availability(self):
        """Test checking series availability on streaming providers."""
        series = {
            "id": 1,
            "title": "Breaking Bad",
            "tvdbId": 81189,
            "seasons": [
                {"seasonNumber": 1, "monitored": True},
                {"seasonNumber": 2, "monitored": True}
            ]
        }
        
        # Mock availability checker
        self.mock_availability_checker.check_series_availability.return_value = {
            "netflix": {"available": True, "seasons": [1, 2]},
            "amazon-prime": {"available": False, "seasons": []}
        }
        
        availability = self.sync_engine._check_series_availability(series)
        
        assert availability["netflix"]["available"] is True
        assert availability["netflix"]["seasons"] == [1, 2]
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
        assert decision.reason == "Available on netflix (seasons: 1, 2)"
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
        
        assert decision.should_process is False
        assert decision.reason == "Not available on any configured streaming providers"

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
        assert result.action_taken == "dry-run"
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
        
        self.mock_sonarr_client.delete_series.assert_called_once_with(1, delete_files=False)

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

    def test_run_sync_complete_workflow(self):
        """Test complete sync workflow."""
        # Mock eligible series
        mock_series = [
            {
                "id": 1,
                "title": "Breaking Bad",
                "monitored": True,
                "added": "2024-01-01T00:00:00Z",
                "tvdbId": 81189,
                "seasons": [
                    {"seasonNumber": 1, "monitored": True},
                    {"seasonNumber": 2, "monitored": True}
                ]
            }
        ]
        
        self.mock_sonarr_client.get_monitored_series.return_value = mock_series
        
        # Mock availability check
        self.mock_availability_checker.check_series_availability.return_value = {
            "netflix": {"available": True, "seasons": [1, 2]},
            "amazon-prime": {"available": False, "seasons": []}
        }
        
        # Run sync
        sync_results = self.sync_engine.run_sync()
        
        assert isinstance(sync_results, list)
        assert len(sync_results) == 1
        
        result = sync_results[0]
        assert result.series_id == 1
        assert result.series_title == "Breaking Bad"
        assert result.success is True
        assert result.action_taken == "dry-run"  # Because dry_run=True

    def test_run_sync_no_eligible_series(self):
        """Test sync when no series are eligible."""
        # Mock no eligible series
        self.mock_sonarr_client.get_monitored_series.return_value = []
        
        sync_results = self.sync_engine.run_sync()
        
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