import re
import os
import warnings
import yaml
import attr

from ..exceptions import BadConfigError
from .volumes import BoundVolume, DevMode, NamedVolume


@attr.s(hash=True)
class Container:
    """
    Represents a single container type that's available to run (not a running container -
    we call those Instances).

    All containers are backed by a local disk directory containing their information,
    even if the actual running server is remote.
    """
    parent_pattern = re.compile(r'^FROM\s+([\S/]+)', re.IGNORECASE)
    git_volume_pattern = re.compile(r'^\{git@gitlab.com:[\w\d_-]*/([\w\s\-]+).git\}(.*)$')

    graph = attr.ib(repr=False, hash=False, eq=False, order=False)
    path = attr.ib(repr=False, hash=True)
    suffix = attr.ib(repr=False, hash=False, eq=False, order=False)
    dockerfile_name = attr.ib(repr=False, hash=False, eq=False, order=False)
    name = attr.ib(init=False, repr=True, hash=True)

    def __attrs_post_init__(self):
        self.load()

    @classmethod
    def from_directory(cls, graph, path):
        """
        Creates a set of one or more Container objects from a source directory.
        The "versions" key in the ftl.yaml file can mean there are multiple variants
        of the container, and we treat each separately (though they share a build
        directory and ftl.yaml settings)
        """
        versions = {None: "Dockerfile"}
        # Read config and get out any non-default versions
        config_path = os.path.join(path, "ftl.yaml")
        if os.path.isfile(config_path):
            # Read out config, making sure a empty file (None) appears as empty dict
            with open(config_path, "r") as fh:
                config_data = yaml.safe_load(fh.read()) or {}
                # Merges extra versions in config file into versions dict
                versions.update({
                    str(suffix): dockerfile_name
                    for suffix, dockerfile_name in config_data.get("versions", {}).items()
                })
        # For each version, make a Container class for it, and return the list of them
        return [
            cls(graph, path, suffix, dockerfile_name)
            for suffix, dockerfile_name in versions.items()
        ]

    def load(self):
        """
        Loads information from the container's files.
        """
        # Work out paths to key files, make sure they exist
        self.dockerfile_path = os.path.join(self.path, self.dockerfile_name)
        self.config_path = os.path.join(self.path, "ftl.yaml")
        if not os.path.isfile(self.dockerfile_path):
            raise BadConfigError("Cannot find Dockerfile for container %s" % self.path)
        # Calculate name from path component
        if self.suffix is None:
            self.name = os.path.basename(self.path)
        else:
            self.name = os.path.basename(self.path) + "-" + self.suffix
        self.image_name = '{prefix}/{name}'.format(
            prefix=self.graph.prefix,
            name=self.name,
        )
        # Load parent image and possible build args from Dockerfile
        self.possible_buildargs = set()
        self.build_parent = None
        with open(self.dockerfile_path, "r") as fh:
            for line in fh:
                parent_match = self.parent_pattern.match(line)
                if parent_match:
                    self.build_parent = parent_match.group(1)
                    # Make sure any ":" in the parent is changed to a "-"
                    # TODO: Add warning here once we've converted enough of the dockerfiles
                    self.build_parent = self.build_parent.replace(":", "-")
                elif line.lower().startswith("arg "):
                    self.possible_buildargs.add(line.split()[1])
        if self.build_parent is None:
            raise BadConfigError("Container {} has no valid FROM line".format(self.path))
        self.build_parent_in_prefix = self.build_parent.startswith(self.graph.prefix + '/')
        # Ensure it does not have an old-style multi version inheritance
        if self.build_parent_in_prefix and ":" in self.build_parent:
            raise BadConfigError(
                "Container {} has versioned build parent - it should be converted to just a name."
                .format(self.path),
            )
        # Load information from ftl.yaml file
        if os.path.isfile(self.config_path):
            with open(self.config_path, "r") as fh:
                config_data = yaml.safe_load(fh.read()) or {}
        else:
            config_data = {}
        # Calculate links
        # TODO: Remove old, deprecated links format.
        self.links = {}
        config_links = config_data.get("links", {})
        if isinstance(config_links, list):
            warnings.warn("Old links format in {}".format(self.config_path))
            # Old list format
            for link_name in config_links:
                self.links[link_name] = {"required": True}
        else:
            # New links format
            for link_name in (config_links.get("required") or []):
                self.links[link_name] = {"required": True}
            for link_name in (config_links.get("optional") or []):
                self.links[link_name] = {"optional": True}
        # Old extra links key
        config_extra_links = config_data.get("extra_links", [])
        if config_extra_links:
            warnings.warn("Old extra_links format in {}".format(self.config_path))
        # Parse waits from the config format
        self.waits = []
        for wait_dict in config_data.get("waits", []):
            for wait_type, params in wait_dict.items():
                if not isinstance(params, dict):
                    # TODO: Deprecate non-dictionary params
                    if wait_type == "time":
                        params = {"seconds": params}
                    else:
                        params = {"port": params}
                self.waits.append({"type": wait_type, "params": params})
        # Volumes is a dict of {container mountpoint: volume name/host path}
        self._bound_volumes = {}
        self._named_volumes = {}
        for mount_point, options in config_data.get("volumes", {}).items():
            options = self._parse_volume_options(options)
            # Split named volumes and directory nounts up
            try:
                if "/" in options["source"]:
                    self._bound_volumes[mount_point] = BoundVolume(**options)
                else:
                    self._named_volumes[mount_point] = NamedVolume(**options)
            except TypeError as e:
                raise BadConfigError("Invalid configuration for volume at {}: {}".format(
                    mount_point,
                    e,
                ))
        # Volumes_mount is a deprecated key from the old buildable volumes system.
        # They turn into named volumes.
        # TODO: Deprecate volumes_mount
        # for mount_point, source in config_data.get("volumes_mount", {}).items():
        #     self._named_volumes[mount_point] = source
        # Devmodes might also have git URLs
        self._devmodes = {}
        for name, mounts in config_data.get("devmodes", {}).items():
            # Allow for empty devmodes
            if not mounts:
                continue
            # Add each mount individually
            self._devmodes[name] = {}
            for mount_point, options in mounts.items():
                options = self._parse_volume_options(options)
                try:
                    self._devmodes[name][mount_point] = DevMode(**options)
                except TypeError as e:
                    raise BadConfigError("Invalid configuration for devmode {}: {}".format(
                        name,
                        e,
                    ))
        # Ports is a dict of {port on container: host exposed port}
        self.ports = config_data.get("ports", {})
        # A list of checks to run before allowing a build (often for network connectivity)
        self.build_checks = config_data.get("build_checks", [])
        # If the container should launch into a foreground shell with its CMD when run,
        # rather than starting up in the background. Useful for test suites etc.
        self.foreground = config_data.get("foreground", False)
        # The image tage to use on the docker image. "local" is a special value that
        # resolves to "latest" without ever attempting to pull.
        self.image_tag = config_data.get("image_tag", "local")
        # image name including tag: format {image_name}:{tag}
        self.image_name_tagged = "{image_name}:{tag}".format(
            image_name=self.image_name,
            tag=self.image_tag if self.image_tag else 'latest'
        )
        # Environment variables to send to the container
        self.environment = config_data.get("environment", {})
        # Fast kill says if the container is safe to kill immediately
        self.fast_kill = config_data.get("fast_kill", False)
        # System says if the container is a supporting "system" container, and lives
        # and runs outside of the profiles (e.g., it's ignored by ftl restart or ftl up)
        self.system = config_data.get("system", False)
        # Abstract says if the container is not intended to ever be run or linked to,
        # just used as a base for other containers
        self.abstract = config_data.get("abstract", False)
        # Build args to pass into the container; right now, these are only
        # settable by plugins.
        self.buildargs = {}
        # Store all extra data so plugins can get to it
        self.mem_limit = config_data.get("mem_limit", 0)
        self.extra_data = {
            key: value
            for key, value in config_data.items()
            if key not in {
                "ports",
                "build_checks",
                "devmodes",
                "foreground",
                "links",
                "waits",
                "volumes",
                "image_tag",
                "mem_limit",
            }
        }

    def _parse_volume_options(self, options):
        # If the value is a string, treat it as the source and use default options
        if isinstance(options, str):
            options = {
                "source": options,
            }
        # Old-style git link
        # TODO: Add warning here once we've converted onough of the dockerfiles?
        git_match = self.git_volume_pattern.match(options["source"])
        if git_match:
            options["source"] = "../{}/{}".format(
                git_match.group(1),
                git_match.group(2).lstrip("/"),
            )
        if "/" in options["source"]:
            # support environment variables in the source, eg $HOME/directory
            source = os.path.expandvars(options["source"])
            # Allow the volume mount root to be different if needed (e.g., Windows)
            if os.environ.get("FTL_VOLUME_HOME"):
                options["source"] = os.path.join(os.environ["FTL_VOLUME_HOME"], source)
            else:
                options["source"] = os.path.abspath(os.path.join(self.graph.path, source))
        return options

    def get_parent_value(self, name, default):
        """
        Shortcut for getting inherited values from parents with a fallback.
        """
        if self.build_parent_in_prefix:
            return getattr(self.graph.build_parent(self), name)
        else:
            return default

    def get_ancestral_extra_data(self, key):
        """
        Returns a list of all extra data values with "key" from this container
        up through all build parents.
        """
        if self.build_parent_in_prefix:
            result = self.graph.build_parent(self).get_ancestral_extra_data(key)
            if key in self.extra_data:
                result.append(self.extra_data[key])
            return result
        elif key in self.extra_data:
            return [self.extra_data[key]]
        else:
            return []

    def get_named_volume_path(self, volume_name):
        """
        Returns the mount path, given a volume name.

        Raises an error if the volume_name provided is not mounted.
        """
        for path, name in self.named_volumes.items():
            if name == volume_name:
                return path
        raise ValueError("{} is not mounted".format(volume_name))

    @property
    def bound_volumes(self):
        value = self.get_parent_value("bound_volumes", {})
        value.update(self._bound_volumes)
        return value

    @property
    def named_volumes(self):
        value = self.get_parent_value("named_volumes", {})
        value.update(self._named_volumes)
        return value

    @property
    def devmodes(self):
        value = self.get_parent_value("devmodes", {})
        value.update(self._devmodes)
        return value
