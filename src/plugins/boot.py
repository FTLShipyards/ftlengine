import sys
import click

from .base import BasePlugin
from ..cli.colors import RED
from ..cli.tasks import Task
from ..constants import PluginHook
from ..docker.introspect import FormationIntrospector
from ..docker.runner import FormationRunner
from ..exceptions import BadConfigError, ImageNotFoundException


class BootPlugin(BasePlugin):
    """
    Plugin for running certain containers at boot.

    Containers should have a 'boot:' config key with 'build' and 'run' sub keys
    listing the containers to boot before the build or run phase, respectively,
    and if they need them (required) or can use them if available (optional):

    boot:
        build:
            apt-cacher: optional
            ssh-agent: required
        run:
            ssh-agent: required

    These values are inherited from build parents.
    """

    provides = ['boot-containers']

    def load(self):
        self.add_hook(PluginHook.PRE_BUILD, self.pre_build)
        self.add_hook(PluginHook.PRE_RUN_CONTAINER, self.pre_start)

    def pre_build(self, host, container, task):
        boot_containers = self.calculate_boot_containers('build', container)
        self.run_boot_containers(host, boot_containers, task)

    def pre_start(self, host, instance, task):
        boot_containers = self.calculate_boot_containers('run', instance.container)
        self.run_boot_containers(host, boot_containers, task)

    def calculate_boot_containers(self, phase, container):
        """
        Given a Container object and phase being 'build' or 'run',
        calculates all boot containers needed based on build parents.
        Returns a dict of {container: required}
        """
        configs = container.get_ancestral_extra_data('boot')
        boot_container_names = {}
        for config in configs:
            for name, required in config.get(phase, {}).items():
                required = required.lower().strip() == 'required'
                # Any required value overrides a previous optional value
                boot_container_names[name] = required or boot_container_names.get(name, False)
        # Translate the names into container objects
        try:
            boot_containers = {
                self.app.containers[name]: required
                for name, required in boot_container_names.items()
            }
        except KeyError as e:
            raise BadConfigError('Invalid boot container specification: {}'.format(e))
        # Check none of them are circular dependencies
        ancestry = self.app.containers.build_ancestry(container) + [container]
        for boot_container, required in boot_containers.items():
            if boot_container in ancestry and required:
                raise BadConfigError(
                    'Container {} has a boot container of {}, which is in its own build ancestry'.format(
                        container.name,
                        boot_container.name,
                    )
                )
        return boot_containers

    def run_boot_containers(self, host, containers, task):
        """
        Takes a dict of {container: required} and makes sure they're all running
        )required ones must be or an error is raised; optional ones are if they
        are available locally).
        """
        formation = FormationIntrospector(host, self.app.containers).introspect()
        to_boot = set()
        for container, required in containers.items():
            # See if container is already running
            if any(instance.container == container for instance in formation):
                continue
            # See if it can be started (use a runner just for missing image - maybe imporove this)
            try:
                formation.add_container(container, host)
            except ImageNotFoundException:
                if required:
                    click.echo(RED('Cannot launch required boot container {} - no image'.format(container.name)))
                    sys.exit(1)
            else:
                to_boot.add(container)
        # Boot those containers
        if to_boot:
            boot_task = Task('Running boot containers', parent=task)
            formation = FormationIntrospector(host, self.app.containers).introspect()
            for container in to_boot:
                formation.add_container(container, host)
            runner = FormationRunner(self.app, host, formation, boot_task, stop=False)
            runner.run()
            boot_task.finish(status='Done', status_flavor=Task.FLAVOR_GOOD)
