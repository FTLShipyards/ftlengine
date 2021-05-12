import attr
from click import Choice, echo
from . import App
from .spell import spell_correct
from .colors import PURPLE, CYAN
from ..utils.functional import cached_property


Choice = attr.s(these={"_choices": attr.ib(default=None)}, init=False)(Choice)


@attr.s
class SpellCorrectChoice(Choice):
    # The superclass defines choices to be a required argument provided when
    # creating an instance of the class. Subclasses of Choice need to override
    # it so we can compute the choices as a cached property instead.
    context = attr.ib(init=False)

    def convert(self, value, param, ctx):
        self.context = ctx
        # Exact match
        if value in self.choices:
            return value
        # Match through normalization
        if ctx is not None and ctx.token_normalize_func is not None:
            value = ctx.token_normalize_func(value)
            for choice in self.choices:
                if ctx.token_normalize_func(choice) == value:
                    return choice
        self.fail(
            'invalid choice: {}. {}'.format(
                PURPLE(value),
                self.get_missing_message(param, value),
            ),
            param,
            ctx,
        )

    def get_missing_message(self, param, value=None):
        message = super(SpellCorrectChoice, self).get_missing_message(param)
        if value:
            echo(f'\nvalue: {value}\nself.choices: {self.choices}\n')
            suggestion = spell_correct(value, self.choices)
            if suggestion:
                message += "\nare you looking for: {suggestion}?".format(suggestion=CYAN(suggestion))


@attr.s
class ContainerType(SpellCorrectChoice):
    name = 'container'
    _all = attr.ib(default=False)
    _profile = attr.ib(default=False)

    class Profile:
        pass

    @cached_property
    def choices(self):
        # Handle no object in the context during error states
        if not hasattr(self, 'context') or not hasattr(self.context, "obj"):
            return App.get_default_containers().containers.keys()
        # Return valid choices
        containers = self.context.obj.containers
        choices = [container.name for container in containers]
        if self._profile:
            choices = ['profile'] + choices
        if self._all:
            choices = ['all'] + choices
        return sorted(choices)

    def convert(self, value, param, ctx):
        name = super(ContainerType, self).convert(value, param, ctx)
        if name == 'all':
            return list(self.context.obj.containers.containers.values())
        elif name == 'profile':
            # Return a list of all containers
            return self.Profile
        else:
            return self.context.obj.containers[name]


@attr.s
class HostType(SpellCorrectChoice):
    name = 'host'

    @cached_property
    def choices(self):
        # Handle no object in the context during error states
        if not hasattr(self, "context") or not hasattr(self.context, "obj"):
            return []
        # Return valid choices
        choices = [host.alias for host in self.context.obj.hosts]
        return sorted(choices)

    def convert(self, value, param, ctx):
        host_name = super(HostType, self).convert(value, param, ctx)
        return self.context.obj.hosts[host_name]


@attr.s
class MountType(SpellCorrectChoice):
    name = 'mount'

    @cached_property
    def choices(self):
        # Handle no object in the context during error states
        if not hasattr(self.context, "obj"):
            return App.get_default_containers().devmode_names()
        # Collapse lists of list of devmode keys into a single set
        choices = self.context.obj.containers.devmode_names()

        return sorted(choices)
