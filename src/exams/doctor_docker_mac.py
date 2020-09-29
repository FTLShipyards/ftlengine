import subprocess
import sys
import os
import re

from ..plugins.base import BasePlugin
from ..plugins.doctor import BaseExamination


class DoctorDockerMacPlugin(BasePlugin):
    """
    Examinations for the local docker environment
    """

    requires = ["doctor"]

    def load(self):
        self.add_catalog_item("doctor-exam", "docker_mac", DockerMacExamination)


class DockerMacExamination(BaseExamination):
    """
    Checks various parts of the Mac OSX install process
    """

    description = "Mac OSX checks"

    def skipped(self):
        """
        Only run when docker command is available, and you're on OSX
        """
        return sys.platform != "darwin"

    def check_ftl_home(self):
        """
        FTL_HOME folder location
        """
        ftl_home = os.environ['FTL_HOME']
        if (re.search(r'\/users\/[a-z0-9\.\-\_]*\/quarkworks/pantheon/.ftl', ftl_home.lower()) is None):
            raise self.Failure("FTL_HOME should point to ~/quarkworks/pantheon/.ftl")

    def check_preferences(self):
        """
        Docker Preferences
        """
        try:
            docker_info = subprocess.check_output(
                "docker info --format '{{.NCPU}}:{{.MemTotal}}'",
                shell=True,
                stderr=subprocess.STDOUT,
            ).decode("utf8").strip().split(':')
            number_cpu = int(docker_info[0])
            memory_total = int(docker_info[1])
            if(number_cpu < 3):
                raise self.Failure(
                    "Insufficient number of CPUs, please allocate at least 3 CPUs for Docker For Mac")
            if(memory_total < 7500000000):
                raise self.Failure(
                    "Insufficient memory, please allocate at least 8GB for Docker For Mac")
        except Exception as e:
            raise self.Failure(
                "Could not run 'docker info': {}".format(str(e)))
