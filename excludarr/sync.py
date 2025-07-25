"""Core sync logic for excludarr."""

import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

from loguru import logger

from excludarr.models import Config
from excludarr.sonarr import SonarrClient, SonarrError
from excludarr.providers import ProviderManager
from excludarr.availability import AvailabilityChecker


class SyncError(Exception):
    """Exception for sync-related errors."""
    pass


@dataclass
class SyncDecision:
    """Represents a decision about whether to sync a series."""
    series_id: int
    series_title: str
    action: str  # "unmonitor" or "delete"
    should_process: bool
    reason: str
    provider: Optional[str] = None
    affected_seasons: Optional[List[int]] = None


@dataclass
class SyncResult:
    """Represents the result of a sync operation."""
    series_id: int
    series_title: str
    success: bool
    action_taken: str
    message: str
    provider: Optional[str] = None
    error: Optional[str] = None


class SyncEngine:
    """Main sync engine that coordinates between Sonarr and streaming providers."""
    
    def __init__(
        self,
        config: Config,
        sonarr_client: Optional[SonarrClient] = None,
        provider_manager: Optional[ProviderManager] = None,
        availability_checker: Optional[AvailabilityChecker] = None
    ):
        """Initialize sync engine.
        
        Args:
            config: Application configuration
            sonarr_client: Sonarr API client (optional for testing)
            provider_manager: Provider manager (optional for testing)
            availability_checker: Availability checker (optional for testing)
        """
        self.config = config
        
        # Initialize clients
        self.sonarr_client = sonarr_client or SonarrClient(config.sonarr)
        self.provider_manager = provider_manager or ProviderManager()
        self.availability_checker = availability_checker or AvailabilityChecker(
            self.provider_manager,
            config.streaming_providers
        )
        
        logger.info("Sync engine initialized")

    def run_sync(self) -> List[SyncResult]:
        """Run complete sync operation.
        
        Returns:
            List of sync results
            
        Raises:
            SyncError: If sync operation fails
        """
        try:
            logger.info("Starting sync operation")
            start_time = time.time()
            
            # Get eligible series
            eligible_series = self._get_eligible_series()
            logger.info(f"Found {len(eligible_series)} eligible series for sync")
            
            if not eligible_series:
                logger.info("No eligible series found, sync complete")
                return []
            
            # Process each series
            results = []
            for series in eligible_series:
                try:
                    result = self._process_series(series)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Failed to process series {series.get('title', 'Unknown')}: {e}")
                    results.append(SyncResult(
                        series_id=series.get("id", 0),
                        series_title=series.get("title", "Unknown"),
                        success=False,
                        action_taken="none",
                        message=f"Processing failed: {e}",
                        error=str(e)
                    ))
            
            # Log summary
            duration = time.time() - start_time
            summary = self._get_sync_summary(results)
            logger.info(f"Sync completed in {duration:.2f}s: {summary['successful']}/{summary['total_processed']} successful")
            
            return results
            
        except Exception as e:
            logger.error(f"Sync operation failed: {e}")
            raise SyncError(f"Sync operation failed: {e}")

    def _get_eligible_series(self) -> List[Dict[str, Any]]:
        """Get series eligible for sync processing.
        
        Returns:
            List of series data from Sonarr
        """
        try:
            # Get all monitored series
            all_series = self.sonarr_client.get_monitored_series()
            logger.debug(f"Retrieved {len(all_series)} monitored series from Sonarr")
            
            # Filter out recently added series
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.config.sync.exclude_recent_days)
            eligible_series = []
            
            for series in all_series:
                # Skip if not monitored
                if not series.get("monitored", False):
                    continue
                
                # Check if series was added recently
                added_date_str = series.get("added")
                if added_date_str:
                    try:
                        # Parse ISO date string
                        added_date = datetime.fromisoformat(added_date_str.replace('Z', '+00:00'))
                        if added_date > cutoff_date:
                            logger.debug(f"Skipping recently added series: {series.get('title')}")
                            continue
                    except ValueError:
                        logger.warning(f"Could not parse added date for series: {series.get('title')}")
                
                eligible_series.append(series)
            
            logger.debug(f"Filtered to {len(eligible_series)} eligible series")
            return eligible_series
            
        except SonarrError as e:
            raise SyncError(f"Failed to get series from Sonarr: {e}")

    def _process_series(self, series: Dict[str, Any]) -> Optional[SyncResult]:
        """Process a single series for sync.
        
        Args:
            series: Series data from Sonarr
            
        Returns:
            Sync result or None if no action needed
        """
        series_title = series.get("title", "Unknown")
        series_id = series.get("id")
        
        logger.debug(f"Processing series: {series_title}")
        
        try:
            # Check availability on streaming providers
            availability = self._check_series_availability(series)
            
            # Make sync decision
            decision = self._make_sync_decision(series, availability)
            
            # Log decision
            logger.info(f"Decision for '{series_title}': {decision.reason}")
            
            # Execute decision if needed
            if decision.should_process:
                return self._execute_sync_decision(decision)
            else:
                # Return result for "no action" case
                return SyncResult(
                    series_id=series_id,
                    series_title=series_title,
                    success=True,
                    action_taken="none",
                    message=decision.reason
                )
            
        except Exception as e:
            logger.error(f"Failed to process series '{series_title}': {e}")
            return SyncResult(
                series_id=series_id,
                series_title=series_title,
                success=False,
                action_taken="none",
                message=f"Processing failed: {e}",
                error=str(e)
            )

    def _check_series_availability(self, series: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Check series availability on configured streaming providers.
        
        Args:
            series: Series data from Sonarr
            
        Returns:
            Dictionary mapping provider names to availability data
        """
        try:
            return self.availability_checker.check_series_availability(series)
        except Exception as e:
            logger.warning(f"Failed to check availability for {series.get('title')}: {e}")
            # Return empty availability data on error
            return {provider.name: {"available": False, "seasons": []} 
                    for provider in self.config.streaming_providers}

    def _make_sync_decision(self, series: Dict[str, Any], availability: Dict[str, Dict[str, Any]]) -> SyncDecision:
        """Make decision about whether to sync a series.
        
        Args:
            series: Series data from Sonarr
            availability: Availability data from providers
            
        Returns:
            Sync decision
        """
        series_title = series.get("title", "Unknown")
        series_id = series.get("id")
        monitored_seasons = [s["seasonNumber"] for s in series.get("seasons", []) 
                           if s.get("monitored", False)]
        
        # Check each provider for availability
        available_providers = []
        for provider_name, provider_data in availability.items():
            if provider_data.get("available", False):
                available_seasons = set(provider_data.get("seasons", []))
                monitored_seasons_set = set(monitored_seasons)
                
                # Check if all monitored seasons are available
                if monitored_seasons_set.issubset(available_seasons):
                    available_providers.append({
                        "name": provider_name,
                        "seasons": sorted(available_seasons.intersection(monitored_seasons_set))
                    })
                else:
                    # Partial availability - log but don't include
                    missing_seasons = monitored_seasons_set - available_seasons
                    logger.debug(f"'{series_title}' partially available on {provider_name}, missing seasons: {sorted(missing_seasons)}")
        
        # Make decision based on availability
        if available_providers:
            # Use the first available provider
            provider = available_providers[0]
            seasons_str = ", ".join(map(str, provider["seasons"]))
            
            return SyncDecision(
                series_id=series_id,
                series_title=series_title,
                action=self.config.sync.action,
                should_process=True,
                reason=f"Available on {provider['name']} (seasons: {seasons_str})",
                provider=provider["name"],
                affected_seasons=provider["seasons"]
            )
        else:
            return SyncDecision(
                series_id=series_id,
                series_title=series_title,
                action=self.config.sync.action,
                should_process=False,
                reason="Not available on any configured streaming providers"
            )

    def _execute_sync_decision(self, decision: SyncDecision) -> SyncResult:
        """Execute a sync decision.
        
        Args:
            decision: Sync decision to execute
            
        Returns:
            Sync result
        """
        if self.config.sync.dry_run:
            # Dry run mode - just log what would happen
            action_verb = "delete" if decision.action == "delete" else "unmonitor"
            message = f"Would {action_verb} series '{decision.series_title}' ({decision.reason})"
            logger.info(f"DRY RUN: {message}")
            
            return SyncResult(
                series_id=decision.series_id,
                series_title=decision.series_title,
                success=True,
                action_taken="dry-run",
                message=message,
                provider=decision.provider
            )
        
        # Execute actual action
        try:
            if decision.action == "unmonitor":
                success = self.sonarr_client.unmonitor_series(decision.series_id)
                if success:
                    message = f"Unmonitored series '{decision.series_title}' ({decision.reason})"
                    logger.info(message)
                    return SyncResult(
                        series_id=decision.series_id,
                        series_title=decision.series_title,
                        success=True,
                        action_taken="unmonitor",
                        message=message,
                        provider=decision.provider
                    )
                else:
                    raise SyncError("Unmonitor operation returned failure")
                    
            elif decision.action == "delete":
                success = self.sonarr_client.delete_series(decision.series_id, delete_files=False)
                if success:
                    message = f"Deleted series '{decision.series_title}' ({decision.reason})"
                    logger.info(message)
                    return SyncResult(
                        series_id=decision.series_id,
                        series_title=decision.series_title,
                        success=True,
                        action_taken="delete",
                        message=message,
                        provider=decision.provider
                    )
                else:
                    raise SyncError("Delete operation returned failure")
            else:
                raise SyncError(f"Unknown action: {decision.action}")
                
        except Exception as e:
            error_msg = f"Failed to {decision.action} series '{decision.series_title}': {e}"
            logger.error(error_msg)
            return SyncResult(
                series_id=decision.series_id,
                series_title=decision.series_title,
                success=False,
                action_taken=decision.action,
                message=error_msg,
                provider=decision.provider,
                error=str(e)
            )

    def _get_sync_summary(self, results: List[SyncResult]) -> Dict[str, Any]:
        """Generate summary statistics from sync results.
        
        Args:
            results: List of sync results
            
        Returns:
            Summary statistics dictionary
        """
        summary = {
            "total_processed": len(results),
            "successful": len([r for r in results if r.success]),
            "failed": len([r for r in results if not r.success]),
            "actions": {},
            "providers": {}
        }
        
        # Count actions taken
        for result in results:
            action = result.action_taken
            summary["actions"][action] = summary["actions"].get(action, 0) + 1
        
        # Count by provider
        for result in results:
            if result.provider:
                provider = result.provider
                summary["providers"][provider] = summary["providers"].get(provider, 0) + 1
        
        return summary

    def test_connectivity(self) -> Dict[str, Any]:
        """Test connectivity to all external services.
        
        Returns:
            Dictionary with connectivity test results
        """
        results = {
            "sonarr": {"connected": False, "error": None},
            "providers": {"loaded": False, "count": 0, "error": None},
            "availability_checker": {"ready": False, "error": None}
        }
        
        # Test Sonarr connection
        try:
            self.sonarr_client.test_connection()
            results["sonarr"]["connected"] = True
        except Exception as e:
            results["sonarr"]["error"] = str(e)
        
        # Test provider manager
        try:
            providers = self.provider_manager.get_all_providers()
            results["providers"]["loaded"] = True
            results["providers"]["count"] = len(providers)
        except Exception as e:
            results["providers"]["error"] = str(e)
        
        # Test availability checker
        try:
            # Just check if it initializes properly
            results["availability_checker"]["ready"] = self.availability_checker is not None
        except Exception as e:
            results["availability_checker"]["error"] = str(e)
        
        return results