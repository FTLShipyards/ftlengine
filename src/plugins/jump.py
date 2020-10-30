import attr
import click

from .base import BasePlugin


@attr.s
class JumpPlugin(BasePlugin):
    """
    Plugin for rebuild + restart commands
    """

    requires = ['build', 'stop', 'up']

    provides = ['jump']

    def load(self):
        self.add_command(jump)


@click.command()
@click.pass_obj
def jump(app):
    """
    Rebuild and restart profile
    """
    # app.print_chart()
    app.invoke('stop')
    # click.echo('Building...')
    app.invoke('build')
    # click.echo('Restarting...')
    app.invoke('up')
