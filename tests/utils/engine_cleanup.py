"""Освобождение кэшей SQLAlchemy, переживающих закрытый тестовый движок.

Зачем это нужно. ``app_fixture`` создаёт свой движок на каждый тест — так
достигается изоляция. Но ``await engine.dispose()`` закрывает только пул
соединений: сам движок с его диалектом продолжает жить, пока на него есть
ссылки. А ссылки остаются в кэшах скомпилированных запросов у ORM-мапперов
(``Mapper._compiled_cache``, до 100 записей на маппер): диалект входит в ключ
такой записи, а мапперы — атрибуты классов моделей и живут всё время процесса.

Итог без очистки: каждый тест оставлял в памяти два диалекта, каждый со своим
кэшем адаптированных типов (~120 ``Enum``). На полном прогоне это давало
воркеру xdist рост до 8-11 ГБ и уводило машину в OOM.

Кэш — чисто ускоряющий: SQLAlchemy заново скомпилирует запрос при следующем
обращении, поведение и результаты не меняются. Сторож — ``tests/test_engine_memory.py``.
"""

from __future__ import annotations

from app.db import Base, SharedBase, TenantBase


def release_mapper_query_caches() -> None:
    """Очистить кэши скомпилированных запросов у всех ORM-мапперов."""

    seen: set[int] = set()
    for base in (Base, SharedBase, TenantBase):
        registry = getattr(base, "registry", None)
        if registry is None:  # pragma: no cover - защитная ветка
            continue
        for mapper in registry.mappers:
            if id(mapper) in seen:
                continue
            seen.add(id(mapper))
            # Берём именно из ``__dict__``: ``_compiled_cache`` — memoized-свойство,
            # обращение через атрибут СОЗДАЛО бы кэш там, где его ещё нет.
            cache = mapper.__dict__.get("_compiled_cache")
            if cache is not None:
                cache.clear()
