from typer.testing import CliRunner

from app.cli.main import cli

runner = CliRunner()


def test_health_release_readiness_json() -> None:
    result = runner.invoke(cli, ["health", "release-readiness", "--json"])

    assert result.exit_code == 0
    assert '"status": "ok"' in result.stdout


def test_backup_command_json() -> None:
    result = runner.invoke(cli, ["backup", "--triggered-by", "ci", "--json"])

    assert result.exit_code == 0
    assert '"operation": "backup"' in result.stdout
    assert '"triggered_by": "ci"' in result.stdout


def test_projections_rebuild_command_available() -> None:
    result = runner.invoke(cli, ["projections", "rebuild", "--json"])

    assert result.exit_code == 0
    assert '"operation": "projections.rebuild"' in result.stdout
