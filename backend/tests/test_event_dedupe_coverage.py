"""У КАЖДОГО типа события обязан быть ключ дедупликации (BIZ-54-57 срез-4).

**Сторож заведён по следу настоящего дефекта.** В этом срезе появилось событие
``WorkPermitIssued``. Тип объявлен, payload-модель написана, в реестре
``_PAYLOADS`` зарегистрирована — а ветки в ``dedupe_key_for`` не было. Итог:
ручка выдачи наряда-допуска отвечала **400** на каждый вызов, потому что
``OutboxService.enqueue`` не мог вычислить личность события. Ни один тест самого
события этого не ловил — поймала только сквозная проверка «выдал наряд →
появилась задача».

Проверка ОБРАТНАЯ по построению: она идёт от реестра событий, а не от списка
известных веток. Новый тип события без ключа краснеет здесь сразу, а не через
400 в бою.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import types
import typing

import pytest

from app.services.events import _PAYLOADS, EventType, dedupe_key_for

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: События, которые ВСЕГДА передают свой ключ явным параметром ``idempotency_key``
#: — им ветка в ``dedupe_key_for`` не нужна. Значение: (файл-источник, причина).
#: Список явный, потому что «ключа нет» и «ключ задаётся снаружи» выглядят
#: одинаково, а стоят разного: первое — 400 в бою, второе — норма.
EVENTS_WITH_OWN_KEY: dict[str, tuple[str, str]] = {
    EventType.API_DEPRECATION_NOTICE.value: (
        "backend/app/services/api_deprecation_notify.py",
        "ключ включает МЕСЯЦ (одно уведомление на арендатора, путь и месяц) — "
        "из payload его не вычислить",
    ),
}


def _dummy(annotation: object) -> object:
    """Значение-заглушка под аннотацию поля payload.

    Модель собирается через ``model_construct`` (без валидации): нам нужна не
    правдоподобность значений, а сам факт, что ключ вычисляется.
    """

    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return _dummy(args[0]) if args else "x"
    if origin in (list, tuple, set):
        return []
    if origin is not None:
        return {}
    if isinstance(annotation, type):
        if issubclass(annotation, bool):
            return False
        if issubclass(annotation, dt.datetime):
            return dt.datetime.now(tz=dt.timezone.utc)
        if issubclass(annotation, dt.date):
            return dt.date.today()
        if issubclass(annotation, int):
            return 1
        if issubclass(annotation, float):
            return 1.0
    return "x"


@pytest.mark.parametrize(
    "event_type",
    sorted(_PAYLOADS, key=lambda e: e.value),
    ids=lambda e: e.value,
)
def test_у_каждого_события_вычисляется_ключ_дедупликации(event_type: EventType) -> None:
    if event_type.value in EVENTS_WITH_OWN_KEY:
        pytest.skip("ключ задаётся явно на месте испускания")
    model_cls = _PAYLOADS[event_type]
    payload = model_cls.model_construct(
        **{name: _dummy(field.annotation) for name, field in model_cls.model_fields.items()}
    )

    key = dedupe_key_for(event_type, payload)

    assert isinstance(key, str) and key.strip(), event_type.value


@pytest.mark.parametrize(
    "event_value", sorted(EVENTS_WITH_OWN_KEY), ids=lambda v: v
)
def test_исключение_не_протухло(event_value: str) -> None:
    """Обратная половина: файл-источник обязан и правда задавать ключ сам.

    Без неё список исключений однажды стал бы кладбищем, и настоящая дыра
    спряталась бы в нём под видом «так и задумано».
    """

    source, reason = EVENTS_WITH_OWN_KEY[event_value]
    assert reason.strip(), event_value
    text = (_REPO_ROOT / source).read_text(encoding="utf-8")
    assert "idempotency_key=" in text, f"{source} больше не задаёт ключ явно"
    assert event_value in text, f"{source} больше не испускает {event_value}"
