"""Core sync logic for excludarr."""

import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

from loguru import logger

from excludarr.models import Config
from excludarr.sonarr import SonarrClient, SonarrError
from excludarr.provider_manager import ProviderManager
from excludarr.simple_cache import TMDBCache


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
    scope: str = "series"  # "series" or "seasons"


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
        cache: Optional[TMDBCache] = None
    ):
        """Initialize sync engine.
        
        Args:
            config: Application configuration
            sonarr_client: Sonarr API client (optional for testing)
            provider_manager: Provider manager (optional for testing)
            cache: TMDB cache instance (optional for testing)
        """
        self.config = config
        
        # Initialize cache
        self.cache = cache or TMDBCache(provider_data_ttl=config.provider_apis.tmdb.cache_ttl)
        
        # Initialize clients
        self.sonarr_client = sonarr_client or SonarrClient(config.sonarr)
        self.provider_manager = provider_manager or ProviderManager(
            config.provider_apis, 
            cache=self.cache
        )
        
        # Extract user provider names and countries for filtering
        self.user_providers = [p.name for p in config.streaming_providers]
        self.user_countries = list(set(p.country for p in config.streaming_providers))
        
        logger.info(f"Sync engine initialized with {len(self.user_providers)} providers in {len(self.user_countries)} countries")

    async def run_sync(self, progress_callback=None) -> List[SyncResult]:
        """Run complete sync operation.
        
        Args:
            progress_callback: Optional callback function(current, total, series_title)
        
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
            total_series = len(eligible_series)
            for i, series in enumerate(eligible_series, 1):
                series_title = series.get('title', 'Unknown')
                
                # Update progress if callback provided
                if progress_callback:
                    progress_callback(i, total_series, series_title)
                
                try:
                    result = await self._process_series(series)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Failed to process series {series_title}: {e}")
                    results.append(SyncResult(
                        series_id=series.get("id", 0),
                        series_title=series_title,
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

    async def _process_series(self, series: Dict[str, Any]) -> Optional[SyncResult]:
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
            availability = await self._check_series_availability(series)
            
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

    async def _check_series_availability(self, series: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Check series availability on configured streaming providers.
        
        Args:
            series: Series data from Sonarr
            
        Returns:
            Dictionary mapping provider names to availability data
        """
        try:
            # Get IMDb ID from series
            imdb_id = series.get('imdbId')
            if not imdb_id:
                logger.warning(f"No IMDb ID found for series {series.get('title')}")
                return {provider.name: {"available": False, "seasons": []} 
                        for provider in self.config.streaming_providers}
            
            # Get availability from provider manager
            availability_data = await self.provider_manager.get_series_availability(
                imdb_id, 
                self.user_countries
            )
            
            # Filter by user's providers
            user_availability = self.provider_manager.filter_by_user_providers(
                availability_data, 
                self.user_providers
            )
            
            # Convert to expected format for sync logic
            result = {}
            for provider in self.config.streaming_providers:
                country_available = user_availability.get(provider.country, False)
                result[provider.name] = {
                    "available": country_available,
                    "seasons": [],  # Season-level data not yet implemented
                    "country": provider.country,
                    "source": "multi-provider"
                }
            
            return result
            
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
        
        # Check each provider for availability - with fallback to series-level when no season data
        best_match = None
        max_available_seasons = 0
        
        for provider_name, provider_data in availability.items():
            if provider_data.get("available", False):
                available_seasons = set(provider_data.get("seasons", []))
                monitored_seasons_set = set(monitored_seasons)
                
                # Handle different scenarios:
                # 1. No season data available -> treat as series-level availability
                # 2. No monitored seasons -> treat as series-level (legacy behavior)
                # 3. Season data available -> use season-level matching
                
                if not available_seasons and not monitored_seasons_set:
                    # Fallback to series-level: no season info available from either side
                    matching_seasons = set([1])  # Assume season 1 for compatibility
                    total_monitored = 1
                    logger.debug(f"'{series_title}' using series-level logic (no season data)")
                elif not monitored_seasons_set:
                    # Series is monitored but no seasons are monitored - treat as series level
                    matching_seasons = set([1])  # Assume season 1 for compatibility
                    total_monitored = 1
                    logger.debug(f"'{series_title}' using series-level logic (no monitored seasons)")
                else:
                    # Use season-level matching when both sides have season data
                    matching_seasons = available_seasons.intersection(monitored_seasons_set)
                    total_monitored = len(monitored_seasons_set)
                
                if matching_seasons:
                    # Keep the provider with the most matching seasons
                    if len(matching_seasons) > max_available_seasons:
                        max_available_seasons = len(matching_seasons)
                        best_match = {
                            "name": provider_name,
                            "seasons": sorted(matching_seasons),
                            "total_monitored": total_monitored,
                            "coverage_percent": len(matching_seasons) / total_monitored * 100
                        }
                    
                    # Log partial availability for visibility (only for true season-level)
                    if available_seasons and monitored_seasons_set and matching_seasons != monitored_seasons_set:
                        missing_seasons = monitored_seasons_set - available_seasons
                        logger.info(f"'{series_title}' partially available on {provider_name}: "
                                  f"available seasons {sorted(matching_seasons)}, "
                                  f"missing seasons {sorted(missing_seasons)}")
        
        # Make decision based on availability
        if best_match:
            seasons_str = ", ".join(map(str, best_match["seasons"]))
            action_type = "delete" if self.config.sync.action == "delete" else "unmonitor"
            
            # Determine action scope based on season availability
            if len(best_match["seasons"]) == best_match["total_monitored"]:
                # All seasons available - can delete/unmonitor entire series
                scope = "series"
                reason = f"All seasons available on {best_match['name']}"
            else:
                # Partial availability - only unmonitor available seasons (no deletion for partial)
                if self.config.sync.action == "delete":
                    action_type = "unmonitor"  # Force to unmonitor for partial matches
                scope = "seasons"
                reason = f"Seasons {seasons_str} available on {best_match['name']}"
            
            return SyncDecision(
                series_id=series_id,
                series_title=series_title,
                action=action_type,
                should_process=True,
                reason=reason,
                provider=best_match["name"],
                affected_seasons=best_match["seasons"],
                scope=scope  # "series" or "seasons"
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
            
            if decision.scope == "seasons" and decision.affected_seasons:
                seasons_str = ", ".join(map(str, decision.affected_seasons))
                target = f"seasons {seasons_str} of series"
            else:
                target = "series"
            
            message = f"Would {action_verb} {target} '{decision.series_title}' ({decision.reason})"
            logger.info(f"DRY RUN: {message}")
            
            return SyncResult(
                series_id=decision.series_id,
                series_title=decision.series_title,
                success=True,
                action_taken=decision.action,
                message=message,
                provider=decision.provider
            )
        
        # Execute actual action
        try:
            if decision.action == "unmonitor":
                if decision.scope == "seasons" and decision.affected_seasons:
                    # Unmonitor specific seasons
                    success_count = 0
                    for season_num in decision.affected_seasons:
                        try:
                            success = self.sonarr_client.unmonitor_season(decision.series_id, season_num)
                            if success:
                                success_count += 1
                                logger.info(f"Unmonitored season {season_num} of series '{decision.series_title}'")
                        except Exception as e:
                            logger.error(f"Failed to unmonitor season {season_num} of series '{decision.series_title}': {e}")
                    
                    if success_count > 0:
                        seasons_str = ", ".join(map(str, decision.affected_seasons[:success_count]))
                        message = f"Unmonitored seasons {seasons_str} of series '{decision.series_title}' ({decision.reason})"
                        return SyncResult(
                            series_id=decision.series_id,
                            series_title=decision.series_title,
                            success=True,
                            action_taken="unmonitor",
                            message=message,
                            provider=decision.provider
                        )
                    else:
                        raise SyncError("Failed to unmonitor any seasons")
                else:
                    # Unmonitor entire series
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
                if decision.scope == "seasons" and decision.affected_seasons:
                    # Delete specific seasons
                    success_count = 0
                    for season_num in decision.affected_seasons:
                        try:
                            success = self.sonarr_client.unmonitor_and_delete_season(decision.series_id, season_num)
                            if success:
                                success_count += 1
                                logger.info(f"Deleted season {season_num} of series '{decision.series_title}'")
                        except Exception as e:
                            logger.error(f"Failed to delete season {season_num} of series '{decision.series_title}': {e}")
                    
                    if success_count > 0:
                        seasons_str = ", ".join(map(str, decision.affected_seasons[:success_count]))
                        message = f"Deleted seasons {seasons_str} of series '{decision.series_title}' ({decision.reason})"
                        return SyncResult(
                            series_id=decision.series_id,
                            series_title=decision.series_title,
                            success=True,
                            action_taken="delete",
                            message=message,
                            provider=decision.provider
                        )
                    else:
                        raise SyncError("Failed to delete any seasons")
                else:
                    # Delete entire series
                    success = self.sonarr_client.delete_series(decision.series_id, delete_files=True)
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
            "provider_manager": {"initialized": False, "providers": 0, "error": None},
            "cache": {"initialized": False, "error": None}
        }
        
        # Test Sonarr connection
        try:
            self.sonarr_client.test_connection()
            results["sonarr"]["connected"] = True
        except Exception as e:
            results["sonarr"]["error"] = str(e)
        
        # Test provider manager
        try:
            quota_status = self.provider_manager.get_quota_status()
            results["provider_manager"]["initialized"] = True
            results["provider_manager"]["providers"] = len(quota_status)
        except Exception as e:
            results["provider_manager"]["error"] = str(e)
        
        # Test cache
        try:
            # Just check if cache is initialized
            stats = self.cache.get_statistics()
            results["cache"]["initialized"] = True
        except Exception as e:
            results["cache"]["error"] = str(e)
        
        return results