"""Runtime patches providing compatibility shims for the test suite."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from test_env_defaults import apply_test_env_defaults

# Set test environment variables BEFORE any imports
# This ensures app code reads correct configuration during test discovery
if "pytest" in sys.modules or (bool(sys.argv) and "pytest" in sys.argv[0]):
    apply_test_env_defaults()


def _ensure_workspace_symlinks() -> None:
    """Expose the repository layout under common ``/workspace*`` prefixes."""

    repo_root = Path(__file__).resolve().parent
    target_app = repo_root / "backend" / "app"
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

    backend_root = repo_root / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))


def _patch_spec_from_file_location() -> None:
    """Provide a graceful fallback when ``/workspace[s]/app`` is missing."""

    try:
        import importlib.util as importlib_util
    except Exception:  # pragma: no cover - extremely defensive
        return

    if getattr(importlib_util.spec_from_file_location, "__patched_for_workspace__", False):
        return

    repo_root = Path(__file__).resolve().parent
    app_root = repo_root / "backend" / "app"

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
