import attr
import click
import sys

from .base import BasePlugin
from ..cli.argument_types import HostType
from ..cli.tasks import Task


@attr.s
class DoctorPlugin(BasePlugin):
    """
    System for running sets of checks defined in plugins to establish system health.
    """

    provides = ["doctor"]

    def load(self):
        self.add_command(doctor)
        self.add_catalog_type("doctor-exam")


@attr.s
class BaseExamination:
    """
    Base class for doctor examinations.

    Write one or more methods that start with check_ and each one will be run
    as a separate exam, with their docstring as the name of the exam.

    If a method raises Failure or Warning, they're printed out to the console.
    If it returns without raising, it is considered successful.
    """

    # Class-level attribute for the check description
    description = None

    app = attr.ib()

    class Failure(BaseException):
        """
        Raised by checks on failure.
        """

    class Warning(BaseException):
        """
        Raised by checks on non-failure, but worrying info.
        """

    def skipped(self):
        return False

    def run(self, host, parent_task):
        """
        Runs through examinations if we're not being skipped.
        """
        # Check skipping
        if self.skipped():
            return
        # Make overall task
        self.host = host
        assert self.description is not None, "You must override description on an examination subclass"
        task = Task(self.description, parent=parent_task)
        # Find all methods
        methods = []
        for name in sorted(dir(self)):
            if name.startswith("check_"):
                methods.append(getattr(self, name))
        if not methods:
            task.finish(status="Empty", status_flavor=Task.FLAVOR_WARNING)
            return
        # Run them in alphabetical order
        for method in methods:
            method_description = method.__doc__.strip() or method.__name__
            subtask = Task(method_description, parent=task)
            try:
                method()
            except self.Warning as e:
                subtask.set_extra_info([x.strip() for x in str(e).split("\n")])
                subtask.finish(status="Warning", status_flavor=Task.FLAVOR_WARNING)
            except self.Failure as e:
                subtask.set_extra_info([x.strip() for x in str(e).split("\n")])
                subtask.finish(status="Failed", status_flavor=Task.FLAVOR_BAD)
                return False
            else:
                subtask.finish(status="OK", status_flavor=Task.FLAVOR_GOOD)
        task.finish(status="OK", status_flavor=Task.FLAVOR_GOOD)
        return True


@click.command()
@click.option('--host', '-h', type=HostType(), default='default')
@click.pass_obj
def doctor(app, host):
    """
    Runs the doctor exams.
    """
    exams = app.get_catalog_items("doctor-exam").values()
    problem = False
    for exam in exams:
        exam_result = exam(app).run(host, app.root_task)
        if exam_result is not None and not exam_result:
            problem = True
    if problem:
        sys.exit(1)
