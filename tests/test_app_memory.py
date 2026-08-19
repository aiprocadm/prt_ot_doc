"""Приложение, созданное ``create_app()``, обязано освобождаться сборщиком мусора.

Зачем этот тест. FastAPI 0.141 кэширует признаки вызываемого объекта
(``_is_coroutine_callable_cached`` и соседи в ``fastapi.dependencies.models``)
в ``functools.lru_cache`` на 4096 записей, живущем всё время процесса. Ключ
кэша — сама функция-обработчик. Поэтому любой обработчик, который замыкает на
себя ``app``, «прибивает» всё приложение к этому кэшу навсегда.

Для прода это незаметно — приложение одно. Для тестов это утечка в чистом
виде: ``app_fixture`` создаёт приложение на каждый тест, и полный прогон
удерживал их все разом (замерено: воркер xdist разрастался до 8-11 ГБ, а
сервер уходил в OOM).

Тест сторожит именно контракт «обработчики не замыкают app», а не конкретную
реализацию: любой новый обработчик с ``app`` в замыкании снова уронит его.
"""

from __future__ import annotations

import gc
import weakref

from app.api.app import create_app


def test_created_app_is_released_by_gc() -> None:
    """После удаления последней явной ссылки приложение не должно оставаться в памяти."""

    app = create_app()
    ref = weakref.ref(app)

    del app
    gc.collect()

    assert ref() is None, (
        "Приложение осталось в памяти после удаления. Обычная причина — обработчик "
        "или middleware, замыкающий на себя `app`: он попадает в вечный lru_cache "
        "FastAPI и удерживает всё приложение. Берите приложение из `request.app`."
    )


def test_repeated_create_app_does_not_accumulate_apps() -> None:
    """Повторные вызовы ``create_app()`` не должны копить приложения в памяти."""

    import fastapi

    def live_apps() -> int:
        return sum(1 for obj in gc.get_objects() if isinstance(obj, fastapi.FastAPI))

    gc.collect()
    before = live_apps()

    for _ in range(5):
        create_app()
    gc.collect()

    after = live_apps()
    assert after - before <= 1, (
        f"После 5 вызовов create_app() в памяти прибавилось {after - before} приложений — "
        "они не освобождаются (см. test_created_app_is_released_by_gc)."
    )
