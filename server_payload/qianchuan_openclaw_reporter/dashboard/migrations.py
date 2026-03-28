from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dashboard.schema import BASE_SCHEMA_SQL


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, name="base_schema", sql=BASE_SCHEMA_SQL),
    # The actual cross-backend column backfill runs in Service.init_db via _ensure_column_locked.
    # This migration only advances the recorded schema version for upgraded databases.
    Migration(
        version=2,
        name="material_create_time",
        sql="SELECT 1;",
    ),
)


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_migrations_table(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def migrations_table_exists(conn: Any) -> bool:
    if getattr(conn, "backend", "") == "postgres":
        row = conn.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'schema_migrations'
            LIMIT 1
            """
        ).fetchone()
        return bool(row)
    rows = conn.execute("PRAGMA table_info(schema_migrations)").fetchall()
    return bool(rows)


def applied_versions(conn: Any) -> set[int]:
    ensure_migrations_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC").fetchall()
    return {int(row["version"]) for row in rows}


def apply_migrations(conn: Any) -> list[dict[str, Any]]:
    applied = applied_versions(conn)
    executed: list[dict[str, Any]] = []
    for migration in MIGRATIONS:
        if migration.version in applied:
            continue
        conn.executescript(migration.sql)
        applied_at = _now_text()
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (migration.version, migration.name, applied_at),
        )
        executed.append(
            {
                "version": migration.version,
                "name": migration.name,
                "applied_at": applied_at,
            }
        )
    return executed


def current_schema_version(conn: Any) -> int:
    if not migrations_table_exists(conn):
        return 0
    row = conn.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
    if not row:
        return 0
    version = row["version"]
    return int(version or 0)


def available_schema_version() -> int:
    if not MIGRATIONS:
        return 0
    return max(item.version for item in MIGRATIONS)
