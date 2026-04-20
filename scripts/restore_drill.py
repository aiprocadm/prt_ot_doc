#!/usr/bin/env python3
"""Run a local backup/restore drill with machine-readable evidence output."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class ObjectSeed:
    key: str
    content_type: str
    content: bytes


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _seed_source(source_db: Path, source_objects: Path, tenant_slug: str) -> dict[str, object]:
    source_objects.mkdir(parents=True, exist_ok=True)

    objects = [
        ObjectSeed(
            key=f"{tenant_slug}/templates/welcome.txt",
            content_type="text/plain",
            content=b"Welcome to restore drill.\n",
        ),
        ObjectSeed(
            key=f"{tenant_slug}/exports/checklist.json",
            content_type="application/json",
            content=json.dumps({"tenant": tenant_slug, "kind": "checklist", "v": 1}, separators=(",", ":")).encode("utf-8"),
        ),
        ObjectSeed(
            key=f"{tenant_slug}/audit/events.log",
            content_type="text/plain",
            content=b"2026-04-19T00:00:00Z seed restore drill\n",
        ),
    ]

    con = sqlite3.connect(source_db)
    try:
        cur = con.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                checksum TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            );
            CREATE TABLE IF NOT EXISTS object_index (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                object_key TEXT NOT NULL,
                content_type TEXT NOT NULL,
                bytes_size INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            );
            """
        )
        cur.execute("INSERT OR REPLACE INTO tenants(id, slug, name) VALUES (1, ?, ?)", (tenant_slug, f"Tenant {tenant_slug}"))
        docs = [
            "Policy A",
            "Risk Register",
            "Training Matrix",
            "Incident Procedure",
        ]
        for idx, title in enumerate(docs, start=1):
            checksum = _sha256_bytes(f"{tenant_slug}:{title}:{idx}".encode("utf-8"))
            cur.execute(
                "INSERT INTO documents(tenant_id, title, checksum, created_at) VALUES (1, ?, ?, ?)",
                (title, checksum, _utc_now()),
            )

        object_manifest: list[dict[str, object]] = []
        for obj in objects:
            object_path = source_objects / obj.key
            object_path.parent.mkdir(parents=True, exist_ok=True)
            object_path.write_bytes(obj.content)
            digest = _sha256_bytes(obj.content)
            metadata = {"cache_control": "max-age=60", "origin": "restore-drill"}
            metadata_path = object_path.with_suffix(object_path.suffix + ".meta.json")
            metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
            cur.execute(
                """
                INSERT INTO object_index(tenant_id, object_key, content_type, bytes_size, sha256, metadata_json)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (obj.key, obj.content_type, len(obj.content), digest, json.dumps(metadata, sort_keys=True)),
            )
            object_manifest.append(
                {
                    "key": obj.key,
                    "content_type": obj.content_type,
                    "bytes_size": len(obj.content),
                    "sha256": digest,
                    "metadata": metadata,
                }
            )

        con.commit()

        document_count = cur.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        object_count = cur.execute("SELECT COUNT(*) FROM object_index").fetchone()[0]
        checks = [row[0] for row in cur.execute("SELECT checksum FROM documents ORDER BY id")]
        documents_checksum = _sha256_bytes("|".join(checks).encode("utf-8"))
    finally:
        con.close()

    return {
        "tenant_slug": tenant_slug,
        "document_count": document_count,
        "object_count": object_count,
        "documents_checksum": documents_checksum,
        "objects": object_manifest,
    }


def _backup(source_db: Path, source_objects: Path, backup_dir: Path) -> dict[str, object]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    db_backup = backup_dir / "db_backup.sqlite3"
    storage_backup = backup_dir / "objects_backup.tar.gz"

    src = sqlite3.connect(source_db)
    dst = sqlite3.connect(db_backup)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    with tarfile.open(storage_backup, "w:gz") as tf:
        tf.add(source_objects, arcname="objects")

    return {
        "db_backup_path": str(db_backup),
        "db_sha256": _sha256_file(db_backup),
        "storage_backup_path": str(storage_backup),
        "storage_sha256": _sha256_file(storage_backup),
    }


def _restore(db_backup: Path, storage_backup: Path, target_db: Path, target_objects: Path) -> None:
    shutil.copy2(db_backup, target_db)
    target_objects.mkdir(parents=True, exist_ok=True)
    with tarfile.open(storage_backup, "r:gz") as tf:
        tf.extractall(path=target_objects, filter="data")


def _read_restore_state(target_db: Path, target_objects: Path) -> dict[str, object]:
    con = sqlite3.connect(target_db)
    try:
        cur = con.cursor()
        tenant_slug = cur.execute("SELECT slug FROM tenants ORDER BY id LIMIT 1").fetchone()[0]
        document_count = cur.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        object_count = cur.execute("SELECT COUNT(*) FROM object_index").fetchone()[0]
        checks = [row[0] for row in cur.execute("SELECT checksum FROM documents ORDER BY id")]
        documents_checksum = _sha256_bytes("|".join(checks).encode("utf-8"))

        objs = []
        for key, content_type, bytes_size, sha256, metadata_json in cur.execute(
            "SELECT object_key, content_type, bytes_size, sha256, metadata_json FROM object_index ORDER BY object_key"
        ):
            object_path = target_objects / "objects" / key
            payload = object_path.read_bytes()
            metadata_path = object_path.with_suffix(object_path.suffix + ".meta.json")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            objs.append(
                {
                    "key": key,
                    "content_type": content_type,
                    "bytes_size": bytes_size,
                    "sha256": sha256,
                    "actual_sha256": _sha256_bytes(payload),
                    "metadata": metadata,
                    "expected_metadata": json.loads(metadata_json),
                }
            )
    finally:
        con.close()

    return {
        "tenant_slug": tenant_slug,
        "document_count": document_count,
        "object_count": object_count,
        "documents_checksum": documents_checksum,
        "objects": objs,
    }


def _app_smoke_boot(target_db: Path) -> dict[str, object]:
    cmd = [sys.executable, "-m", "backend.app.cli.main", "health", "check", "--json"]
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{target_db}"
    env.setdefault("APP_ENV", "test")
    env.setdefault("REDIS_URL", "memory://")
    env.setdefault("REDIS_RESULT_URL", "memory://")
    env.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")
    env.setdefault("PYTHONPATH", str(Path("backend").resolve()))

    completed = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    payload: dict[str, object] = {
        "command": " ".join(cmd),
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    if completed.returncode == 0:
        try:
            payload["json"] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload["json"] = None
    return payload


def run_drill(output_dir: Path, tenant_slug: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    with tempfile.TemporaryDirectory(prefix="restore-drill-") as tmp:
        workspace = Path(tmp)
        source_db = workspace / "source.sqlite3"
        source_objects = workspace / "source-objects"
        backup_dir = workspace / "backup"
        target_db = workspace / "restore" / "restored.sqlite3"
        target_objects = workspace / "restore" / "objects"
        target_db.parent.mkdir(parents=True, exist_ok=True)

        seeded = _seed_source(source_db, source_objects, tenant_slug)
        backup = _backup(source_db, source_objects, backup_dir)
        _restore(Path(backup["db_backup_path"]), Path(backup["storage_backup_path"]), target_db, target_objects)
        restored = _read_restore_state(target_db, target_objects)
        smoke = _app_smoke_boot(target_db)

    verify_counts = seeded["document_count"] == restored["document_count"] and seeded["object_count"] == restored["object_count"]
    verify_checksum = seeded["documents_checksum"] == restored["documents_checksum"]
    metadata_mismatch = [
        item["key"]
        for item in restored["objects"]
        if item["sha256"] != item["actual_sha256"] or item["metadata"] != item["expected_metadata"]
    ]
    verify_objects = len(metadata_mismatch) == 0

    duration_seconds = round(time.monotonic() - started, 3)
    evidence = {
        "drill": {
            "id": f"restore-drill-{timestamp}",
            "executed_at_utc": _utc_now(),
            "duration_seconds": duration_seconds,
            "tenant_slug": tenant_slug,
            "assumed_rto_seconds": 900,
            "assumed_rpo_seconds": 300,
        },
        "seed": seeded,
        "backup": backup,
        "restore": {
            "state": restored,
            "verification": {
                "counts_match": verify_counts,
                "documents_checksum_match": verify_checksum,
                "object_content_and_metadata_match": verify_objects,
                "object_mismatches": metadata_mismatch,
            },
        },
        "smoke_boot": smoke,
        "success": bool(verify_counts and verify_checksum and verify_objects and smoke["exit_code"] == 0),
    }

    output_path = output_dir / f"{timestamp}.json"
    output_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    latest_path = output_dir / "latest.json"
    latest_path.write_text(output_path.read_text(encoding="utf-8"), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local backup/restore drill and emit JSON evidence.")
    parser.add_argument("--output-dir", default="artifacts/restore-drill", help="Directory for JSON evidence artifacts.")
    parser.add_argument("--tenant-slug", default="restore-drill-tenant", help="Tenant slug used for representative seed data.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = run_drill(Path(args.output_dir), tenant_slug=args.tenant_slug)
    print(json.dumps({"status": "ok", "evidence": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
