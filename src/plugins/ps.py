import attr
import click

from .base import BasePlugin
from ..cli.argument_types import HostType
from ..cli.table import Table
from ..docker.introspect import FormationIntrospector
from ..utils import humanize


@attr.s
class PsPlugin(BasePlugin):
    """
    Plugin to see what's running right now.
    """

    def load(self):
        self.add_command(ps)


@click.command()
@click.option("--host", "-h", type=HostType(), default="default")
@click.option("--stats/--no-stats", "-s")
@click.pass_obj
def ps(app, host, stats):
    """
    Shows details about all containers currently running
    """
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
