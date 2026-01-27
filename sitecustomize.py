"""Runtime patches providing compatibility shims for the test suite."""
from __future__ import annotations

import sys
import os
from pathlib import Path
from types import ModuleType

# Set test environment variables BEFORE any imports
# This ensures app code reads correct configuration during test discovery
if "pytest" in sys.modules or "pytest" in sys.argv[0] if sys.argv else False:
    os.environ.setdefault("APP_NAME", "TestService")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
    os.environ.setdefault("REDIS_RESULT_URL", "redis://localhost:6379/15")
    os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
    os.environ.setdefault("S3_BUCKET", "test-bucket")
    os.environ.setdefault("S3_ACCESS_KEY", "test")
    os.environ.setdefault("S3_SECRET_KEY", "test")
    os.environ.setdefault("DEFAULT_LOCALE", "en-US")
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("LIBREOFFICE_BIN", sys.executable)


def _ensure_workspace_symlinks() -> None:
    """Expose the repository layout under common ``/workspace*`` prefixes."""

    repo_root = Path(__file__).resolve().parent
    target_app = repo_root / "app"
    if not target_app.exists():  # pragma: no cover - defensive safeguard
        return

    workspace_root = repo_root.parent
    candidate_roots: set[Path] = {workspace_root}

    if workspace_root.name and not workspace_root.name.endswith("s"):
        alt_root = workspace_root.parent / f"{workspace_root.name}s"
        candidate_roots.add(alt_root)

    for root in candidate_roots:
        if not root.exists():
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError:  # pragma: no cover - permissions edge cases
                continue

        link_path = root / "app"

        try:
            if link_path.exists():
                try:
                    if link_path.is_symlink() and link_path.resolve() == target_app:
                        continue
                    if link_path.is_dir() and link_path.samefile(target_app):  # pragma: no cover
                        continue
                except OSError:  # pragma: no cover - permissions edge cases
                    continue

                try:
                    if link_path.is_symlink():
                        link_path.unlink()
                    else:  # pragma: no cover - avoid clobbering unexpected directories
                        continue
                except OSError:  # pragma: no cover
                    continue

            link_path.symlink_to(target_app, target_is_directory=True)
        except OSError:  # pragma: no cover - permissions edge cases
            continue

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def _patch_spec_from_file_location() -> None:
    """Provide a graceful fallback when ``/workspace[s]/app`` is missing."""

    try:
        import importlib.util as importlib_util
    except Exception:  # pragma: no cover - extremely defensive
        return

    if getattr(importlib_util.spec_from_file_location, "__patched_for_workspace__", False):
        return

    repo_root = Path(__file__).resolve().parent
    app_root = repo_root / "app"

    if not app_root.exists():
        return

    workspace_root = repo_root.parent
    candidate_roots: list[Path] = [workspace_root]
    if workspace_root.name and not workspace_root.name.endswith("s"):
        candidate_roots.append(workspace_root.parent / f"{workspace_root.name}s")

    prefix_strings = []
    for root in candidate_roots:
        prefix_strings.append(root.joinpath("app").as_posix())

    original = importlib_util.spec_from_file_location

    def _resolve_location(location: object) -> object:
        if isinstance(location, (str, os.PathLike)):
            candidate = Path(location)
        elif isinstance(location, bytes):
            try:
                candidate = Path(location.decode())
            except Exception:  # pragma: no cover - ignore undecodable bytes paths
                return location
        else:
            return location

        if candidate.exists():
            return location

        candidate_posix = candidate.as_posix()

        for prefix in prefix_strings:
            if candidate_posix == prefix or candidate_posix.startswith(prefix + "/"):
                relative = candidate_posix[len(prefix) :].lstrip("/")
                resolved = app_root.joinpath(relative)
                if resolved.exists():
                    return resolved
        return location

    def patched(name, location, *args, **kwargs):  # type: ignore[no-redef]
        return original(name, _resolve_location(location), *args, **kwargs)

    patched.__patched_for_workspace__ = True  # type: ignore[attr-defined]
    importlib_util.spec_from_file_location = patched  # type: ignore[assignment]


_ensure_workspace_symlinks()
_patch_spec_from_file_location()

try:  # pragma: no cover - defensive import
    import schemathesis  # noqa: F401
except Exception:  # pragma: no cover
    schemathesis = None  # type: ignore[assignment]

if schemathesis is not None:
    try:
        from schemathesis.core import NOT_SET as _not_set  # type: ignore[attr-defined]
    except ModuleNotFoundError:
        try:
            from schemathesis.constants import NOT_SET as _not_set  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            class _Sentinel:
                pass

            _not_set = _Sentinel()  # type: ignore[assignment]

        core_module = ModuleType("schemathesis.core")
        core_module.NOT_SET = _not_set  # type: ignore[attr-defined]

        try:
            from schemathesis.exceptions import SchemaError as _BaseLoaderError
        except Exception:  # pragma: no cover
            _BaseLoaderError = Exception

        errors_module = ModuleType("schemathesis.core.errors")
        errors_module.LoaderError = _BaseLoaderError  # type: ignore[attr-defined]

        core_module.errors = errors_module  # type: ignore[attr-defined]

        sys.modules.setdefault("schemathesis.core", core_module)
        sys.modules.setdefault("schemathesis.core.errors", errors_module)
    else:  # pragma: no cover - when module already available
        try:
            import schemathesis.core.errors as errors_module  # type: ignore[attr-defined]
        except ModuleNotFoundError:
            try:
                from schemathesis.exceptions import SchemaError as _BaseLoaderError
            except Exception:  # pragma: no cover
                _BaseLoaderError = Exception

            errors_module = ModuleType("schemathesis.core.errors")
            errors_module.LoaderError = _BaseLoaderError  # type: ignore[attr-defined]
        sys.modules.setdefault("schemathesis.core.errors", errors_module)
        setattr(sys.modules["schemathesis.core"], "errors", errors_module)  # type: ignore[index]


try:  # pragma: no cover - optional dependency
    from httpx import AsyncClient
except Exception:  # pragma: no cover - ensure tests still run without httpx
    AsyncClient = None  # type: ignore[assignment]


def _patch_httpx_allow_redirects() -> None:
    if AsyncClient is None:
        return

    original_get = AsyncClient.get

    async def patched_get(self, url, *args, allow_redirects: bool | None = None, **kwargs):
        if allow_redirects is not None and "follow_redirects" not in kwargs:
            kwargs["follow_redirects"] = allow_redirects
        return await original_get(self, url, *args, **kwargs)

    AsyncClient.get = patched_get  # type: ignore[assignment]


_patch_httpx_allow_redirects()
