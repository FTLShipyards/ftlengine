import click
import os
import yaml

from .base import BasePlugin
from ..cli.colors import YELLOW


class CreatePlugin(BasePlugin):
    """
    Provides the FTL command `init`
    """

    requires = ['chart']

    provides = ['create']

    def load(self):
        self.add_command(create)


@click.group()
def create():
    """
    Creates a new FTL project.
    """
    pass


@create.command()
@click.argument(
    'name',
    required=True,
)
@click.argument(
    'file_path',
    required=True,
    type=click.Path(
        dir_okay=True,
        writable=True,
        resolve_path=True,
    ),
    default='.',
)
@click.option(
    '-V',
    '--verbose',
    count=True,
    required=False,
    default=None,
)
@click.pass_context
def project(ctx, name, file_path, verbose):
    """
    Creates a new FTL project
    """
    if verbose:
        click.echo(YELLOW(f'<-->\nname:{name}\nfile_path:{file_path}\n<-->'))
    proj_path_root = os.path.join(file_path, name)
    click.echo(f'proj_path_root:{proj_path_root}')
    try:
        os.makedirs(proj_path_root)
        proj_path_ftl = os.path.join(proj_path_root, '.ftl')
        os.makedirs(proj_path_ftl)
        with open(os.path.join(proj_path_ftl, 'ftl.yaml'), 'w') as fh:
            data = {"prefix": f'{name}'}
            yaml.safe_dump(data, fh, default_flow_style=False, indent=4)
    except OSError:
        pass
