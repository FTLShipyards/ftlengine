class BadConfigError(Exception):
    """
    Raised when a config file is misformatted or mis-typed.
    """
    pass


class FailedCommandException(Exception):
    def __init__(self, source=None, msg=None):
        self.source = source

    def __str__(self):
        return str(self.source)

    def __repr__(self):
        return "<FailedCommandException %s>" % (self,)


class NotFoundException(FailedCommandException):
    pass


class DockerAccessException(FailedCommandException):
    """
    Raised when the docker socket is inaccessible.
    """

    def __init__(self, source, msg=''):
        super(DockerAccessException, self).__init__(source=source)
        self.msg = msg


class BuildFailureError(Exception):
    """
    Raised when a container fails to build.
    """


class DockerRuntimeError(Exception):
    """
    Raised when the Docker status cannot be correctly understood or something
    fails during the run process.
    """

    def __init__(self, message, code=None, instance=None):
        super(DockerRuntimeError, self).__init__(message)
        self.code = code
        self.instance = instance
        self.message = message


class ContainerBootFailure(DockerRuntimeError):
    """
    Container died while trying to boot
    """


class RegistryRequiresLogin(Exception):
    """
    Raised by a registry handler when a registry has not been logged in to
    and so cannot be used.
    """


class ImageNotFoundException(Exception):
    """
    Raised when the image requested does not exist on the docker host being
    talked to.
    """

    def __init__(self, message, image=None, image_tag=None, container=None):
        super(ImageNotFoundException, self).__init__(message)
        self.image = image
        self.image_tag = image_tag
        self.container = container


class ImagePullFailure(Exception):
    """
    Raised when the image fails to be pulled or tagged from the docker
    remote registry.
    """

    def __init__(self, message, remote_name=None, image_tag=None):
        super(ImagePullFailure, self).__init__(message)
        self.remote_name = remote_name
        self.image_tag = image_tag


class DockerInteractiveException(Exception):
    """
    Raised when a starting thread wants to run an interactive session.
    """

    def __init__(self, handler):
        self.handler = handler


class DockerNotAvailableError(Exception):
    """
    Raised when Docker is not available (the socket/machine is gone)
    """
