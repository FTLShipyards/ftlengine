import attr
import click
import sys

from .base import BasePlugin
from ..cli.argument_types import HostType, ContainerType
from ..cli.colors import (
    RED,
    YELLOW,
)
from ..exceptions import (
    BadConfigError,
    RegistryRequiresLogin,
)


@attr.s
class RegistryPlugin(BasePlugin):
    """
    Plugin for fetching and uploading images
    """

    def load(self):
        self.add_command(registry)
        self.add_command(push)


@click.group()
def registry():
    """
    Allows operations on registries.
    """
    pass


@registry.command()
@click.option("--host", "-h", type=HostType(), default="default")
@click.pass_obj
def status(app, host):
    """
    Gives registry status
    """
    app.print_chart()
    registry_instance = host.images.get_registry(app)
    if registry_instance is None:
        click.echo("No registry is configured on this project.")
        return
    try:
        url = registry_instance.url(host)
    except RegistryRequiresLogin:
        click.echo("Registry requires login. Run `ftl registry login` to do so.")
    else:
        click.echo("Registry configured, docker URL: %s" % url)


@registry.command()
@click.option("--host", "-h", type=HostType(), default="default")
@click.pass_obj
def login(app, host):
    """
    Logs into a registry
    """
    app.print_chart()
    try:
        registry_instance = host.images.get_registry(app)
        registry_instance.login(host, app.root_task)
    except BadConfigError as e:
        click.echo(RED(str(e)))
        sys.exit(1)
    except Exception as e:
        click.echo(RED(str(e)))
        click.echo(YELLOW('Missing the property "registry" from project/ftl.yaml'))
        sys.exit(1)


@click.command()
@click.option("--host", "-h", type=HostType(), default="default")
@click.argument("container", type=ContainerType())
@click.argument("tag")
@click.pass_obj
def push(app, host, container, tag):
    """
    Pushes an image up to a registry
    """
    app.print_chart()
    host.images.push_image_version(app, container.image_name, tag, app.root_task)
