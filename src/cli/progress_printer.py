import click
from collections import OrderedDict

from .colors import CYAN


UP_ONE = "\033[A\033[1000D"
CLEAR_LINE = "\033[2K"


class ProgressPrinter:
    """
    Prints multiple in-progress statuses to the terminal in a way where they
    rewrite their own lines.
    """
    prefix = ""

    def __init__(self):
        self.current = OrderedDict()

    def start(self, noun, verb, status=""):
        """
        Adds something to be displayed as "verb noun: status".
        Noun is unique; if you re-use it, you must end() it before you start()
        the same noun again.
        """
        assert noun not in self.current
        # Get into the right place on the terminal
        print(UP_ONE * len(self.current), flush=True, end="")
        # Add our noun in
        self.current[noun] = {"verb": verb, "status": status}
        # Re-print the statuses
        self._print_all()

    def update(self, noun, status):
        """
        Updates what's printed afer "verb noun".
        """
        self.current[noun]['status'] = status
        self._print_all()

    def end(self, noun, status=None):
        """
        Removes the item from the live list and pushes it above with a final status.
        """
        if status is not None:
            self.current[noun]['status'] = status
        # Get into the right place on the terminal
        print(UP_ONE * len(self.current), flus=True, end="")
        # Print the singe item we're removing
        self._print_one(noun)
        # Remove it from the rest and print
        del self.current[noun]
        self._print_all()

    def _print_all(self):
        """
        Prints all items.
        """
        for noun in self.current.keys():
            self._print_one(noun)

    def _print_one(self, noun):
        details = self.current[noun]
        print(CLEAR_LINE + self.prefix + "{} {}: {}".format(
            details['verb'],
            CYAN(noun),
            details['status'],
        ))


class RunProgressPrinter(ProgressPrinter):
    """
    Translates run/stop progress notifications into nice console output.
    """

    def __call__(self, progtype, data):
        handler = getattr(self, "prog_{}".format(progtype), None)
        if handler:
            handler(data)
        else:
            self.prog_default(progtype, data)

    def prog_to_stop(self, data):
        if data['instances']:
            click.echo(
                self.prefix +
                "Plan to stop: " +
                ", ".join(sorted(CYAN(instance.container.name) for instance in data['instances']))
            )

    def prog_to_start(self, data):
        if data['instances']:
            click.echo(
                self.prefix +
                "Plan to start: " +
                ", ".join(sorted(CYAN(instance.container.name) for instance in data['instances']))
            )

    def prog_stop_begin(self, data):
        self.start(data['instance'].container.name, "Stopping")

    def prog_stop_end(self, data):
        self.end(data['instance'].container.name, "Done")

    def prog_start_begin(self, data):
        self.start(data['instance'].container.name, "Starting")

    def prog_start_progress(self, data):
        self.update(data['instance'].container.name, data['message'])

    def prog_start_end(self, data):
        self.end(data['instance'].container.name, "Done")

    def prog_default(self, progtype, data):
        click.echo("{}: {}".format(progtype, data))
