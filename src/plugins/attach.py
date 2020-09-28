import attr
import click
import os
import subprocess
import sys

from .base import BasePlugin
from ..cli.argument_types import ContainerType, HostType
from ..cli.colors import RED
from ..docker.introspect import FormationIntrospector


@attr.s
class AttachPlugin(BasePlugin):
    """
    Plugin for attaching into a running container
    """

    provides = ['attach']

    def load(self):
        self.add_command(attach)


@click.command()
@click.argument('container', type=ContainerType(all=True))
@click.option('--host', '-h', type=HostType(), default='default')
@click.option('--shell', '-s', 'shell_path', default='/bin/bash')
@click.option('--notty/--tty', '-t', default=False)
@click.argument('command', nargs=-1, default=None)
@click.pass_obj
def attach(app, container, host, command, shell_path, notty):
    """
    Attaches to a container
    """
    if command:
        shell = [shell_path, '-lc', ' '.join(command)]
    else:
        shell = [shell_path]
    # see if the container is running
    formation = FormationIntrospector(host, app.containers).introspect()
    for instance in formation:
        if instance.container == container:
            # Work out anything to put before the shell (e.g., ENV)
            pre_args = []
            if os.environ.get('TERM', None):
                pre_args = ['env', 'TERM=%s' % os.environ['TERM']]
            # Launch into an attached shell
            if notty:
                status_code = subprocess.call(['docker', 'exec', instance.name] + pre_args + shell)
            else:
                status_code = subprocess.call(['docker', 'exec', '-it', instance.name] + pre_args + shell)
            sys.exit(status_code)
    # It's not running ;(
    click.echo(RED('Container {name} is not running. It must be started to attach - try `ftl run {name}`.'.format(
        name=container.name,
    )))
