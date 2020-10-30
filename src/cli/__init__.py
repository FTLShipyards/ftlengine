import click
import collections
import pkg_resources
import sys
import os
import traceback
import attr
import requests
import yaml

from .alias_group import SpellcheckableAliasableGroup
from .colors import PURPLE, RED, YELLOW, CYAN, BOLD
from .tasks import RootTask
from ..config import Config
from ..constants import PluginHook
from ..docker.hosts import HostManager
from ..exceptions import DockerNotAvailableError
from ..containers.graph import ContainerGraph
from ..containers.profile import NullProfile, Profile
from ..utils.sorting import dependency_sort


@attr.s
class App(object):
    """
    Main app object that's passed around.

    Contains a "hooks" system, which allows plugins to register hooks (callables
    that take keyword arguments and return nothing) and other code to call them.

    Also contains a "catalog" system, which allows registration of "catalog types"
    and "catalog items", which is similar to the Python entrypoint system but tied
    to FTL plugins instead so we can have contitional loading/ordered loading.
    """
    cli = attr.ib()
    plugins = attr.ib(default=attr.Factory(dict), init=False)

    @classmethod
    def get_default_containers(cls):
        if not hasattr(cls, "containers"):
            cls.load_containers()
        return cls.containers

    @classmethod
    def load_config(cls):
        default_config_paths = ()
        cls.config = Config(default_config_paths)
        cls.hosts = HostManager.from_config(cls.config)
        cls.root_task = RootTask()

    @classmethod
    def load_containers(cls):
        if len(cls.config['ftl'].get('home', '')) == 0:
            return
        cls.containers = ContainerGraph(cls.config['ftl']['home'])

    @classmethod
    def print_chart(cls):
        if not hasattr(cls, 'containers'):
            cls.load_containers()
        click.echo(CYAN(f'Chart: {YELLOW(BOLD(cls.containers.prefix))}'))

    def load_plugins(self):
        """
        Loads all plugins defined in config
        """
        self.hooks = {}
        self.catalog = {}
        # Load plugin classes based on entrypoints
        plugins = []
        for entrypoint in pkg_resources.iter_entry_points("ftlengine.plugins"):
            try:
                plugin = entrypoint.load()
                plugins.append(plugin)
            except ImportError:
                click.echo(PURPLE("Failed to import plugin: {name}".format(name=entrypoint.name)), err=True)
                click.echo(PURPLE(traceback.format_exc()), err=True)
                sys.exit(1)
        # Build plugin provides
        provided = {}
        for plugin in plugins:
            for p in plugin.provides:
                # Make sure another plugin does not provide this
                if p in provided:
                    click.echo(PURPLE("Multiple plugins provide {}, please unload one.".format(p)))
                    sys.exit(1)
                provided[p] = plugin
        # Check plugin requires
        for plugin in plugins:
            for r in plugin.requires:
                if r not in provided:
                    click.echo(PURPLE("Plugin {} requires {}, but nothing provides it.".format(plugin, r)))
                    sys.exit(1)
        # Sort plugins by dependency order, and then alphabetically inside that
        plugins = dependency_sort(plugins, lambda x: [provided[r] for r in x.requires])
        # Load plugins
        for plugin in plugins:
            # We store plugins so you can look their instances up by class
            self.plugins[plugin] = instance = plugin(self)
            instance.load()

    def load_charts(self):
        """
        Loads the current charts
        """
        # check if ~/.ftl/charts.yaml file exists
        chart_file_path = os.path.join(
            self.config['ftl']['chart_data_path']
        )
        if os.path.isfile(chart_file_path):
            # Chart file exists load chart data
            with open(chart_file_path, 'r') as fh:
                chart_data = yaml.safe_load(fh.read())
                if chart_data:
                    self.config['ftl']['home'] = str(chart_data['charts'][0])
        else:
            # Chart file does not exist, so create it
            try:
                os.makedirs(os.path.dirname(chart_file_path))
            except OSError:
                pass
            with open(chart_file_path, 'w') as fh:
                data = {
                    "charts": [
                        '',
                    ],
                }
                yaml.safe_dump(data, fh, default_flow_style=False, indent=4)

    def load_profiles(self):
        """
        Loads the current profile stack
        """
        if len(self.config['ftl']['home']) == 0:
            return
        self.user_profile_path = os.path.join(
            self.config['ftl']['user_profile_home'],
            self.containers.prefix,
            "user_profile.yaml"
        )
        # Load the user profile, if it exists.
        if os.path.exists(self.user_profile_path):
            self.user_profile = Profile(self.user_profile_path)
        else:
            self.user_profile = NullProfile()
        self.profiles = [self.user_profile]
        # Keep following the parent profile tree until we hit the end
        while self.profiles[-1].parent_profile:
            next_profile_path = os.path.join(
                self.config['ftl']['home'],
                'profiles',
                '{}.yaml'.format(self.profiles[-1].parent_profile)
            )
            if not os.path.exists(next_profile_path):
                raise RuntimeError("Cannot load profile %s" % next_profile_path)
            self.profiles.append(Profile(
                next_profile_path,
                default_boot_compatability=True,
            ))
        # Now apply them in reverse order
        for profile in reversed(self.profiles):
            profile.apply(self.containers)

    def add_hook(self, hook_type, receiver):
        """
        Adds a plugin hook to be run later.
        """
        if hook_type not in PluginHook.valid_hooks:
            raise ValueError("Invalid hook type{}".format(hook_type))
        self.hooks.setdefault(hook_type, []).append(receiver)

    def run_hooks(self, hook_type, **kwargs):
        """
        Runs all hooks of the given type with the given keyword arguments.

        Returns True if at least one hook ran, False otherwise.
        """
        hooks = self.hooks.get(hook_type, [])
        for hook in hooks:
            hook(**kwargs)
        return bool(hooks)

    def add_catalog_type(self, name):
        """
        Adds a type of "catalog" for things to register.
        """
        if name in self.catalog:
            raise ValueError("Catalog type {} already registered".format(name))
        self.catalog[name] = collections.OrderedDict()

    def add_catalog_item(self, type_name, name, value):
        """
        Adds a catalog item by name and type
        """
        if type_name not in self.catalog:
            raise ValueError("Catalog type {} does not exist".format(type_name))
        if name in self.catalog[type_name]:
            raise ValueError("Catalog item {}/{} already registered".format(type_name, name))
        self.catalog[type_name][name] = value

    def get_catalog_items(self, type_name):
        if type_name not in self.catalog:
            raise ValueError("Catalog type {} does not exist".format(type_name))
        return self.catalog[type_name]

    def get_plugin(self, klass):
        """
        Given a plugin's class, returns the instance of it we have loaded.
        """
        return self.plugins[klass]

    def invoke(self, command_name, **kwargs):
        """
        Runs a [sub]command by name, passing context automatically.
        """
        context = click.get_current_context()
        command = cli.get_command(context, command_name)
        context.invoke(command, **kwargs)


class AppGroup(SpellcheckableAliasableGroup):
    """
    Group subclass that instantiates an App instance when called, loads
    plugins, and passes the app as the context obj.
    """

    def __init__(self, app_class, **kwargs):
        super(AppGroup, self).__init__(**kwargs)
        self.app = app_class(self)
        self.app.load_plugins()

    def invoke(self, ctx):
        ctx.obj = self.app
        return super(AppGroup, self).invoke(ctx)

    def main(self, *args, **kwargs):
        try:
            # TODO: Configure system pre run hooks
            return super(AppGroup, self).main(*args, **kwargs)
        except DockerNotAvailableError as e:
            # Run the failure hooks, printing a default error if nothing is hooked in
            if not self.app.run_hooks(PluginHook.DOCKER_FAILURE):
                click.echo(RED(str(e)))
            sys.exit(1)
        except requests.exceptions.ReadTimeout:
            click.echo(YELLOW("Transient Docker connection error, please try again."))
            sys.exit(1)


@click.command(cls=AppGroup, app_class=App)
@click.version_option()
@click.pass_obj
def cli(app):
    """
    FTL, the Docker-based development environment management tool.
    """
    # Load config based on CLI parameters
    app.load_config()
    app.load_charts()
    app.load_containers()
    app.load_profiles()


# Run CLI if called directly
if __name__ == '__main__':
    cli()
