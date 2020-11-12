import os
import yaml
import click

from .base import BasePlugin
from ..cli.colors import RED


class ChartPlugin(BasePlugin):
    """
    Allows FTL to chart projects and determine FTL home

    Checks file path for ftl project
    If so:
      Check ftl.yaml manifest root and tree
      Run project defined plugins
      Add project file path to global settings
    """

    provides = ['chart']

    requires = ['dns']

    def load(self):
        self.add_catalog_type('charts')
        # self.add_catalog_item('charts', 'path', ChartHandler)
        self.add_command(chart)


@click.group()
def chart():
    """
    Allows charting of FTL projects.
    """
    pass


@chart.command()
@click.argument(
    "file_path",
    required=True,
    type=click.Path(
        dir_okay=True,
        resolve_path=True,
    ),
    default='.',
)
@click.option('-V', '--verbose', count=True, required=False, default=None)
@click.pass_obj
def add(app, file_path, verbose):
    """
    Add file path to FTL charts
    """
    if verbose:
        click.echo(f'<--\nfile_path:{file_path}\n-->')
    # Check file_path
    if os.path.isdir(file_path) and os.path.exists(os.path.join(file_path, 'ftl.yaml')):
        # Read local chart data
        chart_data = read_chart_data(app, verbose)
        paths = []
        paths.append(file_path)
        chart_data['charts'] = paths
        if verbose:
            click.echo(f'<--\nchart_data:\n{chart_data}\n-->')
        with open(os.path.join(app.config['ftl']['chart_data_path']), 'w') as fh:
            yaml.safe_dump(chart_data, fh, default_flow_style=False, indent=4)
            app.config['ftl']['home'] = str(file_path)
        app.load_containers()
    else:
        click.echo(RED(f'File path {file_path} does not appear to be a valid FTL project.'))
        return
    app.print_chart()
    app.invoke('dns-configure')


@chart.command()
@click.pass_obj
def list(app):
    """
    Configure local FTL projects by file path
    """
    chart_list = app.get_catalog_items('charts')

    click.echo(f'<--\nchart_list:\n{chart_list}\n-->')


def read_chart_data(app, verbose=None):
    """
    # Read local chart data
    """
    chart_file_path = os.path.join(app.config['ftl']['chart_data_path'])
    chart_data = {}
    with open(chart_file_path, 'r') as fh:
        chart_data = yaml.safe_load(fh.read())
        if verbose:
            click.echo(f'<--\nchart_data:\n{chart_data}\n-->')
    return chart_data
