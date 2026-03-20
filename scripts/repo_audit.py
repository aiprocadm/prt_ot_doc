from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def main() -> None:
    package_jsons = sorted(
        path for path in REPO_ROOT.glob('**/package.json') if 'node_modules' not in path.parts and '.git' not in path.parts
    )
    pyproject = REPO_ROOT / 'pyproject.toml'
    backend_main = REPO_ROOT / 'backend/app/main.py'
    frontend_root = REPO_ROOT / 'frontend'
    docs_pairs = [
        ('docs/ADR', 'docs/adr'),
        ('backend/app/modules/approval', 'backend/app/modules/approvals'),
    ]

    lines = [
        '# Repository audit snapshot',
        '',
        '## Canonical roots',
        f'- Backend root: `backend/` (entrypoint `{rel(backend_main)}`).',
        f'- Frontend root: `frontend/` (active manifest `{rel(frontend_root / "package.json")}`).',
        f'- Python project config: `{rel(pyproject)}`.',
        '',
        '## Frontend manifests found',
    ]
    lines.extend(f'- `{rel(path)}`' for path in package_jsons)
    lines.extend([
        '',
        '## Structural flags',
        f'- Backend entrypoint exists: **{"yes" if backend_main.exists() else "no"}**.',
        f'- Frontend package.json count: **{len(package_jsons)}**.',
        f'- Frontend Vite config exists: **{"yes" if (frontend_root / "vite.config.ts").exists() else "no"}**.',
        f'- Frontend tsconfig exists: **{"yes" if (frontend_root / "tsconfig.json").exists() else "no"}**.',
        '',
        '## Legacy / compatibility paths to keep out of new code',
    ])
    for left, right in docs_pairs:
        left_exists = (REPO_ROOT / left).exists()
        right_exists = (REPO_ROOT / right).exists()
        lines.append(f'- `{left}` exists={left_exists}; `{right}` exists={right_exists}. Canonical path should be documented before new changes touch either tree.')

    output = REPO_ROOT / 'docs/audit/REPOSITORY_AUDIT.md'
    output.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(output.relative_to(REPO_ROOT))


if __name__ == '__main__':
    main()
