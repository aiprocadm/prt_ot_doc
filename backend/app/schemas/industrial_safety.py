"""Схемы контура ПромБеза (Доп. №1 разд. 54.2): реестр ОПО."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from app.schemas.base import BaseSchema


class HazardousFacilityCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    #: обязателен: ОПО без номера в госреестре не существует
    register_number: str = Field(min_length=1, max_length=64)
    hazard_class: str = Field(min_length=1, max_length=8)
    site_id: str | None = Field(default=None, min_length=1, max_length=36)
    registered_on: date | None = None
    excluded_on: date | None = None
    status: str = Field(default="registered", max_length=16)
    responsible: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class HazardousFacilityUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    register_number: str | None = Field(default=None, min_length=1, max_length=64)
    hazard_class: str | None = Field(default=None, min_length=1, max_length=8)
    site_id: str | None = Field(default=None, max_length=36)
    registered_on: date | None = None
    excluded_on: date | None = None
    status: str | None = Field(default=None, max_length=16)
    responsible: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class HazardousFacilityRead(BaseSchema):
    id: str
    name: str
    register_number: str
    hazard_class: str
    #: класс и состояние словами — перевод делает сервер, экран его не дублирует
    hazard_class_label: str
    site_id: str | None = None
    registered_on: date | None = None
    excluded_on: date | None = None
    status: str
    status_label: str
    responsible: str | None = None
    notes: str | None = None


class HazardousFacilityPage(BaseSchema):
    items: list[HazardousFacilityRead]
    total: int


class IndustrialReadinessRead(BaseSchema):
    """Сводка ПромБеза: сколько объектов и какого класса опасности.

    От класса зависит режим надзора (объекты I и II класса — постоянный
    государственный надзор и обязательная декларация промышленной
    безопасности), поэтому разрез по классам — не украшение, а первое, что
    нужно специалисту и проверяющему.

    Считаются ДЕЙСТВУЮЩИЕ объекты: исключённый из госреестра остаётся в
    системе ради истории, но объектом надзора быть перестаёт.
    """

    total_facilities: int
    #: класс → число действующих объектов; ключи — всегда все четыре, чтобы
    #: «ноль объектов I класса» отличался от «поле не пришло»
    by_class: dict[str, int]
    excluded_facilities: int
