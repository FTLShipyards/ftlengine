import subprocess
import sys
import os

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
        # Check if using old version
        try:
            ftl_home = os.environ['FTL_HOME']
            raise self.Warning(f'Legacy FTL_HOME detected: Run `ftl chart add {ftl_home}`')
        except KeyError:
            # FTL_HOME not set: GOOD
            pass

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
            if(number_cpu < 2):
                raise self.Failure(
                    "Insufficient number of CPUs, please allocate at least 2 CPUs for Docker For Mac")
            if(number_cpu < 3):
                raise self.Warning("3 CPUs recommended with Docker For Mac")
            if(memory_total < 2000000000):
                raise self.Failure('Insufficient memory, please allocate at least 2GB for Docker For Mac')
            if(memory_total < 4000000000):
                raise self.Warning('4GB memory recommended with Docker For Mac')
        except Exception as e:
            raise self.Failure(
                "Could not run 'docker info': {}".format(str(e)))
