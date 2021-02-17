import attr
import click
import os

from .base import BasePlugin
from ..cli.argument_types import HostType
from ..cli.colors import CYAN, YELLOW, BOLD, RED
from ..cli.table import Table
from ..docker.introspect import FormationIntrospector
from ..utils import humanize


@attr.s
class PsPlugin(BasePlugin):
    """
    Plugin to see what's running right now.
    """

    requires = ['profile', 'mounts']

    provides = ['ps', 'status']

    def load(self):
        self.add_command(ps)
        self.add_command(status)


@click.command()
@click.option("--host", "-h", type=HostType(), default="default")
@click.option("--stats/--no-stats", "-s")
@click.pass_obj
def ps(app, host, stats):
    """
    Shows details about all containers currently running
    """
    app.print_chart()
    # Run the introspector to get the details
    formation = FormationIntrospector(host, app.containers).introspect()
    # Print formation details
    if stats:
        table = Table([
            ("NAME", 30),
            ("DOCKER NAME", 40),
            ("MEMORY", 10),
            ("PORTS (CONTAINER->HOST)", 30),
        ])
    else:
        table = Table([
            ("NAME", 30),
            ("DOCKER NAME", 40),
            ("PORTS (CONTAINER->HOST)", 30),
        ])
    table.print_header()
    for instance in sorted(formation, key=lambda i: i.name):
        row = [
            instance.container.name,
            instance.name,
        ]
        if stats:
            # Get the memory usage from the docker host
            stats = host.client.stats(instance.name, decode=True, stream=False)
            row.append(humanize.file_size(stats['memory_stats']['usage']))
        # Add in port info
        row.append(", ".join(
            "{}->{}".format(private, public)
            for private, public in instance.port_mapping.items()
        ))
        table.print_row(row)


@click.command()
@click.option('-V', '--verbose', count=True, required=False, default=None)
@click.pass_obj
def status(app, verbose):
    """
    Chains the profile mounts ps commands
    """
    app.invoke('profile')
    app.invoke('mounts')
    app.invoke('ps')
    if 'AWS_PROFILE' in os.environ:
        env_profile = os.getenv('AWS_PROFILE', 'default')
        click.echo(CYAN(f'eval AWS_PROFILE: {YELLOW(BOLD(env_profile))}'))
    else:
        click.echo(CYAN(f'eval AWS_PROFILE: {RED(BOLD("NOT SET"))}'))
