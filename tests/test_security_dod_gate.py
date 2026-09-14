"""Сторож: «седьмой вопрос» безопасности стал гейтом (SEC-69, срез-183).

ЧТО БЫЛО. Вопрос «какие новые поверхности атаки вводит фича и как они закрыты?»
жил константой и пунктом шаблона PR. Тест следил за дословностью формулировки —
но не за тем, что на вопрос ОТВЕТИЛИ. Галочку можно было не ставить, и ничего
не происходило. Строка матрицы так и писала: «константа есть, гейта нет».

ЧТО ПРОВЕРЯЕТСЯ ЗДЕСЬ. Три вещи, каждая — отдельный способ обмануть гейт:

1. правка, не трогающая поверхностей, не должна ничего требовать (иначе гейт
   превратится в ритуал и его начнут обходить);
2. новая ручка без ответа — отказ;
3. галочка БЕЗ текста под ней — тоже отказ (галочка без ответа и есть ритуал).

КАК ЗАПУСТИТЬ: ``PYTHONPATH=backend pytest tests/test_security_dod_gate.py -v``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "scripts" / "ci" / "check_security_dod.py"

sys.path.insert(0, str(REPO_ROOT / "backend"))
from app.core.product_spec import SECURITY_QUESTION  # noqa: E402

QUESTION_LINE = f"- [x] **{SECURITY_QUESTION}**"


def _run(files: list[str], body: str | None, tmp_path) -> subprocess.CompletedProcess[str]:
    files_file = tmp_path / "files.txt"
    files_file.write_text("\n".join(files), encoding="utf-8")
    args = [sys.executable, str(GATE), "--files-from", str(files_file)]
    if body is not None:
        body_file = tmp_path / "body.md"
        body_file.write_text(body, encoding="utf-8")
        args += ["--body-file", str(body_file)]
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "backend")}
    env.pop("PR_BODY", None)
    return subprocess.run(args, capture_output=True, text=True, env=env, cwd=REPO_ROOT)


def test_documentation_only_change_asks_nothing(tmp_path) -> None:
    """Правка документации не трогает поверхностей — гейт молчит.

    Это не поблажка, а условие живучести: гейт, который спрашивает всегда,
    очень быстро начинают проходить не глядя.
    """

    result = _run(["docs/SETUP.md", "CHANGELOG.md"], None, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "не трогают поверхности" in result.stdout


def test_new_route_without_an_answer_is_rejected(tmp_path) -> None:
    result = _run(
        ["backend/app/api/routes/reports.py"],
        "## Что это\n\nНовый отчёт.\n\n- [ ] **%s**\n" % SECURITY_QUESTION,
        tmp_path,
    )
    assert result.returncode == 1
    assert "ручки API" in result.stderr
    assert "не отмечен пункт Security DoD" in result.stderr


def test_ticked_checkbox_without_text_is_rejected(tmp_path) -> None:
    """Главная проверка: галочка без ответа — ритуал, а не проверка."""

    body = f"## Security DoD\n\n{QUESTION_LINE}\n\n## Дальше\n"
    result = _run(["backend/app/api/routes/reports.py"], body, tmp_path)
    assert result.returncode == 1
    assert "ответа под ним нет" in result.stderr


def test_ticked_checkbox_with_an_answer_passes(tmp_path) -> None:
    body = (
        f"## Security DoD\n\n{QUESTION_LINE}\n"
        "      Новая ручка GET /reports/{id} доступна ролям admin и employee,\n"
        "      возвращает только отчёты своего арендатора, перебор id ограничен\n"
        "      общим лимитером.\n"
    )
    result = _run(["backend/app/api/routes/reports.py"], body, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "ответ в описании PR есть" in result.stdout


def test_explicit_no_surfaces_is_accepted(tmp_path) -> None:
    """«Нет новых поверхностей» — тоже решение, но написанное словами."""

    body = "## Security DoD\n\nПравка опечатки: нет новых поверхностей атаки.\n"
    result = _run(["backend/app/api/routes/reports.py"], body, tmp_path)
    assert result.returncode == 0, result.stderr


def test_missing_body_is_rejected_not_skipped(tmp_path) -> None:
    """Отсутствие описания не должно означать «проверка пройдена»."""

    result = _run(["backend/app/migrations/versions/20260914_x.py"], None, tmp_path)
    assert result.returncode == 1
    assert "описание PR не передано" in result.stderr


@pytest.mark.parametrize(
    ("path", "surface"),
    [
        ("backend/app/api/routes/x.py", "ручки API"),
        ("backend/app/migrations/versions/x.py", "миграции базы"),
        ("backend/app/middleware/x.py", "промежуточные слои запроса"),
        ("backend/app/modules/files/service.py", "приём и разбор файлов"),
        ("backend/app/core/external_perimeter.py", "внешний контур"),
        ("backend/app/services/webhooks.py", "вебхуки и интеграции"),
        ("backend/app/modules/rbac_abac/engine.py", "права и доступ"),
        ("backend/app/core/secret_cipher.py", "секреты и ключи"),
        ("frontend/package.json", "зависимости"),
    ],
)
def test_every_declared_surface_is_recognised(path: str, surface: str) -> None:
    """Каждая объявленная поверхность закреплена ОБРАЗЦОМ пути.

    Урок среза-156: сторож ловит только то, куда смотрит. Закреплять область
    числом найденного нельзя — при расширении список молча перестаёт покрывать
    то, что обещает.
    """

    sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
    from check_security_dod import touched_surfaces  # noqa: PLC0415

    assert surface in touched_surfaces([path])


class TestЗависимостиОтбираютсяПоИмениФайла:
    """Срез-195: гейт кричал «изменены зависимости» на файлах раздела НПА.

    Первая версия искала подстроку «requirements», и любой файл контура
    «требования по НПА» срабатывал как манифест зависимостей. Нашлось
    применением гейта к собственному PR: он потребовал ответ про зависимости
    там, где не менялся ни один манифест.

    Это не мелочь: сторож, который кричит не по делу, перестают читать — ровно
    от этого гейт и защищает.
    """

    @pytest.mark.parametrize(
        "path",
        [
            "backend/app/api/routes/compliance_requirements.py",
            "backend/app/domains/npa/requirements.py",
            "tests/api/test_compliance_requirements_paging.py",
            "frontend/src/types/dto/complianceRequirements.ts",
        ],
    )
    def test_файлы_раздела_требований_не_считаются_зависимостями(self, path: str) -> None:
        sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
        from check_security_dod import touched_surfaces  # noqa: PLC0415

        assert "зависимости" not in touched_surfaces([path])

    @pytest.mark.parametrize(
        "path",
        [
            "requirements.txt",
            "requirements-dev.txt",
            "pyproject.toml",
            "frontend/package.json",
            "frontend/package-lock.json",
        ],
    )
    def test_настоящие_манифесты_по_прежнему_ловятся(self, path: str) -> None:
        """Обратная половина: сузив правило, легко потерять то, ради чего оно есть."""

        sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
        from check_security_dod import touched_surfaces  # noqa: PLC0415

        assert "зависимости" in touched_surfaces([path])
