from .base import BasePlugin
from ..constants import PluginHook
from ..docker.introspect import FormationIntrospector


class SystemContainerBuildPlugin(BasePlugin):

    def load(self):
        self.system_contaienr_cache = {}
        self.add_hook(PluginHook.POST_GROUP_BUILD, self.post_group_build)

    def post_group_build(self, host, containers, task):
        """Restart all running system containers whose IDs have changed."""
        formation = FormationIntrospector(host, self.app.containers).introspect()
        containers_to_restart = set()
        for container in containers:
            if container.system:
                # If the running instance is based on an outdated image, restart it
                try:
                    instance = formation.get_container_instance(container.name)
                except ValueError:
                    continue
                image_details = host.client.inspect_image(container.image_name)
                if instance and image_details and image_details["Id"] != instance.image_id:
                    containers_to_restart.add(container)
        if containers_to_restart:
            self.app.invoke("restart", containers=containers_to_restart)
