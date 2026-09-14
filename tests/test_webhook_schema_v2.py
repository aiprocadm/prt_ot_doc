"""Сторож: схема 2 сводит два конверта и две единицы подписи (OPS-73, срез-191).

ЧТО БЫЛО НЕ ТАК. Конвейера доставки два, и они расходились дважды.

1. **Конверт.** У подписок — `id`/`type`/`event_type`/`occurred_at`; у очереди —
   `event_id`/`event_type`/`tenant_id`/`headers`. Подписчик, получающий события
   с обоих путей, вынужден держать два разбора одного и того же.
2. **ЕДИНИЦЫ ВРЕМЕНИ В ПОДПИСИ — главная находка среза.** Конвейер подписок
   ставил `X-Timestamp` в МИЛЛИСЕКУНДАХ, конвейер очереди — `X-Signature-Ts` в
   СЕКУНДАХ. Подписчик, проверяющий подпись по описанию, получал несходящуюся
   подпись на половине доставок. Выглядит это как попытка подделки, а не как
   расхождение форматов, — и чинится в последнюю очередь.

ПОЧЕМУ НЕ «ПРОСТО ПОЧИНИТЬ». Любая правка формата — ломающее изменение для всех
живых подписчиков разом. Поэтому версия стала свойством ПОДПИСЧИКА: платформа
шлёт каждому по той схеме, к которой он готов, а старая продолжает работать.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_webhook_schema_v2.py -v``.
"""

from __future__ import annotations

import pytest

from app.core import webhook_contract as wc


class TestВыборСхемы:
    def test_не_задано_означает_умолчание(self) -> None:
        """Пустая строка и None — одно и то же: иначе подписчик остался бы без доставок."""

        assert wc.resolve_schema_version(None) == wc.WEBHOOK_SCHEMA_VERSION
        assert wc.resolve_schema_version("") == wc.WEBHOOK_SCHEMA_VERSION
        assert wc.resolve_schema_version("   ") == wc.WEBHOOK_SCHEMA_VERSION

    def test_подписчик_переключается_поштучно(self) -> None:
        assert wc.resolve_schema_version("2") == wc.WEBHOOK_SCHEMA_VERSION_V2
        assert wc.resolve_schema_version("1") == wc.WEBHOOK_SCHEMA_VERSION

    def test_умолчание_развёртывания_действует_когда_у_подписчика_не_задано(self) -> None:
        assert wc.resolve_schema_version(None, default="2") == wc.WEBHOOK_SCHEMA_VERSION_V2
        # Выбор подписчика сильнее умолчания: иначе переключение развёртывания
        # утащило бы за собой тех, кто ещё не готов.
        assert wc.resolve_schema_version("1", default="2") == wc.WEBHOOK_SCHEMA_VERSION

    def test_опечатка_не_включает_ничего_нового(self) -> None:
        """Молча слать по неизвестной версии значило бы сломать живую доставку."""

        assert wc.resolve_schema_version("v2") == wc.WEBHOOK_SCHEMA_VERSION
        assert wc.resolve_schema_version("99") == wc.WEBHOOK_SCHEMA_VERSION


class TestКонвертВторойСхемы:
    def test_конверт_единый_и_полный(self) -> None:
        envelope = wc.build_envelope_v2(
            event_id="e-1",
            event_type="DocumentSigned",
            tenant_id="t-1",
            occurred_at="2026-09-14T12:00:00+00:00",
            correlation_id="corr-1",
            payload={"document_id": "d-1"},
        )
        assert set(envelope) == set(wc.ENVELOPE_KEYS_V2)
        assert envelope["schema_version"] == "2"
        assert envelope["id"] == "e-1"
        assert envelope["type"] == "DocumentSigned"
        assert envelope["tenant_id"] == "t-1"

    def test_конверты_двух_конвейеров_в_первой_схеме_действительно_разные(self) -> None:
        """Закрепляем ПРИЧИНУ существования схемы 2, а не только её саму.

        Если однажды конверты первой схемы сойдутся сами, этот тест упадёт и
        заставит перечитать решение — а не оставит объяснение, ставшее ложным.
        """

        assert wc.DISPATCHER_ENVELOPE_KEYS != wc.OUTBOX_TASK_BODY_KEYS

    def test_схема_2_сводит_оба_конвейера_к_одному_виду(self) -> None:
        assert wc.ENVELOPE_KEYS_V2 != wc.DISPATCHER_ENVELOPE_KEYS
        assert wc.ENVELOPE_KEYS_V2 != wc.OUTBOX_TASK_BODY_KEYS
        # Ключи, ради которых всё затевалось: одинаковое имя события и
        # арендатор в теле у ОБОИХ путей.
        assert {"id", "type", "tenant_id", "payload"} <= wc.ENVELOPE_KEYS_V2

    def test_единица_времени_во_второй_схеме_названа_явно(self) -> None:
        """Единица подписи — часть контракта, а не деталь реализации."""

        assert wc.SIGNATURE_TIME_UNIT[wc.WEBHOOK_SCHEMA_VERSION_V2] == "seconds"

    def test_пустая_полезная_нагрузка_не_ломает_конверт(self) -> None:
        envelope = wc.build_envelope_v2(
            event_id="e",
            event_type="t",
            tenant_id="t",
            occurred_at="now",
            correlation_id="c",
            payload=None,
        )
        assert envelope["payload"] == {}


@pytest.mark.parametrize("version", sorted(wc.SUPPORTED_SCHEMA_VERSIONS))
def test_каждая_поддержанная_версия_объявляет_единицу_подписи(version: str) -> None:
    """Версия без объявленной единицы времени — та же ловушка, что была."""

    assert version in wc.SIGNATURE_TIME_UNIT
