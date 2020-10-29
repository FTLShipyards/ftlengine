import os
import click
import subprocess
import botocore
import sys
import boto3
import time
import base64
import json

from ..cli.colors import RED, YELLOW
from ..plugins.base import BasePlugin
from ..constants import PluginHook


class AwsPlugin(BasePlugin):
    """
    Allows AWS resource operations (i.e., ECR, SecretsManager, S3)
    1) Using awscli credentials
    """

    requires = ['build']

    def load(self):
        self.add_catalog_item("registry", "aws", AwsRegistryHandler)
        self.add_catalog_type("external_secrets")
        self.add_catalog_item('external_secrets', 'aws', AwsExternalSecretsHandler)
        self.add_hook(PluginHook.PRE_BUILD, self.pre_build)
        self.add_hook(PluginHook.PRE_RUN_CONTAINER, self.pre_start)

    def pre_build(self, host, container, task):
        """
        Sets the following build args:
        - DD_API_KEY: DataDog API Key used in dd-agent container

        """
        external_secrets_plugins = self.app.get_catalog_items('external_secrets')
        external_secrets_data = self.app.containers.external_secrets
        handler = external_secrets_plugins['aws'](self.app, external_secrets_data)
        if handler.data:
            for item in handler.data['aws']['secrets']:
                for key in item.keys():
                    if key in container.possible_buildargs:
                        container.buildargs[key] = handler.get_aws_secret(item[key], key)
        if 'ENV' in container.possible_buildargs and 'ENV' in container.environment:
            # TODO Allow for more possible_buildargs
            container.buildargs['ENV'] = container.environment['ENV']

    def pre_start(self, host, instance, task):
        """
        Sets the following build args:
        - ENV
        """
        if 'ENV' in instance.container.environment:
            # TODO Allow for more possible_buildargs
            instance.environment['DD_ENV'] = instance.container.environment['ENV']


class _DockerLoginFailedException(Exception):

    def __init__(self, underlying_ex):
        super(_DockerLoginFailedException, self).__init__(underlying_ex)


class _RetryException(Exception):

    def __init__(self, msg, ex=None):
        super(_RetryException, self).__init__(ex)
        self.msg = msg

    def __str__(self):
        return self.msg


class _SupportedRegions(object):

    def __init__(self, regions, region_file_path):
        self._regions = regions
        self._region_file_path = region_file_path

    @property
    def regions(self):
        return self._regions

    @property
    def default_region(self):
        if not os.path.exists(self._region_file_path):
            return self._regions[0]
        with open(self._region_file_path, 'r') as fh:
            return fh.read().strip()

    @default_region.setter
    def default_region(self, value):
        if value not in self._regions:
            raise _RetryException(f'{value} region is invalid. Allowed values are {self._regions}')
        with open(self._region_file_path, 'w') as fh:
            fh.write(value + '\n')
        self._ecr_region = value


class AwsExternalSecretsHandler:
    """
    External Secrets handler
    Allows you to populate build arguments with values from AWS Secrets Manager
    """

    def __init__(self, app, data):
        self.app = app
        # Split the data string into variables
        self.data = data
        self.region_name = data['aws']['region'] if data and data.get('aws') else None

    def get_aws_secret(self, name, key):
        """
        Accesses AWS secrets api
        """
        secret_name = name
        region_name = self.region_name

        # Create a Secrets Manager client
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name=region_name
        )

        # In this sample we only handle the specific exceptions for the 'GetSecretValue' API.
        # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        # We rethrow the exception by default.

        try:
            get_secret_value_response = client.get_secret_value(
                SecretId=secret_name
            )
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'DecryptionFailureException':
                # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise e
            elif e.response['Error']['Code'] == 'InternalServiceErrorException':
                # An error occurred on the server side.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise e
            elif e.response['Error']['Code'] == 'InvalidParameterException':
                # You provided an invalid value for a parameter.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise e
            elif e.response['Error']['Code'] == 'InvalidRequestException':
                # You provided a parameter value that is not valid for the current state of the resource.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise e
            elif e.response['Error']['Code'] == 'ResourceNotFoundException':
                # We can't find the resource that you asked for.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise e
        else:
            # Decrypts secret using the associated KMS CMK.
            # Depending on whether the secret is a string or binary, one of these fields will be populated.
            if 'SecretString' in get_secret_value_response:
                secret = get_secret_value_response['SecretString']
                res = json.loads(secret)[key]
                return res
            else:
                decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])
                click.echo(YELLOW(F'decoded_binary_secret: {decoded_binary_secret}'))
                return decoded_binary_secret


class AwsRegistryHandler:
    """
    Registry handler for the aws-ecr scheme.
    """

    def __init__(self, app, data):
        self.app = app
        # Split the data string into individual variables
        self.registry_id, regions, self.namespace = data.split("|", 2)
        self.docker_url = ''
        self._supported_regions = _SupportedRegions(
            regions.split(','),
            os.path.join(self.app.config.get_path('ftl', 'user_data_path', self.app), 'region'),
        )

    def run_docker_login(self):
        try:
            docker_user, docker_password, docker_url = self.read_local_docker_creds()
            subprocess.run(
                f'echo {docker_password} | docker login -u {docker_user} --password-stdin {docker_url}',
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                check=True,
                shell=True,
            )
            return docker_url
        except subprocess.CalledProcessError as ex:
            raise _DockerLoginFailedException(ex)

    def url(self, host):
        """
        Returns the URL to the registry if the user is logged in,
        otherwise gives an error about why it cannot be used.
        """
        if not self.docker_url:
            # See if we already have valid docker credentials
            try:
                self.docker_url = self.run_docker_login()
            except (ValueError, _DockerLoginFailedException) as ex1:
                # ValueError: docker-creds not found -> only if user never logged into ECR
                # _DockerLoginFailedException: docker login error, once a day -> don't want to log this
                if not isinstance(ex1, _DockerLoginFailedException):
                    click.echo(RED(str(ex1)))
                # frist exception: attempt to renew the docker-creds and docker login
                try:
                    access_key, secret_key = self.read_local_aws_token()
                    docker_user, docker_password, self.docker_url = self.load_remote_docker_creds_from_ecr(
                        access_key,
                        secret_key,
                        self.registry_id,
                    )
                    self.write_local_docker_creds(docker_user, docker_password, self.docker_url)
                    self.docker_url = self.run_docker_login()
                except botocore.exceptions.EndpointConnectionError as connection_error:
                    click.echo(RED(f'Connection vailed: {connection_error}'))
                    sys.exit(1)
                except (ValueError, _DockerLoginFailedException) as ex2:
                    # ValueError: aws token not found -> once a month
                    # _DockerLoginFailedException: docker login error, once a day -> don't log this
                    if not isinstance(ex2, _DockerLoginFailedException):
                        click.echo(RED(str(ex2)))
                    # 2nd exception, the ECR token has expired or is missing
                    # promt user to login and renew all tokens
                    self.login(host, self.app.root_task)
                    self.docker_url = self.run_docker_login()
        return self.docker_url.split('://')[1].rstrip('/') + '/' + self.namespace

    def login(self, host, task):
        with task.paused_output():

            # Get AWS tokens from vault
            access_key, secret_key = self.load_remote_aws_token_from_awscli()
            self.write_local_aws_token(access_key, secret_key)
            click.echo('AWS tokens obtained')

            self._prompt_default_region_change()

            # Get Docker login token from Amazon
            docker_user, docker_password, docker_url = self.load_remote_docker_creds_from_ecr(
                access_key,
                secret_key,
                self.registry_id,
            )
            self.write_local_docker_creds(docker_user, docker_password, docker_url)
            click.echo('Docker credentials obtained')

            # Run docker login
            host.client.login(
                username=docker_user,
                password=docker_password,
                registry=docker_url,
                reauth=True,
            )

            click.echo("Login complete.")

    def _prompt_default_region_change(self):
        click.echo("Default region set to {}".format(self._supported_regions.default_region))
        # while True:
        #     region = click.prompt(
        #         "Please select the AWS region the closest to your location to speedup Docker images downloads." +
        #         "\nCurrent region is {}. Supported regions are {}. Leave blank for keeping current region".format(
        #             self._supported_regions.default_region,
        #             self._supported_regions.regions),
        #         default="")
        #     if not region.strip():
        #         return
        # try:
        #     self._supported_regions.default_region = region
        # except _RetryException as ex:
        #     click.echo(RED(ex.msg))
        # else:
        #     click.echo("Default region set to {}".format(self._supported_regions.default_region))
        #     return

    def read_local_docker_creds(self):
        """
        Gets docker creds for the current project
        """
        # See if there's a token written to disk
        docker_token_path = os.path.join(self.app.config.get_path('ftl', 'user_data_path', self.app), 'docker-creds')
        # Load the vault token if it exists
        if os.path.exists(docker_token_path):
            with open(docker_token_path, 'r') as fh:
                docker_user, docker_password, docker_url = fh.read().strip().split(':', 2)
        else:
            raise ValueError('No docker credentials stored')
        return docker_user, docker_password, docker_url

    def write_local_docker_creds(self, docker_user, docker_password, docker_url):
        """
        Saves docker creds to disk
        """
        vault_token_path = os.path.join(self.app.config.get_path('ftl', 'user_data_path', self.app), 'docker-creds')
        with open(vault_token_path, 'w') as fh:
            fh.write(f'{docker_user}:{docker_password}:{docker_url}\n')

    def load_remote_docker_creds_from_ecr(self, access_key, secret_key, registry_id):
        client = boto3.client(
            'ecr',
            region_name=self._supported_regions.default_region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        # IAM has a propagation delay, so keep retrying
        for _ in range(10):
            try:
                docker_credentials = client.get_authorization_token(registryIds=[registry_id])
            except botocore.exceptions.ClientError:
                time.sleep(2)
            else:
                break
        else:
            raise ValueError('Connot obtain docker login from ECR.')
        docker_user, docker_password = base64.b64decode(
            docker_credentials['authorizationData'][0]['authorizationToken']
        ).decode('ascii').split(':', 1)
        docker_url = docker_credentials['authorizationData'][0]['proxyEndpoint']
        return docker_user, docker_password, docker_url

    def read_local_aws_token(self):
        """
        Loads an AWS ECR token pair from disk, returns None if there are no vault tokens stored.
        """
        ecr_token_path = os.path.join(self.app.config.get_path('ftl', 'user_data_path', self.app), 'aws-token')
        if not os.path.exists(ecr_token_path):
            raise ValueError('No ECR token stored')
        with open(ecr_token_path, 'r') as fh:
            return fh.read().strip().split(':', 1)

    def write_local_aws_token(self, access_key, secret_key):
        """
        Persists an AWS ECR token to disk.
        """
        # See if there is a token written to disk
        ecr_token_path = os.path.join(self.app.config.get_path('ftl', 'user_data_path', self.app), 'aws-token')
        with open(ecr_token_path, 'w') as fh:
            fh.write(f'{access_key}:{secret_key}')

    def load_remote_aws_token_from_awscli(self):
        """
        Fetches AWS Credentials from AWS CLI Configure
        """
        access_key, secret_key = None, None
        # res = os.path.expanduser('~/.aws/credentials')
        awscli_config_path = os.path.abspath(os.path.expanduser('~/.aws/credentials'))
        # click.echo(f'{awscli_config_path}')
        if not os.path.isfile(awscli_config_path):
            if 'AWS_ACCESS_KEY_ID' in os.environ and \
                    'AWS_SECRET_ACCESS_KEY' in os.environ:
                access_key = os.getenv('AWS_ACCESS_KEY_ID')
                secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
                return access_key, secret_key
            else:
                raise ValueError(f'No awscli credentails stored in {awscli_config_path}')
        with open(awscli_config_path, 'r') as fh:
            content = fh.read().strip().split('\n')
            for item in content:
                if 'aws_access_key_id' in item:
                    access_key = item.split('=', 1)[1].strip()
                elif 'aws_secret_access_key' in item:
                    secret_key = item.split('=', 1)[1].strip()
        return access_key, secret_key
