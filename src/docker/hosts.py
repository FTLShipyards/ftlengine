import attr
import urllib.parse
import os
import docker
import sys
import subprocess
import json
import requests

from distutils.version import LooseVersion
from ..utils.functional import cached_property, thread_cached_property
from ..exceptions import DockerNotAvailableError
from .images import ImageRepository


@attr.s
class HostManager(object):
    """
    Contains all known hosts.
    """
    _hosts = attr.ib(default=attr.Factory(list))
    hosts = attr.ib(default=attr.Factory(dict), init=False)

    def __attrs_post_init__(self):
        for host in self._hosts:
            self.add_host(host)

    @classmethod
    def from_config(cls, config):
        return cls([
            Host.from_env(),
        ])

    def add_host(self, host):
        if host.alias in self.hosts:
            raise ValueError("Host alias %s is already assigned" % host.alias)
        self.hosts[host.alias] = host

    def __iter__(self):
        return iter(self.hosts.values())

    def __getitem__(self, key):
        return self.hosts[key]


@attr.s
class Host(object):
    """
    A Docker-running host.
    """
    alias = attr.ib()
    url = attr.ib()
    tls_ca = attr.ib()
    tls_cert = attr.ib()
    tls_key = attr.ib()
    url_scheme = attr.ib(init=False)
    url_location = attr.ib(init=False)

    def __attrs_post_init__(self):
        # Parse URL into components
        parse_result = urllib.parse.urlparse(self.url)
        self.url_scheme = parse_result.scheme
        self.url_location = parse_result.netloc
        if self.url_scheme not in ["unix", "tcp"]:
            raise ValueError("Unknown scheme in Docker URL %s" % self.url)

    @classmethod
    def from_env(cls, alias="default"):
        """
        Makes a host from Docker environment variables.
        """
        tls_ca = tls_cert = tls_key = None
        if "DOCKER_CERT_PATH" in os.environ:
            tls_ca = os.path.join(os.environ['DOCKER_CERT_PATH'], "ca.pem")
            tls_cert = os.path.join(os.environ['DOCKER_CERT_PATH'], "cert.pem")
            tls_key = os.path.join(os.environ['DOCKER_CERT_PATH'], "key.pem")
        return cls(
            alias=alias,
            url=os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock"),
            tls_ca=tls_ca,
            tls_cert=tls_cert,
            tls_key=tls_key,
        )

    @cached_property
    def publicly_visible(self):
        """
        Says if the server can be seen by other servers of not.
        """
        return (
            self.url_scheme == "tcp" and
            # TODO: Resolve hostnames first?
            self.url_location.split(".")[0] not in ["10", "192", "127"]
        )

    @cached_property
    def external_host_address(self):
        """
        Returns the address of the host as seen from an external networks and/or
        a host computer where FTL is running against a VM. This is the address which
        exposed ports would apparently appear on.
        """
        if self.url_scheme == "unix":
            return "127.0.0.1"
        elif self.url_scheme == "tcp":
            return self.url_location.split(":", 1)[0]

    @cached_property
    def allow_ssh_agent(self):
        """
        Says if the server is non-shared and thus safe to run ssh-agent on
        (ssh-agent contains the SSH keys of the person who started it in
        plaintext, so it must not be used on a plublic server)
        """
        return self.publicly_visible

    @thread_cached_property
    def client(self):
        """
        Returns a Docker client for the URL
        """
        # TLS setup
        tls = None
        tls_client = None
        if self.tls_cert and self.tls_key:
            tls_client = (self.tls_cert, self.tls_key)
        if tls_client or self.tls_ca:
            tls = docker.tls.TLSConfig(
                ca_cert=self.tls_ca,
                client_cert=tls_client,
                verify=True,
            )
        # Make client
        try:
            return docker.APIClient(
                base_url=self.url,
                version="auto",
                timeout=os.getenv('FTL_HTTP_TIMEOUT', 60),
                tls=tls,
            )
        except docker.errors.DockerException:
            raise DockerNotAvailableError("The docker host at {} is not available".format(self.url))

    @thread_cached_property
    def images(self):
        """
        Returns an image repository for the host
        """
        return ImageRepository(self)

    def container_exists(self, name):
        """
        Shortcut to see if a container exists with the given runtime name
        """
        try:
            self.client.inspect_container(name)
            return True
        except docker.errors.APIError:
            return False
        except requests.exceptions.ChunkedEncodingError:
            return False

    def container_running(self, name, ignore_exists=False):
        """
        says if the named container is running of not. Errors if you provide
        a container that does not exist.
        """
        if ignore_exists and not self.container_exists(name):
            return False
        data = self.client.inspect_container(name)
        return data['State']['Running']

    @cached_property
    def build_host_ip(self):
        """
        Returns the internal IP of the host as seen from the containers during
        build, which is the gateway of the default bridge network.
        Determines the "host" IP containers should use.
        Get the Gateway IP from the docker daemon.
        """
        version = LooseVersion(self.client.version()['Version'].split("-")[0])
        version_17_06 = LooseVersion("17.06.0")
        version_17_12 = LooseVersion("17.12.0")
        version_18_03 = LooseVersion("18.03.0")

        if version >= version_18_03 and sys.platform in ("darwin", "win32"):
            # gateway_ip = "host.docker.internal"
            gateway_ip = "172.17.0.1"
        elif sys.platform == "darwin" and version >= version_17_06:
            # MacOS + recent version of Docker for Mac
            gateway_ip = "docker.for.mac.host.internal" if version >= version_17_12 else "docker.for.mac.localhost"
        elif sys.platform == "win32" and version >= version_17_06:
            # Windows + recent version of Docker for Windows
            gateway_ip = "docker.for.win.host.internal" if version >= version_17_12 else "docker.for.win.localhost"
        else:
            # legacy logic for Linux and older version of docker for Mac and Windows
            # Make sure the network is created first
            try:
                subprocess.check_output(
                    ['docker', 'network', 'create', '-d', 'bridge', 'universe'],
                    universal_newlines=True,
                )
            except subprocess.CalledProcessError:
                # The network already exists
                pass
            # Grab its gateway IP
            docker_network_settings = subprocess.check_output(
                ['docker', 'network', 'inspect', 'universe'],
                universal_newlines=True,
            )
            gateway_ip = json.loads(docker_network_settings)[0]['IPAM']['Config'][0]['Gateway']
        return gateway_ip

    @cached_property
    def is_docker_for_mac(self):
        """
        Works out if the current install is docker for mac or docker-machine
        based.
        """
        if sys.platform != "darwin":
            return False
        if self.url_scheme != "unix":
            return False
        return True

    @cached_property
    def supports_cached_volumes(self):
        """
        If the host supports passing the "cached" flag to volumes to speed them
        up (implemented in Docker for Mac)
        """
        if self.is_docker_for_mac:
            version_info = self.client.version()
            base_version = version_info['Version'].split("-")[0]
            return LooseVersion(base_version) >= LooseVersion("17.05.0")
        else:
            return False
