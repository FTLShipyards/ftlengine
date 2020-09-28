import re
import click


WHITE = lambda s: click.style(s, fg='white')
PURPLE = lambda s: click.style(s, fg='magenta')
BLUE = lambda s: click.style(s, fg='blue')
CYAN = lambda s: click.style(s, fg='bright_cyan')
GREEN = lambda s: click.style(s, fg='green')
YELLOW = lambda s: click.style(s, fg='yellow')
RED = lambda s: click.style(s, fg='red')
BOLD = lambda s: click.style(s, bold=True)
FADED = lambda s: click.style(s, dim=True)

REPLACE_LINE = lambda: click.echo('\033[F\r\033[K', nl=False)
ERASE_LINE = lambda: click.echo('\r\033[K', nl=False)


def yesno(value):
    """
    Converts and colors True/False values into "Yes/No"
    """
    if value:
        return GREEN("Yes")
    else:
        return RED("No")


def remove_ansi(line):
    """
    Removes ANSI control characters from a string
    """
    ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
    return ansi_escape.sub('', line)
