"""OPS-73 (разд. 73.2): заголовки Deprecation/Sunset и мониторинг использования.

Что закрепляется:

* ответы устаревшей поверхности несут ``Deprecation`` (RFC 9745), ``Sunset``
  (RFC 8594) и ``Link rel="successor-version"`` — машинно-читаемое предупреждение;
* обычные пути НЕ получают этих заголовков — предупреждение на живой ручке
  обесценило бы предупреждения вообще;
* **ответы ошибок устаревшей ручки тоже предупреждают**: интеграция, получающая
  только 4xx, всё равно должна узнать об устаревании;
* заголовки, выставленные обработчиком, не перетираются;
* каждый вызов считается метрикой (по префиксу реестра, не по сырому пути) и
  логируется с арендатором — «сколько» и «кто» из разд. 73.2;
* матчится самый длинный префикс реестра.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core import metrics as metrics_module
from app.core.api_deprecation import ApiDeprecation, deprecation_for_path
from app.middleware import api_deprecation as mw_module
from app.middleware.api_deprecation import ApiDeprecationMiddleware


@pytest.fixture(autouse=True)
def _propagate_deprecation_logger():
    """caplog ловит записи через root: если более ранний тест в том же
    xdist-воркере включил боевой logging-конфиг (propagate=False у app.*),
    записи до root не доходят — принудительно возвращаем propagate."""
    lg = logging.getLogger("app.middleware.api_deprecation")
    prev = lg.propagate
    lg.propagate = True
    yield
    lg.propagate = prev

ENTRY = ApiDeprecation(
    path_prefix="/api/v1/files-legacy",
    deprecated_since=date(2026, 7, 30),
    sunset=date(2027, 7, 30),
    successor="/api/v1/files",
)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        mw_module,
        "deprecation_for_path",
        lambda path: ENTRY if path.startswith(ENTRY.path_prefix) else None,
    )
    metrics_module.reset_metrics()

    async def legacy(request):
        return JSONResponse({"ok": True})

    async def legacy_with_own_link(request):
        return JSONResponse({"ok": True}, headers={"Link": '<custom>; rel="self"'})

    async def legacy_error(request):
        return JSONResponse({"detail": "nope"}, status_code=403)

    async def modern(request):
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[
            Route("/api/v1/files-legacy/list", legacy),
            Route("/api/v1/files-legacy/own-link", legacy_with_own_link),
            Route("/api/v1/files-legacy/denied", legacy_error),
            Route("/api/v1/files/list", modern),
        ]
    )
    app.add_middleware(ApiDeprecationMiddleware)
    return TestClient(app)


class TestHeaders:
    def test_deprecated_path_carries_the_three_headers(self, client: TestClient) -> None:
        response = client.get("/api/v1/files-legacy/list")

        assert response.status_code == 200
        # RFC 9745: Deprecation — structured-field Date (@unix-секунды). Формат
        # HTTP-даты здесь был бы дефектом: строгий sf-парсер отверг бы значение,
        # и RFC-совместимая интеграция не узнала бы об устаревании.
        assert response.headers["deprecation"] == "@1785369600"
        # RFC 8594: Sunset — обычная HTTP-дата. Форматы РАЗНЫЕ намеренно.
        assert response.headers["sunset"] == "Fri, 30 Jul 2027 00:00:00 GMT"
        assert '</api/v1/files>; rel="successor-version"' in response.headers["link"]
        assert 'rel="deprecation"' in response.headers["link"]

    def test_modern_path_is_untouched(self, client: TestClient) -> None:
        response = client.get("/api/v1/files/list")

        assert "deprecation" not in response.headers
        assert "sunset" not in response.headers

    def test_error_responses_warn_too(self, client: TestClient) -> None:
        """Интеграция, получающая от ручки только 4xx, тоже должна узнать."""

        response = client.get("/api/v1/files-legacy/denied")

        assert response.status_code == 403
        assert "sunset" in response.headers

    def test_handler_headers_are_not_overwritten(self, client: TestClient) -> None:
        response = client.get("/api/v1/files-legacy/own-link")

        # Обработчик поставил свой Link — он важнее подсказки об устаревании.
        assert response.headers["link"] == '<custom>; rel="self"'


class TestUsageRecording:
    """Срез-3: персистентный учёт «кто ещё на старой версии» (только 2xx)."""

    def test_2xx_hit_is_noted_with_tenant_and_prefix(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        noted: list[tuple[str, str]] = []
        monkeypatch.setattr(
            mw_module,
            "note_deprecated_hit",
            lambda tenant_slug, path_prefix: noted.append((tenant_slug, path_prefix)),
        )
        client.get("/api/v1/files-legacy/list", headers={"X-Tenant": "demo"})
        assert noted == [("demo", "/api/v1/files-legacy")]

    def test_4xx_and_modern_paths_are_not_recorded(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        noted: list[tuple[str, str]] = []
        monkeypatch.setattr(
            mw_module,
            "note_deprecated_hit",
            lambda tenant_slug, path_prefix: noted.append((tenant_slug, path_prefix)),
        )
        client.get("/api/v1/files-legacy/denied", headers={"X-Tenant": "demo"})  # 403
        client.get("/api/v1/files/list", headers={"X-Tenant": "demo"})  # живой путь
        assert noted == []


class TestMonitoring:
    def test_calls_are_counted_by_prefix_and_status_class(self, client: TestClient) -> None:
        """Разрез по статусу обязателен: живая интеграция = 2xx, сканерный шум
        по отключённой поверхности = 4xx. Без него критерий отключения «трафик
        упал до нуля» был бы недостижим никогда (найдено ревью)."""

        client.get("/api/v1/files-legacy/list")  # 200
        client.get("/api/v1/files-legacy/denied")  # 403
        client.get("/api/v1/files/list")  # живой путь не считается

        # Label читается через ту же нормализацию, что и запись: sanitize_label
        # превращает "/api/v1/files-legacy" в "api_v1_files-legacy", и чтение по
        # сырому префиксу молча завело бы НОВЫЙ нулевой ряд.
        metric = metrics_module.get_metrics().api_deprecated_requests_total
        label = metrics_module.sanitize_label("/api/v1/files-legacy")
        ok = metric.labels(path_prefix=label, status_class="2xx")._value.get()
        denied = metric.labels(path_prefix=label, status_class="4xx")._value.get()
        assert (ok, denied) == (1, 1)

    def test_tenant_lands_in_the_log(self, client: TestClient, caplog) -> None:
        """Разд. 73.2: «видно, КТО ещё на старой версии»."""

        import logging

        with caplog.at_level(logging.INFO, logger="app.middleware.api_deprecation"):
            client.get("/api/v1/files-legacy/list", headers={"X-Tenant": "acme"})

        records = [r for r in caplog.records if r.message == "api.deprecated_request"]
        assert records, "обращение к устаревшему пути обязано логироваться"
        assert records[0].tenant == "acme"


class TestRegistryMatching:
    def test_longest_prefix_wins(self) -> None:
        from app.core import api_deprecation as reg

        specific = ApiDeprecation(
            path_prefix="/api/v1/x/specific",
            deprecated_since=date(2026, 1, 1),
            sunset=date(2027, 1, 1),
            successor="/api/v1/y",
        )
        broad = ApiDeprecation(
            path_prefix="/api/v1/x",
            deprecated_since=date(2026, 1, 1),
            sunset=date(2027, 1, 1),
            successor="/api/v1/z",
        )
        original = reg.API_DEPRECATIONS
        reg.API_DEPRECATIONS = (broad, specific)
        try:
            assert deprecation_for_path("/api/v1/x/specific/1").successor == "/api/v1/y"
            assert deprecation_for_path("/api/v1/x/other").successor == "/api/v1/z"
            assert deprecation_for_path("/api/v1/unrelated") is None
        finally:
            reg.API_DEPRECATIONS = original
