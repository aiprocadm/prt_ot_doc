"""Сторож: локализация ПДн сверяется, а не только объявляется (SEC-66, срез-185).

ЧТО БЫЛО. В реестре обработки есть поле «где физически лежат данные». Арендатор
писал туда «RU», и это никто и никогда не сверял с тем, где развёрнута система.
Строка матрицы честно писала: «Осталось: локализация ПДн — вопрос хостинга, не
кода (поле в реестре есть)».

ПОЧЕМУ ЭТО НЕ МЕЛОЧЬ. Реестр обработки показывают регулятору. Строка «данные
хранятся в РФ» — УТВЕРЖДЕНИЕ о системе. Если файлы уезжают в хранилище другого
региона, утверждение ложно, а узнать об этом можно только на проверке. Это тот
же класс, что пустой адаптер, рапортующий об успешной отправке: система
говорит о себе то, чего не проверяет.

ГЛАВНОЕ РАЗЛИЧИЕ, КОТОРОЕ ЗДЕСЬ ЗАКРЕПЛЕНО: несовпадение БЕЗ отметки о
трансграничной передаче — нарушение; несовпадение С отметкой — законная
ситуация, требующая отдельного основания. Смешать их значило бы либо пропускать
нарушения, либо кричать на правильно оформленные процессы.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_pdn_residency.py -v``.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from app.modules.privacy import residency


@dataclass
class _Activity:
    code: str
    name: str
    storage_location: str
    cross_border_transfer: bool = False
    is_active: bool = True


def _settings(region: str = "RU") -> SimpleNamespace:
    return SimpleNamespace(data_residency_region=region)


def test_declared_matches_deployment_is_ok() -> None:
    findings = residency.evaluate(
        [_Activity("hr", "Кадровый учёт", "RU")], settings=_settings("RU")
    )
    assert [f.verdict for f in findings] == [residency.OK]
    assert residency.summarize(findings)["compliant"] is True


def test_mismatch_without_declared_transfer_is_a_violation() -> None:
    """Главная находка: реестр обещает регулятору одно, система делает другое."""

    findings = residency.evaluate(
        [_Activity("hr", "Кадровый учёт", "NL")], settings=_settings("RU")
    )
    assert findings[0].verdict == residency.UNDECLARED_TRANSFER
    assert findings[0].is_violation
    report = residency.summarize(findings)
    assert report["violations"] == 1
    assert report["compliant"] is False


def test_mismatch_with_declared_transfer_is_not_a_violation() -> None:
    """Осознанная трансграничная передача — законная ситуация, а не ошибка.

    Если бы она считалась нарушением, сторож кричал бы на правильно оформленные
    процессы, и его перестали бы читать — вместе с настоящими находками.
    """

    findings = residency.evaluate(
        [_Activity("frdo", "Передача в ФРДО", "NL", cross_border_transfer=True)],
        settings=_settings("RU"),
    )
    assert findings[0].verdict == residency.DECLARED_TRANSFER
    assert not findings[0].is_violation
    report = residency.summarize(findings)
    assert report["violations"] == 0
    assert report["declared_transfers"] == 1
    # Показывается всё равно: такие процессы требуют отдельного основания.
    assert len(report["findings"]) == 1


def test_inactive_activities_are_skipped() -> None:
    """Прекращённый процесс описывает прошлое, а не систему."""

    findings = residency.evaluate(
        [_Activity("old", "Старый процесс", "NL", is_active=False)], settings=_settings("RU")
    )
    assert findings == []


def test_case_and_spaces_do_not_create_false_findings() -> None:
    """«ru» и « RU » — это тот же регион; иначе сторож нашёл бы нарушение на пустом месте."""

    findings = residency.evaluate(
        [_Activity("hr", "Кадры", " ru ")], settings=_settings("RU")
    )
    assert findings[0].verdict == residency.OK


def test_region_defaults_to_ru_when_not_declared() -> None:
    """152-ФЗ и есть причина существования этого реестра — умолчание РФ."""

    assert residency.deployment_region(SimpleNamespace()) == "RU"
    assert residency.deployment_region(SimpleNamespace(data_residency_region="")) == "RU"
    assert residency.deployment_region(SimpleNamespace(data_residency_region="kz")) == "KZ"


def test_report_counts_only_problems_in_findings() -> None:
    """В выдаче — только то, на что надо смотреть: совпавшие строки не шумят."""

    findings = residency.evaluate(
        [
            _Activity("a", "Совпало", "RU"),
            _Activity("b", "Нарушение", "NL"),
            _Activity("c", "Осознанная передача", "DE", cross_border_transfer=True),
        ],
        settings=_settings("RU"),
    )
    report = residency.summarize(findings)
    assert report["checked"] == 3
    assert report["violations"] == 1
    assert {f["code"] for f in report["findings"]} == {"b", "c"}
