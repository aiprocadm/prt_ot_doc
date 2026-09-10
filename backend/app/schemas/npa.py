"""Pydantic schemas for normative legal acts."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator


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

    model_config = {
        "from_attributes": True,
    }


class NpaActListResponse(BaseModel):
    items: list[NpaActRead]
    #: Срез-141: может ли пришедший заводить акты и редакции. Реестр общий для
    #: всех арендаторов, поэтому право есть только у владельца платформы —
    #: витрина по этому флагу показывает или прячет кнопку «Добавить акт».
    can_manage: bool = False


class NpaClauseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1)


class NpaActCreate(BaseModel):
    """Срез-141: заявка на новый акт реестра — вместе с пунктами.

    Пункты идут в той же заявке, потому что отдельной ручки для них нет и не
    нужно: пункт без акта не существует, а акт без пунктов — законен (пункты
    можно не расписывать, пока на них не ссылается оценка влияния).
    """

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
