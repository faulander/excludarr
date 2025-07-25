"""Command-line interface for excludarr."""

import click
from loguru import logger

from excludarr import __version__
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


if __name__ == "__main__":
    cli()