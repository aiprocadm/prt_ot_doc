#!/usr/bin/env python3
"""Run backup/restore drills with machine-readable evidence output."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
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
from typing import Any

import asyncpg
from minio import Minio


@dataclass(frozen=True)
class ObjectSeed:
    key: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class PostgresMinioConfig:
    postgres_source_dsn: str
    postgres_restore_dsn: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool
    source_bucket: str
    restore_bucket: str


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


def _build_seed_objects(tenant_slug: str) -> list[ObjectSeed]:
    return [
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


def _seed_source_sqlite(source_db: Path, source_objects: Path, tenant_slug: str) -> dict[str, object]:
    source_objects.mkdir(parents=True, exist_ok=True)
    objects = _build_seed_objects(tenant_slug)

    con = sqlite3.connect(source_db)
    try:
        cur = con.cursor()
        _ensure_schema_sqlite(cur)
        _seed_rows_sqlite(cur, tenant_slug, objects, source_objects)
        con.commit()

        document_count = cur.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        object_count = cur.execute("SELECT COUNT(*) FROM object_index").fetchone()[0]
        checks = [row[0] for row in cur.execute("SELECT checksum FROM documents ORDER BY id")]
        documents_checksum = _sha256_bytes("|".join(checks).encode("utf-8"))
        object_manifest = [
            {
                "key": key,
                "content_type": content_type,
                "bytes_size": bytes_size,
                "sha256": sha256,
                "metadata": json.loads(metadata_json),
            }
            for key, content_type, bytes_size, sha256, metadata_json in cur.execute(
                "SELECT object_key, content_type, bytes_size, sha256, metadata_json FROM object_index ORDER BY object_key"
            )
        ]
    finally:
        con.close()

    return {
        "tenant_slug": tenant_slug,
        "document_count": document_count,
        "object_count": object_count,
        "documents_checksum": documents_checksum,
        "objects": object_manifest,
    }


def _ensure_schema_sqlite(cur: sqlite3.Cursor) -> None:
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


def _seed_rows_sqlite(cur: sqlite3.Cursor, tenant_slug: str, objects: list[ObjectSeed], source_objects: Path) -> None:
    cur.execute("INSERT OR REPLACE INTO tenants(id, slug, name) VALUES (1, ?, ?)", (tenant_slug, f"Tenant {tenant_slug}"))
    docs = ["Policy A", "Risk Register", "Training Matrix", "Incident Procedure"]
    for idx, title in enumerate(docs, start=1):
        checksum = _sha256_bytes(f"{tenant_slug}:{title}:{idx}".encode("utf-8"))
        cur.execute(
            "INSERT INTO documents(tenant_id, title, checksum, created_at) VALUES (1, ?, ?, ?)",
            (title, checksum, _utc_now()),
        )

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


def _backup_sqlite(source_db: Path, source_objects: Path, backup_dir: Path) -> dict[str, object]:
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


def _restore_sqlite(db_backup: Path, storage_backup: Path, target_db: Path, target_objects: Path) -> None:
    shutil.copy2(db_backup, target_db)
    target_objects.mkdir(parents=True, exist_ok=True)
    with tarfile.open(storage_backup, "r:gz") as tf:
        tf.extractall(path=target_objects, filter="data")


def _read_restore_state_sqlite(target_db: Path, target_objects: Path) -> dict[str, object]:
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


def _run_cmd(cmd: list[str], env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "Command failed: "
            + " ".join(cmd)
            + f"\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


def _minio_client(cfg: PostgresMinioConfig) -> Minio:
    return Minio(cfg.minio_endpoint, access_key=cfg.minio_access_key, secret_key=cfg.minio_secret_key, secure=cfg.minio_secure)


def _ensure_empty_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        return
    objects = list(client.list_objects(bucket, recursive=True))
    if objects:
        for obj in objects:
            client.remove_object(bucket, obj.object_name)


async def _seed_source_postgres(cfg: PostgresMinioConfig, tenant_slug: str) -> dict[str, object]:
    objects = _build_seed_objects(tenant_slug)
    source_conn = await asyncpg.connect(cfg.postgres_source_dsn)
    client = _minio_client(cfg)
    _ensure_empty_bucket(client, cfg.source_bucket)
    _ensure_empty_bucket(client, cfg.restore_bucket)

    try:
        await source_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                checksum TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            );
            CREATE TABLE IF NOT EXISTS object_index (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                object_key TEXT NOT NULL,
                content_type TEXT NOT NULL,
                bytes_size BIGINT NOT NULL,
                sha256 TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            TRUNCATE TABLE documents, object_index, tenants RESTART IDENTITY;
            """
        )
        await source_conn.execute(
            "INSERT INTO tenants(id, slug, name) VALUES (1, $1, $2)",
            tenant_slug,
            f"Tenant {tenant_slug}",
        )
        docs = ["Policy A", "Risk Register", "Training Matrix", "Incident Procedure"]
        for idx, title in enumerate(docs, start=1):
            checksum = _sha256_bytes(f"{tenant_slug}:{title}:{idx}".encode("utf-8"))
            await source_conn.execute(
                "INSERT INTO documents(tenant_id, title, checksum, created_at) VALUES (1, $1, $2, NOW())",
                title,
                checksum,
            )

        object_manifest: list[dict[str, Any]] = []
        for obj in objects:
            metadata = {"cache-control": "max-age=60", "origin": "restore-drill"}
            digest = _sha256_bytes(obj.content)
            client.put_object(
                cfg.source_bucket,
                obj.key,
                data=io.BytesIO(obj.content),
                length=len(obj.content),
                content_type=obj.content_type,
                metadata=metadata,
            )
            await source_conn.execute(
                """
                INSERT INTO object_index(tenant_id, object_key, content_type, bytes_size, sha256, metadata_json)
                VALUES (1, $1, $2, $3, $4, $5)
                """,
                obj.key,
                obj.content_type,
                len(obj.content),
                digest,
                json.dumps(metadata, sort_keys=True),
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

        document_count = await source_conn.fetchval("SELECT COUNT(*) FROM documents")
        object_count = await source_conn.fetchval("SELECT COUNT(*) FROM object_index")
        checks = await source_conn.fetch("SELECT checksum FROM documents ORDER BY id")
        documents_checksum = _sha256_bytes("|".join(row["checksum"] for row in checks).encode("utf-8"))
    finally:
        await source_conn.close()

    return {
        "tenant_slug": tenant_slug,
        "document_count": int(document_count),
        "object_count": int(object_count),
        "documents_checksum": documents_checksum,
        "objects": object_manifest,
    }


def _backup_postgres_minio(cfg: PostgresMinioConfig, backup_dir: Path, object_prefix: str) -> dict[str, object]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    db_backup = backup_dir / "db_backup.dump"
    storage_backup = backup_dir / "objects_backup.tar.gz"

    _run_cmd(["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(db_backup), cfg.postgres_source_dsn])

    client = _minio_client(cfg)
    with tarfile.open(storage_backup, "w:gz") as tf:
        for obj in client.list_objects(cfg.source_bucket, prefix=f"{object_prefix}/", recursive=True):
            response = client.get_object(cfg.source_bucket, obj.object_name)
            try:
                payload = response.read()
            finally:
                response.close()
                response.release_conn()
            stat = client.stat_object(cfg.source_bucket, obj.object_name)
            tar_info = tarfile.TarInfo(name=f"objects/{obj.object_name}")
            tar_info.size = len(payload)
            tf.addfile(tar_info, io.BytesIO(payload))

            meta = {
                "content_type": stat.content_type,
                "metadata": {k.lower(): v for k, v in (stat.metadata or {}).items() if k.lower().startswith("x-amz-meta-")},
            }
            meta_bytes = json.dumps(meta, sort_keys=True).encode("utf-8")
            meta_info = tarfile.TarInfo(name=f"objects/{obj.object_name}.meta.json")
            meta_info.size = len(meta_bytes)
            tf.addfile(meta_info, io.BytesIO(meta_bytes))

    return {
        "db_backup_path": str(db_backup),
        "db_sha256": _sha256_file(db_backup),
        "storage_backup_path": str(storage_backup),
        "storage_sha256": _sha256_file(storage_backup),
    }


def _restore_postgres_minio(cfg: PostgresMinioConfig, db_backup: Path, storage_backup: Path) -> None:
    _run_cmd(["pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges", "--dbname", cfg.postgres_restore_dsn, str(db_backup)])

    client = _minio_client(cfg)
    _ensure_empty_bucket(client, cfg.restore_bucket)

    with tempfile.TemporaryDirectory(prefix="restore-drill-minio-") as temp_extract:
        extract_dir = Path(temp_extract)
        with tarfile.open(storage_backup, "r:gz") as tf:
            tf.extractall(path=extract_dir, filter="data")
        objects_root = extract_dir / "objects"
        for file_path in objects_root.rglob("*"):
            if not file_path.is_file() or file_path.name.endswith(".meta.json"):
                continue
            object_name = str(file_path.relative_to(objects_root)).replace("\\", "/")
            meta_path = file_path.with_suffix(file_path.suffix + ".meta.json")
            metadata_payload = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            raw_meta = metadata_payload.get("metadata", {})
            user_meta = {k.replace("x-amz-meta-", ""): v for k, v in raw_meta.items() if k.startswith("x-amz-meta-")}
            content_type = metadata_payload.get("content_type") or "application/octet-stream"
            payload = file_path.read_bytes()
            client.put_object(
                cfg.restore_bucket,
                object_name,
                data=io.BytesIO(payload),
                length=len(payload),
                content_type=content_type,
                metadata=user_meta,
            )


async def _read_restore_state_postgres(cfg: PostgresMinioConfig) -> dict[str, object]:
    conn = await asyncpg.connect(cfg.postgres_restore_dsn)
    client = _minio_client(cfg)
    try:
        tenant_slug = await conn.fetchval("SELECT slug FROM tenants ORDER BY id LIMIT 1")
        document_count = await conn.fetchval("SELECT COUNT(*) FROM documents")
        object_count = await conn.fetchval("SELECT COUNT(*) FROM object_index")
        checks = await conn.fetch("SELECT checksum FROM documents ORDER BY id")
        documents_checksum = _sha256_bytes("|".join(row["checksum"] for row in checks).encode("utf-8"))

        objs = []
        rows = await conn.fetch(
            "SELECT object_key, content_type, bytes_size, sha256, metadata_json FROM object_index ORDER BY object_key"
        )
        for row in rows:
            key = row["object_key"]
            response = client.get_object(cfg.restore_bucket, key)
            try:
                payload = response.read()
            finally:
                response.close()
                response.release_conn()
            stat = client.stat_object(cfg.restore_bucket, key)
            actual_metadata = {k.lower(): v for k, v in (stat.metadata or {}).items() if k.lower().startswith("x-amz-meta-")}
            expected_metadata = {
                f"x-amz-meta-{k.lower()}": v for k, v in json.loads(row["metadata_json"]).items()
            }
            objs.append(
                {
                    "key": key,
                    "content_type": row["content_type"],
                    "bytes_size": row["bytes_size"],
                    "sha256": row["sha256"],
                    "actual_sha256": _sha256_bytes(payload),
                    "metadata": actual_metadata,
                    "expected_metadata": expected_metadata,
                    "content_type_match": (stat.content_type or "") == row["content_type"],
                }
            )
    finally:
        await conn.close()

    return {
        "tenant_slug": tenant_slug,
        "document_count": int(document_count),
        "object_count": int(object_count),
        "documents_checksum": documents_checksum,
        "objects": objs,
    }


def _app_smoke_boot(*, database_url: str, s3_env: dict[str, str] | None = None) -> dict[str, object]:
    cmd = [sys.executable, "-m", "backend.app.cli.main", "health-check", "--json"]
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env.setdefault("APP_ENV", "test")
    env.setdefault("REDIS_URL", "memory://")
    env.setdefault("REDIS_RESULT_URL", "memory://")
    env.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")
    env.setdefault("PYTHONPATH", str(Path("backend").resolve()))
    if s3_env:
        env.update(s3_env)

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


def run_drill_sqlite(output_dir: Path, tenant_slug: str) -> Path:
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

        seeded = _seed_source_sqlite(source_db, source_objects, tenant_slug)
        backup = _backup_sqlite(source_db, source_objects, backup_dir)
        _restore_sqlite(Path(backup["db_backup_path"]), Path(backup["storage_backup_path"]), target_db, target_objects)
        restored = _read_restore_state_sqlite(target_db, target_objects)
        smoke = _app_smoke_boot(database_url=f"sqlite+aiosqlite:///{target_db}")

    return _write_evidence(output_dir, timestamp, started, tenant_slug, "sqlite", seeded, backup, restored, smoke)


def run_drill_postgres_minio(output_dir: Path, tenant_slug: str, cfg: PostgresMinioConfig) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    with tempfile.TemporaryDirectory(prefix="restore-drill-") as tmp:
        workspace = Path(tmp)
        backup_dir = workspace / "backup"

        seeded = asyncio.run(_seed_source_postgres(cfg, tenant_slug=tenant_slug))
        backup = _backup_postgres_minio(cfg, backup_dir, object_prefix=tenant_slug)
        _restore_postgres_minio(cfg, Path(backup["db_backup_path"]), Path(backup["storage_backup_path"]))
        restored = asyncio.run(_read_restore_state_postgres(cfg))
        smoke = _app_smoke_boot(
            database_url=cfg.postgres_restore_dsn.replace("postgresql://", "postgresql+asyncpg://", 1),
            s3_env={
                "STORAGE_BACKEND": "s3",
                "S3_BACKEND": "minio",
                "S3_ENDPOINT": (f"https://{cfg.minio_endpoint}" if cfg.minio_secure else f"http://{cfg.minio_endpoint}"),
                "S3_BUCKET": cfg.restore_bucket,
                "S3_ACCESS_KEY": cfg.minio_access_key,
                "S3_SECRET_KEY": cfg.minio_secret_key,
                "S3_SECURE": "true" if cfg.minio_secure else "false",
            },
        )

    return _write_evidence(output_dir, timestamp, started, tenant_slug, "postgres-minio", seeded, backup, restored, smoke)


def _write_evidence(
    output_dir: Path,
    timestamp: str,
    started: float,
    tenant_slug: str,
    mode: str,
    seeded: dict[str, object],
    backup: dict[str, object],
    restored: dict[str, object],
    smoke: dict[str, object],
) -> Path:
    verify_counts = seeded["document_count"] == restored["document_count"] and seeded["object_count"] == restored["object_count"]
    verify_checksum = seeded["documents_checksum"] == restored["documents_checksum"]
    metadata_mismatch = [
        item["key"]
        for item in restored["objects"]
        if item["sha256"] != item["actual_sha256"]
        or item["metadata"] != item["expected_metadata"]
        or not item.get("content_type_match", True)
    ]
    verify_objects = len(metadata_mismatch) == 0

    duration_seconds = round(time.monotonic() - started, 3)
    evidence = {
        "drill": {
            "id": f"restore-drill-{mode}-{timestamp}",
            "mode": mode,
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

    output_path = output_dir / f"{mode}-{timestamp}.json"
    output_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    latest_path = output_dir / f"latest-{mode}.json"
    latest_path.write_text(output_path.read_text(encoding="utf-8"), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run backup/restore drills and emit JSON evidence.")
    parser.add_argument("--output-dir", default="artifacts/restore-drill", help="Directory for JSON evidence artifacts.")
    parser.add_argument("--tenant-slug", default="restore-drill-tenant", help="Tenant slug used for representative seed data.")
    parser.add_argument("--mode", choices=["sqlite", "postgres-minio"], default="sqlite", help="Drill mode.")
    parser.add_argument("--postgres-source-dsn", default=os.getenv("RESTORE_DRILL_POSTGRES_SOURCE_DSN", ""), help="Postgres source DSN.")
    parser.add_argument("--postgres-restore-dsn", default=os.getenv("RESTORE_DRILL_POSTGRES_RESTORE_DSN", ""), help="Postgres restore DSN.")
    parser.add_argument("--minio-endpoint", default=os.getenv("RESTORE_DRILL_MINIO_ENDPOINT", "localhost:9000"), help="MinIO endpoint host:port.")
    parser.add_argument("--minio-access-key", default=os.getenv("RESTORE_DRILL_MINIO_ACCESS_KEY", "minioadmin"), help="MinIO access key.")
    parser.add_argument("--minio-secret-key", default=os.getenv("RESTORE_DRILL_MINIO_SECRET_KEY", "minioadmin"), help="MinIO secret key.")
    parser.add_argument("--minio-secure", action="store_true", default=os.getenv("RESTORE_DRILL_MINIO_SECURE", "false").lower() == "true", help="Use TLS for MinIO.")
    parser.add_argument("--minio-source-bucket", default=os.getenv("RESTORE_DRILL_MINIO_SOURCE_BUCKET", "restore-drill-source"), help="MinIO source bucket.")
    parser.add_argument("--minio-restore-bucket", default=os.getenv("RESTORE_DRILL_MINIO_RESTORE_BUCKET", "restore-drill-restored"), help="MinIO restore bucket.")
    return parser.parse_args()


def _require(value: str, name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required for --mode postgres-minio")
    return value


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    if args.mode == "sqlite":
        output_path = run_drill_sqlite(output_dir, tenant_slug=args.tenant_slug)
    else:
        cfg = PostgresMinioConfig(
            postgres_source_dsn=_require(args.postgres_source_dsn, "--postgres-source-dsn"),
            postgres_restore_dsn=_require(args.postgres_restore_dsn, "--postgres-restore-dsn"),
            minio_endpoint=args.minio_endpoint,
            minio_access_key=args.minio_access_key,
            minio_secret_key=args.minio_secret_key,
            minio_secure=bool(args.minio_secure),
            source_bucket=args.minio_source_bucket,
            restore_bucket=args.minio_restore_bucket,
        )
        output_path = run_drill_postgres_minio(output_dir, tenant_slug=args.tenant_slug, cfg=cfg)

    print(json.dumps({"status": "ok", "mode": args.mode, "evidence": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
