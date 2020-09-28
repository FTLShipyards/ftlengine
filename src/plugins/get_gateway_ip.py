from ftl.plugins.base import BasePlugin
from ftl.constants import PluginHook


class GetGatewayIPPlugin(BasePlugin):
    """
    Plugin for resolving the current Docker gateway IP and setting FTL_HOST inside
    containers.

    This ensures we can access containers listening on the gateway IP (e.g. Sinopia) inside
    other containers.

    This will be the docker daemon gateway IP.
    """

    def load(self):
        self.add_hook(PluginHook.PRE_BUILD, self.pre_build)
        self.add_hook(PluginHook.PRE_RUN_CONTAINER, self.pre_start)

    def pre_build(self, host, container, task):
        """
        Sets the IP containers can use to access resources/containers listening on the host address on build.
        """
        if 'FTL_HOST' in container.possible_buildargs:
            container.buildargs['FTL_HOST'] = host.build_host_ip

    def pre_start(self, host, instance, task):
        """
        Sets the IP containers can use to access resources/containers listening on the host address on run.
        """
        instance.environment['FTL_HOST'] = host.build_host_ip
