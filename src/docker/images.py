import attr
import click
import datetime
import json
import os
import sys

from docker.errors import NotFound, APIError
from ..cli.colors import RED
from ..cli.tasks import Task
from ..exceptions import ImageNotFoundException, ImagePullFailure, BadConfigError


def convert_to_json_stream(stream):
    for lines in stream:
        if isinstance(lines, bytes):
            lines = lines.decode('ascii')
        for line in lines.splitlines():
            yield json.loads(line)


@attr.s
class ImageRepository:
    """
    Arepository of available images for containers.

    Recommended use is internal-only by the plugins, do not use directly.
    """
    host = attr.ib()
    images = attr.ib(default=attr.Factory(dict))
    registry = None

    def list_images(self):
        """
        List all available images.
        """
        raise NotImplementedError()

    def add_image(self, image_name, version, image_hash):
        """
        Add a hash for a given image_name and version.

        This will update any existing hash for an image that was previously
        added to the image repository instance.
        """
        raise NotImplementedError()

    def image_versions(self, image_name):
        """
        Returns a dictionary of version name mapped to the image hash for a
        given image name. May return empty dictionary if there are no images.
        """
        # TODO: Expand to read all tags locally, not just a fixed list
        try:
            return {'latest': self.image_version(image_name, 'latest')}
        except ImageNotFoundException:
            return {}

    def get_registry(self, app):
        """
        Given an app, returns the registry handler responsible for handling it
        (or None if it does not need a handler)
        """
        # if no registry key is defined in the configuration, return
        if not app.containers.registry:
            return None
        # cache the registry object so that it is not recreated
        # during each image pull, which would re-execute a docker login
        # for each pull (it takes 3-5 seconds)
        if not self.registry:
            # Work out what registry plugin to use
            plugin_name, registry_data = app.containers.registry.split(':', 1)
            # Call the plugin to log in/etc to the registry
            registry_plugins = app.get_catalog_items('registry')
            if plugin_name == 'plain':
                # The 'plain' plugin is a shortcut for 'no plugin'
                self.registry = BasicRegistryHandler(app, registry_data)
            elif plugin_name in registry_plugins:
                self.registry = registry_plugins[plugin_name](app, registry_data)
            else:
                raise BadConfigError('No registry plugin for {} loaded'.format(plugin_name))
        return self.registry

    def pull_image_version(self, app, image_name, image_tag, parent_task, fail_silently=False):
        """
        Pulls the most recent verison of the given image tag from remote
        docker registry.
        """
        start_time = datetime.datetime.now().replace(microsecond=0)
        assert isinstance(image_name, str)
        assert isinstance(image_tag, str)
        # The string 'local' has a special meaning which means the most recent
        # local image of that name, so we skip the remote call/check.
        if image_tag == 'local':
            if fail_silently:
                return None
            else:
                raise ImagePullFailure(
                    'Cannot pull a local image',
                    remote_name=None,
                    image_tag=image_tag,
                )
        # Check if the image already exists locally
        # This is an optimization to save a trip to the registry: 1-2 sec per image
        if image_tag != 'latest':
            try:
                self.host.images.image_version(image_name, image_tag)
                return None
            except ImageNotFoundException:
                # The image will be pulled from the registry
                pass
        registry = self.get_registry(app)
        # See if the registry is willing to give us a URL (it's logged in)
        if registry:
            registry_url = registry.url(self.host)
        else:
            registry_url = None
        if registry_url is None:
            if fail_silently:
                return None
            else:
                raise ImagePullFailure(
                    'No registry configured',
                    remote_name=None,
                    image_tag=image_tag,
                )
        task = Task(
            'Pulling remote image {}: {}'.format(image_name, image_tag),
            parent=parent_task,
            progress_formatter=lambda x: '{} MB'.format(x // (1024 ** 2)),
        )
        remote_name = f'{registry_url}{image_name}'
        stream = self._pull(app, task, remote_name, image_tag)
        layer_status = {}
        current = None
        total = None
        for json_line in convert_to_json_stream(stream):
            if 'error' in json_line:
                task.finish(status='Failed', status_flavor=Task.FLAVOR_WARNING)
                if fail_silently:
                    return
                else:
                    raise ImagePullFailure(
                        json_line['error'],
                        remote_name=remote_name,
                        image_tag=image_tag,
                    )
            elif 'id' in json_line:
                if json_line['status'].lower() == 'downloading':
                    layer_status[json_line['id']] = json_line['progressDetail']
                elif 'complete' in json_line['status'].lower() and json_line['id'] in layer_status:
                    layer_status[json_line['id']]['current'] = layer_status[json_line['id']]['total']
                if layer_status:
                    statuses = [x for x in layer_status.values() if 'current' in x and 'total' in x]
                    current = sum(x['current'] for x in statuses)
                    total = sum(x['total'] for x in statuses)
                if total is not None:
                    task.update(progress=(current, total))
        end_time = datetime.datetime.now().replace(microsecond=0)
        time_delta_str = str(end_time - start_time)
        if time_delta_str.startswith('0:'):
            time_delta_str = time_delta_str[2:]
        task.finish(status='Done [{}]'.format(time_delta_str), status_flavor=Task.FLAVOR_GOOD)
        # Tag the remote image as the right name
        self._tag_image(remote_name, image_tag, image_name, image_tag, fail_silently)
        self._tag_image(remote_name, image_tag, image_name, 'latest', fail_silently)

    def _pull(self, app, task, remote_name, image_tag, tries=0):
        # this method is called recursively in case the docker credentials expire
        # let's not run it more than 3 times in a row, we don't want an infinite loop here
        # if there is a problem on the remote repository side
        if (tries > 2):
            task.update(status='Too many failures while pulling', status_flavor=Task.FLAVOR_WARNING)
            raise ImagePullFailure('Too many failures while pulling', remote_name=remote_name, image_tag=image_tag)
        try:
            return self.host.client.pull(remote_name, tag=image_tag, stream=True)
        except NotFound as error:
            # we should always have Docker images uploaded on ECR, but if for some
            # reason the image can't be found, we raise an error and it will get build
            # instead
            if 'FTL_NO_REGISTRY' not in os.environ:
                # Sometimes docker python client fails with NotFound error while trying to pull
                # an image without having valid credentials.
                # For the user, it means that all the static images would be build locally. It's a long process.
                # We want to fail fast in that case and give the user the chance to login to the registry.
                click.echo(RED('Cannot pull image {}:{}.'.format(remote_name, image_tag)))
                click.secho('To fix this, please run `ftl registry login`.', bold=True)
                click.echo('To proceed without registry, export FTL_NO_REGISTRY=yes and try again')
                sys.exit(1)
            task.update(status='Not found', status_flavor=Task.FLAVOR_WARNING)
            raise ImagePullFailure(error, remote_name=remote_name, image_tag=image_tag)
        except APIError as error:
            if 'credentials' in str(error):
                # the docker credentials expired while pulling, get a new registry,
                # login again and try pulling again
                self.registry = None
                self.get_registry(app)
                self.registry.url(self.host)
                tries += 1
                return self._pull(app, task, remote_name, image_tag, tries)
            else:
                task.update(status=str(error) + f'{remote_name}', status_flavor=Task.FLAVOR_WARNING)
                raise ImagePullFailure(error, remote_name=remote_name, image_tag=image_tag)

    def _tag_image(self, source_image, source_tag, target_image, target_tag, fail_silently):
        try:
            self.host.client.tag(
                source_image + ':' + source_tag,
                target_image,
                tag=target_tag,
                force=True,
            )
        except NotFound:
            if fail_silently:
                return
            else:
                raise ImagePullFailure(
                    'Failed to tag {}:{}'.format(source_image, source_tag),
                    remote_name=source_image,
                    image_tag=source_tag,
                )

    def image_version(self, image_name, image_tag, ignore_not_found=False):
        """
        Returns the Docker image hash of the requested image and tag, or
        raises ImageNotFoundException if it's not available on the host.
        """
        if image_tag == 'local':
            image_tag = 'latest'
        try:
            docker_info = self.host.client.inspect_image('{}:{}'.format(image_name, image_tag))
            return docker_info['Id']
        except NotFound:
            # TODO: Maybe auto-build if we can?
            if ignore_not_found:
                return None
            else:
                raise ImageNotFoundException(
                    'Cannot find image {}:{}'.format(image_name, image_tag),
                    image=image_name,
                    image_tag=image_tag,
                )

    def push_image_verison(self, app, image_name, image_tag, parent_task):
        """
        Pushes the given image version up to the repository
        """
        assert isinstance(image_name, str)
        assert isinstance(image_tag, str)
        # The string 'local' has a special meaning which means the most recent
        # local image of that name, so we skip the remote call/check.
        if image_tag == 'local':
            raise ValueError('You cannot push the local version')
        # See if the registry is willing to give us a URL (it's logged in)
        registry = self.get_registry(app)
        if registry:
            registry_url = registry.url(self.host)
        else:
            registry_url = None
        if registry_url is None:
            raise RuntimeError('No registry configured')
        task = Task(
            'Pushing image {}:{}'.format(image_name, image_tag),
            parent=parent_task,
            progress_formatter=lambda x: '{} MB'.format(x // (1024 ** 2)),
        )
        # Work out the name it needs to be and tag the image as that
        remote_name = '{registry_url}/{image_name}'.format(
            registry_url=registry_url,
            image_name=image_name,
        )
        self.host.client.tag(
            image_name + ":" + "latest",
            remote_name,
            tag=image_tag,
            force=True
        )
        # Push it up
        stream = self.host.client.push(remote_name, tag=image_tag, stream=True)
        layer_status = {}
        current = None
        total = None
        for line in stream:
            if isinstance(line, bytes):
                line = line.decode('ascii')
            data = json.loads(line)
            if 'error' in data:
                task.finish(status='Failed', status_flavor=Task.FLAVOR_WARNING)
                raise RuntimeError('Push error: %r' % data['errpr'])
            elif 'id' in data:
                if data['status'].lower() == 'pushing':
                    layer_status[data['id']] = data['progressDetail']
                elif 'complete' in data['status'].lower() and data['id'] in layer_status:
                    layer_status[data['id']]['current'] = layer_status[data['id']]['total']
                if layer_status:
                    statuses = [x for x in layer_status.values()
                                if 'current' in x and 'total' in x]
                    current = sum(x['current'] for x in statuses)
                    total = sum(x['total'] for x in statuses)
                if total is not None:
                    task.update(progress=(current, total))
        task.finish(status='Done', status_flavor=Task.FLAVOR_GOOD)


class BasicRegistryHandler:
    """
    Handler for basic (normal Docker) image registries
    """

    def __init__(self, app, data):
        self.registry_url = data

    def url(self, host):
        return self.registry_url

    def login(self, host, task):
        click.echo('Registry does not need a login')

    def logout(self, host, task):
        click.echo('Registry does not need a login')
