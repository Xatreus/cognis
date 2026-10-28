"""Tenant-scoped evaluation storage supporting PostgreSQL and SQLite development."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "cognis.db"


def _connect():
    database_url = os.getenv("COGNIS_DATABASE_URL", "").strip()
    if database_url.startswith(("postgres://", "postgresql://")):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL configured but psycopg is not installed") from exc
        return psycopg.connect(database_url, row_factory=dict_row)
    configured = os.getenv("COGNIS_DATABASE_PATH", str(DEFAULT_DB))
    path = Path(configured)
    if configured != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _is_postgres(conn) -> bool:
    return not isinstance(conn, sqlite3.Connection)


def initialize_store() -> None:
    with closing(_connect()) as conn, conn:
        if _is_postgres(conn):
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    evaluation_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    suite TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('passed', 'failed')),
                    total INTEGER NOT NULL CHECK(total >= 0),
                    passed INTEGER NOT NULL CHECK(passed >= 0),
                    failed INTEGER NOT NULL CHECK(failed >= 0),
                    pass_rate DOUBLE PRECISION NOT NULL CHECK(pass_rate >= 0 AND pass_rate <= 1),
                    created_at TEXT NOT NULL,
                    payload JSONB NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evaluation_runs_tenant_created ON evaluation_runs(tenant_id, created_at DESC)")
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    evaluation_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    suite TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('passed', 'failed')),
                    total INTEGER NOT NULL CHECK(total >= 0),
                    passed INTEGER NOT NULL CHECK(passed >= 0),
                    failed INTEGER NOT NULL CHECK(failed >= 0),
                    pass_rate REAL NOT NULL CHECK(pass_rate >= 0 AND pass_rate <= 1),
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evaluation_runs_tenant_created ON evaluation_runs(tenant_id, created_at DESC)")


def save_evaluation(result: Any, tenant_id: str = "local") -> dict[str, Any]:
    """Persist an evaluation under the authenticated tenant identity."""
    initialize_store()
    payload = result.model_dump(mode="json")
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        if _is_postgres(conn):
            conn.execute("""
                INSERT INTO evaluation_runs
                (evaluation_id, tenant_id, suite, status, total, passed, failed, pass_rate, created_at, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT(evaluation_id) DO UPDATE SET
                    tenant_id=excluded.tenant_id, suite=excluded.suite, status=excluded.status,
                    total=excluded.total, passed=excluded.passed, failed=excluded.failed,
                    pass_rate=excluded.pass_rate, created_at=excluded.created_at, payload=excluded.payload
            """, (payload["evaluation_id"], tenant_id, payload["suite"], payload["status"],
                  payload["total"], payload["passed"], payload["failed"], payload["pass_rate"],
                  created_at, json.dumps(payload, separators=(",", ":"))))
        else:
            conn.execute("""
                INSERT INTO evaluation_runs
                (evaluation_id, tenant_id, suite, status, total, passed, failed, pass_rate, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(evaluation_id) DO UPDATE SET
                    tenant_id=excluded.tenant_id, suite=excluded.suite, status=excluded.status,
                    total=excluded.total, passed=excluded.passed, failed=excluded.failed,
                    pass_rate=excluded.pass_rate, created_at=excluded.created_at, payload=excluded.payload
            """, (payload["evaluation_id"], tenant_id, payload["suite"], payload["status"],
                  payload["total"], payload["passed"], payload["failed"], payload["pass_rate"],
                  created_at, json.dumps(payload, separators=(",", ":"))))
    return {"evaluation_id": payload["evaluation_id"], "created_at": created_at}


def list_evaluations(limit: int = 20, offset: int = 0, tenant_id: str = "local") -> dict[str, Any]:
    initialize_store()
    with _connect() as conn:
        marker = "%s" if _is_postgres(conn) else "?"
        total = conn.execute(f"SELECT COUNT(*) AS count FROM evaluation_runs WHERE tenant_id = {marker}", (tenant_id,)).fetchone()
        rows = conn.execute(f"""
            SELECT evaluation_id, suite, status, total, passed, failed, pass_rate, created_at
            FROM evaluation_runs WHERE tenant_id = {marker}
            ORDER BY created_at DESC, evaluation_id DESC LIMIT {marker} OFFSET {marker}
        """, (tenant_id, limit, offset)).fetchall()
    count = total["count"] if isinstance(total, dict) or hasattr(total, "keys") else total[0]
    return {"total": count, "limit": limit, "offset": offset, "items": [dict(row) for row in rows]}


def get_evaluation(evaluation_id: str, tenant_id: str = "local") -> dict[str, Any] | None:
    initialize_store()
    with _connect() as conn:
        marker = "%s" if _is_postgres(conn) else "?"
        row = conn.execute(
            f"SELECT payload, created_at FROM evaluation_runs WHERE evaluation_id = {marker} AND tenant_id = {marker}",
            (evaluation_id, tenant_id),
        ).fetchone()
    if row is None:
        return None
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {"created_at": row["created_at"], "result": payload}
