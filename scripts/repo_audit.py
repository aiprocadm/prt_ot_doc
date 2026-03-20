from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_OUTPUT = REPO_ROOT / "docs/audit/REPOSITORY_AUDIT.md"
JSON_OUTPUT = REPO_ROOT / "docs/audit/REPOSITORY_AUDIT.json"

EXCLUDED_PARTS = {"node_modules", ".git", ".venv", "dist", "__pycache__"}


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


@dataclass(frozen=True)
class ExistenceCheck:
    label: str
    path: str
    exists: bool
    description: str


CANONICAL_BACKEND_PATHS = [
    CanonicalPath("ASGI entrypoint", "backend/app/main.py", "Uvicorn/FastAPI runtime entrypoint."),
    CanonicalPath("App factory", "backend/app/api/app.py", "Application factory and middleware wiring."),
    CanonicalPath("API router", "backend/app/api/v1/router.py", "Top-level v1 router composition."),
    CanonicalPath("CLI entrypoint", "backend/app/cli/main.py", "Operator CLI commands."),
    CanonicalPath("Worker entrypoint", "backend/app/worker.py", "Celery worker bootstrap."),
    CanonicalPath("Alembic config", "backend/app/migrations/alembic.ini", "Database migration configuration."),
]

CANONICAL_FRONTEND_PATHS = [
    CanonicalPath("Package manifest", "frontend/package.json", "Single active frontend package manifest."),
    CanonicalPath("Vite config", "frontend/vite.config.ts", "Frontend bundler/runtime config."),
    CanonicalPath("TypeScript config", "frontend/tsconfig.json", "Application TypeScript project config."),
    CanonicalPath("Node TS config", "frontend/tsconfig.node.json", "Node-side TS config for build tooling."),
    CanonicalPath("React entrypoint", "frontend/src/main.tsx", "Browser bootstrap for the SPA."),
    CanonicalPath("Route tree", "frontend/src/router/AppRouter.tsx", "Canonical route composition."),
]

REQUIRED_DOCS = [
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
    CanonicalPath("Testing", "docs/TESTING.md", "Test strategy and command matrix."),
    CanonicalPath("Coverage matrix", "docs/audit/TZ_COVERAGE_MATRIX.md", "TZ-to-code/test coverage mapping."),
    CanonicalPath("Acceptance matrix", "ACCEPTANCE_TEST_MATRIX.md", "Acceptance scenarios to checks mapping."),
    CanonicalPath("Gap report", "GAP_REPORT.md", "Open/closed implementation gaps."),
    CanonicalPath("Release readiness", "RELEASE_READINESS.md", "Go-live readiness summary."),
    CanonicalPath("Known limitations", "KNOWN_LIMITATIONS.md", "Residual limitations and follow-up notes."),
    CanonicalPath("Path renames", "CHANGED_PATHS_AND_RENAMES.md", "Documented structural changes/deprecations."),
    CanonicalPath("Workflows and events", "docs/WORKFLOWS_AND_EVENTS.md", "Cross-module workflow/event map."),
    CanonicalPath("Observability", "docs/OBSERVABILITY.md", "Health/readiness/metrics/logging/tracing foundation."),
]

LEGACY_PATH_PAIRS = [
    LegacyPathPair(
        canonical="docs/TESTING.md",
        legacy="docs/testing.md",
        guidance="Prefer `docs/TESTING.md` for new references and keep lowercase `docs/testing.md` as a compatibility pointer.",
    ),
    LegacyPathPair(
        canonical="docs/ADR",
        legacy="docs/adr",
        guidance="Prefer `docs/ADR` for new ADRs and keep `docs/adr` as historical legacy content.",
    ),
    LegacyPathPair(
        canonical="backend/app/modules/approvals",
        legacy="backend/app/modules/approval",
        guidance="Prefer `backend/app/modules/approvals` for active approval APIs; keep singular path as compatibility legacy only.",
    ),
]

ROOT_EXPECTATIONS = [
    ExistenceCheck("Backend root", "backend", True, "Canonical backend source root."),
    ExistenceCheck("Frontend root", "frontend", True, "Canonical frontend source root."),
    ExistenceCheck("Docs root", "docs", True, "Repository documentation root."),
    ExistenceCheck("Root package.json", "package.json", False, "A repo-root frontend manifest should not exist."),
    ExistenceCheck("Frontend package.json", "frontend/package.json", True, "The active frontend package manifest must exist here."),
    ExistenceCheck("Compatibility shim", "app/__init__.py", True, "Legacy `app.*` imports are intentionally supported through this shim."),
]


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def include_path(path: Path) -> bool:
    return path.is_file() and not any(part in EXCLUDED_PARTS for part in path.parts)


def find_files(*patterns: str) -> list[str]:
    matches: set[str] = set()
    for pattern in patterns:
        for path in REPO_ROOT.glob(pattern):
            if include_path(path):
                matches.add(rel(path))
    return sorted(matches)


def existing(paths: list[CanonicalPath]) -> list[CanonicalPath]:
    return [item for item in paths if (REPO_ROOT / item.path).exists()]


def build_inventory() -> dict[str, list[str]]:
    return {
        "package_jsons": find_files("**/package.json"),
        "vite_configs": find_files("**/vite.config.*"),
        "tsconfigs": find_files("**/tsconfig*.json"),
        "eslint_configs": find_files("**/.eslintrc.*", "**/eslint.config.*"),
        "backend_entrypoints": find_files(
            "backend/app/main.py",
            "backend/app/api/app.py",
            "backend/app/worker.py",
            "backend/app/cli/main.py",
        ),
        "frontend_entrypoints": find_files("frontend/src/main.tsx", "frontend/src/router/AppRouter.tsx"),
    }


def build_findings(inventory: dict[str, list[str]]) -> list[str]:
    findings = [
        f"Active frontend manifest count: **{len(inventory['package_jsons'])}**.",
        f"Backend runtime entrypoint present: **{'yes' if (REPO_ROOT / 'backend/app/main.py').exists() else 'no'}**.",
        f"Frontend root contains Vite config: **{'yes' if (REPO_ROOT / 'frontend/vite.config.ts').exists() else 'no'}**.",
        f"Frontend root contains tsconfig: **{'yes' if (REPO_ROOT / 'frontend/tsconfig.json').exists() else 'no'}**.",
        f"Repo-root compatibility package `app/`: **{'yes' if (REPO_ROOT / 'app/__init__.py').exists() else 'no'}**.",
    ]
    if len(inventory["package_jsons"]) != 1:
        findings.append("Frontend manifest inventory is not canonical; resolve multiple `package.json` roots before adding more UI work.")
    if any(path != "frontend/package.json" for path in inventory["package_jsons"]):
        findings.append("At least one `package.json` exists outside `frontend/`; verify it is intentionally inactive or remove it.")
    return findings


def build_root_expectations() -> list[dict[str, object]]:
    results = []
    for item in ROOT_EXPECTATIONS:
        exists = (REPO_ROOT / item.path).exists()
        results.append(
            {
                "label": item.label,
                "path": item.path,
                "expected": item.exists,
                "actual": exists,
                "status": "ok" if exists == item.exists else "mismatch",
                "description": item.description,
            }
        )
    return results


def build_legacy_pairs() -> list[dict[str, object]]:
    pairs: list[dict[str, object]] = []
    for item in LEGACY_PATH_PAIRS:
        pairs.append(
            {
                "canonical": item.canonical,
                "canonical_exists": (REPO_ROOT / item.canonical).exists(),
                "legacy": item.legacy,
                "legacy_exists": (REPO_ROOT / item.legacy).exists(),
                "guidance": item.guidance,
            }
        )
    return pairs


def render_markdown(payload: dict[str, object]) -> str:
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
        f"- **{item['label']}:** `{item['path']}` — {item['description']}" for item in payload["backend_paths"]
    )
    lines.extend(["", "## Active frontend entrypoints and configs"])
    lines.extend(
        f"- **{item['label']}:** `{item['path']}` — {item['description']}" for item in payload["frontend_paths"]
    )
    lines.extend(["", "## Required docs present in the canonical documentation set"])
    lines.extend(
        f"- **{item['label']}:** `{item['path']}` — {item['description']}" for item in payload["docs_paths"]
    )
    lines.extend(["", "## Root expectations"])
    for item in payload["root_expectations"]:
        lines.append(
            f"- **{item['label']}:** `{item['path']}` expected={item['expected']} actual={item['actual']} status={item['status']} — {item['description']}"
        )
    lines.extend(["", "## Manifest and config inventory"])
    inventory = payload["inventory"]
    labels = {
        "package_jsons": "Frontend package manifests",
        "vite_configs": "Frontend Vite configs",
        "tsconfigs": "TypeScript configs",
        "eslint_configs": "ESLint configs",
        "backend_entrypoints": "Backend runtime entrypoints",
        "frontend_entrypoints": "Frontend runtime entrypoints",
    }
    for key, label in labels.items():
        lines.append(f"- {label}:")
        values = inventory[key]
        if values:
            lines.extend(f"  - `{path}`" for path in values)
        else:
            lines.append("  - _none found_")
    lines.extend(["", "## Structural findings"])
    lines.extend(f"- {item}" for item in payload["findings"])
    lines.extend(["", "## Legacy / compatibility paths to keep out of new code"])
    for item in payload["legacy_pairs"]:
        lines.append(
            f"- `{item['canonical']}` exists={item['canonical_exists']}; `{item['legacy']}` exists={item['legacy_exists']}. {item['guidance']}"
        )
    lines.extend(
        [
            "",
            "## Machine-readable artifact",
            "- JSON snapshot: `docs/audit/REPOSITORY_AUDIT.json`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    inventory = build_inventory()
    payload = {
        "backend_paths": [asdict(item) for item in existing(CANONICAL_BACKEND_PATHS)],
        "frontend_paths": [asdict(item) for item in existing(CANONICAL_FRONTEND_PATHS)],
        "docs_paths": [asdict(item) for item in existing(REQUIRED_DOCS)],
        "root_expectations": build_root_expectations(),
        "inventory": inventory,
        "findings": build_findings(inventory),
        "legacy_pairs": build_legacy_pairs(),
    }

    MARKDOWN_OUTPUT.write_text(render_markdown(payload), encoding="utf-8")
    JSON_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(MARKDOWN_OUTPUT.relative_to(REPO_ROOT))
    print(JSON_OUTPUT.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
