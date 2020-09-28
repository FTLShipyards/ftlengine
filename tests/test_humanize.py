import unittest

from src.utils.humanize import file_size


class FilesizeTests(unittest.TestCase):
    """
    Tests the filesize formatter
    """

    def test_binary_values(self):
        self.assertEqual(
            file_size(1),
            "1.0 B",
        )
        self.assertEqual(
            file_size(1024),
            "1.0 KiB",
        )
        self.assertEqual(
            file_size(1524),
            "1.5 KiB",
        )
        self.assertEqual(
            file_size(5500928),
            "5.2 MiB",
        )
        self.assertEqual(
            file_size(7300613312),
            "6.8 GiB",
        )

    def test_decimal_values(self):
        self.assertEqual(
            file_size(1, si=True),
            "1.0 B",
        )
        self.assertEqual(
            file_size(1024, si=True),
            "1.0 KB",
        )
        self.assertEqual(
            file_size(1524, si=True),
            "1.5 KB",
        )
        self.assertEqual(
            file_size(5500928, si=True),
            "5.5 MB",
        )
        self.assertEqual(
            file_size(7300613312, si=True),
            "7.3 GB",
        )
