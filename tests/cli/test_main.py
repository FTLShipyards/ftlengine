from click.testing import CliRunner
from src.cli import cli


def test_app():
    runner = CliRunner()
    result = runner.invoke(cli)
    assert result.exit_code == 0
    print(result.output)
    assert 'Usage: cli [OPTIONS] COMMAND [ARGS]...\n\n  FTL, the Docker-based development environment management tool.\n\n' in result.output  # noqa
