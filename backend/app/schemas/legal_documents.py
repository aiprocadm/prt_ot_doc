"""Схемы юридических текстов (BIZ-52 срез-5, Доп. №1 разд. 52.2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.domains.reseller.legal import LegalDocumentKind
from app.schemas.base import BaseSchema


class LegalDocumentRead(BaseSchema):
    """Действующая редакция — то, что показывают человеку."""

    kind: LegalDocumentKind
    title: str
    body: str
    version: int
    #: Чей текст: `self` / `reseller`. Партнёру нужно видеть, что у клиентов
    #: действует именно его редакция, а не чужая.
    source: str
    published_at: datetime


class LegalDocumentSummary(BaseSchema):
    """Строка списка: что вообще есть у этого арендатора, без тела текста."""

    kind: LegalDocumentKind
    title: str
    version: int
    source: str
    published_at: datetime


class LegalDocumentList(BaseSchema):
    items: list[LegalDocumentSummary]


class LegalAcceptanceStatus(BaseSchema):
    """Состояние одного вида текста для текущего пользователя (срез-11)."""

    kind: LegalDocumentKind
    title: str | None = None
    #: Действующая редакция. `None` — текста нет вовсе, принимать нечего.
    current_version: int | None = None
    #: Принятая этим человеком редакция. `None` — не принимал.
    accepted_version: int | None = None
    accepted_at: datetime | None = None
    #: Принято ли ИМЕННО действующее.
    accepted: bool = False
    #: Принята прежняя редакция, вышла новая. Отдельный признак, а не «не
    #: принято»: человеку показывают «условия изменились», а не «примите
    #: оферту» — это разные сообщения.
    outdated: bool = False


class LegalAcceptanceState(BaseSchema):
    """Что требует подписи от текущего пользователя."""

    items: list[LegalAcceptanceStatus]
    #: Виды, которые ещё не приняты. Дублирует признаки строк намеренно: без
    #: этого поля интерфейсу пришлось бы вычислять «надо ли показывать баннер»
    #: самому, то есть завести вторую правду о готовности.
    pending: list[LegalDocumentKind]


class LegalAcceptanceRead(BaseSchema):
    """Записанное принятие."""

    kind: LegalDocumentKind
    doc_version: int
    source: str
    accepted_at: datetime


class LegalDocumentPublish(BaseSchema):
    """Публикация новой редакции.

    Номер версии НЕ принимается от клиента: его выдаёт сервер как «предыдущая
    + 1». Прими номер снаружи — и две публикации подряд смогут получить один
    номер, а «какая редакция действовала» перестанет иметь однозначный ответ.
    """

    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
