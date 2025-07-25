"""Command-line interface for excludarr."""

import asyncio
import click
from loguru import logger
from rich.console import Console
from rich.table import Table

from excludarr import __version__
from excludarr.config import ConfigManager
from excludarr.logging import setup_logging
from excludarr.providers import ProviderManager, ProviderError
from excludarr.sync import SyncEngine, SyncError


@click.group(invoke_without_command=True)
@click.option(
    "-v", "--verbose",
    count=True,
    help="Increase verbosity (-v, -vv, -vvv)"
)
@click.option(
    "--config",
    type=click.Path(exists=False),
    default="excludarr.yml",
    help="Path to configuration file",
    show_default=True
)
@click.version_option(version=__version__, prog_name="excludarr")
@click.pass_context
def cli(ctx, verbose, config):
    """Excludarr - Sync Sonarr with streaming services.
    
    Automatically unmonitor or delete TV shows and seasons from Sonarr
    when they are available on your configured streaming services.
    """
    # Set up logging based on verbosity
    setup_logging(verbose)
    
    # Store config path in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj['config'] = config
    ctx.obj['verbose'] = verbose
    
    # If no command is specified, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
def version():
    """Show version information."""
    click.echo(f"excludarr version {__version__}")
    logger.info(f"Excludarr version {__version__} started")


@cli.group()
@click.pass_context
def config(ctx):
    """Configuration management commands."""
    pass


@config.command("init")
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing configuration file"
)
@click.pass_context
def config_init(ctx, force):
    """Create example configuration file."""
    config_path = ctx.parent.obj['config']
    manager = ConfigManager(config_path)
    console = Console()
    
    try:
        if force and manager.config_path.exists():
            manager.config_path.unlink()
            console.print(f"[yellow]Removed existing config: {config_path}[/yellow]")
        
        manager.create_example_config()
        console.print(f"[green]✓ Example configuration created: {config_path}[/green]")
        console.print("\n[cyan]Next steps:[/cyan]")
        console.print("1. Edit the configuration file with your Sonarr details")
        console.print("2. Add your streaming provider subscriptions")
        console.print("3. Run 'excludarr config validate' to check your settings")
        
    except FileExistsError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("Use --force to overwrite the existing file")
        ctx.exit(1)
    except Exception as e:
        console.print(f"[red]Failed to create configuration: {e}[/red]")
        ctx.exit(1)


@config.command("validate")
@click.pass_context
def config_validate(ctx):
    """Validate configuration file."""
    config_path = ctx.parent.obj['config']
    manager = ConfigManager(config_path)
    console = Console()
    
    console.print(f"Validating configuration: {config_path}")
    
    is_valid, errors = manager.validate_config()
    
    if is_valid:
        console.print("[green]✓ Configuration is valid[/green]")
        
        # Show configuration summary
        try:
            config = manager.load_config()
            table = Table(title="Configuration Summary")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Sonarr URL", str(config.sonarr.url))
            table.add_row("Providers", str(len(config.streaming_providers)))
            table.add_row("Action", config.sync.action)
            table.add_row("Dry Run", str(config.sync.dry_run))
            
            console.print(table)
            
            # Show providers
            if config.streaming_providers:
                provider_table = Table(title="Streaming Providers")
                provider_table.add_column("Provider", style="cyan")
                provider_table.add_column("Country", style="yellow")
                
                for provider in config.streaming_providers:
                    provider_table.add_row(provider.name, provider.country)
                
                console.print(provider_table)
                
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load config details: {e}[/yellow]")
    else:
        console.print("[red]✗ Configuration validation failed[/red]")
        console.print("\n[red]Errors found:[/red]")
        for error in errors:
            console.print(f"  • {error}")
        ctx.exit(1)


@config.command("info")
@click.pass_context
def config_info(ctx):
    """Show configuration file information."""
    config_path = ctx.parent.obj['config']
    manager = ConfigManager(config_path)
    console = Console()
    
    info = manager.get_config_info()
    
    table = Table(title="Configuration Information")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Config Path", info["config_path"])
    table.add_row("Exists", "✓" if info["exists"] else "✗")
    table.add_row("Readable", "✓" if info["readable"] else "✗")
    table.add_row("Valid", "✓" if info["valid"] else "✗")
    
    if info["valid"]:
        table.add_row("Providers", str(info["providers_count"]))
        table.add_row("Action", info.get("action", "unknown"))
        table.add_row("Dry Run", str(info.get("dry_run", "unknown")))
    
    console.print(table)
    
    if info["errors"]:
        console.print("\n[red]Configuration Errors:[/red]")
        for error in info["errors"]:
            console.print(f"  • {error}")


@cli.group()
@click.pass_context
def providers(ctx):
    """Streaming provider management commands."""
    pass


@providers.command("list")
@click.option(
    "--country",
    help="Filter providers by country code (e.g., US, DE, UK)"
)
@click.option(
    "--search",
    help="Search providers by name"
)
@click.option(
    "--popular",
    is_flag=True,
    help="Show most popular providers"
)
@click.option(
    "--region",
    help="Show region-specific providers (US, EU, ASIA, OCEANIA, AMERICAS)"
)
def providers_list(country, search, popular, region):
    """List available streaming providers."""
    console = Console()
    
    try:
        manager = ProviderManager()
        
        if popular:
            # Show popular providers
            popular_providers = manager.get_popular_providers(limit=15)
            table = Table(title="Most Popular Streaming Providers")
            table.add_column("Provider", style="cyan")
            table.add_column("Display Name", style="green")
            table.add_column("Countries", style="yellow", justify="right")
            
            for provider in popular_providers:
                table.add_row(
                    provider["name"],
                    provider["display_name"],
                    str(provider["country_count"])
                )
            
            console.print(table)
            return
        
        if region:
            # Show region-specific providers
            regional_providers = manager.get_regional_providers(region)
            if not regional_providers:
                console.print(f"[yellow]No region-specific providers found for {region}[/yellow]")
                return
            
            table = Table(title=f"Region-Specific Providers ({region.upper()})")
            table.add_column("Provider", style="cyan")
            table.add_column("Display Name", style="green")
            table.add_column("Countries", style="yellow")
            
            for provider_name in regional_providers:
                provider_info = manager.get_provider_info(provider_name)
                countries = ", ".join(provider_info["countries"][:5])
                if len(provider_info["countries"]) > 5:
                    countries += f" (+ {len(provider_info['countries']) - 5} more)"
                
                table.add_row(
                    provider_name,
                    provider_info["display_name"],
                    countries
                )
            
            console.print(table)
            return
        
        if search:
            # Search providers
            results = manager.search_providers(search)
            if not results:
                console.print(f"[yellow]No providers found matching '{search}'[/yellow]")
                return
            
            table = Table(title=f"Search Results: '{search}'")
            table.add_column("Provider", style="cyan")
            table.add_column("Display Name", style="green")
            table.add_column("Countries", style="yellow", justify="right")
            
            for provider_name in results:
                provider_info = manager.get_provider_info(provider_name)
                table.add_row(
                    provider_name,
                    provider_info["display_name"],
                    str(len(provider_info["countries"]))
                )
            
            console.print(table)
            return
        
        if country:
            # Filter by country
            country_providers = manager.get_providers_by_country(country)
            if not country_providers:
                console.print(f"[yellow]No providers found for country {country}[/yellow]")
                return
            
            table = Table(title=f"Providers Available in {country.upper()}")
            table.add_column("Provider", style="cyan")
            table.add_column("Display Name", style="green")
            
            for provider_name in country_providers:
                provider_info = manager.get_provider_info(provider_name)
                table.add_row(provider_name, provider_info["display_name"])
            
            console.print(table)
            return
        
        # Show all providers
        all_providers = manager.get_all_providers()
        table = Table(title="All Streaming Providers")
        table.add_column("Provider", style="cyan")
        table.add_column("Display Name", style="green")
        table.add_column("Countries", style="yellow", justify="right")
        
        for provider_name, provider_data in sorted(all_providers.items()):
            table.add_row(
                provider_name,
                provider_data["display_name"],
                str(len(provider_data["countries"]))
            )
        
        console.print(table)
        
    except ProviderError as e:
        console.print(f"[red]Provider error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@providers.command("info")
@click.argument("provider_name")
def provider_info(provider_name):
    """Show detailed information about a specific provider."""
    console = Console()
    
    try:
        manager = ProviderManager()
        provider_info = manager.get_provider_info(provider_name)
        
        # Basic info
        table = Table(title=f"Provider Information: {provider_info['display_name']}")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Internal Name", provider_info["name"])
        table.add_row("Display Name", provider_info["display_name"])
        table.add_row("Total Countries", str(len(provider_info["countries"])))
        
        console.print(table)
        
        # Countries list
        countries = provider_info["countries"]
        if countries:
            countries_table = Table(title="Available Countries")
            
            # Split into columns for better display
            cols_per_row = 6
            countries_table.add_column("", style="yellow", width=3)
            for i in range(cols_per_row - 1):
                countries_table.add_column("", style="yellow", width=3)
            
            for i in range(0, len(countries), cols_per_row):
                row = countries[i:i + cols_per_row]
                # Pad row to match column count
                while len(row) < cols_per_row:
                    row.append("")
                countries_table.add_row(*row)
            
            console.print(countries_table)
        
    except ProviderError as e:
        console.print(f"[red]Provider error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@providers.command("stats")
def provider_stats():
    """Show provider statistics."""
    console = Console()
    
    try:
        manager = ProviderManager()
        stats = manager.get_provider_stats()
        
        # Overall stats
        table = Table(title="Provider Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")
        
        table.add_row("Total Providers", str(stats["total_providers"]))
        table.add_row("Total Countries", str(stats["total_countries"]))
        
        console.print(table)
        
        # Top countries by provider count
        providers_by_country = stats["providers_by_country"]
        sorted_countries = sorted(providers_by_country.items(), key=lambda x: x[1], reverse=True)
        
        top_countries_table = Table(title="Top Countries by Provider Count")
        top_countries_table.add_column("Country", style="cyan")
        top_countries_table.add_column("Providers", style="green", justify="right")
        
        for country, count in sorted_countries[:15]:  # Top 15
            top_countries_table.add_row(country, str(count))
        
        console.print(top_countries_table)
        
    except ProviderError as e:
        console.print(f"[red]Provider error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@providers.command("validate")
@click.argument("provider_name")
@click.argument("country_code")
def provider_validate(provider_name, country_code):
    """Validate a provider and country combination."""
    console = Console()
    
    try:
        manager = ProviderManager()
        is_valid, error = manager.validate_provider(provider_name, country_code)
        
        if is_valid:
            provider_info = manager.get_provider_info(provider_name)
            console.print(f"[green]✓ Valid: {provider_info['display_name']} is available in {country_code.upper()}[/green]")
        else:
            console.print(f"[red]✗ Invalid: {error}[/red]")
    
    except ProviderError as e:
        console.print(f"[red]Provider error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@cli.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview changes without applying them (overrides config setting)"
)
@click.option(
    "--action",
    type=click.Choice(["unmonitor", "delete"]),
    help="Action to take (overrides config setting)"
)
@click.option(
    "--confirm",
    is_flag=True,
    help="Skip confirmation prompts (for automation)"
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output results in JSON format (for automation/scripting)"
)
@click.pass_context
def sync(ctx, dry_run, action, confirm, json_output):
    """Sync Sonarr with streaming providers."""
    if json_output:
        # For JSON output, disable rich console to avoid ANSI codes
        console = Console(file=None, force_terminal=False)
        # Also suppress logging to avoid mixed output
        import logging
        logging.getLogger("excludarr").setLevel(logging.CRITICAL)
    else:
        console = Console()
    config_path = ctx.obj['config']
    
    try:
        # Load configuration
        config_manager = ConfigManager(config_path)
        config = config_manager.load_config()
        
        # Override config settings if provided
        if dry_run:
            config.sync.dry_run = True
        if action:
            config.sync.action = action
        
        # Show configuration summary (skip for JSON output)
        if not json_output:
            console.print("\n[cyan]Sync Configuration:[/cyan]")
            table = Table()
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Sonarr URL", str(config.sonarr.url))
            table.add_row("Action", config.sync.action)
            table.add_row("Dry Run", "Yes" if config.sync.dry_run else "No")
            table.add_row("Exclude Recent Days", str(config.sync.exclude_recent_days))
            table.add_row("Streaming Providers", str(len(config.streaming_providers)))
            
            console.print(table)
            
            # Show providers
            if config.streaming_providers:
                provider_table = Table(title="Configured Streaming Providers")
                provider_table.add_column("Provider", style="cyan")
                provider_table.add_column("Country", style="yellow")
                
                for provider in config.streaming_providers:
                    provider_table.add_row(provider.name, provider.country)
                
                console.print(provider_table)
        
        # Confirmation for non-dry-run operations
        if not config.sync.dry_run and not confirm:
            console.print(f"\n[yellow]⚠️  This will {config.sync.action} series from Sonarr![/yellow]")
            if not click.confirm("Are you sure you want to continue?"):
                console.print("[red]Sync cancelled by user[/red]")
                return
        
        # Initialize sync engine
        if not json_output:
            console.print("\n[cyan]Initializing sync engine...[/cyan]")
        sync_engine = SyncEngine(config)
        
        # Test connectivity
        if json_output:
            connectivity = sync_engine.test_connectivity()
        else:
            with console.status("[blue]Testing connectivity..."):
                connectivity = sync_engine.test_connectivity()
        
        # Check connectivity results
        if not connectivity["sonarr"]["connected"]:
            if json_output:
                error_output = {
                    "error": "sonarr_connection_failed",
                    "message": connectivity['sonarr']['error']
                }
                import json
                print(json.dumps(error_output))
            else:
                console.print(f"[red]✗ Sonarr connection failed: {connectivity['sonarr']['error']}[/red]")
            ctx.exit(1)
        
        if not connectivity["provider_manager"]["initialized"]:
            if json_output:
                error_output = {
                    "error": "provider_manager_failed",
                    "message": connectivity['provider_manager']['error']
                }
                import json
                print(json.dumps(error_output))
            else:
                console.print(f"[red]✗ Provider manager initialization failed: {connectivity['provider_manager']['error']}[/red]")
            ctx.exit(1)
        
        if not connectivity["cache"]["initialized"]:
            if json_output:
                error_output = {
                    "error": "cache_failed",
                    "message": connectivity['cache']['error']
                }
                import json
                print(json.dumps(error_output))
            else:
                console.print(f"[red]✗ Cache initialization failed: {connectivity['cache']['error']}[/red]")
            ctx.exit(1)
        
        if not json_output:
            console.print("[green]✓ All connectivity checks passed[/green]")
            console.print("\n[cyan]Starting sync operation...[/cyan]")
        
        # Run sync
        if json_output:
            results = asyncio.run(sync_engine.run_sync())
        else:
            with console.status("[blue]Syncing with streaming providers..."):
                results = asyncio.run(sync_engine.run_sync())
        
        # Display results
        if not results:
            if json_output:
                import json
                from datetime import datetime
                output = {
                    "timestamp": datetime.now().isoformat(),
                    "dry_run": config.sync.dry_run,
                    "action": config.sync.action,
                    "summary": {"total_processed": 0, "successful": 0, "failed": 0, "actions": {}, "providers": {}},
                    "results": []
                }
                print(json.dumps(output, indent=2))
            else:
                console.print("[yellow]No series processed during sync[/yellow]")
            return
        
        # Summary statistics
        summary = sync_engine._get_sync_summary(results)
        
        # JSON output mode for automation/scripting
        if json_output:
            import json
            from datetime import datetime
            
            # Convert results to JSON-serializable format
            json_results = []
            for result in results:
                json_results.append({
                    "series_id": result.series_id,
                    "series_title": result.series_title,
                    "success": result.success,
                    "action_taken": result.action_taken,
                    "message": result.message,
                    "provider": result.provider,
                    "error": result.error
                })
            
            output = {
                "timestamp": datetime.now().isoformat(),
                "dry_run": config.sync.dry_run,
                "action": config.sync.action,
                "summary": summary,
                "results": json_results
            }
            
            print(json.dumps(output, indent=2))
            return
        
        console.print(f"\n[green]✓ Sync completed![/green]")
        console.print(f"Processed: {summary['total_processed']}")
        console.print(f"Successful: {summary['successful']}")
        console.print(f"Failed: {summary['failed']}")
        
        # Show actions taken
        if summary['actions']:
            action_table = Table(title="Actions Taken")
            action_table.add_column("Action", style="cyan")
            action_table.add_column("Count", style="green", justify="right")
            
            for action_name, count in summary['actions'].items():
                action_table.add_row(action_name, str(count))
            
            console.print(action_table)
        
        # Show provider breakdown
        if summary['providers']:
            provider_table = Table(title="Provider Breakdown")
            provider_table.add_column("Provider", style="cyan")
            provider_table.add_column("Series", style="green", justify="right")
            
            for provider_name, count in summary['providers'].items():
                provider_table.add_row(provider_name, str(count))
            
            console.print(provider_table)
        
        # Show actions for dry-run or verbose mode
        verbose_level = ctx.obj.get('verbose', 0)
        show_details = verbose_level > 0 or config.sync.dry_run
        
        # Filter results that have actions to show
        actionable_results = [r for r in results if r.action_taken != "none"]
        
        if show_details and actionable_results:
            title = "Dry Run Actions" if config.sync.dry_run else "Detailed Results"
            console.print(f"\n[cyan]{title}:[/cyan]")
            result_table = Table()
            result_table.add_column("Series", style="cyan")
            result_table.add_column("Action", style="yellow")
            result_table.add_column("Reason", style="green")
            result_table.add_column("Provider", style="blue")
            
            for result in actionable_results:
                # Clean up the message for better display
                reason = result.message
                if "Would " in reason and "(" in reason:
                    # Extract reason from "Would unmonitor series 'Title' (reason)"
                    reason = reason.split("(", 1)[-1].rstrip(")")
                elif " series '" in reason and "(" in reason:
                    # Extract reason from "Unmonitored series 'Title' (reason)"
                    reason = reason.split("(", 1)[-1].rstrip(")")
                
                action_display = "Would " + result.action_taken.title() if config.sync.dry_run else result.action_taken.title()
                
                result_table.add_row(
                    result.series_title,
                    action_display,
                    reason,
                    result.provider or "N/A"
                )
            
            console.print(result_table)
        elif show_details and not actionable_results:
            if config.sync.dry_run:
                console.print("\n[green]No actions would be taken - all series are either not available on streaming services or were recently added.[/green]")
        
        # Show errors if any
        failed_results = [r for r in results if not r.success]
        if failed_results:
            console.print("\n[red]Errors encountered:[/red]")
            for result in failed_results:
                console.print(f"  • {result.series_title}: {result.message}")
        
    except FileNotFoundError:
        console.print(f"[red]Configuration file not found: {config_path}[/red]")
        console.print("Run 'excludarr config init' to create a configuration file")
        ctx.exit(1)
    except SyncError as e:
        console.print(f"[red]Sync failed: {e}[/red]")
        ctx.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        logger.exception("Unexpected error during sync")
        ctx.exit(1)


if __name__ == "__main__":
    cli()