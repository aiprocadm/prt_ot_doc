"""Сторож: витрина читает область шаблона из того поля, что отдаёт сервер (срез-162).

ЧТО БЫЛО. Сервер отдаёт область шаблона в поле `level` (схема
``TemplateScopeDTO``). Название `type` он ПРИНИМАЕТ на запись как синоним, но
в ответе его нет. Витрина же читала только `type`:

* в карточке шаблона область не показывалась вовсе;
* форма правки открывалась с «Тенант» независимо от настоящей области;
* сохранение такой формы отправляло `type: "tenant"` — область площадки или
  организации молча превращалась в тенанта. То есть правка названия шаблона
  меняла ещё и то, к кому он применяется.

КАК ПРОВЕРЯЕТСЯ. Поля, которые витрина объявляет у области, сверяются со
схемой сервера из снимка контракта. `type` разрешён отдельной строкой как
синоним на запись, всё остальное обязано существовать у сервера — иначе поле
всегда пустое, и на экране это прочерк без объяснения.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO_ROOT / "docs" / "stabilization" / "openapi_routes_baseline.json"
DTO = REPO_ROOT / "frontend" / "src" / "types" / "dto" / "templates.ts"
DIALOG = REPO_ROOT / "frontend" / "src" / "features" / "templates" / "TemplateFormDialog.tsx"

#: Синоним на запись: сервер принимает `type`, но в ответе его не возвращает.
WRITE_ONLY_ALIASES = {"type"}


def _server_fields() -> set[str]:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    fields = snapshot["schema_fields"].get("TemplateScopeDTO")
    assert fields, "схема области шаблона исчезла из снимка контракта"
    return set(fields)


def _front_fields() -> set[str]:
    text = DTO.read_text(encoding="utf-8")
    block = text.split("export interface TemplateScopeDto", 1)[1].split("\n}", 1)[0]
    # поля объявления: имя в начале строки с двумя пробелами отступа
    return set(re.findall(r"^\s{2}([a-z_][A-Za-z0-9_]*)\??\s*:", block, re.M))


def test_исходники_читаются() -> None:
    assert "level" in _server_fields()
    assert "tenant_id" in _front_fields()


def test_витрина_не_ждёт_полей_которых_сервер_не_отдаёт() -> None:
    unknown = sorted(_front_fields() - _server_fields() - WRITE_ONLY_ALIASES)
    assert not unknown, (
        "витрина объявила у области шаблона поля, которых нет в ответе сервера — "
        "они всегда пустые: " + ", ".join(unknown)
    )


def test_форма_читает_область_из_поля_сервера() -> None:
    text = DIALOG.read_text(encoding="utf-8")
    assert "scope?.level" in text, (
        "форма правки шаблона снова читает область только из `type` — она "
        "покажет «Тенант» для любого шаблона и сбросит область при сохранении"
    )
