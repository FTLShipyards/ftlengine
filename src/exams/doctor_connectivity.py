import subprocess

from ..plugins.base import BasePlugin
from ..plugins.doctor import BaseExamination


class DoctorConnectivityPlugin(BasePlugin):
    """
    Examinations to check there are no stale .pyc files
    """

    requires = ["doctor"]

    def load(self):
        self.add_catalog_item("doctor-exam", "connectivity", ConnectivityExamination)


class ConnectivityExamination(BaseExamination):
    """
    Checks various parts of the Mac OS install process
    """

    description = "Connectivity checks"

    def check_github_connectivity(self):
        """
        Testing GitHub connectivity
        """
        try:
            subprocess.check_output(
                ['ssh', '-T', '-o', 'StrictHostKeychecking=no', 'git@github.com'],
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as e:
            if e.returncode != 1:
                raise self.Failure(
                    "Can't access github\n" +
                    "Have you run `ssh-add` on your Host computer?\n" +
                    "Depending on your system, you may have to manually run `ssh-add` after each restart.\n" +
                    "ssh-add configures and runs an SSH Agent with your ssh key so git can access it to checkout code."
                )

    def check_gitlab_connectivity(self):
        """
        Testing GitLab connectivity
        """
        try:
            subprocess.check_output(
                ['ssh', '-T', '-o', 'StrictHostKeychecking=no', 'git@gitlab.com'],
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as e:
            if e.returncode != 1:
                raise self.Failure(
                    "Can't access gitlab\n" +
                    "Have you run `ssh-add` on your Host computer?\n" +
                    "Depending on your system, you may have to manually run `ssh-add` after each restart.\n" +
                    "ssh-add configures and runs an SSH Agent with your ssh key so git can access it to checkout code."
                )
