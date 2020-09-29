import attr
import warnings

from ..exceptions import ImageNotFoundException
from ..utils.sorting import dependency_sort


@attr.s
class ContainerFormation:
    """
    Represents a desired or current layout of containers on a single host,
    including their links, image versions, environment etc.

    Formations have a network, which is how we identify which containers might
    be part of a formation or not (e.g., if a container is launched on an
    "universal" netowrk but the formation does not contain it, it should be
    shut down).

    Cross-network linking is done via use of "proxy containers", which get
    put in as a link alias with the right name and forward all connections
    on the appropriate ports to a remote endpoint. Formations are only scoped
    to the host; higher-level management of a set of different hosts is done
    elsewhere.
    """
    graph = attr.ib(repr=False)
    network = attr.ib(default=None)
    _instances = attr.ib(default=attr.Factory(list), repr=False)
    container_instances = attr.ib(default=attr.Factory(dict), init=False, repr=False)

    def __attrs_post_init__(self):
        if self.network is None:
            self.network = self.graph.prefix
        for instance in self._instances:
            self.add_instance(instance)

    def validate(self):
        for instance in self:
            instance.validate()

    def add_instance(self, instance):
        """
        Adds an existing instance into the formation.
        """
        assert instance.formation is None
        self.container_instances[instance.name] = instance
        instance.formation = self

    def remove_instance(self, instance, ignore_dependencies=False):
        """
        Removes an instance from the formation
        """
        # Make sure the instance being removed is part of us
        assert instance.formation is self
        # Resolve the dependent containers so they can all be removed
        dependent_descendancy = set(dependency_sort([instance.container], self.graph.dependents)[:-1])
        for other_instance in list(self):
            if other_instance.container in dependent_descendancy and other_instance.formation:
                if ignore_dependencies:
                    # only remove the dependency
                    # prevent a starting container to be stuck waiting for a dependency
                    self.graph.discard_dependency(other_instance.container, instance.container)
                else:
                    # Fully remove all the dependent containers
                    other_instance.formation = None
                    del self.container_instances[other_instance.name]
        # Remove the requested container
        del self.container_instances[instance.name]
        instance.formation = None

    def remove_instances(self, instances):
        for instance in instances:
            # Make sure that it was not removed from the formation already as a dependent
            if instance.formation:
                self.remove_instance(instance)

    def add_container(self, container, host, ignore_dependencies=False):
        """
        Adds a container to run inside the formation along with all dependencies.
        Returns the Instance that was created for the container.
        """
        # Get the list of all dependencies and dependency-ancestors in topological order
        # (this also makes sure there are no cycles as a nice side effect)
        devmodes = self.graph.options(container).get('devmodes', set())
        dependency_ancestry = dependency_sort([container], self.graph.dependencies)[:-1]
        direct_dependencies = self.graph.dependencies(container)
        # Make sure all its dependencies are in the formation
        links = {}
        for dependency in dependency_ancestry:
            # Find the container to satisfy the dependency
            for instance in self:
                if instance.container == dependency:
                    break
            else:
                # OK, we need to make one
                try:
                    instance = self.add_container(dependency, host, ignore_dependencies)
                except ImageNotFoundException as e:
                    # Annotate the error with the container
                    e.container = dependency
                    raise
            if dependency in direct_dependencies:
                links[dependency.name] = instance
        # Look up the image hash to use in the repo
        image_id = host.images.image_version(
            container.image_name,
            container.image_tag,
            ignore_not_found=ignore_dependencies,
        )
        # Make the instance
        instance = ContainerInstance(
            name="{}.{}.1".format(self.graph.prefix, container.name),
            container=container,
            image_id=image_id,
            links=links,
            devmodes=devmodes,
            foreground=container.foreground,
            environment=container.environment,
            mem_limit=container.mem_limit,
        )
        self.add_instance(instance)
        return instance

    def clone(self):
        """
        Clones the formation into a new copy entirely unlinked from this one,
        including new Instances.
        """
        new = self.__class__(self.graph, self.network)
        for instance in self:
            new.add_instance(instance.clone())
        return new

    def has_container(self, container):
        """
        Returns True if the formation has an instance running the given container.
        """
        return any(instance.container == container for instance in self)

    def get_container_instance(self, container_name):
        """
        Given the container name (not the runtime name, the working
        human name to refer to), returns the corresponding
        ContainerInstance.
        """
        for instance in self:
            if instance.container.name == container_name:
                return instance
        raise ValueError("Could not find a running instance of {}".format(container_name))

    def get_instances_using_volume(self, name):
        """
        Return a list of instances that require the named volume.
        """
        return [
            instance for instance in self if
            any(name == v.source for v in instance.container.named_volumes.values())
        ]

    def __getitem__(self, key):
        return self.container_instances[key]

    def __contains__(self, key):
        return key.name in self.container_instances

    def __iter__(self):
        return iter(self.container_instances.values())


@attr.s(hash=False)
class ContainerInstance:
    """
    Represents a single container as part of an overall ContainerFormation
    request.

    :name: The runtime name of the container, like "quarkworks.core-frontend.1"
    :container: The Container instance that's backing this container
    :image_id: The image hash to use for the container
    :links: A dictionary of {alias_str: ContainerInstance} that maps other containers to links
    :devmodes: A set of enabled devmode strings as defined on the Container
    :ports: Exposed ports as {external_port: container_port}
    :environment: Extra environment variables to set in the container
    :command: A custom command override (as a list of string arguments, like subprocess.call takes)
    :foreground: If True, the container is launched in the foreground and a TTY attached
    """
    name = attr.ib()
    container = attr.ib(eq=False, order=False)
    image_id = attr.ib(eq=False, order=False)
    links = attr.ib(default=attr.Factory(dict), repr=False, eq=False, order=False)
    devmodes = attr.ib(default=attr.Factory(set), repr=False, eq=False, order=False)
    ports = attr.ib(default=attr.Factory(dict), repr=False, eq=False, order=False)
    environment = attr.ib(default=attr.Factory(dict), repr=False, eq=False, order=False)
    mem_limit = attr.ib(default=0, repr=False, eq=False, order=False)
    command = attr.ib(default=None, repr=False, eq=False, order=False)
    foreground = attr.ib(default=None, repr=False, eq=False, order=False)
    formation = attr.ib(default=None, init=False, repr=False, eq=False, order=False)

    def __attrs_post_init__(self):
        self.ports.update(dict(self.container.ports.items()))

    def validate(self):
        """
        Cross-checks the settings we have against the options the Container has
        """
        # Verify all link targets are possible
        for alias, target in list(self.links.items()):
            if isinstance(target, str):
                try:
                    self.resolve_links()
                    continue
                except Exception as e:
                    raise ValueError(f"Link target {target} is still a string! {e}")
            if target.container not in self.container.graph.dependencies(self.container):
                del self.links[alias]
        # Verify devmodes exist
        for devmode in list(self.devmodes):
            if devmode not in self.container.devmodes:
                warnings.warn("Invalid devmode %s on container %s" % (devmode, self.container.name))
                self.devmodes.remove(devmode)

    def clone(self):
        """
        Returns a safely mutable clone of this instance
        """
        return self.__class__(
            name=self.name,
            container=self.container,
            image_id=self.image_id,
            links=self.links,
            devmodes=self.devmodes,
            ports=self.ports,
            environment=self.environment,
            mem_limit=self.mem_limit,
            command=self.command,
            foreground=self.foreground,
        )

    def different_from(self, other):
        """
        Returns if the other instance is different from this one at all
        (i.e., we need to stop it and start us)
        """
        return (
            self.name != other.name or
            self.container != other.container or
            self.image_id != other.image_id or
            self.links != other.links or
            self.devmodes != other.devmodes or
            self.ports != other.ports or
            self.environment != other.environment or
            self.mem_limit != other.mem_limit or
            self.command != other.command or
            other.foreground or
            self.foreground
        )

    def resolve_links(self):
        """
        Resolves any links that are still names to instances from the formation
        """
        for alias, target in list(self.links.items()):
            # If it's a string, it's come from an introspection process where we couldn't
            # resolve into an instance at the time (as not all of them were around)
            if isinstance(target, str):
                try:
                    target = self.formation[target]
                except KeyError:
                    # We don't error here as that would prevent you stopping orphaned containers;
                    # instead, we delete the link and warn the user. The deleted link means `up` will recreate it
                    # if it's orphaned.
                    del self.links[alias]
                else:
                    self.links[alias]
            elif isinstance(target, ContainerInstance):
                pass
            else:
                raise ValueError("Invalid link value {}".format(repr(target)))

    def __eq__(self, other):
        return self.name == other.name

    def __ne__(self, other):
        return not (self == other)

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return "<ContainerInstance {} ({})>".format(self.name, self.container.name)
