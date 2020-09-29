from .base import BasePlugin
from ..constants import PluginHook


class LegacyEnvPlugin(BasePlugin):
    """
    Plugin that adds legacy style (REDIS_1_PORT_6379_TCP_ADDR) environment variables to containers based on links.
    """

    def load(self):
        self.add_hook(PluginHook.PRE_RUN_CONTAINER, self.add_link_envs)

    def add_link_envs(self, host, instance, task):
        """
        Takes the instance and modifies the environment to have legacy link variables.
        """
        for alias, target in instance.links.items():
            # Ask Docker for all open ports
            ports = host.client.inspect_container(target.name)['NetworkSettings']['Ports']
            if ports:
                for port, _ in ports.items():
                    number, protocol = port.split("/")
                    name = "{}_1_PORT_{}_{}".format(
                        alias.replace("-", "_").upper(),
                        number,
                        protocol.upper(),
                    )
                    instance.environment[name] = "{}://{}:{}".format(protocol, alias, number)
                    instance.environment[name + "_ADDR"] = alias
                    instance.environment[name + "_PORT"] = number
