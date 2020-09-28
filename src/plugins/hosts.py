import attr
import click

from .base import BasePlugin
from ..cli.table import Table
from ..cli.colors import yesno


@attr.s
class HostsPlugin(BasePlugin):
    """
    Plugin for showing information about the current Docker hosts the system
    has
    """

    def load(self):
        self.add_command(hosts)


@click.command()
@click.pass_obj
def hosts(app):
    """
    Lists available hosts
    """
    # Start a table
    table = Table([
        ('ALIAS', 30),
        ('URL', 50),
        ('visible', 10),
    ])
    table.print_header()
    # Iterate through docker hosts and ping to see if they're accessible
    for host in app.hosts:
        visible = host.client.ping()
        table.print_row([
            host.alias,
            host.url,
            yesno(visible),
        ])
