"""Small durable SQLite store for completed Cognis evaluation runs.

SQLite is appropriate for local/single-instance deployments. Use PostgreSQL
before horizontal scaling or multi-tenant production traffic.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "cognis.db"


def _connect() -> sqlite3.Connection:
    configured = os.getenv("COGNIS_DATABASE_PATH", str(DEFAULT_DB))
    path = Path(configured)
    if configured != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def initialize_store() -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_runs (
                evaluation_id TEXT PRIMARY KEY,
                suite TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('passed', 'failed')),
                total INTEGER NOT NULL CHECK(total >= 0),
                passed INTEGER NOT NULL CHECK(passed >= 0),
                failed INTEGER NOT NULL CHECK(failed >= 0),
                pass_rate REAL NOT NULL CHECK(pass_rate >= 0 AND pass_rate <= 1),
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_evaluation_runs_created "
            "ON evaluation_runs(created_at DESC)"
        )


def save_evaluation(result: Any) -> dict[str, Any]:
    """Persist a validated Pydantic evaluation response and return its metadata."""
    initialize_store()
    payload = result.model_dump(mode="json")
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO evaluation_runs
            (evaluation_id, suite, status, total, passed, failed, pass_rate, created_at, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(evaluation_id) DO UPDATE SET
                suite=excluded.suite, status=excluded.status, total=excluded.total,
                passed=excluded.passed, failed=excluded.failed,
                pass_rate=excluded.pass_rate, payload=excluded.payload
            """,
            (
                payload["evaluation_id"], payload["suite"], payload["status"],
                payload["total"], payload["passed"], payload["failed"],
                payload["pass_rate"], created_at, json.dumps(payload, separators=(",", ":")),
            ),
        )
    return {"evaluation_id": payload["evaluation_id"], "created_at": created_at}


def list_evaluations(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    initialize_store()
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM evaluation_runs").fetchone()[0]
        rows = conn.execute(
            """
            SELECT evaluation_id, suite, status, total, passed, failed, pass_rate, created_at
            FROM evaluation_runs ORDER BY created_at DESC, evaluation_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "items": [dict(row) for row in rows]}


def get_evaluation(evaluation_id: str) -> dict[str, Any] | None:
    initialize_store()
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload, created_at FROM evaluation_runs WHERE evaluation_id = ?",
            (evaluation_id,),
        ).fetchone()
    if row is None:
        return None
    return {"created_at": row["created_at"], "result": json.loads(row["payload"])}
