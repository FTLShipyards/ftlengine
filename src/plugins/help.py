import click
import sys

from .base import BasePlugin
from ..cli.colors import RED


class HelpPlugin(BasePlugin):
    """
    Just makes "ftl help" show the help
    """

    def load(self):
        self.add_command(help)


@click.command()
@click.argument("command_name", default=None, required=False)
@click.pass_context
def help(ctx, command_name):
    """
    Shows main command list.
    """
    from ..cli import cli
    # Find subcommand
    if command_name:
        subcommand = cli.get_command(None, command_name)
        if subcommand is None:
            click.echo(RED('There is no command {}'.format(command_name)))
            sys.exit(1)
        else:
            # Override info name so help prints correctly
            ctx.info_name = subcommand.name
            click.echo(subcommand.get_help(ctx))
        # Print main help
    else:
        ctx.info_name = 'ftl'
        ctx.parent = None
        click.echo(cli.get_help(ctx))
