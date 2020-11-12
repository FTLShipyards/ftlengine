import os
import yaml
import itertools
import attr

from ..exceptions import BadConfigError
from .container import Container


@attr.s
class ContainerGraph:
    """
    Represents the graph of all available containers.

    Containers are loaded from a source directory. The graph has containers as
    nodes and (runtime) dependencies as edges. It also stores as set of "options"
    for each container, which contain information like which devmodes to apply/
    containers to start by default.
    """
    path = attr.ib(converter=os.path.abspath)
    containers = attr.ib(default=attr.Factory(dict), init=False, repr=False)
    _dependencies = attr.ib(default=attr.Factory(dict), repr=False)
    _build_dependencies = attr.ib(default=attr.Factory(dict), init=False, repr=False)
    _options = attr.ib(default=attr.Factory(dict), init=False, repr=False)
    config_path = attr.ib(init=False)

    def __attrs_post_init__(self):
        """
        Loads containers from the filesystem and sets up the graph.
        """
        self.load_config()
        self.load_containers()

    def load_config(self):
        """
        Loads top-level configuration
        """
        self.prefix = None
        self.registry = None
        self.external_secrets = None
        self.domainname = None
        self.plugin_configuration = dict()
        # Work out the path to the configuration file
        self.config_path = os.path.join(self.path, "ftl.yaml")
        if not os.path.isfile(self.config_path):
            raise BadConfigError(
                "Cannot find ftl.yaml in top level of container library at {}".format(
                    self.path,
                )
            )
        # Load the configuration file
        with open(self.config_path, "r") as fh:
            config_data = yaml.safe_load(fh.read())
        if not isinstance(config_data, dict):
            raise BadConfigError(
                "{} is badly formatted (not a dict)".format(
                    self.config_path,
                )
            )
        for key, value in config_data.items():
            if key == "prefix":
                self.prefix = value
            elif key == "registry":
                self.registry = value
            elif key == "plugin_configuration":
                self.plugin_configuration = value
            elif key == 'external_secrets':
                self.external_secrets = value
            elif key == 'domainname':
                self.domainname = value
            else:
                raise BadConfigError(
                    "Unknown key in {}: {}".format(
                        self.config_path,
                        key
                    )
                )
        if self.prefix is None:
            raise BadConfigError(
                "No prefix set in top-level ftl.yaml {}".format(
                    self.config_path,
                )
            )

    def load_containers(self):
        """
        Loads containers from their directories.
        """
        # Scan through directories and load ones that look right
        containers = []
        for name in os.listdir(self.path):
            container_path = os.path.join(self.path, name)
            if os.path.isdir(container_path) and os.path.isfile(os.path.join(container_path, "Dockerfile")):
                containers.extend(Container.from_directory(self, container_path))
        self.add_containers(containers)

    def add_containers(self, containers):
        """
        Adds container nodes to the graph and links them up based on their `links`
        """
        # Add to main set
        for container in containers:
            self.containers[container.name] = container
        # Link by dependency
        for container in containers:
            # Runtime dependencies
            try:
                self.set_dependencies(
                    container,
                    [
                        self.containers[link_name]
                        for link_name, link_details
                        in container.links.items()
                        if link_details.get("required")
                    ],
                )
            except KeyError as e:
                raise BadConfigError("Container not found for required link {}".format(e.args[0]))
            # Build dependencies
            if container.build_parent_in_prefix:
                self.add_build_dependency(container, self.containers[container.build_parent.split("/")[1]])

    def set_dependencies(self, depender, providers):
        """
        Adds runtime dependency edges to the graph where `depender` depends on each
        of `providers`
        """
        self._dependencies[depender] = set()
        for provider in providers:
            if provider not in self.containers.values() or depender not in self.containers.values():
                raise ValueError(
                    "Cannot link between containers {} and {} - one or both not in graph.".format(
                        provider,
                        depender,
                    )
                )
            self._dependencies[depender].add(provider)

    def set_option(self, container, option, value):
        """
        Sets the option named `option` on the container to the given value.
        Also does some basic checks of what valid options are.
        """
        if option in ("default_boot", "in_profile"):
            value = bool(value)
        elif option == "devmodes":
            if not isinstance(value, set):
                raise BadConfigError("Devmodes option must be a set.")
        else:
            raise BadConfigError("Unknown option %s being set" % option)
        self._options.setdefault(container, {})[option] = value

    def add_build_dependency(self, depender, provider):
        """
        Adds a build dependency edge to the graph where `depender` depends on `provider`
        """
        if provider not in self.containers.values() or depender not in self.containers.values():
            raise ValueError("Cannot build - link between containers {} and {} - one or both not in graph.".format(
                provider,
                depender,
            ))
        self._build_dependencies[depender] = provider

    def dependencies(self, container):
        """
        Returns a set of the dependencies of the container
        """
        return self._dependencies.get(container, set())

    def discard_dependency(self, container, dependency_container):
        """
        Discard a runtime dependency for a container.
        """
        self._dependencies.get(container, set()).discard(dependency_container)

    def dependents(self, container):
        """
        Returns the containers that depend on the named container
        """
        result = set()
        for candidate, dependencies in self._dependencies.items():
            if container in dependencies:
                result.add(candidate)
        return result

    def devmode_names(self):
        """
        Returns a set of all available devmode names
        """
        devmode_names = set(itertools.chain.from_iterable(
            container.devmodes.keys() for container in self
        ))

        return devmode_names

    def build_ancestry(self, container):
        """
        Returns the ancestors of the container based on build dependencies, in
        order from furthest ancestor to immediate parent.
        """
        ancestry = []
        while container is not None:
            ancestry.insert(0, container)
            container = self._build_dependencies.get(container, None)
        return ancestry[:-1]

    def build_parent(self, container):
        """
        Returns the immediate parent of a container, per its build dependencies.
        """
        return self._build_dependencies.get(container, None)

    def options(self, container):
        """
        Returns runtime options for the container
        """
        return self._options.get(container, {})

    def __getitem__(self, key):
        return self.containers[key]

    def __iter__(self):
        return iter(self.containers.values())
