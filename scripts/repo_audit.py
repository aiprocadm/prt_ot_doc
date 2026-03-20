from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_OUTPUT = REPO_ROOT / "docs/audit/REPOSITORY_AUDIT.md"
JSON_OUTPUT = REPO_ROOT / "docs/audit/REPOSITORY_AUDIT.json"

EXCLUDED_PARTS = {"node_modules", ".git", ".venv", "dist", "__pycache__", ".pytest_cache"}


@dataclass(frozen=True)
class CanonicalPath:
    label: str
    path: str
    description: str


@dataclass(frozen=True)
class LegacyPathPair:
    canonical: str
    legacy: str
    guidance: str


REQUIRED_DOCS: tuple[CanonicalPath, ...] = (
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
    CanonicalPath("Observability", "docs/OBSERVABILITY.md", "Health/readiness/metrics/logging/tracing foundation."),
    CanonicalPath("Testing", "docs/TESTING.md", "Test strategy and command matrix."),
    CanonicalPath("Coverage matrix", "docs/audit/TZ_COVERAGE_MATRIX.md", "TZ-to-code/test coverage mapping."),
    CanonicalPath("Acceptance matrix", "ACCEPTANCE_TEST_MATRIX.md", "Acceptance scenarios to checks mapping."),
    CanonicalPath("Gap report", "GAP_REPORT.md", "Open/closed implementation gaps."),
    CanonicalPath("Release readiness", "RELEASE_READINESS.md", "Go-live readiness summary."),
    CanonicalPath("Known limitations", "KNOWN_LIMITATIONS.md", "Residual limitations and follow-up notes."),
    CanonicalPath("Path renames", "CHANGED_PATHS_AND_RENAMES.md", "Documented structural changes/deprecations."),
    CanonicalPath("Workflows and events", "docs/WORKFLOWS_AND_EVENTS.md", "Cross-module workflow/event map."),
)

LEGACY_PATHS: tuple[LegacyPathPair, ...] = (
    LegacyPathPair(
        canonical="docs/TESTING.md",
        legacy="docs/testing.md",
        guidance="Prefer the uppercase testing guide; keep the lowercase path as a compatibility pointer only.",
    ),
    LegacyPathPair(
        canonical="docs/ADR",
        legacy="docs/adr",
        guidance="Prefer `docs/ADR` for new ADRs and treat `docs/adr` as historical legacy content.",
    ),
    LegacyPathPair(
        canonical="backend/app/modules/approvals",
        legacy="backend/app/modules/approval",
        guidance="Prefer the plural approvals module for new orchestration work and keep the singular path only for compatibility imports.",
    ),
    LegacyPathPair(
        canonical="docs/PROJECT_STRUCTURE.md",
        legacy="docs/repo-structure.md",
        guidance="Prefer the canonical project structure doc and keep the lowercase file only as legacy documentation.",
    ),
)


CANONICAL_ROOTS = {
    "backend_root": "backend",
    "frontend_root": "frontend",
    "docs_root": "docs",
    "tests_roots": ["tests", "integration_tests", "frontend/src/__tests__"],
}


BACKEND_PATHS = (
    CanonicalPath("ASGI entrypoint", "backend/app/main.py", "Uvicorn/FastAPI runtime entrypoint."),
    CanonicalPath("App factory", "backend/app/api/app.py", "Application factory and middleware wiring."),
    CanonicalPath("API router", "backend/app/api/v1/router.py", "Top-level v1 router composition."),
    CanonicalPath("CLI entrypoint", "backend/app/cli/main.py", "Operator CLI commands."),
    CanonicalPath("Worker entrypoint", "backend/app/worker.py", "Celery worker bootstrap."),
    CanonicalPath("Alembic config", "backend/app/migrations/alembic.ini", "Database migration configuration."),
)

FRONTEND_PATHS = (
    CanonicalPath("Package manifest", "frontend/package.json", "Single active frontend package manifest."),
    CanonicalPath("Vite config", "frontend/vite.config.ts", "Frontend bundler/runtime config."),
    CanonicalPath("TypeScript config", "frontend/tsconfig.json", "Application TypeScript project config."),
    CanonicalPath("Node TS config", "frontend/tsconfig.node.json", "Node-side TS config for build tooling."),
    CanonicalPath("React entrypoint", "frontend/src/main.tsx", "Browser bootstrap for the SPA."),
    CanonicalPath("Route tree", "frontend/src/router/AppRouter.tsx", "Canonical route composition."),
)


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)


def existing(paths: tuple[CanonicalPath, ...]) -> list[CanonicalPath]:
    return [item for item in paths if (REPO_ROOT / item.path).exists()]


def find_files(*patterns: str) -> list[str]:
    matches: set[str] = set()
    for pattern in patterns:
        for path in REPO_ROOT.glob(pattern):
            if _is_excluded(path):
                continue
            if path.is_file():
                matches.add(rel(path))
    return sorted(matches)


def inventory_roots() -> dict[str, list[str]]:
    return {
        "repo_level_directories": sorted(
            rel(path)
            for path in REPO_ROOT.iterdir()
            if path.is_dir() and not _is_excluded(path)
        )
    }


def audit_legacy_paths() -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for pair in LEGACY_PATHS:
        canonical_exists = (REPO_ROOT / pair.canonical).exists()
        legacy_exists = (REPO_ROOT / pair.legacy).exists()
        results.append(
            {
                "canonical": pair.canonical,
                "legacy": pair.legacy,
                "canonical_exists": canonical_exists,
                "legacy_exists": legacy_exists,
                "guidance": pair.guidance,
            }
        )
    return results


def build_payload() -> dict[str, object]:
    package_jsons = find_files("**/package.json")
    vite_configs = find_files("**/vite.config.*")
    tsconfigs = find_files("**/tsconfig*.json")
    backend_entrypoints = find_files(
        "backend/app/main.py",
        "backend/app/api/app.py",
        "backend/app/worker.py",
        "backend/app/cli/main.py",
    )
    required_docs = existing(REQUIRED_DOCS)
    legacy_paths = audit_legacy_paths()

    return {
        "canonical_roots": CANONICAL_ROOTS,
        "backend_paths": [asdict(item) for item in existing(BACKEND_PATHS)],
        "frontend_paths": [asdict(item) for item in existing(FRONTEND_PATHS)],
        "required_docs": [asdict(item) for item in required_docs],
        "inventory": {
            "package_jsons": package_jsons,
            "vite_configs": vite_configs,
            "tsconfigs": tsconfigs,
            "backend_entrypoints": backend_entrypoints,
            **inventory_roots(),
        },
        "findings": {
            "active_frontend_manifest_count": len(package_jsons),
            "backend_runtime_entrypoint_present": (REPO_ROOT / "backend/app/main.py").exists(),
            "frontend_vite_config_present": (REPO_ROOT / "frontend/vite.config.ts").exists(),
            "frontend_tsconfig_present": (REPO_ROOT / "frontend/tsconfig.json").exists(),
            "app_compat_shim_present": (REPO_ROOT / "app/__init__.py").exists(),
            "required_docs_present": len(required_docs),
            "required_docs_expected": len(REQUIRED_DOCS),
        },
        "legacy_paths": legacy_paths,
        "generated_from": rel(Path(__file__)),
        "consistency_watchlist": [
            "Keep README.md and docs/README.md aligned when startup commands or canonical paths change.",
            "Keep legacy compatibility paths out of new imports, routes, and docs references.",
        ],
    }


def render_markdown(payload: dict[str, object]) -> str:
    inventory = payload["inventory"]
    findings = payload["findings"]
    lines = [
        "# Repository audit snapshot",
        "",
        "This file is generated by `python scripts/repo_audit.py` and captures the canonical active roots, configs, required docs, and legacy compatibility paths.",
        "",
        "## Canonical roots",
        f"- Backend root: `{payload['canonical_roots']['backend_root']}`.",
        f"- Frontend root: `{payload['canonical_roots']['frontend_root']}`.",
        f"- Repository docs root: `{payload['canonical_roots']['docs_root']}` plus root release/audit reports.",
        "- Tests roots: " + ", ".join(f"`{item}`" for item in payload["canonical_roots"]["tests_roots"]) + ".",
        "",
        "## Active backend entrypoints and configs",
    ]
    lines.extend(
        f"- **{item['label']}:** `{item['path']}` — {item['description']}" for item in payload["backend_paths"]
    )
    lines.extend(["", "## Active frontend entrypoints and configs"])
    lines.extend(
        f"- **{item['label']}:** `{item['path']}` — {item['description']}" for item in payload["frontend_paths"]
    )
    lines.extend(["", "## Required docs present in the canonical documentation set"])
    lines.extend(
        f"- **{item['label']}:** `{item['path']}` — {item['description']}" for item in payload["required_docs"]
    )
    lines.extend([
        "",
        "## Manifest and config inventory",
        "- Frontend package manifests:",
    ])
    lines.extend(f"  - `{path}`" for path in inventory["package_jsons"])
    lines.append("- Frontend Vite configs:")
    lines.extend(f"  - `{path}`" for path in inventory["vite_configs"])
    lines.append("- TypeScript configs:")
    lines.extend(f"  - `{path}`" for path in inventory["tsconfigs"])
    lines.append("- Backend runtime entrypoints:")
    lines.extend(f"  - `{path}`" for path in inventory["backend_entrypoints"])
    lines.append("- Repo-level directories:")
    lines.extend(f"  - `{path}`" for path in inventory["repo_level_directories"])
    lines.extend([
        "",
        "## Structural findings",
        f"- Active frontend manifest count: **{findings['active_frontend_manifest_count']}**.",
        f"- Backend runtime entrypoint present: **{'yes' if findings['backend_runtime_entrypoint_present'] else 'no'}**.",
        f"- Frontend root contains Vite config: **{'yes' if findings['frontend_vite_config_present'] else 'no'}**.",
        f"- Frontend root contains tsconfig: **{'yes' if findings['frontend_tsconfig_present'] else 'no'}**.",
        f"- Repo-root compatibility package `app/`: **{'yes' if findings['app_compat_shim_present'] else 'no'}**.",
        f"- Required docs present: **{findings['required_docs_present']}/{findings['required_docs_expected']}**.",
        "",
        "## Legacy / compatibility paths to keep out of new code",
    ])
    for item in payload["legacy_paths"]:
        lines.append(
            f"- canonical `{item['canonical']}` exists={item['canonical_exists']}; legacy `{item['legacy']}` exists={item['legacy_exists']}. {item['guidance']}"
        )
    lines.extend([
        "",
        "## Consistency watchlist",
    ])
    lines.extend(f"- {item}" for item in payload["consistency_watchlist"])
    lines.extend([
        "",
        "## Machine-readable snapshot",
        f"- JSON export: `{rel(JSON_OUTPUT)}`.",
    ])
    return "\n".join(lines) + "\n"


def write_outputs(payload: dict[str, object]) -> None:
    MARKDOWN_OUTPUT.write_text(render_markdown(payload), encoding="utf-8")
    JSON_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    payload = build_payload()
    write_outputs(payload)
    print(MARKDOWN_OUTPUT.relative_to(REPO_ROOT))
    print(JSON_OUTPUT.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
