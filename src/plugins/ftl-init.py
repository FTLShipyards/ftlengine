import click
# import os

from .base import BasePlugin
from ..cli.colors import YELLOW


class FtlInitPlugin(BasePlugin):
    """
    Provides the FTL command `init`
    """

    requires = ['chart']

    provides = ['init']

    def load(self):
        self.add_command(init)


@click.group()
def init():
    """
    Creates a new FTL project.
    """
    pass


@init.command()
@click.argument('file_path', required=True)
@click.option('-V', '--verbose', count=True, required=False, default=None)
@click.pass_obj
def project(app, file_path, verbose):
    """
    Creates a new FTL project
    """
    if verbose:
        click.echo(YELLOW(f'<--\nfile_path:{file_path}\n-->'))
