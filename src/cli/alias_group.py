import click

from .colors import CYAN
from .spell import spell_correct


class SpellcheckableAliasableGroup(click.Group):
    """
    custom Group subclass that also has aliasing and spell correction.
    """

    def __init__(self, *args, **kwargs):
        super(SpellcheckableAliasableGroup, self).__init__(*args, **kwargs)
        self.aliases = {}

    def add_alias(self, command, alias_name):
        """
        Aliases `alias_name` to run `command`
        """
        self.aliases[alias_name] = command

    def suggest_command(self, ctx, cmd_name):
        """
        Uses edit distance to suggest a command if there's no match.
        """
        suggestion = spell_correct(cmd_name, self.list_commands(ctx) + list(self.aliases.keys()))
        if suggestion:
            ctx.fail('No such command "{cmd_name}", are you trying to run: {suggestion}?'.format(
                cmd_name=cmd_name,
                suggestion=CYAN(suggestion),
            ))

    def get_command(self, ctx, cmd_name):
        # Try to get the command directly or via and alias
        cmd = super(SpellcheckableAliasableGroup, self).get_command(ctx, cmd_name) or self.aliases.get(cmd_name)
        if cmd:
            return cmd
        # Run spellcheck
        self.suggest_command(ctx, cmd_name)
