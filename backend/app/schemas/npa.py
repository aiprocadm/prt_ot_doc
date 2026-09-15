"""Pydantic schemas for normative legal acts."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.domains.npa.scope import REGISTRY_SCOPE, TENANT_SCOPE


class NpaClauseRead(BaseModel):
    id: str
    code: str = Field(max_length=128)
    text: str

    model_config = {
        "from_attributes": True,
    }


class NpaActRead(BaseModel):
    id: str
    code: str = Field(max_length=128)
    title: str
    edition: str
    valid_from: date | None = None
    valid_to: date | None = None
    clauses: list[NpaClauseRead] = []
    #: Срез-201: из какого ящика акт — общий реестр платформы или собственный
    #: акт арендатора. Витрина обязана их различать: «Приказ Минтруда» и «наш
    #: приказ по организации» лежат в одном списке, а весят разное.
    scope: str = REGISTRY_SCOPE
    scope_title: str = ""

    model_config = {
        "from_attributes": True,
    }


class NpaActListResponse(BaseModel):
    items: list[NpaActRead]
    #: Срез-141: может ли пришедший заводить акты и редакции. Реестр общий для
    #: всех арендаторов, поэтому право есть только у владельца платформы —
    #: витрина по этому флагу показывает или прячет кнопку «Добавить акт».
    can_manage: bool = False
    #: Срез-201: а свой собственный акт завести может? Это ДРУГОЕ право: общий
    #: реестр закрыт всем, кроме владельца платформы, а свой приказ ведёт любой
    #: арендатор. Без отдельного флага витрина прятала бы кнопку «Добавить свой
    #: акт» ровно у тех, кому она и нужна.
    can_create_own: bool = False


class NpaClauseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1)


class NpaActCreate(BaseModel):
    """Срез-141: заявка на новый акт реестра — вместе с пунктами.

    Пункты идут в той же заявке, потому что отдельной ручки для них нет и не
    нужно: пункт без акта не существует, а акт без пунктов — законен (пункты
    можно не расписывать, пока на них не ссылается оценка влияния).
    """

    #: Срез-201: в какой ящик писать. Значение по умолчанию — общий реестр:
    #: так ручка ведёт себя ровно как до среза, и старые вызовы не меняют
    #: смысла молча.
    scope: Literal[REGISTRY_SCOPE, TENANT_SCOPE] = REGISTRY_SCOPE
    code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    edition: str = Field(min_length=1, max_length=128)
    valid_from: date | None = None
    valid_to: date | None = None
    clauses: list[NpaClauseCreate] = []

    @model_validator(mode="after")
    def _check(self) -> NpaActCreate:
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to не может быть раньше valid_from")
        codes = [clause.code for clause in self.clauses]
        if len(codes) != len(set(codes)):
            raise ValueError("коды пунктов внутри акта должны быть уникальны")
        return self


class NpaRevisionCreate(BaseModel):
    revision_code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    effective_from: date | None = None
    effective_to: date | None = None
    change_summary: str | None = None

    @model_validator(mode="after")
    def _check(self) -> NpaRevisionCreate:
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to не может быть раньше effective_from")
        return self


class NpaRevisionRead(BaseModel):
    id: str
    act_id: str
    revision_code: str
    title: str
    effective_from: date | None = None
    effective_to: date | None = None
    change_summary: str | None = None

    model_config = {
        "from_attributes": True,
    }


class NpaBindingContext(BaseModel):
    """Область действия связи: кого и где она касается (срез-197).

    Не свободный словарь: лишние ключи отвергаются. Свободное поле здесь уже
    было — именно из-за него сводка влияния читала то, что никто не мог
    записать, и всегда показывала ноль.
    """

    role_code: str | None = Field(default=None, max_length=64)
    site_id: str | None = Field(default=None, max_length=36)

    model_config = {"extra": "forbid"}


class NpaBindingCreate(BaseModel):
    """Срез-142: связь акта с сущностью арендатора — то, что читает оценка влияния."""

    entity_type: Literal["document", "template_version", "pack"]
    entity_id: str = Field(min_length=1, max_length=36)
    ref: str | None = Field(default=None, max_length=255)
    #: Срез-197: «кого и где касается». До него ручка ставила контекст пустым, и
    #: категории сводки, читавшие его, были вечными нулями.
    context: NpaBindingContext = Field(default_factory=NpaBindingContext)


class NpaBindingRead(BaseModel):
    id: str
    npa_id: str
    entity_type: str
    #: Область действия связи словами (срез-197): роль и площадка, если заданы.
    context: dict[str, str] = Field(default_factory=dict)
    entity_id: str
    ref: str | None = None
    #: Имя сущности для витрины — документ, шаблон или пакет по-человечески,
    #: а не идентификатор.
    title: str
    #: Срез-144 (разд. 19.4): по какой редакции связь сверяли в последний раз
    #: и не разошлась ли она с действующей. ``stale`` — «не пересмотрена».
    reviewed_revision_id: str | None = None
    reviewed_revision_code: str | None = None
    stale: bool = False
