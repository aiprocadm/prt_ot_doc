"""Задачи-заглушки не возвращаются, и у каждой назван настоящий механизм (срез-230).

ЧТО БЫЛО. В ``app/tasks/_core.py`` жили восемь фоновых задач, которые
возвращали заготовленный ответ и не делали ничего: обход просроченных
согласований, обновление статуса подписи, обработка входящего сообщения ЭДО,
выдача протокола ЭДО, рассылка вебхуков. Каждое имя встречалось в коде и тестах
РОВНО один раз — в собственном объявлении, то есть их не звал никто.

Вреда они не наносили именно поэтому. Опасны были другим: читающий видел
«обход просроченных согласований» и считал механизм существующим — а он
существовал в другом месте и под другим именем. Ровно та же порода, что мёртвые
таблицы-дубликаты (срез-224) и выдуманные роли (срезы 226–228): имя
правдоподобно, проверки зелёные, работы нет.

ЧТО ДЕРЖИТ ЭТОТ СТОРОЖ. Ни одно из восьми имён не возвращается. Рядом с каждым
записано, ЧТО делает работу на самом деле, — чтобы следующая волна не завела
заглушку заново, «раз механизма нет».
"""

from __future__ import annotations

import pytest

#: Имя снятой заглушки → что делает эту работу на самом деле.
STUBS_AND_REAL_MECHANISM: dict[str, str] = {
    "approval_deadline_sweeper_job": (
        "просроченные согласования помечает `workflow.sla.tick`, а запускает её "
        "обход `workflow.sweep.tick` из расписания (срез-170)"
    ),
    "escalation_scan_job": ("то же самое: заглушка лишь звала соседнюю заглушку"),
    "refresh_signature_status_job": (
        "статус подписи ведут ручки подписания (`routes/pep_signing.py`, "
        "`routes/approval_signing_v1.py`) прямо в запросе"
    ),
    "verify_signature_job": (
        "проверку подписи как шаг конвейера делает `app.tasks.verify_signature_job` "
        "в `celery/tasks/document_jobs_required.py`; здешняя заглушка была тёзкой "
        "с другим именем задачи"
    ),
    "refresh_edo_status_job": (
        "статус сообщения ЭДО обновляет `EdoStatusProjectionService` в ручке "
        "приёма вебхука (`routes/approval_orchestration.py`)"
    ),
    "process_edo_webhook_job": (
        "входящее сообщение принимает `EdoWebhookService.ingest` в той же ручке"
    ),
    "generate_edo_protocol_job": (
        "протокол отдаёт ручка `GET /edo/messages/{id}/protocol` синхронно"
    ),
    "webhook_dispatch_job": (
        "рассылку исходящих ведёт `outbox.dispatch_all` из расписания; у заглушки "
        "вдобавок стояло тестовое значение по умолчанию: арендатор «test»"
    ),
}


@pytest.fixture(scope="module")
def registered_task_names() -> set[str]:
    """Имена задач, которые ЗНАЕТ приложение.

    Модули задач подтягиваются явно: без этого список пуст, и проверка была бы
    зелёной при любом положении дел.
    """

    import app.celery.tasks  # noqa: F401 — регистрирует задачи конвейера
    import app.tasks  # noqa: F401 — регистрирует задачи ядра
    from app.services.celery_app import celery_app

    names = {name for name in celery_app.tasks if not name.startswith("celery.")}
    assert len(names) > 50, f"зарегистрировано всего {len(names)} задач — разбор сломан"
    return names


@pytest.mark.parametrize("stub", sorted(STUBS_AND_REAL_MECHANISM))
def test_заглушка_не_вернулась(stub: str, registered_task_names: set[str]) -> None:
    assert stub not in registered_task_names, (
        f"задача «{stub}» снова зарегистрирована. Работу делает: "
        f"{STUBS_AND_REAL_MECHANISM[stub]}"
    )


def test_у_каждой_снятой_заглушки_назван_настоящий_механизм() -> None:
    """Реестр без причины — это список, а список забывают."""

    empty = sorted(name for name, reason in STUBS_AND_REAL_MECHANISM.items() if len(reason) < 30)
    assert not empty, f"нет объяснения, чем заменена: {empty}"
