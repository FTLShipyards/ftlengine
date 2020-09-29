import attr
import http.client
import ssl
import socket
import time
from docker.errors import NotFound

from .base import BasePlugin
from ..cli.tasks import Task
from ..constants import PluginHook
from ..exceptions import ContainerBootFailure, DockerRuntimeError


class WaitsPlugin(BasePlugin):
    """
    Contains the basic, standard waits. Waits' .check is called repeatedly and should return True if the condition is
    met or False if it is not.
    """

    provides = ["waits"]

    def load(self):
        self.add_hook(PluginHook.POST_RUN_CONTAINER, self.post_start)
        self.add_catalog_type("wait")
        self.add_catalog_item("wait", "http", HttpWait)
        self.add_catalog_item("wait", "https", HttpsWait)
        self.add_catalog_item("wait", "tcp", TcpWait)
        self.add_catalog_item("wait", "time", TimeWait)
        self.add_catalog_item("wait", "file", FileWait)

    def post_start(self, host, instance, task):
        # Loop through all waits and build instances
        wait_instances = []
        for wait in instance.container.waits:
            # Look up wait in app
            try:
                wait_class = self.app.get_catalog_items("wait")[wait["type"]]
            except KeyError:
                raise DockerRuntimeError(
                    "Unknown wait type {} for {}".format(wait["type"], instance.container.name)
                )
            # Initialise it and attach a task
            params = wait.get("params", {})
            params["instance"] = instance
            params["host"] = host
            wait_instance = wait_class(**params)
            wait_instance.task = Task("Waiting for {}".format(wait_instance.description()), parent=task)
            wait_instance.task.update(status="Waiting")
            wait_instances.append(wait_instance)

        # Check on them all until they finish
        while wait_instances:
            # See if the container actually died
            if not host.container_running(instance.name):
                task.update(status="Dead", status_flavor=Task.FLAVOR_BAD)

                raise ContainerBootFailure(
                    "Failed during waits",
                    instance=instance,
                )
            # Check the waits
            for wait_instance in list(wait_instances):
                try:
                    if wait_instance.ready():
                        wait_instance.task.finish(status="Done", status_flavor=Task.FLAVOR_GOOD)
                        wait_instances.remove(wait_instance)
                except Exception as e:
                    task.update(status="Failed", status_flavor=Task.FLAVOR_BAD)
                    raise DockerRuntimeError("Failed while waiting for {}:\n{}".format(instance.container.name, e))
            time.sleep(1)


@attr.s
class TcpWait:
    """
    Checks that a TCP port is open
    """

    instance = attr.ib()
    host = attr.ib()
    port = attr.ib(default=80)
    timeout = attr.ib(default=1)

    def ready(self):
        try:
            conn_kwargs = {}
            if self.timeout:
                conn_kwargs['timeout'] = self.timeout
            if self.port not in self.instance.port_mapping:
                raise DockerRuntimeError("Trying to wait on non-exposed port {}".format(self.port))
            conn = socket.create_connection(self.target(), **conn_kwargs)
            conn.close()
            return True
        except socket.error:
            return False

    def target(self):
        """
        Returns (host, port) target information.
        """
        if self.port not in self.instance.port_mapping:
            raise DockerRuntimeError("Trying to wait on non-exposed port {}".format(self.port))
        return (self.host.external_host_address, self.instance.port_mapping[self.port])

    def description(self):
        return "TCP on port {}".format(self.port)


@attr.s
class HttpWait(TcpWait):
    """
    Checks that a HTTP endpoint exists and returns a good value.
    """

    path = attr.ib(default="/")
    method = attr.ib(default="GET")
    headers = attr.ib(default=attr.Factory(dict))
    expected_codes = attr.ib(default=attr.Factory(lambda: range(200, 400)))

    connection_class = http.client.HTTPConnection

    def _get_connection(self, **kwargs):
        addr, port = self.target()
        return self.connection_class(addr, port, timeout=self.timeout, **kwargs)

    def _ready_request(self, conn):
        while True:
            try:
                conn.request(self.method, self.path, headers=self.headers)
                response = conn.getresponse()
                if response.status in self.expected_codes:
                    return True
                return False
            except http.client.RemoteDisconnected:
                conn.connect()
                continue

    def ready(self):
        conn = self._get_connection()
        # Run wait
        try:
            return self._ready_request(conn)
        except Exception:
            return False
        finally:
            conn.close()

    def description(self):
        return "HTTP on port {}".format(self.port)


@attr.s
class HttpsWait(HttpWait):
    """
    HTTPS variant of the HTTP wait.

    If verify_cert is True, this will let the underlying SSL library attempt to verify the CA
    cert provided by the server. This means the SSL library must be able to find the cert.
    Usually this is accomplished by setting the SSL_CERT_FILE environment variable.
    """
    verify_cert = attr.ib(default=False)

    connection_class = http.client.HTTPSConnection

    def _get_connection(self, **kwargs):
        context = ssl.create_default_context()
        # We are going to be making a request to an IP address, so we cannot rely on the cert
        # having the correct hostname.
        context.check_hostname = False
        if not self.verify_cert:
            context.verify_mode = ssl.CERT_NONE
        return super(HttpsWait, self)._get_connection(context=context)

    def ready(self):
        conn = self._get_connection()
        try:
            return self._ready_request(conn)
        except (ssl.SSLError, ssl.CertificateError):
            # If there is a problem with the cert or SSL connection, error out immediately
            self.task.update(status="SSL error")
            raise
        except Exception:
            return False
        finally:
            conn.close()

    def description(self):
        return "HTTPS on port {}".format(self.port)


@attr.s
class TimeWait:
    """
    Waits a number of seconds
    """

    # Everything needs instance and host, alas
    instance = attr.ib()
    host = attr.ib()
    seconds = attr.ib()

    def __attrs_post_init__(self):
        self.wait_until = time.time() + int(self.seconds)

    def ready(self):
        return time.time() >= self.wait_until

    def description(self):
        return "{} seconds".format(self.seconds)


@attr.s
class FileWait:
    """
    Waits until a named file appears in the container
    """

    instance = attr.ib()
    host = attr.ib()
    path = attr.ib()
    waiting_name = attr.ib(default=None)

    def ready(self):
        # Get the file from the host
        try:
            self.host.client.get_archive(self.instance.name, self.path)
        except NotFound:
            return False
        else:
            return True

    def description(self):
        return self.waiting_name or "file {}".format(self.path)
