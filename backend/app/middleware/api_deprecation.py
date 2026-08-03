"""OPS-73 (разд. 73.2): заголовки ``Deprecation``/``Sunset`` и мониторинг.

Закрывает два этапа управляемого устаревания:

* **Предупреждения** — каждый ответ устаревшей поверхности несёт заголовки
  ``Deprecation`` (RFC 9745: момент объявления), ``Sunset`` (RFC 8594: дата
  отключения) и ``Link rel="successor-version"`` — машинно-читаемо, чтобы
  интеграция могла заметить их сама, а не ждать письма;
* **Мониторинг использования** — разд. 73.2: «видно, КТО ещё на старой версии,
  чтобы не отключить используемое». Два канала осознанно: метрика
  ``api_deprecated_requests_total{path_prefix}`` отвечает на «сколько», а
  структурный лог с арендатором — на «кто». Тащить арендатора в label метрики
  нельзя: перебор арендаторов раздувает кардинальность Prometheus, и мониторинг
  сам стал бы проблемой эксплуатации.

Чистый ASGI-слой по образцу ``security_headers.py``: перехватывает
``http.response.start`` и ДОПИСЫВАЕТ заголовки, не перетирая выставленные
обработчиком. Ответы ошибок тоже получают заголовки — интеграция, которая
получает от устаревшей ручки только 4xx, всё равно должна узнать об устаревании.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from email.utils import format_datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.api_deprecation import ApiDeprecation, deprecation_for_path
from app.core.metrics import get_metrics
from app.services.api_deprecation_recorder import note_deprecated_hit

__all__ = ["ApiDeprecationMiddleware"]

logger = logging.getLogger(__name__)


def _http_date(day) -> str:
    """Дата → IMF-fixdate (RFC 8594 требует его для ``Sunset``)."""

    return format_datetime(datetime.combine(day, time(0, 0), tzinfo=timezone.utc), usegmt=True)


def _sf_date(day) -> str:
    """Дата → structured-field Date (``@<unix-секунды>``).

    Финальный RFC 9745 (март 2025) определяет ``Deprecation`` как sf-Date —
    IMF-fixdate там был только в черновике. Строгий structured-fields парсер
    отверг бы HTTP-дату, и RFC-совместимая интеграция НЕ узнала бы об
    устаревании — при том что весь смысл заголовка в машинной читаемости.
    Найдено состязательным ревью против текста финального RFC.
    """

    epoch = int(datetime.combine(day, time(0, 0), tzinfo=timezone.utc).timestamp())
    return f"@{epoch}"


class ApiDeprecationMiddleware:
    """Ставит заголовки устаревания и считает обращения к устаревшим путям."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def _headers_for(entry: ApiDeprecation) -> list[tuple[bytes, bytes]]:
        link = (
            f'<{entry.successor}>; rel="successor-version", '
            f'<{entry.docs_url}>; rel="deprecation"'
        )
        return [
            # RFC 9745: sf-Date (@epoch). RFC 8594: HTTP-дата. Форматы РАЗНЫЕ
            # намеренно — каждый заголовок в том виде, которого требует его RFC.
            (b"deprecation", _sf_date(entry.deprecated_since).encode("latin-1")),
            (b"sunset", _http_date(entry.sunset).encode("latin-1")),
            (b"link", link.encode("latin-1")),
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", "/"))
        entry = deprecation_for_path(path)
        if entry is None:
            # Обычные пути не платят ничего, кроме одного поиска по короткому
            # кортежу — реестр устаревших поверхностей по определению мал.
            await self.app(scope, receive, send)
            return

        # «Кто ещё на старой версии»: заголовок арендатора уже есть в запросе,
        # и лог с ним — прямой ответ на вопрос разд. 73.2. Метрика — «сколько».
        tenant = ""
        for name, value in scope.get("headers", ()):
            if name in (b"x-tenant", b"x-tenant-slug"):
                tenant = value.decode("latin-1", "replace")
                break
        extra_headers = self._headers_for(entry)

        async def _send(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers = message.setdefault("headers", [])
                present = {name.lower() for name, _ in headers}
                headers.extend(
                    (name, value) for name, value in extra_headers if name not in present
                )
                # Учёт — ПО СТАТУСУ ответа, а не по факту запроса. Найдено
                # ревью: в production legacy-поверхность отключена, и каждый
                # интернет-сканер получал бы 404, но растил счётчик — критерий
                # отключения «трафик не растёт» стал бы недостижим навсегда.
                # Живая интеграция видна как 2xx; шум остаётся в 4xx.
                status = int(message.get("status", 0))
                status_class = f"{status // 100}xx" if status else "unknown"
                get_metrics().record_api_deprecated_request(
                    path_prefix=entry.path_prefix, status_class=status_class
                )
                # Срез-3: персистентный учёт «кто ещё» — только живой трафик
                # (2xx), тем же критерием, что и решение об отключении.
                if status_class == "2xx":
                    note_deprecated_hit(tenant, entry.path_prefix)
                logger.info(
                    "api.deprecated_request",
                    extra={
                        "path": path,
                        "deprecated_prefix": entry.path_prefix,
                        "sunset": entry.sunset.isoformat(),
                        "tenant": tenant,
                        "status": status,
                    },
                )
            await send(message)

        await self.app(scope, receive, _send)
