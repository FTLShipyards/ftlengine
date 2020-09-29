import os
import warnings
import yaml
import attr

from ..exceptions import BadConfigError


@attr.s
class Profile:
    """
    Represents a profile - a way of running containers based on a base graph.

    A profile comes from a single config file, and then applies changes from that
    to a ContainerGraph. Multiple profiles might be used one after the other.
    """
    file_path = attr.ib(default=None)
    load_immediately = attr.ib(default=True)
    default_boot_compatability = attr.ib(default=False)
    parent_profile = attr.ib(default=None, init=False)
    description = attr.ib(default=None, init=False)
    version = attr.ib(default=None, init=False)
    containers = attr.ib(default=attr.Factory(dict), init=False)
    # Ignore the required dependencies coming from the container(s) ftl.yaml
    ignore_dependencies = attr.ib(default=False, init=False)

    def __attrs_post_init__(self):
        if self.load_immediately:
            self.load()
        if self.file_path:
            self.name = os.path.basename(self.file_path).split(".")[0]
        else:
            self.name = "<empty>"

    def load(self):
        """
        Loads the profile data from a YAML file
        """
        # Read in file
        with open(self.file_path, "r") as fh:
            data = yaml.safe_load(fh.read())
        if data is None:
            return
        # Parse container details
        try:
            self.parent_profile = data.get("inherits", data.get("name"))
        except AttributeError:
            self.parent_profile = None  # The parent profile is a null.
        self.description = data.get("description")
        self.version = data.get("min-version")
        self.ignore_dependencies = data.get("ignore-dependencies")
        for name, details in data.get("containers", {}).items():
            if details is None:
                details = {}
            self.containers[name] = {
                "links": details.get("links") or {},
                "devmodes": set(details.get("devmodes") or []),
                "ports": details.get("ports") or {},
                "environment": details.get("environment") or {},
                "ephemeral": details.get("ephemeral") or False,
                "default_boot": details.get("default_boot"),
            }
            # Make sure links has dicts for the right things
            self.containers[name]["links"].setdefault("optional", [])
            self.containers[name]["links"].setdefault("required", [])
            # Merge legacy settings into those
            # TODO: Remove old profile links format
            if "ignore_links" in details:
                warnings.warn("Old-format ignore_links detected in {}".format(self.file_path))
                self.containers[name]["links"]["optional"].extend(details["ignore_links"])
            if "extra_links" in details:
                warnings.warn("Old-format extra_links detected in {}".format(self.file_path))
                self.containers[name]["links"]["required"].extend(details["extra_links"])
            if "mem_limit" in details:
                self.containers[name]["mem_limit"] = details["mem_limit"]

    def dump(self):
        data = {
            "name": self.parent_profile,
        }
        containers = {}

        for container_name, container_data in self.containers.items():
            if container_data and not container_data.get("ephemeral"):
                container_details_to_write = {}
                for k, v in container_data.items():
                    # Only write out links if populated
                    if k == "links":
                        if v['optional']:
                            container_details_to_write.setdefault('links', {})
                            container_details_to_write['links']['optional'] = sorted(v['optional'])
                        if v['required']:
                            container_details_to_write.setdefault('links', {})
                            container_details_to_write['links']['required'] = sorted(v['required'])
                    # Serialize sets as sored lists
                    elif v:
                        if isinstance(v, set):
                            container_details_to_write[k] = sorted(v)
                        else:
                            container_details_to_write[k] = v
                if container_details_to_write:
                    containers[container_name] = container_details_to_write
        if containers:
            data['containers'] = containers
        if self.version:
            data['min-version'] = self.version
        return data

    def apply(self, graph):
        """
        Applies the profile to the given graph
        """
        self.graph = graph
        for name, details in self.containers.items():
            try:
                container = self.graph[name]
            except KeyError:
                continue
            # Apply container links
            if "links" in details:
                if details["links"]["required"] or details["links"]["optional"]:
                    self.graph.set_dependencies(
                        container,
                        [self.graph[link]
                         for link in self.calculate_links(container)],
                    )
            # Set flag saying it's specified in a profile (for ftl build
            # profile) - not set for the user profile for now
            # TODO: remove user profile restriction with default boot compat stuff
            if self.default_boot_compatability:
                self.graph.set_option(container, "in_profile", True)
            # Set default boot mode
            if details.get("default_boot") is not None:
                self.graph.set_option(container, "default_boot", bool(details["default_boot"]))
            else:
                # TODO: Remove this temporary fix that allows parent profiles
                # default boot based on just having the container in the profile
                # (provided it is not a foreground container)
                if not container.foreground and self.default_boot_compatability:
                    self.graph.set_option(container, "default_boot", True)
            # Set devmodes
            self.graph.set_option(container, "devmodes", details["devmodes"])
            # Set ports to apply
            if "ports" in details:
                for a, b in details["ports"].items():
                    try:
                        container.ports[int(a)] = int(b)
                    except TypeError:
                        raise BadConfigError("Profile contains invalid ports for {}: {}".format(a, b))
            # Apply any image tag override
            if "image_tag" in details:
                container.image_tag = details["image_tag"]
            # Store environment variables
            for key, value in details.get("environment", {}).items():
                container.environment[key] = value
            if "mem_limit" in details:
                container.mem_limit = details["mem_limit"]

    def calculate_links(self, container):
        """
        Works out what links the container should have
        """
        # Check that they are all valid links
        optional_links = self.containers[container.name]['links']['optional']
        required_links = self.containers[container.name]['links']['required']
        for link_name in optional_links:
            if link_name not in container.links:
                raise BadConfigError(
                    'Profile {} contains invalid optional link for {}: {}'.format(
                        self.name,
                        container.name,
                        link_name,
                    )
                )
        for link_name in required_links:
            if link_name not in container.links:
                raise BadConfigError(
                    'Profile {} contains invalid required link for {}: {}'.format(
                        self.name,
                        container.name,
                        link_name,
                    )
                )
        # Work out desired final set of links
        current_dependencies = [c.name for c in self.graph.dependencies(container)]
        return {
            link_name
            for link_name, link_options in container.links.items()
            if (
                (link_name in current_dependencies and link_name not in optional_links) or
                (link_name in required_links)
            )
        }

    def save(self):
        '''
        Saves the user profile things to disc after loading.

        Persists the profile to disk as YAML
        '''
        # Set user profile to ~/.ftl/quarkworks/user_profile.yaml
        try:
            os.makedirs(os.path.dirname(self.file_path))
        except OSError:
            pass
        with open(self.file_path, 'w') as fh:
            yaml.safe_dump(self.dump(), fh, default_flow_style=False, indent=4)


@attr.s
class NullProfile(Profile):
    file_path = attr.ib(default=None, init=False)

    def load(self):
        '''
        Loads the empty profile.
        '''
        self.containers = {}

    def save(self):
        '''
        Raises an error, you can't save a NullProfile.
        '''
        raise BadConfigError('You cannot save a NullProfile, please load a profile using `ftl profile <profile_name>`')

    def calculate_links(self, container):
        '''
        Returns None, a NullProfile has no links.
        '''

    def apply(self, graph):
        '''
        Returns None, you can't apply a NullProfile to a container-graph.
        '''
