import os
import sys
import subprocess
import click

from .base import BasePlugin
# from ..constants import PluginHook
from ..docker.introspect import FormationIntrospector
from ..cli.argument_types import HostType


class DomainNamePlugin(BasePlugin):
    """
    Allows FTL to manage domain names per chart
    """

    provides = ['dns']

    def load(self):
        self.add_catalog_type('domainname')
        self.add_catalog_item('domainname', 'localhost', DomainNameHandler)
        # self.add_hook(PluginHook.PRE_GROUP_START, self.pre_flight_check)
        self.add_command(dns)
        self.add_alias(configure, 'dns-configure')

    def pre_flight_check(self, host, formation, task):
        """
        Checks the /etc/hosts file for the chart's domain name, if provided
        """
        click.echo('>START pre_flight_check')
        domain_name_plugins = self.app.get_catalog_items('domainname')
        click.echo(f'<--\ndomain_name_plugins: {domain_name_plugins}\n-->')
        domain_name_data = formation.graph.domainname
        click.echo(f'<--\ndomain_name_data: {domain_name_data}\n-->')
        handler = domain_name_plugins['localhost'](self.app, domain_name_data)
        domain_status = handler.check_localhost()
        click.echo(f'>VAR domain_status: {domain_status}\n')
        click.prompt(f'>domain_status: {domain_status}\n')
        # click.prompt(f'<-- END pre_flight_check -->')
        click.echo('>END pre_flight_check')


class DomainNameHandler:
    """
    Domain Name Handler
    Allows the retrieving of domain names from ftl configs
    """

    def __init__(self, app, data):
        self.app = app
        self.data = data
        self.hostfile_path = '/etc/hosts'

    def get_domainname(self):
        if self.data:
            return self.data.get('localhost', '')
        else:
            return None

    def check_localhost(self):
        """
        Returns True if formation domainname in local /etc/hosts
        False otherwise
        """
        domain_name = self.get_domainname()
        if domain_name == '':
            return True  # no domainname configured

        with open(self.hostfile_path, 'r') as fh:
            for line in fh:
                if domain_name in line:
                    return True
                else:
                    continue
            return False
            # file_data = [line for line in fh]
            # if self.data.get('localhost', '') in item for item in file_data:
            #     return True
            # else:
            #     return False

    def configure_localhost_if_needed(self):
        """
        If self.data contains a valid domain name string
        Check the local hosts file if domain configured to resolve to local host
        If not, then set it
        """
        # with task.paused_output():
        with open('/etc/hosts', 'r') as fh:
            host_entries = [line for line in fh]
            click.echo(f'>host_entries: {host_entries}')
            # for line in fh:
            #     click.echo(f'line: {line}')
        domain_name = self.data.get('localhost', '')
        click.echo(f'>domain_name: {domain_name}')
        if os.geteuid() == 0:
            click.echo('>We are root!')
            try:
                with open('/etc/hosts', 'a') as fh:
                    fh.write('# Added by FTLengine\n')
                    fh.write(f'127.0.0.1\t{domain_name}\n')
                    fh.write('# End of section\n')
            except Exception as e:
                click.echo(f'>e: {e}')
        else:
            subprocess.call(['sudo', 'ftl', 'dns', 'configure'])
            sys.exit()
        click.prompt('>END: configure_localhost_if_needed')


@click.group(invoke_without_command=True)
@click.pass_obj
def dns(app):
    """
    Allows configuration of localhost domain names
    """
    pass


@dns.command()
@click.option("--host", "-h", type=HostType(), default="default")
@click.option('-V', '--verbose', count=True, required=False, default=None)
@click.pass_obj
def configure(app, host, verbose):
    """
    Configure local /etc/hosts for localhost domainname defined in root level ftl.yaml
    """
    app.print_chart()
    if verbose:
        click.echo('>START dns configure')
    domain_name_plugins = app.get_catalog_items('domainname')
    formation = FormationIntrospector(host, app.containers).introspect()
    domain_name_data = formation.graph.domainname
    handler = domain_name_plugins['localhost'](app, domain_name_data)
    domain_name = handler.get_domainname()
    if verbose:
        click.echo(f'>domain_name_plugins: {domain_name_plugins}')
        click.echo(f'>domain_name_data: {domain_name_data}')
        click.echo(f'>domainname: {domain_name}')
    if domain_name is None:
        click.echo('No domain name configured')
        return
    localhost_status = handler.check_localhost()
    if verbose:
        click.echo(f'>localhost_status: {localhost_status}')
    if localhost_status is True:
        click.echo(f'Domainname: {domain_name} already configured')
        return
    if os.geteuid() != 0:
        subprocess.call(['sudo', 'ftl', 'dns', 'configure'])
        sys.exit()
    try:
        with open('/etc/hosts', 'a') as fh:
            fh.write('# Added by FTLengine\n')
            fh.write(f'127.0.0.1\t{domain_name}\n')
            fh.write('# End of section\n')
    except Exception as e:
        click.echo(f'>e: {e}')
    finally:
        if verbose:
            click.echo('>END dns configure')
