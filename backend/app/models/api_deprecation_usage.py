"""OPS-73 срез-3: персистентный учёт использования устаревших поверхностей API.

Платформенные (не арендаторские) данные эксплуатации: строка отвечает на
вопрос разд. 73.2 «видно, КТО ещё на старой версии» и хранит троттлинг
уведомлений. Арендатор здесь — слугом-строкой, а не FK: заголовок ``X-Tenant``
может быть пустым или неизвестным (сканер), и такой трафик тоже надо видеть.
Колонки ``tenant_id`` нет намеренно — таблица вне tenant-RLS контура
(данные видит только платформенный админ, RLS-ратчет её не классифицирует).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SharedModel


class ApiDeprecationUsage(SharedModel):
    __tablename__ = "api_deprecation_usage"

    #: Слуг арендатора из заголовка запроса; "" = запрос без арендатора.
    tenant_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    path_prefix: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Только 2xx: живая интеграция, а не шум сканеров (см. middleware).
    hits_2xx: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("tenant_slug", "path_prefix", name="uq_api_deprecation_usage"),
    )
