import sys
import attr
import click


from distutils.version import StrictVersion
from ..constants import PluginHook
from ..plugins.base import BasePlugin
from ..plugins.plugin_config import PluginConfig
from ..cli.colors import RED
from ..version import __version__


def _check_version(name, expected, found, upgrade_message):
    if StrictVersion(found) < StrictVersion(expected):
        click.echo(RED(F"Incompatible {name} version, expected {expected}, found {found}. {upgrade_message}."))
        sys.exit(1)


@attr.s
class UpgradePlugin(BasePlugin):
    """
    Plugin to check for required versions for ftl
    It throws an error if the current version is not supported.
    """

    def load(self):
        self.plugin_config = PluginConfig('upgrade')
        self.add_hook(PluginHook.PRE_GROUP_BUILD, self._check_version)
        self.add_hook(PluginHook.PRE_RUN_CONTAINER, self._check_version)

    def _check_version(self, *args, **kwargs):
        if not self.plugin_config.get_config(self, 'enable', False):
            return
        _check_version(
            'ftlengine',
            self.plugin_config.get_config(
                self,
                'required_ftl_version',
            ),
            __version__,
            self.plugin_config.get_config(
                self,
                'ftl_upgrade_message',
                "Please upgrade FTL",
            ),
        )
