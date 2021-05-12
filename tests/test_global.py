from src import __version__, __version_info__


def test_version():
    assert len(__version__) == 6


def test_version_info():
    assert len(__version_info__) == 3
