import attr
import click
import sys

from .base import BasePlugin
from .gc import GarbageCollector
from ..cli.argument_types import HostType, ContainerType
from ..cli.colors import RED
from ..cli.table import Table
from ..cli.tasks import Task


@attr.s
class ImagesPlugin(BasePlugin):
    """
    Plugin for listing and destroying container images
    """

    requires = ["gc"]

    def load(self):
        self.add_command(image)


@click.group()
def image():
    """
    Allows operations on images.
    """
    pass


@image.command()
@click.option("--host", "-h", type=HostType(), default="default")
@click.pass_context
def list(ctx, host):
    """
    Lists available images _for containers_
    """
    if not ctx.invoked_subcommand:
        # Start a table
        table = Table([
            ("CONTAINER", 40),
            ("VERSION", 15),
            ("IMAGE", 50),
        ])
        table.print_header()
        # Iterate through docker containers and try to get their images
        for container in sorted(ctx.obj.containers, key=lambda c: c.name):
            versions = host.images.image_versions(container.image_name)
            for version, image_id in sorted(versions.items()):
                table.print_row([
                    container.name,
                    version,
                    image_id,
                ])


@image.command()
@click.option("--host", "-h", type=HostType(), default="default")
@click.option("--force", "-f", type=bool, default=False)
@click.argument("container", type=ContainerType())
@click.argument("version", default="latest")
@click.pass_obj
def destroy(app, host, container, version, force):
    """
    Removes an image for a container
    """
    # Check the version
    image_versions = host.images.image_versions(container.image_name)
    if version not in image_versions:
        click.echo(RED("There is no version '{} of {}".format(version, container.name)))
        sys.exit(1)
    # Run garbage collection on containers
    task = Task("Destroying {}:{}".format(container.image_name, version))
    garbage_collector = GarbageCollector(host)
    garbage_collector.gc_containers(task)
    # Destroy it
    host.client.remove_image(image_versions[version], force=force)
    task.finish(status="Done", status_flavor=Task.FLAVOR_GOOD)
