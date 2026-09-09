import pytest
from typer.testing import CliRunner

from app.cli.main import EXIT_NOT_IMPLEMENTED, EXIT_RESOURCES, cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_health_release_readiness_json(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["health", "release-readiness", "--json"])

    assert result.exit_code == 0
    assert '"status": "ok"' in result.stdout


def test_backup_command_json(runner: CliRunner) -> None:
    """Срез-130: раньше проверка требовала НОЛЯ на выходе у команды, которая
    ничего не делала, — и тем закрепляла ложь. Резервным копированием продукт
    не управляет, поэтому команда обязана сказать это прямо."""

    result = runner.invoke(cli, ["backup", "--triggered-by", "ci", "--json"])

    assert result.exit_code == EXIT_NOT_IMPLEMENTED
    assert '"operation": "backup"' in result.stdout
    assert '"status": "not_implemented"' in result.stdout


def test_projections_rebuild_command_available(runner: CliRunner) -> None:
    """Срез-130: команда пересобирает read model'ы по-настоящему.

    У этого файла нет фикстуры базы — состояние базы зависит от того, что
    крутилось до него. Поэтому проверяется КОНТРАКТ, а не одна из веток: либо
    итог работы (`rebuilt`), либо честное «база не готова» с кодом ресурсов.
    Раньше третья ветка была самой вероятной — «queued» с нулём, не сделав
    ничего; её больше нет. Работа команды на живых данных проверяется в
    `tests/test_cli_commands_are_honest.py`, где база поднята фикстурой.
    """

    result = runner.invoke(cli, ["projections", "rebuild", "--json"])

    assert '"operation": "projections.rebuild"' in result.stdout
    if result.exit_code == 0:
        assert '"rebuilt"' in result.stdout
    else:
        assert result.exit_code == EXIT_RESOURCES
        assert '"status": "unavailable"' in result.stdout
