import attr
import click
import sys

from .base import BasePlugin
from ..cli.argument_types import ContainerType, HostType
from ..cli.colors import CYAN, RED
from ..cli.tasks import Task
from ..constants import PluginHook
from ..docker.introspect import FormationIntrospector
from ..docker.runner import FormationRunner
from ..exceptions import DockerRuntimeError, ImageNotFoundException


@attr.s
class RunPlugin(BasePlugin):
    """
    Plugin for running containers.
    """

    provides = ['stop', 'start']

    requires = ["tail"]

    def load(self):
        self.add_command(run)
        self.add_alias(run, "start")
        self.add_command(shell)
        self.add_command(stop)
        self.add_command(restart)
        self.add_alias(restart, "hup")
        self.add_alias(restart, "reload")


@click.command()
@click.argument("containers", type=ContainerType(), nargs=-1)
@click.option("--host", "-h", type=HostType(), default="default")
@click.option("--tail/--notail", "-t", default=False)
@click.pass_obj
def run(app, containers, host, tail):
    """
    Runs containers by name, including any dependencies needed
    """
    app.print_chart()
    profile = app.profiles[1] if app.profiles and len(app.profiles) > 1 else None
    ignore_dependencies = profile.ignore_dependencies if profile else False
    # Get the current formation
    formation = FormationIntrospector(host, app.containers).introspect()
    # Make a Formation that represents what we want to do by taking the existing
    # state and adding in the containers we want
    for container in containers:
        try:
            formation.add_container(container, host, ignore_dependencies)
        except ImageNotFoundException as e:
            # If it's the container we're trying to add directly, have one error -
            # otherwise, say it's a link
            if e.image == container.image_name:
                click.echo(RED(
                    "This container ({name}) does not have a built image. Try `ftl build {name}` first.".format(
                        name=container.name,
                    )
                ))
                sys.exit(1)
            elif hasattr(e, "container"):
                click.echo(RED("No image for linked container {name} - try `ftl build {name}` first.".format(
                    name=e.container.name,
                )))
                sys.exit(1)
            else:
                click.echo(RED("No image for linked container %s!" % e.image))
                sys.exit(1)
    # Run that change
    task = Task("Starting containers", parent=app.root_task)
    run_formation(app, host, formation, task, containers)
    # If they asked to tail, then run tail
    if tail:
        if len(containers) != 1:
            click.echo(RED("You cannot tail more than one container!"))
            sys.exit(1)
        app.invoke("tail", host=host, container=containers[0], follow=True)


@click.command()
@click.argument("container", type=ContainerType())
@click.option("--host", "-h", type=HostType(), default="default")
@click.option("--shell", "-s", "shell_path", default="/bin/bash")
@click.argument("command", nargs=-1, default=None)
@click.pass_obj
def shell(app, container, host, command, shell_path):
    """
    Runs a single container with foreground enabled and overridden to use bash.
    """
    app.print_chart()
    profile = app.profiles[1] if app.profiles and len(app.profiles) > 1 else None
    ignore_dependencies = profile.ignore_dependencies if profile else False
    # Get the current formation
    formation = FormationIntrospector(host, app.containers).introspect()
    # Make a Formation with that container launched with bash in foreground
    try:
        instance = formation.add_container(container, host, ignore_dependencies)
    except ImageNotFoundException as e:
        click.echo(RED(str(e)))
        sys.exit(1)
    instance.foreground = True
    if command:
        instance.command = ['{} -lc "{}"'.format(shell_path, ' '.join(command))]
    else:
        instance.command = ["{} -l".format(shell_path)]
    # Run that change
    task = Task("Shelling into {}".format(container.name), parent=app.root_task)
    run_formation(app, host, formation, task, [container])


@click.command()
@click.argument("containers", type=ContainerType(), nargs=-1)
@click.option("--host", "-h", type=HostType(), default="default")
@click.pass_obj
def stop(app, containers, host):
    """
    Stops containers and ones that depend on them
    """
    app.print_chart()
    formation = FormationIntrospector(host, app.containers).introspect()
    # Look through the formation and remove the containers matching the name
    for instance in list(formation):
        # If there are no names, then we remove everything
        if instance.container in containers or (not containers and not instance.container.system):
            # Make sure that it was not removed already as a dependent
            if instance.formation:
                formation.remove_instance(instance)
    # Run the change
    task = Task("Stopping containers", parent=app.root_task)
    run_formation(app, host, formation, task)


@click.command()
@click.argument("containers", type=ContainerType(), nargs=-1)
@click.option("--host", "-h", type=HostType(), default="default")
@click.pass_obj
def restart(app, containers, host):
    """
    Stops and then starts containers.
    """
    app.invoke("stop", containers=containers, host=host)
    if containers:
        app.invoke("run", containers=containers, host=host)
    else:
        app.invoke("up", host=host)


def run_formation(app, host, formation, task, arg_containers=[]):
    """
    Common function to run a formation change.
    """
    profile = app.profiles[1] if app.profiles and len(app.profiles) > 1 else None
    ignore_dependencies = profile.ignore_dependencies if profile else False
    run_hook = task.name != "Stopping containers"

    # If ignore dependencies set, remove the containers not listed in the profile
    if ignore_dependencies:
        profile_containers = [c for c in app.containers if app.containers.options(c).get('default_boot')]
        for instance in list(formation):
            c = instance.container
            if not instance.container.system and c not in profile_containers and c not in arg_containers:
                formation.remove_instance(instance, True)

    if run_hook:
        app.run_hooks(PluginHook.PRE_GROUP_START, host=host, formation=formation, task=task)
    container_in_error = None
    error_message = None
    show_tail_message = False
    try:
        FormationRunner(app, host, formation, task).run()
    # General docker/runner error
    except DockerRuntimeError as e:
        container_in_error = e.instance.container
        error_message = str(e)
        if e.code == "BOOT_FAIL":
            show_tail_message = True
    # An image was not found
    except ImageNotFoundException as e:
        container_in_error = e.instance.container
        error_message = "Missing image for {} - cannot continue boot.".format(container_in_error.name)

    # Set error properties to be used in post hook
    if run_hook:
        app.run_hooks(PluginHook.POST_GROUP_START, host=host, formation=formation, task=task,
                  container_in_error=container_in_error, error_message=error_message)
    if error_message:
        click.echo(RED(error_message))
        if show_tail_message:
            click.echo(CYAN("You can see its output with `ftl tail {}`.".format(container_in_error.name)))
    else:
        task.finish(status="Done", status_flavor=Task.FLAVOR_GOOD)
