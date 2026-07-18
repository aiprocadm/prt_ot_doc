"""File storage abstractions used by the API layer."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

__all__ = ["FileStorageError", "FileStorageService", "StoredObject"]


class FileStorageError(RuntimeError):
    """Raised when the storage backend cannot persist an object."""


@dataclass(frozen=True)
class StoredObject:
    """Description of an object stored by :class:`FileStorageService`."""

    key: str
    size: int
    content_type: str | None


class FileStorageService:
    """Simple file-system backed storage implementation.

    The service writes binary streams directly to disk to avoid loading the
    entire payload into memory. Keys are always treated as POSIX style paths
    relative to the configured storage root. Directory traversal attempts are
    rejected to prevent overwriting arbitrary files on the host.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def upload(
        self,
        *,
        key: str,
        data: BinaryIO,
        content_type: str | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> StoredObject:
        """Persist an object stream under the given key.

        Parameters
        ----------
        key:
            Relative object key to store the stream under.
        data:
            A binary stream supporting ``read`` and optionally ``seek``.
        content_type:
            Optional MIME type associated with the stream.
        chunk_size:
            Number of bytes to read from the stream per iteration.
        """

        normalized_key = self._normalize_key(key)
        destination = self._root / normalized_key
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Create a deterministic backup of the existing object, if any, before
        # overwriting it. The timestamp makes the backup key predictable and
        # simplifies clean-up policies.
        if destination.exists():
            timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup_path = destination.with_suffix(destination.suffix + f".bak.{timestamp}")
            try:
                shutil.copy2(destination, backup_path)
            except OSError as exc:  # pragma: no cover - defensive branch
                raise FileStorageError(f"Failed to create backup for {normalized_key}") from exc

        try:
            if hasattr(data, "seek"):
                data.seek(0)
        except OSError as exc:  # pragma: no cover - defensive branch
            raise FileStorageError("Unable to seek within provided stream") from exc

        temporary_path = destination.with_name(f".{destination.name}.tmp-{uuid4().hex}")

        size = 0
        try:
            with temporary_path.open("wb") as buffer:
                while True:
                    chunk = data.read(chunk_size)
                    if not chunk:
                        break
                    buffer.write(chunk)
                    size += len(chunk)
                buffer.flush()
                os.fsync(buffer.fileno())
            # Ensure contents are flushed to disk before rename.
            os.replace(temporary_path, destination)
        except OSError as exc:
            try:
                if temporary_path.exists():
                    temporary_path.unlink()
            finally:
                raise FileStorageError(f"Failed to persist object {normalized_key}") from exc

        return StoredObject(key=normalized_key.as_posix(), size=size, content_type=content_type)

    def _normalize_key(self, key: str) -> Path:
        candidate = Path(key)
        if candidate.is_absolute():
            raise FileStorageError("Object key must be relative")
        if ".." in candidate.parts:
            raise FileStorageError("Object key cannot contain parent directory references")
        # Normalise to POSIX style even on Windows hosts.
        normalized = Path(*candidate.parts)
        if not normalized.name:
            raise FileStorageError("Object key must include a filename")
        return normalized

    def resolve_path(self, key: str) -> Path:
        """Resolve a storage key to an absolute path under the root."""

        normalized = self._normalize_key(key)
        return self._root / normalized

    def read(self, key: str) -> bytes:
        """Read object bytes from storage."""

        path = self.resolve_path(key)
        try:
            return path.read_bytes()
        except OSError as exc:  # pragma: no cover - defensive branch
            raise FileStorageError(f"Unable to read object {key}") from exc

    def open(self, key: str) -> BinaryIO:
        """Open a read-only stream for the object key."""

        path = self.resolve_path(key)
        try:
            return path.open("rb")
        except OSError as exc:  # pragma: no cover - defensive branch
            raise FileStorageError(f"Unable to open object {key}") from exc

    def ensure_ready(self) -> None:
        """Create the storage root if it does not yet exist."""

        try:
            os.makedirs(self._root, exist_ok=True)
        except OSError as exc:  # pragma: no cover - defensive branch
            raise FileStorageError(f"Unable to prepare storage root {self._root}") from exc

    def delete(self, key: str) -> None:
        """Remove an object from storage if it exists."""

        path = self._root / self._normalize_key(key)
        try:
            path.unlink(missing_ok=True)
        except TypeError:  # pragma: no cover - Python <3.8 guard (not expected)
            if path.exists():
                path.unlink()
        except OSError as exc:  # pragma: no cover - defensive branch
            raise FileStorageError(f"Unable to delete object {key}") from exc
