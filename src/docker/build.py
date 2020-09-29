import datetime
import io
import json
import logging
import os
import tarfile
import tempfile
import attr

from docker.utils import exclude_paths
from ..cli.colors import CYAN, remove_ansi
from ..cli.tasks import Task
from ..constants import PluginHook
from ..exceptions import BuildFailureError, FailedCommandException


class TaskExtraInfoHandler(logging.Handler):
    """
    Custom log handler that emits to a task's extra info.
    """

    def __init__(self, task):
        super(TaskExtraInfoHandler, self).__init__()
        self.task = task

    def emit(self, record):
        text = self.format(record)
        # Sanitise that text and make it short-ish
        text = remove_ansi(text).replace('\n', '').replace('\r', '').strip()[:80]
        self.task.set_extra_info(
            self.task.extra_info[-3:] + [text]
        )


@attr.s
class Builder:
    """
    Build an image from a single container.
    """
    host = attr.ib()
    container = attr.ib()
    app = attr.ib()
    logfile_name = attr.ib()
    parent_task = attr.ib()
    # Set docker_cache to False to force docker to rebuild every layer.
    docker_cache = attr.ib(default=True)
    verbose = attr.ib(default=False)
    logger = attr.ib(init=False)

    def __attrs_post_init__(self):
        self.logger = logging.getLogger('build_logger')
        self.logger.setLevel(logging.INFO)
        # Close all old logging handlers
        if self.logger.handlers:
            [handler.close() for handler in self.logger.handlers]
            self.logger.handlers = []
        # Add build log file handler
        file_handler = logging.FileHandler(self.logfile_name)
        self.logger.addHandler(file_handler)
        # Optionally add task (console) log handler
        self.task = Task(
            'Building {}'.format(CYAN(self.container.name)),
            parent=self.parent_task,
            collapse_if_finished=True,
        )
        if self.verbose:
            self.logger.addHandler(TaskExtraInfoHandler(self.task))

    def build(self):
        """
        Runs the build process and raises BuildFailureerror if it fails.
        """
        self.logger.info('Building image {}'.format(self.container.name))
        build_successful = True
        progress = 0
        start_time = datetime.datetime.now().replace(microsecond=0)
        self.app.run_hooks(PluginHook.PRE_BUILD, host=self.host, container=self.container, task=self.task)
        try:
            # Prep normalised context
            build_context = self.make_build_context()
            # Run build
            result = self.host.client.build(
                self.container.path,
                dockerfile=self.container.dockerfile_name,
                tag=self.container.image_name_tagged,
                nocache=not self.docker_cache,
                rm=True,
                # stream=True,
                custom_context=True,
                encoding="gzip",
                fileobj=build_context,
                buildargs=self.container.buildargs,
                # If the parent image is not in prefix, pull it during build
                pull=not self.container.build_parent_in_prefix,
            )
            with self.task.rate_limit() as limited_task:
                self.logger.task = limited_task
                for data in result:
                    # Make sure data is a string
                    if isinstance(data, bytes):
                        data = data.decode('utf8')
                    # Deal with any potential double chunks
                    data_buffer = ''
                    for data_segment in data.strip().split('\r\n'):
                        data_buffer += data_segment
                        try:
                            data_obj = json.loads(data_buffer.strip())
                            data_buffer = ''
                        except json.decoder.JSONDecodeError:
                            # Deal with incomplete segments, perhaps ends in subsequent segments
                            continue
                        if 'stream' in data_obj:
                            # docker data stream has extra newlines in it
                            # we will strip them before logging.
                            self.logger.info(data_obj['stream'].rstrip())
                            if data_obj['stream'].startswith('Step '):
                                progress += 1
                                self.task.update(status='.' * progress)
                        if 'error' in data_obj:
                            self.logger.info(data_obj['error'].rstrip())
                            build_successful = False
                self.logger.task = self.task
            # always tag built image as 'latest'.
            # if the image is referenced in a FROM statement,
            # it would find it even if the version is not set in the 'FROM' statement.
            if build_successful and self.container.image_tag != 'latest':
                self.host.client.tag(self.container.image_name_tagged,
                self.container.image_name, tag='latest', force=True)
            else:
                raise FailedCommandException
        except FailedCommandException:
            message = 'Build FAILED for image{}!'.format(self.container.name)
            self.logger.info(message)
            self.task.finish(status='FAILED', status_flavor=Task.FLAVOR_BAD)
            raise BuildFailureError(message)
        else:
            # Run post-build hooks
            self.app.run_hooks(PluginHook.POST_BUILD, host=self.host, container=self.container, task=self.task)
            # Print out end-of-build message
            end_time = datetime.datetime.now().replace(microsecond=0)
            time_delta_str = str(end_time - start_time)
            if time_delta_str.startswith('0:'):
                # no point in showing hours, unless it runs for more than one hour
                time_delta_str = time_delta_str[2:]
            build_completion_message = 'Build time for {image_name} image: {build_time}'.format(
                image_name=self.container.name,
                build_time=time_delta_str,
            )
            self.logger.info(build_completion_message)
            # Close out the task
            self.task.finish(status='Done [{}]'.format(time_delta_str), status_flavor=Task.FLAVOR_GOOD)

    def make_build_context(self):
        """
        Makes a Docker build context from a local director.
        Normalises all file ownership and times so that the docker hashes align
        better.
        """
        # Start temporary tar file
        fileobj = tempfile.NamedTemporaryFile()
        tfile = tarfile.open(mode='w:gz', fileobj=fileobj)
        # Get list of files/dirs to add to the tar
        paths = exclude_paths(self.container.path, [])
        # For each file, add it to the tar with normalisation
        for path in paths:
            disk_location = os.path.join(self.container.path, path)
            # For Kubernetes images, use original date values for source code
            user_real_time = (
                'FTL_BUILD_SRC_REAL_TIME' in os.environ
                and os.environ['FTL_BUILD_SRC_REAL_TIME'] == 'true'
                and "/src/" in disk_location
            )
            # Directory addition
            if os.path.isdir(disk_location):
                info = tarfile.TarInfo(name=path)
                info.mtime = (0, os.stat(disk_location).st_mtime)[user_real_time]
                info.mode = 0o775
                info.type = tarfile.DIRTYPE
                info.uid = 0
                info.gid = 0
                info.uname = 'root'
                info.gname = 'root'
                tfile.addfile(info)
            # Normal file addition
            elif os.path.isfile(disk_location):
                stat = os.stat(disk_location)
                info = tarfile.TarInfo(name=path)
                info.mtime = (0, stat.st_mtime)[user_real_time]
                info.size = stat.st_size
                info.mode = 0o775
                info.type = tarfile.REGTYPE
                info.uid = 0
                info.gid = 0
                info.uname = 'root'
                info.gname = 'root'
                # Rewrite docker FROM lines with a : in them and raise a warning
                # TODO: Deprecate this!
                if path.lstrip('/') == self.container.dockerfile_name:
                    # Read in dockerfile line by line, replacing the FROM line
                    dockerfile = io.BytesIO()
                    with open(disk_location, 'r') as fh:
                        for line in fh:
                            if line.upper().startswith('FROM') and self.container.build_parent_in_prefix:
                                line = line.replace(':', '-')
                            dockerfile.write(line.encode('utf8'))
                    dockerfile.seek(0)
                    tfile.addfile(info, dockerfile)
                else:
                    with open(disk_location, 'rb') as fh:
                        tfile.addfile(info, fh)
            # Ignore symlinks
            elif os.path.islink(disk_location):
                pass
            # Error for anything else
            else:
                raise ValueError(
                    'Cannot add non-file/dir {} to docker build context'.format(path)
                )
        # Return that tarfile
        tfile.close()
        fileobj.seek(0)
        return fileobj
