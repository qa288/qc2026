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
    Migration(
        version=3,
        name="runtime_config_overrides",
        sql="""
        CREATE TABLE IF NOT EXISTS runtime_config_overrides (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            customer_center_id TEXT NOT NULL DEFAULT '',
            refresh_token TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        """,
    ),
    Migration(
        version=4,
        name="customer_center_scoped_snapshots",
        sql="SELECT 1;",
    ),
    Migration(
        version=5,
        name="comment_storage",
        sql="""
        CREATE TABLE IF NOT EXISTS comment_records (
            customer_center_id TEXT NOT NULL DEFAULT '',
            advertiser_id BIGINT NOT NULL,
            comment_id TEXT NOT NULL,
            comment_date TEXT NOT NULL DEFAULT '',
            create_time TEXT NOT NULL DEFAULT '',
            advertiser_name TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '',
            reply_count INTEGER NOT NULL DEFAULT 0,
            hide_status TEXT NOT NULL DEFAULT 'NOT_HIDE',
            level_type TEXT NOT NULL DEFAULT '',
            comment_user_name TEXT NOT NULL DEFAULT '',
            comment_user_id TEXT NOT NULL DEFAULT '',
            like_count INTEGER NOT NULL DEFAULT 0,
            item_title TEXT NOT NULL DEFAULT '',
            comment_type TEXT NOT NULL DEFAULT '',
            promotion_id TEXT NOT NULL DEFAULT '',
            material_id TEXT NOT NULL DEFAULT '',
            item_id TEXT NOT NULL DEFAULT '',
            raw_json TEXT NOT NULL DEFAULT '{}',
            fetched_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (customer_center_id, advertiser_id, comment_id)
        );
        CREATE INDEX IF NOT EXISTS idx_comment_records_cc_date_adv
        ON comment_records (customer_center_id, comment_date, advertiser_id, create_time);
        CREATE INDEX IF NOT EXISTS idx_comment_records_cc_promotion
        ON comment_records (customer_center_id, advertiser_id, promotion_id);
        CREATE INDEX IF NOT EXISTS idx_comment_records_cc_material
        ON comment_records (customer_center_id, advertiser_id, material_id);

        CREATE TABLE IF NOT EXISTS comment_sync_states (
            customer_center_id TEXT NOT NULL DEFAULT '',
            advertiser_id BIGINT NOT NULL,
            sync_date TEXT NOT NULL,
            advertiser_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            comment_count INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT NOT NULL DEFAULT '',
            last_success_at TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (customer_center_id, advertiser_id, sync_date)
        );
        CREATE INDEX IF NOT EXISTS idx_comment_sync_states_cc_date_adv
        ON comment_sync_states (customer_center_id, sync_date, advertiser_id);
        """,
    ),
    Migration(
        version=6,
        name="comment_storage_bigint",
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
