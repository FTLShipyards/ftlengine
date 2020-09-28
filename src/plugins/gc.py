import attr
import click
import subprocess

from .base import BasePlugin
from ..cli.argument_types import HostType
from ..cli.tasks import Task
from ..cli.colors import YELLOW


@attr.s
class GcPlugin(BasePlugin):
    """
    Does garbage collection on demand.
    """

    provides = ['gc']

    def load(self):
        self.add_command(gc)


@attr.s
class GarbageCollector:
    """
    Allows garbage collection on a host.
    """

    host = attr.ib()

    def gc_all(self, parent_task):
        task = Task('Running garbage collection', parent=parent_task)
        click.echo(YELLOW('INFO: Run ftl up first if you don\'t want to remove all your containers.'))
        try:
            subprocess.check_call(['docker', 'system', 'prune'])
            task.finish(status='Done', status_flavor=Task.FLAVOR_GOOD)
        except subprocess.CalledProcessError as err:
            task.finish(status='Error while removing unused data: {}'.format(err), status_flavor=Task.FLAVOR_BAD)

    def gc_containers(self, parent_task):
        """
        Remove all stopped containers
        """
        task = Task('Removeing all stopped containers', parent=parent_task)
        response = self.host.client.prune_containers()
        task.finish(status='Done, reclaimed {:.1f} MB'.format(
            response['SpaceReclaimed'] / 1024 / 1024), status_flavor=Task.FLAVOR_GOOD
        )


@click.command()
@click.option('--host', '-h', type=HostType(), default='default')
@click.pass_obj
def gc(app, host):
    """
    Runs the garbage collection manually.
    """
    GarbageCollector(host).gc_all(app.root_task)
