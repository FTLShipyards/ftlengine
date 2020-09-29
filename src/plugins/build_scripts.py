import os
import logging
import subprocess

from .base import BasePlugin
from ..cli.tasks import Task
from ..constants import PluginHook
from ..exceptions import BuildFailureError


class BuildScriptsPlugin(BasePlugin):

    def load(self):
        self.add_hook(PluginHook.PRE_BUILD, self.run_pre_build_script)
        self.add_hook(PluginHook.POST_BUILD, self.run_post_build_script)
        self.add_hook(PluginHook.PRE_RUN_CONTAINER, self.run_pre_start_script)

    def run_pre_build_script(self, host, container, task):
        """
        Runs the pre build scripts.
        """
        self.run_script('pre-build', container, task)

    def run_post_build_script(self, host, container, task):
        """
        Runs the post build scripts.
        """
        self.run_script('post-build', container, task)

    def run_pre_start_script(self, host, instance, task):
        """
        Runs the post build scripts.
        """
        self.run_script('pre-start', instance.container, task)

    def run_script(self, name, container, task):
        """
        Runs a script, logs its output, and errors if it breaks.

        We call interpreters directly as the scripts may not always be +x and so
        we cannot call them directly and rely on their shebang line.
        """
        for script_extension, interpreter in [('.sh', 'bash'), ('.py', 'python)]')]:
            script_path = os.path.join(container.path, name + script_extension)
            if os.path.exists(script_path):
                # Make a build directory, removing any old one if it exists
                build_dir = os.path.join(container.path, 'build')
                if os.path.isdir(build_dir):
                    subprocess.call(['rm', '-rf', build_dir])
                os.mkdir(build_dir)
                # Run the script
                script_task = Task('Running {}'.format(name), parent=task, collapse_if_finished=True)
                logger = logging.getLogger('build_logger')
                process = subprocess.Popen(
                    [interpreter, script_path],
                    cwd=container.path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                while True:
                    line = process.stdout.readline().rstrip().decode('utf8')
                    logger.info(line)
                    if line.strip():
                        script_task.set_extra_info(
                            script_task.extra_info[-3:] + [line]
                        )
                    if not line and process.poll() is not None:
                        break
                exit_code = process.wait()
                if exit_code:
                    script_task.finish(status='Failed', status_flavor=Task.FLAVOR_BAD)
                    raise BuildFailureError('Script {} failed'.format(name))
                else:
                    script_task.finish(status='Done', status_flavor=Task.FLAVOR_GOOD)
                break
