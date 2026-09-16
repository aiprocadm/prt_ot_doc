"""SEC-64, разд. 64.1, строка «Broken Access Control»: чужая строка не выдаётся НА ЧТЕНИИ.

ЗАЧЕМ. Таблица OWASP Top-10 требует буквально: «IDOR на ВСЕХ ``/{id}``-роутах;
cross-tenant deny». Слово ВСЕХ проверяется только обходом, и обход показал
устройство защиты: в приложении 567 ручек с номером в пути, 244 из них достают
объект по номеру, и почти каждая привязывает его к арендатору САМА — фильтром,
служебным помощником или сервисом, созданным под арендатора.

Защита, которую надо повторить 244 раза, держится на памяти автора. Одна забытая
строка — и ручка отдаёт чужой объект, причём выглядит это как обычный успешный
ответ: ни ошибки, ни записи в журнале. На PostgreSQL второй рубеж есть (RLS,
разд. 65), но он прикрывает только таблицы из реестра и только когда в сессии
выставлены его переменные.

ЧТО ЗДЕСЬ. Один рубеж на чтение: когда ORM ОТДАЁТ объект арендатора в сессию,
у которой есть свой арендатор, чужая строка не выдаётся вовсе. Это не замена
фильтрам в ручках — это второй рубеж, как RLS, только работающий и на SQLite,
и в фоновых задачах.

ПОЧЕМУ ОТКАЗ, А НЕ ЗАПИСЬ В ЖУРНАЛ. Запись в журнале означала бы, что чужие
данные всё-таки ушли наружу, просто мы об этом знаем. Отказ означает, что не
ушли.

ЕСТЬ ЗАКОННОЕ ЧТЕНИЕ ЧУЖОГО — И ОНО НАЗЫВАЕТСЯ ВСЛУХ. Управляющий арендатор
(партнёр, ведущий клиентов) по разд. 63 обязан видеть данные своих клиентов.
Такое чтение разрешается ЯВНО и с причиной — ``allow_cross_tenant_read``.
Молчаливого исключения нет: если чтение чужого законно, это решение, и оно
записано в коде словами.

ЧУЖАЯ СТРОКА НЕ «ЗАПРЕЩЕНА», А НЕ СУЩЕСТВУЕТ — И ЭТО ПОЙМАНО ПРОГОНОМ.
Первая версия рубежа роняла запрос ошибкой. Собственный прогон показал, чем это
плохо, на живой проверке ``test_complete_rejects_cross_tenant_file_404``: ручка
и без рубежа отвечала правильно — «файл-доказательство не найден», — а рубеж
подменял этот точный ответ общим. Хуже того, первый вариант отвечал «нет
доступа», а такой ответ САМ ПОДТВЕРЖДАЕТ, что объект с таким номером есть, —
ровно то, что выясняет перебирающий номера.

Поэтому рубеж устроен как RLS: чужие строки просто НЕ ПОПАДАЮТ в выдачу
запроса (условие подмешивается к каждому запросу ORM). Ручка получает пустоту и
говорит СВОИМИ словами то, что и должна: такого объекта нет. Проверка
загруженной строки осталась ВТОРОЙ сетью — на случай пути, где условие
подмешать не удалось.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "CROSS_TENANT_READ_KEY",
    "CrossTenantReadError",
    "allow_cross_tenant_read",
    "hide_foreign_rows",
    "refuse_foreign_row",
]

#: Ключ в ``session.info``, которым чтение чужого арендатора разрешается явно.
#: Хранится ПРИЧИНА, а не ``True``: разрешение без причины через полгода никто
#: не сможет ни объяснить, ни снять.
CROSS_TENANT_READ_KEY = "cross_tenant_read_reason"


class CrossTenantReadError(LookupError):
    """Сессия одного арендатора получила строку другого.

    Это не ошибка пользователя, а сорванная попытка выдать чужие данные:
    либо ручка забыла фильтр, либо номер объекта подобран снаружи.

    ПОЧЕМУ «НЕ НАЙДЕНО», А НЕ «НЕТ ДОСТУПА». Ответ «нет доступа» САМ
    ПОДТВЕРЖДАЕТ, что объект с таким номером существует, — а именно это и
    выясняет тот, кто перебирает номера. Для арендатора чужого объекта просто
    НЕТ. Поймано собственным прогоном: первая версия наследовалась от ошибки
    доступа, и проверка `test_complete_rejects_cross_tenant_file_404` честно
    покраснела — она требует 404 там, где ручка и так отвечала правильно.
    """

    def __init__(self, model: str, row_tenant: str, session_tenant: str) -> None:
        super().__init__(
            f"строка {model} принадлежит другому арендатору "
            f"({row_tenant} вместо {session_tenant})"
        )
        self.model = model
        self.row_tenant = row_tenant
        self.session_tenant = session_tenant


@contextmanager
def allow_cross_tenant_read(session: Any, *, reason: str) -> Iterator[None]:
    """Разрешить этой сессии читать строки других арендаторов — с причиной.

    Пример законного случая: управляющий арендатор смотрит данные клиента,
    которого ведёт (разд. 63). Причина попадает в журнал при первом же чужом
    чтении, поэтому она пишется словами, а не «надо».
    """

    if not reason or len(reason.strip()) < 10:
        raise ValueError("причина чтения чужого арендатора обязана быть написана словами")
    info = session.info
    previous = info.get(CROSS_TENANT_READ_KEY)
    info[CROSS_TENANT_READ_KEY] = reason
    try:
        yield
    finally:
        if previous is None:
            info.pop(CROSS_TENANT_READ_KEY, None)
        else:
            info[CROSS_TENANT_READ_KEY] = previous


def _criteria_for(model: Any, tenant_id: str) -> Any:
    """Условие «строка принадлежит этому арендатору» для одной модели.

    Условие задаётся ФУНКЦИЕЙ ОТ САМОЙ МОДЕЛИ, а не готовым выражением. Разница
    не косметическая: когда та же таблица попадает в запрос ВТОРОЙ раз под
    псевдонимом (обычное соединение — стажировка и её наставник из той же
    таблицы людей), готовое выражение осталось бы привязанным к таблице без
    псевдонима, и запрос бы не собрался. Поймано собственным прогоном: десять
    проверок карточки сотрудника легли с ошибкой «нет такого столбца».
    """

    from sqlalchemy.orm import with_loader_criteria  # noqa: PLC0415

    return with_loader_criteria(
        model, lambda cls: cls.tenant_id == tenant_id, include_aliases=True
    )


def _session_tenant(session: Any) -> str:
    """Арендатор сессии или пустая строка, если его нет."""

    info = getattr(session, "info", None)
    if not isinstance(info, dict):
        return ""
    return str(info.get("tenant_id") or "").strip()


def hide_foreign_rows(orm_execute_state: Any) -> None:
    """ОСНОВНОЙ рубеж: к каждому запросу ORM подмешивается условие по арендатору.

    Работает как RLS, только на уровне приложения: чужие строки не «запрещены»,
    их просто НЕТ в выдаче. Ручка получает пустоту и отвечает своими словами —
    точнее и понятнее, чем общий отказ от рубежа.
    """

    if not orm_execute_state.is_select:
        return
    session = orm_execute_state.session
    tenant_id = _session_tenant(session)
    if not tenant_id:
        # Служебная работа без арендатора — сравнивать не с чем.
        return
    info = session.info
    if info.get(CROSS_TENANT_READ_KEY):
        return
    # Внутренние догрузки (обновление объекта, ленивые связи) условие уже
    # получили при первом запросе; подмешивать его второй раз незачем.
    if orm_execute_state.is_column_load or orm_execute_state.is_relationship_load:
        return

    # Условие ставится ПОИМЁННО по моделям, которые участвуют в этом запросе.
    #
    # ПОЧЕМУ НЕ ПО ОБЩЕЙ ЗАГОТОВКЕ. Арендаторских моделей в продукте ДВА
    # СЕМЕЙСТВА: одни наследуют общую заготовку `TenantBaseModel`, другие
    # объявлены сами по себе и лишь помечены `__tenant_model__`. Условие по
    # одной заготовке накрыло бы только первое семейство — и рубеж вёл бы себя
    # по-разному у разных таблиц. Поймано собственным прогоном.
    options = []
    for mapper in orm_execute_state.all_mappers:
        model = mapper.class_
        if not getattr(model, "__tenant_model__", False):
            continue
        if "tenant_id" not in mapper.columns:
            continue
        options.append(_criteria_for(model, tenant_id))
    if options:
        orm_execute_state.statement = orm_execute_state.statement.options(*options)


def refuse_foreign_row(session: Any, instance: Any) -> None:
    """Обработчик события «ORM отдала объект в сессию».

    Намеренно дешёвый: сравнение двух строк и выход. Событие срабатывает на
    КАЖДЫЙ загруженный объект, поэтому здесь не может быть ни запросов к базе,
    ни разбора чего бы то ни было.
    """

    tenant_id = getattr(instance, "tenant_id", None)
    if tenant_id is None:
        return
    info = getattr(session, "info", None)
    if not isinstance(info, dict):
        return
    session_tenant = str(info.get("tenant_id") or "").strip()
    if not session_tenant:
        # У сессии нет арендатора — это общая или служебная работа (миграции,
        # управление арендаторами, стартовая настройка). Запрещать тут значило
        # бы сломать то, что к данным арендаторов отношения не имеет.
        return
    row_tenant = str(tenant_id).strip()
    if row_tenant == session_tenant:
        return

    reason = info.get(CROSS_TENANT_READ_KEY)
    if reason:
        logger.info(
            "db.cross_tenant_read.allowed",
            extra={
                "model": type(instance).__name__,
                "row_tenant_id": row_tenant,
                "session_tenant_id": session_tenant,
                "reason": reason,
            },
        )
        return

    logger.warning(
        "db.cross_tenant_read.refused",
        extra={
            "model": type(instance).__name__,
            "row_id": getattr(instance, "id", None),
            "row_tenant_id": row_tenant,
            "session_tenant_id": session_tenant,
        },
    )
    raise CrossTenantReadError(type(instance).__name__, row_tenant, session_tenant)
