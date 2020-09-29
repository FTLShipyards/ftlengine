import attr
import click

from .colors import CYAN


@attr.s
class Table(object):
    """
    Table pretty-printer.

    Initialize with a list of ("COLUMNNAME", width_int). One space is added
    between columns.
    """
    columns = attr.ib()
    format_string = attr.ib(init=False)

    def __attrs_post_init__(self):
        self.format_string = " ".join(
            "%%-%is" % width
            for name, width in self.columns
        )

    def print_header(self):
        click.echo(CYAN(self.format_string % tuple(name for name, width in self.columns)))

    def print_row(self, data):
        click.echo(self.format_string % tuple(data))

    def print_all(self, datas):
        """
        Prints a table with header and all data at once
        """
        self.print_header()
        for data in datas:
            self.print_data(data)
