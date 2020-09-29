import ntplib
import time

from ..plugins.base import BasePlugin
from ..plugins.doctor import BaseExamination


class DoctorTimePlugin(BasePlugin):
    """
    Examinations to check the time on the docker server is roughly correct
    """

    requires = ["doctor"]

    def load(self):
        self.add_catalog_item("doctor-exam", "time", TimeExamination)


class TimeExamination(BaseExamination):
    """
    Checks the datetime on the docker server is not too out of drift
    """

    warning_limit = 10
    error_limit = 120

    description = "Time checks"

    def check_docker_time(self):
        """Testing docker clock sync"""
        # Check to see if the docker server agrees with our clock
        self.host.client.pull("alpine", "3.5")
        container = self.host.client.create_container(
            "alpine:3.5",
            command=["/bin/date", "+%s"],
            detach=True,
            tty=False,
        )
        self.host.client.start(container)
        while self.host.container_running(container['Id']):
            time.sleep(0.1)
        docker_time = self.host.client.logs(container['Id']).strip()
        delta = abs(int(docker_time) - time.time())
        if delta > self.error_limit:
            raise self.Failure("%i seconds out of sync" % delta)
        elif delta > self.warning_limit:
            raise self.Warning("%i seconds out of sync" % delta)

    def check_local_time(self):
        """Testing local clock sync"""
        # Query an NTP server for the time
        c = ntplib.NTPClient()
        response = c.request('pool.ntp.org', version=3)
        delta = abs(response.offset)
        if delta > self.error_limit:
            raise self.Failure("%i seconds out of sync" % delta)
        elif delta > self.warning_limit:
            raise self.Warning("%i seconds out of sync" % delta)
