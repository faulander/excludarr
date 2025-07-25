"""Command-line interface for excludarr."""

import click
from loguru import logger
from rich.console import Console
from rich.table import Table

from excludarr import __version__
from excludarr.config import ConfigManager
from excludarr.logging import setup_logging


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


if __name__ == "__main__":
    cli()