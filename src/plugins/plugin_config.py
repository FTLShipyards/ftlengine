from ..exceptions import DockerRuntimeError


class PluginConfig():
    """
    Load global ftl.yaml configuration for a given plugin.
    Plugin configuration is defined under 'plugin_configuration'.
    """
    plugin_name = ''

    def __init__(self, plugin_name):
        self.plugin_name = plugin_name

    def get_config(self, ctx, property_name, default=None):
        """
        Get the configuration value for plugin from the root ftl.yaml.

        Note: This method should only be called in the hooks. Calling it during
        plugin load or __init__ will throw an exception since the configuration
        has not been read yet.
        """
        config = ctx.app.containers.plugin_configuration.get(
            self.plugin_name, dict())
        if default is None:
            if property_name not in config.keys():
                raise DockerRuntimeError(
                    "Missing config property 'plugin_configuration.{}.{}'".format(
                        self.plugin_name, property_name
                    )
                )
            return config[property_name]
        return config.get(property_name, default)
