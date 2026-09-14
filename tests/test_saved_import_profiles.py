"""Сторож: профиль импорта заводится из СВОЕГО файла (OPS-71, срез-192).

ЧТО БЫЛО. Профили источников лежали константами в коде, и остаток строки звучал
так: «профили конкурентов (нужны образцы их выгрузок — вопрос владельцу)».
Поддержка каждого нового формата упиралась сразу в две вещи: достать чужой файл
и написать под него код. Обе — вне досягаемости того, кто прямо сейчас
переезжает и у кого файл УЖЕ ЕСТЬ.

РЕШЕНИЕ. Образцы не нужны: клиент один раз сопоставляет колонки руками и
сохраняет сопоставление профилем. Система учится у того, у кого файл есть.

ЧТО ПРОВЕРЯЕТСЯ, по убыванию важности:

1. подпись файла считается САМА (спрашивать её у человека — задавать вопрос, на
   который он не знает ответа) и УСТОЙЧИВА между запусками;
2. разбор составной колонки не может ссылаться на несуществующий заголовок —
   иначе он молча не сработает, и человек получит пустые фамилию и имя;
3. свой профиль сильнее одноимённого встроенного: спорить с человеком о его
   собственных данных нельзя.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_saved_import_profiles.py -v``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.modules.imports import saved_profiles as sp
from app.modules.imports.profiles import ColumnSplit, ImportProfile

TARGETS = {"people", "sites"}


def _draft(**over) -> sp.ProfileDraft:
    base = {
        "code": "my-old-system",
        "title": "Выгрузка из нашей прошлой программы",
        "target": "people",
        "mapping": {
            "full_name": "ФИО работника",
            "tab_number": "Таб. №",
            "position": "Должность",
            "department": "Подразделение",
            "hired_at": "Дата приёма",
        },
        "splits": {"ФИО работника": ["last_name", "first_name", "middle_name"]},
        "description": "",
    }
    base.update(over)
    return sp.ProfileDraft(**base)


@dataclass
class _Row:
    code: str
    title: str
    target: str
    mapping: dict
    splits: dict
    signature: list
    description: str | None = None


class TestПодпись:
    def test_считается_из_сопоставленных_заголовков(self) -> None:
        """Спрашивать подпись у человека — задавать вопрос, на который он не знает ответа."""

        signature = sp.build_signature(_draft().mapping)
        assert signature
        assert len(signature) <= sp.SIGNATURE_SIZE

    def test_устойчива_между_запусками(self) -> None:
        """Иначе одно сопоставление давало бы разные подписи, и профиль перестал
        бы совпадать сам с собой."""

        first = sp.build_signature(_draft().mapping)
        second = sp.build_signature(dict(reversed(list(_draft().mapping.items()))))
        assert first == second

    def test_берутся_заголовки_источника_а_не_имена_наших_полей(self) -> None:
        """Узнаём мы ЧУЖОЙ файл, а не свою модель."""

        signature = sp.build_signature({"full_name": "ФИО работника"})
        assert "full_name" not in signature


class TestПроверкаЧерновика:
    def test_годный_черновик_проходит(self) -> None:
        sp.validate_draft(_draft(), known_targets=TARGETS)

    def test_разбор_несуществующей_колонки_отвергается(self) -> None:
        """ГЛАВНОЕ: иначе разбор молча не сработает, и человек получит пустые
        фамилию и имя, ничего не заметив."""

        draft = _draft(splits={"Ф.И.О.": ["last_name", "first_name"]})
        with pytest.raises(sp.SavedProfileError, match="молча не сработал"):
            sp.validate_draft(draft, known_targets=TARGETS)

    def test_разбор_на_одну_часть_бессмыслен(self) -> None:
        draft = _draft(splits={"ФИО работника": ["last_name"]})
        with pytest.raises(sp.SavedProfileError, match="минимум две части"):
            sp.validate_draft(draft, known_targets=TARGETS)

    def test_профиль_без_сопоставления_отвергается(self) -> None:
        with pytest.raises(sp.SavedProfileError, match="бесполезен"):
            sp.validate_draft(_draft(mapping={}, splits={}), known_targets=TARGETS)

    def test_пустой_заголовок_у_поля_отвергается(self) -> None:
        draft = _draft(mapping={"full_name": "  "}, splits={})
        with pytest.raises(sp.SavedProfileError, match="не выбран заголовок"):
            sp.validate_draft(draft, known_targets=TARGETS)

    def test_неизвестная_цель_отвергается(self) -> None:
        with pytest.raises(sp.SavedProfileError, match="Неизвестная цель"):
            sp.validate_draft(_draft(target="dragons"), known_targets=TARGETS)

    @pytest.mark.parametrize("code", ["", "с кириллицей", "a" * 65, "bad code"])
    def test_негодный_код_отвергается(self, code: str) -> None:
        with pytest.raises(sp.SavedProfileError, match="Код профиля"):
            sp.validate_draft(_draft(code=code), known_targets=TARGETS)


class TestПеречень:
    def test_свой_профиль_вытесняет_одноимённый_встроенный(self) -> None:
        """Арендатор знает свою прошлую систему лучше, чем догадка платформы."""

        builtin = [ImportProfile(code="1c_zup", title="1С:ЗУП", target="people", source="1c")]
        own = [ImportProfile(code="1c_zup", title="Наш 1С", target="people", source="tenant")]
        merged = sp.merge_profiles(builtin, own)
        assert len(merged) == 1
        assert merged[0].title == "Наш 1С"

    def test_свои_идут_впереди(self) -> None:
        builtin = [ImportProfile(code="excel", title="Excel", target="people", source="excel")]
        own = [ImportProfile(code="mine", title="Мой", target="people", source="tenant")]
        assert sp.merge_profiles(builtin, own)[0].code == "mine"


class TestОпознание:
    def test_файл_узнаётся_по_своему_профилю(self) -> None:
        row = _Row(
            code="mine",
            title="Мой",
            target="people",
            mapping={"full_name": "ФИО работника"},
            splits={},
            signature=["фио работника"],
        )
        profile = sp.to_import_profile(row)
        found = sp.detect([profile], ["ФИО работника", "Должность"])
        assert found is not None
        assert found.code == "mine"

    def test_неполное_совпадение_не_считается(self) -> None:
        """Профиль меняет трактовку колонок — ошибиться дороже, чем не угадать."""

        row = _Row(
            code="mine",
            title="Мой",
            target="people",
            mapping={},
            splits={},
            signature=["фио работника", "таб номер"],
        )
        assert sp.detect([sp.to_import_profile(row)], ["ФИО работника"]) is None

    def test_при_равенстве_подписей_побеждает_свой(self) -> None:
        builtin = ImportProfile(
            code="excel", title="Excel", target="people", source="excel", signature=("ФИО",)
        )
        own = ImportProfile(
            code="mine", title="Мой", target="people", source=sp.TENANT_SOURCE, signature=("ФИО",)
        )
        found = sp.detect([builtin, own], ["ФИО"])
        assert found is not None and found.code == "mine"

    def test_разбор_переносится_в_профиль(self) -> None:
        row = _Row(
            code="mine",
            title="Мой",
            target="people",
            mapping={"full_name": "ФИО"},
            splits={"ФИО": ["last_name", "first_name", "middle_name"]},
            signature=["фио"],
        )
        profile = sp.to_import_profile(row)
        assert profile.splits == (
            ColumnSplit(source="ФИО", parts=("last_name", "first_name", "middle_name")),
        )

    def test_свой_профиль_помечен_источником(self) -> None:
        """Без отметки человек не отличит своё от поставляемого платформой."""

        row = _Row(code="m", title="М", target="people", mapping={}, splits={}, signature=[])
        assert sp.to_import_profile(row).source == sp.TENANT_SOURCE
