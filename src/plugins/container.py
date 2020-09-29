import attr
import click

from .base import BasePlugin
from ..cli.argument_types import ContainerType
from ..cli.colors import CYAN
from ..cli.table import Table


@attr.s
class ContainerPlugin(BasePlugin):
    """
    Plugin for showing informaiton about containers
    """

    def load(self):
        self.add_command(container)


@click.command()
@click.argument('container', type=ContainerType(), required=False)
@click.pass_obj
def container(app, container=None):
    """
    Shows details on containers
    """
    if container is None:
        # Print containers
        table = Table([
            ('NAME', 30),
        ])
        table.print_header()
        for container in sorted(app.containers, key=lambda c: c.name):
            table.print_row([
                container.name,
            ])
    else:
        # Container name
        click.echo(CYAN("Name: ") + container.name)
        # Build parent
        click.echo(
            CYAN("Build ancestry: ") +
            ", ".join(other.name for other in app.containers.build_ancestry(container))
        )
        # Runtime dependencies
        dependencies = app.containers.dependencies(container)
        if dependencies:
            click.echo(CYAN("Depends on: ") + ", ".join(sorted(other.name for other in dependencies)))
        else:
            click.echo(CYAN("Depends on: ") + "(nothing)")
        # Dependents
        dependents = app.containers.dependents(container)
        if dependents:
            click.echo(CYAN("Depended on by: ") + ", ".join(sorted(other.name for other in dependents)))
        else:
            click.echo(CYAN("Depended on by: ") + "(nothing)")
        # Volumes
        click.echo(CYAN("Named volumes:"))
        for mount_point, volume in container.named_volumes.items():
            click.echo("  {}: {}".format(mount_point, volume.source))
        click.echo(CYAN("Bind-mounted volumes:"))
        for mount_point, volume in container.bound_volumes.items():
            click.echo("  {}: {}".format(mount_point, volume.source))
        # Devmodes
        click.echo(CYAN("Mounts (devmodes):"))
        for name, mounts in container.devmodes.items():
            click.echo("  {}:".format(name))
            for mount_point, volume in mounts.items():
                click.echo("    {}: {}".format(mount_point, volume.source))
