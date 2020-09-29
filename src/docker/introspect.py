import attr
import warnings

from ..containers.formation import ContainerFormation, ContainerInstance
from ..exceptions import DockerRuntimeError


@attr.s
class FormationIntrospector:
    """
    Given a docker host, introspects it to work out what Formation it is
    currently running and returns that for use/comparison with a desired new
    Formation.
    """
    host = attr.ib()
    graph = attr.ib()
    network = attr.ib(default=None)
    formation = attr.ib(init=False)

    class ContainerNotFound(DockerRuntimeError):
        pass

    def __attrs_post_init__(self):
        if self.network is None:
            self.network = self.graph.prefix

    def introspect(self):
        """
        Runs the instrospection and reutns a ContainerFormation.
        """
        # Make the formation
        self.formation = ContainerFormation(self.graph, self.network)
        # Go through all containers on the remote host that are running and on the right network
        for container in self.host.client.containers(all=False):
            if self.network in container['NetworkSettings']['Networks']:
                self.add_container(container['Names'][0].lstrip('/'))
        # As a second phase, go through and resolve links
        for instance in self.formation:
            instance.resolve_links()
        return self.formation

    def introspect_single_container(self, name):
        """
        Returns a single container introspected directly
        """
        # Inspect image and list images have different formats, so we use list with filter here to match the other code
        details = self.host.client.containers(filters={"name": name})
        if not details:
            raise DockerRuntimeError('Cannot introspect singe container {}'.format(name))
        # A race condition in docker [2017/09] means it returns a different format for containers that have just died
        if isinstance(details[0], dict):
            container_name = details[0]['Names'][0].lstrip('/')
        else:
            container_name = details[0]
        return self._create_container(container_name)

    def add_container(self, container_details):
        try:
            instance = self._create_container(container_details)
            self.formation.add_instance(instance)
        except self.ContainerNotFound as e:
            warnings.warn(e.args[0])

    def _create_container(self, container_name):
        """
        Returns a container build from introspected information
        """
        assert isinstance(container_name, str)
        container_details = self.host.client.inspect_container(container_name)
        # Find the container name in the graph
        try:
            labels = container_details['Config']['Labels']
            # Use the ftl-specific (not quarkworks-specific, just named uniquely as per the docker label spec) label
            # to work out what container name this was.
            container = self.graph[labels['com.quarkworks.ftl.container']]
        except KeyError:
            raise self.ContainerNotFound(
                (
                    'Cannot find local container for running container {}. '
                    'Perhaps its configuration was moved or deleted?'
                ).format(container_name)
            )
        # Get the image hash
        image = container_details['Image']
        assert ':' in image
        if image.startswith('sha256:'):
            image_id = image
        else:
            # It's a string name of a image
            # CONVERT IMAGE NAME INTO HASH USING REPO
            name, tag = image.split(':', 1)
            image_id = self.host.images.image_version(name, tag)
        # Work out links
        links = {}
        for link in (container_details['NetworkSettings']['Networks'][self.network].get('Links', None) or []):
            linked_container_name, link_alias = link.split(':', 1)
            links[link_alias] = linked_container_name
        # Work out devmodes
        mounted_targets = set()
        devmodes = set()
        for mount in container_details['Mounts']:
            mounted_targets.add(mount['Destination'])
        for devmode, mounts in container.devmodes.items():
            if all((destination in mounted_targets) for destination in mounts.keys()):
                devmodes.add(devmode)
        # Make a formation instance
        instance = ContainerInstance(
            name=container_name,
            container=container,
            image_id=image_id,
            links=links,
            devmodes=devmodes,
        )
        # Set extra networking attributes because it's running
        instance.ip_address = container_details['NetworkSettings']['Networks'][self.network]['IPAddress']
        instance.port_mapping = {}
        for container_port, host_details in container_details['NetworkSettings'].get('Ports', {}).items():
            if host_details:
                private_port = int(container_port.split('/', 1)[0])
                public_port = int(host_details[0]['HostPort'])
                instance.port_mapping[private_port] = public_port
        return instance
