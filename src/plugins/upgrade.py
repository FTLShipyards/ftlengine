import sys
import attr
import click
import ftl


from distutils.version import StrictVersion
from ftl.constants import PluginHook
from ftl.plugins.base import BasePlugin
from ftl.plugins.plugin_config import PluginConfig
from ftl.cli.colors import RED


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
            'ftl',
            self.plugin_config.get_config(
                self,
                'required_ftl_version',
            ),
            ftl.__version__,
            self.plugin_config.get_config(
                self,
                'ftl_upgrade_message',
                "Please upgrade FTL",
            ),
        )
