"""SEC-64 (разд. 64.1): заголовки безопасности на уровне приложения.

ТЗ называет их дважды: «XSS → CSP-заголовки» и «Security Misconfiguration →
Secure headers». В репозитории они были только в ``proxy/nginx.conf``, а конфиг
живого стенда (``infra/stand/nginx/``) их не ставил вовсе — то есть на реальном
развёртывании их не было ни одного.

Ставить их в приложении, а не только на прокси, принципиально: прокси меняются
(nginx, Traefik, облачный балансировщик, прямой доступ в dev), и защита, которая
живёт только в одном из них, отсутствует во всех остальных. Прокси при этом никуда
не девается — вместе получается defense-in-depth.

Что ставится:

* ``Content-Security-Policy`` — для JSON-API строгий ``default-src 'none'``:
  ответы не должны ничего подгружать, а если в них попадёт HTML (например,
  отражённое сообщение об ошибке), браузеру нечего будет исполнить;
* ``X-Content-Type-Options: nosniff`` — запрет угадывания типа: загруженный
  «текстовый» файл не должен быть исполнен как HTML/JS;
* ``X-Frame-Options`` + ``frame-ancestors 'none'`` — clickjacking;
* ``Referrer-Policy: no-referrer`` — токен в query портала не утечёт хотя бы
  через Referer (SEC-68);
* ``Cross-Origin-Opener-Policy`` / ``Cross-Origin-Resource-Policy`` — изоляция
  контекста;
* ``Strict-Transport-Security`` — **только** в production/staging: за
  TLS-терминирующим прокси приложение видит http, и слать HSTS из dev-запуска по
  http значит закрепить в браузере разработчика редирект на https для localhost.

Документация (`/docs`, `/redoc`) исключена из CSP: Swagger UI тянет ассеты с CDN,
и строгая политика его ломает. В production документация и так отключена
(``_disable_openapi_in_production``), поэтому исключение не расширяет поверхность.
"""

from __future__ import annotations

from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = ["SecurityHeadersMiddleware", "DEFAULT_API_CSP"]

# Строгая политика для JSON-API: ответы не подгружают ничего и не встраиваются.
DEFAULT_API_CSP = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)

_STATIC_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    # Явно отключаем мощные API браузера: платформе они не нужны, а запрет
    # ограничивает ущерб от внедрённого скрипта.
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
)


class SecurityHeadersMiddleware:
    """Добавляет заголовки безопасности ко всем ответам приложения."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        csp: str = DEFAULT_API_CSP,
        hsts_max_age: int = 0,
        exempt_path_prefixes: Iterable[str] = (),
    ) -> None:
        self.app = app
        self.csp = csp
        self.hsts_max_age = int(hsts_max_age or 0)
        self.exempt_path_prefixes = tuple(exempt_path_prefixes)

    def _headers_for(self, path: str) -> list[tuple[bytes, bytes]]:
        headers = list(_STATIC_HEADERS)
        if self.csp and not path.startswith(self.exempt_path_prefixes):
            headers.append((b"content-security-policy", self.csp.encode("latin-1")))
        if self.hsts_max_age > 0:
            headers.append(
                (
                    b"strict-transport-security",
                    f"max-age={self.hsts_max_age}; includeSubDomains".encode("latin-1"),
                )
            )
        return headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        extra = self._headers_for(str(scope.get("path", "/")))

        async def _send(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers = message.setdefault("headers", [])
                # Не перетираем то, что уже выставил обработчик или прокси-слой:
                # у ответа может быть осознанно другая политика (например, у
                # отдаваемого файла).
                present = {name.lower() for name, _ in headers}
                headers.extend(
                    (name, value) for name, value in extra if name not in present
                )
            await send(message)

        await self.app(scope, receive, _send)
