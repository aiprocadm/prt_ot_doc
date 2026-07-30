"""OPS-73 (разд. 73.1/73.3): ломающее изменение API без смены версии = красный билд.

Гейт различает ломающее и аддитивное — в отличие от snapshot-гарда ARCH-4,
который падает на ЛЮБОМ дрейфе и потому живёт вне CI (им пользуются при
рефакторингах вручную). Здесь наоборот: добавление операции или схемы —
законная эволюция текущей мажорной версии (разд. 73.1: «добавления — в
текущей»), а ИСЧЕЗНОВЕНИЕ операции или схемы — ломающее изменение, которому
место только в новой мажорной версии.

Список того, что считается ломающим, берётся из канона —
``product_spec.API_BREAKING_CHANGES`` (разд. 73.1). До этого среза константа
не использовалась нигде: канон был объявлен, но ничем не подкреплён.

Отдельно закрепляется дисциплина реестра устаревания (разд. 73.2):

* устаревшая поверхность обязана СУЩЕСТВОВАТЬ, пока не наступил sunset —
  «параллельная работа» означает, что удалить ручку раньше срока нельзя;
* у каждой записи есть преемник и срок, и срок даёт потребителям те самые
  6–12 месяцев на миграцию.

Suite ``tests/contract`` уже стоит в CI (job ``openapi-contract``), поэтому
новый файл попадает в гейт без правки workflow.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core.api_deprecation import API_DEPRECATIONS
from app.core.product_spec import API_BREAKING_CHANGES

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "docs" / "stabilization" / "openapi_routes_baseline.json"

pytestmark = pytest.mark.contract


@pytest.fixture(scope="module")
def runtime_openapi() -> dict:
    for key in ("SECRET_KEY", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        os.environ.setdefault(key, "contract-gate")
    from app.api.app import create_app

    return create_app().openapi()


@pytest.fixture(scope="module")
def baseline() -> dict:
    assert BASELINE_PATH.exists(), (
        "Базлайн OpenAPI отсутствует — без него гейт нечем кормить: "
        "python scripts/ci/check_openapi_snapshot.py --snapshot"
    )
    return json.loads(BASELINE_PATH.read_text())


def _runtime_operations(spec: dict) -> set[str]:
    methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    operations: set[str] = set()
    for path, item in (spec.get("paths") or {}).items():
        for method in item:
            if method.lower() in methods:
                operations.add(f"{method.upper()} {path}")
    return operations


class TestBreakingChangesGate:
    def test_no_operation_disappears_within_a_major_version(
        self, runtime_openapi: dict, baseline: dict
    ) -> None:
        """Удаление ручки — ломающее изменение (API_BREAKING_CHANGES: remove_field
        и его эндпоинт-аналог).

        Исключение одно: поверхность из реестра устаревания, у которой sunset
        УЖЕ наступил, — её удаление и есть завершение процесса разд. 73.2.
        Без исключения законное снятие ручки в день после sunset красило бы
        билд с вводящим в заблуждение сообщением (найдено ревью).
        """

        current = _runtime_operations(runtime_openapi)
        today = date.today()
        expired_prefixes = tuple(e.path_prefix for e in API_DEPRECATIONS if e.sunset <= today)
        removed = sorted(
            op
            for op in set(baseline.get("operations", [])) - current
            if not op.split(" ", 1)[1].startswith(expired_prefixes or ("\0",))
        )

        assert not removed, (
            "Операции исчезли из /api/v1 без смены мажорной версии — по разд. 73.1 "
            f"это ломающее изменение ({', '.join(sorted(API_BREAKING_CHANGES))}). "
            "Если удаление сознательное: сперва запись в core/api_deprecation.py "
            "(анонс + Sunset), удаление — только после даты sunset. Исчезли: "
            + ", ".join(removed[:20])
        )

    def test_baseline_is_fresh_so_additions_cannot_hide(
        self, runtime_openapi: dict, baseline: dict
    ) -> None:
        """Добавления обязаны попадать в базлайн В ТОМ ЖЕ PR.

        Иначе у гейта слепое окно (найдено ревью): ручка, добавленная после
        последнего снимка и удалённая через релиз, ни разу не попадает в базлайн
        — её исчезновение никто не заметит. Свежий базлайн стоит одну команду:
        python scripts/ci/check_openapi_snapshot.py --snapshot
        """

        current = _runtime_operations(runtime_openapi)
        unrecorded = sorted(current - set(baseline.get("operations", [])))

        assert not unrecorded, (
            "Операции есть в приложении, но не в базлайне — обновите снимок в этом же PR "
            "(python scripts/ci/check_openapi_snapshot.py --snapshot): "
            + ", ".join(unrecorded[:20])
        )

    def test_no_schema_disappears_within_a_major_version(
        self, runtime_openapi: dict, baseline: dict
    ) -> None:
        """Схема ответа — тоже контракт: её исчезновение равносильно remove_field."""

        current = set((runtime_openapi.get("components") or {}).get("schemas", {}))
        removed = sorted(set(baseline.get("schemas", [])) - current)

        assert not removed, "Схемы исчезли из OpenAPI без смены мажорной версии: " + ", ".join(
            removed[:20]
        )


class TestFieldLevelContract:
    """Разд. 73.1 на уровне ПОЛЕЙ схем.

    До этого гейт видел только исчезновение схемы целиком, и 4 из 5 категорий
    канона проходили зелёными (найдено ревью живым экспериментом: удаление
    обязательного поля из ActionPlanOut — 9/9 passed). Базлайн теперь хранит
    подпись полей каждой схемы ({поле: тип}), и гейт ловит:

    * ``remove_field`` — поле исчезло из схемы;
    * ``rename_field`` — частный случай remove (старое имя исчезло);
    * ``change_type`` — тип поля изменился.

    ``change_semantics`` и ``tighten_validation`` механически недетектируемы —
    это ЧЕСТНО записано в docs/API_VERSIONING.md, а не замолчано.
    """

    def test_no_field_disappears_and_no_type_changes(
        self, runtime_openapi: dict, baseline: dict
    ) -> None:
        base_fields: dict = baseline.get("schema_fields") or {}
        if not base_fields:
            pytest.skip("базлайн ещё без подписей полей — переснимите --snapshot")

        current_schemas = (runtime_openapi.get("components") or {}).get("schemas", {})
        problems: list[str] = []
        for schema_name, fields in base_fields.items():
            schema = current_schemas.get(schema_name)
            if not isinstance(schema, dict):
                continue  # исчезновение схемы целиком ловит соседний тест
            props = schema.get("properties")
            if not isinstance(props, dict):
                continue
            for field_name, base_type in fields.items():
                if field_name not in props:
                    problems.append(f"{schema_name}.{field_name}: удалено (remove_field)")
                    continue
                cur = props[field_name]
                if isinstance(cur, dict):
                    if "type" in cur:
                        cur_type = str(cur["type"])
                    elif "$ref" in cur:
                        cur_type = str(cur["$ref"]).rsplit("/", 1)[-1]
                    elif "anyOf" in cur or "oneOf" in cur or "allOf" in cur:
                        variants = cur.get("anyOf") or cur.get("oneOf") or cur.get("allOf")
                        parts = []
                        for v in variants:
                            if isinstance(v, dict):
                                parts.append(
                                    str(v.get("type") or str(v.get("$ref", "?")).rsplit("/", 1)[-1])
                                )
                        cur_type = "|".join(sorted(parts))
                    else:
                        cur_type = "any"
                else:
                    cur_type = "any"
                if cur_type != base_type:
                    problems.append(
                        f"{schema_name}.{field_name}: тип {base_type} → {cur_type} (change_type)"
                    )

        assert not problems, (
            "Ломающие изменения полей без смены мажорной версии "
            f"(канон: {', '.join(sorted(API_BREAKING_CHANGES))}). Если изменение "
            "сознательное аддитивное — переснимите базлайн; если ломающее — ему место "
            "в /api/v2. Найдено: " + "; ".join(problems[:15])
        )


class TestDeprecationRegistryDiscipline:
    def test_breaking_change_catalogue_is_the_canonical_one(self) -> None:
        """Канон разд. 73.1 зафиксирован константой; гейт обязан читать её же."""

        assert set(API_BREAKING_CHANGES) == {
            "remove_field",
            "rename_field",
            "change_type",
            "change_semantics",
            "tighten_validation",
        }

    def test_every_entry_names_a_successor_and_a_future_sunset(self) -> None:
        """«Этого больше не будет» без «куда переходить» — не deprecation, а угроза."""

        for entry in API_DEPRECATIONS:
            assert entry.successor.strip(), entry.path_prefix
            assert entry.sunset > entry.deprecated_since, entry.path_prefix
            # Разд. 73.2: анонс за 6–12 месяцев. Проверяем нижнюю границу — полгода.
            assert entry.sunset - entry.deprecated_since >= timedelta(
                days=180
            ), f"{entry.path_prefix}: между анонсом и отключением меньше 6 месяцев"

    def test_deprecated_surface_still_exists_until_sunset(self, runtime_openapi: dict) -> None:
        """Разд. 73.2 «Параллельная работа»: удалить ручку раньше sunset нельзя.

        Пока дата не наступила, устаревшая поверхность обязана отвечать — иначе
        заголовок Sunset был обещанием, которое нарушили досрочно.
        """

        operations = _runtime_operations(runtime_openapi)
        today = date.today()
        for entry in API_DEPRECATIONS:
            if entry.sunset <= today:
                continue  # срок вышел — удаление законно
            if entry.path_prefix == "/api/v1/files-legacy":
                # Legacy-файлы смонтированы за флагом enable_files_legacy_routes
                # (в production он принудительно выключен) — проверяем только
                # там, где флаг включает поверхность.
                from app.core.config import get_settings

                if not get_settings().enable_files_legacy_routes:
                    continue
            assert any(
                op.split(" ", 1)[1].startswith(entry.path_prefix) for op in operations
            ), f"{entry.path_prefix}: поверхность исчезла раньше даты sunset ({entry.sunset})"
