#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from report_qianchuan import (  # noqa: E402
    PLAN_MATERIAL_TYPES,
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
    plan_delivery_status_label,
    plan_marketing_goal_label,
    plan_opt_status_label,
)
from dashboard.db_backend import connect_database, database_backend  # noqa: E402


APP_NAME = "Qianchuan"
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "/app/config/config.json"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", str(DATA_DIR / "dashboard.db")))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
TOKEN_CACHE_PATH = Path(os.environ.get("TOKEN_CACHE_PATH", str(DATA_DIR / "token_cache.json")))
LATEST_TOKEN_PATH = Path(os.environ.get("LATEST_TOKEN_PATH", str(DATA_DIR / "qianchuan_latest_token.json")))
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Shanghai")
ALERT_COOLDOWN_DEFAULT = int(os.environ.get("ALERT_COOLDOWN_DEFAULT", "60"))
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "180"))
DASHBOARD_USERNAME = os.environ.get("DASHBOARD_USERNAME", "admin")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "replace-me")
RANGE_CACHE_SECONDS = int(os.environ.get("RANGE_CACHE_SECONDS", "55"))
PERFORMANCE_RANGES = {"day", "week", "month", "custom"}
DETAIL_SYNC_INTERVAL_MINUTES = int(os.environ.get("DETAIL_SYNC_INTERVAL_MINUTES", "10"))
ENABLE_IN_PROCESS_SCHEDULER = os.environ.get("ENABLE_IN_PROCESS_SCHEDULER", "0") == "1"
ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
PUBLIC_SORT_FIELDS = {"stat_cost", "pay_amount", "order_count", "roi"}
EMPLOYEE_KEYWORD_SCOPES = {"all", "account", "plan", "product", "material"}
EMPLOYEE_BINDING_TYPES = {"account", "plan", "product", "material"}
ALERT_ENTITY_TYPES = {"account", "plan", "account_balance", "shared_wallet", "burst_plan"}
ALERT_METRICS = {"stat_cost", "roi", "order_count", "pay_amount", "account_balance", "wallet_balance", "burst_order_count"}
ALERT_ENTITY_METRICS = {
    "account": {"stat_cost", "roi", "order_count", "pay_amount"},
    "plan": {"stat_cost", "roi", "order_count", "pay_amount"},
    "account_balance": {"account_balance"},
    "shared_wallet": {"wallet_balance"},
    "burst_plan": {"burst_order_count"},
}


def now_text(tz_name: str = TIMEZONE) -> str:
    return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M:%S")


def build_password_hash(password: str, iterations: int = 390000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    text = str(stored_hash or "").strip()
    try:
        algorithm, iterations_text, salt_b64, digest_b64 = text.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def normalize_summary_times(value: str) -> str:
    tokens = re.split(r"[,，\s]+", str(value or "").strip())
    valid = sorted({token for token in tokens if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", token)})
    return ",".join(valid)


def build_performance_window(range_key: str, tz_name: str) -> tuple[datetime, datetime, str]:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    if range_key == "week":
        start_dt = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=tz) - timedelta(days=6)
        label = "近 7 天"
    elif range_key == "month":
        start_dt = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=tz) - timedelta(days=29)
        label = "近 30 天"
    else:
        start_dt = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=tz)
        label = "今日"
    return start_dt, now, label


def _parse_date_input(value: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是 YYYY-MM-DD") from exc


def build_custom_performance_window(start_date: str, end_date: str, tz_name: str) -> tuple[datetime, datetime, str]:
    if not str(start_date or "").strip() or not str(end_date or "").strip():
        raise ValueError("自定义时间段必须同时提供开始日期和结束日期")

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
    return start_dt, end_dt, "自定义时间段"


def build_performance_cache_key(range_key: str, start_date: str = "", end_date: str = "") -> str:
    normalized = str(range_key or "day").strip().lower()
    if normalized == "custom":
        return f"custom:{str(start_date or '').strip()}:{str(end_date or '').strip()}"
    return normalized


class AlertRulePayload(BaseModel):
    entity_type: str = Field(pattern="^(account|plan|account_balance|shared_wallet|burst_plan)$")
    metric: str = Field(pattern="^(stat_cost|roi|order_count|pay_amount|account_balance|wallet_balance|burst_order_count)$")
    operator: str = Field(pattern="^(gt|lt|gte|lte)$")
    threshold: float
    min_spend: float = 0.0
    cooldown_minutes: int = ALERT_COOLDOWN_DEFAULT
    enabled: bool = True
    target_id: str = ""
    note: str = ""


def validate_alert_rule_payload(payload: AlertRulePayload) -> None:
    entity_type = str(payload.entity_type or "").strip()
    metric = str(payload.metric or "").strip()
    allowed_metrics = ALERT_ENTITY_METRICS.get(entity_type, set())
    if metric not in allowed_metrics:
        raise ValueError("当前对象不支持所选指标。")
    if entity_type in {"account_balance", "shared_wallet", "burst_plan"} and float(payload.min_spend or 0) != 0:
        raise ValueError("当前规则类型不支持最低消耗限制。")


class NotificationSettingsPayload(BaseModel):
    enabled: bool = False
    channel: str = Field(default="feishu", min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    account: str = Field(default="default", max_length=80)
    target: str = Field(default="", max_length=200)
    alert_enabled: bool = False
    alert_batch_size: int = Field(default=6, ge=1, le=20)
    summary_enabled: bool = False
    summary_times: str = Field(default="", max_length=200)
    summary_account_limit: int = Field(default=6, ge=1, le=20)
    summary_plan_limit: int = Field(default=10, ge=1, le=30)


class AuthCodeExchangePayload(BaseModel):
    auth_code: str = Field(min_length=20, max_length=200)


class EmployeePayload(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=200)
    enabled: bool = True


class EmployeeKeywordPayload(BaseModel):
    keyword: str = Field(min_length=1, max_length=80)
    scope: str = Field(default="all", pattern="^(all|account|plan|product|material)$")
    priority: int = Field(default=100, ge=1, le=9999)
    enabled: bool = True


class EmployeeBindingPayload(BaseModel):
    object_type: str = Field(pattern="^(account|plan|product|material)$")
    object_key: str = Field(min_length=1, max_length=200)
    object_label: str = Field(default="", max_length=255)
    note: str = Field(default="", max_length=200)


class AppUserPayload(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(default="", max_length=120)
    role: str = Field(default=ROLE_OPERATOR, pattern="^(admin|operator)$")
    display_name: str = Field(default="", max_length=80)
    enabled: bool = True


class UserScopePayload(BaseModel):
    advertiser_ids: list[int] = Field(default_factory=list)


class DashboardService:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._sync_lock = asyncio.Lock()
        self._detail_sync_lock = asyncio.Lock()
        self._templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
        self._range_cache: dict[str, dict[str, Any]] = {}

    @property
    def templates(self) -> Jinja2Templates:
        return self._templates

    def init_db(self) -> None:
        with self.db() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;

                CREATE TABLE IF NOT EXISTS summary_snapshots (
                    snapshot_time TEXT PRIMARY KEY,
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
                    plan_failures INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS account_snapshots (
                    snapshot_time TEXT NOT NULL,
                    advertiser_id BIGINT NOT NULL,
                    advertiser_name TEXT NOT NULL,
                    stat_cost REAL NOT NULL,
                    roi REAL NOT NULL,
                    order_count INTEGER NOT NULL,
                    pay_amount REAL NOT NULL,
                    ok INTEGER NOT NULL,
                    error TEXT,
                    PRIMARY KEY (snapshot_time, advertiser_id)
                );

                CREATE TABLE IF NOT EXISTS plan_snapshots (
                    snapshot_time TEXT NOT NULL,
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
                    stat_cost REAL NOT NULL,
                    roi REAL NOT NULL,
                    order_count INTEGER NOT NULL,
                    pay_amount REAL NOT NULL,
                    PRIMARY KEY (snapshot_time, ad_id)
                );

                CREATE TABLE IF NOT EXISTS plan_detail_snapshots (
                    snapshot_time TEXT NOT NULL,
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
                    PRIMARY KEY (snapshot_time, ad_id)
                );

                CREATE TABLE IF NOT EXISTS product_snapshots (
                    snapshot_time TEXT NOT NULL,
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
                    PRIMARY KEY (snapshot_time, ad_id, product_key)
                );

                CREATE TABLE IF NOT EXISTS material_snapshots (
                    snapshot_time TEXT NOT NULL,
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
                    video_id TEXT NOT NULL DEFAULT '',
                    product_show_count INTEGER NOT NULL DEFAULT 0,
                    product_click_count INTEGER NOT NULL DEFAULT 0,
                    stat_cost REAL NOT NULL DEFAULT 0,
                    pay_amount REAL NOT NULL DEFAULT 0,
                    order_count INTEGER NOT NULL DEFAULT 0,
                    roi REAL NOT NULL DEFAULT 0,
                    raw_json TEXT NOT NULL,
                    PRIMARY KEY (snapshot_time, ad_id, material_type, material_key)
                );

                CREATE TABLE IF NOT EXISTS video_origin_flags (
                    snapshot_time TEXT NOT NULL,
                    advertiser_id BIGINT NOT NULL,
                    material_id TEXT NOT NULL,
                    is_original INTEGER NOT NULL DEFAULT 0,
                    raw_json TEXT NOT NULL,
                    PRIMARY KEY (snapshot_time, advertiser_id, material_id)
                );

                CREATE TABLE IF NOT EXISTS extended_sync_runs (
                    snapshot_time TEXT PRIMARY KEY,
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
                    finished_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alert_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    min_spend REAL NOT NULL DEFAULT 0,
                    cooldown_minutes INTEGER NOT NULL DEFAULT 60,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    target_id TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alert_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id INTEGER NOT NULL,
                    snapshot_time TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    entity_name TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    current_value REAL NOT NULL,
                    stat_cost REAL NOT NULL,
                    pay_amount REAL NOT NULL,
                    order_count INTEGER NOT NULL,
                    roi REAL NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    sent_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(rule_id) REFERENCES alert_rules(id)
                );

                CREATE TABLE IF NOT EXISTS notification_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled INTEGER NOT NULL DEFAULT 0,
                    channel TEXT NOT NULL DEFAULT 'feishu',
                    account TEXT NOT NULL DEFAULT 'default',
                    target TEXT NOT NULL DEFAULT '',
                    alert_enabled INTEGER NOT NULL DEFAULT 0,
                    alert_batch_size INTEGER NOT NULL DEFAULT 6,
                    summary_enabled INTEGER NOT NULL DEFAULT 0,
                    summary_times TEXT NOT NULL DEFAULT '09:00',
                    summary_account_limit INTEGER NOT NULL DEFAULT 6,
                    summary_plan_limit INTEGER NOT NULL DEFAULT 10,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notification_dispatch_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    schedule_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    account TEXT NOT NULL,
                    target TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(kind, schedule_key)
                );

                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    app_id TEXT NOT NULL,
                    customer_center_id TEXT NOT NULL,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    expires_at INTEGER NOT NULL DEFAULT 0,
                    refresh_token_expires_in INTEGER,
                    updated_at INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT 'runtime',
                    PRIMARY KEY (app_id, customer_center_id)
                );

                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    display_name TEXT NOT NULL UNIQUE,
                    note TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS employee_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL,
                    keyword TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'all',
                    priority INTEGER NOT NULL DEFAULT 100,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(employee_id) REFERENCES employees(id)
                );

                CREATE TABLE IF NOT EXISTS employee_manual_bindings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL,
                    object_type TEXT NOT NULL,
                    object_key TEXT NOT NULL,
                    object_label TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(employee_id) REFERENCES employees(id),
                    UNIQUE (object_type, object_key)
                );

                CREATE TABLE IF NOT EXISTS app_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'admin',
                    display_name TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_account_scopes (
                    user_id INTEGER NOT NULL,
                    advertiser_id BIGINT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, advertiser_id),
                    FOREIGN KEY(user_id) REFERENCES app_users(id)
                );

                CREATE TABLE IF NOT EXISTS account_balances (
                    snapshot_time TEXT NOT NULL,
                    advertiser_id BIGINT NOT NULL,
                    advertiser_name TEXT NOT NULL,
                    account_balance REAL NOT NULL DEFAULT 0,
                    available_balance REAL NOT NULL DEFAULT 0,
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (snapshot_time, advertiser_id)
                );

                CREATE TABLE IF NOT EXISTS shared_wallets (
                    snapshot_time TEXT NOT NULL,
                    main_wallet_id TEXT NOT NULL,
                    wallet_name TEXT NOT NULL DEFAULT '',
                    total_balance REAL NOT NULL DEFAULT 0,
                    valid_balance REAL NOT NULL DEFAULT 0,
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (snapshot_time, main_wallet_id)
                );

                CREATE TABLE IF NOT EXISTS shared_wallet_account_relations (
                    snapshot_time TEXT NOT NULL,
                    main_wallet_id TEXT NOT NULL,
                    advertiser_id BIGINT NOT NULL,
                    child_wallet_id TEXT NOT NULL DEFAULT '',
                    wallet_name TEXT NOT NULL DEFAULT '',
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (snapshot_time, main_wallet_id, advertiser_id)
                );

                CREATE INDEX IF NOT EXISTS idx_account_snapshots_adv_time
                ON account_snapshots (advertiser_id, snapshot_time);

                CREATE INDEX IF NOT EXISTS idx_plan_snapshots_plan_time
                ON plan_snapshots (ad_id, snapshot_time);

                CREATE INDEX IF NOT EXISTS idx_plan_detail_snapshots_plan_time
                ON plan_detail_snapshots (ad_id, snapshot_time);

                CREATE INDEX IF NOT EXISTS idx_product_snapshots_plan_time
                ON product_snapshots (ad_id, snapshot_time);

                CREATE INDEX IF NOT EXISTS idx_product_snapshots_product_time
                ON product_snapshots (product_id, snapshot_time);

                CREATE INDEX IF NOT EXISTS idx_material_snapshots_plan_time
                ON material_snapshots (ad_id, snapshot_time);

                CREATE INDEX IF NOT EXISTS idx_material_snapshots_material_time
                ON material_snapshots (material_id, snapshot_time);

                CREATE INDEX IF NOT EXISTS idx_video_origin_flags_material_time
                ON video_origin_flags (material_id, snapshot_time);

                CREATE INDEX IF NOT EXISTS idx_alert_events_status_created
                ON alert_events (status, created_at);

                CREATE INDEX IF NOT EXISTS idx_notification_dispatch_kind_key
                ON notification_dispatch_log (kind, schedule_key);

                CREATE INDEX IF NOT EXISTS idx_oauth_tokens_updated
                ON oauth_tokens (updated_at);

                CREATE INDEX IF NOT EXISTS idx_employees_enabled
                ON employees (enabled, display_name);

                CREATE INDEX IF NOT EXISTS idx_employee_keywords_employee
                ON employee_keywords (employee_id, enabled, scope);

                CREATE INDEX IF NOT EXISTS idx_employee_manual_bindings_employee
                ON employee_manual_bindings (employee_id, object_type);

                CREATE INDEX IF NOT EXISTS idx_app_users_role_enabled
                ON app_users (role, enabled);

                CREATE INDEX IF NOT EXISTS idx_user_account_scopes_user
                ON user_account_scopes (user_id);

                CREATE INDEX IF NOT EXISTS idx_account_balances_adv_time
                ON account_balances (advertiser_id, snapshot_time);

                CREATE INDEX IF NOT EXISTS idx_shared_wallets_wallet_time
                ON shared_wallets (main_wallet_id, snapshot_time);

                CREATE INDEX IF NOT EXISTS idx_shared_wallet_account_rel_wallet_adv
                ON shared_wallet_account_relations (main_wallet_id, advertiser_id, snapshot_time);
                """
            )
            self._ensure_notification_settings_locked(conn)

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

    def _ensure_notification_settings_locked(self, conn: Any) -> None:
        exists = conn.execute("SELECT 1 FROM notification_settings WHERE id = 1").fetchone()
        if exists:
            return
        conn.execute(
            """
            INSERT INTO notification_settings (
                id, enabled, channel, account, target, alert_enabled, alert_batch_size,
                summary_enabled, summary_times, summary_account_limit, summary_plan_limit, updated_at
            ) VALUES (1, 0, 'feishu', 'default', ?, 0, 6, 0, '09:00', 6, 10, ?)
            """,
            (self._default_notification_target(), now_text()),
        )

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
                    SET password_hash = ?, role = ?, enabled = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (hashed, ROLE_ADMIN, now, row["id"]),
                )
                return
            conn.execute(
                """
                INSERT INTO app_users (username, password_hash, role, display_name, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (username, hashed, ROLE_ADMIN, "管理员", now, now),
            )

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self.db() as conn:
            row = conn.execute(
                """
                SELECT id, username, role, display_name, enabled, created_at, updated_at
                FROM app_users
                WHERE id = ?
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if not row or not bool(row["enabled"]):
            return None
        return dict(row)

    def authenticate_user(self, username: str, password: str) -> dict[str, Any] | None:
        with self.db() as conn:
            row = conn.execute(
                """
                SELECT id, username, password_hash, role, display_name, enabled
                FROM app_users
                WHERE username = ?
                LIMIT 1
                """,
                (str(username or "").strip(),),
            ).fetchone()
        if not row or not bool(row["enabled"]):
            return None
        if not verify_password(password, str(row["password_hash"] or "")):
            return None
        payload = dict(row)
        payload.pop("password_hash", None)
        return payload

    def allowed_advertiser_ids_for_user(self, user: dict[str, Any] | None) -> set[int] | None:
        if not user:
            return None
        if str(user.get("role") or "") == ROLE_ADMIN:
            return None
        with self.db() as conn:
            rows = conn.execute(
                "SELECT advertiser_id FROM user_account_scopes WHERE user_id = ?",
                (int(user["id"]),),
            ).fetchall()
        return {int(row["advertiser_id"]) for row in rows}

    def list_users(self) -> list[dict[str, Any]]:
        with self.db() as conn:
            rows = conn.execute(
                """
                SELECT id, username, role, display_name, enabled, created_at, updated_at
                FROM app_users
                ORDER BY role ASC, username ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def create_user(self, payload: AppUserPayload) -> dict[str, Any]:
        password = str(payload.password or "").strip()
        if not password:
            raise ValueError("创建账号时必须填写密码。")
        now = now_text()
        password_hash = build_password_hash(password)
        with self.db() as conn:
            exists = conn.execute(
                "SELECT 1 FROM app_users WHERE username = ? LIMIT 1",
                (str(payload.username).strip(),),
            ).fetchone()
            if exists:
                raise ValueError("用户名已存在。")
            conn.execute(
                """
                INSERT INTO app_users (username, password_hash, role, display_name, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.username).strip(),
                    password_hash,
                    str(payload.role).strip(),
                    str(payload.display_name).strip(),
                    1 if payload.enabled else 0,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT id
                FROM app_users
                WHERE username = ?
                LIMIT 1
                """,
                (str(payload.username).strip(),),
            ).fetchone()
        return self.get_user_by_id(int(row["id"])) if row else {}

    def update_user(self, user_id: int, payload: AppUserPayload) -> dict[str, Any]:
        current = self.get_user_by_id(user_id)
        if not current:
            raise ValueError("用户不存在。")
        with self.db() as conn:
            exists = conn.execute(
                """
                SELECT 1
                FROM app_users
                WHERE username = ? AND id <> ?
                LIMIT 1
                """,
                (str(payload.username).strip(), user_id),
            ).fetchone()
            if exists:
                raise ValueError("用户名已存在。")
        params: list[Any] = [
            str(payload.username).strip(),
            str(payload.role).strip(),
            str(payload.display_name).strip(),
            1 if payload.enabled else 0,
            now_text(),
        ]
        sql = """
            UPDATE app_users
            SET username = ?, role = ?, display_name = ?, enabled = ?, updated_at = ?
        """
        password = str(payload.password or "").strip()
        if password:
            sql += ", password_hash = ?"
            params.append(build_password_hash(password))
        sql += " WHERE id = ?"
        params.append(user_id)
        with self.db() as conn:
            conn.execute(sql, tuple(params))
        return self.get_user_by_id(user_id) or {}

    def user_account_scopes(self, user_id: int) -> list[int]:
        with self.db() as conn:
            rows = conn.execute(
                """
                SELECT advertiser_id
                FROM user_account_scopes
                WHERE user_id = ?
                ORDER BY advertiser_id ASC
                """,
                (user_id,),
            ).fetchall()
        return [int(row["advertiser_id"]) for row in rows]

    def replace_user_account_scopes(self, user_id: int, advertiser_ids: list[int]) -> list[int]:
        if not self.get_user_by_id(user_id):
            raise ValueError("用户不存在。")
        unique_ids = sorted({int(item) for item in advertiser_ids if int(item) > 0})
        now = now_text()
        with self.db() as conn:
            conn.execute("DELETE FROM user_account_scopes WHERE user_id = ?", (user_id,))
            if unique_ids:
                conn.executemany(
                    """
                    INSERT INTO user_account_scopes (user_id, advertiser_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    [(user_id, advertiser_id, now) for advertiser_id in unique_ids],
                )
        return unique_ids

    def list_employees(self) -> list[dict[str, Any]]:
        with self.db() as conn:
            employee_rows = conn.execute(
                """
                SELECT id, display_name, note, enabled, created_at, updated_at
                FROM employees
                ORDER BY enabled DESC, display_name ASC
                """
            ).fetchall()
            keyword_rows = conn.execute(
                """
                SELECT employee_id, COUNT(*) AS keyword_count
                FROM employee_keywords
                GROUP BY employee_id
                """
            ).fetchall()
            binding_rows = conn.execute(
                """
                SELECT employee_id, COUNT(*) AS binding_count
                FROM employee_manual_bindings
                GROUP BY employee_id
                """
            ).fetchall()
        keyword_count = {int(row["employee_id"]): int(row["keyword_count"]) for row in keyword_rows}
        binding_count = {int(row["employee_id"]): int(row["binding_count"]) for row in binding_rows}
        items: list[dict[str, Any]] = []
        for row in employee_rows:
            item = dict(row)
            item["keyword_count"] = keyword_count.get(int(row["id"]), 0)
            item["binding_count"] = binding_count.get(int(row["id"]), 0)
            item["enabled"] = bool(item["enabled"])
            items.append(item)
        return items

    def employee_detail(self, employee_id: int) -> dict[str, Any] | None:
        with self.db() as conn:
            row = conn.execute(
                """
                SELECT id, display_name, note, enabled, created_at, updated_at
                FROM employees
                WHERE id = ?
                LIMIT 1
                """,
                (employee_id,),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        return item

    def create_employee(self, payload: EmployeePayload) -> dict[str, Any]:
        now = now_text()
        with self.db() as conn:
            exists = conn.execute(
                "SELECT 1 FROM employees WHERE display_name = ? LIMIT 1",
                (str(payload.display_name).strip(),),
            ).fetchone()
            if exists:
                raise ValueError("归属人名称已存在。")
            conn.execute(
                """
                INSERT INTO employees (display_name, note, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(payload.display_name).strip(),
                    str(payload.note).strip(),
                    1 if payload.enabled else 0,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT id
                FROM employees
                WHERE display_name = ?
                LIMIT 1
                """,
                (str(payload.display_name).strip(),),
            ).fetchone()
        return self.employee_detail(int(row["id"])) if row else {}

    def update_employee(self, employee_id: int, payload: EmployeePayload) -> dict[str, Any]:
        if not self.employee_detail(employee_id):
            raise ValueError("归属人不存在。")
        with self.db() as conn:
            exists = conn.execute(
                """
                SELECT 1
                FROM employees
                WHERE display_name = ? AND id <> ?
                LIMIT 1
                """,
                (str(payload.display_name).strip(), employee_id),
            ).fetchone()
            if exists:
                raise ValueError("归属人名称已存在。")
            conn.execute(
                """
                UPDATE employees
                SET display_name = ?, note = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(payload.display_name).strip(),
                    str(payload.note).strip(),
                    1 if payload.enabled else 0,
                    now_text(),
                    employee_id,
                ),
            )
        return self.employee_detail(employee_id) or {}

    def list_employee_keywords(self, employee_id: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT k.id, k.employee_id, e.display_name AS employee_name, k.keyword, k.scope, k.priority,
                   k.enabled, k.created_at, k.updated_at
            FROM employee_keywords AS k
            INNER JOIN employees AS e ON e.id = k.employee_id
        """
        params: tuple[Any, ...] = ()
        if employee_id is not None:
            query += " WHERE k.employee_id = ?"
            params = (employee_id,)
        query += " ORDER BY e.display_name ASC, k.priority ASC, LENGTH(k.keyword) DESC, k.id ASC"
        with self.db() as conn:
            rows = conn.execute(query, params).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            item["enabled"] = bool(item["enabled"])
        return items

    def create_employee_keyword(self, employee_id: int, payload: EmployeeKeywordPayload) -> dict[str, Any]:
        if not self.employee_detail(employee_id):
            raise ValueError("归属人不存在。")
        now = now_text()
        with self.db() as conn:
            exists = conn.execute(
                """
                SELECT 1
                FROM employee_keywords
                WHERE employee_id = ? AND keyword = ? AND scope = ?
                LIMIT 1
                """,
                (employee_id, str(payload.keyword).strip(), str(payload.scope).strip()),
            ).fetchone()
            if exists:
                raise ValueError("同一归属人下已存在相同关键词。")
            conn.execute(
                """
                INSERT INTO employee_keywords (employee_id, keyword, scope, priority, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    employee_id,
                    str(payload.keyword).strip(),
                    str(payload.scope).strip(),
                    int(payload.priority),
                    1 if payload.enabled else 0,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT id
                FROM employee_keywords
                WHERE employee_id = ? AND keyword = ? AND scope = ? AND created_at = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (employee_id, str(payload.keyword).strip(), str(payload.scope).strip(), now),
            ).fetchone()
        keyword_id = int(row["id"]) if row else 0
        return next((item for item in self.list_employee_keywords(employee_id) if int(item["id"]) == keyword_id), {})

    def update_employee_keyword(self, keyword_id: int, payload: EmployeeKeywordPayload) -> dict[str, Any]:
        now = now_text()
        with self.db() as conn:
            row = conn.execute(
                "SELECT employee_id FROM employee_keywords WHERE id = ? LIMIT 1",
                (keyword_id,),
            ).fetchone()
            if not row:
                raise ValueError("关键词不存在。")
            employee_id = int(row["employee_id"])
            conn.execute(
                """
                UPDATE employee_keywords
                SET keyword = ?, scope = ?, priority = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(payload.keyword).strip(),
                    str(payload.scope).strip(),
                    int(payload.priority),
                    1 if payload.enabled else 0,
                    now,
                    keyword_id,
                ),
            )
        return next((item for item in self.list_employee_keywords(employee_id) if int(item["id"]) == keyword_id), {})

    def delete_employee_keyword(self, keyword_id: int) -> None:
        with self.db() as conn:
            conn.execute("DELETE FROM employee_keywords WHERE id = ?", (keyword_id,))

    def list_employee_bindings(self, employee_id: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT b.id, b.employee_id, e.display_name AS employee_name, b.object_type, b.object_key,
                   b.object_label, b.note, b.created_at, b.updated_at
            FROM employee_manual_bindings AS b
            INNER JOIN employees AS e ON e.id = b.employee_id
        """
        params: tuple[Any, ...] = ()
        if employee_id is not None:
            query += " WHERE b.employee_id = ?"
            params = (employee_id,)
        query += " ORDER BY e.display_name ASC, b.object_type ASC, b.object_label ASC, b.id ASC"
        with self.db() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def create_employee_binding(self, employee_id: int, payload: EmployeeBindingPayload) -> dict[str, Any]:
        if not self.employee_detail(employee_id):
            raise ValueError("归属人不存在。")
        now = now_text()
        with self.db() as conn:
            exists = conn.execute(
                """
                SELECT 1
                FROM employee_manual_bindings
                WHERE object_type = ? AND object_key = ?
                LIMIT 1
                """,
                (str(payload.object_type).strip(), str(payload.object_key).strip()),
            ).fetchone()
            if exists:
                raise ValueError("该对象已经绑定到其他归属人。")
            conn.execute(
                """
                INSERT INTO employee_manual_bindings (employee_id, object_type, object_key, object_label, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    employee_id,
                    str(payload.object_type).strip(),
                    str(payload.object_key).strip(),
                    str(payload.object_label).strip(),
                    str(payload.note).strip(),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT id
                FROM employee_manual_bindings
                WHERE employee_id = ? AND object_type = ? AND object_key = ?
                LIMIT 1
                """,
                (employee_id, str(payload.object_type).strip(), str(payload.object_key).strip()),
            ).fetchone()
        binding_id = int(row["id"]) if row else 0
        return next((item for item in self.list_employee_bindings(employee_id) if int(item["id"]) == binding_id), {})

    def delete_employee_binding(self, binding_id: int) -> None:
        with self.db() as conn:
            conn.execute("DELETE FROM employee_manual_bindings WHERE id = ?", (binding_id,))

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
        with self.db() as conn:
            latest_summary = self._latest_summary_meta(conn)
            latest_extended = self._latest_extended_sync_run(conn)
            accounts: list[dict[str, Any]] = []
            plans: list[dict[str, Any]] = []
            products: list[dict[str, Any]] = []
            materials: list[dict[str, Any]] = []
            if latest_summary:
                snapshot_time = str(latest_summary["snapshot_time"])
                accounts = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT advertiser_id, advertiser_name
                        FROM account_snapshots
                        WHERE snapshot_time = ?
                        ORDER BY advertiser_name ASC, advertiser_id ASC
                        """,
                        (snapshot_time,),
                    ).fetchall()
                ]
                plans = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT advertiser_id, advertiser_name, ad_id, ad_name, product_id, product_name
                        FROM plan_snapshots
                        WHERE snapshot_time = ?
                        ORDER BY ad_name ASC, ad_id ASC
                        """,
                        (snapshot_time,),
                    ).fetchall()
                ]
            if latest_extended:
                extended_snapshot = str(latest_extended["snapshot_time"])
                products = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT advertiser_id, advertiser_name, ad_id, ad_name, product_key, product_id, product_name
                        FROM product_snapshots
                        WHERE snapshot_time = ?
                        ORDER BY product_name ASC, product_id ASC, product_key ASC
                        """,
                        (extended_snapshot,),
                    ).fetchall()
                ]
                materials = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT advertiser_id, advertiser_name, ad_id, ad_name, material_key, material_id, material_name, video_id, material_type
                        FROM material_snapshots
                        WHERE snapshot_time = ?
                        ORDER BY material_name ASC, material_id ASC, material_key ASC
                        """,
                        (extended_snapshot,),
                    ).fetchall()
                ]
        return {
            "summary_snapshot_time": str(latest_summary["snapshot_time"]) if latest_summary else "",
            "detail_snapshot_time": str(latest_extended["snapshot_time"]) if latest_extended else "",
            "accounts": accounts,
            "plans": plans,
            "products": products,
            "materials": materials,
        }

    @staticmethod
    def _normalize_match_text(*values: Any) -> str:
        return " ".join(str(value or "").strip() for value in values if str(value or "").strip()).casefold()

    def preview_keyword_matches(self, keyword: str, scope: str = "all", allowed_advertiser_ids: set[int] | None = None) -> dict[str, Any]:
        needle = str(keyword or "").strip()
        scope_value = str(scope or "all").strip().lower()
        if not needle:
            raise ValueError("关键词不能为空。")
        if scope_value not in EMPLOYEE_KEYWORD_SCOPES:
            raise ValueError("scope 必须是 all/account/plan/product/material 之一。")
        catalog = self._reference_catalog()
        allowed = None if allowed_advertiser_ids is None else {int(item) for item in allowed_advertiser_ids}
        matcher = needle.casefold()

        def allowed_row(row: dict[str, Any]) -> bool:
            if allowed is None:
                return True
            advertiser_id = int(row.get("advertiser_id", 0) or 0)
            return advertiser_id in allowed

        sections: dict[str, list[dict[str, Any]]] = {"accounts": [], "plans": [], "products": [], "materials": []}
        if scope_value in {"all", "account"}:
            for row in catalog["accounts"]:
                if not allowed_row(row):
                    continue
                if matcher in self._normalize_match_text(row.get("advertiser_name"), row.get("advertiser_id")):
                    sections["accounts"].append(row)
        if scope_value in {"all", "plan"}:
            for row in catalog["plans"]:
                if not allowed_row(row):
                    continue
                if matcher in self._normalize_match_text(row.get("ad_name"), row.get("ad_id"), row.get("advertiser_name")):
                    sections["plans"].append(row)
        if scope_value in {"all", "product"}:
            for row in catalog["products"]:
                if not allowed_row(row):
                    continue
                if matcher in self._normalize_match_text(
                    row.get("product_name"),
                    row.get("product_id"),
                    row.get("product_key"),
                    row.get("ad_name"),
                ):
                    sections["products"].append(row)
        if scope_value in {"all", "material"}:
            for row in catalog["materials"]:
                if not allowed_row(row):
                    continue
                if matcher in self._normalize_match_text(
                    row.get("material_name"),
                    row.get("material_id"),
                    row.get("material_key"),
                    row.get("video_id"),
                    row.get("ad_name"),
                ):
                    sections["materials"].append(row)
        return {
            "keyword": needle,
            "scope": scope_value,
            "summary_snapshot_time": catalog["summary_snapshot_time"],
            "detail_snapshot_time": catalog["detail_snapshot_time"],
            "counts": {key: len(value) for key, value in sections.items()},
            "items": sections,
        }

    def read_config(self) -> dict[str, Any]:
        return load_runtime_config(CONFIG_PATH)

    def build_client(self, config: dict[str, Any]) -> OceanEngineClient:
        return OceanEngineClient(
            config=config,
            token_cache_path=TOKEN_CACHE_PATH,
            latest_token_path=LATEST_TOKEN_PATH,
            token_persist_callback=self.persist_token_record,
        )

    def persist_token_record(self, payload: dict[str, Any]) -> None:
        app_id = str(payload.get("app_id") or "").strip()
        customer_center_id = str(payload.get("customer_center_id") or "").strip()
        if not app_id or not customer_center_id:
            return
        with self.db() as conn:
            conn.execute(
                """
                INSERT INTO oauth_tokens (
                    app_id, customer_center_id, access_token, refresh_token,
                    expires_at, refresh_token_expires_in, updated_at, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (app_id, customer_center_id) DO UPDATE SET
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    expires_at = excluded.expires_at,
                    refresh_token_expires_in = excluded.refresh_token_expires_in,
                    updated_at = excluded.updated_at,
                    source = excluded.source
                """,
                (
                    app_id,
                    customer_center_id,
                    str(payload.get("access_token") or ""),
                    str(payload.get("refresh_token") or ""),
                    int(payload.get("expires_at") or 0),
                    int(payload.get("refresh_token_expires_in") or 0),
                    int(payload.get("updated_at") or int(time.time())),
                    str(payload.get("source") or "runtime"),
                ),
            )

    def _db_token_payload(self) -> dict[str, Any] | None:
        config = self.read_config()
        with self.db() as conn:
            row = conn.execute(
                """
                SELECT app_id, customer_center_id, access_token, refresh_token,
                       expires_at, refresh_token_expires_in, updated_at, source
                FROM oauth_tokens
                WHERE app_id = ? AND customer_center_id = ?
                LIMIT 1
                """,
                (str(config["app_id"]), str(config["customer_center_id"])),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def bootstrap_token_store(self) -> None:
        existing = self._db_token_payload()
        if existing:
            return
        client = self.build_client(self.read_config())
        payload = client.latest_token_payload()
        if payload.get("access_token") or payload.get("refresh_token"):
            payload["source"] = "file_cache"
            self.persist_token_record(payload)

    @staticmethod
    def _mask_token(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if len(text) <= 10:
            return text
        return f"{text[:4]}...{text[-6:]}"

    def latest_token_payload(self, masked: bool = False) -> dict[str, Any]:
        payload = self._db_token_payload()
        if not payload:
            config = self.read_config()
            client = self.build_client(config)
            payload = client.latest_token_payload()
            if payload.get("access_token") or payload.get("refresh_token"):
                payload["source"] = "file_cache"
                self.persist_token_record(payload)
        if not masked:
            return payload
        masked_payload = dict(payload)
        masked_payload["access_token"] = self._mask_token(masked_payload.get("access_token", ""))
        masked_payload["refresh_token"] = self._mask_token(masked_payload.get("refresh_token", ""))
        return masked_payload

    def exchange_auth_code(self, auth_code: str) -> dict[str, Any]:
        config = self.read_config()
        client = self.build_client(config)
        return client.exchange_auth_code(auth_code)

    @staticmethod
    def _decorate_plan_item(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["marketing_goal_label"] = plan_marketing_goal_label(item["marketing_goal"])
        item["marketing_goal_text"] = item["marketing_goal_label"]
        item["status_label"] = plan_delivery_status_label(item["status"])
        item["opt_status_label"] = plan_opt_status_label(item["opt_status"])
        item["status_text"] = format_plan_status_text(item["status"], item["opt_status"])
        item["status_code_text"] = f"{item['status']} / {item['opt_status']}".strip(" /")
        return item

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

    def _build_material_rankings(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                    "stat_cost": 0.0,
                    "pay_amount": 0.0,
                    "order_count": 0,
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
            order_count = int(float(row.get("order_count", 0.0) or 0.0))
            group["stat_cost"] = round(group["stat_cost"] + stat_cost, 2)
            group["pay_amount"] = round(group["pay_amount"] + pay_amount, 2)
            group["order_count"] += order_count
            group["plan_ids"].add(int(row.get("ad_id", 0) or 0))
            group["advertiser_ids"].add(int(row.get("advertiser_id", 0) or 0))
            group["is_original"] = bool(group["is_original"] or row.get("is_original"))
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

        material_rows: list[dict[str, Any]] = []
        for group in groups.values():
            roi = round(group["pay_amount"] / group["stat_cost"], 2) if group["stat_cost"] > 0 else 0.0
            material_rows.append(
                {
                    "material_key": group["material_key"],
                    "material_id": group["material_id"],
                    "material_name": group["material_name"],
                    "material_type": group["material_type"],
                    "video_id": group["video_id"],
                    "stat_cost": group["stat_cost"],
                    "pay_amount": group["pay_amount"],
                    "order_count": group["order_count"],
                    "plan_count": len(group["plan_ids"]),
                    "advertiser_count": len(group["advertiser_ids"]),
                    "is_original": bool(group["is_original"]),
                    "top_plan_name": group["top_plan_name"],
                    "top_account_name": group["top_account_name"],
                    "roi": roi,
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

    def _rankings_bundle(
        self, summary: dict[str, Any], accounts: list[dict[str, Any]], plans: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        products = self._build_product_rankings(plans)
        employees = self._build_employee_rankings(plans)
        enriched_summary = dict(summary)
        enriched_summary["product_count"] = len(products)
        enriched_summary["active_product_count"] = sum(1 for item in products if float(item["stat_cost"]) > 0)
        enriched_summary["employee_count"] = len(employees)
        enriched_summary["active_employee_count"] = sum(1 for item in employees if float(item["stat_cost"]) > 0)
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
        return enriched_summary, products, employees

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

    def _apply_account_scope(
        self, payload: dict[str, Any], allowed_advertiser_ids: set[int] | None
    ) -> dict[str, Any]:
        if allowed_advertiser_ids is None:
            return payload
        allowed = {int(item) for item in allowed_advertiser_ids}
        accounts = [dict(item) for item in payload.get("accounts", []) if int(item.get("advertiser_id", 0) or 0) in allowed]
        plans = [dict(item) for item in payload.get("plans", []) if int(item.get("advertiser_id", 0) or 0) in allowed]
        account_balances = [
            dict(item) for item in payload.get("accountBalances", []) if int(item.get("advertiser_id", 0) or 0) in allowed
        ]
        wallet_relations = [
            dict(item) for item in payload.get("walletRelations", []) if int(item.get("advertiser_id", 0) or 0) in allowed
        ]
        allowed_wallet_ids = {str(item.get("main_wallet_id") or "") for item in wallet_relations if str(item.get("main_wallet_id") or "")}
        shared_wallets = [
            dict(item) for item in payload.get("sharedWallets", []) if str(item.get("main_wallet_id") or "") in allowed_wallet_ids
        ]
        next_payload = dict(payload)
        next_payload["accounts"] = accounts
        next_payload["plans"] = plans
        next_payload["accountBalances"] = account_balances
        next_payload["walletRelations"] = wallet_relations
        next_payload["sharedWallets"] = shared_wallets
        next_payload["summary"], next_payload["products"], next_payload["employees"] = self._rankings_bundle(
            self._scoped_summary(accounts, plans),
            accounts,
            plans,
        )
        return next_payload

    @staticmethod
    def _wallet_display_name(wallet_id: str, member_count: int) -> str:
        text = str(wallet_id or "").strip()
        if not text:
            return "未命名钱包"
        suffix = text[-6:] if len(text) > 6 else text
        return f"{'共享钱包' if member_count > 1 else '钱包'} {suffix}"

    def _collect_balance_snapshot(self, client: OceanEngineClient, accounts: list[dict[str, Any]]) -> dict[str, Any]:
        account_ids = [int(item.get("advertiser_id", 0) or 0) for item in accounts if int(item.get("advertiser_id", 0) or 0)]
        account_map = {int(item["advertiser_id"]): item for item in accounts if int(item.get("advertiser_id", 0) or 0)}
        if not account_ids:
            return {
                "account_balances": [],
                "shared_wallets": [],
                "wallet_relations": [],
                "errors": [],
            }

        try:
            rows = client.list_account_funds(account_ids, account_type="QIANCHUAN")
        except Exception as exc:  # noqa: BLE001
            return {
                "account_balances": [],
                "shared_wallets": [],
                "wallet_relations": [],
                "errors": [
                    {
                        "stage": "account_fund_get",
                        "error": str(exc),
                    }
                ],
            }
        fund_map = {int(item.get("account_id", 0) or 0): item for item in rows if int(item.get("account_id", 0) or 0)}

        account_balance_rows: list[dict[str, Any]] = []
        shared_wallet_groups: dict[str, dict[str, Any]] = {}
        errors: list[dict[str, Any]] = []

        for advertiser_id in account_ids:
            meta = account_map.get(advertiser_id) or {}
            raw = fund_map.get(advertiser_id)
            if not raw:
                errors.append(
                    {
                        "stage": "account_fund_get",
                        "advertiser_id": advertiser_id,
                        "error": "missing account fund row",
                    }
                )
                continue

            advertiser_name = str(meta.get("advertiser_name") or raw.get("account_id") or advertiser_id)
            wallet_id = str(raw.get("wallet_id") or "").strip()
            balance = normalize_account_fund_money(raw.get("balance"))
            valid_balance = normalize_account_fund_money(raw.get("valid_balance"))
            wallet_valid_balance = normalize_account_fund_money(raw.get("wallet_total_balance_valid"))
            account_balance_rows.append(
                {
                    "advertiser_id": advertiser_id,
                    "advertiser_name": advertiser_name,
                    "account_balance": balance,
                    "available_balance": valid_balance,
                    "wallet_id": wallet_id,
                    "wallet_balance": wallet_valid_balance,
                    "stat_cost": 0.0,
                    "pay_amount": 0.0,
                    "order_count": 0,
                    "roi": 0.0,
                    "raw_json": self._json_text(raw),
                }
            )

            if not wallet_id:
                continue
            group = shared_wallet_groups.setdefault(
                wallet_id,
                {
                    "main_wallet_id": wallet_id,
                    "account_ids": set(),
                    "account_names": [],
                    "valid_balances": [],
                    "rows": [],
                },
            )
            group["account_ids"].add(advertiser_id)
            group["account_names"].append(advertiser_name)
            group["valid_balances"].append(wallet_valid_balance)
            group["rows"].append(raw)

        shared_wallet_rows: list[dict[str, Any]] = []
        wallet_relation_rows: list[dict[str, Any]] = []
        for wallet_id, group in shared_wallet_groups.items():
            member_count = len(group["account_ids"])
            if member_count < 2:
                continue
            wallet_name = self._wallet_display_name(wallet_id, member_count)
            valid_balance = max((float(item or 0.0) for item in group["valid_balances"]), default=0.0)
            shared_wallet_rows.append(
                {
                    "main_wallet_id": wallet_id,
                    "wallet_name": wallet_name,
                    "wallet_balance": round(valid_balance, 2),
                    "total_balance": round(valid_balance, 2),
                    "valid_balance": round(valid_balance, 2),
                    "member_count": member_count,
                    "stat_cost": 0.0,
                    "pay_amount": 0.0,
                    "order_count": 0,
                    "roi": 0.0,
                    "raw_json": self._json_text(
                        {
                            "source": "account_fund_get_v3.0",
                            "account_ids": sorted(group["account_ids"]),
                            "account_names": group["account_names"],
                            "rows": group["rows"],
                        }
                    ),
                }
            )
            for advertiser_id in sorted(group["account_ids"]):
                advertiser_name = str(account_map.get(advertiser_id, {}).get("advertiser_name") or advertiser_id)
                wallet_relation_rows.append(
                    {
                        "main_wallet_id": wallet_id,
                        "advertiser_id": advertiser_id,
                        "advertiser_name": advertiser_name,
                        "child_wallet_id": wallet_id,
                        "wallet_name": wallet_name,
                        "raw_json": self._json_text(
                            {
                                "source": "account_fund_get_v3.0",
                                "wallet_id": wallet_id,
                                "advertiser_id": advertiser_id,
                            }
                        ),
                    }
                )

        account_balance_rows.sort(key=lambda item: (-float(item["available_balance"]), int(item["advertiser_id"])))
        shared_wallet_rows.sort(key=lambda item: (-float(item["valid_balance"]), str(item["main_wallet_id"])))
        wallet_relation_rows.sort(key=lambda item: (str(item["main_wallet_id"]), int(item["advertiser_id"])))
        return {
            "account_balances": account_balance_rows,
            "shared_wallets": shared_wallet_rows,
            "wallet_relations": wallet_relation_rows,
            "errors": errors,
        }

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

    def _snapshot_account_balances(self, conn: Any, snapshot_time: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT *
            FROM account_balances
            WHERE snapshot_time = ?
            ORDER BY available_balance DESC, advertiser_id ASC
            """,
            (snapshot_time,),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                raw = json.loads(str(item.get("raw_json") or "{}"))
            except Exception:
                raw = {}
            item["wallet_id"] = str(raw.get("wallet_id") or "")
            item["wallet_balance"] = normalize_account_fund_money(raw.get("wallet_total_balance_valid"))
            items.append(item)
        return items

    def _snapshot_shared_wallets(self, conn: Any, snapshot_time: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT w.*,
                   COALESCE(rel.member_count, 0) AS member_count
            FROM shared_wallets AS w
            LEFT JOIN (
                SELECT snapshot_time, main_wallet_id, COUNT(*) AS member_count
                FROM shared_wallet_account_relations
                GROUP BY snapshot_time, main_wallet_id
            ) AS rel
              ON rel.snapshot_time = w.snapshot_time
             AND rel.main_wallet_id = w.main_wallet_id
            WHERE w.snapshot_time = ?
            ORDER BY w.valid_balance DESC, w.main_wallet_id ASC
            """,
            (snapshot_time,),
        ).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            item["wallet_balance"] = item.get("valid_balance", 0)
        return items

    def _snapshot_wallet_relations(self, conn: Any, snapshot_time: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT *
            FROM shared_wallet_account_relations
            WHERE snapshot_time = ?
            ORDER BY main_wallet_id ASC, advertiser_id ASC
            """,
            (snapshot_time,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _latest_summary_meta(self, conn: Any) -> Any:
        return conn.execute(
            """
            SELECT snapshot_time, window_start, window_end
            FROM summary_snapshots
            ORDER BY snapshot_time DESC
            LIMIT 1
            """
        ).fetchone()

    def _latest_extended_sync_run(self, conn: Any) -> Any:
        return conn.execute(
            """
            SELECT *
            FROM extended_sync_runs
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

    def _collect_window_snapshot(self, start_dt: datetime, end_dt: datetime) -> dict[str, Any]:
        config = self.read_config()
        client = self.build_client(config)
        accounts = client.list_accounts()
        balance_snapshot = self._collect_balance_snapshot(client, accounts)
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
                    product_id, product_name, anchor_name, marketing_goal, status,
                    opt_status, roi_goal, stat_cost, roi, order_count, pay_amount
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        item["status"],
                        item["opt_status"],
                        item["roi_goal"],
                        item["stat_cost"],
                        item["roi"],
                        item["order_count"],
                        item["pay_amount"],
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

    def collect_extended_snapshot(self) -> dict[str, Any]:
        config = self.read_config()
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
            plans = self._snapshot_plans(conn, meta["snapshot_time"])

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
            "video_flag_rows": video_flag_rows,
            "errors": errors,
        }

    def persist_extended_snapshot(self, payload: dict[str, Any]) -> None:
        if payload.get("skipped"):
            return
        with self.db() as conn:
            conn.execute("DELETE FROM plan_detail_snapshots WHERE snapshot_time = ?", (payload["snapshot_time"],))
            conn.execute("DELETE FROM product_snapshots WHERE snapshot_time = ?", (payload["snapshot_time"],))
            conn.execute("DELETE FROM material_snapshots WHERE snapshot_time = ?", (payload["snapshot_time"],))
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
                        video_id, product_show_count, product_click_count, stat_cost,
                        pay_amount, order_count, roi, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload["material_rows"],
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

    def latest_snapshot(self, allowed_advertiser_ids: set[int] | None = None) -> dict[str, Any] | None:
        with self.db() as conn:
            latest = conn.execute(
                "SELECT snapshot_time FROM summary_snapshots ORDER BY snapshot_time DESC LIMIT 1"
            ).fetchone()
            if not latest:
                return None
            snapshot_time = latest["snapshot_time"]
            summary = conn.execute(
                "SELECT * FROM summary_snapshots WHERE snapshot_time = ?",
                (snapshot_time,),
            ).fetchone()
            accounts = conn.execute(
                """
                SELECT * FROM account_snapshots
                WHERE snapshot_time = ?
                ORDER BY stat_cost DESC, advertiser_id ASC
                """,
                (snapshot_time,),
            ).fetchall()
            plans = conn.execute(
                """
                SELECT * FROM plan_snapshots
                WHERE snapshot_time = ?
                ORDER BY order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, ad_id ASC
                """,
                (snapshot_time,),
            ).fetchall()
            account_items = [dict(row) for row in accounts]
            plan_items = self._apply_employee_attribution(
                [self._decorate_plan_item(row) for row in plans],
                account_items,
            )
            account_balance_items = self._snapshot_account_balances(conn, snapshot_time)
            shared_wallet_items = self._snapshot_shared_wallets(conn, snapshot_time)
            wallet_relation_items = self._snapshot_wallet_relations(conn, snapshot_time)
            summary_payload, products, employees = self._rankings_bundle(
                dict(summary),
                account_items,
                plan_items,
            )
            summary_payload["wallet_count"] = len(shared_wallet_items)
            summary_payload["account_balance_count"] = len(account_balance_items)
            extended_run = conn.execute(
                "SELECT * FROM extended_sync_runs WHERE snapshot_time = ?",
                (snapshot_time,),
            ).fetchone()
            payload = {
                "snapshot_time": snapshot_time,
                "summary": summary_payload,
                "accounts": account_items,
                "plans": plan_items,
                "accountBalances": account_balance_items,
                "sharedWallets": shared_wallet_items,
                "walletRelations": wallet_relation_items,
                "products": products,
                "employees": employees,
                "extendedSync": dict(extended_run) if extended_run else None,
            }
            return self._apply_account_scope(payload, allowed_advertiser_ids)

    def latest_extended_sync(self) -> dict[str, Any] | None:
        with self.db() as conn:
            row = self._latest_extended_sync_run(conn)
        return dict(row) if row else None

    def plan_assets(
        self, ad_id: int, snapshot_time: str = "", allowed_advertiser_ids: set[int] | None = None
    ) -> dict[str, Any]:
        with self.db() as conn:
            target_snapshot = str(snapshot_time or "").strip()
            if not target_snapshot:
                latest = self._latest_summary_meta(conn)
                if not latest:
                    return {"snapshot_time": "", "plan": None, "detail": None, "products": [], "materials": []}
                target_snapshot = str(latest["snapshot_time"])

            plan_row = conn.execute(
                """
                SELECT *
                FROM plan_snapshots
                WHERE snapshot_time = ? AND ad_id = ?
                LIMIT 1
                """,
                (target_snapshot, ad_id),
            ).fetchone()
            detail_row = conn.execute(
                """
                SELECT *
                FROM plan_detail_snapshots
                WHERE snapshot_time = ? AND ad_id = ?
                LIMIT 1
                """,
                (target_snapshot, ad_id),
            ).fetchone()
            products = conn.execute(
                """
                SELECT *
                FROM product_snapshots
                WHERE snapshot_time = ? AND ad_id = ?
                ORDER BY order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, product_key ASC
                """,
                (target_snapshot, ad_id),
            ).fetchall()
            materials = conn.execute(
                """
                SELECT *
                FROM material_snapshots
                WHERE snapshot_time = ? AND ad_id = ?
                ORDER BY order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, material_type ASC, material_key ASC
                """,
                (target_snapshot, ad_id),
            ).fetchall()
            original_flags = {
                str(row["material_id"]): bool(row["is_original"])
                for row in conn.execute(
                    """
                    SELECT material_id, is_original
                    FROM video_origin_flags
                    WHERE snapshot_time = ? AND advertiser_id = (
                        SELECT advertiser_id
                        FROM plan_snapshots
                        WHERE snapshot_time = ? AND ad_id = ?
                        LIMIT 1
                    )
                    """,
                    (target_snapshot, target_snapshot, ad_id),
                ).fetchall()
            }

        if plan_row and allowed_advertiser_ids is not None:
            allowed = {int(item) for item in allowed_advertiser_ids}
            if int(plan_row["advertiser_id"] or 0) not in allowed:
                return {"snapshot_time": target_snapshot, "plan": None, "detail": None, "products": [], "materials": []}

        plan_payload = self._decorate_plan_item(plan_row) if plan_row else None
        detail_payload = dict(detail_row) if detail_row else None
        if detail_payload:
            detail_payload["marketing_goal_label"] = plan_marketing_goal_label(detail_payload["marketing_goal"])
            detail_payload["status_text"] = format_plan_status_text(detail_payload["status"], detail_payload["opt_status"])
        material_items: list[dict[str, Any]] = []
        for row in materials:
            item = dict(row)
            item["is_original"] = bool(original_flags.get(str(item["material_id"]), False))
            material_items.append(item)
        return {
            "snapshot_time": target_snapshot,
            "plan": plan_payload,
            "detail": detail_payload,
            "products": [dict(row) for row in products],
            "materials": material_items,
            "originalVideoCount": sum(1 for item in material_items if item["is_original"]),
        }

    def material_rankings(
        self, snapshot_time: str = "", allowed_advertiser_ids: set[int] | None = None
    ) -> dict[str, Any]:
        with self.db() as conn:
            target_snapshot = str(snapshot_time or "").strip()
            if not target_snapshot:
                latest = self._latest_extended_sync_run(conn)
                if not latest:
                    return {"snapshot_time": "", "items": [], "meta": None}
                target_snapshot = str(latest["snapshot_time"])
                latest_meta = dict(latest)
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

            rows = conn.execute(
                """
                SELECT m.*, COALESCE(v.is_original, 0) AS is_original
                FROM material_snapshots AS m
                LEFT JOIN video_origin_flags AS v
                  ON v.snapshot_time = m.snapshot_time
                 AND v.advertiser_id = m.advertiser_id
                 AND v.material_id = m.material_id
                WHERE m.snapshot_time = ?
                ORDER BY m.order_count DESC, m.pay_amount DESC, m.roi DESC, m.stat_cost DESC
                """,
                (target_snapshot,),
            ).fetchall()
        scoped_rows = [dict(row) for row in rows]
        if allowed_advertiser_ids is not None:
            allowed = {int(item) for item in allowed_advertiser_ids}
            scoped_rows = [row for row in scoped_rows if int(row.get("advertiser_id", 0) or 0) in allowed]
        items = self._build_material_rankings(scoped_rows)
        return {"snapshot_time": target_snapshot, "items": items, "meta": latest_meta}

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
            raise ValueError("range must be one of day/week/month/custom")
        cache_key = build_performance_cache_key(normalized, start_date, end_date)
        cached = self._range_cache.get(cache_key)
        now_ts = time.time()
        if not force_refresh and cached and now_ts - float(cached.get("_cached_at", 0.0)) < RANGE_CACHE_SECONDS:
            return self._apply_account_scope(cached["payload"], allowed_advertiser_ids)

        config = self.read_config()
        if normalized == "custom":
            start_dt, end_dt, range_label = build_custom_performance_window(start_date, end_date, config["timezone"])
        else:
            start_dt, end_dt, range_label = build_performance_window(normalized, config["timezone"])
        payload = self._collect_window_snapshot(start_dt, end_dt)
        payload["range_key"] = normalized
        payload["range_label"] = range_label
        payload["query_start_date"] = start_dt.strftime("%Y-%m-%d")
        payload["query_end_date"] = end_dt.strftime("%Y-%m-%d")
        payload["plans"] = self._apply_employee_attribution(
            [self._decorate_plan_item(item) for item in payload["plans"]],
            payload["accounts"],
        )
        payload["summary"], payload["products"], payload["employees"] = self._rankings_bundle(
            payload["summary"],
            payload["accounts"],
            payload["plans"],
        )
        self._range_cache[cache_key] = {"_cached_at": now_ts, "payload": payload}
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
        metric = sort_key if sort_key in PUBLIC_SORT_FIELDS else "stat_cost"
        direction = "asc" if sort_dir == "asc" else "desc"
        items = [dict(item) for item in payload.get("employees", [])]
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
            "items": items,
        }

    def summary_history(self, limit: int = 144) -> list[dict[str, Any]]:
        with self.db() as conn:
            rows = conn.execute(
                """
                SELECT snapshot_time, stat_cost, pay_amount, order_count, roi
                FROM summary_snapshots
                ORDER BY snapshot_time DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def account_history(
        self,
        advertiser_id: int,
        limit: int = 72,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_advertiser_ids is not None and int(advertiser_id) not in {int(item) for item in allowed_advertiser_ids}:
            return []
        with self.db() as conn:
            rows = conn.execute(
                """
                SELECT snapshot_time, stat_cost, pay_amount, order_count, roi
                FROM account_snapshots
                WHERE advertiser_id = ?
                ORDER BY snapshot_time DESC
                LIMIT ?
                """,
                (advertiser_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def plan_history(
        self,
        ad_id: int,
        limit: int = 72,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        with self.db() as conn:
            if allowed_advertiser_ids is not None:
                latest = conn.execute(
                    """
                    SELECT advertiser_id
                    FROM plan_snapshots
                    WHERE ad_id = ?
                    ORDER BY snapshot_time DESC
                    LIMIT 1
                    """,
                    (ad_id,),
                ).fetchone()
                if not latest or int(latest["advertiser_id"] or 0) not in {int(item) for item in allowed_advertiser_ids}:
                    return []
            rows = conn.execute(
                """
                SELECT snapshot_time, stat_cost, pay_amount, order_count, roi
                FROM plan_snapshots
                WHERE ad_id = ?
                ORDER BY snapshot_time DESC
                LIMIT ?
                """,
                (ad_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def get_notification_settings(self) -> dict[str, Any]:
        with self.db() as conn:
            self._ensure_notification_settings_locked(conn)
            row = conn.execute("SELECT * FROM notification_settings WHERE id = 1").fetchone()
        payload = dict(row)
        payload["enabled"] = bool(payload["enabled"])
        payload["alert_enabled"] = bool(payload["alert_enabled"])
        payload["summary_enabled"] = bool(payload["summary_enabled"])
        payload["summary_times"] = normalize_summary_times(payload["summary_times"])
        payload["summary_times_list"] = [item for item in payload["summary_times"].split(",") if item]
        return payload

    def update_notification_settings(self, payload: NotificationSettingsPayload) -> None:
        normalized_times = normalize_summary_times(payload.summary_times)
        if payload.enabled and not payload.target.strip():
            raise ValueError("启用通知前必须填写通知目标 target。")
        if payload.summary_enabled and not normalized_times:
            raise ValueError("启用定时简报前必须至少配置一个推送时间，例如 09:00,12:00。")
        with self.db() as conn:
            self._ensure_notification_settings_locked(conn)
            conn.execute(
                """
                UPDATE notification_settings
                SET enabled = ?, channel = ?, account = ?, target = ?, alert_enabled = ?,
                    alert_batch_size = ?, summary_enabled = ?, summary_times = ?,
                    summary_account_limit = ?, summary_plan_limit = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    1 if payload.enabled else 0,
                    payload.channel.strip(),
                    payload.account.strip(),
                    payload.target.strip(),
                    1 if payload.alert_enabled else 0,
                    payload.alert_batch_size,
                    1 if payload.summary_enabled else 0,
                    normalized_times,
                    payload.summary_account_limit,
                    payload.summary_plan_limit,
                    now_text(),
                ),
            )

    def list_alert_rules(self) -> list[dict[str, Any]]:
        with self.db() as conn:
            rows = conn.execute(
                "SELECT * FROM alert_rules ORDER BY entity_type ASC, metric ASC, id DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def create_alert_rule(self, payload: AlertRulePayload) -> None:
        validate_alert_rule_payload(payload)
        now_text = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
        with self.db() as conn:
            conn.execute(
                """
                INSERT INTO alert_rules (
                    entity_type, metric, operator, threshold, min_spend, cooldown_minutes,
                    enabled, target_id, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.entity_type,
                    payload.metric,
                    payload.operator,
                    payload.threshold,
                    payload.min_spend,
                    payload.cooldown_minutes,
                    1 if payload.enabled else 0,
                    payload.target_id.strip(),
                    payload.note.strip(),
                    now_text,
                    now_text,
                ),
            )

    def update_alert_rule(self, rule_id: int, payload: AlertRulePayload) -> None:
        validate_alert_rule_payload(payload)
        now_text = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
        with self.db() as conn:
            conn.execute(
                """
                UPDATE alert_rules
                SET entity_type = ?, metric = ?, operator = ?, threshold = ?, min_spend = ?,
                    cooldown_minutes = ?, enabled = ?, target_id = ?, note = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.entity_type,
                    payload.metric,
                    payload.operator,
                    payload.threshold,
                    payload.min_spend,
                    payload.cooldown_minutes,
                    1 if payload.enabled else 0,
                    payload.target_id.strip(),
                    payload.note.strip(),
                    now_text,
                    rule_id,
                ),
            )

    def delete_alert_rule(self, rule_id: int) -> None:
        with self.db() as conn:
            conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))

    def alert_events(self, limit: int = 80) -> list[dict[str, Any]]:
        with self.db() as conn:
            rows = conn.execute(
                """
                SELECT * FROM alert_events
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

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
        self._range_cache.clear()
        return payload

    def collect_extended_and_store(self) -> dict[str, Any]:
        payload = self.collect_extended_snapshot()
        if payload.get("skipped"):
            return payload
        self.persist_extended_snapshot(payload)
        self.cleanup_history()
        return payload

    async def start(self) -> None:
        self.init_db()
        self.bootstrap_auth_store()
        self.bootstrap_token_store()
        if ENABLE_IN_PROCESS_SCHEDULER:
            await self.run_sync()

    async def stop(self) -> None:
        return None


service = DashboardService()
app = FastAPI(title=APP_NAME)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")


def require_auth(request: Request) -> dict[str, Any]:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    user = service.get_user_by_id(int(user_id))
    if not user:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    return user


def require_admin(user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    if str(user.get("role") or "") != ROLE_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return user


@app.on_event("startup")
async def startup() -> None:
    if not DASHBOARD_PASSWORD:
        raise RuntimeError("DASHBOARD_PASSWORD is required")
    await service.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await service.stop()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if request.session.get("user_id"):
        return RedirectResponse("/workbench", status_code=302)
    return service.templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "app_name": APP_NAME},
    )


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    user = service.authenticate_user(username, password)
    if user:
        request.session["authenticated"] = True
        request.session["user_id"] = int(user["id"])
        request.session["username"] = str(user["username"])
        request.session["role"] = str(user["role"])
        return RedirectResponse("/workbench", status_code=302)
    return RedirectResponse("/login?error=1", status_code=302)


@app.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/", response_class=HTMLResponse)
async def public_index(request: Request) -> HTMLResponse:
    return service.templates.TemplateResponse(
        request=request,
        name="public.html",
        context={
            "request": request,
            "app_name": APP_NAME,
            "customer_center_id": service.read_config()["customer_center_id"],
        },
    )


@app.get("/workbench", response_class=HTMLResponse)
async def index(request: Request, _user: dict[str, Any] = Depends(require_auth)) -> HTMLResponse:
    return service.templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "app_name": APP_NAME,
            "customer_center_id": service.read_config()["customer_center_id"],
        },
    )


@app.get("/api/public/employee-rankings")
async def public_employee_rankings(
    range: str = "day",
    start_date: str = "",
    end_date: str = "",
    sort_key: str = "stat_cost",
    sort_dir: str = "desc",
) -> JSONResponse:
    try:
        payload = await asyncio.to_thread(service.public_employee_rankings, range, start_date, end_date, sort_key, sort_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(payload)


@app.get("/api/session/me")
async def current_session(user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
    allowed = service.allowed_advertiser_ids_for_user(user)
    return JSONResponse(
        {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "display_name": user.get("display_name") or "",
            "scope_type": "all" if allowed is None else "restricted",
            "scope_count": None if allowed is None else len(allowed),
        }
    )


@app.get("/api/employees")
async def employees(_user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
    return JSONResponse({"items": service.list_employees()})


@app.post("/api/employees")
async def create_employee(payload: EmployeePayload, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
    try:
        item = service.create_employee(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(item)


@app.put("/api/employees/{employee_id}")
async def update_employee(
    employee_id: int,
    payload: EmployeePayload,
    _user: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    try:
        item = service.update_employee(employee_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(item)


@app.get("/api/employees/{employee_id}/keywords")
async def employee_keywords(employee_id: int, _user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
    return JSONResponse({"items": service.list_employee_keywords(employee_id)})


@app.post("/api/employees/{employee_id}/keywords")
async def create_employee_keyword(
    employee_id: int,
    payload: EmployeeKeywordPayload,
    _user: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    try:
        item = service.create_employee_keyword(employee_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(item)


@app.put("/api/employee-keywords/{keyword_id}")
async def update_employee_keyword(
    keyword_id: int,
    payload: EmployeeKeywordPayload,
    _user: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    try:
        item = service.update_employee_keyword(keyword_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(item)


@app.delete("/api/employee-keywords/{keyword_id}")
async def delete_employee_keyword(keyword_id: int, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
    service.delete_employee_keyword(keyword_id)
    return JSONResponse({"ok": True})


@app.get("/api/employees/{employee_id}/bindings")
async def employee_bindings(employee_id: int, _user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
    return JSONResponse({"items": service.list_employee_bindings(employee_id)})


@app.post("/api/employees/{employee_id}/bindings")
async def create_employee_binding(
    employee_id: int,
    payload: EmployeeBindingPayload,
    _user: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    try:
        item = service.create_employee_binding(employee_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(item)


@app.delete("/api/employee-bindings/{binding_id}")
async def delete_employee_binding(binding_id: int, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
    service.delete_employee_binding(binding_id)
    return JSONResponse({"ok": True})


@app.get("/api/employee-match-preview")
async def employee_match_preview(
    keyword: str,
    scope: str = "all",
    user: dict[str, Any] = Depends(require_auth),
) -> JSONResponse:
    allowed = service.allowed_advertiser_ids_for_user(user)
    try:
        payload = service.preview_keyword_matches(keyword, scope, allowed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(payload)


@app.get("/api/users")
async def users(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
    return JSONResponse({"items": service.list_users()})


@app.post("/api/users")
async def create_user(payload: AppUserPayload, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
    try:
        item = service.create_user(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(item)


@app.put("/api/users/{user_id}")
async def update_user(
    user_id: int,
    payload: AppUserPayload,
    _user: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    try:
        item = service.update_user(user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(item)


@app.get("/api/users/{user_id}/account-scopes")
async def user_account_scopes(user_id: int, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
    return JSONResponse({"advertiser_ids": service.user_account_scopes(user_id)})


@app.put("/api/users/{user_id}/account-scopes")
async def replace_user_account_scopes(
    user_id: int,
    payload: UserScopePayload,
    _user: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    try:
        advertiser_ids = service.replace_user_account_scopes(user_id, payload.advertiser_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"advertiser_ids": advertiser_ids})


@app.get("/api/catalog/accounts")
async def available_accounts(user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
    allowed = service.allowed_advertiser_ids_for_user(user)
    return JSONResponse({"items": service.latest_account_catalog(allowed)})


@app.get("/api/dashboard")
async def dashboard_data(user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
    allowed = service.allowed_advertiser_ids_for_user(user)
    latest = service.latest_snapshot(allowed)
    return JSONResponse(
        {
            "session": {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "display_name": user.get("display_name") or "",
                "scope_type": "all" if allowed is None else "restricted",
                "scope_count": None if allowed is None else len(allowed),
            },
            "latest": latest,
            "extendedSync": service.latest_extended_sync(),
            "tokenInfo": service.latest_token_payload(masked=True),
            "summaryHistory": service.summary_history(),
            "notificationSettings": service.get_notification_settings(),
            "alertRules": service.list_alert_rules(),
            "alertEvents": service.alert_events(),
            "timezone": TIMEZONE,
        }
    )


@app.get("/api/performance")
async def performance_data(
    range: str = "day",
    start_date: str = "",
    end_date: str = "",
    user: dict[str, Any] = Depends(require_auth),
) -> JSONResponse:
    try:
        allowed = service.allowed_advertiser_ids_for_user(user)
        payload = await asyncio.to_thread(service.get_performance_snapshot, range, start_date, end_date, False, allowed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(payload)


@app.post("/api/sync")
async def manual_sync(_auth: None = Depends(require_auth)) -> JSONResponse:
    result = await service.run_sync(manual=True)
    return JSONResponse(result)


@app.post("/api/sync/extended")
async def manual_extended_sync(_auth: None = Depends(require_auth)) -> JSONResponse:
    result = await service.run_detail_sync(manual=True)
    return JSONResponse(result)


@app.get("/api/system/integrations/ocean-engine/token-latest")
async def latest_token(_auth: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
    return JSONResponse(service.latest_token_payload(masked=False))


@app.post("/api/system/integrations/ocean-engine/exchange-auth-code")
async def exchange_auth_code(
    payload: AuthCodeExchangePayload, _auth: dict[str, Any] = Depends(require_auth)
) -> JSONResponse:
    try:
        token_payload = await asyncio.to_thread(service.exchange_auth_code, payload.auth_code)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "token": token_payload})


@app.get("/api/accounts/{advertiser_id}/history")
async def account_history(advertiser_id: int, user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
    allowed = service.allowed_advertiser_ids_for_user(user)
    return JSONResponse({"items": service.account_history(advertiser_id, allowed_advertiser_ids=allowed)})


@app.get("/api/plans/{ad_id}/history")
async def plan_history(ad_id: int, user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
    allowed = service.allowed_advertiser_ids_for_user(user)
    return JSONResponse({"items": service.plan_history(ad_id, allowed_advertiser_ids=allowed)})


@app.get("/api/plans/{ad_id}/assets")
async def plan_assets(ad_id: int, snapshot_time: str = "", user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
    allowed = service.allowed_advertiser_ids_for_user(user)
    return JSONResponse(service.plan_assets(ad_id, snapshot_time, allowed))


@app.get("/api/material-rankings")
async def material_rankings(snapshot_time: str = "", user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
    allowed = service.allowed_advertiser_ids_for_user(user)
    return JSONResponse(service.material_rankings(snapshot_time, allowed))


@app.get("/api/alert-rules")
async def alert_rules(_auth: None = Depends(require_auth)) -> JSONResponse:
    return JSONResponse({"items": service.list_alert_rules()})


@app.get("/api/notification-settings")
async def notification_settings(_auth: None = Depends(require_auth)) -> JSONResponse:
    return JSONResponse(service.get_notification_settings())


@app.put("/api/notification-settings")
async def update_notification_settings(
    payload: NotificationSettingsPayload, _auth: None = Depends(require_auth)
) -> JSONResponse:
    try:
        service.update_notification_settings(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True})


@app.post("/api/alert-rules")
async def create_alert_rule(payload: AlertRulePayload, _auth: None = Depends(require_auth)) -> JSONResponse:
    try:
        service.create_alert_rule(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True})


@app.put("/api/alert-rules/{rule_id}")
async def update_alert_rule(rule_id: int, payload: AlertRulePayload, _auth: None = Depends(require_auth)) -> JSONResponse:
    try:
        service.update_alert_rule(rule_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True})


@app.delete("/api/alert-rules/{rule_id}")
async def delete_alert_rule(rule_id: int, _auth: None = Depends(require_auth)) -> JSONResponse:
    service.delete_alert_rule(rule_id)
    return JSONResponse({"ok": True})
