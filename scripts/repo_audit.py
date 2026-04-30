from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_OUTPUT = REPO_ROOT / "docs/audit/REPOSITORY_AUDIT.md"
JSON_OUTPUT = REPO_ROOT / "docs/audit/REPOSITORY_AUDIT.json"

EXCLUDED_PARTS = {"node_modules", ".git", ".venv", "dist", "__pycache__", ".pytest_cache"}
WORKTREE_MARKERS = {".git"}  # Files indicating worktree/nested repo


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


@dataclass(frozen=True)
class CanonicalSection:
    label: str
    paths: tuple[str, ...]
    description: str


CANONICAL_ROOTS = {
    "backend_root": "backend",
    "frontend_root": "frontend",
    "docs_root": "docs",
    "tests_roots": ["tests", "integration_tests", "frontend/src/__tests__"],
}

CANONICAL_LAYOUT: tuple[CanonicalSection, ...] = (
    CanonicalSection(
        "backend",
        (
            "backend/app",
            "backend/app/api",
            "backend/app/modules",
            "backend/app/domains",
            "backend/app/migrations",
            "backend/tests",
        ),
        "Backend runtime, domain/application modules, and backend-local tests.",
    ),
    CanonicalSection(
        "frontend",
        (
            "frontend/src",
            "frontend/src/router",
            "frontend/src/pages",
            "frontend/src/components",
            "frontend/src/__tests__",
        ),
        "SPA runtime, route tree, feature pages, shared components, and frontend tests.",
    ),
    CanonicalSection(
        "docs",
        ("docs", "docs/audit", "docs/ADR", "docs/runbook", "docs/spec"),
        "Canonical documentation roots, audit reports, ADRs, runbooks, and spec snapshots.",
    ),
    CanonicalSection(
        "tooling",
        ("scripts", "infra", "config", "seed", "proxy"),
        "Operational scripts, infrastructure manifests, environment config, seed data, and proxy assets.",
    ),
)

BACKEND_PATHS: tuple[CanonicalPath, ...] = (
    CanonicalPath("ASGI entrypoint", "backend/app/main.py", "Uvicorn/FastAPI runtime entrypoint."),
    CanonicalPath("App factory", "backend/app/api/app.py", "Application factory and middleware wiring."),
    CanonicalPath("API router", "backend/app/api/v1/router.py", "Top-level v1 router composition."),
    CanonicalPath("CLI entrypoint", "backend/app/cli/main.py", "Operator CLI commands."),
    CanonicalPath("Worker entrypoint", "backend/app/worker.py", "Celery worker bootstrap."),
    CanonicalPath("Alembic config", "backend/app/migrations/alembic.ini", "Database migration configuration."),
)

FRONTEND_PATHS: tuple[CanonicalPath, ...] = (
    CanonicalPath("Package manifest", "frontend/package.json", "Single active frontend package manifest."),
    CanonicalPath("Vite config", "frontend/vite.config.ts", "Frontend bundler/runtime config."),
    CanonicalPath("TypeScript config", "frontend/tsconfig.json", "Application TypeScript project config."),
    CanonicalPath("Node TS config", "frontend/tsconfig.node.json", "Node-side TS config for build tooling."),
    CanonicalPath("React entrypoint", "frontend/src/main.tsx", "Browser bootstrap for the SPA."),
    CanonicalPath("Route tree", "frontend/src/router/AppRouter.tsx", "Canonical route composition."),
)

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

LEGACY_PATH_PAIRS: tuple[LegacyPathPair, ...] = (
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
    LegacyPathPair(
        canonical="docs/PROJECT_STRUCTURE.md",
        legacy="docs/repo-structure.md",
        guidance="Prefer `docs/PROJECT_STRUCTURE.md` and keep `docs/repo-structure.md` only as legacy documentation.",
    ),
)

ROOT_EXPECTATIONS: tuple[ExistenceCheck, ...] = (
    ExistenceCheck("Backend root", "backend", True, "Canonical backend source root."),
    ExistenceCheck("Frontend root", "frontend", True, "Canonical frontend source root."),
    ExistenceCheck("Docs root", "docs", True, "Repository documentation root."),
    ExistenceCheck("Root package.json", "package.json", False, "A repo-root frontend manifest should not exist."),
    ExistenceCheck("Frontend package.json", "frontend/package.json", True, "The active frontend package manifest must exist here."),
    ExistenceCheck("Compatibility shim", "app/__init__.py", True, "Legacy `app.*` imports are intentionally supported through this shim."),
)


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def include_path(path: Path) -> bool:
    """Check if a path should be included in the audit.

    Excludes:
    - Non-files
    - Paths containing excluded parts (node_modules, .git, .venv, etc.)
    - Paths from worktrees (detected by .git file markers in parent dirs)
    """
    if not path.is_file():
        return False

    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False

    # Exclude files from worktree directories (detected by .git file in any parent except root)
    for parent in path.parents:
        if parent == REPO_ROOT:
            break
        git_marker = parent / ".git"
        if git_marker.exists() and git_marker.is_file():
            return False  # This is a worktree, exclude it

    return True


def find_files(*patterns: str) -> list[str]:
    matches: set[str] = set()
    for pattern in patterns:
        for path in REPO_ROOT.glob(pattern):
            if include_path(path):
                matches.add(rel(path))
    return sorted(matches)


def existing(paths: tuple[CanonicalPath, ...]) -> list[CanonicalPath]:
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
        "repo_level_directories": sorted(
            path.name for path in REPO_ROOT.iterdir() if path.is_dir() and path.name not in EXCLUDED_PARTS
        ),
    }


def build_layout_sections() -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    for section in CANONICAL_LAYOUT:
        entries = []
        for path in section.paths:
            entries.append(
                {
                    "path": path,
                    "exists": (REPO_ROOT / path).exists(),
                }
            )
        sections.append(
            {
                "label": section.label,
                "description": section.description,
                "paths": entries,
            }
        )
    return sections


def build_doc_alignment() -> dict[str, object]:
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    docs_index_text = (REPO_ROOT / "docs/README.md").read_text(encoding="utf-8")
    canonical_links = [
        "docs/ARCHITECTURE.md",
        "docs/PROJECT_STRUCTURE.md",
        "docs/SETUP.md",
        "docs/BACKEND.md",
        "docs/FRONTEND.md",
        "docs/MODULES.md",
        "docs/API_OVERVIEW.md",
        "docs/DOMAIN_MODEL.md",
        "docs/DOCUMENT_CORE.md",
        "docs/INTEGRATIONS.md",
        "docs/SECURITY.md",
        "docs/OBSERVABILITY.md",
        "docs/TESTING.md",
        "docs/WORKFLOWS_AND_EVENTS.md",
    ]
    return {
        "readme_mentions": {
            path: (path in readme_text) for path in canonical_links
        },
        "docs_index_mentions": {
            path: (path.removeprefix("docs/") in docs_index_text) for path in canonical_links
        },
    }


def build_root_expectations() -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for item in ROOT_EXPECTATIONS:
        actual = (REPO_ROOT / item.path).exists()
        results.append(
            {
                "label": item.label,
                "path": item.path,
                "expected": item.exists,
                "actual": actual,
                "status": "ok" if actual == item.exists else "mismatch",
                "description": item.description,
            }
        )
    return results


def build_findings(inventory: dict[str, list[str]]) -> list[str]:
    required_docs_present = len(existing(REQUIRED_DOCS))
    required_docs_expected = len(REQUIRED_DOCS)
    duplicate_frontend_roots = [path for path in inventory["package_jsons"] if path != "frontend/package.json"]
    return [
        f"Active frontend manifest count: **{len(inventory['package_jsons'])}**.",
        f"Unexpected extra frontend manifests: **{', '.join(duplicate_frontend_roots) if duplicate_frontend_roots else 'none'}**.",
        f"Backend runtime entrypoint present: **{'yes' if (REPO_ROOT / 'backend/app/main.py').exists() else 'no'}**.",
        f"Frontend root contains Vite config: **{'yes' if (REPO_ROOT / 'frontend/vite.config.ts').exists() else 'no'}**.",
        f"Frontend root contains tsconfig: **{'yes' if (REPO_ROOT / 'frontend/tsconfig.json').exists() else 'no'}**.",
        f"Repo-root compatibility package `app/`: **{'yes' if (REPO_ROOT / 'app/__init__.py').exists() else 'no'}**.",
        f"Required docs present: **{required_docs_present}/{required_docs_expected}**.",
    ]


def build_legacy_pairs() -> list[dict[str, object]]:
    return [
        {
            "canonical": item.canonical,
            "canonical_exists": (REPO_ROOT / item.canonical).exists(),
            "legacy": item.legacy,
            "legacy_exists": (REPO_ROOT / item.legacy).exists(),
            "guidance": item.guidance,
        }
        for item in LEGACY_PATH_PAIRS
    ]


def build_payload() -> dict[str, object]:
    inventory = build_inventory()
    required_docs_present = len(existing(REQUIRED_DOCS))
    required_docs_expected = len(REQUIRED_DOCS)
    return {
        "canonical_roots": CANONICAL_ROOTS,
        "canonical_layout": build_layout_sections(),
        "backend_paths": [asdict(item) for item in existing(BACKEND_PATHS)],
        "frontend_paths": [asdict(item) for item in existing(FRONTEND_PATHS)],
        "required_docs": [asdict(item) for item in existing(REQUIRED_DOCS)],
        "root_expectations": build_root_expectations(),
        "inventory": inventory,
        "findings": {
            "active_frontend_manifest_count": len(inventory["package_jsons"]),
            "backend_runtime_entrypoint_present": (REPO_ROOT / "backend/app/main.py").exists(),
            "frontend_vite_config_present": (REPO_ROOT / "frontend/vite.config.ts").exists(),
            "frontend_tsconfig_present": (REPO_ROOT / "frontend/tsconfig.json").exists(),
            "app_compat_shim_present": (REPO_ROOT / "app/__init__.py").exists(),
            "required_docs_present": required_docs_present,
            "required_docs_expected": required_docs_expected,
            "summary_lines": build_findings(inventory),
        },
        "doc_alignment": build_doc_alignment(),
        "legacy_paths": build_legacy_pairs(),
        "legacy_pairs": build_legacy_pairs(),
        "generated_from": rel(Path(__file__)),
        "consistency_watchlist": [
            "Keep README.md and docs/README.md aligned when startup commands or canonical paths change.",
            "Keep `.env.example`, `backend/.env.example`, and docs/SETUP.md aligned when environment variables or startup flags change.",
            "Keep legacy compatibility paths out of new imports, routes, and docs references.",
        ],
    }


def render_markdown(payload: dict[str, object]) -> str:
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
        "## Canonical layout sections",
    ]
    for section in payload["canonical_layout"]:
        lines.append(f"- **{section['label']}:** {section['description']}")
        lines.extend(
            f"  - `{item['path']}` exists={item['exists']}" for item in section["paths"]
        )
    lines.extend([
        "",
        "## Active backend entrypoints and configs",
    ])
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
        "repo_level_directories": "Repo-level directories",
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
    lines.extend(f"- {item}" for item in payload["findings"]["summary_lines"])
    lines.extend(["", "## README / docs index alignment"])
    lines.append("- README.md canonical doc references:")
    for path, present in payload["doc_alignment"]["readme_mentions"].items():
        lines.append(f"  - `{path}` present={present}")
    lines.append("- docs/README.md canonical doc references:")
    for path, present in payload["doc_alignment"]["docs_index_mentions"].items():
        lines.append(f"  - `{path.removeprefix('docs/')}` present={present}")
    lines.extend(["", "## Legacy / compatibility paths to keep out of new code"])
    for item in payload["legacy_pairs"]:
        lines.append(
            f"- `{item['canonical']}` exists={item['canonical_exists']}; `{item['legacy']}` exists={item['legacy_exists']}. {item['guidance']}"
        )
    lines.extend(["", "## Consistency watchlist"])
    lines.extend(f"- {item}" for item in payload["consistency_watchlist"])
    lines.extend(["", "## Machine-readable artifact", "- JSON snapshot: `docs/audit/REPOSITORY_AUDIT.json`."])
    return "\n".join(lines) + "\n"


def write_outputs(payload: dict[str, object]) -> None:
    MARKDOWN_OUTPUT.write_text(render_markdown(payload), encoding="utf-8")
    JSON_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    payload = build_payload()
    write_outputs(payload)
    print(rel(MARKDOWN_OUTPUT))
    print(rel(JSON_OUTPUT))


if __name__ == "__main__":
    main()
