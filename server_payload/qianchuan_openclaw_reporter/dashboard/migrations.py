from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import inspect
from typing import Any, Callable

from dashboard.schema import BASE_SCHEMA_SQL


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str = ""
    apply_fn: Callable[..., None] | None = None


def _column_exists(conn: Any, table_name: str, column_name: str) -> bool:
    table = str(table_name or "").strip()
    column = str(column_name or "").strip()
    if not table or not column:
        return False
    if getattr(conn, "backend", "") == "postgres":
        row = conn.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
            LIMIT 1
            """,
            (table, column),
        ).fetchone()
        return bool(row)
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row["name"]) == column for row in rows)


def _table_exists(conn: Any, table_name: str) -> bool:
    table = str(table_name or "").strip()
    if not table:
        return False
    if getattr(conn, "backend", "") == "postgres":
        row = conn.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            LIMIT 1
            """,
            (table,),
        ).fetchone()
        return bool(row)
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table,),
    ).fetchone()
    return bool(row)


def _column_type(conn: Any, table_name: str, column_name: str) -> str:
    table = str(table_name or "").strip()
    column = str(column_name or "").strip()
    if not table or not column:
        return ""
    if getattr(conn, "backend", "") == "postgres":
        row = conn.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
            LIMIT 1
            """,
            (table, column),
        ).fetchone()
        return str(row["data_type"] or "").strip().lower() if row else ""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    for row in rows:
        if str(row["name"]) == column:
            return str(row["type"] or "").strip().lower()
    return ""


def _ensure_column(conn: Any, table_name: str, column_name: str, definition: str) -> None:
    if _column_exists(conn, table_name, column_name):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _ensure_bigint_column(conn: Any, table_name: str, column_name: str) -> None:
    if getattr(conn, "backend", "") != "postgres":
        return
    current_type = _column_type(conn, table_name, column_name)
    if current_type in {"integer", "int", "int4", "smallint", "int2"}:
        conn.execute(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE BIGINT")


def _ensure_performance_daily_read_models(conn: Any) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS summary_daily (
            customer_center_id TEXT NOT NULL DEFAULT '',
            biz_date TEXT NOT NULL,
            snapshot_time TEXT NOT NULL,
            account_count INTEGER NOT NULL,
            active_account_count INTEGER NOT NULL,
            plan_count INTEGER NOT NULL,
            active_plan_count INTEGER NOT NULL,
            stat_cost REAL NOT NULL,
            pay_amount REAL NOT NULL,
            order_count INTEGER NOT NULL,
            roi REAL NOT NULL,
            account_failures INTEGER NOT NULL,
            plan_failures INTEGER NOT NULL,
            PRIMARY KEY (customer_center_id, biz_date)
        );
        CREATE TABLE IF NOT EXISTS account_daily (
            customer_center_id TEXT NOT NULL DEFAULT '',
            biz_date TEXT NOT NULL,
            snapshot_time TEXT NOT NULL,
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            stat_cost REAL NOT NULL,
            roi REAL NOT NULL,
            order_count INTEGER NOT NULL,
            pay_amount REAL NOT NULL,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            settled_roi REAL NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            pay_order_cost REAL NOT NULL DEFAULT 0,
            settled_amount_rate REAL NOT NULL DEFAULT 0,
            refund_rate_1h REAL NOT NULL DEFAULT 0,
            refund_amount_1h REAL NOT NULL DEFAULT 0,
            plan_count INTEGER NOT NULL DEFAULT 0,
            ok INTEGER NOT NULL,
            error TEXT,
            PRIMARY KEY (customer_center_id, biz_date, advertiser_id)
        );
        CREATE TABLE IF NOT EXISTS plan_daily (
            customer_center_id TEXT NOT NULL DEFAULT '',
            biz_date TEXT NOT NULL,
            snapshot_time TEXT NOT NULL,
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            ad_id BIGINT NOT NULL,
            ad_name TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            anchor_name TEXT NOT NULL,
            marketing_goal TEXT NOT NULL,
            plan_source TEXT NOT NULL DEFAULT 'UNI_PROMOTION',
            plan_delivery_type TEXT NOT NULL DEFAULT 'GLOBAL',
            status TEXT NOT NULL,
            opt_status TEXT NOT NULL,
            roi_goal REAL NOT NULL,
            stat_cost REAL NOT NULL,
            roi REAL NOT NULL,
            order_count INTEGER NOT NULL,
            pay_amount REAL NOT NULL,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            settled_roi REAL NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            pay_order_cost REAL NOT NULL DEFAULT 0,
            settled_amount_rate REAL NOT NULL DEFAULT 0,
            refund_rate_1h REAL NOT NULL DEFAULT 0,
            refund_amount_1h REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (customer_center_id, biz_date, ad_id)
        );
        CREATE INDEX IF NOT EXISTS idx_summary_daily_date_cc
        ON summary_daily (biz_date, customer_center_id);
        CREATE INDEX IF NOT EXISTS idx_account_daily_date_cc_adv
        ON account_daily (biz_date, customer_center_id, advertiser_id);
        CREATE INDEX IF NOT EXISTS idx_plan_daily_date_cc_plan
        ON plan_daily (biz_date, customer_center_id, ad_id);
        """
    )


def _material_metric_sort_partial_indexes(conn: Any) -> None:
    index_statements = (
        """
        CREATE INDEX IF NOT EXISTS idx_material_current_stat_cost_nonzero
        ON material_current (customer_center_id, stat_cost DESC, material_key)
        WHERE stat_cost > 0
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_material_current_total_pay_nonzero
        ON material_current (customer_center_id, total_pay_amount DESC, material_key)
        WHERE total_pay_amount > 0
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_material_current_settled_pay_nonzero
        ON material_current (customer_center_id, settled_pay_amount DESC, material_key)
        WHERE settled_pay_amount > 0
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_material_current_pay_nonzero
        ON material_current (customer_center_id, pay_amount DESC, material_key)
        WHERE pay_amount > 0
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_material_current_order_nonzero
        ON material_current (customer_center_id, order_count DESC, material_key)
        WHERE order_count > 0
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_material_daily_stat_cost_nonzero
        ON material_daily (biz_date, customer_center_id, stat_cost DESC, material_key)
        WHERE stat_cost > 0
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_material_daily_total_pay_nonzero
        ON material_daily (biz_date, customer_center_id, total_pay_amount DESC, material_key)
        WHERE total_pay_amount > 0
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_material_daily_settled_pay_nonzero
        ON material_daily (biz_date, customer_center_id, settled_pay_amount DESC, material_key)
        WHERE settled_pay_amount > 0
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_material_daily_pay_nonzero
        ON material_daily (biz_date, customer_center_id, pay_amount DESC, material_key)
        WHERE pay_amount > 0
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_material_daily_order_nonzero
        ON material_daily (biz_date, customer_center_id, order_count DESC, material_key)
        WHERE order_count > 0
        """,
    )
    for statement in index_statements:
        conn.execute(statement)


def _legacy_schema_backfill(conn: Any) -> None:
    _ensure_column(conn, "app_users", "upload_materials_enabled", "INTEGER NOT NULL DEFAULT 0")

    _ensure_column(conn, "account_snapshots", "total_pay_amount", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "account_snapshots", "settled_pay_amount", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "account_snapshots", "settled_roi", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "account_snapshots", "settled_order_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "account_snapshots", "pay_order_cost", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "account_snapshots", "settled_amount_rate", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "account_snapshots", "refund_rate_1h", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "account_snapshots", "refund_amount_1h", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "account_snapshots", "plan_count", "INTEGER NOT NULL DEFAULT 0")

    _ensure_column(conn, "plan_snapshots", "plan_source", "TEXT NOT NULL DEFAULT 'UNI_PROMOTION'")
    _ensure_column(conn, "plan_snapshots", "plan_delivery_type", "TEXT NOT NULL DEFAULT 'GLOBAL'")
    _ensure_column(conn, "plan_snapshots", "raw_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "plan_snapshots", "total_pay_amount", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "plan_snapshots", "settled_pay_amount", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "plan_snapshots", "settled_roi", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "plan_snapshots", "settled_order_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "plan_snapshots", "pay_order_cost", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "plan_snapshots", "settled_amount_rate", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "plan_snapshots", "refund_rate_1h", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "plan_snapshots", "refund_amount_1h", "REAL NOT NULL DEFAULT 0")

    _ensure_column(conn, "material_upload_jobs", "task_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_upload_jobs", "processed_files", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_upload_jobs", "success_files", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_upload_jobs", "failed_files", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_upload_jobs", "started_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_upload_jobs", "completed_at", "TEXT NOT NULL DEFAULT ''")

    _ensure_column(conn, "material_upload_job_files", "file_sha256", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_upload_job_files", "file_md5", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_upload_job_files", "processed_advertisers", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_upload_job_files", "success_advertisers", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_upload_job_files", "failed_advertisers", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_upload_job_files", "material_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_upload_job_files", "video_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_upload_job_files", "video_url", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_upload_job_files", "message", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_upload_job_files", "updated_at", "TEXT NOT NULL DEFAULT ''")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_upload_job_target_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            file_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES material_upload_jobs(id),
            FOREIGN KEY(target_id) REFERENCES material_upload_job_targets(id),
            FOREIGN KEY(file_id) REFERENCES material_upload_job_files(id)
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_material_upload_job_target_assets_unique
        ON material_upload_job_target_assets (job_id, target_id, file_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_upload_job_target_assets_job
        ON material_upload_job_target_assets (job_id, target_id, file_id, status)
        """
    )

    for table_name in ("material_snapshots", "material_rollups"):
        _ensure_column(conn, table_name, "create_time", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, table_name, "cover_url", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, table_name, "aweme_item_id", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, table_name, "video_url", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, table_name, "total_pay_amount", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, table_name, "settled_pay_amount", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, table_name, "settled_order_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "top_anchor_name", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_rollups", "product_info_text", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_rollups", "product_names_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "material_rollups", "overall_show_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "overall_click_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "overall_ctr", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "settled_roi", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "pay_order_cost", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "settled_amount_rate", "REAL NOT NULL DEFAULT 0")

    conn.execute(
        """
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
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_comment_records_cc_date_adv
        ON comment_records (customer_center_id, comment_date, advertiser_id, create_time)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_comment_records_cc_promotion
        ON comment_records (customer_center_id, advertiser_id, promotion_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_comment_records_cc_material
        ON comment_records (customer_center_id, advertiser_id, material_id)
        """
    )
    conn.execute(
        """
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
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_comment_sync_states_cc_date_adv
        ON comment_sync_states (customer_center_id, sync_date, advertiser_id)
        """
    )
    _ensure_bigint_column(conn, "comment_records", "advertiser_id")
    _ensure_bigint_column(conn, "comment_sync_states", "advertiser_id")


def _customer_center_scope_schema_backfill(conn: Any) -> None:
    table_names = (
        "summary_snapshots",
        "account_snapshots",
        "plan_snapshots",
        "plan_detail_snapshots",
        "product_snapshots",
        "material_snapshots",
        "material_rollups",
        "video_origin_flags",
        "extended_sync_runs",
        "account_balances",
        "shared_wallets",
        "shared_wallet_account_relations",
    )
    for table_name in table_names:
        _ensure_column(conn, table_name, "customer_center_id", "TEXT NOT NULL DEFAULT ''")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_summary_snapshots_cc_time ON summary_snapshots (customer_center_id, snapshot_time)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_account_snapshots_cc_adv_time ON account_snapshots (customer_center_id, advertiser_id, snapshot_time)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_plan_snapshots_cc_plan_time ON plan_snapshots (customer_center_id, ad_id, snapshot_time)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_plan_detail_snapshots_cc_plan_time ON plan_detail_snapshots (customer_center_id, ad_id, snapshot_time)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_snapshots_cc_plan_time ON product_snapshots (customer_center_id, ad_id, snapshot_time)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_material_snapshots_cc_plan_time ON material_snapshots (customer_center_id, ad_id, snapshot_time)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_material_rollups_cc_snapshot_time ON material_rollups (customer_center_id, snapshot_time)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_video_origin_flags_cc_material_time ON video_origin_flags (customer_center_id, material_id, snapshot_time)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_extended_sync_runs_cc_time ON extended_sync_runs (customer_center_id, snapshot_time)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_account_balances_cc_adv_time ON account_balances (customer_center_id, advertiser_id, snapshot_time)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shared_wallets_cc_time ON shared_wallets (customer_center_id, snapshot_time)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shared_wallet_relations_cc_time ON shared_wallet_account_relations (customer_center_id, snapshot_time)"
    )


def _history_backfill_jobs_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history_backfill_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_key TEXT NOT NULL,
            kind TEXT NOT NULL,
            task_name TEXT NOT NULL,
            range_start TEXT NOT NULL DEFAULT '',
            range_end TEXT NOT NULL DEFAULT '',
            days INTEGER NOT NULL DEFAULT 0,
            requested_missing_days INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'queued',
            task_id TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            result_json TEXT NOT NULL DEFAULT '{}',
            queued_at TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_history_backfill_jobs_job_key
        ON history_backfill_jobs (job_key)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_history_backfill_jobs_kind_status_updated
        ON history_backfill_jobs (kind, status, updated_at)
        """
    )


def _plan_refresh_schedule_fields_schema(conn: Any) -> None:
    _ensure_column(conn, "plan_refresh_states", "last_warm_sync_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "plan_refresh_states", "next_cold_due_at", "TEXT NOT NULL DEFAULT ''")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_plan_refresh_states_cc_next_cold_due
        ON plan_refresh_states (customer_center_id, next_cold_due_at, ad_id)
        """
    )


def _plan_refresh_error_backoff_fields_schema(conn: Any) -> None:
    _ensure_column(conn, "plan_refresh_states", "last_material_error_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "plan_refresh_states", "last_material_error_code", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "plan_refresh_states", "last_material_error_message", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "plan_refresh_states", "last_material_error_retryable", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "plan_refresh_states", "consecutive_material_error_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "plan_refresh_states", "next_material_retry_at", "TEXT NOT NULL DEFAULT ''")


def _material_relation_edges_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_relation_edges (
            customer_center_id TEXT NOT NULL DEFAULT '',
            material_key TEXT NOT NULL,
            material_id TEXT NOT NULL DEFAULT '',
            advertiser_id BIGINT NOT NULL DEFAULT 0,
            advertiser_name TEXT NOT NULL DEFAULT '',
            ad_id BIGINT NOT NULL DEFAULT 0,
            ad_name TEXT NOT NULL DEFAULT '',
            first_seen_at TEXT NOT NULL DEFAULT '',
            last_seen_at TEXT NOT NULL DEFAULT '',
            last_snapshot_time TEXT NOT NULL DEFAULT '',
            seen_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (customer_center_id, material_key, advertiser_id, ad_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_relation_edges_cc_material
        ON material_relation_edges (customer_center_id, material_key, last_seen_at DESC, advertiser_id, ad_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_relation_edges_cc_advertiser
        ON material_relation_edges (customer_center_id, advertiser_id, last_seen_at DESC, material_key)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_relation_edges_cc_ad
        ON material_relation_edges (customer_center_id, ad_id, last_seen_at DESC, material_key)
        """
    )


def _material_relation_read_model_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_relation_current (
            customer_center_id TEXT NOT NULL DEFAULT '',
            snapshot_time TEXT NOT NULL,
            window_start TEXT NOT NULL DEFAULT '',
            window_end TEXT NOT NULL DEFAULT '',
            advertiser_id BIGINT NOT NULL DEFAULT 0,
            advertiser_name TEXT NOT NULL DEFAULT '',
            ad_id BIGINT NOT NULL DEFAULT 0,
            ad_name TEXT NOT NULL DEFAULT '',
            material_type TEXT NOT NULL DEFAULT '',
            material_key TEXT NOT NULL,
            material_id TEXT NOT NULL DEFAULT '',
            material_name TEXT NOT NULL DEFAULT '',
            create_time TEXT NOT NULL DEFAULT '',
            video_id TEXT NOT NULL DEFAULT '',
            cover_url TEXT NOT NULL DEFAULT '',
            aweme_item_id TEXT NOT NULL DEFAULT '',
            video_url TEXT NOT NULL DEFAULT '',
            stat_cost REAL NOT NULL DEFAULT 0,
            pay_amount REAL NOT NULL DEFAULT 0,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            order_count INTEGER NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            overall_show_count INTEGER NOT NULL DEFAULT 0,
            overall_click_count INTEGER NOT NULL DEFAULT 0,
            top_anchor_name TEXT NOT NULL DEFAULT '',
            product_info_text TEXT NOT NULL DEFAULT '',
            is_original INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (customer_center_id, advertiser_id, ad_id, material_type, material_key)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_relation_current_snapshot
        ON material_relation_current (snapshot_time, customer_center_id, material_key)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_relation_daily (
            customer_center_id TEXT NOT NULL DEFAULT '',
            biz_date TEXT NOT NULL,
            snapshot_time TEXT NOT NULL,
            window_start TEXT NOT NULL DEFAULT '',
            window_end TEXT NOT NULL DEFAULT '',
            advertiser_id BIGINT NOT NULL DEFAULT 0,
            advertiser_name TEXT NOT NULL DEFAULT '',
            ad_id BIGINT NOT NULL DEFAULT 0,
            ad_name TEXT NOT NULL DEFAULT '',
            material_type TEXT NOT NULL DEFAULT '',
            material_key TEXT NOT NULL,
            material_id TEXT NOT NULL DEFAULT '',
            material_name TEXT NOT NULL DEFAULT '',
            create_time TEXT NOT NULL DEFAULT '',
            video_id TEXT NOT NULL DEFAULT '',
            cover_url TEXT NOT NULL DEFAULT '',
            aweme_item_id TEXT NOT NULL DEFAULT '',
            video_url TEXT NOT NULL DEFAULT '',
            stat_cost REAL NOT NULL DEFAULT 0,
            pay_amount REAL NOT NULL DEFAULT 0,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            order_count INTEGER NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            overall_show_count INTEGER NOT NULL DEFAULT 0,
            overall_click_count INTEGER NOT NULL DEFAULT 0,
            top_anchor_name TEXT NOT NULL DEFAULT '',
            product_info_text TEXT NOT NULL DEFAULT '',
            is_original INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (customer_center_id, biz_date, advertiser_id, ad_id, material_type, material_key)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_relation_daily_date
        ON material_relation_daily (biz_date, customer_center_id, material_key)
        """
    )


def _material_name_lookup_indexes(conn: Any) -> None:
    if getattr(conn, "backend", "") == "postgres":
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_material_current_name_trgm
            ON material_current USING gin (LOWER(material_name) gin_trgm_ops)
            WHERE COALESCE(material_name, '') <> ''
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_material_daily_name_trgm
            ON material_daily USING gin (LOWER(material_name) gin_trgm_ops)
            WHERE COALESCE(material_name, '') <> ''
            """
        )
        return
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_current_name
        ON material_current (material_name)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_daily_date_name
        ON material_daily (biz_date, material_name)
        """
    )


def _material_snapshot_primary_key_with_advertiser(conn: Any) -> None:
    _rebuild_table_with_schema(
        conn,
        "material_snapshots",
        """
        CREATE TABLE {table_name} (
            snapshot_time TEXT NOT NULL,
            customer_center_id TEXT NOT NULL DEFAULT '',
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            ad_id BIGINT NOT NULL,
            ad_name TEXT NOT NULL,
            material_type TEXT NOT NULL,
            material_key TEXT NOT NULL,
            material_id TEXT NOT NULL,
            material_name TEXT NOT NULL,
            create_time TEXT NOT NULL DEFAULT '',
            video_id TEXT NOT NULL DEFAULT '',
            cover_url TEXT NOT NULL DEFAULT '',
            aweme_item_id TEXT NOT NULL DEFAULT '',
            video_url TEXT NOT NULL DEFAULT '',
            product_show_count INTEGER NOT NULL DEFAULT 0,
            product_click_count INTEGER NOT NULL DEFAULT 0,
            stat_cost REAL NOT NULL DEFAULT 0,
            pay_amount REAL NOT NULL DEFAULT 0,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            order_count INTEGER NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            roi REAL NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (customer_center_id, snapshot_time, advertiser_id, ad_id, material_type, material_key)
        )
        """,
        [
            "snapshot_time",
            "customer_center_id",
            "window_start",
            "window_end",
            "advertiser_id",
            "advertiser_name",
            "ad_id",
            "ad_name",
            "material_type",
            "material_key",
            "material_id",
            "material_name",
            "create_time",
            "video_id",
            "cover_url",
            "aweme_item_id",
            "video_url",
            "product_show_count",
            "product_click_count",
            "stat_cost",
            "pay_amount",
            "total_pay_amount",
            "settled_pay_amount",
            "order_count",
            "settled_order_count",
            "roi",
            "raw_json",
        ],
    )


def _customer_center_scope_data_backfill(
    conn: Any,
    context: dict[str, Any] | None = None,
) -> None:
    table_names = (
        "summary_snapshots",
        "account_snapshots",
        "plan_snapshots",
        "plan_detail_snapshots",
        "product_snapshots",
        "material_snapshots",
        "material_rollups",
        "video_origin_flags",
        "extended_sync_runs",
        "account_balances",
        "shared_wallets",
        "shared_wallet_account_relations",
    )
    runtime_override: dict[str, Any] = {}
    if _table_exists(conn, "runtime_config_overrides"):
        row = conn.execute(
            """
            SELECT customer_center_id, updated_at
            FROM runtime_config_overrides
            WHERE id = 1
            LIMIT 1
            """
        ).fetchone()
        runtime_override = dict(row) if row else {}

    base_customer_center_id = str((context or {}).get("base_customer_center_id") or "").strip()
    override_customer_center_id = str(runtime_override.get("customer_center_id") or "").strip()
    override_updated_at = str(runtime_override.get("updated_at") or "").strip()
    fallback_customer_center_id = override_customer_center_id or base_customer_center_id
    if not fallback_customer_center_id:
        return

    for table_name in table_names:
        if not _table_exists(conn, table_name):
            continue
        if override_customer_center_id and override_customer_center_id != base_customer_center_id and override_updated_at:
            if base_customer_center_id:
                conn.execute(
                    f"""
                    UPDATE {table_name}
                    SET customer_center_id = ?
                    WHERE COALESCE(customer_center_id, '') = ''
                      AND snapshot_time < ?
                    """,
                    (base_customer_center_id, override_updated_at),
                )
            conn.execute(
                f"""
                UPDATE {table_name}
                SET customer_center_id = ?
                WHERE COALESCE(customer_center_id, '') = ''
                  AND snapshot_time >= ?
                """,
                (override_customer_center_id, override_updated_at),
            )
        if base_customer_center_id:
            conn.execute(
                f"""
                UPDATE {table_name}
                SET customer_center_id = ?
                WHERE COALESCE(customer_center_id, '') = ''
                """,
                (base_customer_center_id,),
            )
        else:
            conn.execute(
                f"""
                UPDATE {table_name}
                SET customer_center_id = ?
                WHERE COALESCE(customer_center_id, '') = ''
                """,
                (fallback_customer_center_id,),
            )


def _rebuild_table_with_schema(
    conn: Any,
    table_name: str,
    create_sql: str,
    column_names: list[str],
) -> None:
    temp_table_name = f"{table_name}__v10"
    conn.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
    conn.execute(create_sql.replace("{table_name}", temp_table_name))
    columns_sql = ", ".join(column_names)
    conn.execute(f"INSERT INTO {temp_table_name} ({columns_sql}) SELECT {columns_sql} FROM {table_name}")
    conn.execute(f"DROP TABLE {table_name}")
    conn.execute(f"ALTER TABLE {temp_table_name} RENAME TO {table_name}")


def _ensure_snapshot_table_indexes(conn: Any) -> None:
    index_statements = (
        "CREATE INDEX IF NOT EXISTS idx_account_snapshots_adv_time ON account_snapshots (advertiser_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_summary_snapshots_cc_time ON summary_snapshots (customer_center_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_account_snapshots_cc_adv_time ON account_snapshots (customer_center_id, advertiser_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_plan_snapshots_plan_time ON plan_snapshots (ad_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_plan_snapshots_cc_plan_time ON plan_snapshots (customer_center_id, ad_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_plan_detail_snapshots_plan_time ON plan_detail_snapshots (ad_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_plan_detail_snapshots_cc_plan_time ON plan_detail_snapshots (customer_center_id, ad_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_product_snapshots_plan_time ON product_snapshots (ad_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_product_snapshots_cc_plan_time ON product_snapshots (customer_center_id, ad_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_product_snapshots_product_time ON product_snapshots (product_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_material_snapshots_plan_time ON material_snapshots (ad_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_material_snapshots_cc_plan_time ON material_snapshots (customer_center_id, ad_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_material_snapshots_material_time ON material_snapshots (material_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_material_rollups_snapshot_time ON material_rollups (snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_material_rollups_cc_snapshot_time ON material_rollups (customer_center_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_video_origin_flags_material_time ON video_origin_flags (material_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_video_origin_flags_cc_material_time ON video_origin_flags (customer_center_id, material_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_extended_sync_runs_cc_time ON extended_sync_runs (customer_center_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_account_balances_adv_time ON account_balances (advertiser_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_account_balances_cc_adv_time ON account_balances (customer_center_id, advertiser_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_shared_wallets_wallet_time ON shared_wallets (main_wallet_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_shared_wallets_cc_time ON shared_wallets (customer_center_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_shared_wallet_account_rel_wallet_adv ON shared_wallet_account_relations (main_wallet_id, advertiser_id, snapshot_time)",
        "CREATE INDEX IF NOT EXISTS idx_shared_wallet_relations_cc_time ON shared_wallet_account_relations (customer_center_id, snapshot_time)",
    )
    for statement in index_statements:
        conn.execute(statement)


def _snapshot_composite_primary_keys(conn: Any) -> None:
    _rebuild_table_with_schema(
        conn,
        "summary_snapshots",
        """
        CREATE TABLE {table_name} (
            customer_center_id TEXT NOT NULL DEFAULT '',
            snapshot_time TEXT NOT NULL,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            account_count INTEGER NOT NULL,
            active_account_count INTEGER NOT NULL,
            plan_count INTEGER NOT NULL,
            active_plan_count INTEGER NOT NULL,
            stat_cost REAL NOT NULL,
            pay_amount REAL NOT NULL,
            order_count INTEGER NOT NULL,
            roi REAL NOT NULL,
            account_failures INTEGER NOT NULL,
            plan_failures INTEGER NOT NULL,
            PRIMARY KEY (customer_center_id, snapshot_time)
        )
        """,
        [
            "customer_center_id",
            "snapshot_time",
            "window_start",
            "window_end",
            "account_count",
            "active_account_count",
            "plan_count",
            "active_plan_count",
            "stat_cost",
            "pay_amount",
            "order_count",
            "roi",
            "account_failures",
            "plan_failures",
        ],
    )
    _rebuild_table_with_schema(
        conn,
        "account_snapshots",
        """
        CREATE TABLE {table_name} (
            snapshot_time TEXT NOT NULL,
            customer_center_id TEXT NOT NULL DEFAULT '',
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            stat_cost REAL NOT NULL,
            roi REAL NOT NULL,
            order_count INTEGER NOT NULL,
            pay_amount REAL NOT NULL,
            ok INTEGER NOT NULL,
            error TEXT,
            PRIMARY KEY (customer_center_id, snapshot_time, advertiser_id)
        )
        """,
        [
            "snapshot_time",
            "customer_center_id",
            "advertiser_id",
            "advertiser_name",
            "stat_cost",
            "roi",
            "order_count",
            "pay_amount",
            "ok",
            "error",
        ],
    )
    _rebuild_table_with_schema(
        conn,
        "plan_snapshots",
        """
        CREATE TABLE {table_name} (
            snapshot_time TEXT NOT NULL,
            customer_center_id TEXT NOT NULL DEFAULT '',
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            ad_id BIGINT NOT NULL,
            ad_name TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            anchor_name TEXT NOT NULL,
            marketing_goal TEXT NOT NULL,
            plan_source TEXT NOT NULL DEFAULT 'UNI_PROMOTION',
            plan_delivery_type TEXT NOT NULL DEFAULT 'GLOBAL',
            status TEXT NOT NULL,
            opt_status TEXT NOT NULL,
            roi_goal REAL NOT NULL,
            stat_cost REAL NOT NULL,
            roi REAL NOT NULL,
            order_count INTEGER NOT NULL,
            pay_amount REAL NOT NULL,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            settled_roi REAL NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            pay_order_cost REAL NOT NULL DEFAULT 0,
            settled_amount_rate REAL NOT NULL DEFAULT 0,
            refund_rate_1h REAL NOT NULL DEFAULT 0,
            refund_amount_1h REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (customer_center_id, snapshot_time, ad_id)
        )
        """,
        [
            "snapshot_time",
            "customer_center_id",
            "advertiser_id",
            "advertiser_name",
            "ad_id",
            "ad_name",
            "product_id",
            "product_name",
            "anchor_name",
            "marketing_goal",
            "plan_source",
            "plan_delivery_type",
            "status",
            "opt_status",
            "roi_goal",
            "stat_cost",
            "roi",
            "order_count",
            "pay_amount",
            "total_pay_amount",
            "settled_pay_amount",
            "settled_roi",
            "settled_order_count",
            "pay_order_cost",
            "settled_amount_rate",
            "refund_rate_1h",
            "refund_amount_1h",
        ],
    )
    _rebuild_table_with_schema(
        conn,
        "plan_detail_snapshots",
        """
        CREATE TABLE {table_name} (
            snapshot_time TEXT NOT NULL,
            customer_center_id TEXT NOT NULL DEFAULT '',
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            ad_id BIGINT NOT NULL,
            ad_name TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            anchor_name TEXT NOT NULL,
            marketing_goal TEXT NOT NULL,
            status TEXT NOT NULL,
            opt_status TEXT NOT NULL,
            roi_goal REAL NOT NULL,
            modify_time TEXT NOT NULL DEFAULT '',
            product_count INTEGER NOT NULL DEFAULT 0,
            room_count INTEGER NOT NULL DEFAULT 0,
            has_delivery_setting INTEGER NOT NULL DEFAULT 0,
            has_creative_setting INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (customer_center_id, snapshot_time, ad_id)
        )
        """,
        [
            "snapshot_time",
            "customer_center_id",
            "advertiser_id",
            "advertiser_name",
            "ad_id",
            "ad_name",
            "product_id",
            "product_name",
            "anchor_name",
            "marketing_goal",
            "status",
            "opt_status",
            "roi_goal",
            "modify_time",
            "product_count",
            "room_count",
            "has_delivery_setting",
            "has_creative_setting",
            "raw_json",
        ],
    )
    _rebuild_table_with_schema(
        conn,
        "product_snapshots",
        """
        CREATE TABLE {table_name} (
            snapshot_time TEXT NOT NULL,
            customer_center_id TEXT NOT NULL DEFAULT '',
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            ad_id BIGINT NOT NULL,
            ad_name TEXT NOT NULL,
            product_key TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            product_show_count INTEGER NOT NULL DEFAULT 0,
            product_click_count INTEGER NOT NULL DEFAULT 0,
            stat_cost REAL NOT NULL DEFAULT 0,
            pay_amount REAL NOT NULL DEFAULT 0,
            order_count INTEGER NOT NULL DEFAULT 0,
            roi REAL NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (customer_center_id, snapshot_time, ad_id, product_key)
        )
        """,
        [
            "snapshot_time",
            "customer_center_id",
            "window_start",
            "window_end",
            "advertiser_id",
            "advertiser_name",
            "ad_id",
            "ad_name",
            "product_key",
            "product_id",
            "product_name",
            "product_show_count",
            "product_click_count",
            "stat_cost",
            "pay_amount",
            "order_count",
            "roi",
            "raw_json",
        ],
    )
    _rebuild_table_with_schema(
        conn,
        "material_snapshots",
        """
        CREATE TABLE {table_name} (
            snapshot_time TEXT NOT NULL,
            customer_center_id TEXT NOT NULL DEFAULT '',
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            ad_id BIGINT NOT NULL,
            ad_name TEXT NOT NULL,
            material_type TEXT NOT NULL,
            material_key TEXT NOT NULL,
            material_id TEXT NOT NULL,
            material_name TEXT NOT NULL,
            create_time TEXT NOT NULL DEFAULT '',
            video_id TEXT NOT NULL DEFAULT '',
            cover_url TEXT NOT NULL DEFAULT '',
            aweme_item_id TEXT NOT NULL DEFAULT '',
            video_url TEXT NOT NULL DEFAULT '',
            product_show_count INTEGER NOT NULL DEFAULT 0,
            product_click_count INTEGER NOT NULL DEFAULT 0,
            stat_cost REAL NOT NULL DEFAULT 0,
            pay_amount REAL NOT NULL DEFAULT 0,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            order_count INTEGER NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            roi REAL NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (customer_center_id, snapshot_time, ad_id, material_type, material_key)
        )
        """,
        [
            "snapshot_time",
            "customer_center_id",
            "window_start",
            "window_end",
            "advertiser_id",
            "advertiser_name",
            "ad_id",
            "ad_name",
            "material_type",
            "material_key",
            "material_id",
            "material_name",
            "create_time",
            "video_id",
            "cover_url",
            "aweme_item_id",
            "video_url",
            "product_show_count",
            "product_click_count",
            "stat_cost",
            "pay_amount",
            "total_pay_amount",
            "settled_pay_amount",
            "order_count",
            "settled_order_count",
            "roi",
            "raw_json",
        ],
    )
    _rebuild_table_with_schema(
        conn,
        "material_rollups",
        """
        CREATE TABLE {table_name} (
            snapshot_time TEXT NOT NULL,
            customer_center_id TEXT NOT NULL DEFAULT '',
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            material_key TEXT NOT NULL,
            material_id TEXT NOT NULL,
            material_name TEXT NOT NULL,
            create_time TEXT NOT NULL DEFAULT '',
            material_type TEXT NOT NULL,
            video_id TEXT NOT NULL DEFAULT '',
            cover_url TEXT NOT NULL DEFAULT '',
            aweme_item_id TEXT NOT NULL DEFAULT '',
            video_url TEXT NOT NULL DEFAULT '',
            stat_cost REAL NOT NULL DEFAULT 0,
            pay_amount REAL NOT NULL DEFAULT 0,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            order_count INTEGER NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            plan_count INTEGER NOT NULL DEFAULT 0,
            advertiser_count INTEGER NOT NULL DEFAULT 0,
            plan_ids_json TEXT NOT NULL DEFAULT '[]',
            advertiser_ids_json TEXT NOT NULL DEFAULT '[]',
            is_original INTEGER NOT NULL DEFAULT 0,
            top_plan_name TEXT NOT NULL DEFAULT '',
            top_account_name TEXT NOT NULL DEFAULT '',
            roi REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (customer_center_id, snapshot_time, material_key)
        )
        """,
        [
            "snapshot_time",
            "customer_center_id",
            "window_start",
            "window_end",
            "material_key",
            "material_id",
            "material_name",
            "create_time",
            "material_type",
            "video_id",
            "cover_url",
            "aweme_item_id",
            "video_url",
            "stat_cost",
            "pay_amount",
            "total_pay_amount",
            "settled_pay_amount",
            "order_count",
            "settled_order_count",
            "plan_count",
            "advertiser_count",
            "plan_ids_json",
            "advertiser_ids_json",
            "is_original",
            "top_plan_name",
            "top_account_name",
            "roi",
        ],
    )
    _rebuild_table_with_schema(
        conn,
        "video_origin_flags",
        """
        CREATE TABLE {table_name} (
            snapshot_time TEXT NOT NULL,
            customer_center_id TEXT NOT NULL DEFAULT '',
            advertiser_id BIGINT NOT NULL,
            material_id TEXT NOT NULL,
            is_original INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (customer_center_id, snapshot_time, advertiser_id, material_id)
        )
        """,
        [
            "snapshot_time",
            "customer_center_id",
            "advertiser_id",
            "material_id",
            "is_original",
            "raw_json",
        ],
    )
    _rebuild_table_with_schema(
        conn,
        "extended_sync_runs",
        """
        CREATE TABLE {table_name} (
            customer_center_id TEXT NOT NULL DEFAULT '',
            snapshot_time TEXT NOT NULL,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            status TEXT NOT NULL,
            plan_count INTEGER NOT NULL DEFAULT 0,
            detail_count INTEGER NOT NULL DEFAULT 0,
            product_row_count INTEGER NOT NULL DEFAULT 0,
            material_row_count INTEGER NOT NULL DEFAULT 0,
            original_video_row_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            error_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            PRIMARY KEY (customer_center_id, snapshot_time)
        )
        """,
        [
            "customer_center_id",
            "snapshot_time",
            "window_start",
            "window_end",
            "status",
            "plan_count",
            "detail_count",
            "product_row_count",
            "material_row_count",
            "original_video_row_count",
            "error_count",
            "error_json",
            "created_at",
            "finished_at",
        ],
    )
    _rebuild_table_with_schema(
        conn,
        "account_balances",
        """
        CREATE TABLE {table_name} (
            snapshot_time TEXT NOT NULL,
            customer_center_id TEXT NOT NULL DEFAULT '',
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            account_balance REAL NOT NULL DEFAULT 0,
            available_balance REAL NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (customer_center_id, snapshot_time, advertiser_id)
        )
        """,
        [
            "snapshot_time",
            "customer_center_id",
            "advertiser_id",
            "advertiser_name",
            "account_balance",
            "available_balance",
            "raw_json",
        ],
    )
    _rebuild_table_with_schema(
        conn,
        "shared_wallets",
        """
        CREATE TABLE {table_name} (
            snapshot_time TEXT NOT NULL,
            customer_center_id TEXT NOT NULL DEFAULT '',
            main_wallet_id TEXT NOT NULL,
            wallet_name TEXT NOT NULL DEFAULT '',
            total_balance REAL NOT NULL DEFAULT 0,
            valid_balance REAL NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (customer_center_id, snapshot_time, main_wallet_id)
        )
        """,
        [
            "snapshot_time",
            "customer_center_id",
            "main_wallet_id",
            "wallet_name",
            "total_balance",
            "valid_balance",
            "raw_json",
        ],
    )
    _rebuild_table_with_schema(
        conn,
        "shared_wallet_account_relations",
        """
        CREATE TABLE {table_name} (
            snapshot_time TEXT NOT NULL,
            customer_center_id TEXT NOT NULL DEFAULT '',
            main_wallet_id TEXT NOT NULL,
            advertiser_id BIGINT NOT NULL,
            child_wallet_id TEXT NOT NULL DEFAULT '',
            wallet_name TEXT NOT NULL DEFAULT '',
            raw_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (customer_center_id, snapshot_time, main_wallet_id, advertiser_id)
        )
        """,
        [
            "snapshot_time",
            "customer_center_id",
            "main_wallet_id",
            "advertiser_id",
            "child_wallet_id",
            "wallet_name",
            "raw_json",
        ],
    )
    _ensure_snapshot_table_indexes(conn)


def _rebuild_table_with_query(
    conn: Any,
    table_name: str,
    create_sql: str,
    insert_columns: list[str],
    select_sql: str,
) -> None:
    temp_table_name = f"{table_name}__v12"
    conn.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
    conn.execute(create_sql.replace("{table_name}", temp_table_name))
    columns_sql = ", ".join(insert_columns)
    conn.execute(f"INSERT INTO {temp_table_name} ({columns_sql}) {select_sql}")
    conn.execute(f"DROP TABLE {table_name}")
    conn.execute(f"ALTER TABLE {temp_table_name} RENAME TO {table_name}")


def _postgres_native_runtime_types(conn: Any, context: dict[str, Any] | None = None) -> None:
    if getattr(conn, "backend", "") != "postgres":
        return
    timezone = str((context or {}).get("timezone") or "Asia/Shanghai").strip() or "Asia/Shanghai"
    timezone_sql = timezone.replace("'", "''")

    def ts_expr(column_name: str) -> str:
        return (
            f"CASE WHEN {column_name} IS NULL OR BTRIM({column_name}) = '' THEN NULL "
            f"ELSE (NULLIF(REPLACE({column_name}, '/', '-'), '')::timestamp AT TIME ZONE '{timezone_sql}') END"
        )

    if _table_exists(conn, "extended_sync_runs"):
        _rebuild_table_with_query(
            conn,
            "extended_sync_runs",
            """
            CREATE TABLE {table_name} (
                customer_center_id TEXT NOT NULL DEFAULT '',
                snapshot_time TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                status TEXT NOT NULL,
                plan_count INTEGER NOT NULL DEFAULT 0,
                detail_count INTEGER NOT NULL DEFAULT 0,
                product_row_count INTEGER NOT NULL DEFAULT 0,
                material_row_count INTEGER NOT NULL DEFAULT 0,
                original_video_row_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                error_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                PRIMARY KEY (customer_center_id, snapshot_time)
            )
            """,
            [
                "customer_center_id",
                "snapshot_time",
                "window_start",
                "window_end",
                "status",
                "plan_count",
                "detail_count",
                "product_row_count",
                "material_row_count",
                "original_video_row_count",
                "error_count",
                "error_json",
                "created_at",
                "finished_at",
            ],
            f"""
            SELECT
                customer_center_id,
                snapshot_time,
                window_start,
                window_end,
                status,
                plan_count,
                detail_count,
                product_row_count,
                material_row_count,
                original_video_row_count,
                error_count,
                CASE WHEN error_json IS NULL OR BTRIM(error_json) = '' THEN '[]'::jsonb ELSE error_json::jsonb END,
                {ts_expr("created_at")},
                {ts_expr("finished_at")}
            FROM extended_sync_runs
            """,
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_extended_sync_runs_cc_time ON extended_sync_runs (customer_center_id, snapshot_time)"
        )

    if _table_exists(conn, "comment_records"):
        _rebuild_table_with_query(
            conn,
            "comment_records",
            """
            CREATE TABLE {table_name} (
                customer_center_id TEXT NOT NULL DEFAULT '',
                advertiser_id BIGINT NOT NULL,
                comment_id TEXT NOT NULL,
                comment_date DATE,
                create_time TIMESTAMPTZ,
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
                raw_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                fetched_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ,
                PRIMARY KEY (customer_center_id, advertiser_id, comment_id)
            )
            """,
            [
                "customer_center_id",
                "advertiser_id",
                "comment_id",
                "comment_date",
                "create_time",
                "advertiser_name",
                "text",
                "reply_count",
                "hide_status",
                "level_type",
                "comment_user_name",
                "comment_user_id",
                "like_count",
                "item_title",
                "comment_type",
                "promotion_id",
                "material_id",
                "item_id",
                "raw_json",
                "fetched_at",
                "updated_at",
            ],
            f"""
            SELECT
                customer_center_id,
                advertiser_id,
                comment_id,
                CASE WHEN comment_date IS NULL OR BTRIM(comment_date) = '' THEN NULL ELSE NULLIF(REPLACE(comment_date, '/', '-'), '')::date END,
                {ts_expr("create_time")},
                advertiser_name,
                text,
                reply_count,
                hide_status,
                level_type,
                comment_user_name,
                comment_user_id,
                like_count,
                item_title,
                comment_type,
                promotion_id,
                material_id,
                item_id,
                CASE WHEN raw_json IS NULL OR BTRIM(raw_json) = '' THEN '{{}}'::jsonb ELSE raw_json::jsonb END,
                {ts_expr("fetched_at")},
                {ts_expr("updated_at")}
            FROM comment_records
            """,
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_comment_records_cc_date_adv
            ON comment_records (customer_center_id, comment_date, advertiser_id, create_time)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_comment_records_cc_promotion
            ON comment_records (customer_center_id, advertiser_id, promotion_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_comment_records_cc_material
            ON comment_records (customer_center_id, advertiser_id, material_id)
            """
        )

    if _table_exists(conn, "comment_sync_states"):
        _rebuild_table_with_query(
            conn,
            "comment_sync_states",
            """
            CREATE TABLE {table_name} (
                customer_center_id TEXT NOT NULL DEFAULT '',
                advertiser_id BIGINT NOT NULL,
                sync_date DATE,
                advertiser_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                comment_count INTEGER NOT NULL DEFAULT 0,
                last_attempt_at TIMESTAMPTZ,
                last_success_at TIMESTAMPTZ,
                error_message TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (customer_center_id, advertiser_id, sync_date)
            )
            """,
            [
                "customer_center_id",
                "advertiser_id",
                "sync_date",
                "advertiser_name",
                "status",
                "comment_count",
                "last_attempt_at",
                "last_success_at",
                "error_message",
            ],
            f"""
            SELECT
                customer_center_id,
                advertiser_id,
                CASE WHEN sync_date IS NULL OR BTRIM(sync_date) = '' THEN NULL ELSE NULLIF(REPLACE(sync_date, '/', '-'), '')::date END,
                advertiser_name,
                status,
                comment_count,
                {ts_expr("last_attempt_at")},
                {ts_expr("last_success_at")},
                error_message
            FROM comment_sync_states
            """,
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_comment_sync_states_cc_date_adv
            ON comment_sync_states (customer_center_id, sync_date, advertiser_id)
            """
        )

    if _table_exists(conn, "history_backfill_jobs"):
        _rebuild_table_with_query(
            conn,
            "history_backfill_jobs",
            """
            CREATE TABLE {table_name} (
                id BIGSERIAL PRIMARY KEY,
                job_key TEXT NOT NULL,
                kind TEXT NOT NULL,
                task_name TEXT NOT NULL,
                range_start DATE,
                range_end DATE,
                days INTEGER NOT NULL DEFAULT 0,
                requested_missing_days INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'queued',
                task_id TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                queued_at TIMESTAMPTZ,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ
            )
            """,
            [
                "id",
                "job_key",
                "kind",
                "task_name",
                "range_start",
                "range_end",
                "days",
                "requested_missing_days",
                "status",
                "task_id",
                "message",
                "result_json",
                "queued_at",
                "started_at",
                "finished_at",
                "updated_at",
            ],
            f"""
            SELECT
                id,
                job_key,
                kind,
                task_name,
                CASE WHEN range_start IS NULL OR BTRIM(range_start) = '' THEN NULL ELSE NULLIF(REPLACE(range_start, '/', '-'), '')::date END,
                CASE WHEN range_end IS NULL OR BTRIM(range_end) = '' THEN NULL ELSE NULLIF(REPLACE(range_end, '/', '-'), '')::date END,
                days,
                requested_missing_days,
                status,
                task_id,
                message,
                CASE WHEN result_json IS NULL OR BTRIM(result_json) = '' THEN '{{}}'::jsonb ELSE result_json::jsonb END,
                {ts_expr("queued_at")},
                {ts_expr("started_at")},
                {ts_expr("finished_at")},
                {ts_expr("updated_at")}
            FROM history_backfill_jobs
            """,
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_history_backfill_jobs_job_key
            ON history_backfill_jobs (job_key)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_history_backfill_jobs_kind_status_updated
            ON history_backfill_jobs (kind, status, updated_at)
            """
        )
        conn.execute(
            """
            SELECT setval(
                pg_get_serial_sequence('history_backfill_jobs', 'id'),
                COALESCE((SELECT MAX(id) FROM history_backfill_jobs), 1),
                true
            )
            """
        )


def _material_rollup_context_schema_backfill(conn: Any) -> None:
    _ensure_column(conn, "material_rollups", "top_anchor_name", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_rollups", "product_info_text", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_rollups", "product_names_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "material_rollups", "overall_show_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "overall_click_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "overall_ctr", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "settled_roi", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "pay_order_cost", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "settled_amount_rate", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "refund_amount_1h", "REAL NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_rollups", "refund_rate_1h", "REAL DEFAULT NULL")


def _material_report_snapshot_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_report_snapshots (
            snapshot_time TEXT NOT NULL,
            customer_center_id TEXT NOT NULL DEFAULT '',
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            advertiser_id BIGINT NOT NULL,
            material_type TEXT NOT NULL,
            material_match_key TEXT NOT NULL,
            material_id TEXT NOT NULL DEFAULT '',
            material_name TEXT NOT NULL DEFAULT '',
            create_time TEXT NOT NULL DEFAULT '',
            stat_cost REAL NOT NULL DEFAULT 0,
            pay_amount REAL NOT NULL DEFAULT 0,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            order_count INTEGER NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            overall_show_count INTEGER NOT NULL DEFAULT 0,
            overall_click_count INTEGER NOT NULL DEFAULT 0,
            roi REAL NOT NULL DEFAULT 0,
            settled_roi REAL NOT NULL DEFAULT 0,
            pay_order_cost REAL NOT NULL DEFAULT 0,
            settled_amount_rate REAL NOT NULL DEFAULT 0,
            refund_amount_1h REAL NOT NULL DEFAULT 0,
            refund_rate_1h REAL DEFAULT NULL,
            raw_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (customer_center_id, snapshot_time, advertiser_id, material_type, material_match_key)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_report_snapshots_cc_time
        ON material_report_snapshots (customer_center_id, snapshot_time)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_report_snapshots_material
        ON material_report_snapshots (customer_center_id, material_type, material_id, snapshot_time)
        """
    )


def _material_report_snapshot_context_columns(conn: Any) -> None:
    _ensure_column(conn, "material_report_snapshots", "create_time", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "material_report_snapshots", "overall_show_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "material_report_snapshots", "overall_click_count", "INTEGER NOT NULL DEFAULT 0")


def _account_snapshot_rollup_fields(conn: Any) -> None:
    for table_name in ("account_snapshots", "account_daily"):
        if not _table_exists(conn, table_name):
            continue
        _ensure_column(conn, table_name, "total_pay_amount", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, table_name, "settled_pay_amount", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, table_name, "settled_roi", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, table_name, "settled_order_count", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, table_name, "pay_order_cost", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, table_name, "settled_amount_rate", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, table_name, "refund_rate_1h", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, table_name, "refund_amount_1h", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, table_name, "plan_count", "INTEGER NOT NULL DEFAULT 0")


def _plan_delivery_type_metadata_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_delivery_type_metadata (
            customer_center_id TEXT NOT NULL DEFAULT '',
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL DEFAULT '',
            ad_id BIGINT NOT NULL,
            ad_name TEXT NOT NULL DEFAULT '',
            marketing_goal TEXT NOT NULL DEFAULT '',
            plan_delivery_type TEXT NOT NULL DEFAULT 'GLOBAL',
            source TEXT NOT NULL DEFAULT 'UNI_MAIN_LIST',
            detected_at TEXT NOT NULL DEFAULT '',
            refreshed_at TEXT NOT NULL,
            PRIMARY KEY (customer_center_id, ad_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_plan_delivery_type_metadata_cc_adv
        ON plan_delivery_type_metadata (customer_center_id, advertiser_id, plan_delivery_type)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_plan_delivery_type_metadata_cc_refresh
        ON plan_delivery_type_metadata (customer_center_id, refreshed_at)
        """
    )


def _current_and_material_daily_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS summary_current (
            customer_center_id TEXT NOT NULL DEFAULT '',
            snapshot_time TEXT NOT NULL,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            account_count INTEGER NOT NULL,
            active_account_count INTEGER NOT NULL,
            plan_count INTEGER NOT NULL,
            active_plan_count INTEGER NOT NULL,
            stat_cost REAL NOT NULL,
            pay_amount REAL NOT NULL,
            order_count INTEGER NOT NULL,
            roi REAL NOT NULL,
            account_failures INTEGER NOT NULL,
            plan_failures INTEGER NOT NULL,
            PRIMARY KEY (customer_center_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_summary_current_snapshot
        ON summary_current (snapshot_time, customer_center_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS account_current (
            customer_center_id TEXT NOT NULL DEFAULT '',
            snapshot_time TEXT NOT NULL,
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            stat_cost REAL NOT NULL,
            roi REAL NOT NULL,
            order_count INTEGER NOT NULL,
            pay_amount REAL NOT NULL,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            settled_roi REAL NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            pay_order_cost REAL NOT NULL DEFAULT 0,
            settled_amount_rate REAL NOT NULL DEFAULT 0,
            refund_rate_1h REAL NOT NULL DEFAULT 0,
            refund_amount_1h REAL NOT NULL DEFAULT 0,
            plan_count INTEGER NOT NULL DEFAULT 0,
            ok INTEGER NOT NULL,
            error TEXT,
            PRIMARY KEY (customer_center_id, advertiser_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_account_current_snapshot
        ON account_current (snapshot_time, customer_center_id, advertiser_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_current (
            customer_center_id TEXT NOT NULL DEFAULT '',
            snapshot_time TEXT NOT NULL,
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            ad_id BIGINT NOT NULL,
            ad_name TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            anchor_name TEXT NOT NULL,
            marketing_goal TEXT NOT NULL,
            plan_source TEXT NOT NULL DEFAULT 'UNI_PROMOTION',
            plan_delivery_type TEXT NOT NULL DEFAULT 'GLOBAL',
            status TEXT NOT NULL,
            opt_status TEXT NOT NULL,
            roi_goal REAL NOT NULL,
            stat_cost REAL NOT NULL,
            roi REAL NOT NULL,
            order_count INTEGER NOT NULL,
            pay_amount REAL NOT NULL,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            settled_roi REAL NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            pay_order_cost REAL NOT NULL DEFAULT 0,
            settled_amount_rate REAL NOT NULL DEFAULT 0,
            refund_rate_1h REAL NOT NULL DEFAULT 0,
            refund_amount_1h REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (customer_center_id, ad_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_plan_current_snapshot
        ON plan_current (snapshot_time, customer_center_id, ad_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_current (
            customer_center_id TEXT NOT NULL DEFAULT '',
            snapshot_time TEXT NOT NULL,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            material_key TEXT NOT NULL,
            material_id TEXT NOT NULL,
            material_name TEXT NOT NULL,
            create_time TEXT NOT NULL DEFAULT '',
            material_type TEXT NOT NULL,
            video_id TEXT NOT NULL DEFAULT '',
            cover_url TEXT NOT NULL DEFAULT '',
            aweme_item_id TEXT NOT NULL DEFAULT '',
            video_url TEXT NOT NULL DEFAULT '',
            stat_cost REAL NOT NULL DEFAULT 0,
            pay_amount REAL NOT NULL DEFAULT 0,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            order_count INTEGER NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            plan_count INTEGER NOT NULL DEFAULT 0,
            advertiser_count INTEGER NOT NULL DEFAULT 0,
            plan_ids_json TEXT NOT NULL DEFAULT '[]',
            advertiser_ids_json TEXT NOT NULL DEFAULT '[]',
            is_original INTEGER NOT NULL DEFAULT 0,
            top_plan_name TEXT NOT NULL DEFAULT '',
            top_account_name TEXT NOT NULL DEFAULT '',
            top_anchor_name TEXT NOT NULL DEFAULT '',
            product_info_text TEXT NOT NULL DEFAULT '',
            product_names_json TEXT NOT NULL DEFAULT '[]',
            overall_show_count INTEGER NOT NULL DEFAULT 0,
            overall_click_count INTEGER NOT NULL DEFAULT 0,
            overall_ctr REAL NOT NULL DEFAULT 0,
            roi REAL NOT NULL DEFAULT 0,
            settled_roi REAL NOT NULL DEFAULT 0,
            pay_order_cost REAL NOT NULL DEFAULT 0,
            settled_amount_rate REAL NOT NULL DEFAULT 0,
            refund_amount_1h REAL NOT NULL DEFAULT 0,
            refund_rate_1h REAL DEFAULT NULL,
            PRIMARY KEY (customer_center_id, material_key)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_current_snapshot
        ON material_current (snapshot_time, customer_center_id, material_key)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_daily (
            customer_center_id TEXT NOT NULL DEFAULT '',
            biz_date TEXT NOT NULL,
            snapshot_time TEXT NOT NULL,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            material_key TEXT NOT NULL,
            material_id TEXT NOT NULL,
            material_name TEXT NOT NULL,
            create_time TEXT NOT NULL DEFAULT '',
            material_type TEXT NOT NULL,
            video_id TEXT NOT NULL DEFAULT '',
            cover_url TEXT NOT NULL DEFAULT '',
            aweme_item_id TEXT NOT NULL DEFAULT '',
            video_url TEXT NOT NULL DEFAULT '',
            stat_cost REAL NOT NULL DEFAULT 0,
            pay_amount REAL NOT NULL DEFAULT 0,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            order_count INTEGER NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            plan_count INTEGER NOT NULL DEFAULT 0,
            advertiser_count INTEGER NOT NULL DEFAULT 0,
            plan_ids_json TEXT NOT NULL DEFAULT '[]',
            advertiser_ids_json TEXT NOT NULL DEFAULT '[]',
            is_original INTEGER NOT NULL DEFAULT 0,
            top_plan_name TEXT NOT NULL DEFAULT '',
            top_account_name TEXT NOT NULL DEFAULT '',
            top_anchor_name TEXT NOT NULL DEFAULT '',
            product_info_text TEXT NOT NULL DEFAULT '',
            product_names_json TEXT NOT NULL DEFAULT '[]',
            overall_show_count INTEGER NOT NULL DEFAULT 0,
            overall_click_count INTEGER NOT NULL DEFAULT 0,
            overall_ctr REAL NOT NULL DEFAULT 0,
            roi REAL NOT NULL DEFAULT 0,
            settled_roi REAL NOT NULL DEFAULT 0,
            pay_order_cost REAL NOT NULL DEFAULT 0,
            settled_amount_rate REAL NOT NULL DEFAULT 0,
            refund_amount_1h REAL NOT NULL DEFAULT 0,
            refund_rate_1h REAL DEFAULT NULL,
            PRIMARY KEY (customer_center_id, biz_date, material_key)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_daily_date
        ON material_daily (biz_date, customer_center_id, material_key)
        """
    )
    _material_metric_sort_partial_indexes(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_profile (
            customer_center_id TEXT NOT NULL DEFAULT '',
            material_key TEXT NOT NULL,
            material_id TEXT NOT NULL DEFAULT '',
            material_name TEXT NOT NULL DEFAULT '',
            create_time TEXT NOT NULL DEFAULT '',
            material_type TEXT NOT NULL DEFAULT '',
            video_id TEXT NOT NULL DEFAULT '',
            cover_url TEXT NOT NULL DEFAULT '',
            aweme_item_id TEXT NOT NULL DEFAULT '',
            video_url TEXT NOT NULL DEFAULT '',
            is_original INTEGER NOT NULL DEFAULT 0,
            top_plan_name TEXT NOT NULL DEFAULT '',
            top_account_name TEXT NOT NULL DEFAULT '',
            top_anchor_name TEXT NOT NULL DEFAULT '',
            product_info_text TEXT NOT NULL DEFAULT '',
            product_names_json TEXT NOT NULL DEFAULT '[]',
            plan_ids_json TEXT NOT NULL DEFAULT '[]',
            advertiser_ids_json TEXT NOT NULL DEFAULT '[]',
            plan_count INTEGER NOT NULL DEFAULT 0,
            advertiser_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (customer_center_id, material_key)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_material_profile_updated
        ON material_profile (updated_at, customer_center_id, material_key)
        """
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, name="base_schema", sql=BASE_SCHEMA_SQL),
    # Historical compatibility for older databases is consolidated in later Python migrations.
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
    Migration(
        version=7,
        name="legacy_schema_backfill",
        apply_fn=_legacy_schema_backfill,
    ),
    Migration(
        version=8,
        name="customer_center_scope_schema_backfill",
        apply_fn=_customer_center_scope_schema_backfill,
    ),
    Migration(
        version=9,
        name="history_backfill_jobs",
        apply_fn=_history_backfill_jobs_schema,
    ),
    Migration(
        version=10,
        name="snapshot_composite_primary_keys",
        apply_fn=_snapshot_composite_primary_keys,
    ),
    Migration(
        version=11,
        name="customer_center_scope_data_backfill",
        apply_fn=_customer_center_scope_data_backfill,
    ),
    Migration(
        version=12,
        name="postgres_native_runtime_types",
        apply_fn=_postgres_native_runtime_types,
    ),
    Migration(
        version=13,
        name="performance_daily_read_models",
        sql="""
        CREATE TABLE IF NOT EXISTS summary_daily (
            customer_center_id TEXT NOT NULL DEFAULT '',
            biz_date TEXT NOT NULL,
            snapshot_time TEXT NOT NULL,
            account_count INTEGER NOT NULL,
            active_account_count INTEGER NOT NULL,
            plan_count INTEGER NOT NULL,
            active_plan_count INTEGER NOT NULL,
            stat_cost REAL NOT NULL,
            pay_amount REAL NOT NULL,
            order_count INTEGER NOT NULL,
            roi REAL NOT NULL,
            account_failures INTEGER NOT NULL,
            plan_failures INTEGER NOT NULL,
            PRIMARY KEY (customer_center_id, biz_date)
        );
        CREATE TABLE IF NOT EXISTS account_daily (
            customer_center_id TEXT NOT NULL DEFAULT '',
            biz_date TEXT NOT NULL,
            snapshot_time TEXT NOT NULL,
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            stat_cost REAL NOT NULL,
            roi REAL NOT NULL,
            order_count INTEGER NOT NULL,
            pay_amount REAL NOT NULL,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            settled_roi REAL NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            pay_order_cost REAL NOT NULL DEFAULT 0,
            settled_amount_rate REAL NOT NULL DEFAULT 0,
            refund_rate_1h REAL NOT NULL DEFAULT 0,
            refund_amount_1h REAL NOT NULL DEFAULT 0,
            plan_count INTEGER NOT NULL DEFAULT 0,
            ok INTEGER NOT NULL,
            error TEXT,
            PRIMARY KEY (customer_center_id, biz_date, advertiser_id)
        );
        CREATE TABLE IF NOT EXISTS plan_daily (
            customer_center_id TEXT NOT NULL DEFAULT '',
            biz_date TEXT NOT NULL,
            snapshot_time TEXT NOT NULL,
            advertiser_id BIGINT NOT NULL,
            advertiser_name TEXT NOT NULL,
            ad_id BIGINT NOT NULL,
            ad_name TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            anchor_name TEXT NOT NULL,
            marketing_goal TEXT NOT NULL,
            plan_source TEXT NOT NULL DEFAULT 'UNI_PROMOTION',
            plan_delivery_type TEXT NOT NULL DEFAULT 'GLOBAL',
            status TEXT NOT NULL,
            opt_status TEXT NOT NULL,
            roi_goal REAL NOT NULL,
            stat_cost REAL NOT NULL,
            roi REAL NOT NULL,
            order_count INTEGER NOT NULL,
            pay_amount REAL NOT NULL,
            total_pay_amount REAL NOT NULL DEFAULT 0,
            settled_pay_amount REAL NOT NULL DEFAULT 0,
            settled_roi REAL NOT NULL DEFAULT 0,
            settled_order_count INTEGER NOT NULL DEFAULT 0,
            pay_order_cost REAL NOT NULL DEFAULT 0,
            settled_amount_rate REAL NOT NULL DEFAULT 0,
            refund_rate_1h REAL NOT NULL DEFAULT 0,
            refund_amount_1h REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (customer_center_id, biz_date, ad_id)
        );
        CREATE INDEX IF NOT EXISTS idx_summary_daily_date_cc
        ON summary_daily (biz_date, customer_center_id);
        CREATE INDEX IF NOT EXISTS idx_account_daily_date_cc_adv
        ON account_daily (biz_date, customer_center_id, advertiser_id);
        CREATE INDEX IF NOT EXISTS idx_plan_daily_date_cc_plan
        ON plan_daily (biz_date, customer_center_id, ad_id);
        """,
    ),
    Migration(
        version=14,
        name="material_rollup_context_fields",
        apply_fn=_material_rollup_context_schema_backfill,
    ),
    Migration(
        version=15,
        name="material_report_snapshots",
        apply_fn=_material_report_snapshot_schema,
    ),
    Migration(
        version=16,
        name="material_report_snapshot_context_columns",
        apply_fn=_material_report_snapshot_context_columns,
    ),
    Migration(
        version=17,
        name="account_snapshot_rollup_fields",
        apply_fn=_account_snapshot_rollup_fields,
    ),
    Migration(
        version=18,
        name="plan_delivery_type_metadata",
        apply_fn=_plan_delivery_type_metadata_schema,
    ),
    Migration(
        version=19,
        name="current_and_material_daily_tables",
        apply_fn=_current_and_material_daily_schema,
    ),
    Migration(
        version=20,
        name="plan_refresh_states",
        sql="""
        CREATE TABLE IF NOT EXISTS plan_refresh_states (
            customer_center_id TEXT NOT NULL DEFAULT '',
            ad_id BIGINT NOT NULL,
            advertiser_id BIGINT NOT NULL DEFAULT 0,
            advertiser_name TEXT NOT NULL DEFAULT '',
            ad_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            opt_status TEXT NOT NULL DEFAULT '',
            last_hot_sync_at TEXT NOT NULL DEFAULT '',
            last_cold_sync_at TEXT NOT NULL DEFAULT '',
            last_material_sync_at TEXT NOT NULL DEFAULT '',
            last_material_change_at TEXT NOT NULL DEFAULT '',
            last_status_change_at TEXT NOT NULL DEFAULT '',
            last_nonzero_perf_at TEXT NOT NULL DEFAULT '',
            last_material_row_count INTEGER NOT NULL DEFAULT 0,
            sync_priority TEXT NOT NULL DEFAULT 'cold',
            updated_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (customer_center_id, ad_id)
        );
        CREATE INDEX IF NOT EXISTS idx_plan_refresh_states_cc_priority_sync
        ON plan_refresh_states (customer_center_id, sync_priority, last_material_sync_at, ad_id);
        CREATE INDEX IF NOT EXISTS idx_plan_refresh_states_cc_cold_sync
        ON plan_refresh_states (customer_center_id, last_cold_sync_at, ad_id);
        """,
    ),
    Migration(
        version=21,
        name="history_refresh_states",
        sql="""
        CREATE TABLE IF NOT EXISTS history_refresh_states (
            customer_center_id TEXT NOT NULL DEFAULT '',
            target_date TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            trigger TEXT NOT NULL DEFAULT '',
            snapshot_time TEXT NOT NULL DEFAULT '',
            affected_tables_json TEXT NOT NULL DEFAULT '[]',
            detail_json TEXT NOT NULL DEFAULT '{}',
            last_attempt_at TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            last_success_at TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (customer_center_id, target_date, stage)
        );
        CREATE INDEX IF NOT EXISTS idx_history_refresh_states_stage_date
        ON history_refresh_states (stage, target_date, customer_center_id);
        CREATE INDEX IF NOT EXISTS idx_history_refresh_states_status_updated
        ON history_refresh_states (status, updated_at);
        """,
    ),
    Migration(
        version=22,
        name="plan_refresh_schedule_fields",
        apply_fn=_plan_refresh_schedule_fields_schema,
    ),
    Migration(
        version=23,
        name="material_relation_edges",
        apply_fn=_material_relation_edges_schema,
    ),
    Migration(
        version=24,
        name="material_snapshot_primary_key_with_advertiser",
        apply_fn=_material_snapshot_primary_key_with_advertiser,
    ),
    Migration(
        version=25,
        name="plan_refresh_error_backoff_fields",
        apply_fn=_plan_refresh_error_backoff_fields_schema,
    ),
    Migration(
        version=26,
        name="material_relation_read_model_tables",
        apply_fn=_material_relation_read_model_schema,
    ),
    Migration(
        version=27,
        name="ensure_performance_daily_read_models",
        apply_fn=_ensure_performance_daily_read_models,
    ),
    Migration(
        version=28,
        name="material_metric_sort_partial_indexes",
        apply_fn=_material_metric_sort_partial_indexes,
    ),
    Migration(
        version=29,
        name="material_name_lookup_indexes",
        apply_fn=_material_name_lookup_indexes,
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


def apply_migrations(conn: Any, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    applied = applied_versions(conn)
    executed: list[dict[str, Any]] = []
    for migration in MIGRATIONS:
        if migration.version in applied:
            continue
        if migration.apply_fn is not None:
            parameter_count = len(inspect.signature(migration.apply_fn).parameters)
            if parameter_count >= 2:
                migration.apply_fn(conn, context or {})
            else:
                migration.apply_fn(conn)
        elif migration.sql:
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
