import unittest

from src.utils import threading


class ThreadingTests(unittest.TestCase):
    """
    Tests threading module
    """

    def test_default(self):
        obj = threading.ExceptionalThread()
        self.assertIsNone(obj.target)

