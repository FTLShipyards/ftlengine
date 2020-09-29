import contextlib
import sys
import threading
import time


class ExceptionalThread(threading.Thread):
    """
    Thread subclass that allows exceptions to be easily re-raised in the parent.
    """

    def __init__(self, target=None, args=None, kwargs=None, daemon=False):
        threading.Thread.__init__(self, daemon=daemon)
        self.target = target
        self.args = args or tuple()
        self.kwargs = kwargs or {}
        self.__exception = None

    def run_with_exception(self):
        """
        This method should be overriden if you want to subclass this.
        """
        if self.target:
            self.target(*self.args, **self.kwargs)
        else:
            raise NotImplementedError("You must override run_with_exception")

    def run(self):
        """This method should NOT be overriden."""
        try:
            self.run_with_exception()
        except BaseException:
            self.__exception = sys.exc_info()

    def maybe_raise(self):
        if self.__exception is not None:
            raise self.__exception[1]


class ThreadSet(set):
    """
    Threadsafe set extended with check-and-set style operations
    """

    def __init__(self, *args, **kwargs):
        super(ThreadSet, self).__init__(*args, **kwargs)
        self.lock = threading.Lock()

    def check_and_add(self, value):
        """
        Checks if value is in the set and if it is not, adds it.
        Returns False if value is already in the set, True if value was not in the set and was added.
        """
        with self.lock:
            if value in self:
                return False
            self.add(value)
            return True

    @contextlib.contextmanager
    def entry_lock(self, value, interval=1):
        """
        Context manager that allows entry when the value is not in the set, and removes it
        once finished.
        """
        while not self.check_and_add(value):
            time.sleep(interval)
        yield
        self.remove(value)
