import os
import sys
import subprocess
import click

from .base import BasePlugin
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
        self.add_command(dns)
        self.add_alias(configure, 'dns-configure')


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
        # TODO: FTL-39
        if domain_name == '':
            return True  # no domainname configured

        with open(self.hostfile_path, 'r') as fh:
            for line in fh:
                for item in domain_name:
                    if item in line:
                        return True
                    else:
                        continue
            return False


@click.group()
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
        click.echo(f'Configuring chart domainname: {domain_name} on localhost . . . ')
        subprocess.call(['sudo', 'ftl', 'dns', 'configure'])
        sys.exit()
    try:
        with open('/etc/hosts', 'a') as fh:
            fh.write('# Added by FTLengine\n')
            for item in domain_name:
                fh.write(f'127.0.0.1\t{item}\n')
            fh.write('# End of section\n')
    except Exception as e:
        click.echo(f'>e: {e}')
    finally:
        if verbose:
            click.echo('>END dns configure')
