"""Utilities for enqueuing uploaded files for ClamAV scanning."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from queue import Empty, SimpleQueue
from typing import BinaryIO, Protocol

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import session_scope
from app.domains.files import s3
from app.models.file import File, FileScanStatus

logger = logging.getLogger(__name__)

__all__ = [
    "ClamAVScanRequest",
    "ClamAVVerdict",
    "ClamAVScanOutcome",
    "QuarantinePublisher",
    "MemoryQuarantinePublisher",
    "enqueue_scan_request",
    "get_quarantine_publisher",
    "reset_quarantine_publisher",
    "get_clamav_client",
    "reset_clamav_client",
    "process_scan_request",
]


class ClamAVScanRequest(BaseModel):
    """Message describing an object that must be scanned by ClamAV."""

    model_config = ConfigDict(extra="forbid")

    bucket: str
    key: str
    size: int = Field(ge=0)
    mime: str
    sha256: str = Field(min_length=64, max_length=64)
    tenant_id: str
    tenant_slug: str


class ClamAVVerdict(str, Enum):
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"


@dataclass(slots=True)
class ClamAVScanOutcome:
    status: ClamAVVerdict
    signature: str | None = None
    raw: str = "unknown"


class ClamAVError(RuntimeError):
    """Raised when the ClamAV client cannot complete a scan."""


class ClamAVScanner(Protocol):
    """Interface implemented by ClamAV scanning clients."""

    def scan_stream(self, stream: BinaryIO) -> ClamAVScanOutcome:
        """Scan a binary stream and return a verdict."""


class ClamAVClient:
    """Client wrapper around :mod:`clamd` supporting network and unix sockets."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        timeout: float,
        unix_socket: str | None,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._unix_socket = unix_socket

    def _connection(self):  # pragma: no cover - exercised via scan_stream
        try:
            import clamd
        except ImportError as exc:
            raise RuntimeError("clamd package is required for antivirus scanning") from exc

        if self._unix_socket:
            return clamd.ClamdUnixSocket(path=self._unix_socket, timeout=self._timeout)
        return clamd.ClamdNetworkSocket(
            host=self._host,
            port=self._port,
            timeout=self._timeout,
        )

    def scan_stream(self, stream: BinaryIO) -> ClamAVScanOutcome:
        connection = self._connection()
        try:
            if hasattr(stream, "seek"):
                stream.seek(0)  # type: ignore[arg-type]
        except Exception:  # pragma: no cover - defensive best effort
            pass

        try:
            result = connection.instream(stream)
        except Exception as exc:  # pragma: no cover - network failure
            raise ClamAVError("ClamAV scan failed") from exc

        if not isinstance(result, dict) or not result:
            raise ClamAVError("Unexpected ClamAV response")

        _, payload = next(iter(result.items()))
        status, signature = payload if isinstance(payload, tuple) else (payload, None)
        verdict = str(status).upper()
        signature_str = str(signature) if signature else None

        if verdict == "OK":
            return ClamAVScanOutcome(status=ClamAVVerdict.CLEAN, signature=None, raw=verdict)
        if verdict == "FOUND":
            return ClamAVScanOutcome(
                status=ClamAVVerdict.INFECTED,
                signature=signature_str,
                raw=verdict,
            )
        return ClamAVScanOutcome(
            status=ClamAVVerdict.ERROR,
            signature=signature_str,
            raw=verdict,
        )


class QuarantinePublisher(Protocol):
    """Abstraction for publishing scan requests to a quarantine queue."""

    def publish(self, message: ClamAVScanRequest) -> None:
        """Publish a scan request message."""


@dataclass(slots=True)
class MemoryQuarantinePublisher:
    """In-memory queue used for tests and local development."""

    _queue: SimpleQueue[ClamAVScanRequest] = field(default_factory=SimpleQueue)

    def publish(self, message: ClamAVScanRequest) -> None:
        self._queue.put(message)

    def drain(self) -> list[ClamAVScanRequest]:
        """Return all queued messages without blocking."""

        drained: list[ClamAVScanRequest] = []
        while True:
            try:
                drained.append(self._queue.get_nowait())
            except Empty:
                break
        return drained


@dataclass(slots=True)
class KombuQuarantinePublisher:
    """AMQP publisher backed by :mod:`kombu` for production deployments."""

    url: str
    queue_name: str

    def publish(self, message: ClamAVScanRequest) -> None:  # pragma: no cover - network I/O
        try:
            from kombu import Connection, Queue
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("kombu is required for AMQP quarantine publishing") from exc

        payload = message.model_dump()
        with Connection(self.url) as connection:
            queue = Queue(self.queue_name, durable=True)
            producer = connection.Producer(serializer="json")
            producer.publish(
                payload,
                exchange="",
                routing_key=self.queue_name,
                declare=[queue],
                retry=True,
                retry_policy={"interval_start": 1, "interval_max": 5, "interval_step": 1},
            )


_publisher: QuarantinePublisher | None = None
_clamav_client: ClamAVScanner | None = None


@asynccontextmanager
async def _session_from_factory(
    factory: Callable[[], AsyncSession],
) -> AsyncIterator[AsyncSession]:
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def reset_quarantine_publisher() -> None:
    """Reset cached quarantine publisher instance."""

    global _publisher
    _publisher = None


def reset_clamav_client() -> None:
    """Reset cached ClamAV client."""

    global _clamav_client
    _clamav_client = None


def get_quarantine_publisher() -> QuarantinePublisher:
    """Return a cached quarantine publisher based on current settings."""

    global _publisher
    if _publisher is not None:
        return _publisher

    settings = get_settings()
    queue_url = settings.clamav_queue_url.strip().lower()

    if queue_url.startswith("memory://"):
        _publisher = MemoryQuarantinePublisher()
    elif queue_url.startswith("amqp://") or queue_url.startswith("amqps://"):
        _publisher = KombuQuarantinePublisher(
            settings.clamav_queue_url,
            settings.clamav_scan_queue,
        )
    else:
        raise RuntimeError(
            "Unsupported CLAMAV_QUEUE_URL scheme; use memory:// for tests or amqp(s):// in production",
        )
    return _publisher


def get_clamav_client() -> ClamAVScanner:
    """Return a cached ClamAV client instance based on current settings."""

    global _clamav_client
    if _clamav_client is not None:
        return _clamav_client

    settings = get_settings()
    _clamav_client = ClamAVClient(
        host=settings.clamav_host,
        port=settings.clamav_port,
        timeout=settings.clamav_timeout,
        unix_socket=settings.clamav_unix_socket,
    )
    return _clamav_client


def enqueue_scan_request(message: ClamAVScanRequest) -> None:
    """Publish a ClamAV scan request, logging but not surfacing queue errors."""

    publisher = get_quarantine_publisher()
    try:
        publisher.publish(message)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception(
            "files.clamav.enqueue_failed",
            extra={
                "bucket": message.bucket,
                "key": message.key,
                "tenant_id": message.tenant_id,
            },
        )
        raise


async def process_scan_request(
    message: ClamAVScanRequest,
    *,
    scanner: ClamAVScanner | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> ClamAVScanOutcome:
    """Download an object, scan it with ClamAV, and persist the verdict."""

    client = scanner or get_clamav_client()
    log_context = {
        "tenant": message.tenant_slug,
        "tenant_id": message.tenant_id,
        "bucket": message.bucket,
        "key": message.key,
        "size": message.size,
        "mime": message.mime,
        "sha256": message.sha256,
    }

    try:
        with s3.stream_object(key=message.key) as stream:
            outcome = client.scan_stream(stream)
    except s3.S3OperationError as exc:
        logger.error(
            "files.clamav.download_failed",
            extra={**log_context, **exc.context()},
        )
        raise
    except ClamAVError as exc:
        logger.error(
            "files.clamav.scan_failed",
            extra=log_context,
            exc_info=exc,
        )
        outcome = ClamAVScanOutcome(
            status=ClamAVVerdict.ERROR,
            signature=None,
            raw=str(exc),
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error(
            "files.clamav.scan_exception",
            extra=log_context,
            exc_info=exc,
        )
        outcome = ClamAVScanOutcome(
            status=ClamAVVerdict.ERROR,
            signature=None,
            raw=str(exc),
        )

    scanned_at = datetime.now(timezone.utc)

    status_map = {
        ClamAVVerdict.CLEAN: FileScanStatus.CLEAN,
        ClamAVVerdict.INFECTED: FileScanStatus.INFECTED,
        ClamAVVerdict.ERROR: FileScanStatus.ERROR,
    }

    if session_factory is None:
        session_cm = session_scope(tenant=message.tenant_slug)
    else:
        session_cm = _session_from_factory(session_factory)

    async with session_cm as session:
        tenant_id = str(message.tenant_id)
        result = await session.execute(
            select(File).where(
                File.storage_key == message.key,
                File.tenant_id == tenant_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            logger.warning(
                "files.clamav.record_missing",
                extra=log_context,
            )
            return outcome

        record.scan_status = status_map[outcome.status]
        record.is_quarantined = record.scan_status != FileScanStatus.CLEAN
        record.clamav_signature = outcome.signature
        record.clamav_scanned_at = scanned_at
        await session.flush()

    log_payload = {**log_context, "status": outcome.status.value}
    if outcome.signature:
        log_payload["signature"] = outcome.signature

    if outcome.status is ClamAVVerdict.INFECTED:
        logger.warning("files.clamav.detected", extra=log_payload)
    elif outcome.status is ClamAVVerdict.ERROR:
        logger.error("files.clamav.error", extra=log_payload)
    else:
        logger.info("files.clamav.scanned", extra=log_payload)

    return outcome
