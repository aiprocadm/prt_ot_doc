"""BIZ-52 срез-3: исключения режима «только чтение» совпадают по границе сегмента.

Списки «всегда доступных» путей режимов чтения (офбординг OPS-72 и каскад
партнёра BIZ-52) содержат `/api/v1/auth`. С обычным `startswith` путь
`/api/v1/authorizations` попал бы в исключения просто потому, что начинается с
тех же букв, — и молча обошёл бы защиту. Сегодня такой ручки нет; тест стоит,
чтобы она не появилась незамеченной.
"""

from __future__ import annotations

import pytest

from app.api.helpers.request_tenant import path_is_under

PREFIXES = ("/api/v1/auth", "/api/v1/offboarding")


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/offboarding",
        "/api/v1/offboarding/request",
    ],
)
def test_настоящие_исключения_проходят(path: str) -> None:
    assert path_is_under(path, PREFIXES)


@pytest.mark.parametrize(
    "path",
    [
        # Ловушка, ради которой всё и затевалось.
        "/api/v1/authorizations",
        "/api/v1/auth-tokens",
        "/api/v1/offboarding-reports",
        "/api/v1/companies",
        "/api/v1/persons/auth",
    ],
)
def test_похожие_пути_исключением_не_становятся(path: str) -> None:
    assert not path_is_under(path, PREFIXES)


def test_пустой_список_префиксов_никого_не_пропускает() -> None:
    """Пустой список — это «исключений нет», а не «пропускать всех»."""

    assert not path_is_under("/api/v1/auth/login", ())
