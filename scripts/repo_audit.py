from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CanonicalPath:
    label: str
    path: str
    description: str


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def existing(paths: list[CanonicalPath]) -> list[CanonicalPath]:
    return [item for item in paths if (REPO_ROOT / item.path).exists()]


def find_files(*patterns: str) -> list[str]:
    matches: set[str] = set()
    for pattern in patterns:
        for path in REPO_ROOT.glob(pattern):
            if any(part in {"node_modules", ".git", ".venv", "dist", "__pycache__"} for part in path.parts):
                continue
            if path.is_file():
                matches.add(rel(path))
    return sorted(matches)


def main() -> None:
    backend_paths = existing(
        [
            CanonicalPath("ASGI entrypoint", "backend/app/main.py", "Uvicorn/FastAPI runtime entrypoint."),
            CanonicalPath("App factory", "backend/app/api/app.py", "Application factory and middleware wiring."),
            CanonicalPath("API router", "backend/app/api/v1/router.py", "Top-level v1 router composition."),
            CanonicalPath("CLI entrypoint", "backend/app/cli/main.py", "Operator CLI commands."),
            CanonicalPath("Worker entrypoint", "backend/app/worker.py", "Celery worker bootstrap."),
            CanonicalPath("Alembic config", "backend/app/migrations/alembic.ini", "Database migration configuration."),
        ]
    )
    frontend_paths = existing(
        [
            CanonicalPath("Package manifest", "frontend/package.json", "Single active frontend package manifest."),
            CanonicalPath("Vite config", "frontend/vite.config.ts", "Frontend bundler/runtime config."),
            CanonicalPath("TypeScript config", "frontend/tsconfig.json", "Application TypeScript project config."),
            CanonicalPath("Node TS config", "frontend/tsconfig.node.json", "Node-side TS config for build tooling."),
            CanonicalPath("React entrypoint", "frontend/src/main.tsx", "Browser bootstrap for the SPA."),
            CanonicalPath("Route tree", "frontend/src/router/AppRouter.tsx", "Canonical route composition."),
        ]
    )
    docs_paths = existing(
        [
            CanonicalPath("Architecture", "docs/ARCHITECTURE.md", "Architecture overview and layering expectations."),
            CanonicalPath("Project structure", "docs/PROJECT_STRUCTURE.md", "Canonical repository layout."),
            CanonicalPath("Setup", "docs/SETUP.md", "Reproducible local setup and startup."),
            CanonicalPath("Backend", "docs/BACKEND.md", "Backend runtime/modules overview."),
            CanonicalPath("Frontend", "docs/FRONTEND.md", "Frontend structure/routes/data layer overview."),
            CanonicalPath("Modules", "docs/MODULES.md", "Domain/module inventory."),
            CanonicalPath("API overview", "docs/API_OVERVIEW.md", "Public/internal API map."),
            CanonicalPath("Domain model", "docs/DOMAIN_MODEL.md", "Key entities and relationships."),
            CanonicalPath("Document core", "docs/DOCUMENT_CORE.md", "Generation/template/branding flow."),
            CanonicalPath("Integrations", "docs/INTEGRATIONS.md", "Webhooks/API/provider integration notes."),
            CanonicalPath("Security", "docs/SECURITY.md", "Security, tenancy, authz guidance."),
            CanonicalPath("Testing", "docs/testing.md", "Test strategy and command matrix."),
            CanonicalPath("Coverage matrix", "docs/audit/TZ_COVERAGE_MATRIX.md", "TZ-to-code/test coverage mapping."),
            CanonicalPath("Acceptance matrix", "ACCEPTANCE_TEST_MATRIX.md", "Acceptance scenarios to checks mapping."),
            CanonicalPath("Gap report", "GAP_REPORT.md", "Open/closed implementation gaps."),
            CanonicalPath("Release readiness", "RELEASE_READINESS.md", "Go-live readiness summary."),
            CanonicalPath("Known limitations", "KNOWN_LIMITATIONS.md", "Residual limitations and follow-up notes."),
            CanonicalPath("Path renames", "CHANGED_PATHS_AND_RENAMES.md", "Documented structural changes/deprecations."),
            CanonicalPath("Workflows and events", "docs/WORKFLOWS_AND_EVENTS.md", "Cross-module workflow/event map."),
            CanonicalPath("Observability", "docs/OBSERVABILITY.md", "Health/readiness/metrics/logging/tracing foundation."),
        ]
    )
    package_jsons = find_files("**/package.json")
    vite_configs = find_files("**/vite.config.*")
    tsconfigs = find_files("**/tsconfig*.json")
    backend_entrypoints = find_files("backend/app/main.py", "backend/app/api/app.py", "backend/app/worker.py", "backend/app/cli/main.py")
    duplicate_pairs = [
        ("docs/ADR", "docs/adr", "Prefer `docs/ADR` for new ADRs and keep `docs/adr` as historical legacy content."),
        (
            "backend/app/modules/approval",
            "backend/app/modules/approvals",
            "Prefer `backend/app/modules/approvals` for active approval APIs; keep singular path as compatibility legacy only.",
        ),
    ]

    lines = [
        "# Repository audit snapshot",
        "",
        "This file is generated by `python scripts/repo_audit.py` and captures the canonical active roots, configs, and known legacy paths.",
        "",
        "## Canonical roots",
        "- Backend root: `backend/`.",
        "- Frontend root: `frontend/`.",
        "- Repository docs root: `docs/` plus root release/audit reports.",
        "- Tests roots: `tests/`, `integration_tests/`, and `frontend/src/__tests__/`.",
        "",
        "## Active backend entrypoints and configs",
    ]
    lines.extend(
        f"- **{item.label}:** `{item.path}` — {item.description}" for item in backend_paths
    )
    lines.extend([
        "",
        "## Active frontend entrypoints and configs",
    ])
    lines.extend(
        f"- **{item.label}:** `{item.path}` — {item.description}" for item in frontend_paths
    )
    lines.extend([
        "",
        "## Required docs present in the canonical documentation set",
    ])
    lines.extend(
        f"- **{item.label}:** `{item.path}` — {item.description}" for item in docs_paths
    )
    lines.extend([
        "",
        "## Manifest and config inventory",
        "- Frontend package manifests:",
    ])
    lines.extend(f"  - `{path}`" for path in package_jsons)
    lines.append("- Frontend Vite configs:")
    lines.extend(f"  - `{path}`" for path in vite_configs)
    lines.append("- TypeScript configs:")
    lines.extend(f"  - `{path}`" for path in tsconfigs)
    lines.append("- Backend runtime entrypoints:")
    lines.extend(f"  - `{path}`" for path in backend_entrypoints)
    lines.extend([
        "",
        "## Structural findings",
        f"- Active frontend manifest count: **{len(package_jsons)}**.",
        f"- Backend runtime entrypoint present: **{'yes' if (REPO_ROOT / 'backend/app/main.py').exists() else 'no'}**.",
        f"- Frontend root contains Vite config: **{'yes' if (REPO_ROOT / 'frontend/vite.config.ts').exists() else 'no'}**.",
        f"- Frontend root contains tsconfig: **{'yes' if (REPO_ROOT / 'frontend/tsconfig.json').exists() else 'no'}**.",
        f"- Repo-root compatibility package `app/`: **{'yes' if (REPO_ROOT / 'app/__init__.py').exists() else 'no'}**.",
        "",
        "## Legacy / compatibility paths to keep out of new code",
    ])
    for left, right, guidance in duplicate_pairs:
        left_exists = (REPO_ROOT / left).exists()
        right_exists = (REPO_ROOT / right).exists()
        lines.append(f"- `{left}` exists={left_exists}; `{right}` exists={right_exists}. {guidance}")

    output = REPO_ROOT / "docs/audit/REPOSITORY_AUDIT.md"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
