"""HTTP-based EDO adapter for production operators (configurable base URL).

Contract: POST ``{base}{outbound_path}`` with JSON
``{ "filename": str, "content_base64": str, "metadata": object }``.
Response JSON should include ``id`` or ``external_id`` and optional ``status``.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from app.core.integration_url_validation import assert_safe_http_base_url

from .interfaces import BaseEDOIntegration, IntegrationStatus

logger = logging.getLogger(__name__)


class HttpEDOIntegration(BaseEDOIntegration):
    """Production-oriented EDO client; requires ``EDO_INTEGRATION_BASE_URL``."""

    name = "http-edo"

    def __init__(
        self,
        *,
        base_url: str,
        api_token: str | None = None,
        timeout_seconds: float = 30.0,
        outbound_path: str = "/v1/outbound/documents",
        app_env: str = "development",
    ) -> None:
        assert_safe_http_base_url(base_url.strip(), app_env=app_env)
        self._base = base_url.rstrip("/")
        self._token = (api_token or "").strip() or None
        self._timeout = timeout_seconds
        self._outbound_path = outbound_path if outbound_path.startswith("/") else f"/{outbound_path}"

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        h: dict[str, str] = {}
        if json_body:
            h["Content-Type"] = "application/json"
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(f"{self._base}/health", headers=self._headers())
                return r.status_code < 500
        except Exception as exc:  # noqa: BLE001
            logger.warning("http_edo.health_failed", extra={"error": str(exc)})
            return False

    async def send_document(
        self, *, content: bytes, filename: str, metadata: dict[str, Any] | None = None
    ) -> IntegrationStatus:
        body = {
            "filename": filename,
            "content_base64": base64.b64encode(content).decode("ascii"),
            "metadata": metadata or {},
        }
        url = f"{self._base}{self._outbound_path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(url, json=body, headers=self._headers(json_body=True))
            r.raise_for_status()
            data = r.json()
            http_status = r.status_code
        ext = data.get("id") or data.get("external_id")
        external_id = str(ext) if ext is not None else f"edo-http-{filename}"
        status = str(data.get("status", "accepted"))
        return IntegrationStatus(
            external_id=external_id,
            status=status,
            details={
                "adapter_type": "http_edo",
                "http_status": http_status,
                "response": data,
            },
            raw=data,
        )

    async def download_document(self, external_id: str) -> bytes:
        url = f"{self._base}/v1/inbound/documents/{external_id}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(url, headers=self._headers())
            r.raise_for_status()
            return r.content

    async def get_document_status(self, external_id: str) -> IntegrationStatus:
        url = f"{self._base}/v1/inbound/documents/{external_id}/status"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(url, headers=self._headers())
            r.raise_for_status()
            data = r.json() if r.content else {}
        return IntegrationStatus(
            external_id=external_id,
            status=str(data.get("status", "unknown")),
            details={"adapter_type": "http_edo", "response": data},
            raw=data,
        )
