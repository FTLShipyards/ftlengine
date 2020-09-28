import attr


class PluginMetaclass(type):
    """
    Custom plugin metaclass to allow comparison for sorting by memory ID
    """

    @property
    def _orderable_id(cls):
        """
        Property that is unique but orderable enough that plugins load
        in the same order each call unless they're named exactly the same.
        """
        return cls.__name__ + str(id(cls))

    def __gt__(cls, other):
        return cls._orderable_id > other._orderable_id

    def __lt__(cls, other):
        return cls._orderable_id < other._orderable_id

    def __eq__(cls, other):
        return cls._orderable_id == other._orderable_id

    def __ne__(cls, other):
        return cls._orderable_id != other._orderable_id

    def __hash__(cls):
        return hash(cls._orderable_id)


@attr.s
class BasePlugin(object, metaclass=PluginMetaclass):
    """
    Base plugin template.
    """
    app = attr.ib()
    # Simple plugin dependency checking - any strings in requires must be
    # in exactly one other loaded plugin's provides.
    provides = []
    requires = []

    def load(self):
        pass

    def add_command(self, func):
        self.app.cli.add_command(func)

    def add_alias(self, command_name, alias):
        self.app.cli.add_alias(command_name, alias)

    def add_hook(self, hook_type, func):
        self.app.add_hook(hook_type, func)

    def add_catalog_type(self, name):
        self.app.add_catalog_type(name)

    def add_catalog_item(self, type_name, name, value):
        self.app.add_catalog_item(type_name, name, value)
