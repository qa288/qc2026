#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, UploadFile, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from report_qianchuan import (  # noqa: E402
    PLAN_MATERIAL_TYPES,
    PLAN_PRODUCT_FIELDS,
    PLAN_SOURCE_STANDARD,
    PLAN_SOURCE_UNI_PROMOTION,
    AccountSummary,
    OceanEngineClient,
    PlanSummary,
    build_window,
    fetch_account_bundle,
    fetch_plan_bundle,
    format_plan_status_text,
    load_runtime_config,
    normalize_account_fund_money,
    normalize_plan_money,
    plan_material_fields_for_type,
    plan_delivery_status_label,
    plan_marketing_goal_label,
    plan_opt_status_label,
    sanitize_material_title,
)
from dashboard.alert_access import AlertAccess  # noqa: E402
from dashboard.alert_routes import register_alert_routes  # noqa: E402
from dashboard.alert_schemas import AlertRulePayload, NotificationSettingsPayload  # noqa: E402
from dashboard.auth import build_auth_dependencies, build_password_hash, verify_password  # noqa: E402
from dashboard.balance_access import BalanceAccess  # noqa: E402
from dashboard.catalog_access import CatalogAccess  # noqa: E402
from dashboard.db_backend import connect_database, database_backend  # noqa: E402
from dashboard.employee_access import EmployeeAccess  # noqa: E402
from dashboard.employee_routes import register_employee_routes  # noqa: E402
from dashboard.employee_schemas import EmployeeBindingPayload, EmployeeKeywordPayload, EmployeePayload  # noqa: E402
from dashboard.health_routes import register_health_routes  # noqa: E402
from dashboard.history_access import HistoryAccess  # noqa: E402
from dashboard.migrations import apply_migrations  # noqa: E402
from dashboard.page_routes import register_page_routes  # noqa: E402
from dashboard.performance_access import PerformanceAccess  # noqa: E402
from dashboard.query_routes import register_query_routes  # noqa: E402
from dashboard.runtime_checks import readiness_payload  # noqa: E402
from dashboard.settings import settings  # noqa: E402
from dashboard.snapshot_access import SnapshotAccess  # noqa: E402
from dashboard.system_routes import register_system_routes  # noqa: E402
from dashboard.token_access import TokenAccess  # noqa: E402
from dashboard.upload_routes import register_upload_routes  # noqa: E402
from dashboard.upload_access import UploadAccess  # noqa: E402
from dashboard.user_access import UserAccess  # noqa: E402
from dashboard.user_routes import register_user_routes  # noqa: E402
from dashboard.user_schemas import AppUserPayload, UserKeywordPayload, UserScopePayload  # noqa: E402


APP_NAME = settings.app_name
CONFIG_PATH = settings.config_path
DATA_DIR = settings.data_dir
UPLOAD_DIR = settings.upload_dir
DATABASE_PATH = settings.database_path
DATABASE_URL = settings.database_url
TOKEN_CACHE_PATH = settings.token_cache_path
LATEST_TOKEN_PATH = settings.latest_token_path
TIMEZONE = settings.timezone
ALERT_COOLDOWN_DEFAULT = settings.alert_cooldown_default
RETENTION_DAYS = settings.retention_days
DASHBOARD_USERNAME = settings.dashboard_username
DASHBOARD_PASSWORD = settings.dashboard_password
SESSION_SECRET = settings.session_secret
RANGE_CACHE_SECONDS = settings.range_cache_seconds
BACKFILL_QUEUE_DEBOUNCE_SECONDS = settings.backfill_queue_debounce_seconds
PERFORMANCE_RANGES = {"day", "yesterday", "week", "month", "custom"}
RANGE_LABEL_MAP = {
    "day": "今日",
    "yesterday": "昨日",
    "week": "近7天",
    "month": "近30天",
    "custom": "指定日期范围",
}
DETAIL_SYNC_INTERVAL_MINUTES = settings.detail_sync_interval_minutes
ENABLE_IN_PROCESS_SCHEDULER = settings.enable_in_process_scheduler
ROLE_ADMIN = "admin"
ROLE_SUPERVISOR = "supervisor"
ROLE_OPERATOR = "operator"
PUBLIC_SORT_FIELDS = {"stat_cost", "pay_amount", "order_count", "roi"}
EMPLOYEE_KEYWORD_SCOPES = {"all", "account", "plan", "product", "material"}
EMPLOYEE_BINDING_TYPES = {"account", "plan", "product", "material"}
MATERIAL_REPORT_CORE_METRICS = [
    "stat_cost_for_roi2",
    "total_pay_order_gmv_for_roi2",
    "total_pay_order_count_for_roi2",
    "total_prepay_and_pay_order_roi2",
]
MATERIAL_REPORT_EXTENDED_METRICS = MATERIAL_REPORT_CORE_METRICS + [
    "total_pay_order_gmv_include_coupon_for_roi2",
    "total_order_settle_amount_for_roi2_1h",
    "total_prepay_and_pay_settle_roi2_1h",
    "total_order_settle_count_for_roi2_1h",
    "total_cost_per_pay_order_for_roi2",
    "total_order_settle_amount_rate_for_roi2_1h",
]
MATERIAL_REPORT_TITLE_METRICS = MATERIAL_REPORT_CORE_METRICS + [
    "total_pay_order_gmv_include_coupon_for_roi2",
    "total_cost_per_pay_order_for_roi2",
]
MATERIAL_REPORT_TOPIC_CONFIGS = {
    "VIDEO": {
        "data_topic": "SITE_PROMOTION_PRODUCT_POST_DATA_VIDEO",
        "dimensions": ["roi2_material_video_name", "material_id"],
        "name_fields": ["roi2_material_video_name"],
        "metrics": list(MATERIAL_REPORT_EXTENDED_METRICS),
    },
    "IMAGE": {
        "data_topic": "SITE_PROMOTION_PRODUCT_POST_DATA_IMAGE",
        "dimensions": ["material_id", "roi2_material_image_name"],
        "name_fields": ["roi2_material_image_name"],
        "metrics": list(MATERIAL_REPORT_EXTENDED_METRICS),
    },
    "TITLE": {
        "data_topic": "SITE_PROMOTION_PRODUCT_POST_DATA_TITLE",
        "dimensions": ["roi2_title_material_v3"],
        "name_fields": ["roi2_title_material_v3"],
        "metrics": list(MATERIAL_REPORT_TITLE_METRICS),
    },
}


def now_text(tz_name: str = TIMEZONE) -> str:
    return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M:%S")

def build_performance_window(range_key: str, tz_name: str) -> tuple[datetime, datetime, str]:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=tz)
    if range_key == "yesterday":
        start_dt = today_start - timedelta(days=1)
        end_dt = today_start - timedelta(seconds=1)
        label = "昨日"
    elif range_key == "week":
        start_dt = today_start - timedelta(days=6)
        end_dt = now
        label = "近7天"
    elif range_key == "month":
        start_dt = today_start - timedelta(days=29)
        end_dt = now
        label = "近30天"
    else:
        start_dt = today_start
        end_dt = now
        label = "今日"
    return start_dt, end_dt, label


def _parse_date_input(value: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是 YYYY-MM-DD") from exc


def build_custom_performance_window(start_date: str, end_date: str, tz_name: str) -> tuple[datetime, datetime, str]:
    if not str(start_date or "").strip() or not str(end_date or "").strip():
        raise ValueError("指定日期范围必须同时提供开始日期和结束日期")

    start_day = _parse_date_input(start_date, "start_date")
    end_day = _parse_date_input(end_date, "end_date")
    if start_day > end_day:
        raise ValueError("开始日期不能晚于结束日期")

    span_days = (end_day.date() - start_day.date()).days + 1
    if span_days > RETENTION_DAYS:
        raise ValueError(f"单次查询时间跨度不能超过 {RETENTION_DAYS} 天")

    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    start_dt = datetime(start_day.year, start_day.month, start_day.day, 0, 0, 0, tzinfo=tz)
    end_dt = datetime(end_day.year, end_day.month, end_day.day, 23, 59, 59, tzinfo=tz)
    if start_dt > now:
        raise ValueError("开始日期不能晚于当前时间")
    if end_dt > now:
        end_dt = now
    return start_dt, end_dt, "指定日期范围"


def build_performance_cache_key(range_key: str, start_date: str = "", end_date: str = "") -> str:
    normalized = str(range_key or "day").strip().lower()
    if normalized == "custom":
        return f"custom:{str(start_date or '').strip()}:{str(end_date or '').strip()}"
    return normalized


def build_scope_cache_key(allowed_advertiser_ids: set[int] | None) -> str:
    if allowed_advertiser_ids is None:
        return "all"
    values = sorted(int(item) for item in allowed_advertiser_ids)
    return ",".join(str(item) for item in values)


def build_material_cache_key(
    range_key: str,
    start_date: str = "",
    end_date: str = "",
    snapshot_time: str = "",
    allowed_advertiser_ids: set[int] | None = None,
) -> str:
    if str(snapshot_time or "").strip():
        return f"snapshot:{str(snapshot_time).strip()}:{build_scope_cache_key(allowed_advertiser_ids)}"
    return (
        f"{build_performance_cache_key(range_key, start_date, end_date)}:"
        f"{build_scope_cache_key(allowed_advertiser_ids)}"
    )


class DashboardService:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._sync_lock = asyncio.Lock()
        self._detail_sync_lock = asyncio.Lock()
        self._templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
        self._performance_cache: dict[str, dict[str, Any]] = {}
        self._material_cache: dict[str, dict[str, Any]] = {}
        self._backfill_queue_marks: dict[str, float] = {}
        self.user_access = UserAccess(
            self.db,
            now_text,
            build_password_hash,
            verify_password,
            role_admin=ROLE_ADMIN,
            role_supervisor=ROLE_SUPERVISOR,
            role_operator=ROLE_OPERATOR,
        )
        self.employee_access = EmployeeAccess(self.db, now_text)
        self.alert_access = AlertAccess(self.db, now_text, self._default_notification_target)
        self.balance_access = BalanceAccess(self._json_text, normalize_account_fund_money)
        self.history_access = HistoryAccess()
        self.performance_access = PerformanceAccess(
            self.db,
            self._rankings_bundle,
            self._scoped_summary,
            self._decorate_plan_item,
            self._apply_employee_attribution,
            self._snapshot_account_balances,
            self._snapshot_shared_wallets,
            self._snapshot_wallet_relations,
        )
        self.snapshot_access = SnapshotAccess(
            self.db,
            self._latest_summary_meta,
            self._latest_extended_sync_run,
            self._decorate_plan_item,
            plan_marketing_goal_label,
            format_plan_status_text,
        )
        self.catalog_access = CatalogAccess(
            self.db,
            self._latest_summary_meta,
            self._latest_extended_sync_run,
            self._normalize_match_text,
            EMPLOYEE_KEYWORD_SCOPES,
        )
        self.token_access = TokenAccess(self.db, self.read_config, self.build_client)
        self.upload_access = UploadAccess(
            self.db,
            now_text,
            ROLE_ADMIN,
            self.allowed_advertiser_ids_for_user,
            self.latest_snapshot,
            self._normalize_match_text,
            sanitize_material_title,
        )

    @property
    def templates(self) -> Jinja2Templates:
        return self._templates

    def _range_span_days(self, start_dt: datetime, end_dt: datetime) -> int:
        return max((end_dt.date() - start_dt.date()).days + 1, 1)

    def _enqueue_backfill_task(self, task_name: str, days: int, dedupe_key: str) -> bool:
        now_ts = time.time()
        last_ts = float(self._backfill_queue_marks.get(dedupe_key, 0.0) or 0.0)
        if now_ts - last_ts < BACKFILL_QUEUE_DEBOUNCE_SECONDS:
            return True
        from dashboard.celery_app import celery_app

        celery_app.send_task(task_name, args=[max(int(days or 1), 1)])
        self._backfill_queue_marks[dedupe_key] = now_ts
        return True

    def _queue_history_backfill_if_needed(
        self,
        kind: str,
        start_dt: datetime,
        end_dt: datetime,
        missing_days: int,
    ) -> bool:
        if missing_days <= 0:
            return False
        days = min(self._range_span_days(start_dt, end_dt), RETENTION_DAYS)
        range_key = f"{start_dt.strftime('%Y-%m-%d')}:{end_dt.strftime('%Y-%m-%d')}"
        if kind == "performance":
            return self._enqueue_backfill_task("dashboard.performance_backfill", days, f"performance:{range_key}")
        if kind == "detail":
            return self._enqueue_backfill_task("dashboard.detail_backfill", days, f"detail:{range_key}")
        return False

    def init_db(self) -> None:
        with self.db() as conn:
            apply_migrations(conn)
            self._ensure_plan_snapshot_schema_locked(conn)
            self._ensure_app_users_schema_locked(conn)
            self._ensure_material_upload_schema_locked(conn)
            self._ensure_material_preview_schema_locked(conn)
            self.alert_access.ensure_notification_settings(conn)

    def _column_exists_locked(self, conn: Any, table_name: str, column_name: str) -> bool:
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

    def _ensure_app_users_schema_locked(self, conn: Any) -> None:
        if not self._column_exists_locked(conn, "app_users", "upload_materials_enabled"):
            conn.execute("ALTER TABLE app_users ADD COLUMN upload_materials_enabled INTEGER NOT NULL DEFAULT 0")

    def _ensure_column_locked(self, conn: Any, table_name: str, column_name: str, definition: str) -> None:
        if self._column_exists_locked(conn, table_name, column_name):
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _ensure_material_upload_schema_locked(self, conn: Any) -> None:
        self._ensure_column_locked(conn, "material_upload_jobs", "task_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column_locked(conn, "material_upload_jobs", "processed_files", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "material_upload_jobs", "success_files", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "material_upload_jobs", "failed_files", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "material_upload_jobs", "started_at", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column_locked(conn, "material_upload_jobs", "completed_at", "TEXT NOT NULL DEFAULT ''")

        self._ensure_column_locked(conn, "material_upload_job_files", "file_sha256", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column_locked(conn, "material_upload_job_files", "file_md5", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column_locked(conn, "material_upload_job_files", "processed_advertisers", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "material_upload_job_files", "success_advertisers", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "material_upload_job_files", "failed_advertisers", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "material_upload_job_files", "material_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column_locked(conn, "material_upload_job_files", "video_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column_locked(conn, "material_upload_job_files", "video_url", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column_locked(conn, "material_upload_job_files", "message", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column_locked(conn, "material_upload_job_files", "updated_at", "TEXT NOT NULL DEFAULT ''")

    def _ensure_material_preview_schema_locked(self, conn: Any) -> None:
        for table_name in ("material_snapshots", "material_rollups"):
            self._ensure_column_locked(conn, table_name, "cover_url", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column_locked(conn, table_name, "aweme_item_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column_locked(conn, table_name, "video_url", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column_locked(conn, table_name, "total_pay_amount", "REAL NOT NULL DEFAULT 0")
            self._ensure_column_locked(conn, table_name, "settled_pay_amount", "REAL NOT NULL DEFAULT 0")
            self._ensure_column_locked(conn, table_name, "settled_order_count", "INTEGER NOT NULL DEFAULT 0")

    def _ensure_plan_snapshot_schema_locked(self, conn: Any) -> None:
        self._ensure_column_locked(conn, "plan_snapshots", "plan_source", "TEXT NOT NULL DEFAULT 'UNI_PROMOTION'")
        self._ensure_column_locked(conn, "plan_snapshots", "total_pay_amount", "REAL NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "plan_snapshots", "settled_pay_amount", "REAL NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "plan_snapshots", "settled_roi", "REAL NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "plan_snapshots", "settled_order_count", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "plan_snapshots", "pay_order_cost", "REAL NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "plan_snapshots", "settled_amount_rate", "REAL NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "plan_snapshots", "refund_rate_1h", "REAL NOT NULL DEFAULT 0")
        self._ensure_column_locked(conn, "plan_snapshots", "refund_amount_1h", "REAL NOT NULL DEFAULT 0")

    @contextmanager
    def db(self) -> Any:
        conn = connect_database(DATABASE_URL, DATABASE_PATH)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _default_notification_target(self) -> str:
        try:
            payload = load_runtime_config(CONFIG_PATH)
        except Exception:
            return ""
        return str(payload.get("feishu_target") or "").strip()

    def bootstrap_auth_store(self) -> None:
        username = str(DASHBOARD_USERNAME or "").strip()
        password = str(DASHBOARD_PASSWORD or "").strip()
        if not username or not password:
            return
        hashed = build_password_hash(password)
        now = now_text()
        with self.db() as conn:
            row = conn.execute("SELECT id FROM app_users WHERE username = ?", (username,)).fetchone()
            if row:
                conn.execute(
                    """
                UPDATE app_users
                SET password_hash = ?, role = ?, upload_materials_enabled = 1, enabled = 1, updated_at = ?
                WHERE id = ?
                """,
                    (hashed, ROLE_ADMIN, now, row["id"]),
                )
                return
            conn.execute(
                """
                INSERT INTO app_users (username, password_hash, role, display_name, upload_materials_enabled, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, 1, ?, ?)
                """,
                (username, hashed, ROLE_ADMIN, "管理员", now, now),
            )

    def get_user_by_id(self, user_id: int, include_disabled: bool = False) -> dict[str, Any] | None:
        return self.user_access.get_user_by_id(user_id, include_disabled=include_disabled)

    def authenticate_user(self, username: str, password: str) -> dict[str, Any] | None:
        return self.user_access.authenticate_user(username, password)

    def allowed_advertiser_ids_for_user(self, user: dict[str, Any] | None) -> set[int] | None:
        return self.user_access.allowed_advertiser_ids_for_user(user)

    def can_upload_materials(self, user: dict[str, Any] | None) -> bool:
        return self.user_access.can_upload_materials(user)

    def list_users(self) -> list[dict[str, Any]]:
        return self.user_access.list_users()

    def create_user(self, payload: AppUserPayload) -> dict[str, Any]:
        return self.user_access.create_user(payload)

    def update_user(self, user_id: int, payload: AppUserPayload) -> dict[str, Any]:
        return self.user_access.update_user(user_id, payload)

    def user_account_scopes(self, user_id: int) -> list[int]:
        return self.user_access.user_account_scopes(user_id)

    def replace_user_account_scopes(self, user_id: int, advertiser_ids: list[int]) -> list[int]:
        return self.user_access.replace_user_account_scopes(user_id, advertiser_ids)

    def list_user_keywords(self, user_id: int) -> list[dict[str, Any]]:
        return self.user_access.list_user_keywords(user_id)

    def create_user_keyword(self, user_id: int, payload: UserKeywordPayload) -> dict[str, Any]:
        return self.user_access.create_user_keyword(user_id, payload)

    def delete_user_keyword(self, keyword_id: int) -> None:
        self.user_access.delete_user_keyword(keyword_id)

    def list_employees(self) -> list[dict[str, Any]]:
        return self.employee_access.list_employees()

    def employee_detail(self, employee_id: int) -> dict[str, Any] | None:
        return self.employee_access.employee_detail(employee_id)

    def create_employee(self, payload: EmployeePayload) -> dict[str, Any]:
        return self.employee_access.create_employee(payload)

    def update_employee(self, employee_id: int, payload: EmployeePayload) -> dict[str, Any]:
        return self.employee_access.update_employee(employee_id, payload)

    def list_employee_keywords(self, employee_id: int | None = None) -> list[dict[str, Any]]:
        return self.employee_access.list_employee_keywords(employee_id)

    def create_employee_keyword(self, employee_id: int, payload: EmployeeKeywordPayload) -> dict[str, Any]:
        return self.employee_access.create_employee_keyword(employee_id, payload)

    def update_employee_keyword(self, keyword_id: int, payload: EmployeeKeywordPayload) -> dict[str, Any]:
        return self.employee_access.update_employee_keyword(keyword_id, payload)

    def delete_employee_keyword(self, keyword_id: int) -> None:
        self.employee_access.delete_employee_keyword(keyword_id)

    def list_employee_bindings(self, employee_id: int | None = None) -> list[dict[str, Any]]:
        return self.employee_access.list_employee_bindings(employee_id)

    def create_employee_binding(self, employee_id: int, payload: EmployeeBindingPayload) -> dict[str, Any]:
        return self.employee_access.create_employee_binding(employee_id, payload)

    def delete_employee_binding(self, binding_id: int) -> None:
        self.employee_access.delete_employee_binding(binding_id)

    def get_notification_settings(self) -> dict[str, Any]:
        return self.alert_access.get_notification_settings()

    def update_notification_settings(self, payload: NotificationSettingsPayload) -> None:
        self.alert_access.update_notification_settings(payload)

    def list_alert_rules(self) -> list[dict[str, Any]]:
        return self.alert_access.list_alert_rules()

    def create_alert_rule(self, payload: AlertRulePayload) -> None:
        self.alert_access.create_alert_rule(payload)

    def update_alert_rule(self, rule_id: int, payload: AlertRulePayload) -> None:
        self.alert_access.update_alert_rule(rule_id, payload)

    def delete_alert_rule(self, rule_id: int) -> None:
        self.alert_access.delete_alert_rule(rule_id)

    def alert_events(self, limit: int = 80) -> list[dict[str, Any]]:
        return self.alert_access.alert_events(limit)

    def latest_extended_sync(self) -> dict[str, Any] | None:
        return self.snapshot_access.latest_extended_sync()

    def plan_assets(
        self, ad_id: int, snapshot_time: str = "", allowed_advertiser_ids: set[int] | None = None
    ) -> dict[str, Any]:
        return self.snapshot_access.plan_assets(ad_id, snapshot_time, allowed_advertiser_ids)

    def summary_history(self, limit: int = 144) -> list[dict[str, Any]]:
        return self.snapshot_access.summary_history(limit)

    def account_history(
        self,
        advertiser_id: int,
        limit: int = 72,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        return self.snapshot_access.account_history(advertiser_id, limit, allowed_advertiser_ids)

    def plan_history(
        self,
        ad_id: int,
        limit: int = 72,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        return self.snapshot_access.plan_history(ad_id, limit, allowed_advertiser_ids)

    def persist_token_record(self, payload: dict[str, Any]) -> None:
        self.token_access.persist_token_record(payload)

    def bootstrap_token_store(self) -> None:
        self.token_access.bootstrap_token_store()

    def latest_token_payload(self, masked: bool = False) -> dict[str, Any]:
        return self.token_access.latest_token_payload(masked)

    def exchange_auth_code(self, auth_code: str) -> dict[str, Any]:
        return self.token_access.exchange_auth_code(auth_code)

    def _visible_upload_targets(self, user: dict[str, Any], scope: str, query: str) -> dict[str, Any]:
        return self.upload_access.visible_upload_targets(user, scope, query)

    def _update_material_upload_job(self, conn: Any, job_id: int, **fields: Any) -> None:
        self.upload_access.update_material_upload_job(conn, job_id, **fields)

    def _recompute_material_upload_job_locked(self, conn: Any, job_id: int) -> dict[str, int]:
        return self.upload_access.recompute_material_upload_job_locked(conn, job_id)

    def _material_title_from_filename(self, filename: str) -> str:
        return self.upload_access.material_title_from_filename(filename)

    def _latest_plan_context_map(self, ad_ids: list[int]) -> dict[int, dict[str, Any]]:
        return self.upload_access.latest_plan_context_map(ad_ids)

    def _find_advertiser_material_asset_locked(self, conn: Any, advertiser_id: int, file_sha256: str) -> dict[str, Any] | None:
        return self.upload_access.find_advertiser_material_asset_locked(conn, advertiser_id, file_sha256)

    def _upsert_advertiser_material_asset_locked(
        self,
        conn: Any,
        advertiser_id: int,
        file_sha256: str,
        material_id: str,
        video_id: str,
        video_url: str,
        material_name: str,
    ) -> None:
        self.upload_access.upsert_advertiser_material_asset_locked(
            conn,
            advertiser_id,
            file_sha256,
            material_id,
            video_id,
            video_url,
            material_name,
        )

    def _upsert_material_upload_file_asset_locked(
        self,
        conn: Any,
        job_id: int,
        file_id: int,
        advertiser_id: int,
        advertiser_name: str,
        status: str,
        material_id: str = "",
        video_id: str = "",
        video_url: str = "",
        message: str = "",
    ) -> None:
        self.upload_access.upsert_material_upload_file_asset_locked(
            conn,
            job_id,
            file_id,
            advertiser_id,
            advertiser_name,
            status,
            material_id,
            video_id,
            video_url,
            message,
        )

    def attach_material_upload_task(self, job_id: int, task_id: str) -> None:
        self.upload_access.attach_material_upload_task(job_id, task_id)

    def mark_material_upload_job_failed(self, job_id: int, message: str) -> None:
        self.upload_access.mark_material_upload_job_failed(job_id, message)

    def list_material_upload_jobs(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        return self.upload_access.list_material_upload_jobs(user)

    def _material_upload_job_row_for_user_locked(
        self,
        conn: Any,
        user: dict[str, Any],
        job_id: int,
    ) -> Any:
        role = str(user.get("role") or "")
        if role == ROLE_ADMIN:
            return conn.execute(
                "SELECT * FROM material_upload_jobs WHERE id = ? LIMIT 1",
                (int(job_id),),
            ).fetchone()
        return conn.execute(
            """
            SELECT *
            FROM material_upload_jobs
            WHERE id = ? AND created_by_user_id = ?
            LIMIT 1
            """,
            (int(job_id), int(user.get("id", 0) or 0)),
        ).fetchone()

    def _store_material_upload_file_source(
        self,
        job_id: int,
        index: int,
        source: dict[str, Any],
        created_at: str,
    ) -> tuple[Any, ...]:
        original_name = Path(str(source.get("original_name") or "")).name or f"video-{index}.mp4"
        safe_name = f"{index:03d}_{secrets.token_hex(6)}_{original_name}"
        relative_path = f"{job_id}/{safe_name}"
        destination = UPLOAD_DIR / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = source.get("content")
        if isinstance(content, bytes):
            destination.write_bytes(content)
            file_size = len(content)
            file_sha256 = hashlib.sha256(content).hexdigest()
            file_md5 = hashlib.md5(content).hexdigest()
        else:
            source_path = Path(str(source.get("source_path") or ""))
            if not source_path.exists():
                raise FileNotFoundError(f"source file missing: {source_path}")
            shutil.copy2(source_path, destination)
            file_size = int(source.get("file_size") or 0) or int(destination.stat().st_size)
            file_sha256 = str(source.get("file_sha256") or "")
            file_md5 = str(source.get("file_md5") or "")
            if not file_sha256 or not file_md5:
                copied = destination.read_bytes()
                if not file_sha256:
                    file_sha256 = hashlib.sha256(copied).hexdigest()
                if not file_md5:
                    file_md5 = hashlib.md5(copied).hexdigest()
        return (
            int(job_id),
            original_name,
            safe_name,
            relative_path,
            file_size,
            str(source.get("mime_type") or ""),
            file_sha256,
            file_md5,
            created_at,
            "stored",
            created_at,
        )

    def _create_material_upload_job_locked(
        self,
        conn: Any,
        created_by_user_id: int,
        scope: str,
        query_text: str,
        target_plans: list[dict[str, Any]],
        file_sources: list[dict[str, Any]],
        note: str,
    ) -> dict[str, Any]:
        now = now_text()
        job_row = conn.execute(
            """
            INSERT INTO material_upload_jobs (
                created_by_user_id, scope, query_text, status, total_files, total_targets,
                uploaded_files, processed_files, success_files, failed_files,
                processed_targets, success_targets, failed_targets, note, created_at, updated_at
            ) VALUES (?, ?, ?, 'queued', ?, ?, 0, 0, 0, 0, 0, 0, 0, ?, ?, ?)
            RETURNING *
            """,
            (
                int(created_by_user_id),
                str(scope or "plan"),
                str(query_text or "").strip(),
                len(file_sources),
                len(target_plans),
                str(note or "上传任务已创建，等待后台执行。"),
                now,
                now,
            ),
        ).fetchone()
        job_id = int(job_row["id"])
        (UPLOAD_DIR / str(job_id)).mkdir(parents=True, exist_ok=True)
        file_rows = [
            self._store_material_upload_file_source(job_id, index, source, now)
            for index, source in enumerate(file_sources, start=1)
        ]
        conn.executemany(
            """
            INSERT INTO material_upload_job_files (
                job_id, original_name, stored_name, relative_path, file_size, mime_type,
                file_sha256, file_md5, updated_at, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            file_rows,
        )
        conn.executemany(
            """
            INSERT INTO material_upload_job_targets (
                job_id, advertiser_id, advertiser_name, ad_id, ad_name, status, message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'queued', '', ?, ?)
            """,
            [
                (
                    job_id,
                    int(item["advertiser_id"]),
                    str(item["advertiser_name"]),
                    int(item["ad_id"]),
                    str(item["ad_name"]),
                    now,
                    now,
                )
                for item in target_plans
            ],
        )
        return {
            "id": job_id,
            "status": "queued",
            "scope": str(scope or "plan"),
            "query_text": str(query_text or "").strip(),
            "total_files": len(file_sources),
            "total_targets": len(target_plans),
            "note": str(note or "上传任务已创建，等待后台执行。"),
            "created_at": now,
        }

    def retry_material_upload_job(self, user: dict[str, Any], job_id: int) -> dict[str, Any]:
        role = str(user.get("role") or "")
        if role not in {ROLE_ADMIN, ROLE_SUPERVISOR} or not self.can_upload_materials(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        with self.db() as conn:
            job = self._material_upload_job_row_for_user_locked(conn, user, int(job_id))
            if not job:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="上传任务不存在")
            job = dict(job)
            status_text = str(job.get("status") or "").strip().lower()
            if status_text in {"queued", "running"}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务仍在执行中，暂时不能重试")
            file_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM material_upload_job_files
                    WHERE job_id = ?
                    ORDER BY id ASC
                    """,
                    (int(job_id),),
                ).fetchall()
            ]
            target_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM material_upload_job_targets
                    WHERE job_id = ?
                    ORDER BY advertiser_id ASC, ad_id ASC
                    """,
                    (int(job_id),),
                ).fetchall()
            ]
            retry_file_rows = [
                row for row in file_rows if str(row.get("status") or "").strip().lower() in {"failed", "partial"}
            ]
            retry_target_rows = [
                row for row in target_rows if str(row.get("status") or "").strip().lower() in {"failed", "partial"}
            ]
            if not retry_file_rows and int(job.get("failed_targets", 0) or 0) > 0:
                retry_file_rows = list(file_rows)
            if not retry_target_rows and (
                int(job.get("failed_files", 0) or 0) > 0
                or int(job.get("failed_targets", 0) or 0) > 0
                or status_text in {"failed", "partial"}
            ):
                retry_target_rows = list(target_rows)
            if not retry_file_rows or not retry_target_rows:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前任务没有可重试的失败项")
            file_sources: list[dict[str, Any]] = []
            missing_files = 0
            for row in retry_file_rows:
                source_path = UPLOAD_DIR / str(row.get("relative_path") or "")
                if not source_path.exists():
                    missing_files += 1
                    continue
                file_sources.append(
                    {
                        "original_name": str(row.get("original_name") or ""),
                        "mime_type": str(row.get("mime_type") or ""),
                        "source_path": source_path,
                        "file_size": int(row.get("file_size", 0) or 0),
                        "file_sha256": str(row.get("file_sha256") or ""),
                        "file_md5": str(row.get("file_md5") or ""),
                    }
                )
            if not file_sources:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="失败文件已丢失，无法重试")
            retry_note = f"重试任务来自 #{int(job_id)}，等待后台执行。"
            if missing_files > 0:
                retry_note = f"{retry_note} 已跳过 {missing_files} 个缺失文件。"
            payload = self._create_material_upload_job_locked(
                conn,
                int(user.get("id", 0) or 0),
                str(job.get("scope") or "plan"),
                str(job.get("query_text") or ""),
                [
                    {
                        "advertiser_id": int(item.get("advertiser_id", 0) or 0),
                        "advertiser_name": str(item.get("advertiser_name") or ""),
                        "ad_id": int(item.get("ad_id", 0) or 0),
                        "ad_name": str(item.get("ad_name") or ""),
                    }
                    for item in retry_target_rows
                ],
                file_sources,
                retry_note,
            )
        payload["source_job_id"] = int(job_id)
        payload["retry_file_count"] = len(file_sources)
        payload["retry_target_count"] = len(retry_target_rows)
        if missing_files > 0:
            payload["skipped_missing_files"] = missing_files
        return payload

    def _collect_balance_snapshot(self, client: OceanEngineClient, accounts: list[dict[str, Any]]) -> dict[str, Any]:
        return self.balance_access.collect_balance_snapshot(client, accounts)

    def _snapshot_account_balances(self, conn: Any, snapshot_time: str) -> list[dict[str, Any]]:
        return self.balance_access.snapshot_account_balances(conn, snapshot_time)

    def _snapshot_shared_wallets(self, conn: Any, snapshot_time: str) -> list[dict[str, Any]]:
        return self.balance_access.snapshot_shared_wallets(conn, snapshot_time)

    def _snapshot_wallet_relations(self, conn: Any, snapshot_time: str) -> list[dict[str, Any]]:
        return self.balance_access.snapshot_wallet_relations(conn, snapshot_time)

    def _apply_account_scope(
        self, payload: dict[str, Any], allowed_advertiser_ids: set[int] | None
    ) -> dict[str, Any]:
        return self.performance_access.apply_account_scope(payload, allowed_advertiser_ids)

    def _missing_summary_days(self, conn: Any, start_dt: datetime, end_dt: datetime) -> list[datetime]:
        return self.performance_access.missing_summary_days(conn, start_dt, end_dt)

    def _performance_snapshot_from_db(self, start_dt: datetime, end_dt: datetime) -> dict[str, Any]:
        return self.performance_access.performance_snapshot_from_db(start_dt, end_dt)

    def latest_snapshot(self, allowed_advertiser_ids: set[int] | None = None) -> dict[str, Any] | None:
        return self.performance_access.latest_snapshot(allowed_advertiser_ids)

    def _latest_extended_sync_run(self, conn: Any) -> Any:
        return self.history_access.latest_extended_sync_run(conn)

    def _latest_extended_sync_runs_for_window(
        self, conn: Any, start_dt: datetime, end_dt: datetime
    ) -> list[dict[str, Any]]:
        return self.history_access.latest_extended_sync_runs_for_window(conn, start_dt, end_dt)

    def _summary_meta_for_day(self, conn: Any, target_day: datetime) -> dict[str, Any] | None:
        return self.history_access.summary_meta_for_day(conn, target_day)

    def _missing_extended_days(self, conn: Any, start_dt: datetime, end_dt: datetime) -> list[datetime]:
        return self.history_access.missing_extended_days(conn, start_dt, end_dt)

    def latest_account_catalog(self, allowed_advertiser_ids: set[int] | None = None) -> list[dict[str, Any]]:
        latest = self.latest_snapshot(allowed_advertiser_ids)
        if not latest:
            return []
        items = latest.get("accounts", [])
        return [
            {
                "advertiser_id": int(item.get("advertiser_id", 0) or 0),
                "advertiser_name": str(item.get("advertiser_name") or "").strip(),
            }
            for item in items
        ]

    def _reference_catalog(self) -> dict[str, Any]:
        return self.catalog_access.reference_catalog()

    @staticmethod
    def _normalize_match_text(*values: Any) -> str:
        return " ".join(str(value or "").strip() for value in values if str(value or "").strip()).casefold()

    @staticmethod
    def _report_dimension_value(payload: dict[str, Any], field: str) -> str:
        node = (payload or {}).get(field) or {}
        if isinstance(node, dict):
            return str(node.get("ValueStr") or node.get("Value") or "").strip()
        return str(node or "").strip()

    @staticmethod
    def _report_metric_value(payload: dict[str, Any], field: str) -> float:
        node = (payload or {}).get(field) or {}
        value = node.get("Value") if isinstance(node, dict) else node
        try:
            return round(float(value or 0.0), 2)
        except Exception:
            return 0.0

    def _collect_material_report_metrics_for_advertisers(
        self,
        client: OceanEngineClient,
        advertiser_ids: set[int],
        start_time: str,
        end_time: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        rows: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        material_topics = [str(config["data_topic"]) for config in MATERIAL_REPORT_TOPIC_CONFIGS.values()]
        for advertiser_id in sorted(int(item) for item in advertiser_ids if int(item or 0)):
            available_metrics_by_topic: dict[str, set[str]] = {}
            config_loaded = False
            try:
                config_response = client.get_uni_promotion_config(advertiser_id, material_topics)
                config_loaded = True
                for item in (config_response.get("data") or {}).get("custom_config_datas") or []:
                    data_topic = str(item.get("data_topic") or "").strip()
                    if data_topic not in material_topics:
                        continue
                    available_metrics_by_topic[data_topic] = {
                        str(metric.get("field") or "").strip()
                        for metric in item.get("metrics") or []
                        if str(metric.get("field") or "").strip()
                    }
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "stage": "material_report_config",
                        "advertiser_id": advertiser_id,
                        "error": str(exc),
                    }
                )
            for material_type, config in MATERIAL_REPORT_TOPIC_CONFIGS.items():
                data_topic = str(config["data_topic"])
                requested_metrics = list(config["metrics"])
                if config_loaded and data_topic not in available_metrics_by_topic:
                    errors.append(
                        {
                            "stage": "material_report_topic_missing",
                            "advertiser_id": advertiser_id,
                            "material_type": material_type,
                            "data_topic": data_topic,
                            "error": "topic unavailable in config",
                        }
                    )
                    continue
                available_metrics = available_metrics_by_topic.get(data_topic)
                if available_metrics is not None:
                    requested_metrics = [metric for metric in requested_metrics if metric in available_metrics]
                if not requested_metrics:
                    errors.append(
                        {
                            "stage": "material_report_topic_metrics",
                            "advertiser_id": advertiser_id,
                            "material_type": material_type,
                            "data_topic": data_topic,
                            "error": "no supported metrics available",
                        }
                    )
                    continue
                page = 1
                while True:
                    try:
                        response = client.get_uni_promotion_data(
                            advertiser_id=advertiser_id,
                            data_topic=data_topic,
                            dimensions=list(config["dimensions"]),
                            metrics=requested_metrics,
                            start_time=start_time,
                            end_time=end_time,
                            filters=[],
                            order_by=[{"field": requested_metrics[0], "type": 1}],
                            page=page,
                            page_size=200,
                        )
                    except Exception as exc:  # noqa: BLE001
                        errors.append(
                            {
                                "stage": "material_report_topic",
                                "advertiser_id": advertiser_id,
                                "material_type": material_type,
                                "data_topic": data_topic,
                                "error": str(exc),
                            }
                        )
                        break
                    data = response.get("data") or {}
                    page_rows = data.get("rows") or data.get("list") or []
                    for item in page_rows:
                        dimensions = item.get("dimensions") or {}
                        metrics = item.get("metrics") or {}
                        material_id = self._report_dimension_value(dimensions, "material_id")
                        material_name = ""
                        for field in config["name_fields"]:
                            material_name = self._report_dimension_value(dimensions, str(field))
                            if material_name:
                                break
                        stat_cost = self._report_metric_value(metrics, "stat_cost_for_roi2")
                        pay_amount = self._report_metric_value(metrics, "total_pay_order_gmv_for_roi2")
                        total_pay_amount = self._report_metric_value(metrics, "total_pay_order_gmv_include_coupon_for_roi2")
                        settled_pay_amount = self._report_metric_value(metrics, "total_order_settle_amount_for_roi2_1h")
                        order_count = int(self._report_metric_value(metrics, "total_pay_order_count_for_roi2"))
                        settled_order_count = int(self._report_metric_value(metrics, "total_order_settle_count_for_roi2_1h"))
                        roi = self._report_metric_value(metrics, "total_prepay_and_pay_order_roi2")
                        rows.append(
                            {
                                "advertiser_id": advertiser_id,
                                "material_type": material_type,
                                "material_id": material_id,
                                "material_name": material_name,
                                "stat_cost": stat_cost,
                                "pay_amount": pay_amount,
                                "total_pay_amount": total_pay_amount,
                                "settled_pay_amount": settled_pay_amount,
                                "order_count": order_count,
                                "settled_order_count": settled_order_count,
                                "roi": roi,
                            }
                        )
                    page_info = data.get("page_info") or {}
                    total_page = int(page_info.get("total_page", 1) or 1)
                    if page >= total_page or not page_rows:
                        break
                    page += 1
        return rows, errors

    def _apply_material_report_metrics(
        self,
        groups: dict[str, dict[str, Any]],
        source_rows: list[dict[str, Any]],
        report_rows: list[dict[str, Any]],
    ) -> None:
        if not groups or not source_rows or not report_rows:
            return
        by_id: dict[tuple[int, str, str], dict[str, Any]] = {}
        by_name: dict[tuple[int, str, str], dict[str, Any]] = {}
        report_by_key: dict[str, dict[str, Any]] = {}
        for item in report_rows:
            advertiser_id = int(item.get("advertiser_id", 0) or 0)
            material_type = str(item.get("material_type") or "").strip().upper()
            material_id = str(item.get("material_id") or "").strip()
            material_name = self._normalize_match_text(item.get("material_name"))
            report_key = f"{advertiser_id}:{material_type}:{material_id or material_name}"
            report_by_key[report_key] = item
            if material_id:
                by_id[(advertiser_id, material_type, material_id)] = item
            if material_name:
                by_name[(advertiser_id, material_type, material_name)] = item

        grouped_report_keys: dict[str, set[str]] = {}
        for row in source_rows:
            material_key = str(row.get("material_key") or "").strip()
            advertiser_id = int(row.get("advertiser_id", 0) or 0)
            material_type = str(row.get("material_type") or "").strip().upper()
            material_id = str(row.get("material_id") or "").strip()
            material_name = self._normalize_match_text(row.get("material_name"))
            matched = None
            if material_id:
                matched = by_id.get((advertiser_id, material_type, material_id))
            if matched is None and material_name:
                matched = by_name.get((advertiser_id, material_type, material_name))
            if not matched:
                continue
            report_key = f"{advertiser_id}:{material_type}:{str(matched.get('material_id') or '').strip() or self._normalize_match_text(matched.get('material_name'))}"
            grouped_report_keys.setdefault(material_key, set()).add(report_key)

        for material_key, report_keys in grouped_report_keys.items():
            group = groups.get(material_key)
            if not group:
                continue
            stat_cost = 0.0
            pay_amount = 0.0
            total_pay_amount = 0.0
            settled_pay_amount = 0.0
            order_count = 0
            settled_order_count = 0
            for report_key in report_keys:
                item = report_by_key.get(report_key)
                if not item:
                    continue
                stat_cost = round(stat_cost + float(item.get("stat_cost", 0.0) or 0.0), 2)
                pay_amount = round(pay_amount + float(item.get("pay_amount", 0.0) or 0.0), 2)
                total_pay_amount = round(total_pay_amount + float(item.get("total_pay_amount", 0.0) or 0.0), 2)
                settled_pay_amount = round(settled_pay_amount + float(item.get("settled_pay_amount", 0.0) or 0.0), 2)
                order_count += int(item.get("order_count", 0) or 0)
                settled_order_count += int(item.get("settled_order_count", 0) or 0)
            if (
                stat_cost > 0
                or pay_amount > 0
                or total_pay_amount > 0
                or settled_pay_amount > 0
                or order_count > 0
                or settled_order_count > 0
            ):
                group["stat_cost"] = stat_cost
                group["pay_amount"] = pay_amount
                group["total_pay_amount"] = total_pay_amount
                group["settled_pay_amount"] = settled_pay_amount
                group["order_count"] = order_count
                group["settled_order_count"] = settled_order_count

    def preview_keyword_matches(self, keyword: str, scope: str = "all", allowed_advertiser_ids: set[int] | None = None) -> dict[str, Any]:
        return self.catalog_access.preview_keyword_matches(keyword, scope, allowed_advertiser_ids)

    def read_config(self) -> dict[str, Any]:
        return load_runtime_config(CONFIG_PATH)

    def build_client(self, config: dict[str, Any]) -> OceanEngineClient:
        return OceanEngineClient(
            config=config,
            token_cache_path=TOKEN_CACHE_PATH,
            latest_token_path=LATEST_TOKEN_PATH,
            token_persist_callback=self.persist_token_record,
        )

    @staticmethod
    def _decorate_plan_item(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["plan_source"] = str(item.get("plan_source") or PLAN_SOURCE_UNI_PROMOTION).strip().upper()
        item["plan_source_text"] = "基础投放" if item["plan_source"] == PLAN_SOURCE_STANDARD else "全域投放"
        item["marketing_goal_label"] = plan_marketing_goal_label(item["marketing_goal"])
        if item["marketing_goal_label"]:
            item["marketing_goal_text"] = f"{item['plan_source_text']} / {item['marketing_goal_label']}"
        else:
            item["marketing_goal_text"] = item["plan_source_text"]
        item["status_label"] = plan_delivery_status_label(item["status"])
        item["opt_status_label"] = plan_opt_status_label(item["opt_status"])
        item["status_text"] = format_plan_status_text(item["status"], item["opt_status"])
        item["status_code_text"] = f"{item['status']} / {item['opt_status']}".strip(" /")
        return item

    @staticmethod
    def _plan_ratio(numerator: Any, denominator: Any) -> float:
        denominator_value = float(denominator or 0.0)
        if denominator_value <= 0:
            return 0.0
        return round(float(numerator or 0.0) / denominator_value, 2)

    @staticmethod
    def _plan_percent(numerator: Any, denominator: Any) -> float:
        denominator_value = float(denominator or 0.0)
        if denominator_value <= 0:
            return 0.0
        return round(float(numerator or 0.0) / denominator_value * 100.0, 2)

    @staticmethod
    def _employee_name(value: Any) -> str:
        text = str(value or "").strip()
        return text or "未归属"

    @staticmethod
    def _product_key(item: dict[str, Any]) -> str:
        product_id = str(item.get("product_id") or "").strip()
        product_name = str(item.get("product_name") or "").strip()
        if product_id:
            return f"id:{product_id}"
        if product_name:
            return f"name:{product_name}"
        return "unlinked"

    @staticmethod
    def _product_name(item: dict[str, Any]) -> str:
        product_name = str(item.get("product_name") or "").strip()
        product_id = str(item.get("product_id") or "").strip()
        if product_name:
            return product_name
        if product_id:
            return f"商品 {product_id}"
        return "未关联商品"

    @staticmethod
    def _json_text(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _json_object(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except Exception:
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _first_text(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _detail_material_types(config: dict[str, Any]) -> list[str]:
        values = config.get("detail_material_types") or PLAN_MATERIAL_TYPES
        items: list[str] = []
        for value in values:
            text = str(value or "").strip().upper()
            if text in PLAN_MATERIAL_TYPES and text not in items:
                items.append(text)
        return items or list(PLAN_MATERIAL_TYPES)

    @staticmethod
    def _detail_sync_workers(config: dict[str, Any]) -> int:
        value = int(config.get("detail_sync_workers", 2) or 2)
        return max(1, min(value, 8))

    @staticmethod
    def _detail_sync_plan_limit(config: dict[str, Any]) -> int:
        value = int(config.get("detail_sync_plan_limit", 0) or 0)
        return max(0, value)

    @classmethod
    def _extract_detail_modify_time(cls, detail_data: dict[str, Any]) -> str:
        direct_keys = ("modify_time", "modified_time", "update_time", "updated_time")
        for key in direct_keys:
            text = cls._first_text(detail_data.get(key))
            if text:
                return text
        for section_key in ("base_info", "ad_info", "delivery_setting", "creative_setting"):
            section = detail_data.get(section_key)
            if not isinstance(section, dict):
                continue
            for key in direct_keys:
                text = cls._first_text(section.get(key))
                if text:
                    return text
        return ""

    @classmethod
    def _normalize_plan_detail_row(
        cls,
        snapshot_time: str,
        plan_row: dict[str, Any],
        detail_data: dict[str, Any],
    ) -> tuple[Any, ...]:
        return (
            snapshot_time,
            int(plan_row["advertiser_id"]),
            str(plan_row["advertiser_name"] or ""),
            int(plan_row["ad_id"]),
            str(plan_row["ad_name"] or ""),
            str(plan_row["product_id"] or ""),
            str(plan_row["product_name"] or ""),
            str(plan_row["anchor_name"] or ""),
            str(plan_row["marketing_goal"] or ""),
            str(plan_row["status"] or ""),
            str(plan_row["opt_status"] or ""),
            round(float(plan_row.get("roi_goal", 0.0) or 0.0), 2),
            cls._extract_detail_modify_time(detail_data),
            len(detail_data.get("product_infos") or []),
            len(detail_data.get("room_info") or []),
            1 if detail_data.get("delivery_setting") else 0,
            1 if detail_data.get("creative_setting") else 0,
            cls._json_text(detail_data),
        )

    @classmethod
    def _normalize_product_row(
        cls,
        snapshot_time: str,
        window_start: str,
        window_end: str,
        plan_row: dict[str, Any],
        row: dict[str, Any],
    ) -> tuple[Any, ...]:
        product_info = row.get("product_info") or {}
        stats_info = row.get("stats_info") or {}
        product_id = cls._first_text(product_info.get("product_id"), product_info.get("id"))
        product_name = cls._first_text(product_info.get("product_name"), product_info.get("name"))
        product_key = cls._first_text(product_id, product_name) or "unlinked"
        return (
            snapshot_time,
            window_start,
            window_end,
            int(plan_row["advertiser_id"]),
            str(plan_row["advertiser_name"] or ""),
            int(plan_row["ad_id"]),
            str(plan_row["ad_name"] or ""),
            product_key,
            product_id,
            product_name,
            cls._safe_int(stats_info.get("product_show_count_for_roi2")),
            cls._safe_int(stats_info.get("product_click_count_for_roi2")),
            normalize_plan_money(stats_info.get("stat_cost_for_roi2")),
            normalize_plan_money(stats_info.get("total_pay_order_gmv_for_roi2")),
            cls._safe_int(stats_info.get("total_pay_order_count_for_roi2")),
            round(cls._safe_float(stats_info.get("total_prepay_and_pay_order_roi2")), 2),
            cls._json_text(row),
        )

    @classmethod
    def _extract_material_identity(cls, material_type: str, row: dict[str, Any]) -> dict[str, str]:
        material_info = row.get("material_info") or {}
        preferred_keys = {
            "VIDEO": ["video_material"],
            "IMAGE": ["image_material"],
            "TITLE": ["title_material"],
            "CAROUSEL": ["carousel_material"],
            "LIVE_ROOM": ["live_room_material"],
        }
        candidate_sections: list[dict[str, Any]] = []
        for key in preferred_keys.get(material_type, []):
            value = material_info.get(key)
            if isinstance(value, dict):
                candidate_sections.append(value)
        for value in material_info.values():
            if isinstance(value, dict) and value not in candidate_sections:
                candidate_sections.append(value)
        if not candidate_sections and isinstance(material_info, dict):
            candidate_sections.append(material_info)

        chosen: dict[str, Any] = {}
        for item in candidate_sections:
            if any(
                cls._first_text(item.get(key))
                for key in (
                    "material_id",
                    "id",
                    "video_id",
                    "aweme_id",
                    "room_id",
                    "material_name",
                    "name",
                    "title",
                    "text",
                    "image_url",
                    "cover_url",
                )
            ):
                chosen = item
                break

        material_id = cls._first_text(
            chosen.get("material_id"),
            chosen.get("id"),
            chosen.get("video_id"),
            chosen.get("aweme_id"),
            chosen.get("room_id"),
        )
        video_id = cls._first_text(chosen.get("video_id"), chosen.get("aweme_id"))
        material_name = cls._first_text(
            chosen.get("material_name"),
            chosen.get("name"),
            chosen.get("title"),
            chosen.get("text"),
            chosen.get("video_name"),
            chosen.get("room_name"),
        )
        material_key = cls._first_text(
            material_id,
            video_id,
            chosen.get("image_uri"),
            chosen.get("image_url"),
            chosen.get("cover_url"),
            material_name,
        )
        if not material_key:
            material_key = cls._json_text(material_info)[:200]
        return {
            "material_key": material_key,
            "material_id": material_id,
            "material_name": material_name,
            "video_id": video_id,
        }

    @classmethod
    def _extract_material_preview(cls, material_type: str, row: dict[str, Any]) -> dict[str, str]:
        material_info = cls._json_object(row.get("material_info"))
        preferred_keys = {
            "VIDEO": ["video_material"],
            "IMAGE": ["image_material"],
            "CAROUSEL": ["carousel_material"],
            "LIVE_ROOM": ["live_room_material"],
        }
        candidate_sections: list[dict[str, Any]] = []
        for key in preferred_keys.get(material_type, []):
            value = material_info.get(key)
            if isinstance(value, dict):
                candidate_sections.append(value)
        for value in material_info.values():
            if isinstance(value, dict) and value not in candidate_sections:
                candidate_sections.append(value)
        if not candidate_sections and material_info:
            candidate_sections.append(material_info)
        chosen = candidate_sections[0] if candidate_sections else {}
        cover_image = cls._json_object(chosen.get("cover_image"))
        return {
            "cover_url": cls._first_text(
                chosen.get("cover_url"),
                cover_image.get("image_url"),
                chosen.get("image_url"),
                chosen.get("poster_url"),
            ),
            "aweme_item_id": cls._first_text(
                chosen.get("aweme_item_id"),
                chosen.get("aweme_id"),
                chosen.get("item_id"),
            ),
            "video_url": cls._first_text(
                chosen.get("video_url"),
                chosen.get("play_url"),
                chosen.get("url"),
                chosen.get("material_url"),
            ),
        }

    @classmethod
    def _normalize_material_row(
        cls,
        snapshot_time: str,
        window_start: str,
        window_end: str,
        plan_row: dict[str, Any],
        material_type: str,
        row: dict[str, Any],
    ) -> tuple[Any, ...]:
        stats_info = row.get("stats_info") or {}
        identity = cls._extract_material_identity(material_type, row)
        preview = cls._extract_material_preview(material_type, row)
        return (
            snapshot_time,
            window_start,
            window_end,
            int(plan_row["advertiser_id"]),
            str(plan_row["advertiser_name"] or ""),
            int(plan_row["ad_id"]),
            str(plan_row["ad_name"] or ""),
            material_type,
            identity["material_key"],
            identity["material_id"],
            identity["material_name"],
            identity["video_id"],
            preview["cover_url"],
            preview["aweme_item_id"],
            preview["video_url"],
            cls._safe_int(stats_info.get("product_show_count_for_roi2")),
            cls._safe_int(stats_info.get("product_click_count_for_roi2")),
            normalize_plan_money(stats_info.get("stat_cost_for_roi2")),
            normalize_plan_money(stats_info.get("total_pay_order_gmv_for_roi2")),
            cls._safe_int(stats_info.get("total_pay_order_count_for_roi2")),
            round(cls._safe_float(stats_info.get("total_prepay_and_pay_order_roi2")), 2),
            cls._json_text(row),
        )

    @staticmethod
    def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, str]:
        return (
            int(candidate.get("priority", 100) or 100),
            -int(candidate.get("keyword_length", 0) or 0),
            str(candidate.get("employee_name") or ""),
        )

    def _best_candidate(self, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not candidates:
            return None
        return sorted(candidates, key=self._candidate_sort_key)[0]

    def _best_voted_candidate(self, votes: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
        if not votes:
            return None
        ranked = sorted(
            votes.values(),
            key=lambda item: (
                -int(item.get("count", 0) or 0),
                *self._candidate_sort_key(item["candidate"]),
            ),
        )
        return ranked[0]["candidate"]

    def _active_employee_config(self) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        with self.db() as conn:
            employees = {
                int(row["id"]): {
                    "id": int(row["id"]),
                    "display_name": str(row["display_name"] or "").strip(),
                    "note": str(row["note"] or "").strip(),
                }
                for row in conn.execute(
                    """
                    SELECT id, display_name, note
                    FROM employees
                    WHERE enabled = 1
                    ORDER BY display_name ASC
                    """
                ).fetchall()
            }
            keywords = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, employee_id, keyword, scope, priority, enabled
                    FROM employee_keywords
                    WHERE enabled = 1
                    ORDER BY priority ASC, LENGTH(keyword) DESC, id ASC
                    """
                ).fetchall()
            ]
            bindings = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, employee_id, object_type, object_key, object_label, note
                    FROM employee_manual_bindings
                    ORDER BY object_type ASC, id ASC
                    """
                ).fetchall()
            ]
        keywords = [item for item in keywords if int(item["employee_id"]) in employees]
        bindings = [item for item in bindings if int(item["employee_id"]) in employees]
        return employees, keywords, bindings

    def _operator_config(
        self,
        *,
        include_disabled: bool = False,
        only_user_id: int | None = None,
    ) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
        with self.db() as conn:
            clauses = ["role = ?"]
            params: list[Any] = [ROLE_OPERATOR]
            if not include_disabled:
                clauses.append("enabled = 1")
            if only_user_id is not None:
                clauses.append("id = ?")
                params.append(int(only_user_id))
            users = {
                int(row["id"]): {
                    "id": int(row["id"]),
                    "username": str(row["username"] or "").strip(),
                    "display_name": str(row["display_name"] or "").strip() or str(row["username"] or "").strip(),
                }
                for row in conn.execute(
                    f"""
                    SELECT id, username, display_name
                    FROM app_users
                    WHERE {" AND ".join(clauses)}
                    ORDER BY COALESCE(display_name, username) ASC, id ASC
                    """,
                    params,
                ).fetchall()
            }
            keywords = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, user_id, keyword, enabled
                    FROM user_keywords
                    WHERE enabled = 1
                    ORDER BY LENGTH(keyword) DESC, keyword ASC, id ASC
                    """
                ).fetchall()
            ]
        keywords = [item for item in keywords if int(item["user_id"]) in users]
        return users, keywords

    def _active_operator_config(self) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
        return self._operator_config()

    def _match_operator_candidates(
        self,
        texts: list[str],
        operators: dict[int, dict[str, Any]],
        keywords: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        haystack = self._normalize_match_text(*texts)
        if not haystack:
            return []
        matches: dict[int, dict[str, Any]] = {}
        for row in keywords:
            keyword_text = str(row.get("keyword") or "").strip()
            if not keyword_text or keyword_text.casefold() not in haystack:
                continue
            operator_id = int(row["user_id"])
            operator = operators.get(operator_id)
            if not operator:
                continue
            item = matches.setdefault(
                operator_id,
                {
                    "operator_id": operator_id,
                    "operator_name": str(operator["display_name"]),
                    "operator_username": str(operator["username"]),
                    "matched_keywords": set(),
                },
            )
            item["matched_keywords"].add(keyword_text)
        return sorted(matches.values(), key=lambda item: (str(item["operator_name"]), int(item["operator_id"])))

    def _matched_operators_for_plan(
        self,
        row: dict[str, Any],
        operators: dict[int, dict[str, Any]],
        keywords: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return self._match_operator_candidates(
            [
                str(row.get("advertiser_name") or "").strip(),
                str(row.get("ad_name") or "").strip(),
                str(row.get("product_name") or "").strip(),
                str(row.get("product_id") or "").strip(),
                str(row.get("anchor_name") or "").strip(),
            ],
            operators,
            keywords,
        )

    def _matched_operators_for_material(
        self,
        row: dict[str, Any],
        operators: dict[int, dict[str, Any]],
        keywords: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return self._match_operator_candidates(
            [
                str(row.get("material_name") or "").strip(),
            ],
            operators,
            keywords,
        )

    def _keyword_candidate(
        self,
        employee: dict[str, Any],
        keyword_row: dict[str, Any],
        source: str,
        matched_value: str,
        object_key: str,
    ) -> dict[str, Any]:
        keyword = str(keyword_row.get("keyword") or "").strip()
        return {
            "employee_id": int(employee["id"]),
            "employee_name": str(employee["display_name"]),
            "source": source,
            "source_label": source,
            "priority": int(keyword_row.get("priority", 100) or 100),
            "keyword": keyword,
            "keyword_length": len(keyword),
            "matched_value": matched_value,
            "object_key": object_key,
        }

    def _manual_candidate(
        self,
        employee: dict[str, Any],
        source: str,
        object_key: str,
        matched_value: str,
    ) -> dict[str, Any]:
        return {
            "employee_id": int(employee["id"]),
            "employee_name": str(employee["display_name"]),
            "source": source,
            "source_label": source,
            "priority": 0,
            "keyword": "",
            "keyword_length": 0,
            "matched_value": matched_value,
            "object_key": object_key,
        }

    def _match_text_candidate(
        self,
        texts: list[str],
        scope_value: str,
        keywords: list[dict[str, Any]],
        employees: dict[int, dict[str, Any]],
        object_key: str,
    ) -> dict[str, Any] | None:
        haystack = self._normalize_match_text(*texts)
        if not haystack:
            return None
        candidates: list[dict[str, Any]] = []
        for row in keywords:
            employee = employees.get(int(row["employee_id"]))
            if not employee:
                continue
            keyword_scope = str(row.get("scope") or "all").strip()
            if keyword_scope not in {"all", scope_value}:
                continue
            keyword_text = str(row.get("keyword") or "").strip()
            if keyword_text and keyword_text.casefold() in haystack:
                candidates.append(
                    self._keyword_candidate(
                        employee,
                        row,
                        f"keyword_{scope_value}",
                        texts[0] if texts else object_key,
                        object_key,
                    )
                )
        return self._best_candidate(candidates)

    def _object_binding_maps(
        self,
        employees: dict[int, dict[str, Any]],
        bindings: list[dict[str, Any]],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        result: dict[str, dict[str, dict[str, Any]]] = {
            "account": {},
            "plan": {},
            "product": {},
            "material": {},
        }
        for item in bindings:
            employee = employees.get(int(item["employee_id"]))
            if not employee:
                continue
            object_type = str(item.get("object_type") or "").strip()
            object_key = str(item.get("object_key") or "").strip()
            if object_type not in result or not object_key:
                continue
            result[object_type][object_key] = self._manual_candidate(
                employee,
                f"manual_{object_type}",
                object_key,
                str(item.get("object_label") or object_key),
            )
        return result

    def _product_material_votes(
        self,
        employees: dict[int, dict[str, Any]],
        keywords: list[dict[str, Any]],
        binding_maps: dict[str, dict[str, dict[str, Any]]],
    ) -> tuple[dict[int, dict[int, dict[str, Any]]], dict[int, dict[int, dict[str, Any]]]]:
        catalog = self._reference_catalog()
        product_votes: dict[int, dict[int, dict[str, Any]]] = {}
        material_votes: dict[int, dict[int, dict[str, Any]]] = {}

        for row in catalog["products"]:
            plan_id = int(row.get("ad_id", 0) or 0)
            if not plan_id:
                continue
            product_key = str(row.get("product_key") or "").strip()
            candidate = binding_maps["product"].get(product_key)
            if not candidate:
                candidate = self._match_text_candidate(
                    [
                        str(row.get("product_name") or "").strip(),
                        str(row.get("product_id") or "").strip(),
                        product_key,
                        str(row.get("ad_name") or "").strip(),
                    ],
                    "product",
                    keywords,
                    employees,
                    product_key or str(plan_id),
                )
            if not candidate:
                continue
            plan_votes = product_votes.setdefault(plan_id, {})
            vote = plan_votes.setdefault(
                int(candidate["employee_id"]),
                {"count": 0, "candidate": candidate},
            )
            vote["count"] += 1
            if self._candidate_sort_key(candidate) < self._candidate_sort_key(vote["candidate"]):
                vote["candidate"] = candidate

        for row in catalog["materials"]:
            plan_id = int(row.get("ad_id", 0) or 0)
            if not plan_id:
                continue
            material_key = str(row.get("material_key") or "").strip()
            candidate = binding_maps["material"].get(material_key)
            if not candidate:
                candidate = self._match_text_candidate(
                    [
                        str(row.get("material_name") or "").strip(),
                        str(row.get("material_id") or "").strip(),
                        str(row.get("video_id") or "").strip(),
                        material_key,
                        str(row.get("ad_name") or "").strip(),
                    ],
                    "material",
                    keywords,
                    employees,
                    material_key or str(plan_id),
                )
            if not candidate:
                continue
            plan_votes = material_votes.setdefault(plan_id, {})
            vote = plan_votes.setdefault(
                int(candidate["employee_id"]),
                {"count": 0, "candidate": candidate},
            )
            vote["count"] += 1
            if self._candidate_sort_key(candidate) < self._candidate_sort_key(vote["candidate"]):
                vote["candidate"] = candidate

        return product_votes, material_votes

    def _assign_employee_to_plan(
        self,
        row: dict[str, Any],
        employees: dict[int, dict[str, Any]],
        keywords: list[dict[str, Any]],
        binding_maps: dict[str, dict[str, dict[str, Any]]],
        product_votes: dict[int, dict[int, dict[str, Any]]],
        material_votes: dict[int, dict[int, dict[str, Any]]],
    ) -> dict[str, Any] | None:
        ad_id = int(row.get("ad_id", 0) or 0)
        advertiser_id = int(row.get("advertiser_id", 0) or 0)
        if ad_id and ad_id in material_votes:
            return self._best_voted_candidate(material_votes[ad_id])
        product_key = self._product_key(row)
        if product_key and product_key in binding_maps["product"]:
            return binding_maps["product"][product_key]
        if ad_id and ad_id in product_votes:
            return self._best_voted_candidate(product_votes[ad_id])
        direct_plan = binding_maps["plan"].get(str(ad_id))
        if direct_plan:
            return direct_plan
        direct_account = binding_maps["account"].get(str(advertiser_id))
        if direct_account:
            return direct_account

        plan_candidate = self._match_text_candidate(
            [str(row.get("ad_name") or "").strip(), str(ad_id)],
            "plan",
            keywords,
            employees,
            str(ad_id),
        )
        if plan_candidate:
            return plan_candidate
        account_candidate = self._match_text_candidate(
            [str(row.get("advertiser_name") or "").strip(), str(advertiser_id)],
            "account",
            keywords,
            employees,
            str(advertiser_id),
        )
        if account_candidate:
            return account_candidate
        return None

    def _apply_employee_attribution(
        self,
        plans: list[dict[str, Any]],
        accounts: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        employees, keywords, bindings = self._active_employee_config()
        if not employees:
            fallback_rows: list[dict[str, Any]] = []
            for item in plans:
                row = dict(item)
                row["employee_id"] = None
                row["employee_name"] = self._employee_name(row.get("anchor_name"))
                row["employee_source"] = "legacy_anchor"
                row["employee_source_label"] = "主播字段归属"
                row["employee_keyword"] = ""
                fallback_rows.append(row)
            return fallback_rows

        binding_maps = self._object_binding_maps(employees, bindings)
        product_votes, material_votes = self._product_material_votes(employees, keywords, binding_maps)
        rows: list[dict[str, Any]] = []
        for item in plans:
            row = dict(item)
            assignment = self._assign_employee_to_plan(row, employees, keywords, binding_maps, product_votes, material_votes)
            if assignment:
                row["employee_id"] = int(assignment["employee_id"])
                row["employee_name"] = str(assignment["employee_name"])
                row["employee_source"] = str(assignment["source"])
                row["employee_source_label"] = str(assignment["source_label"])
                row["employee_keyword"] = str(assignment.get("keyword") or "")
                row["employee_matched_value"] = str(assignment.get("matched_value") or "")
            else:
                row["employee_id"] = None
                row["employee_name"] = "未归属"
                row["employee_source"] = "unassigned"
                row["employee_source_label"] = "未命中归属规则"
                row["employee_keyword"] = ""
                row["employee_matched_value"] = ""
            rows.append(row)
        return rows

    def _build_product_rankings(self, plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for row in plans:
            product_key = self._product_key(row)
            employee_name = self._employee_name(row.get("employee_name") or row.get("anchor_name"))
            group = groups.setdefault(
                product_key,
                {
                    "product_key": product_key,
                    "product_id": str(row.get("product_id") or "").strip(),
                    "product_name": self._product_name(row),
                    "stat_cost": 0.0,
                    "pay_amount": 0.0,
                    "order_count": 0,
                    "plan_count": 0,
                    "active_plan_count": 0,
                    "advertiser_ids": set(),
                    "advertiser_names": set(),
                    "employee_names": set(),
                    "top_plan_name": "",
                    "top_plan_orders": -1,
                    "top_plan_pay_amount": -1.0,
                },
            )
            stat_cost = round(float(row.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(row.get("pay_amount", 0.0) or 0.0), 2)
            order_count = int(float(row.get("order_count", 0.0) or 0.0))
            group["stat_cost"] = round(group["stat_cost"] + stat_cost, 2)
            group["pay_amount"] = round(group["pay_amount"] + pay_amount, 2)
            group["order_count"] += order_count
            group["plan_count"] += 1
            if stat_cost > 0:
                group["active_plan_count"] += 1
            group["advertiser_ids"].add(int(row.get("advertiser_id", 0) or 0))
            group["advertiser_names"].add(str(row.get("advertiser_name") or "").strip())
            group["employee_names"].add(employee_name)
            if (
                order_count > group["top_plan_orders"]
                or (order_count == group["top_plan_orders"] and pay_amount > group["top_plan_pay_amount"])
            ):
                group["top_plan_name"] = str(row.get("ad_name") or "").strip()
                group["top_plan_orders"] = order_count
                group["top_plan_pay_amount"] = pay_amount

        rows: list[dict[str, Any]] = []
        for group in groups.values():
            roi = round(group["pay_amount"] / group["stat_cost"], 2) if group["stat_cost"] > 0 else 0.0
            rows.append(
                {
                    "product_key": group["product_key"],
                    "product_id": group["product_id"],
                    "product_name": group["product_name"],
                    "stat_cost": group["stat_cost"],
                    "pay_amount": group["pay_amount"],
                    "order_count": group["order_count"],
                    "plan_count": group["plan_count"],
                    "active_plan_count": group["active_plan_count"],
                    "advertiser_count": len([name for name in group["advertiser_names"] if name]),
                    "employee_count": len(group["employee_names"]),
                    "top_plan_name": group["top_plan_name"],
                    "roi": roi,
                }
            )
        rows.sort(key=lambda item: (-item["order_count"], -item["pay_amount"], -item["roi"], -item["stat_cost"], item["product_name"]))
        return rows

    def _build_employee_rankings(self, plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for row in plans:
            employee_name = self._employee_name(row.get("employee_name") or row.get("anchor_name"))
            employee_id = row.get("employee_id")
            employee_source = str(row.get("employee_source") or "")
            product_key = self._product_key(row)
            group = groups.setdefault(
                employee_name,
                {
                    "employee_id": employee_id,
                    "employee_name": employee_name,
                    "employee_source": employee_source,
                    "stat_cost": 0.0,
                    "pay_amount": 0.0,
                    "order_count": 0,
                    "plan_count": 0,
                    "active_plan_count": 0,
                    "advertiser_names": set(),
                    "product_keys": set(),
                    "top_plan_name": "",
                    "top_plan_orders": -1,
                    "top_plan_pay_amount": -1.0,
                },
            )
            stat_cost = round(float(row.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(row.get("pay_amount", 0.0) or 0.0), 2)
            order_count = int(float(row.get("order_count", 0.0) or 0.0))
            group["stat_cost"] = round(group["stat_cost"] + stat_cost, 2)
            group["pay_amount"] = round(group["pay_amount"] + pay_amount, 2)
            group["order_count"] += order_count
            group["plan_count"] += 1
            if stat_cost > 0:
                group["active_plan_count"] += 1
            advertiser_name = str(row.get("advertiser_name") or "").strip()
            if advertiser_name:
                group["advertiser_names"].add(advertiser_name)
            group["product_keys"].add(product_key)
            if (
                order_count > group["top_plan_orders"]
                or (order_count == group["top_plan_orders"] and pay_amount > group["top_plan_pay_amount"])
            ):
                group["top_plan_name"] = str(row.get("ad_name") or "").strip()
                group["top_plan_orders"] = order_count
                group["top_plan_pay_amount"] = pay_amount

        rows: list[dict[str, Any]] = []
        for group in groups.values():
            roi = round(group["pay_amount"] / group["stat_cost"], 2) if group["stat_cost"] > 0 else 0.0
            rows.append(
                {
                    "employee_id": group["employee_id"],
                    "employee_name": group["employee_name"],
                    "employee_source": group["employee_source"],
                    "stat_cost": group["stat_cost"],
                    "pay_amount": group["pay_amount"],
                    "order_count": group["order_count"],
                    "plan_count": group["plan_count"],
                    "active_plan_count": group["active_plan_count"],
                    "advertiser_count": len(group["advertiser_names"]),
                    "product_count": len(group["product_keys"]),
                    "top_plan_name": group["top_plan_name"],
                    "roi": roi,
                }
            )
        rows.sort(key=lambda item: (-item["pay_amount"], -item["order_count"], -item["roi"], -item["stat_cost"], item["employee_name"]))
        return rows

    def _build_operator_rankings(self, plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
        operators, keywords = self._active_operator_config()
        if not operators or not keywords:
            return []
        groups: dict[int, dict[str, Any]] = {}
        for row in plans:
            matches = self._matched_operators_for_plan(row, operators, keywords)
            if not matches:
                continue
            stat_cost = round(float(row.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(row.get("pay_amount", 0.0) or 0.0), 2)
            order_count = int(float(row.get("order_count", 0.0) or 0.0))
            advertiser_id = int(row.get("advertiser_id", 0) or 0)
            ad_id = int(row.get("ad_id", 0) or 0)
            for match in matches:
                operator_id = int(match["operator_id"])
                group = groups.setdefault(
                    operator_id,
                    {
                        "operator_id": operator_id,
                        "operator_name": str(match["operator_name"]),
                        "operator_username": str(match["operator_username"]),
                        "stat_cost": 0.0,
                        "pay_amount": 0.0,
                        "order_count": 0,
                        "plan_ids": set(),
                        "advertiser_ids": set(),
                        "matched_keywords": set(),
                        "top_plan_name": "",
                        "top_plan_orders": -1,
                        "top_plan_pay_amount": -1.0,
                    },
                )
                group["stat_cost"] = round(group["stat_cost"] + stat_cost, 2)
                group["pay_amount"] = round(group["pay_amount"] + pay_amount, 2)
                group["order_count"] += order_count
                if ad_id:
                    group["plan_ids"].add(ad_id)
                if advertiser_id:
                    group["advertiser_ids"].add(advertiser_id)
                group["matched_keywords"].update(match["matched_keywords"])
                if (
                    order_count > group["top_plan_orders"]
                    or (order_count == group["top_plan_orders"] and pay_amount > group["top_plan_pay_amount"])
                ):
                    group["top_plan_name"] = str(row.get("ad_name") or "").strip()
                    group["top_plan_orders"] = order_count
                    group["top_plan_pay_amount"] = pay_amount

        rows: list[dict[str, Any]] = []
        for group in groups.values():
            roi = round(group["pay_amount"] / group["stat_cost"], 2) if group["stat_cost"] > 0 else 0.0
            rows.append(
                {
                    "operator_id": group["operator_id"],
                    "operator_name": group["operator_name"],
                    "operator_username": group["operator_username"],
                    "stat_cost": group["stat_cost"],
                    "pay_amount": group["pay_amount"],
                    "order_count": group["order_count"],
                    "plan_count": len(group["plan_ids"]),
                    "advertiser_count": len(group["advertiser_ids"]),
                    "keyword_count": len(group["matched_keywords"]),
                    "top_plan_name": group["top_plan_name"],
                    "roi": roi,
                }
            )
        rows.sort(
            key=lambda item: (
                -float(item["stat_cost"]),
                -float(item["pay_amount"]),
                -int(item["order_count"]),
                -float(item["roi"]),
                str(item["operator_name"]),
            )
        )
        return rows

    def _group_material_rows(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            material_key = str(row.get("material_key") or "").strip()
            if not material_key:
                continue
            group = groups.setdefault(
                material_key,
                {
                    "material_key": material_key,
                    "material_id": str(row.get("material_id") or "").strip(),
                    "material_name": str(row.get("material_name") or "").strip() or "未命名素材",
                    "material_type": str(row.get("material_type") or "").strip() or "OTHER",
                    "video_id": str(row.get("video_id") or "").strip(),
                    "cover_url": str(row.get("cover_url") or "").strip(),
                    "aweme_item_id": str(row.get("aweme_item_id") or "").strip(),
                    "video_url": str(row.get("video_url") or "").strip(),
                    "stat_cost": 0.0,
                    "pay_amount": 0.0,
                    "total_pay_amount": 0.0,
                    "settled_pay_amount": 0.0,
                    "order_count": 0,
                    "settled_order_count": 0,
                    "plan_ids": set(),
                    "advertiser_ids": set(),
                    "is_original": False,
                    "top_plan_name": "",
                    "top_plan_orders": -1,
                    "top_plan_pay_amount": -1.0,
                    "top_account_name": "",
                },
            )
            stat_cost = round(float(row.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(row.get("pay_amount", 0.0) or 0.0), 2)
            total_pay_amount = round(float(row.get("total_pay_amount", 0.0) or 0.0), 2)
            settled_pay_amount = round(float(row.get("settled_pay_amount", 0.0) or 0.0), 2)
            order_count = int(float(row.get("order_count", 0.0) or 0.0))
            settled_order_count = int(float(row.get("settled_order_count", 0.0) or 0.0))
            group["stat_cost"] = round(group["stat_cost"] + stat_cost, 2)
            group["pay_amount"] = round(group["pay_amount"] + pay_amount, 2)
            group["total_pay_amount"] = round(group["total_pay_amount"] + total_pay_amount, 2)
            group["settled_pay_amount"] = round(group["settled_pay_amount"] + settled_pay_amount, 2)
            group["order_count"] += order_count
            group["settled_order_count"] += settled_order_count
            group["plan_ids"].add(int(row.get("ad_id", 0) or 0))
            group["advertiser_ids"].add(int(row.get("advertiser_id", 0) or 0))
            group["is_original"] = bool(group["is_original"] or row.get("is_original"))
            if not group["cover_url"]:
                group["cover_url"] = str(row.get("cover_url") or "").strip()
            if not group["aweme_item_id"]:
                group["aweme_item_id"] = str(row.get("aweme_item_id") or "").strip()
            if not group["video_url"]:
                group["video_url"] = str(row.get("video_url") or "").strip()
            if not group["top_account_name"]:
                group["top_account_name"] = str(row.get("advertiser_name") or "").strip()
            if (
                order_count > group["top_plan_orders"]
                or (order_count == group["top_plan_orders"] and pay_amount > group["top_plan_pay_amount"])
            ):
                group["top_plan_name"] = str(row.get("ad_name") or "").strip()
                group["top_plan_orders"] = order_count
                group["top_plan_pay_amount"] = pay_amount
                group["top_account_name"] = str(row.get("advertiser_name") or "").strip()

        return groups

    def _material_rankings_from_groups(self, groups: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        material_rows: list[dict[str, Any]] = []
        for group in groups.values():
            stat_cost = round(float(group.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(group.get("pay_amount", 0.0) or 0.0), 2)
            total_pay_amount = round(float(group.get("total_pay_amount", 0.0) or 0.0), 2)
            settled_pay_amount = round(float(group.get("settled_pay_amount", 0.0) or 0.0), 2)
            order_count = int(group.get("order_count", 0) or 0)
            settled_order_count = int(group.get("settled_order_count", 0) or 0)
            roi = round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0
            settled_roi = round(settled_pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0
            pay_order_cost = round(stat_cost / order_count, 2) if order_count > 0 else 0.0
            settled_amount_rate = round(settled_pay_amount / total_pay_amount * 100.0, 2) if total_pay_amount > 0 else 0.0
            material_rows.append(
                {
                    "material_key": group["material_key"],
                    "material_id": group["material_id"],
                    "material_name": group["material_name"],
                    "material_type": group["material_type"],
                    "video_id": group["video_id"],
                    "cover_url": group.get("cover_url", ""),
                    "aweme_item_id": group.get("aweme_item_id", ""),
                    "video_url": group.get("video_url", ""),
                    "stat_cost": stat_cost,
                    "pay_amount": pay_amount,
                    "total_pay_amount": total_pay_amount,
                    "settled_pay_amount": settled_pay_amount,
                    "order_count": order_count,
                    "settled_order_count": settled_order_count,
                    "plan_count": len(group["plan_ids"]),
                    "advertiser_count": len(group["advertiser_ids"]),
                    "plan_ids": sorted(int(item) for item in group["plan_ids"] if int(item or 0)),
                    "advertiser_ids": sorted(int(item) for item in group["advertiser_ids"] if int(item or 0)),
                    "is_original": bool(group["is_original"]),
                    "top_plan_name": group["top_plan_name"],
                    "top_account_name": group["top_account_name"],
                    "roi": roi,
                    "settled_roi": settled_roi,
                    "pay_order_cost": pay_order_cost,
                    "settled_amount_rate": settled_amount_rate,
                }
            )
        material_rows.sort(
            key=lambda item: (
                -item["order_count"],
                -item["pay_amount"],
                -item["roi"],
                -item["stat_cost"],
                item["material_name"],
            )
        )
        return material_rows

    def _build_material_rankings(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._material_rankings_from_groups(self._group_material_rows(rows))

    def _build_material_rollup_rows(
        self,
        snapshot_time: str,
        window_start: str,
        window_end: str,
        rows: list[dict[str, Any]] | None = None,
        groups: dict[str, dict[str, Any]] | None = None,
    ) -> list[tuple[Any, ...]]:
        material_groups = groups if groups is not None else self._group_material_rows(rows or [])
        rollups: list[tuple[Any, ...]] = []
        for group in material_groups.values():
            stat_cost = round(float(group["stat_cost"] or 0.0), 2)
            pay_amount = round(float(group["pay_amount"] or 0.0), 2)
            total_pay_amount = round(float(group.get("total_pay_amount", 0.0) or 0.0), 2)
            settled_pay_amount = round(float(group.get("settled_pay_amount", 0.0) or 0.0), 2)
            order_count = int(group["order_count"] or 0)
            settled_order_count = int(group.get("settled_order_count", 0) or 0)
            plan_ids = sorted(int(item) for item in group["plan_ids"] if int(item or 0))
            advertiser_ids = sorted(int(item) for item in group["advertiser_ids"] if int(item or 0))
            roi = round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0
            rollups.append(
                (
                    snapshot_time,
                    window_start,
                    window_end,
                    str(group["material_key"] or ""),
                    str(group["material_id"] or ""),
                    str(group["material_name"] or ""),
                    str(group["material_type"] or ""),
                    str(group["video_id"] or ""),
                    str(group.get("cover_url") or ""),
                    str(group.get("aweme_item_id") or ""),
                    str(group.get("video_url") or ""),
                    stat_cost,
                    pay_amount,
                    total_pay_amount,
                    settled_pay_amount,
                    order_count,
                    settled_order_count,
                    len(plan_ids),
                    len(advertiser_ids),
                    json.dumps(plan_ids, ensure_ascii=False),
                    json.dumps(advertiser_ids, ensure_ascii=False),
                    1 if bool(group["is_original"]) else 0,
                    str(group["top_plan_name"] or ""),
                    str(group["top_account_name"] or ""),
                    roi,
                )
            )
        return rollups

    @staticmethod
    def _chunked_material_keys(material_keys: list[str], size: int = 400) -> list[list[str]]:
        items = [str(item or "").strip() for item in material_keys if str(item or "").strip()]
        return [items[index : index + size] for index in range(0, len(items), size)]

    @staticmethod
    def _empty_material_preview_fields() -> dict[str, str]:
        return {
            "video_id": "",
            "cover_url": "",
            "aweme_item_id": "",
            "video_url": "",
        }

    @classmethod
    def _merge_material_preview_fields(cls, target: dict[str, str], row: dict[str, Any]) -> None:
        for field in ("video_id", "cover_url", "aweme_item_id", "video_url"):
            if target.get(field):
                continue
            text = str(row.get(field) or "").strip()
            if text:
                target[field] = text

    @staticmethod
    def _material_preview_available(preview: dict[str, str]) -> bool:
        return any(
            str(preview.get(field) or "").strip()
            for field in ("cover_url", "aweme_item_id", "video_url")
        )

    def _latest_material_preview_map(self, conn: Any, material_keys: list[str]) -> dict[str, dict[str, str]]:
        normalized_keys = sorted({str(item or "").strip() for item in material_keys if str(item or "").strip()})
        if not normalized_keys:
            return {}
        preview_map = {key: self._empty_material_preview_fields() for key in normalized_keys}
        pending = set(normalized_keys)
        for batch in self._chunked_material_keys(normalized_keys):
            placeholders = ",".join("?" for _ in batch)
            rows = conn.execute(
                f"""
                SELECT source.material_key, source.video_id, source.cover_url, source.aweme_item_id, source.video_url
                FROM material_rollups AS source
                JOIN (
                    SELECT material_key, MAX(snapshot_time) AS latest_snapshot_time
                    FROM material_rollups
                    WHERE material_key IN ({placeholders})
                    GROUP BY material_key
                ) latest
                  ON latest.material_key = source.material_key
                 AND latest.latest_snapshot_time = source.snapshot_time
                WHERE source.material_key IN ({placeholders})
                ORDER BY source.material_key ASC
                """,
                [*batch, *batch],
            ).fetchall()
            for raw_row in rows:
                row = dict(raw_row)
                material_key = str(row.get("material_key") or "").strip()
                if not material_key or material_key not in preview_map:
                    continue
                preview = preview_map[material_key]
                self._merge_material_preview_fields(preview, row)
                if self._material_preview_available(preview):
                    pending.discard(material_key)
        for table_name in ("material_rollups", "material_snapshots"):
            if not pending:
                break
            for batch in self._chunked_material_keys(sorted(pending)):
                placeholders = ",".join("?" for _ in batch)
                rows = conn.execute(
                    f"""
                    SELECT material_key, video_id, cover_url, aweme_item_id, video_url
                    FROM {table_name}
                    WHERE material_key IN ({placeholders})
                    ORDER BY material_key ASC, snapshot_time DESC
                    """,
                    batch,
                ).fetchall()
                for raw_row in rows:
                    row = dict(raw_row)
                    material_key = str(row.get("material_key") or "").strip()
                    if not material_key or material_key not in preview_map:
                        continue
                    preview = preview_map[material_key]
                    self._merge_material_preview_fields(preview, row)
                    if self._material_preview_available(preview):
                        pending.discard(material_key)
        return {key: value for key, value in preview_map.items() if any(str(item).strip() for item in value.values())}

    def _apply_latest_material_previews(self, conn: Any, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not items:
            return items
        preview_map = self._latest_material_preview_map(
            conn,
            [str(item.get("material_key") or "").strip() for item in items],
        )
        if not preview_map:
            return items
        for item in items:
            preview = preview_map.get(str(item.get("material_key") or "").strip())
            if not preview:
                continue
            for field in ("video_id", "cover_url", "aweme_item_id", "video_url"):
                text = str(preview.get(field) or "").strip()
                if text:
                    item[field] = text
        return items

    def _aggregate_material_rollups(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            material_key = str(row.get("material_key") or "").strip()
            if not material_key:
                continue
            plan_ids = {int(item) for item in json.loads(str(row.get("plan_ids_json") or "[]")) if int(item or 0)}
            advertiser_ids = {int(item) for item in json.loads(str(row.get("advertiser_ids_json") or "[]")) if int(item or 0)}
            group = groups.get(material_key)
            if group is None:
                group = dict(row)
                group["stat_cost"] = 0.0
                group["pay_amount"] = 0.0
                group["total_pay_amount"] = 0.0
                group["settled_pay_amount"] = 0.0
                group["order_count"] = 0
                group["settled_order_count"] = 0
                group["plan_ids"] = set()
                group["advertiser_ids"] = set()
                group["_top_plan_orders"] = -1
                group["_top_plan_pay_amount"] = -1.0
                groups[material_key] = group
            stat_cost = round(float(row.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(row.get("pay_amount", 0.0) or 0.0), 2)
            total_pay_amount = round(float(row.get("total_pay_amount", 0.0) or 0.0), 2)
            settled_pay_amount = round(float(row.get("settled_pay_amount", 0.0) or 0.0), 2)
            order_count = int(float(row.get("order_count", 0.0) or 0.0))
            settled_order_count = int(float(row.get("settled_order_count", 0.0) or 0.0))
            group["stat_cost"] = round(float(group["stat_cost"] or 0.0) + stat_cost, 2)
            group["pay_amount"] = round(float(group["pay_amount"] or 0.0) + pay_amount, 2)
            group["total_pay_amount"] = round(float(group["total_pay_amount"] or 0.0) + total_pay_amount, 2)
            group["settled_pay_amount"] = round(float(group["settled_pay_amount"] or 0.0) + settled_pay_amount, 2)
            group["order_count"] = int(group["order_count"] or 0) + order_count
            group["settled_order_count"] = int(group["settled_order_count"] or 0) + settled_order_count
            group["plan_ids"].update(plan_ids)
            group["advertiser_ids"].update(advertiser_ids)
            group["is_original"] = bool(group.get("is_original")) or bool(row.get("is_original"))
            if (
                order_count > int(group.get("_top_plan_orders", -1))
                or (
                    order_count == int(group.get("_top_plan_orders", -1))
                    and pay_amount > float(group.get("_top_plan_pay_amount", -1.0))
                )
            ):
                group["top_plan_name"] = str(row.get("top_plan_name") or "")
                group["top_account_name"] = str(row.get("top_account_name") or "")
                group["_top_plan_orders"] = order_count
                group["_top_plan_pay_amount"] = pay_amount

        rankings: list[dict[str, Any]] = []
        for group in groups.values():
            stat_cost = round(float(group.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(group.get("pay_amount", 0.0) or 0.0), 2)
            total_pay_amount = round(float(group.get("total_pay_amount", 0.0) or 0.0), 2)
            settled_pay_amount = round(float(group.get("settled_pay_amount", 0.0) or 0.0), 2)
            order_count = int(group.get("order_count", 0) or 0)
            settled_order_count = int(group.get("settled_order_count", 0) or 0)
            rankings.append(
                {
                    "material_key": str(group.get("material_key") or ""),
                    "material_id": str(group.get("material_id") or ""),
                    "material_name": str(group.get("material_name") or "") or "未命名素材",
                    "material_type": str(group.get("material_type") or "") or "OTHER",
                    "video_id": str(group.get("video_id") or ""),
                    "cover_url": str(group.get("cover_url") or ""),
                    "aweme_item_id": str(group.get("aweme_item_id") or ""),
                    "video_url": str(group.get("video_url") or ""),
                    "stat_cost": stat_cost,
                    "pay_amount": pay_amount,
                    "total_pay_amount": total_pay_amount,
                    "settled_pay_amount": settled_pay_amount,
                    "order_count": order_count,
                    "settled_order_count": settled_order_count,
                    "plan_count": len(group["plan_ids"]),
                    "advertiser_count": len(group["advertiser_ids"]),
                    "plan_ids": sorted(int(item) for item in group["plan_ids"] if int(item or 0)),
                    "advertiser_ids": sorted(int(item) for item in group["advertiser_ids"] if int(item or 0)),
                    "is_original": bool(group.get("is_original")),
                    "top_plan_name": str(group.get("top_plan_name") or ""),
                    "top_account_name": str(group.get("top_account_name") or ""),
                    "roi": round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                    "settled_roi": round(settled_pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                    "pay_order_cost": round(stat_cost / order_count, 2) if order_count > 0 else 0.0,
                    "settled_amount_rate": round(settled_pay_amount / total_pay_amount * 100.0, 2) if total_pay_amount > 0 else 0.0,
                }
            )
        rankings.sort(
            key=lambda item: (
                -int(item["order_count"]),
                -float(item["pay_amount"]),
                -float(item["roi"]),
                -float(item["stat_cost"]),
                str(item["material_name"]),
            )
        )
        return rankings

    def _rankings_bundle(
        self, summary: dict[str, Any], accounts: list[dict[str, Any]], plans: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        products = self._build_product_rankings(plans)
        employees = self._build_employee_rankings(plans)
        operators = self._build_operator_rankings(plans)
        enriched_summary = dict(summary)
        enriched_summary["product_count"] = len(products)
        enriched_summary["active_product_count"] = sum(1 for item in products if float(item["stat_cost"]) > 0)
        enriched_summary["employee_count"] = len(employees)
        enriched_summary["active_employee_count"] = sum(1 for item in employees if float(item["stat_cost"]) > 0)
        enriched_summary["operator_count"] = len(operators)
        enriched_summary["active_operator_count"] = sum(1 for item in operators if float(item["stat_cost"]) > 0)
        enriched_summary["account_count"] = enriched_summary.get("account_count", len(accounts))
        enriched_summary["active_account_count"] = enriched_summary.get(
            "active_account_count",
            sum(1 for item in accounts if bool(item.get("ok", True)) and float(item.get("stat_cost", 0.0) or 0.0) > 0),
        )
        enriched_summary["plan_count"] = enriched_summary.get("plan_count", len(plans))
        enriched_summary["active_plan_count"] = enriched_summary.get(
            "active_plan_count",
            sum(1 for item in plans if float(item.get("stat_cost", 0.0) or 0.0) > 0),
        )
        return enriched_summary, products, employees, operators

    @staticmethod
    def _scoped_summary(accounts: list[dict[str, Any]], plans: list[dict[str, Any]]) -> dict[str, Any]:
        stat_cost = round(sum(float(item.get("stat_cost", 0.0) or 0.0) for item in accounts), 2)
        pay_amount = round(sum(float(item.get("pay_amount", 0.0) or 0.0) for item in accounts), 2)
        order_count = int(sum(int(float(item.get("order_count", 0.0) or 0.0)) for item in accounts))
        roi = round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0
        return {
            "account_count": len(accounts),
            "active_account_count": sum(
                1 for item in accounts if bool(item.get("ok", True)) and float(item.get("stat_cost", 0.0) or 0.0) > 0
            ),
            "plan_count": len(plans),
            "active_plan_count": sum(1 for item in plans if float(item.get("stat_cost", 0.0) or 0.0) > 0),
            "stat_cost": stat_cost,
            "pay_amount": pay_amount,
            "order_count": order_count,
            "roi": roi,
            "account_failures": sum(1 for item in accounts if not bool(item.get("ok", True))),
            "plan_failures": 0,
        }

    def _aggregate_accounts_from_plans(
        self,
        plans: list[dict[str, Any]],
        account_catalog: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        catalog = {int(item.get("advertiser_id", 0) or 0): dict(item) for item in (account_catalog or [])}
        groups: dict[int, dict[str, Any]] = {}
        for row in plans:
            advertiser_id = int(row.get("advertiser_id", 0) or 0)
            if not advertiser_id:
                continue
            base = catalog.get(advertiser_id, {})
            group = groups.setdefault(
                advertiser_id,
                {
                    "advertiser_id": advertiser_id,
                    "advertiser_name": str(row.get("advertiser_name") or base.get("advertiser_name") or advertiser_id),
                    "ok": bool(base.get("ok", True)),
                    "status": str(base.get("status") or ""),
                    "stat_cost": 0.0,
                    "pay_amount": 0.0,
                    "order_count": 0,
                },
            )
            group["stat_cost"] = round(group["stat_cost"] + float(row.get("stat_cost", 0.0) or 0.0), 2)
            group["pay_amount"] = round(group["pay_amount"] + float(row.get("pay_amount", 0.0) or 0.0), 2)
            group["order_count"] += int(float(row.get("order_count", 0.0) or 0.0))
        rows: list[dict[str, Any]] = []
        for item in groups.values():
            stat_cost = round(float(item.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(item.get("pay_amount", 0.0) or 0.0), 2)
            row = dict(item)
            row["roi"] = round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0
            rows.append(row)
        rows.sort(key=lambda item: (-float(item.get("stat_cost", 0.0) or 0.0), int(item.get("advertiser_id", 0) or 0)))
        return rows

    def _filter_plans_for_operator(
        self,
        plans: list[dict[str, Any]],
        user_id: int,
        operators: dict[int, dict[str, Any]] | None = None,
        keywords: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if operators is None or keywords is None:
            operators, keywords = self._active_operator_config()
        if int(user_id or 0) not in operators:
            return []
        result: list[dict[str, Any]] = []
        for row in plans:
            matches = self._matched_operators_for_plan(row, operators, keywords)
            if any(int(item["operator_id"]) == int(user_id) for item in matches):
                result.append(dict(row))
        return result

    def _filter_material_items_for_operator(
        self,
        items: list[dict[str, Any]],
        user_id: int,
        operators: dict[int, dict[str, Any]] | None = None,
        keywords: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if operators is None or keywords is None:
            operators, keywords = self._active_operator_config()
        if int(user_id or 0) not in operators:
            return []
        result: list[dict[str, Any]] = []
        for row in items:
            matches = self._matched_operators_for_material(row, operators, keywords)
            if any(int(item["operator_id"]) == int(user_id) for item in matches):
                result.append(dict(row))
        return result

    def _apply_operator_scope(self, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        user_id = int(user.get("id", 0) or 0)
        operator_plans = self._filter_plans_for_operator(payload.get("plans", []), user_id)
        operator_accounts = self._aggregate_accounts_from_plans(operator_plans, payload.get("accounts", []))
        next_payload = dict(payload)
        next_payload["accounts"] = operator_accounts
        next_payload["plans"] = operator_plans
        next_payload["accountBalances"] = []
        next_payload["sharedWallets"] = []
        next_payload["walletRelations"] = []
        next_payload["summary"], next_payload["products"], next_payload["employees"], _operators = self._rankings_bundle(
            self._scoped_summary(operator_accounts, operator_plans),
            operator_accounts,
            operator_plans,
        )
        next_payload["operators"] = payload.get("operators", [])
        return next_payload

    def _apply_material_scope(self, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        if str(user.get("role") or "") != ROLE_OPERATOR:
            return payload
        next_payload = dict(payload)
        next_payload["items"] = self._filter_material_items_for_operator(payload.get("items", []), int(user.get("id", 0) or 0))
        return next_payload

    def matched_materials_for_user(
        self,
        user_id: int,
        range_key: str = "day",
        start_date: str = "",
        end_date: str = "",
        query: str = "",
    ) -> dict[str, Any]:
        user = self.get_user_by_id(user_id, include_disabled=True)
        if not user or str(user.get("role") or "") != ROLE_OPERATOR:
            return {"items": [], "range_key": range_key, "query": str(query or "").strip()}
        operators, keywords = self._operator_config(include_disabled=True, only_user_id=user_id)
        payload = self.material_rankings(range_key, start_date, end_date, "", None)
        items = self._filter_material_items_for_operator(payload.get("items", []), user_id, operators, keywords)
        query_text = str(query or "").strip().casefold()
        if query_text:
            items = [
                item
                for item in items
                if query_text in self._normalize_match_text(
                    str(item.get("material_name") or ""),
                )
            ]
        return {
            "user": user,
            "items": items[:200],
            "range_key": payload.get("range_key", range_key),
            "range_label": payload.get("range_label", RANGE_LABEL_MAP.get(range_key, "今日")),
            "query": str(query or "").strip(),
            "snapshot_time": payload.get("snapshot_time", ""),
            "snapshot_count": int(payload.get("snapshot_count") or 0),
        }

    def process_material_upload_job(self, job_id: int) -> dict[str, Any]:
        config = self.read_config()
        client = self.build_client(config)
        with self.db() as conn:
            job = conn.execute("SELECT * FROM material_upload_jobs WHERE id = ? LIMIT 1", (int(job_id),)).fetchone()
            if not job:
                raise RuntimeError(f"upload job not found: {job_id}")
            if str(job["status"] or "") == "success":
                return {"job_id": int(job_id), "status": "success", "skipped": True}
            now = now_text()
            self._update_material_upload_job(
                conn,
                int(job_id),
                status="running",
                started_at=str(job.get("started_at") or now),
                note="正在上传素材并绑定计划。",
                updated_at=now,
            )
            file_rows = [dict(row) for row in conn.execute(
                """
                SELECT *
                FROM material_upload_job_files
                WHERE job_id = ?
                ORDER BY id ASC
                """,
                (int(job_id),),
            ).fetchall()]
            target_rows = [dict(row) for row in conn.execute(
                """
                SELECT *
                FROM material_upload_job_targets
                WHERE job_id = ?
                ORDER BY advertiser_id ASC, ad_id ASC
                """,
                (int(job_id),),
            ).fetchall()]
        plan_context_map = self._latest_plan_context_map([int(item["ad_id"]) for item in target_rows])
        advertiser_plan_map: dict[int, list[dict[str, Any]]] = {}
        for target in target_rows:
            advertiser_plan_map.setdefault(int(target["advertiser_id"]), []).append(target)

        file_assets: dict[tuple[int, int], dict[str, str]] = {}
        for file_row in file_rows:
            file_id = int(file_row["id"])
            file_path = UPLOAD_DIR / str(file_row["relative_path"] or "")
            if not file_path.exists():
                with self.db() as conn:
                    conn.execute(
                        """
                        UPDATE material_upload_job_files
                        SET status = 'failed', message = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        ("文件不存在，无法执行上传。", now_text(), file_id),
                    )
                    self._recompute_material_upload_job_locked(conn, int(job_id))
                continue

            success_advertisers = 0
            failed_advertisers = 0
            first_asset: dict[str, str] | None = None
            file_errors: list[str] = []
            for advertiser_id, targets in advertiser_plan_map.items():
                advertiser_name = str(targets[0].get("advertiser_name") or "")
                with self.db() as conn:
                    cached = self._find_advertiser_material_asset_locked(
                        conn,
                        advertiser_id,
                        str(file_row.get("file_sha256") or ""),
                    )
                if cached and str(cached.get("video_id") or ""):
                    asset = {
                        "material_id": str(cached.get("material_id") or ""),
                        "video_id": str(cached.get("video_id") or ""),
                        "video_url": str(cached.get("video_url") or ""),
                    }
                    file_assets[(file_id, advertiser_id)] = asset
                    first_asset = first_asset or asset
                    success_advertisers += 1
                    with self.db() as conn:
                        self._upsert_material_upload_file_asset_locked(
                            conn,
                            int(job_id),
                            file_id,
                            advertiser_id,
                            advertiser_name,
                            "success",
                            material_id=asset["material_id"],
                            video_id=asset["video_id"],
                            video_url=asset["video_url"],
                            message="复用账户已有素材。",
                        )
                    continue
                try:
                    upload_response = client.upload_local_video(
                        advertiser_id=advertiser_id,
                        material_name=str(file_row.get("original_name") or ""),
                        file_path=file_path,
                        video_signature=str(file_row.get("file_md5") or ""),
                        mime_type=str(file_row.get("mime_type") or "video/mp4"),
                    )
                    data = upload_response.get("data") or {}
                    asset = {
                        "material_id": str(data.get("material_id") or ""),
                        "video_id": str(data.get("video_id") or ""),
                        "video_url": str(data.get("video_url") or ""),
                    }
                    if not asset["video_id"]:
                        raise RuntimeError(f"上传响应缺少 video_id: {upload_response}")
                    file_assets[(file_id, advertiser_id)] = asset
                    first_asset = first_asset or asset
                    success_advertisers += 1
                    with self.db() as conn:
                        self._upsert_advertiser_material_asset_locked(
                            conn,
                            advertiser_id,
                            str(file_row.get("file_sha256") or ""),
                            asset["material_id"],
                            asset["video_id"],
                            asset["video_url"],
                            str(file_row.get("original_name") or ""),
                        )
                        self._upsert_material_upload_file_asset_locked(
                            conn,
                            int(job_id),
                            file_id,
                            advertiser_id,
                            advertiser_name,
                            "success",
                            material_id=asset["material_id"],
                            video_id=asset["video_id"],
                            video_url=asset["video_url"],
                            message="上传成功。",
                        )
                except Exception as exc:
                    failed_advertisers += 1
                    message = str(exc)
                    file_errors.append(f"{advertiser_name or advertiser_id}: {message}")
                    with self.db() as conn:
                        self._upsert_material_upload_file_asset_locked(
                            conn,
                            int(job_id),
                            file_id,
                            advertiser_id,
                            advertiser_name,
                            "failed",
                            message=message,
                        )
                with self.db() as conn:
                    conn.execute(
                        """
                        UPDATE material_upload_job_files
                        SET processed_advertisers = ?, success_advertisers = ?, failed_advertisers = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (success_advertisers + failed_advertisers, success_advertisers, failed_advertisers, now_text(), file_id),
                    )
                    self._recompute_material_upload_job_locked(conn, int(job_id))

            file_status = "success" if failed_advertisers == 0 and success_advertisers > 0 else "failed"
            if success_advertisers > 0 and failed_advertisers > 0:
                file_status = "partial"
            message = "上传成功。" if file_status == "success" else "；".join(file_errors[:3]) or "上传失败。"
            with self.db() as conn:
                conn.execute(
                    """
                    UPDATE material_upload_job_files
                    SET status = ?, message = ?, material_id = ?, video_id = ?, video_url = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        file_status,
                        message,
                        str((first_asset or {}).get("material_id") or ""),
                        str((first_asset or {}).get("video_id") or ""),
                        str((first_asset or {}).get("video_url") or ""),
                        now_text(),
                        file_id,
                    ),
                )
                self._recompute_material_upload_job_locked(conn, int(job_id))

        for target in target_rows:
            target_id = int(target["id"])
            advertiser_id = int(target["advertiser_id"])
            ad_id = int(target["ad_id"])
            context = plan_context_map.get(ad_id) or {}
            if not context:
                with self.db() as conn:
                    conn.execute(
                        """
                        UPDATE material_upload_job_targets
                        SET status = 'failed', message = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        ("计划上下文不存在，无法绑定素材。", now_text(), target_id),
                    )
                    self._recompute_material_upload_job_locked(conn, int(job_id))
                continue
            success_count = 0
            failed_count = 0
            bind_errors: list[str] = []
            for file_row in file_rows:
                asset = file_assets.get((int(file_row["id"]), advertiser_id))
                if not asset or not str(asset.get("video_id") or ""):
                    failed_count += 1
                    bind_errors.append(f"{file_row.get('original_name') or file_row.get('stored_name')}: 未上传到账户素材库")
                    continue
                try:
                    client.add_plan_material(
                        advertiser_id=advertiser_id,
                        ad_id=ad_id,
                        material_title=self._material_title_from_filename(str(file_row.get("original_name") or "")),
                        video_id=str(asset.get("video_id") or ""),
                        marketing_goal=str(context.get("marketing_goal") or ""),
                        product_id=str(context.get("product_id") or ""),
                    )
                    success_count += 1
                except Exception as exc:
                    failed_count += 1
                    bind_errors.append(f"{file_row.get('original_name') or file_row.get('stored_name')}: {exc}")
            target_status = "success" if failed_count == 0 and success_count > 0 else "failed"
            if success_count > 0 and failed_count > 0:
                target_status = "partial"
            summary = f"成功 {success_count} / 失败 {failed_count}"
            if bind_errors:
                summary = f"{summary}；{bind_errors[0]}"
            with self.db() as conn:
                conn.execute(
                    """
                    UPDATE material_upload_job_targets
                    SET status = ?, message = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (target_status, summary, now_text(), target_id),
                )
                self._recompute_material_upload_job_locked(conn, int(job_id))

        with self.db() as conn:
            counts = self._recompute_material_upload_job_locked(conn, int(job_id))
            target_rows = conn.execute(
                "SELECT status FROM material_upload_job_targets WHERE job_id = ?",
                (int(job_id),),
            ).fetchall()
            statuses = {str(row["status"] or "") for row in target_rows}
            final_status = "success" if statuses == {"success"} else "failed"
            if "partial" in statuses or ("success" in statuses and "failed" in statuses):
                final_status = "partial"
            if not statuses:
                final_status = "failed"
            note = "素材上传完成。" if final_status == "success" else "素材上传已结束，存在失败项。"
            self._update_material_upload_job(
                conn,
                int(job_id),
                status=final_status,
                note=note,
                completed_at=now_text(),
                updated_at=now_text(),
            )
        return {
            "job_id": int(job_id),
            "status": final_status,
            **counts,
        }

    async def create_material_upload_job(
        self,
        user: dict[str, Any],
        scope: str,
        query: str,
        target_plan_ids: list[int],
        files: list[UploadFile],
    ) -> dict[str, Any]:
        role = str(user.get("role") or "")
        if role not in {ROLE_ADMIN, ROLE_SUPERVISOR} or not self.can_upload_materials(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        normalized_scope = "account" if str(scope or "").strip() == "account" else "plan"
        normalized_target_ids = sorted({int(item) for item in target_plan_ids if int(item or 0) > 0})
        if not normalized_target_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少选择一个计划")
        valid_files = [item for item in files if item and str(item.filename or "").strip()]
        if not valid_files:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少选择一个视频文件")
        if len(valid_files) > 50:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="单次最多上传 50 个视频")

        visible = self._visible_upload_targets(user, normalized_scope, query)
        visible_plan_map = {int(item["ad_id"]): item for item in visible.get("plans", [])}
        target_plans = [visible_plan_map[item] for item in normalized_target_ids if item in visible_plan_map]
        if not target_plans:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="所选计划不在当前可用范围内")

        file_sources = []
        for upload in valid_files:
            content = await upload.read()
            file_sources.append(
                {
                    "original_name": str(upload.filename or ""),
                    "mime_type": str(upload.content_type or ""),
                    "content": content,
                }
            )
        with self.db() as conn:
            return self._create_material_upload_job_locked(
                conn,
                int(user.get("id", 0) or 0),
                normalized_scope,
                str(query or "").strip(),
                target_plans,
                file_sources,
                "上传任务已创建，等待后台执行。",
            )

    def _previous_plan_order_map(self, conn: Any, snapshot_time: str) -> dict[int, int]:
        previous = conn.execute(
            """
            SELECT snapshot_time
            FROM summary_snapshots
            WHERE snapshot_time < ?
            ORDER BY snapshot_time DESC
            LIMIT 1
            """,
            (snapshot_time,),
        ).fetchone()
        if not previous:
            return {}
        rows = conn.execute(
            """
            SELECT ad_id, order_count
            FROM plan_snapshots
            WHERE snapshot_time = ?
            """,
            (str(previous["snapshot_time"]),),
        ).fetchall()
        return {int(row["ad_id"]): int(row["order_count"] or 0) for row in rows}

    @staticmethod
    def _build_burst_rows(plans: list[dict[str, Any]], previous_orders: dict[int, int]) -> list[dict[str, Any]]:
        burst_rows: list[dict[str, Any]] = []
        for row in plans:
            current_orders = int(row.get("order_count", 0) or 0)
            previous = int(previous_orders.get(int(row.get("ad_id", 0) or 0), 0) or 0)
            delta = current_orders - previous
            if delta <= 0:
                continue
            item = dict(row)
            item["burst_order_count"] = delta
            burst_rows.append(item)
        return burst_rows

    def _latest_summary_meta(self, conn: Any) -> Any:
        return conn.execute(
            """
            SELECT snapshot_time, window_start, window_end
            FROM summary_snapshots
            ORDER BY snapshot_time DESC
            LIMIT 1
            """
        ).fetchone()

    def _snapshot_plans(self, conn: Any, snapshot_time: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT *
            FROM plan_snapshots
            WHERE snapshot_time = ?
            ORDER BY order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, ad_id ASC
            """,
            (snapshot_time,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _collect_window_snapshot(
        self,
        start_dt: datetime,
        end_dt: datetime,
        *,
        include_balances: bool = True,
    ) -> dict[str, Any]:
        config = self.read_config()
        client = self.build_client(config)
        accounts = client.list_accounts()
        if include_balances:
            balance_snapshot = self._collect_balance_snapshot(client, accounts)
        else:
            balance_snapshot = {
                "account_balances": [],
                "shared_wallets": [],
                "wallet_relations": [],
                "errors": [],
            }
        account_workers = int(config.get("max_workers", 6) or 6)
        plan_workers = int(config.get("plan_max_workers", 2) or 2)

        summaries: list[AccountSummary] = []
        plans: list[PlanSummary] = []
        failures: list[AccountSummary] = []
        plan_failures: list[str] = []
        plan_failure_ids: set[int] = set()

        with ThreadPoolExecutor(max_workers=account_workers) as pool:
            future_map = {
                pool.submit(fetch_account_bundle, client, item, start_dt, end_dt): item
                for item in accounts
            }
            for future in as_completed(future_map):
                summary = future.result()
                summaries.append(summary)
                if not summary.ok:
                    failures.append(summary)

        with ThreadPoolExecutor(max_workers=plan_workers) as pool:
            future_map = {
                pool.submit(fetch_plan_bundle, client, item, start_dt, end_dt): item
                for item in accounts
            }
            for future in as_completed(future_map):
                item = future_map[future]
                account_plans, plan_error = future.result()
                plans.extend(account_plans)
                if plan_error:
                    plan_failures.append(plan_error)
                    plan_failure_ids.add(int(item["advertiser_id"]))

        plan_rollups: dict[int, dict[str, Any]] = {}
        for item in plans:
            bucket = plan_rollups.setdefault(
                int(item.advertiser_id),
                {
                    "advertiser_name": item.advertiser_name,
                    "stat_cost": 0.0,
                    "pay_amount": 0.0,
                    "order_count": 0,
                },
            )
            bucket["stat_cost"] = round(bucket["stat_cost"] + float(item.stat_cost or 0.0), 2)
            bucket["pay_amount"] = round(bucket["pay_amount"] + float(item.pay_amount or 0.0), 2)
            bucket["order_count"] += int(item.order_count or 0)

        normalized_summaries: list[AccountSummary] = []
        failures = []
        for summary in summaries:
            if summary.ok:
                normalized_summaries.append(summary)
                continue
            if summary.advertiser_id in plan_failure_ids:
                normalized_summaries.append(summary)
                failures.append(summary)
                continue
            fallback = plan_rollups.get(summary.advertiser_id, {})
            fallback_cost = round(float(fallback.get("stat_cost", 0.0) or 0.0), 2)
            fallback_pay = round(float(fallback.get("pay_amount", 0.0) or 0.0), 2)
            fallback_orders = int(fallback.get("order_count", 0) or 0)
            fallback_roi = round(fallback_pay / fallback_cost, 2) if fallback_cost > 0 else 0.0
            normalized_summaries.append(
                AccountSummary(
                    advertiser_id=summary.advertiser_id,
                    advertiser_name=summary.advertiser_name,
                    stat_cost=fallback_cost,
                    roi=fallback_roi,
                    order_count=fallback_orders,
                    pay_amount=fallback_pay,
                    ok=True,
                    error="fallback: plan rollup",
                )
            )

        summaries = normalized_summaries
        summaries.sort(key=lambda item: (-item.stat_cost, item.advertiser_id))
        plans.sort(key=lambda item: (-item.order_count, -item.pay_amount, -item.roi, -item.stat_cost, item.ad_id))

        total_cost = round(sum(item.stat_cost for item in summaries if item.ok), 2)
        total_pay = round(sum(item.pay_amount for item in summaries if item.ok), 2)
        total_orders = sum(item.order_count for item in summaries if item.ok)
        active_accounts = sum(1 for item in summaries if item.ok and item.stat_cost > 0)
        active_plans = [item for item in plans if item.stat_cost > 0]
        total_roi = round(total_pay / total_cost, 2) if total_cost > 0 else 0.0
        snapshot_time = datetime.now(ZoneInfo(config["timezone"])).replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "snapshot_time": snapshot_time,
            "window_start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "window_end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "account_count": len(summaries),
                "active_account_count": active_accounts,
                "plan_count": len(plans),
                "active_plan_count": len(active_plans),
                "stat_cost": total_cost,
                "pay_amount": total_pay,
                "order_count": total_orders,
                "roi": total_roi,
                "account_failures": len(failures),
                "plan_failures": len(plan_failures),
                "wallet_count": len(balance_snapshot["shared_wallets"]),
                "balance_failures": len(balance_snapshot["errors"]),
            },
            "accounts": [asdict(item) for item in summaries],
            "plans": [asdict(item) for item in plans],
            "accountBalances": balance_snapshot["account_balances"],
            "sharedWallets": balance_snapshot["shared_wallets"],
            "walletRelations": balance_snapshot["wallet_relations"],
            "errors": {
                "accounts": [asdict(item) for item in failures],
                "plans": plan_failures,
                "balances": balance_snapshot["errors"],
            },
        }

    def collect_snapshot(self) -> dict[str, Any]:
        config = self.read_config()
        start_dt, end_dt, _title, _label = build_window("intraday", config["timezone"])
        return self._collect_window_snapshot(start_dt, end_dt)

    def backfill_performance_history(self, start_dt: datetime, end_dt: datetime) -> dict[str, Any]:
        tz = ZoneInfo(self.read_config()["timezone"])
        today = datetime.now(tz).date()
        with self.db() as conn:
            missing_days = self._missing_summary_days(conn, start_dt, end_dt)
        backfilled = 0
        skipped_current_day = 0
        for day_marker in missing_days:
            target_day = day_marker.date()
            if target_day >= today:
                skipped_current_day += 1
                continue
            day_start = datetime(target_day.year, target_day.month, target_day.day, 0, 0, 0, tzinfo=tz)
            day_end = datetime(target_day.year, target_day.month, target_day.day, 23, 59, 59, tzinfo=tz)
            payload = self._collect_window_snapshot(day_start, day_end, include_balances=False)
            payload["snapshot_time"] = day_end.strftime("%Y-%m-%d %H:%M:%S")
            payload["window_start"] = day_start.strftime("%Y-%m-%d %H:%M:%S")
            payload["window_end"] = day_end.strftime("%Y-%m-%d %H:%M:%S")
            payload["accountBalances"] = []
            payload["sharedWallets"] = []
            payload["walletRelations"] = []
            if "errors" not in payload or not isinstance(payload["errors"], dict):
                payload["errors"] = {"accounts": [], "plans": [], "balances": []}
            else:
                payload["errors"]["balances"] = []
            self.persist_snapshot(payload)
            backfilled += 1
        if backfilled:
            self._performance_cache.clear()
        return {"backfilled_days": backfilled, "skipped_current_day": skipped_current_day}

    def backfill_extended_history(self, start_dt: datetime, end_dt: datetime) -> dict[str, Any]:
        tz = ZoneInfo(self.read_config()["timezone"])
        today = datetime.now(tz).date()
        self.backfill_performance_history(start_dt, end_dt)
        with self.db() as conn:
            missing_days = self._missing_extended_days(conn, start_dt, end_dt)
        backfilled = 0
        skipped_current_day = 0
        missing_summary_days = 0
        for day_marker in missing_days:
            target_day = day_marker.date()
            if target_day >= today:
                skipped_current_day += 1
                continue
            with self.db() as conn:
                meta = self._summary_meta_for_day(conn, day_marker)
            if not meta:
                missing_summary_days += 1
                continue
            payload = self._collect_extended_snapshot_for_meta(meta)
            if payload.get("skipped"):
                continue
            self.persist_extended_snapshot(payload)
            backfilled += 1
        if backfilled:
            self._material_cache.clear()
        return {
            "backfilled_days": backfilled,
            "skipped_current_day": skipped_current_day,
            "missing_summary_days": missing_summary_days,
        }

    def backfill_recent_performance_history(self, days: int = 30) -> dict[str, Any]:
        tz = ZoneInfo(self.read_config()["timezone"])
        end_dt = datetime.now(tz).replace(hour=23, minute=59, second=59, microsecond=0)
        start_day = (end_dt.date() - timedelta(days=max(int(days or 30) - 1, 0)))
        start_dt = datetime(start_day.year, start_day.month, start_day.day, 0, 0, 0, tzinfo=tz)
        result = self.backfill_performance_history(start_dt, end_dt)
        result.update(
            {
                "range_start": start_dt.strftime("%Y-%m-%d"),
                "range_end": end_dt.strftime("%Y-%m-%d"),
                "days": max(int(days or 30), 1),
            }
        )
        return result

    def backfill_recent_extended_history(self, days: int = 30) -> dict[str, Any]:
        tz = ZoneInfo(self.read_config()["timezone"])
        end_dt = datetime.now(tz).replace(hour=23, minute=59, second=59, microsecond=0)
        start_day = (end_dt.date() - timedelta(days=max(int(days or 30) - 1, 0)))
        start_dt = datetime(start_day.year, start_day.month, start_day.day, 0, 0, 0, tzinfo=tz)
        result = self.backfill_extended_history(start_dt, end_dt)
        result.update(
            {
                "range_start": start_dt.strftime("%Y-%m-%d"),
                "range_end": end_dt.strftime("%Y-%m-%d"),
                "days": max(int(days or 30), 1),
            }
        )
        return result

    def persist_snapshot(self, payload: dict[str, Any]) -> None:
        with self.db() as conn:
            conn.execute(
                """
                INSERT INTO summary_snapshots (
                    snapshot_time, window_start, window_end, account_count, active_account_count,
                    plan_count, active_plan_count, stat_cost, pay_amount, order_count, roi,
                    account_failures, plan_failures
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (snapshot_time) DO UPDATE SET
                    window_start = excluded.window_start,
                    window_end = excluded.window_end,
                    account_count = excluded.account_count,
                    active_account_count = excluded.active_account_count,
                    plan_count = excluded.plan_count,
                    active_plan_count = excluded.active_plan_count,
                    stat_cost = excluded.stat_cost,
                    pay_amount = excluded.pay_amount,
                    order_count = excluded.order_count,
                    roi = excluded.roi,
                    account_failures = excluded.account_failures,
                    plan_failures = excluded.plan_failures
                """,
                (
                    payload["snapshot_time"],
                    payload["window_start"],
                    payload["window_end"],
                    payload["summary"]["account_count"],
                    payload["summary"]["active_account_count"],
                    payload["summary"]["plan_count"],
                    payload["summary"]["active_plan_count"],
                    payload["summary"]["stat_cost"],
                    payload["summary"]["pay_amount"],
                    payload["summary"]["order_count"],
                    payload["summary"]["roi"],
                    payload["summary"]["account_failures"],
                    payload["summary"]["plan_failures"],
                ),
            )
            conn.execute("DELETE FROM account_snapshots WHERE snapshot_time = ?", (payload["snapshot_time"],))
            conn.execute("DELETE FROM plan_snapshots WHERE snapshot_time = ?", (payload["snapshot_time"],))
            conn.execute("DELETE FROM account_balances WHERE snapshot_time = ?", (payload["snapshot_time"],))
            conn.execute("DELETE FROM shared_wallets WHERE snapshot_time = ?", (payload["snapshot_time"],))
            conn.execute("DELETE FROM shared_wallet_account_relations WHERE snapshot_time = ?", (payload["snapshot_time"],))
            conn.executemany(
                """
                INSERT INTO account_snapshots (
                    snapshot_time, advertiser_id, advertiser_name, stat_cost, roi,
                    order_count, pay_amount, ok, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        payload["snapshot_time"],
                        item["advertiser_id"],
                        item["advertiser_name"],
                        item["stat_cost"],
                        item["roi"],
                        item["order_count"],
                        item["pay_amount"],
                        1 if item["ok"] else 0,
                        item["error"],
                    )
                    for item in payload["accounts"]
                ],
            )
            conn.executemany(
                """
                INSERT INTO plan_snapshots (
                    snapshot_time, advertiser_id, advertiser_name, ad_id, ad_name,
                    product_id, product_name, anchor_name, marketing_goal, plan_source, status,
                    opt_status, roi_goal, stat_cost, roi, order_count, pay_amount,
                    total_pay_amount, settled_pay_amount, settled_roi, settled_order_count,
                    pay_order_cost, settled_amount_rate, refund_rate_1h, refund_amount_1h
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        payload["snapshot_time"],
                        item["advertiser_id"],
                        item["advertiser_name"],
                        item["ad_id"],
                        item["ad_name"],
                        item["product_id"],
                        item["product_name"],
                        item["anchor_name"],
                        item["marketing_goal"],
                        item.get("plan_source", PLAN_SOURCE_UNI_PROMOTION),
                        item["status"],
                        item["opt_status"],
                        item["roi_goal"],
                        item["stat_cost"],
                        item["roi"],
                        item["order_count"],
                        item["pay_amount"],
                        item.get("total_pay_amount", 0.0),
                        item.get("settled_pay_amount", 0.0),
                        item.get("settled_roi", 0.0),
                        item.get("settled_order_count", 0),
                        item.get("pay_order_cost", 0.0),
                        item.get("settled_amount_rate", 0.0),
                        item.get("refund_rate_1h", 0.0),
                        item.get("refund_amount_1h", 0.0),
                    )
                    for item in payload["plans"]
                ],
            )
            if payload.get("accountBalances"):
                conn.executemany(
                    """
                    INSERT INTO account_balances (
                        snapshot_time, advertiser_id, advertiser_name, account_balance,
                        available_balance, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            payload["snapshot_time"],
                            item["advertiser_id"],
                            item["advertiser_name"],
                            item["account_balance"],
                            item["available_balance"],
                            item["raw_json"],
                        )
                        for item in payload["accountBalances"]
                    ],
                )
            if payload.get("sharedWallets"):
                conn.executemany(
                    """
                    INSERT INTO shared_wallets (
                        snapshot_time, main_wallet_id, wallet_name, total_balance,
                        valid_balance, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            payload["snapshot_time"],
                            item["main_wallet_id"],
                            item["wallet_name"],
                            item["total_balance"],
                            item["valid_balance"],
                            item["raw_json"],
                        )
                        for item in payload["sharedWallets"]
                    ],
                )
            if payload.get("walletRelations"):
                conn.executemany(
                    """
                    INSERT INTO shared_wallet_account_relations (
                        snapshot_time, main_wallet_id, advertiser_id, child_wallet_id,
                        wallet_name, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            payload["snapshot_time"],
                            item["main_wallet_id"],
                            item["advertiser_id"],
                            item["child_wallet_id"],
                            item["wallet_name"],
                            item["raw_json"],
                        )
                        for item in payload["walletRelations"]
                    ],
                )

    def _collect_plan_assets_bundle(
        self,
        client: OceanEngineClient,
        snapshot_time: str,
        window_start: str,
        window_end: str,
        start_date: str,
        end_date: str,
        material_types: list[str],
        plan_row: dict[str, Any],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "detail_row": None,
            "product_rows": [],
            "material_rows": [],
            "video_material_ids": [],
            "errors": [],
        }
        advertiser_id = int(plan_row["advertiser_id"])
        ad_id = int(plan_row["ad_id"])

        try:
            detail_response = client.get_plan_detail(advertiser_id, ad_id)
            detail_data = detail_response.get("data") or {}
            result["detail_row"] = self._normalize_plan_detail_row(snapshot_time, plan_row, detail_data)
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(
                {
                    "stage": "plan_detail",
                    "advertiser_id": advertiser_id,
                    "ad_id": ad_id,
                    "error": str(exc),
                }
            )

        try:
            products = client.list_plan_products(
                advertiser_id=advertiser_id,
                ad_id=ad_id,
                start_date=start_date,
                end_date=end_date,
                fields=PLAN_PRODUCT_FIELDS,
            )
            result["product_rows"] = [
                self._normalize_product_row(snapshot_time, window_start, window_end, plan_row, row)
                for row in products
            ]
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(
                {
                    "stage": "plan_products",
                    "advertiser_id": advertiser_id,
                    "ad_id": ad_id,
                    "error": str(exc),
                }
            )

        material_rows: list[tuple[Any, ...]] = []
        video_material_ids: list[str] = []
        for material_type in material_types:
            if material_type == "LIVE_ROOM" and str(plan_row.get("marketing_goal") or "") != "LIVE_PROM_GOODS":
                continue
            filtering: dict[str, Any] = {
                "material_type": material_type,
                "start_date": start_date,
                "end_date": end_date,
                "material_status": "ALL",
            }
            if material_type == "VIDEO":
                filtering["video_type"] = "ALL"
            try:
                materials = client.list_plan_materials(
                    advertiser_id=advertiser_id,
                    ad_id=ad_id,
                    filtering=filtering,
                    fields=plan_material_fields_for_type(material_type),
                )
                for row in materials:
                    normalized = self._normalize_material_row(
                        snapshot_time,
                        window_start,
                        window_end,
                        plan_row,
                        material_type,
                        row,
                    )
                    material_rows.append(normalized)
                    if material_type == "VIDEO":
                        material_id = str(normalized[9] or "").strip()
                        if material_id:
                            video_material_ids.append(material_id)
            except Exception as exc:  # noqa: BLE001
                result["errors"].append(
                    {
                        "stage": "plan_materials",
                        "advertiser_id": advertiser_id,
                        "ad_id": ad_id,
                        "material_type": material_type,
                        "error": str(exc),
                    }
                )
        result["material_rows"] = material_rows
        result["video_material_ids"] = sorted(set(video_material_ids))
        return result

    def _collect_extended_snapshot_for_meta(self, meta: dict[str, Any]) -> dict[str, Any]:
        config = self.read_config()
        with self.db() as conn:
            plans = self._snapshot_plans(conn, str(meta["snapshot_time"]))
        plans = [
            row
            for row in plans
            if str(row.get("plan_source") or PLAN_SOURCE_UNI_PROMOTION).strip().upper() == PLAN_SOURCE_UNI_PROMOTION
        ]

        plan_limit = self._detail_sync_plan_limit(config)
        if plan_limit > 0:
            plans = plans[:plan_limit]
        material_types = self._detail_material_types(config)
        workers = self._detail_sync_workers(config)
        start_date = str(meta["window_start"])[:10]
        end_date = str(meta["window_end"])[:10]
        snapshot_time = str(meta["snapshot_time"])
        window_start = str(meta["window_start"])
        window_end = str(meta["window_end"])

        client = self.build_client(config)
        detail_rows: list[tuple[Any, ...]] = []
        product_rows: list[tuple[Any, ...]] = []
        material_rows: list[tuple[Any, ...]] = []
        errors: list[dict[str, Any]] = []
        video_material_ids_by_advertiser: dict[int, set[str]] = {}
        material_report_rows: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(
                    self._collect_plan_assets_bundle,
                    client,
                    snapshot_time,
                    window_start,
                    window_end,
                    start_date,
                    end_date,
                    material_types,
                    row,
                ): row
                for row in plans
            }
            for future in as_completed(future_map):
                plan_row = future_map[future]
                try:
                    payload = future.result()
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "stage": "plan_assets_bundle",
                            "advertiser_id": int(plan_row["advertiser_id"]),
                            "ad_id": int(plan_row["ad_id"]),
                            "error": str(exc),
                        }
                    )
                    continue
                if payload["detail_row"] is not None:
                    detail_rows.append(payload["detail_row"])
                product_rows.extend(payload["product_rows"])
                material_rows.extend(payload["material_rows"])
                errors.extend(payload["errors"])
                advertiser_id = int(plan_row["advertiser_id"])
                bucket = video_material_ids_by_advertiser.setdefault(advertiser_id, set())
                bucket.update(payload["video_material_ids"])

        advertiser_ids = {int(row.get("advertiser_id", 0) or 0) for row in plans if int(row.get("advertiser_id", 0) or 0)}
        report_rows, report_errors = self._collect_material_report_metrics_for_advertisers(
            client,
            advertiser_ids,
            window_start,
            window_end,
        )
        material_report_rows.extend(report_rows)
        errors.extend(report_errors)

        video_flag_rows: list[tuple[Any, ...]] = []
        for advertiser_id, material_ids in sorted(video_material_ids_by_advertiser.items()):
            if not material_ids:
                continue
            sorted_ids = sorted(material_ids)
            for start_index in range(0, len(sorted_ids), 100):
                batch = sorted_ids[start_index : start_index + 100]
                try:
                    response = client.get_original_videos(advertiser_id, batch)
                    data = response.get("data") or {}
                    original_ids = {str(item) for item in (data.get("original_material_ids") or [])}
                    raw_json = self._json_text(
                        {
                            "query_material_ids": batch,
                            "original_material_ids": list(original_ids),
                            "response": data,
                        }
                    )
                    for material_id in batch:
                        video_flag_rows.append(
                            (
                                snapshot_time,
                                advertiser_id,
                                str(material_id),
                                1 if str(material_id) in original_ids else 0,
                                raw_json,
                            )
                        )
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "stage": "video_original",
                            "advertiser_id": advertiser_id,
                            "material_ids": batch,
                            "error": str(exc),
                        }
                    )

        return {
            "ok": True,
            "skipped": False,
            "snapshot_time": snapshot_time,
            "window_start": window_start,
            "window_end": window_end,
            "plan_count": len(plans),
            "detail_rows": detail_rows,
            "product_rows": product_rows,
            "material_rows": material_rows,
            "material_report_rows": material_report_rows,
            "video_flag_rows": video_flag_rows,
            "errors": errors,
        }

    def collect_extended_snapshot(self) -> dict[str, Any]:
        with self.db() as conn:
            meta = self._latest_summary_meta(conn)
            if not meta:
                return {
                    "ok": False,
                    "skipped": True,
                    "reason": "missing summary snapshot",
                }
            existing = conn.execute(
                "SELECT status FROM extended_sync_runs WHERE snapshot_time = ?",
                (meta["snapshot_time"],),
            ).fetchone()
            if existing and str(existing["status"]) == "ok":
                return {
                    "ok": True,
                    "skipped": True,
                    "snapshot_time": meta["snapshot_time"],
                    "reason": "already synced",
                }
        return self._collect_extended_snapshot_for_meta(dict(meta))

    def persist_extended_snapshot(self, payload: dict[str, Any]) -> None:
        if payload.get("skipped"):
            return
        original_material_keys: set[tuple[int, str]] = {
            (int(row[1]), str(row[2]))
            for row in payload["video_flag_rows"]
            if int(row[3] or 0) == 1
        }
        material_source_rows: list[dict[str, Any]] = []
        for row in payload["material_rows"]:
            advertiser_id = int(row[3])
            material_id = str(row[9] or "")
            material_source_rows.append(
                {
                    "snapshot_time": row[0],
                    "window_start": row[1],
                    "window_end": row[2],
                    "advertiser_id": advertiser_id,
                    "advertiser_name": row[4],
                    "ad_id": int(row[5]),
                    "ad_name": row[6],
                    "material_type": row[7],
                    "material_key": row[8],
                    "material_id": material_id,
                    "material_name": row[10],
                    "video_id": row[11],
                    "cover_url": row[12],
                    "aweme_item_id": row[13],
                    "video_url": row[14],
                    "stat_cost": row[17],
                    "pay_amount": row[18],
                    "order_count": row[19],
                    "is_original": (advertiser_id, material_id) in original_material_keys,
                }
            )
        material_groups = self._group_material_rows(material_source_rows)
        self._apply_material_report_metrics(
            material_groups,
            material_source_rows,
            list(payload.get("material_report_rows") or []),
        )
        material_rollup_rows = self._build_material_rollup_rows(
            payload["snapshot_time"],
            payload["window_start"],
            payload["window_end"],
            groups=material_groups,
        )
        with self.db() as conn:
            conn.execute("DELETE FROM plan_detail_snapshots WHERE snapshot_time = ?", (payload["snapshot_time"],))
            conn.execute("DELETE FROM product_snapshots WHERE snapshot_time = ?", (payload["snapshot_time"],))
            conn.execute("DELETE FROM material_snapshots WHERE snapshot_time = ?", (payload["snapshot_time"],))
            conn.execute("DELETE FROM material_rollups WHERE snapshot_time = ?", (payload["snapshot_time"],))
            conn.execute("DELETE FROM video_origin_flags WHERE snapshot_time = ?", (payload["snapshot_time"],))
            if payload["detail_rows"]:
                conn.executemany(
                    """
                    INSERT INTO plan_detail_snapshots (
                        snapshot_time, advertiser_id, advertiser_name, ad_id, ad_name,
                        product_id, product_name, anchor_name, marketing_goal, status,
                        opt_status, roi_goal, modify_time, product_count, room_count,
                        has_delivery_setting, has_creative_setting, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload["detail_rows"],
                )
            if payload["product_rows"]:
                conn.executemany(
                    """
                    INSERT INTO product_snapshots (
                        snapshot_time, window_start, window_end, advertiser_id, advertiser_name,
                        ad_id, ad_name, product_key, product_id, product_name,
                        product_show_count, product_click_count, stat_cost, pay_amount,
                        order_count, roi, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload["product_rows"],
                )
            if payload["material_rows"]:
                conn.executemany(
                    """
                    INSERT INTO material_snapshots (
                        snapshot_time, window_start, window_end, advertiser_id, advertiser_name,
                        ad_id, ad_name, material_type, material_key, material_id, material_name,
                        video_id, cover_url, aweme_item_id, video_url, product_show_count,
                        product_click_count, stat_cost, pay_amount, order_count, roi, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload["material_rows"],
                )
            if material_rollup_rows:
                conn.executemany(
                    """
                    INSERT INTO material_rollups (
                        snapshot_time, window_start, window_end, material_key, material_id,
                        material_name, material_type, video_id, cover_url, aweme_item_id, video_url, stat_cost, pay_amount,
                        total_pay_amount, settled_pay_amount, order_count, settled_order_count, plan_count, advertiser_count,
                        plan_ids_json, advertiser_ids_json, is_original, top_plan_name, top_account_name, roi
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    material_rollup_rows,
                )
            if payload["video_flag_rows"]:
                conn.executemany(
                    """
                    INSERT INTO video_origin_flags (
                        snapshot_time, advertiser_id, material_id, is_original, raw_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    payload["video_flag_rows"],
                )
            conn.execute(
                """
                INSERT INTO extended_sync_runs (
                    snapshot_time, window_start, window_end, status, plan_count, detail_count,
                    product_row_count, material_row_count, original_video_row_count,
                    error_count, error_json, created_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (snapshot_time) DO UPDATE SET
                    window_start = excluded.window_start,
                    window_end = excluded.window_end,
                    status = excluded.status,
                    plan_count = excluded.plan_count,
                    detail_count = excluded.detail_count,
                    product_row_count = excluded.product_row_count,
                    material_row_count = excluded.material_row_count,
                    original_video_row_count = excluded.original_video_row_count,
                    error_count = excluded.error_count,
                    error_json = excluded.error_json,
                    created_at = excluded.created_at,
                    finished_at = excluded.finished_at
                """,
                (
                    payload["snapshot_time"],
                    payload["window_start"],
                    payload["window_end"],
                    "ok" if not payload["errors"] else "partial",
                    payload["plan_count"],
                    len(payload["detail_rows"]),
                    len(payload["product_rows"]),
                    len(payload["material_rows"]),
                    len(payload["video_flag_rows"]),
                    len(payload["errors"]),
                    self._json_text(payload["errors"]),
                    now_text(),
                    now_text(),
                ),
            )

    def cleanup_history(self) -> None:
        cutoff = (datetime.now(ZoneInfo(TIMEZONE)) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        with self.db() as conn:
            conn.execute("DELETE FROM summary_snapshots WHERE snapshot_time < ?", (cutoff,))
            conn.execute("DELETE FROM account_snapshots WHERE snapshot_time < ?", (cutoff,))
            conn.execute("DELETE FROM plan_snapshots WHERE snapshot_time < ?", (cutoff,))
            conn.execute("DELETE FROM account_balances WHERE snapshot_time < ?", (cutoff,))
            conn.execute("DELETE FROM shared_wallets WHERE snapshot_time < ?", (cutoff,))
            conn.execute("DELETE FROM shared_wallet_account_relations WHERE snapshot_time < ?", (cutoff,))
            conn.execute("DELETE FROM plan_detail_snapshots WHERE snapshot_time < ?", (cutoff,))
            conn.execute("DELETE FROM product_snapshots WHERE snapshot_time < ?", (cutoff,))
            conn.execute("DELETE FROM material_snapshots WHERE snapshot_time < ?", (cutoff,))
            conn.execute("DELETE FROM material_rollups WHERE snapshot_time < ?", (cutoff,))
            conn.execute("DELETE FROM video_origin_flags WHERE snapshot_time < ?", (cutoff,))
            conn.execute("DELETE FROM extended_sync_runs WHERE snapshot_time < ?", (cutoff,))

    def evaluate_alerts(self, payload: dict[str, Any]) -> None:
        with self.db() as conn:
            rules = conn.execute(
                """
                SELECT * FROM alert_rules
                WHERE enabled = 1
                ORDER BY id ASC
                """
            ).fetchall()
            if not rules:
                return

            latest_accounts = [item for item in payload["accounts"] if item["ok"]]
            latest_plans = payload["plans"]
            latest_account_balances = payload.get("accountBalances", [])
            latest_wallets = payload.get("sharedWallets", [])
            now_text = payload["snapshot_time"]
            burst_rows = self._build_burst_rows(latest_plans, self._previous_plan_order_map(conn, now_text))

            for rule in rules:
                entity_type = str(rule["entity_type"] or "")
                metric = str(rule["metric"] or "")
                if entity_type == "account":
                    rows = latest_accounts
                    entity_id_field = "advertiser_id"
                    entity_name_field = "advertiser_name"
                elif entity_type in {"plan", "burst_plan"}:
                    rows = burst_rows if entity_type == "burst_plan" else latest_plans
                    entity_id_field = "ad_id"
                    entity_name_field = "ad_name"
                elif entity_type == "account_balance":
                    rows = latest_account_balances
                    entity_id_field = "advertiser_id"
                    entity_name_field = "advertiser_name"
                elif entity_type == "shared_wallet":
                    rows = latest_wallets
                    entity_id_field = "main_wallet_id"
                    entity_name_field = "wallet_name"
                else:
                    continue
                for row in rows:
                    if metric not in row:
                        continue
                    entity_id = str(row[entity_id_field])
                    if rule["target_id"] and rule["target_id"] != entity_id:
                        continue
                    if entity_type in {"account", "plan", "burst_plan"} and float(row["stat_cost"]) < float(rule["min_spend"]):
                        continue
                    current_value = float(row[metric])
                    if not self._compare(current_value, str(rule["operator"]), float(rule["threshold"])):
                        continue
                    recent = conn.execute(
                        """
                        SELECT id FROM alert_events
                        WHERE rule_id = ? AND entity_id = ? AND created_at >= ?
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (
                            rule["id"],
                            entity_id,
                            (
                                datetime.fromisoformat(now_text)
                                - timedelta(minutes=int(rule["cooldown_minutes"] or ALERT_COOLDOWN_DEFAULT))
                            ).strftime("%Y-%m-%d %H:%M:%S"),
                        ),
                    ).fetchone()
                    if recent:
                        continue
                    entity_name = row[entity_name_field]
                    message = self._build_alert_message(rule, row, now_text)
                    conn.execute(
                        """
                        INSERT INTO alert_events (
                            rule_id, snapshot_time, entity_type, entity_id, entity_name,
                            metric, operator, threshold, current_value, stat_cost, pay_amount,
                            order_count, roi, message, status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                        """,
                        (
                            rule["id"],
                            payload["snapshot_time"],
                            rule["entity_type"],
                            entity_id,
                            entity_name,
                            rule["metric"],
                            rule["operator"],
                            rule["threshold"],
                            current_value,
                            row.get("stat_cost", 0),
                            row.get("pay_amount", 0),
                            row.get("order_count", 0),
                            row.get("roi", 0),
                            message,
                            now_text,
                        ),
                    )

    def material_rankings(
        self,
        range_key: str = "day",
        start_date: str = "",
        end_date: str = "",
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        target_snapshot = str(snapshot_time or "").strip()
        normalized = str(range_key or "day").strip().lower()
        range_label = ""
        start_dt: datetime | None = None
        end_dt: datetime | None = None
        if not target_snapshot:
            config = self.read_config()
            if normalized not in PERFORMANCE_RANGES:
                raise ValueError("range must be one of day/yesterday/week/month/custom")
            if normalized == "custom":
                start_dt, end_dt, range_label = build_custom_performance_window(start_date, end_date, config["timezone"])
            else:
                start_dt, end_dt, range_label = build_performance_window(normalized, config["timezone"])
        cache_key = build_material_cache_key(range_key, start_date, end_date, snapshot_time, allowed_advertiser_ids)
        cached = self._material_cache.get(cache_key)
        now_ts = time.time()
        if cached and now_ts - float(cached.get("_cached_at", 0.0)) < RANGE_CACHE_SECONDS:
            cached_payload = dict(cached["payload"])
            missing_cached_days = int(cached_payload.get("missing_history_days", 0) or 0)
            if (
                not target_snapshot
                and start_dt is not None
                and end_dt is not None
                and cached_payload.get("history_backfill_pending")
                and missing_cached_days > 0
            ):
                cached_payload["history_backfill_queued"] = self._queue_history_backfill_if_needed(
                    "detail", start_dt, end_dt, missing_cached_days
                )
            return cached_payload

        missing_days = 0

        with self.db() as conn:
            if not target_snapshot:
                assert start_dt is not None and end_dt is not None
                if normalized in {"yesterday", "week", "month", "custom"}:
                    missing_days = len(self._missing_extended_days(conn, start_dt, end_dt))
                runs = self._latest_extended_sync_runs_for_window(conn, start_dt, end_dt)
                if not runs:
                    backfill_queued = self._queue_history_backfill_if_needed("detail", start_dt, end_dt, missing_days)
                    return {
                        "snapshot_time": "",
                        "items": [],
                        "meta": None,
                        "range_key": normalized,
                        "range_label": range_label,
                        "query_start_date": start_dt.strftime("%Y-%m-%d"),
                        "query_end_date": end_dt.strftime("%Y-%m-%d"),
                        "snapshot_count": 0,
                        "history_backfill_pending": missing_days > 0,
                        "missing_history_days": missing_days,
                        "history_backfill_queued": backfill_queued,
                    }
                snapshot_times = [str(item.get("snapshot_time") or "") for item in runs if str(item.get("snapshot_time") or "").strip()]
                latest_meta = {
                    "snapshot_time": snapshot_times[-1],
                    "status": "partial" if any(str(item.get("status") or "") != "ok" for item in runs) else "ok",
                    "plan_count": sum(int(item.get("plan_count") or 0) for item in runs),
                    "detail_count": sum(int(item.get("detail_count") or 0) for item in runs),
                    "product_count": sum(int(item.get("product_count") or 0) for item in runs),
                    "material_count": sum(int(item.get("material_count") or 0) for item in runs),
                    "video_count": sum(int(item.get("video_count") or 0) for item in runs),
                    "error_count": sum(int(item.get("error_count") or 0) for item in runs),
                    "snapshot_dates": [str(item.get("snapshot_time") or "")[:10] for item in runs],
                }
            else:
                latest_meta_row = conn.execute(
                    """
                    SELECT *
                    FROM extended_sync_runs
                    WHERE snapshot_time = ?
                    LIMIT 1
                    """,
                    (target_snapshot,),
                ).fetchone()
                latest_meta = dict(latest_meta_row) if latest_meta_row else None
                snapshot_times = [target_snapshot]
                normalized = "custom" if snapshot_time else str(range_key or "day").strip().lower()
                range_label = "指定快照" if snapshot_time else ""

            placeholders = ",".join("?" for _ in snapshot_times)
            rollup_rows = conn.execute(
                f"""
                SELECT
                    *
                FROM material_rollups
                WHERE snapshot_time IN ({placeholders})
                ORDER BY snapshot_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC
                """,
                snapshot_times,
            ).fetchall()
            fallback_rows: list[Any] = []
            if len(rollup_rows) == 0:
                fallback_rows = conn.execute(
                    f"""
                    SELECT
                        m.snapshot_time,
                        m.advertiser_id,
                        m.advertiser_name,
                        m.ad_id,
                        m.ad_name,
                        m.material_type,
                        m.material_key,
                        m.material_id,
                        m.material_name,
                        m.video_id,
                        m.cover_url,
                        m.aweme_item_id,
                        m.video_url,
                        m.stat_cost,
                        m.pay_amount,
                        m.total_pay_amount,
                        m.settled_pay_amount,
                        m.order_count,
                        m.settled_order_count,
                        COALESCE(v.is_original, 0) AS is_original
                    FROM material_snapshots AS m
                    LEFT JOIN video_origin_flags AS v
                      ON v.snapshot_time = m.snapshot_time
                     AND v.advertiser_id = m.advertiser_id
                     AND v.material_id = m.material_id
                    WHERE m.snapshot_time IN ({placeholders})
                    ORDER BY m.snapshot_time DESC, m.order_count DESC, m.pay_amount DESC, m.roi DESC, m.stat_cost DESC
                    """,
                    snapshot_times,
                ).fetchall()
        if rollup_rows:
            scoped_rollup_rows = [dict(row) for row in rollup_rows]
            if allowed_advertiser_ids is not None:
                allowed = {int(item) for item in allowed_advertiser_ids}
                scoped_rollup_rows = [
                    row
                    for row in scoped_rollup_rows
                    if any(int(item) in allowed for item in json.loads(str(row.get("advertiser_ids_json") or "[]")))
                ]
            items = self._aggregate_material_rollups(scoped_rollup_rows)
        else:
            scoped_rows = [dict(row) for row in fallback_rows]
            if allowed_advertiser_ids is not None:
                allowed = {int(item) for item in allowed_advertiser_ids}
                scoped_rows = [row for row in scoped_rows if int(row.get("advertiser_id", 0) or 0) in allowed]
            items = self._build_material_rankings(scoped_rows)
        if items:
            with self.db() as preview_conn:
                items = self._apply_latest_material_previews(preview_conn, items)
        payload = {
            "snapshot_time": str(latest_meta.get("snapshot_time") or "") if latest_meta else target_snapshot,
            "items": items,
            "meta": latest_meta,
            "snapshot_count": len(snapshot_times),
        }
        if not target_snapshot:
            backfill_queued = self._queue_history_backfill_if_needed("detail", start_dt, end_dt, missing_days)
            payload["range_key"] = normalized
            payload["range_label"] = range_label
            payload["query_start_date"] = start_dt.strftime("%Y-%m-%d")
            payload["query_end_date"] = end_dt.strftime("%Y-%m-%d")
            payload["history_backfill_pending"] = missing_days > 0
            payload["missing_history_days"] = missing_days
            payload["history_backfill_queued"] = backfill_queued
        self._material_cache[cache_key] = {"_cached_at": now_ts, "payload": payload}
        return payload

    def get_performance_snapshot(
        self,
        range_key: str,
        start_date: str = "",
        end_date: str = "",
        force_refresh: bool = False,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        normalized = str(range_key or "day").strip().lower()
        if normalized not in PERFORMANCE_RANGES:
            raise ValueError("range must be one of day/yesterday/week/month/custom")
        config = self.read_config()
        if normalized == "custom":
            start_dt, end_dt, range_label = build_custom_performance_window(start_date, end_date, config["timezone"])
        else:
            start_dt, end_dt, range_label = build_performance_window(normalized, config["timezone"])
        cache_key = build_performance_cache_key(normalized, start_date, end_date)
        cached = self._performance_cache.get(cache_key)
        now_ts = time.time()
        if not force_refresh and cached and now_ts - float(cached.get("_cached_at", 0.0)) < RANGE_CACHE_SECONDS:
            cached_payload = dict(cached["payload"])
            if cached_payload.get("history_backfill_pending") and int(cached_payload.get("missing_history_days", 0) or 0) > 0:
                cached_payload["history_backfill_queued"] = self._queue_history_backfill_if_needed(
                    "performance", start_dt, end_dt, int(cached_payload.get("missing_history_days", 0) or 0)
                )
            return self._apply_account_scope(cached_payload, allowed_advertiser_ids)
        missing_days = 0
        if normalized in {"week", "month", "custom", "yesterday"}:
            with self.db() as conn:
                missing_days = len(self._missing_summary_days(conn, start_dt, end_dt))
        backfill_queued = self._queue_history_backfill_if_needed("performance", start_dt, end_dt, missing_days)
        payload = self._performance_snapshot_from_db(start_dt, end_dt)
        payload["range_key"] = normalized
        payload["range_label"] = range_label
        payload["query_start_date"] = start_dt.strftime("%Y-%m-%d")
        payload["query_end_date"] = end_dt.strftime("%Y-%m-%d")
        payload["history_backfill_pending"] = missing_days > 0
        payload["missing_history_days"] = missing_days
        payload["history_backfill_queued"] = backfill_queued
        payload["plans"] = self._apply_employee_attribution(
            [self._decorate_plan_item(item) for item in payload["plans"]],
            payload["accounts"],
        )
        payload["summary"], payload["products"], payload["employees"], payload["operators"] = self._rankings_bundle(
            payload["summary"],
            payload["accounts"],
            payload["plans"],
        )
        self._performance_cache[cache_key] = {"_cached_at": now_ts, "payload": payload}
        return self._apply_account_scope(payload, allowed_advertiser_ids)

    def public_employee_rankings(
        self,
        range_key: str,
        start_date: str = "",
        end_date: str = "",
        sort_key: str = "stat_cost",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        payload = self.get_performance_snapshot(range_key, start_date, end_date)
        employees_cfg, _, _ = self._active_employee_config()
        configured_mode = bool(employees_cfg)
        metric = sort_key if sort_key in PUBLIC_SORT_FIELDS else "stat_cost"
        direction = "asc" if sort_dir == "asc" else "desc"
        items = [dict(item) for item in payload.get("employees", [])]
        if configured_mode:
            items = [item for item in items if item.get("employee_id") is not None]
        items.sort(
            key=lambda item: (
                float(item.get(metric, 0.0) or 0.0),
                float(item.get("pay_amount", 0.0) or 0.0),
                float(item.get("order_count", 0.0) or 0.0),
                str(item.get("employee_name") or ""),
            ),
            reverse=direction == "desc",
        )
        return {
            "range_key": payload.get("range_key", range_key),
            "range_label": payload.get("range_label", ""),
            "query_start_date": payload.get("query_start_date", ""),
            "query_end_date": payload.get("query_end_date", ""),
            "sort_key": metric,
            "sort_dir": direction,
            "updated_at": payload.get("snapshot_time", ""),
            "attribution_mode": "configured" if configured_mode else "legacy_anchor_fallback",
            "configured_employee_count": len(employees_cfg),
            "unassigned_group_count": len(
                [
                    item
                    for item in payload.get("employees", [])
                    if str(item.get("employee_source") or "").strip() == "unassigned"
                ]
            ),
            "items": items,
        }

    def _build_unassigned_candidates(self, plans: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
        scope_value = str(scope or "all").strip().lower()
        if scope_value not in {"all", "account", "plan", "product", "material"}:
            raise ValueError("scope must be one of all/account/plan/product/material")

        items: list[dict[str, Any]] = []
        plan_ids = {int(row.get("ad_id", 0) or 0) for row in plans if int(row.get("ad_id", 0) or 0)}

        if scope_value in {"all", "plan"}:
            for row in plans:
                stat_cost = round(float(row.get("stat_cost", 0.0) or 0.0), 2)
                pay_amount = round(float(row.get("pay_amount", 0.0) or 0.0), 2)
                order_count = int(float(row.get("order_count", 0.0) or 0.0))
                product_key = self._product_key(row)
                binding_options = [
                    {
                        "object_type": "plan",
                        "object_key": str(row.get("ad_id") or ""),
                        "object_label": str(row.get("ad_name") or "").strip(),
                        "action_label": "绑定计划",
                    },
                    {
                        "object_type": "account",
                        "object_key": str(row.get("advertiser_id") or ""),
                        "object_label": str(row.get("advertiser_name") or "").strip(),
                        "action_label": "绑定账户",
                    },
                ]
                if product_key:
                    binding_options.append(
                        {
                            "object_type": "product",
                            "object_key": product_key,
                            "object_label": str(row.get("product_name") or row.get("product_id") or "").strip(),
                            "action_label": "绑定商品",
                        }
                    )
                items.append(
                    {
                        "object_type": "plan",
                        "object_type_label": "计划",
                        "object_key": str(row.get("ad_id") or ""),
                        "object_label": str(row.get("ad_name") or "").strip() or f"计划 {row.get('ad_id') or '-'}",
                        "advertiser_name": str(row.get("advertiser_name") or "").strip(),
                        "plan_name": str(row.get("ad_name") or "").strip(),
                        "product_name": str(row.get("product_name") or "").strip(),
                        "stat_cost": stat_cost,
                        "pay_amount": pay_amount,
                        "order_count": order_count,
                        "roi": round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                        "plan_count": 1,
                        "binding_options": binding_options,
                    }
                )

        if scope_value in {"all", "material"} and plan_ids:
            material_groups: dict[str, dict[str, Any]] = {}
            for row in self._reference_catalog()["materials"]:
                plan_id = int(row.get("ad_id", 0) or 0)
                if plan_id not in plan_ids:
                    continue
                material_key = str(row.get("material_key") or "").strip()
                if not material_key:
                    continue
                group = material_groups.setdefault(
                    material_key,
                    {
                        "object_type": "material",
                        "object_type_label": "素材",
                        "object_key": material_key,
                        "object_label": str(row.get("material_name") or row.get("material_id") or material_key).strip(),
                        "advertiser_name": str(row.get("advertiser_name") or "").strip(),
                        "plan_name": "",
                        "product_name": "",
                        "material_type": str(row.get("material_type") or "").strip(),
                        "stat_cost": 0.0,
                        "pay_amount": 0.0,
                        "order_count": 0,
                        "plan_count": 0,
                        "top_plan_name": "",
                        "top_plan_orders": -1,
                        "top_plan_pay_amount": -1.0,
                    },
                )
                stat_cost = round(float(row.get("stat_cost", 0.0) or 0.0), 2)
                pay_amount = round(float(row.get("pay_amount", 0.0) or 0.0), 2)
                order_count = int(float(row.get("order_count", 0.0) or 0.0))
                group["stat_cost"] = round(group["stat_cost"] + stat_cost, 2)
                group["pay_amount"] = round(group["pay_amount"] + pay_amount, 2)
                group["order_count"] += order_count
                group["plan_count"] += 1
                if order_count > group["top_plan_orders"] or (
                    order_count == group["top_plan_orders"] and pay_amount > group["top_plan_pay_amount"]
                ):
                    group["top_plan_name"] = str(row.get("ad_name") or "").strip()
                    group["top_plan_orders"] = order_count
                    group["top_plan_pay_amount"] = pay_amount

            for group in material_groups.values():
                group["roi"] = round(group["pay_amount"] / group["stat_cost"], 2) if group["stat_cost"] > 0 else 0.0
                group["plan_name"] = group["top_plan_name"]
                group["binding_options"] = [
                    {
                        "object_type": "material",
                        "object_key": group["object_key"],
                        "object_label": group["object_label"],
                        "action_label": "绑定素材",
                    }
                ]
                items.append(group)

        if scope_value in {"all", "product"}:
            product_groups: dict[str, dict[str, Any]] = {}
            for row in plans:
                product_key = self._product_key(row)
                if not product_key:
                    continue
                group = product_groups.setdefault(
                    product_key,
                    {
                        "object_type": "product",
                        "object_type_label": "商品",
                        "object_key": product_key,
                        "object_label": str(row.get("product_name") or row.get("product_id") or "").strip() or product_key,
                        "advertiser_name": str(row.get("advertiser_name") or "").strip(),
                        "plan_name": "",
                        "product_name": str(row.get("product_name") or "").strip(),
                        "stat_cost": 0.0,
                        "pay_amount": 0.0,
                        "order_count": 0,
                        "plan_count": 0,
                        "top_plan_name": "",
                        "top_plan_orders": -1,
                        "top_plan_pay_amount": -1.0,
                    },
                )
                stat_cost = round(float(row.get("stat_cost", 0.0) or 0.0), 2)
                pay_amount = round(float(row.get("pay_amount", 0.0) or 0.0), 2)
                order_count = int(float(row.get("order_count", 0.0) or 0.0))
                group["stat_cost"] = round(group["stat_cost"] + stat_cost, 2)
                group["pay_amount"] = round(group["pay_amount"] + pay_amount, 2)
                group["order_count"] += order_count
                group["plan_count"] += 1
                if order_count > group["top_plan_orders"] or (
                    order_count == group["top_plan_orders"] and pay_amount > group["top_plan_pay_amount"]
                ):
                    group["top_plan_name"] = str(row.get("ad_name") or "").strip()
                    group["top_plan_orders"] = order_count
                    group["top_plan_pay_amount"] = pay_amount

            for group in product_groups.values():
                group["roi"] = round(group["pay_amount"] / group["stat_cost"], 2) if group["stat_cost"] > 0 else 0.0
                group["plan_name"] = group["top_plan_name"]
                group["binding_options"] = [
                    {
                        "object_type": "product",
                        "object_key": group["object_key"],
                        "object_label": group["object_label"],
                        "action_label": "绑定商品",
                    }
                ]
                items.append(group)

        if scope_value in {"all", "account"}:
            account_groups: dict[int, dict[str, Any]] = {}
            for row in plans:
                advertiser_id = int(row.get("advertiser_id", 0) or 0)
                if not advertiser_id:
                    continue
                group = account_groups.setdefault(
                    advertiser_id,
                    {
                        "object_type": "account",
                        "object_type_label": "账户",
                        "object_key": str(advertiser_id),
                        "object_label": str(row.get("advertiser_name") or "").strip() or str(advertiser_id),
                        "advertiser_name": str(row.get("advertiser_name") or "").strip(),
                        "plan_name": "",
                        "product_name": "",
                        "stat_cost": 0.0,
                        "pay_amount": 0.0,
                        "order_count": 0,
                        "plan_count": 0,
                        "top_plan_name": "",
                        "top_plan_orders": -1,
                        "top_plan_pay_amount": -1.0,
                    },
                )
                stat_cost = round(float(row.get("stat_cost", 0.0) or 0.0), 2)
                pay_amount = round(float(row.get("pay_amount", 0.0) or 0.0), 2)
                order_count = int(float(row.get("order_count", 0.0) or 0.0))
                group["stat_cost"] = round(group["stat_cost"] + stat_cost, 2)
                group["pay_amount"] = round(group["pay_amount"] + pay_amount, 2)
                group["order_count"] += order_count
                group["plan_count"] += 1
                if order_count > group["top_plan_orders"] or (
                    order_count == group["top_plan_orders"] and pay_amount > group["top_plan_pay_amount"]
                ):
                    group["top_plan_name"] = str(row.get("ad_name") or "").strip()
                    group["top_plan_orders"] = order_count
                    group["top_plan_pay_amount"] = pay_amount

            for group in account_groups.values():
                group["roi"] = round(group["pay_amount"] / group["stat_cost"], 2) if group["stat_cost"] > 0 else 0.0
                group["plan_name"] = group["top_plan_name"]
                group["binding_options"] = [
                    {
                        "object_type": "account",
                        "object_key": group["object_key"],
                        "object_label": group["object_label"],
                        "action_label": "绑定账户",
                    }
                ]
                items.append(group)

        sort_order = {"plan": 0, "material": 1, "product": 2, "account": 3}
        items.sort(
            key=lambda item: (
                -float(item.get("stat_cost", 0.0) or 0.0),
                -float(item.get("order_count", 0.0) or 0.0),
                -float(item.get("pay_amount", 0.0) or 0.0),
                sort_order.get(str(item.get("object_type") or ""), 9),
                str(item.get("object_label") or ""),
            )
        )
        return items

    def unassigned_candidates(
        self,
        range_key: str,
        start_date: str = "",
        end_date: str = "",
        scope: str = "all",
        allowed_advertiser_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        payload = self.get_performance_snapshot(range_key, start_date, end_date, allowed_advertiser_ids=allowed_advertiser_ids)
        plans = [
            dict(item)
            for item in payload.get("plans", [])
            if str(item.get("employee_source") or "").strip() == "unassigned"
        ]
        items = self._build_unassigned_candidates(plans, scope)
        return {
            "range_key": payload.get("range_key", range_key),
            "range_label": payload.get("range_label", ""),
            "query_start_date": payload.get("query_start_date", ""),
            "query_end_date": payload.get("query_end_date", ""),
            "scope": scope,
            "total_plan_count": len(plans),
            "item_count": len(items),
            "items": items,
        }

    @staticmethod
    def _compare(current_value: float, operator: str, threshold: float) -> bool:
        if operator == "gt":
            return current_value > threshold
        if operator == "gte":
            return current_value >= threshold
        if operator == "lt":
            return current_value < threshold
        if operator == "lte":
            return current_value <= threshold
        return False

    @staticmethod
    def _build_alert_message(rule: Any, row: dict[str, Any], now_text: str) -> str:
        entity_label = {
            "account": "账户",
            "plan": "计划",
            "burst_plan": "爆单计划",
            "account_balance": "账户余额",
            "shared_wallet": "共享钱包",
        }.get(str(rule["entity_type"] or ""), "对象")
        if str(rule["entity_type"] or "") == "account_balance":
            return (
                f"[千川告警] 账户余额触发阈值\n"
                f"时间：{now_text}\n"
                f"账户：{row['advertiser_name']}\n"
                f"规则：账户余额 {rule['operator']} {rule['threshold']}\n"
                f"当前余额：{row.get('account_balance', 0)}\n"
                f"可用余额：{row.get('available_balance', 0)}\n"
                f"备注：{rule['note'] or '请及时补充账户余额。'}"
            )
        if str(rule["entity_type"] or "") == "shared_wallet":
            return (
                f"[千川告警] 共享钱包触发阈值\n"
                f"时间：{now_text}\n"
                f"钱包：{row['wallet_name']}\n"
                f"规则：共享钱包余额 {rule['operator']} {rule['threshold']}\n"
                f"当前余额：{row.get('wallet_balance', 0)}\n"
                f"覆盖账户数：{row.get('member_count', 0)}\n"
                f"备注：{rule['note'] or '请及时检查共享钱包余额。'}"
            )
        extra = ""
        if str(rule["entity_type"] or "") in {"plan", "burst_plan"}:
            if row["product_name"]:
                extra += f"\n商品：{row['product_name']}"
            if row["anchor_name"]:
                extra += f"\n主播：{row['anchor_name']}"
            extra += f"\n账户：{row['advertiser_name']}"
        metric_label = "爆单订单数" if str(rule["metric"] or "") == "burst_order_count" else rule["metric"]
        return (
            f"[千川告警] {entity_label}触发阈值\n"
            f"时间：{now_text}\n"
            f"{entity_label}：{row['advertiser_name'] if rule['entity_type'] == 'account' else row['ad_name']}"
            f"{extra}\n"
            f"规则：{metric_label} {rule['operator']} {rule['threshold']}\n"
            f"当前值：{row[rule['metric']]}\n"
            f"消耗：{row['stat_cost']}\n"
            f"支付：{row['pay_amount']}\n"
            f"订单：{row['order_count']}\n"
            f"ROI：{row['roi']}\n"
            f"备注：{rule['note'] or '请及时检查投放并调整。'}"
        )

    async def run_sync(self, manual: bool = False) -> dict[str, Any]:
        async with self._sync_lock:
            payload = await asyncio.to_thread(self.collect_and_store)
            return {"ok": True, "manual": manual, "snapshot_time": payload["snapshot_time"]}

    async def run_detail_sync(self, manual: bool = False) -> dict[str, Any]:
        async with self._detail_sync_lock:
            payload = await asyncio.to_thread(self.collect_extended_and_store)
            return {
                "ok": bool(payload.get("ok", True)),
                "manual": manual,
                "skipped": bool(payload.get("skipped", False)),
                "snapshot_time": payload.get("snapshot_time", ""),
                "reason": payload.get("reason", ""),
                "error_count": len(payload.get("errors", [])),
            }

    def collect_and_store(self) -> dict[str, Any]:
        payload = self.collect_snapshot()
        self.persist_snapshot(payload)
        self.evaluate_alerts(payload)
        self.cleanup_history()
        self._performance_cache.clear()
        return payload

    def collect_extended_and_store(self) -> dict[str, Any]:
        payload = self.collect_extended_snapshot()
        if payload.get("skipped"):
            return payload
        self.persist_extended_snapshot(payload)
        self.cleanup_history()
        self._material_cache.clear()
        try:
            self.material_rankings("day")
        except Exception:
            pass
        return payload

    async def start(self) -> None:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.init_db()
        self.bootstrap_auth_store()
        self.bootstrap_token_store()
        if ENABLE_IN_PROCESS_SCHEDULER:
            await self.run_sync()

    async def stop(self) -> None:
        return None


service = DashboardService()
require_auth, require_admin, require_material_uploader = build_auth_dependencies(
    service,
    role_admin=ROLE_ADMIN,
    role_supervisor=ROLE_SUPERVISOR,
)
app = FastAPI(title=APP_NAME)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
register_user_routes(app, service, require_admin)
register_employee_routes(app, service, require_admin)
register_alert_routes(app, service, require_admin)
register_system_routes(app, service, require_admin)
register_query_routes(
    app,
    service,
    require_auth,
    require_admin,
    role_admin=ROLE_ADMIN,
    role_operator=ROLE_OPERATOR,
    timezone=TIMEZONE,
)
register_upload_routes(app, service, require_material_uploader)
register_page_routes(app, service, APP_NAME)
register_health_routes(app, readiness_payload)


@app.on_event("startup")
async def startup() -> None:
    if not DASHBOARD_PASSWORD:
        raise RuntimeError("DASHBOARD_PASSWORD is required")
    await service.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await service.stop()
