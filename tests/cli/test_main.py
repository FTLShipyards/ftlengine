from click.testing import CliRunner
from src.cli import cli


def test_app():
    runner = CliRunner()
    result = runner.invoke(cli)
    assert result.exit_code == 0
    print(result.output)
    assert 'FTL_HOME is not set\n' in result.output
