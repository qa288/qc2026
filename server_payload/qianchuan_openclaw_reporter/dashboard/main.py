#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

try:
    import redis
except Exception:  # noqa: BLE001
    redis = None

from fastapi import FastAPI, HTTPException, UploadFile, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from report_qianchuan import (  # noqa: E402
    ACCESS_TOKEN_URL,
    CUSTOMER_CENTER_URL,
    PLAN_DELIVERY_TYPE_CUBIC,
    PLAN_DELIVERY_TYPE_GLOBAL,
    PLAN_MATERIAL_TYPES,
    PLAN_PRODUCT_FIELDS,
    PLAN_SOURCE_UNI_PROMOTION,
    REFRESH_URL,
    AccountSummary,
    ApiError,
    OceanEngineClient,
    PlanSummary,
    build_window,
    dump_json,
    fetch_account_bundle,
    fetch_plan_bundle,
    format_plan_status_text,
    get_json_with_retries,
    load_runtime_config,
    normalize_account_fund_money,
    normalize_plan_money,
    plan_material_fields_for_type,
    plan_delivery_status_label,
    plan_marketing_goal_label,
    plan_opt_status_label,
    post_json,
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
from dashboard.video_probe import (  # noqa: E402
    VideoProbeError,
    format_video_probe_summary,
    probe_video_file,
    validate_video_probe_for_upload,
)


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
EXTENDED_RETENTION_DAYS = settings.extended_retention_days
DASHBOARD_USERNAME = settings.dashboard_username
DASHBOARD_PASSWORD = settings.dashboard_password
SESSION_SECRET = settings.session_secret
RANGE_CACHE_SECONDS = settings.range_cache_seconds
COMMENT_SYNC_SUCCESS_TTL_SECONDS = settings.comment_sync_success_ttl_seconds
COMMENT_SYNC_ERROR_RETRY_SECONDS = settings.comment_sync_error_retry_seconds
BACKFILL_QUEUE_DEBOUNCE_SECONDS = settings.backfill_queue_debounce_seconds
COMMENT_SYNC_QUEUE_DEBOUNCE_SECONDS = max(30, min(COMMENT_SYNC_SUCCESS_TTL_SECONDS, 120))
PERFORMANCE_RANGES = {"day", "yesterday", "week", "month", "custom"}
RANGE_LABEL_MAP = {
    "day": "今日",
    "yesterday": "昨日",
    "week": "近7天",
    "month": "近30天",
    "custom": "指定日期范围",
}
DETAIL_SYNC_INTERVAL_MINUTES = settings.detail_sync_interval_minutes
HISTORY_BACKFILL_DAYS = settings.history_backfill_days
EXTENDED_HISTORY_REFRESH_DAYS = settings.extended_history_refresh_days
ENABLE_IN_PROCESS_SCHEDULER = settings.enable_in_process_scheduler
ROLE_ADMIN = "admin"
ROLE_SUPERVISOR = "supervisor"
ROLE_OPERATOR = "operator"
DISPLAY_SCOPE_CURRENT = "current"
DISPLAY_SCOPE_ALL = "all"
PUBLIC_SORT_FIELDS = {"stat_cost", "pay_amount", "order_count", "roi"}
EMPLOYEE_KEYWORD_SCOPES = {"all", "account", "plan", "product", "material"}
EMPLOYEE_BINDING_TYPES = {"account", "plan", "product", "material"}
COMMENT_TYPE_LABELS = {
    "TEXT_COMMENT": "文字评论",
    "IMAGE_COMMENT": "图片评论",
    "IMAGE_TEXT_COMMENT": "图文评论",
}
COMMENT_HIDE_STATUS_LABELS = {
    "HIDE": "已隐藏",
    "NOT_HIDE": "未隐藏",
}
COMMENT_LEVEL_LABELS = {
    "LEVEL_ONE": "一级评论",
    "LEVEL_TWO": "二级评论",
}
COMMENT_REPLY_MAX_LENGTH = 100
COMMENT_INCREMENTAL_HOT_DAYS = 2
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
MATERIAL_PREVIEW_REFRESH_CACHE_SECONDS = 600
PREVIEW_VIDEO_RESOLVE_CACHE_SECONDS = 300
LATEST_SNAPSHOT_CACHE_SECONDS = max(RANGE_CACHE_SECONDS, 300)
LATEST_SNAPSHOT_STALE_SECONDS = max(LATEST_SNAPSHOT_CACHE_SECONDS * 3, 900)
AUTH_AUDIT_STALE_HOURS = 12
FULL_REFRESH_STATUS_CACHE_KEY = "dashboard:full-refresh:status"
FULL_REFRESH_STATUS_TTL_SECONDS = 86400
FULL_REFRESH_STAGE_SEQUENCE = ("summary", "performance", "detail_sync", "detail_history")
FULL_REFRESH_STAGE_LABELS = {
    "summary": "今日汇总",
    "performance": "历史表现",
    "detail_sync": "今日明细",
    "detail_history": "历史明细",
}
INIT_DB_LOCK_NAMESPACE = 20260330
INIT_DB_LOCK_KEY = 1
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


def build_performance_cache_key(
    range_key: str,
    start_date: str = "",
    end_date: str = "",
    customer_center_id: str = "",
) -> str:
    normalized = str(range_key or "day").strip().lower()
    prefix = f"{str(customer_center_id or '').strip()}:" if str(customer_center_id or "").strip() else ""
    if normalized == "custom":
        return f"{prefix}custom:{str(start_date or '').strip()}:{str(end_date or '').strip()}"
    return f"{prefix}{normalized}"


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
    customer_center_id: str = "",
) -> str:
    prefix = f"{str(customer_center_id or '').strip()}:" if str(customer_center_id or "").strip() else ""
    if str(snapshot_time or "").strip():
        return f"{prefix}snapshot:{str(snapshot_time).strip()}:{build_scope_cache_key(allowed_advertiser_ids)}"
    return (
        f"{build_performance_cache_key(range_key, start_date, end_date, customer_center_id)}:"
        f"{build_scope_cache_key(allowed_advertiser_ids)}"
    )


def build_comment_cache_key(
    range_key: str,
    start_date: str = "",
    end_date: str = "",
    advertiser_id: int | None = None,
    allowed_advertiser_ids: set[int] | None = None,
    customer_center_id: str = "",
) -> str:
    return (
        f"{build_performance_cache_key(range_key, start_date, end_date, customer_center_id)}:"
        f"{build_scope_cache_key(allowed_advertiser_ids)}:"
        f"{int(advertiser_id or 0)}"
    )


def build_latest_snapshot_cache_key(
    allowed_advertiser_ids: set[int] | None = None,
    display_scope: str = DISPLAY_SCOPE_CURRENT,
    customer_center_id: str = "",
) -> str:
    return (
        f"latest:{str(display_scope or DISPLAY_SCOPE_CURRENT).strip().lower()}:"
        f"{str(customer_center_id or '').strip()}:{build_scope_cache_key(allowed_advertiser_ids)}"
    )


def build_dashboard_overview_cache_key(
    allowed_advertiser_ids: set[int] | None = None,
    display_scope: str = DISPLAY_SCOPE_CURRENT,
    customer_center_id: str = "",
    role: str = "",
    user_id: int = 0,
    version: str = "1",
) -> str:
    scope_digest = hashlib.sha1(build_scope_cache_key(allowed_advertiser_ids).encode("utf-8")).hexdigest()[:16]
    return (
        f"dashboard-overview:v{str(version or '1').strip()}:"
        f"{str(display_scope or DISPLAY_SCOPE_CURRENT).strip().lower()}:"
        f"{str(customer_center_id or '').strip()}:"
        f"{str(role or '').strip().lower()}:{int(user_id or 0)}:{scope_digest}"
    )


class DashboardService:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._sync_lock = asyncio.Lock()
        self._detail_sync_lock = asyncio.Lock()
        self._db_init_thread_lock = threading.Lock()
        self._db_init_pid: int | None = None
        self._templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
        self._performance_cache: dict[str, dict[str, Any]] = {}
        self._material_cache: dict[str, dict[str, Any]] = {}
        self._material_preview_refresh_cache: dict[str, dict[str, Any]] = {}
        self._preview_video_resolve_cache: dict[str, dict[str, Any]] = {}
        self._comment_cache: dict[str, dict[str, Any]] = {}
        self._latest_snapshot_cache: dict[str, dict[str, Any]] = {}
        self._latest_snapshot_refreshing: set[str] = set()
        self._latest_snapshot_cache_lock = threading.Lock()
        self._full_refresh_status_local: dict[str, Any] = {}
        self._redis_client: Any | None = None
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
        self.balance_access = BalanceAccess(self._json_text, normalize_account_fund_money, self._current_customer_center_id)
        self.history_access = HistoryAccess(self._current_customer_center_id)
        self.performance_access = PerformanceAccess(
            self.db,
            self._rankings_bundle,
            self._scoped_summary,
            self._decorate_plan_item,
            self._apply_employee_attribution,
            self._current_customer_center_id,
            self._snapshot_account_balances,
            self._snapshot_shared_wallets,
            self._snapshot_wallet_relations,
        )
        self.snapshot_access = SnapshotAccess(
            self.db,
            self._latest_summary_meta,
            self._latest_extended_sync_run,
            self._current_customer_center_id,
            self._decorate_plan_item,
            plan_marketing_goal_label,
            format_plan_status_text,
        )
        self.catalog_access = CatalogAccess(
            self.db,
            self._latest_summary_meta,
            self._latest_extended_sync_run,
            self._current_customer_center_id,
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
            self._current_customer_center_id,
            self._normalize_match_text,
            sanitize_material_title,
        )

    @property
    def templates(self) -> Jinja2Templates:
        return self._templates

    def _redis(self) -> Any | None:
        redis_url = str(settings.redis_url or "").strip()
        if not redis_url or redis is None:
            return None
        if self._redis_client is None:
            self._redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        return self._redis_client

    def _shared_cache_version(self, namespace: str) -> str:
        client = self._redis()
        if client is None:
            return "1"
        version_key = f"dashboard:cache-version:{str(namespace or 'default').strip()}"
        try:
            value = str(client.get(version_key) or "").strip()
            if value:
                return value
            client.set(version_key, "1")
            return "1"
        except Exception:  # noqa: BLE001
            return "1"

    def _bump_shared_cache_version(self, namespace: str) -> None:
        client = self._redis()
        if client is None:
            return
        version_key = f"dashboard:cache-version:{str(namespace or 'default').strip()}"
        try:
            client.incr(version_key)
        except Exception:  # noqa: BLE001
            pass

    def _shared_json_cache_get(self, key: str) -> dict[str, Any] | list[Any] | None:
        client = self._redis()
        if client is None:
            return None
        try:
            raw = client.get(key)
        except Exception:  # noqa: BLE001
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001
            return None
        if isinstance(payload, (dict, list)):
            return payload
        return None

    def _shared_json_cache_set(self, key: str, payload: dict[str, Any] | list[Any], ttl_seconds: int) -> None:
        client = self._redis()
        if client is None:
            return
        try:
            client.setex(
                key,
                max(int(ttl_seconds or RANGE_CACHE_SECONDS), 1),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            )
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _runtime_lock_key(lock_name: str) -> str:
        return f"dashboard:runtime-lock:{str(lock_name or '').strip()}"

    def runtime_lock_active(self, lock_name: str) -> bool:
        client = self._redis()
        if client is None:
            return False
        try:
            return bool(client.exists(self._runtime_lock_key(lock_name)))
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _default_full_refresh_status() -> dict[str, Any]:
        return {
            "task_id": "",
            "status": "idle",
            "stage": "",
            "stage_label": "",
            "message": "",
            "queued_at": "",
            "started_at": "",
            "updated_at": "",
            "finished_at": "",
            "progress": {
                "completed_steps": 0,
                "total_steps": len(FULL_REFRESH_STAGE_SEQUENCE),
                "stage_completed_steps": 0,
                "stage_total_steps": 0,
            },
            "stages": {},
            "result": {},
        }

    def _normalize_full_refresh_status(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        baseline = self._default_full_refresh_status()
        if not isinstance(payload, dict):
            return baseline
        normalized = dict(baseline)
        normalized.update(
            {
                "task_id": str(payload.get("task_id") or "").strip(),
                "status": str(payload.get("status") or "idle").strip().lower() or "idle",
                "stage": str(payload.get("stage") or "").strip(),
                "stage_label": str(payload.get("stage_label") or "").strip(),
                "message": str(payload.get("message") or "").strip(),
                "queued_at": str(payload.get("queued_at") or "").strip(),
                "started_at": str(payload.get("started_at") or "").strip(),
                "updated_at": str(payload.get("updated_at") or "").strip(),
                "finished_at": str(payload.get("finished_at") or "").strip(),
                "stages": copy.deepcopy(payload.get("stages") or {}),
                "result": copy.deepcopy(payload.get("result") or {}),
            }
        )
        if normalized["stage"] and not normalized["stage_label"]:
            normalized["stage_label"] = FULL_REFRESH_STAGE_LABELS.get(normalized["stage"], normalized["stage"])
        progress_payload = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
        total_steps = max(
            int(progress_payload.get("total_steps", len(FULL_REFRESH_STAGE_SEQUENCE)) or len(FULL_REFRESH_STAGE_SEQUENCE)),
            1,
        )
        completed_steps = max(min(int(progress_payload.get("completed_steps", 0) or 0), total_steps), 0)
        stage_total_steps = max(int(progress_payload.get("stage_total_steps", 0) or 0), 0)
        stage_completed_steps = max(min(int(progress_payload.get("stage_completed_steps", 0) or 0), stage_total_steps), 0)
        normalized["progress"] = {
            "completed_steps": completed_steps,
            "total_steps": total_steps,
            "stage_completed_steps": stage_completed_steps,
            "stage_total_steps": stage_total_steps,
        }
        return normalized

    def full_refresh_status(self) -> dict[str, Any]:
        client = self._redis()
        payload: dict[str, Any] | None = None
        if client is None:
            payload = copy.deepcopy(self._full_refresh_status_local) if self._full_refresh_status_local else None
        else:
            cached = self._shared_json_cache_get(FULL_REFRESH_STATUS_CACHE_KEY)
            payload = cached if isinstance(cached, dict) else None
        normalized = self._normalize_full_refresh_status(payload)
        if normalized["status"] in {"queued", "running"} and not self.runtime_lock_active("full-refresh"):
            if not normalized["finished_at"]:
                normalized["finished_at"] = now_text()
            if normalized["status"] == "running":
                normalized["status"] = "unknown"
                if not normalized["message"]:
                    normalized["message"] = "任务锁已释放，但未写入完成状态。"
        return normalized

    def _set_full_refresh_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_full_refresh_status(payload)
        client = self._redis()
        if client is None:
            self._full_refresh_status_local = copy.deepcopy(normalized)
            return normalized
        self._shared_json_cache_set(FULL_REFRESH_STATUS_CACHE_KEY, normalized, FULL_REFRESH_STATUS_TTL_SECONDS)
        return normalized

    def update_full_refresh_status(self, **fields: Any) -> dict[str, Any]:
        current = self.full_refresh_status()
        merged = dict(current)
        for key, value in fields.items():
            if key == "stages" and isinstance(value, dict):
                next_stages = dict(merged.get("stages") or {})
                for stage_key, stage_payload in value.items():
                    next_stages[str(stage_key)] = copy.deepcopy(stage_payload)
                merged["stages"] = next_stages
                continue
            if key in {"progress", "result"} and isinstance(value, dict):
                merged[key] = copy.deepcopy(value)
                continue
            merged[key] = value
        return self._set_full_refresh_status(merged)

    def mark_full_refresh_queued(self, task_id: str) -> dict[str, Any]:
        queued_at = now_text()
        return self._set_full_refresh_status(
            {
                "task_id": str(task_id or "").strip(),
                "status": "queued",
                "stage": "",
                "stage_label": "",
                "message": "任务已进入队列，等待开始执行。",
                "queued_at": queued_at,
                "started_at": "",
                "updated_at": queued_at,
                "finished_at": "",
                "progress": {
                    "completed_steps": 0,
                    "total_steps": len(FULL_REFRESH_STAGE_SEQUENCE),
                    "stage_completed_steps": 0,
                    "stage_total_steps": 0,
                },
                "stages": {},
                "result": {},
            }
        )

    @staticmethod
    def _versioned_cache_key(version: str, raw_key: str) -> str:
        return f"v{str(version or '1').strip()}:{str(raw_key or '').strip()}"

    @staticmethod
    def _shared_payload_cache_storage_key(namespace: str, raw_key: str, version: str) -> str:
        digest = hashlib.sha1(str(raw_key or "").encode("utf-8")).hexdigest()[:20]
        return f"dashboard:payload:{str(namespace or 'default').strip()}:v{str(version or '1').strip()}:{digest}"

    @staticmethod
    def _local_dict_cache_get(
        cache_store: dict[str, dict[str, Any]],
        cache_key: str,
        ttl_seconds: int,
    ) -> dict[str, Any] | None:
        cached = cache_store.get(cache_key)
        if not cached:
            return None
        cached_at = float(cached.get("_cached_at", 0.0) or 0.0)
        if time.time() - cached_at >= max(int(ttl_seconds or 0), 1):
            return None
        payload = cached.get("payload")
        return copy.deepcopy(payload) if isinstance(payload, dict) else None

    @staticmethod
    def _local_dict_cache_set(
        cache_store: dict[str, dict[str, Any]],
        cache_key: str,
        payload: dict[str, Any],
    ) -> None:
        cache_store[cache_key] = {
            "_cached_at": time.time(),
            "payload": copy.deepcopy(payload),
        }

    def _shared_dict_cache_get(self, namespace: str, raw_key: str, version: str) -> dict[str, Any] | None:
        payload = self._shared_json_cache_get(self._shared_payload_cache_storage_key(namespace, raw_key, version))
        return copy.deepcopy(payload) if isinstance(payload, dict) else None

    def _shared_dict_cache_set(self, namespace: str, raw_key: str, version: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        self._shared_json_cache_set(
            self._shared_payload_cache_storage_key(namespace, raw_key, version),
            payload,
            ttl_seconds,
        )

    def _invalidate_cache_namespaces(self, *namespaces: str) -> None:
        for namespace in namespaces:
            self._bump_shared_cache_version(namespace)

    @contextmanager
    def _distributed_runtime_lock(
        self,
        lock_name: str,
        *,
        timeout_seconds: int,
        blocking_timeout_seconds: int = 0,
    ) -> Any:
        client = self._redis()
        if client is None:
            yield True
            return
        lock = client.lock(
            self._runtime_lock_key(lock_name),
            timeout=max(int(timeout_seconds or 0), 1),
            blocking_timeout=max(int(blocking_timeout_seconds or 0), 0),
        )
        try:
            acquired = bool(lock.acquire(blocking=blocking_timeout_seconds > 0))
        except Exception:  # noqa: BLE001
            acquired = False
        if not acquired:
            yield False
            return
        try:
            yield True
        finally:
            try:
                lock.release()
            except Exception:  # noqa: BLE001
                pass

    def _range_span_days(self, start_dt: datetime, end_dt: datetime) -> int:
        return max((end_dt.date() - start_dt.date()).days + 1, 1)

    @staticmethod
    def _history_backfill_kind(task_name: str) -> str:
        return "detail" if str(task_name or "").strip() == "dashboard.detail_backfill" else "performance"

    @staticmethod
    def _db_optional_timestamp_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return value

    def _record_history_backfill_job_locked(
        self,
        conn: Any,
        *,
        job_key: str,
        kind: str,
        task_name: str,
        range_start: str,
        range_end: str,
        days: int,
        requested_missing_days: int,
        status: str,
        task_id: str = "",
        message: str = "",
        result_json: Any = "{}",
        queued_at: Any = "",
        started_at: Any = "",
        finished_at: Any = "",
    ) -> None:
        updated_at = now_text()
        conn.execute(
            """
            INSERT INTO history_backfill_jobs (
                job_key, kind, task_name, range_start, range_end, days, requested_missing_days,
                status, task_id, message, result_json, queued_at, started_at, finished_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (job_key) DO UPDATE SET
                kind = excluded.kind,
                task_name = excluded.task_name,
                range_start = excluded.range_start,
                range_end = excluded.range_end,
                days = excluded.days,
                requested_missing_days = excluded.requested_missing_days,
                status = excluded.status,
                task_id = excluded.task_id,
                message = excluded.message,
                result_json = excluded.result_json,
                queued_at = excluded.queued_at,
                started_at = excluded.started_at,
                finished_at = excluded.finished_at,
                updated_at = excluded.updated_at
            """,
            (
                job_key,
                kind,
                task_name,
                range_start,
                range_end,
                max(int(days or 0), 0),
                max(int(requested_missing_days or 0), 0),
                status,
                task_id,
                message,
                result_json,
                self._db_optional_timestamp_value(queued_at),
                self._db_optional_timestamp_value(started_at),
                self._db_optional_timestamp_value(finished_at),
                updated_at,
            ),
        )

    def mark_history_backfill_job_started(self, job_key: str, task_id: str = "") -> None:
        normalized_job_key = str(job_key or "").strip()
        if not normalized_job_key:
            return
        with self.db() as conn:
            row = conn.execute(
                "SELECT kind, task_name, range_start, range_end, days, requested_missing_days FROM history_backfill_jobs WHERE job_key = ? LIMIT 1",
                (normalized_job_key,),
            ).fetchone()
            if not row:
                return
            started_at = now_text()
            self._record_history_backfill_job_locked(
                conn,
                job_key=normalized_job_key,
                kind=str(row["kind"] or "").strip(),
                task_name=str(row["task_name"] or "").strip(),
                range_start=str(row["range_start"] or "").strip(),
                range_end=str(row["range_end"] or "").strip(),
                days=int(row["days"] or 0),
                requested_missing_days=int(row["requested_missing_days"] or 0),
                status="running",
                task_id=str(task_id or row["task_id"] or "").strip(),
                message="",
                result_json="{}",
                queued_at="",
                started_at=started_at,
                finished_at="",
            )

    def mark_history_backfill_job_finished(
        self,
        job_key: str,
        status: str,
        *,
        message: str = "",
        result: dict[str, Any] | None = None,
    ) -> None:
        normalized_job_key = str(job_key or "").strip()
        if not normalized_job_key:
            return
        with self.db() as conn:
            row = conn.execute(
                """
                SELECT kind, task_name, range_start, range_end, days, requested_missing_days, task_id, queued_at, started_at
                FROM history_backfill_jobs
                WHERE job_key = ?
                LIMIT 1
                """,
                (normalized_job_key,),
            ).fetchone()
            if not row:
                return
            self._record_history_backfill_job_locked(
                conn,
                job_key=normalized_job_key,
                kind=str(row["kind"] or "").strip(),
                task_name=str(row["task_name"] or "").strip(),
                range_start=str(row["range_start"] or "").strip(),
                range_end=str(row["range_end"] or "").strip(),
                days=int(row["days"] or 0),
                requested_missing_days=int(row["requested_missing_days"] or 0),
                status=str(status or "success").strip() or "success",
                task_id=str(row["task_id"] or "").strip(),
                message=str(message or "").strip(),
                result_json=self._json_text(result or {}),
                queued_at=str(row["queued_at"] or "").strip(),
                started_at=str(row["started_at"] or "").strip(),
                finished_at=now_text(),
            )

    def _enqueue_backfill_task(
        self,
        task_name: str,
        days: int,
        dedupe_key: str,
        *,
        range_start: str = "",
        range_end: str = "",
        requested_missing_days: int = 0,
    ) -> bool:
        now_ts = time.time()
        client = self._redis()
        normalized_task_name = str(task_name or "").strip()
        normalized_job_key = str(dedupe_key or "").strip()
        normalized_kind = self._history_backfill_kind(normalized_task_name)
        if client is not None:
            redis_key = f"dashboard:backfill-dedupe:{str(dedupe_key or '').strip()}"
            try:
                acquired = bool(
                    client.set(
                        redis_key,
                        str(now_ts),
                        nx=True,
                        ex=max(int(BACKFILL_QUEUE_DEBOUNCE_SECONDS or 0), 1),
                    )
                )
            except Exception:  # noqa: BLE001
                acquired = None
            if acquired is True:
                from dashboard.celery_app import celery_app

                task = celery_app.send_task(normalized_task_name, args=[max(int(days or 1), 1), normalized_job_key])
                with self.db() as conn:
                    self._record_history_backfill_job_locked(
                        conn,
                        job_key=normalized_job_key,
                        kind=normalized_kind,
                        task_name=normalized_task_name,
                        range_start=range_start,
                        range_end=range_end,
                        days=max(int(days or 1), 1),
                        requested_missing_days=max(int(requested_missing_days or 0), 0),
                        status="queued",
                        task_id=str(getattr(task, "id", "") or "").strip(),
                        message="",
                        result_json="{}",
                        queued_at=now_text(),
                        started_at="",
                        finished_at="",
                    )
                return True
            if acquired is False:
                return True
        last_ts = float(self._backfill_queue_marks.get(dedupe_key, 0.0) or 0.0)
        if now_ts - last_ts < BACKFILL_QUEUE_DEBOUNCE_SECONDS:
            return True
        from dashboard.celery_app import celery_app

        task = celery_app.send_task(normalized_task_name, args=[max(int(days or 1), 1), normalized_job_key])
        with self.db() as conn:
            self._record_history_backfill_job_locked(
                conn,
                job_key=normalized_job_key,
                kind=normalized_kind,
                task_name=normalized_task_name,
                range_start=range_start,
                range_end=range_end,
                days=max(int(days or 1), 1),
                requested_missing_days=max(int(requested_missing_days or 0), 0),
                status="queued",
                task_id=str(getattr(task, "id", "") or "").strip(),
                message="",
                result_json="{}",
                queued_at=now_text(),
                started_at="",
                finished_at="",
            )
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
            return self._enqueue_backfill_task(
                "dashboard.performance_backfill",
                days,
                f"performance:{range_key}",
                range_start=start_dt.strftime("%Y-%m-%d"),
                range_end=end_dt.strftime("%Y-%m-%d"),
                requested_missing_days=missing_days,
            )
        if kind == "detail":
            return self._enqueue_backfill_task(
                "dashboard.detail_backfill",
                days,
                f"detail:{range_key}",
                range_start=start_dt.strftime("%Y-%m-%d"),
                range_end=end_dt.strftime("%Y-%m-%d"),
                requested_missing_days=missing_days,
            )
        return False

    @staticmethod
    def _normalize_allowed_advertiser_ids(
        allowed_advertiser_ids: set[int] | list[int] | tuple[int, ...] | None,
    ) -> set[int] | None:
        if allowed_advertiser_ids is None:
            return None
        return {int(item) for item in allowed_advertiser_ids if int(item or 0)}

    def _comment_sync_dedupe_key(
        self,
        start_date: str,
        end_date: str,
        advertiser_id: int = 0,
        allowed_advertiser_ids: set[int] | list[int] | tuple[int, ...] | None = None,
    ) -> str:
        normalized_allowed = self._normalize_allowed_advertiser_ids(allowed_advertiser_ids)
        scope_digest = hashlib.sha1(build_scope_cache_key(normalized_allowed).encode("utf-8")).hexdigest()[:16]
        return (
            f"comment-sync:{self._current_customer_center_id()}:{str(start_date or '').strip()}:"
            f"{str(end_date or '').strip()}:{int(advertiser_id or 0)}:{scope_digest}"
        )

    def _queue_comment_sync_if_needed(
        self,
        start_date: str,
        end_date: str,
        advertiser_id: int = 0,
        allowed_advertiser_ids: set[int] | list[int] | tuple[int, ...] | None = None,
        force_refresh: bool = False,
    ) -> bool:
        normalized_allowed = self._normalize_allowed_advertiser_ids(allowed_advertiser_ids)
        dedupe_key = self._comment_sync_dedupe_key(
            start_date,
            end_date,
            advertiser_id=advertiser_id,
            allowed_advertiser_ids=normalized_allowed,
        )
        now_ts = time.time()
        last_ts = float(self._backfill_queue_marks.get(dedupe_key, 0.0) or 0.0)
        if now_ts - last_ts < COMMENT_SYNC_QUEUE_DEBOUNCE_SECONDS:
            return False
        from dashboard.celery_app import celery_app

        try:
            celery_app.send_task(
                "dashboard.comment_sync_recent",
                kwargs={
                    "start_date": str(start_date or "").strip(),
                    "end_date": str(end_date or "").strip(),
                    "advertiser_id": int(advertiser_id or 0),
                    "allowed_advertiser_ids": (
                        sorted(int(item) for item in normalized_allowed)
                        if normalized_allowed is not None
                        else None
                    ),
                    "force_refresh": bool(force_refresh),
                },
            )
        except Exception:  # noqa: BLE001
            return False
        self._backfill_queue_marks[dedupe_key] = now_ts
        return True

    def queue_manual_history_backfill(self, kind: str, days: int = 30) -> dict[str, Any]:
        normalized_kind = "detail" if str(kind or "").strip() == "detail" else "performance"
        normalized_days = max(int(days or 30), 1)
        tz = ZoneInfo(self.read_config()["timezone"])
        end_dt = datetime.now(tz).replace(hour=23, minute=59, second=59, microsecond=0)
        start_day = end_dt.date() - timedelta(days=max(normalized_days - 1, 0))
        start_dt = datetime(start_day.year, start_day.month, start_day.day, 0, 0, 0, tzinfo=tz)
        task_name = "dashboard.detail_backfill" if normalized_kind == "detail" else "dashboard.performance_backfill"
        job_key = (
            f"manual:{normalized_kind}:{start_dt.strftime('%Y-%m-%d')}:"
            f"{end_dt.strftime('%Y-%m-%d')}:{int(time.time())}"
        )
        from dashboard.celery_app import celery_app

        task = celery_app.send_task(task_name, args=[normalized_days, job_key])
        with self.db() as conn:
            self._record_history_backfill_job_locked(
                conn,
                job_key=job_key,
                kind=normalized_kind,
                task_name=task_name,
                range_start=start_dt.strftime("%Y-%m-%d"),
                range_end=end_dt.strftime("%Y-%m-%d"),
                days=normalized_days,
                requested_missing_days=0,
                status="queued",
                task_id=str(getattr(task, "id", "") or "").strip(),
                message="manual trigger",
                result_json="{}",
                queued_at=now_text(),
                started_at="",
                finished_at="",
            )
        return {
            "ok": True,
            "queued": True,
            "task_id": str(getattr(task, "id", "") or "").strip(),
            "task_name": task_name,
            "job_key": job_key,
            "days": normalized_days,
            "range_start": start_dt.strftime("%Y-%m-%d"),
            "range_end": end_dt.strftime("%Y-%m-%d"),
        }

    def init_db(self) -> None:
        with self.db() as conn:
            self._acquire_init_db_lock(conn)
            apply_migrations(
                conn,
                context={
                    "base_customer_center_id": str(
                        self._base_runtime_config().get("customer_center_id") or ""
                    ).strip(),
                    "timezone": TIMEZONE,
                },
            )
            self.alert_access.ensure_notification_settings(conn)

    def init_db_once(self) -> None:
        current_pid = os.getpid()
        if self._db_init_pid == current_pid:
            return
        with self._db_init_thread_lock:
            if self._db_init_pid == current_pid:
                return
            self.init_db()
            self._db_init_pid = current_pid

    @staticmethod
    def _acquire_init_db_lock(conn: Any) -> None:
        if getattr(conn, "backend", "") != "postgres":
            return
        conn.execute(
            "SELECT pg_advisory_xact_lock(?, ?)",
            (INIT_DB_LOCK_NAMESPACE, INIT_DB_LOCK_KEY),
        )

    def _runtime_config_override_row_locked(self, conn: Any) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT id, customer_center_id, refresh_token, updated_at
            FROM runtime_config_overrides
            WHERE id = 1
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

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

    @staticmethod
    def _merge_runtime_config_override(
        base_config: dict[str, Any],
        override_row: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(base_config)
        if not override_row:
            return merged
        customer_center_id = str(override_row.get("customer_center_id") or "").strip()
        refresh_token = str(override_row.get("refresh_token") or "").strip()
        if customer_center_id:
            merged["customer_center_id"] = customer_center_id
        if refresh_token:
            merged["refresh_token"] = refresh_token
        return merged

    def _base_runtime_config(self) -> dict[str, Any]:
        return load_runtime_config(CONFIG_PATH)

    def _runtime_config_override_row(self) -> dict[str, Any] | None:
        try:
            with self.db() as conn:
                row = self._runtime_config_override_row_locked(conn)
        except Exception:
            return None
        return row

    def _current_customer_center_id(self) -> str:
        return str(self.read_config().get("customer_center_id") or "").strip()

    @staticmethod
    def _normalize_display_scope(display_scope: str) -> str:
        return DISPLAY_SCOPE_ALL if str(display_scope or "").strip().lower() == DISPLAY_SCOPE_ALL else DISPLAY_SCOPE_CURRENT

    def _display_scope_uses_all_customer_centers(self, display_scope: str) -> bool:
        return self._normalize_display_scope(display_scope) == DISPLAY_SCOPE_ALL

    @staticmethod
    def _snapshot_pairs_from_rows(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
        return {
            (
                str(row.get("customer_center_id") or "").strip(),
                str(row.get("snapshot_time") or "").strip(),
            )
            for row in rows
            if str(row.get("customer_center_id") or "").strip() and str(row.get("snapshot_time") or "").strip()
        }

    @staticmethod
    def _latest_snapshot_pairs_by_customer_center(selected_pairs: set[tuple[str, str]]) -> set[tuple[str, str]]:
        latest_by_customer_center: dict[str, str] = {}
        for customer_center_id, snapshot_time in selected_pairs:
            current_snapshot = latest_by_customer_center.get(customer_center_id, "")
            if snapshot_time > current_snapshot:
                latest_by_customer_center[customer_center_id] = snapshot_time
        return {
            (customer_center_id, snapshot_time)
            for customer_center_id, snapshot_time in latest_by_customer_center.items()
            if customer_center_id and snapshot_time
        }

    @staticmethod
    def _filter_rows_for_snapshot_pairs(
        rows: list[dict[str, Any]],
        selected_pairs: set[tuple[str, str]],
    ) -> list[dict[str, Any]]:
        if not rows or not selected_pairs:
            return []
        return [
            row
            for row in rows
            if (
                str(row.get("customer_center_id") or "").strip(),
                str(row.get("snapshot_time") or "").strip(),
            )
            in selected_pairs
        ]

    def _latest_extended_sync_all_customer_centers(self) -> dict[str, Any] | None:
        with self.db() as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM extended_sync_runs
                    WHERE COALESCE(customer_center_id, '') <> ''
                    ORDER BY snapshot_time DESC, customer_center_id ASC
                    """
                ).fetchall()
            ]
        latest_rows = self._latest_rows_by_customer_center(rows)
        if not latest_rows:
            return None
        latest_snapshot_time = max(str(row.get("snapshot_time") or "") for row in latest_rows)
        return {
            "snapshot_time": latest_snapshot_time,
            "status": "partial" if any(str(row.get("status") or "") != "ok" for row in latest_rows) else "ok",
            "plan_count": sum(int(row.get("plan_count") or 0) for row in latest_rows),
            "detail_count": sum(int(row.get("detail_count") or 0) for row in latest_rows),
            "product_row_count": sum(int(row.get("product_row_count") or 0) for row in latest_rows),
            "material_row_count": sum(int(row.get("material_row_count") or 0) for row in latest_rows),
            "original_video_row_count": sum(int(row.get("original_video_row_count") or 0) for row in latest_rows),
            "error_count": sum(int(row.get("error_count") or 0) for row in latest_rows),
            "customer_center_count": len(latest_rows),
        }

    def _summary_history_all_customer_centers(self, limit: int = 144) -> list[dict[str, Any]]:
        with self.db() as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT snapshot_time, customer_center_id, stat_cost, pay_amount, order_count
                    FROM summary_snapshots
                    WHERE COALESCE(customer_center_id, '') <> ''
                    ORDER BY snapshot_time DESC, customer_center_id ASC
                    """
                ).fetchall()
            ]
        latest_rows = self._latest_rows_by_customer_center_day(rows)
        grouped: dict[str, dict[str, Any]] = {}
        for row in latest_rows:
            day_key = str(row.get("snapshot_time") or "")[:10]
            if not day_key:
                continue
            bucket = grouped.setdefault(
                day_key,
                {
                    "snapshot_time": "",
                    "stat_cost": 0.0,
                    "pay_amount": 0.0,
                    "order_count": 0,
                },
            )
            snapshot_time = str(row.get("snapshot_time") or "")
            if snapshot_time > str(bucket.get("snapshot_time") or ""):
                bucket["snapshot_time"] = snapshot_time
            bucket["stat_cost"] = round(float(bucket.get("stat_cost", 0.0) or 0.0) + float(row.get("stat_cost", 0.0) or 0.0), 2)
            bucket["pay_amount"] = round(float(bucket.get("pay_amount", 0.0) or 0.0) + float(row.get("pay_amount", 0.0) or 0.0), 2)
            bucket["order_count"] = int(bucket.get("order_count", 0) or 0) + int(row.get("order_count") or 0)
        items = []
        for day_key in sorted(grouped):
            item = dict(grouped[day_key])
            stat_cost = round(float(item.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(item.get("pay_amount", 0.0) or 0.0), 2)
            item["roi"] = round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0
            items.append(item)
        return items[-max(int(limit or 0), 0) :] if limit > 0 else items

    def _persist_runtime_config_override(
        self,
        customer_center_id: str,
        refresh_token: str | None = None,
    ) -> dict[str, Any]:
        normalized_customer_center_id = str(customer_center_id or "").strip()
        if not normalized_customer_center_id:
            raise ValueError("customer_center_id 不能为空")
        existing = self._runtime_config_override_row() or {}
        next_refresh_token = str(existing.get("refresh_token") or "").strip()
        if refresh_token is not None:
            next_refresh_token = str(refresh_token).strip()
        updated_at = now_text()
        with self.db() as conn:
            conn.execute(
                """
                INSERT INTO runtime_config_overrides (
                    id, customer_center_id, refresh_token, updated_at
                ) VALUES (1, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    customer_center_id = excluded.customer_center_id,
                    refresh_token = excluded.refresh_token,
                    updated_at = excluded.updated_at
                """,
                (normalized_customer_center_id, next_refresh_token, updated_at),
            )
        return {
            "customer_center_id": normalized_customer_center_id,
            "refresh_token": next_refresh_token,
            "updated_at": updated_at,
        }

    def _exchange_auth_code_payload(self, config: dict[str, Any], auth_code: str) -> dict[str, Any]:
        now = int(time.time())
        response = post_json(
            ACCESS_TOKEN_URL,
            {
                "app_id": config["app_id"],
                "secret": config["app_secret"],
                "grant_type": "auth_code",
                "auth_code": str(auth_code or "").strip(),
            },
        )
        if response.get("code") != 0:
            raise ApiError(f"exchange auth_code failed: {response}")
        data = response["data"]
        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": now + int(data["expires_in"]),
            "refresh_token_expires_in": data.get("refresh_token_expires_in"),
            "updated_at": now,
            "source": "auth_code",
        }

    def _customer_center_preview(
        self,
        config: dict[str, Any],
        access_token: str,
        sample_limit: int = 5,
    ) -> dict[str, Any]:
        response = get_json_with_retries(
            CUSTOMER_CENTER_URL,
            access_token,
            {
                "cc_account_id": config["customer_center_id"],
                "account_source": config["account_source"],
                "page": 1,
                "page_size": 100,
            },
        )
        if response.get("code") != 0:
            raise ApiError(f"list accounts failed: {response}")
        data = response.get("data") or {}
        rows = list(data.get("list") or [])
        page_info = data.get("page_info") or {}
        total_count = int(page_info.get("total_number", len(rows)) or len(rows))
        sample_accounts = [
            {
                "advertiser_id": int(item.get("advertiser_id") or item.get("account_id") or 0),
                "advertiser_name": str(
                    item.get("advertiser_name")
                    or item.get("account_name")
                    or item.get("name")
                    or item.get("advertiser_id")
                    or item.get("account_id")
                    or ""
                ).strip(),
            }
            for item in rows[: max(int(sample_limit or 0), 0)]
            if int(item.get("advertiser_id") or item.get("account_id") or 0)
        ]
        return {
            "account_count": total_count,
            "sample_accounts": sample_accounts,
        }

    def _persist_token_cache_for_config(self, config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized["app_id"] = str(config.get("app_id") or "")
        normalized["customer_center_id"] = str(config.get("customer_center_id") or "")
        dump_json(TOKEN_CACHE_PATH, normalized)
        try:
            os.chmod(TOKEN_CACHE_PATH, 0o600)
        except OSError:
            pass
        if LATEST_TOKEN_PATH != TOKEN_CACHE_PATH:
            dump_json(LATEST_TOKEN_PATH, normalized)
            try:
                os.chmod(LATEST_TOKEN_PATH, 0o600)
            except OSError:
                pass
        self.persist_token_record(normalized)
        return normalized

    def _stored_token_payload_for_config(self, config: dict[str, Any]) -> dict[str, Any] | None:
        return self.token_access.token_payload_for(
            str(config.get("app_id") or ""),
            str(config.get("customer_center_id") or ""),
        )

    def _access_token_from_payload(
        self,
        config: dict[str, Any],
        payload: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        now = int(time.time())
        normalized = dict(payload or {})
        access_token = str(normalized.get("access_token") or "").strip()
        expires_at = int(normalized.get("expires_at") or 0)
        if access_token and expires_at > now + 300:
            normalized["updated_at"] = int(normalized.get("updated_at") or now)
            normalized["source"] = str(normalized.get("source") or "stored_token")
            return access_token, normalized

        refresh_token = str(normalized.get("refresh_token") or config.get("refresh_token") or "").strip()
        if not refresh_token:
            raise ApiError("No refresh token is available for the selected customer_center_id")
        response = post_json(
            REFRESH_URL,
            {
                "app_id": config["app_id"],
                "secret": config["app_secret"],
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        if response.get("code") != 0:
            raise ApiError(f"refresh token failed: {response}")
        data = response["data"]
        refreshed = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": now + int(data["expires_in"]),
            "refresh_token_expires_in": data.get("refresh_token_expires_in"),
            "updated_at": now,
            "source": "refresh_token",
        }
        return str(refreshed["access_token"]), refreshed

    @staticmethod
    def _latest_rows_by_customer_center(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen_customer_centers: set[str] = set()
        for raw_row in rows:
            row = dict(raw_row)
            customer_center_id = str(row.get("customer_center_id") or "").strip()
            if not customer_center_id or customer_center_id in seen_customer_centers:
                continue
            selected.append(row)
            seen_customer_centers.add(customer_center_id)
        return selected

    @staticmethod
    def _latest_rows_by_customer_center_day(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        for raw_row in rows:
            row = dict(raw_row)
            customer_center_id = str(row.get("customer_center_id") or "").strip()
            snapshot_time = str(row.get("snapshot_time") or "").strip()
            day_key = snapshot_time[:10]
            if not customer_center_id or not day_key:
                continue
            dedupe_key = (customer_center_id, day_key)
            if dedupe_key in seen_keys:
                continue
            selected.append(row)
            seen_keys.add(dedupe_key)
        selected.sort(key=lambda item: str(item.get("snapshot_time") or ""))
        return selected

    def list_bound_customer_centers(self) -> list[dict[str, Any]]:
        base_config = self._base_runtime_config()
        current_customer_center_id = self._current_customer_center_id()
        base_customer_center_id = str(base_config.get("customer_center_id") or "").strip()
        override_row = self._runtime_config_override_row() or {}
        override_customer_center_id = str(override_row.get("customer_center_id") or "").strip()
        app_id = str(base_config.get("app_id") or "").strip()

        with self.db() as conn:
            token_rows = (
                [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT customer_center_id, updated_at, source, expires_at
                        FROM oauth_tokens
                        WHERE app_id = ?
                        ORDER BY updated_at DESC, customer_center_id ASC
                        """,
                        (app_id,),
                    ).fetchall()
                ]
                if app_id
                else []
            )
            summary_rows = self._latest_rows_by_customer_center(
                [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT
                            customer_center_id,
                            snapshot_time,
                            account_count,
                            active_account_count,
                            plan_count,
                            active_plan_count,
                            stat_cost,
                            pay_amount,
                            order_count,
                            roi
                        FROM summary_snapshots
                        WHERE COALESCE(customer_center_id, '') <> ''
                        ORDER BY snapshot_time DESC, customer_center_id ASC
                        """
                    ).fetchall()
                ]
            )
            detail_rows = self._latest_rows_by_customer_center(
                [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT
                            customer_center_id,
                            snapshot_time,
                            status,
                            material_row_count,
                            error_count
                        FROM extended_sync_runs
                        WHERE COALESCE(customer_center_id, '') <> ''
                        ORDER BY snapshot_time DESC, customer_center_id ASC
                        """
                    ).fetchall()
                ]
            )

        summary_by_customer_center = {
            str(row.get("customer_center_id") or "").strip(): row for row in summary_rows if str(row.get("customer_center_id") or "").strip()
        }
        detail_by_customer_center = {
            str(row.get("customer_center_id") or "").strip(): row for row in detail_rows if str(row.get("customer_center_id") or "").strip()
        }

        records: dict[str, dict[str, Any]] = {}
        for row in token_rows:
            customer_center_id = str(row.get("customer_center_id") or "").strip()
            if not customer_center_id:
                continue
            records[customer_center_id] = {
                "customer_center_id": customer_center_id,
                "has_saved_token": True,
                "token_updated_at": int(row.get("updated_at") or 0),
                "token_source": str(row.get("source") or "").strip(),
                "token_expires_at": int(row.get("expires_at") or 0),
            }

        items: list[dict[str, Any]] = []
        for customer_center_id, row in records.items():
            summary_row = summary_by_customer_center.get(customer_center_id) or {}
            detail_row = detail_by_customer_center.get(customer_center_id) or {}
            items.append(
                {
                    **row,
                    "is_current": customer_center_id == current_customer_center_id,
                    "is_base_customer_center": customer_center_id == base_customer_center_id,
                    "is_override_customer_center": bool(override_customer_center_id)
                    and customer_center_id == override_customer_center_id,
                    "latest_snapshot_time": str(summary_row.get("snapshot_time") or "").strip(),
                    "latest_detail_snapshot_time": str(detail_row.get("snapshot_time") or "").strip(),
                    "account_count": int(summary_row.get("account_count") or 0),
                    "active_account_count": int(summary_row.get("active_account_count") or 0),
                    "plan_count": int(summary_row.get("plan_count") or 0),
                    "active_plan_count": int(summary_row.get("active_plan_count") or 0),
                    "stat_cost": round(float(summary_row.get("stat_cost", 0.0) or 0.0), 2),
                    "pay_amount": round(float(summary_row.get("pay_amount", 0.0) or 0.0), 2),
                    "order_count": int(summary_row.get("order_count") or 0),
                    "roi": round(float(summary_row.get("roi", 0.0) or 0.0), 2),
                    "detail_status": str(detail_row.get("status") or "").strip(),
                    "detail_material_row_count": int(detail_row.get("material_row_count") or 0),
                    "detail_error_count": int(detail_row.get("error_count") or 0),
                }
            )

        items.sort(
            key=lambda item: (
                0 if bool(item.get("is_current")) else 1,
                0 if bool(item.get("has_saved_token")) else 1,
                -int(item.get("token_updated_at") or 0),
                0 if str(item.get("latest_snapshot_time") or "").strip() else 1,
                str(item.get("customer_center_id") or ""),
            )
        )
        return items

    def ocean_engine_runtime_config(self) -> dict[str, Any]:
        base_config = self._base_runtime_config()
        override_row = self._runtime_config_override_row() or {}
        effective_config = self._merge_runtime_config_override(base_config, override_row)
        token_payload = self.latest_token_payload(masked=True)
        override_customer_center_id = str(override_row.get("customer_center_id") or "").strip()
        override_refresh_token = str(override_row.get("refresh_token") or "").strip()
        return {
            "app_id": str(effective_config.get("app_id") or ""),
            "customer_center_id": str(effective_config.get("customer_center_id") or ""),
            "base_customer_center_id": str(base_config.get("customer_center_id") or ""),
            "override_customer_center_id": override_customer_center_id,
            "has_customer_center_override": bool(override_customer_center_id),
            "has_refresh_token_override": bool(override_refresh_token),
            "account_source": str(effective_config.get("account_source") or ""),
            "timezone": str(effective_config.get("timezone") or ""),
            "token_updated_at": int(token_payload.get("updated_at") or 0),
            "token_source": str(token_payload.get("source") or ""),
            "bound_customer_centers": self.list_bound_customer_centers(),
        }

    @staticmethod
    def _classify_customer_center_auth_error(message: str) -> tuple[str, str]:
        normalized = str(message or "").strip()
        lowered = normalized.lower()
        if "40002" in normalized or "no permission to operate account" in lowered:
            return (
                "permission_denied",
                "千川侧已取消当前应用/主体对该客群中心的操作权限，需要重新授权。",
            )
        if "refresh token failed" in lowered or "40103" in normalized or "已过期" in normalized:
            return (
                "token_invalid",
                "保存的 refresh_token 已失效，需要重新授权。",
            )
        if "no refresh token is available" in lowered:
            return (
                "token_missing",
                "系统内没有该客群中心可用的 refresh_token，需要重新授权。",
            )
        return ("error", normalized or "unknown error")

    @staticmethod
    def _parse_snapshot_time_text(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    def audit_customer_center_authorizations(
        self,
        stale_hours: int = AUTH_AUDIT_STALE_HOURS,
    ) -> dict[str, Any]:
        stale_seconds = max(int(stale_hours or AUTH_AUDIT_STALE_HOURS), 1) * 3600
        with self._distributed_runtime_lock("oauth-audit", timeout_seconds=1800) as acquired:
            if not acquired:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "oauth audit already running",
                    "stale_hours": stale_hours,
                    "customer_center_count": 0,
                    "checked_count": 0,
                    "ok_count": 0,
                    "repaired_count": 0,
                    "error_count": 0,
                    "items": [],
                }

            items: list[dict[str, Any]] = []
            repaired_count = 0
            error_count = 0
            now_dt = datetime.now(ZoneInfo(str(self.read_config().get("timezone") or TIMEZONE)))
            customer_center_ids = self.bound_customer_center_ids()

            for customer_center_id in customer_center_ids:
                latest_snapshot_time = ""
                latest_snapshot_age_hours = 0.0
                with self.db() as conn:
                    latest_meta = self._latest_summary_meta(conn, customer_center_id)
                if latest_meta:
                    latest_snapshot_time = str(latest_meta["snapshot_time"] or "").strip()
                    latest_snapshot_dt = self._parse_snapshot_time_text(latest_snapshot_time)
                    if latest_snapshot_dt:
                        latest_snapshot_age_hours = round(
                            max((now_dt.replace(tzinfo=None) - latest_snapshot_dt).total_seconds(), 0.0) / 3600.0,
                            2,
                        )
                item = {
                    "customer_center_id": customer_center_id,
                    "latest_snapshot_time": latest_snapshot_time,
                    "latest_snapshot_age_hours": latest_snapshot_age_hours,
                    "status": "ok",
                    "reason": "",
                    "account_count": 0,
                    "repaired": False,
                    "repair_summary_snapshot_time": "",
                    "repair_detail_snapshot_time": "",
                }
                try:
                    client = self._build_scoped_customer_center_client(customer_center_id)
                    accounts = client.list_accounts()
                    item["account_count"] = len(accounts)
                    snapshot_dt = self._parse_snapshot_time_text(latest_snapshot_time)
                    needs_repair = (
                        not latest_snapshot_time
                        or snapshot_dt is None
                        or (now_dt.replace(tzinfo=None) - snapshot_dt).total_seconds() >= stale_seconds
                    )
                    if needs_repair:
                        summary_payload = self.collect_snapshot_for_customer_center(customer_center_id)
                        self.persist_snapshot(summary_payload)
                        item["repaired"] = True
                        item["repair_summary_snapshot_time"] = str(summary_payload.get("snapshot_time") or "").strip()
                        detail_payload = self.collect_extended_snapshot(force_refresh=True, customer_center_id=customer_center_id)
                        if not detail_payload.get("skipped"):
                            self.persist_extended_snapshot(detail_payload, replace_same_day=True)
                            item["repair_detail_snapshot_time"] = str(detail_payload.get("snapshot_time") or "").strip()
                        repaired_count += 1
                except Exception as exc:  # noqa: BLE001
                    error_count += 1
                    status_text, reason_text = self._classify_customer_center_auth_error(str(exc))
                    item["status"] = status_text
                    item["reason"] = reason_text
                    item["error"] = str(exc)
                items.append(item)

            if repaired_count:
                self.cleanup_history()
                self.clear_runtime_caches()

            ok_count = sum(1 for item in items if str(item.get("status") or "") == "ok")
            return {
                "ok": error_count == 0,
                "skipped": False,
                "reason": "" if error_count == 0 else f"{error_count} customer center authorization checks failed",
                "stale_hours": stale_hours,
                "customer_center_count": len(customer_center_ids),
                "checked_count": len(items),
                "ok_count": ok_count,
                "repaired_count": repaired_count,
                "error_count": error_count,
                "items": items,
            }

    def update_ocean_engine_runtime_config(self, payload: Any) -> dict[str, Any]:
        target_customer_center_id = str(getattr(payload, "customer_center_id", "") or "").strip()
        auth_code = str(getattr(payload, "auth_code", "") or "").strip()
        if not target_customer_center_id:
            raise ValueError("customer_center_id 不能为空")

        current_config = self.read_config()
        candidate_config = dict(current_config)
        candidate_config["customer_center_id"] = target_customer_center_id

        fallback_refresh_token = str(current_config.get("refresh_token") or "")
        next_token_payload: dict[str, Any] | None = None
        if auth_code:
            next_token_payload = self._exchange_auth_code_payload(candidate_config, auth_code)
            access_token = str(next_token_payload["access_token"])
        else:
            stored_target_payload = self._stored_token_payload_for_config(candidate_config)
            if stored_target_payload and (
                stored_target_payload.get("access_token") or stored_target_payload.get("refresh_token")
            ):
                access_token, next_token_payload = self._access_token_from_payload(candidate_config, stored_target_payload)
            else:
                access_token = self.build_client(current_config).get_access_token()
                current_token_payload = self._stored_token_payload_for_config(current_config)
                if current_token_payload:
                    fallback_refresh_token = str(
                        current_token_payload.get("refresh_token") or current_config.get("refresh_token") or ""
                    )

        try:
            preview = self._customer_center_preview(candidate_config, access_token, sample_limit=6)
        except Exception:
            if not auth_code and not next_token_payload:
                raise ApiError(
                    "The target CC has no saved token in this system, and the current token cannot access it. "
                    "Authorize this account into the system first, then switch by CC ID."
                )
            raise
        if next_token_payload:
            persisted_payload = self._persist_token_cache_for_config(candidate_config, next_token_payload)
            next_refresh_token = str(persisted_payload.get("refresh_token") or "")
        else:
            next_refresh_token = fallback_refresh_token
        self._persist_runtime_config_override(
            target_customer_center_id,
            refresh_token=next_refresh_token,
        )
        self.clear_runtime_caches()
        return {
            "config": self.ocean_engine_runtime_config(),
            "preview": preview,
        }

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

    def latest_extended_sync(self, display_scope: str = DISPLAY_SCOPE_CURRENT) -> dict[str, Any] | None:
        if self._display_scope_uses_all_customer_centers(display_scope):
            return self._latest_extended_sync_all_customer_centers()
        return self.snapshot_access.latest_extended_sync()

    def plan_assets(
        self,
        ad_id: int,
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> dict[str, Any]:
        if self._display_scope_uses_all_customer_centers(display_scope):
            return self._plan_assets_all_customer_centers(ad_id, snapshot_time, allowed_advertiser_ids)
        return self.snapshot_access.plan_assets(ad_id, snapshot_time, allowed_advertiser_ids)

    def summary_history(self, limit: int = 144, display_scope: str = DISPLAY_SCOPE_CURRENT) -> list[dict[str, Any]]:
        if self._display_scope_uses_all_customer_centers(display_scope):
            return self._summary_history_all_customer_centers(limit)
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

    def _upsert_material_upload_target_asset_locked(
        self,
        conn: Any,
        job_id: int,
        target_id: int,
        file_id: int,
        status: str,
        message: str = "",
    ) -> None:
        self.upload_access.upsert_material_upload_target_asset_locked(
            conn,
            job_id,
            target_id,
            file_id,
            status,
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
        target_file_pairs: list[dict[str, int]] | None = None,
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
        inserted_file_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id
                FROM material_upload_job_files
                WHERE job_id = ?
                ORDER BY id ASC
                """,
                (job_id,),
            ).fetchall()
        ]
        inserted_target_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id
                FROM material_upload_job_targets
                WHERE job_id = ?
                ORDER BY id ASC
                """,
                (job_id,),
            ).fetchall()
        ]
        source_file_id_map: dict[int, int] = {}
        for index, row in enumerate(inserted_file_rows):
            source_id = int(file_sources[index].get("_source_file_id", 0) or 0)
            if source_id > 0:
                source_file_id_map[source_id] = int(row["id"])
        source_target_id_map: dict[int, int] = {}
        for index, row in enumerate(inserted_target_rows):
            source_id = int(target_plans[index].get("_source_target_id", 0) or 0)
            if source_id > 0:
                source_target_id_map[source_id] = int(row["id"])

        pair_rows: list[tuple[Any, ...]] = []
        if target_file_pairs:
            seen_pairs: set[tuple[int, int]] = set()
            for pair in target_file_pairs:
                source_target_id = int(pair.get("source_target_id", 0) or 0)
                source_file_id = int(pair.get("source_file_id", 0) or 0)
                target_id = int(source_target_id_map.get(source_target_id, 0) or 0)
                file_id = int(source_file_id_map.get(source_file_id, 0) or 0)
                if not target_id or not file_id:
                    continue
                pair_key = (target_id, file_id)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                pair_rows.append((job_id, target_id, file_id, "queued", "", now, now))
            if not pair_rows:
                raise RuntimeError("material upload retry mapping is empty")
        else:
            pair_rows = [
                (job_id, int(target_row["id"]), int(file_row["id"]), "queued", "", now, now)
                for target_row in inserted_target_rows
                for file_row in inserted_file_rows
            ]
        conn.executemany(
            """
            INSERT INTO material_upload_job_target_assets (
                job_id, target_id, file_id, status, message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            pair_rows,
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
            retry_pair_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT target_id, file_id
                    FROM material_upload_job_target_assets
                    WHERE job_id = ? AND status = 'failed'
                    ORDER BY target_id ASC, file_id ASC
                    """,
                    (int(job_id),),
                ).fetchall()
            ]
            file_map = {int(row["id"]): row for row in file_rows}
            target_map = {int(row["id"]): row for row in target_rows}
            target_file_pairs: list[dict[str, int]] | None = None
            if retry_pair_rows:
                target_file_pairs = [
                    {
                        "source_target_id": int(row["target_id"]),
                        "source_file_id": int(row["file_id"]),
                    }
                    for row in retry_pair_rows
                ]
                retry_target_rows = [
                    target_map[target_id]
                    for target_id in dict.fromkeys(int(row["target_id"]) for row in retry_pair_rows)
                    if target_id in target_map
                ]
                retry_file_rows = [
                    file_map[file_id]
                    for file_id in dict.fromkeys(int(row["file_id"]) for row in retry_pair_rows)
                    if file_id in file_map
                ]
            else:
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
            available_file_ids: set[int] = set()
            for row in retry_file_rows:
                source_path = UPLOAD_DIR / str(row.get("relative_path") or "")
                if not source_path.exists():
                    missing_files += 1
                    continue
                source_file_id = int(row.get("id", 0) or 0)
                if source_file_id > 0:
                    available_file_ids.add(source_file_id)
                file_sources.append(
                    {
                        "original_name": str(row.get("original_name") or ""),
                        "mime_type": str(row.get("mime_type") or ""),
                        "source_path": source_path,
                        "file_size": int(row.get("file_size", 0) or 0),
                        "file_sha256": str(row.get("file_sha256") or ""),
                        "file_md5": str(row.get("file_md5") or ""),
                        "_source_file_id": source_file_id,
                    }
                )
            if not file_sources:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="失败文件已丢失，无法重试")
            if target_file_pairs is not None:
                target_file_pairs = [
                    pair for pair in target_file_pairs if int(pair["source_file_id"]) in available_file_ids
                ]
                if not target_file_pairs:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="失败文件已丢失，无法重试")
                allowed_target_ids = {int(pair["source_target_id"]) for pair in target_file_pairs}
                retry_target_rows = [
                    row for row in retry_target_rows if int(row.get("id", 0) or 0) in allowed_target_ids
                ]
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
                        "_source_target_id": int(item.get("id", 0) or 0),
                    }
                    for item in retry_target_rows
                ],
                file_sources,
                retry_note,
                target_file_pairs=target_file_pairs,
            )
        payload["source_job_id"] = int(job_id)
        payload["retry_file_count"] = len(file_sources)
        payload["retry_target_count"] = len(retry_target_rows)
        if missing_files > 0:
            payload["skipped_missing_files"] = missing_files
        return payload

    def delete_material_upload_job(self, user: dict[str, Any], job_id: int) -> dict[str, Any]:
        role = str(user.get("role") or "")
        if role not in {ROLE_ADMIN, ROLE_SUPERVISOR} or not self.can_upload_materials(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        cleanup_dir = UPLOAD_DIR / str(int(job_id))
        with self.db() as conn:
            job = self._material_upload_job_row_for_user_locked(conn, user, int(job_id))
            if not job:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="upload job not found")
            status_text = str(job.get("status") or "").strip().lower()
            if status_text in {"queued", "running"}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The upload job is still running and cannot be deleted yet.",
                )
            conn.execute("DELETE FROM material_upload_job_target_assets WHERE job_id = ?", (int(job_id),))
            conn.execute("DELETE FROM material_upload_job_file_assets WHERE job_id = ?", (int(job_id),))
            conn.execute("DELETE FROM material_upload_job_targets WHERE job_id = ?", (int(job_id),))
            conn.execute("DELETE FROM material_upload_job_files WHERE job_id = ?", (int(job_id),))
            conn.execute("DELETE FROM material_upload_jobs WHERE id = ?", (int(job_id),))
        try:
            if cleanup_dir.exists():
                shutil.rmtree(cleanup_dir, ignore_errors=True)
        except Exception:
            pass
        return {"id": int(job_id), "deleted": True}

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
        scoped_payload = self.performance_access.apply_account_scope(payload, allowed_advertiser_ids)
        return self._safe_apply_material_operator_rankings(
            scoped_payload,
            allowed_advertiser_ids=allowed_advertiser_ids,
        )

    def _missing_summary_days(self, conn: Any, start_dt: datetime, end_dt: datetime) -> list[datetime]:
        return self.performance_access.missing_summary_days(conn, start_dt, end_dt)

    def _performance_snapshot_from_db(self, start_dt: datetime, end_dt: datetime) -> dict[str, Any]:
        return self.performance_access.performance_snapshot_from_db(start_dt, end_dt)

    def _latest_snapshot_all_customer_centers(
        self,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> dict[str, Any] | None:
        with self.db() as conn:
            summary_rows = self._latest_rows_by_customer_center(
                [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT snapshot_time, customer_center_id
                        FROM summary_snapshots
                        WHERE COALESCE(customer_center_id, '') <> ''
                        ORDER BY snapshot_time DESC, customer_center_id ASC
                        """
                    ).fetchall()
                ]
            )
            selected_pairs = self._snapshot_pairs_from_rows(summary_rows)
            if not selected_pairs:
                return None
            snapshot_times = sorted({snapshot_time for _customer_center_id, snapshot_time in selected_pairs})
            placeholders = ",".join("?" for _ in snapshot_times)
            account_rows = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM account_snapshots
                        WHERE snapshot_time IN ({placeholders})
                        ORDER BY snapshot_time DESC, stat_cost DESC, advertiser_id ASC
                        """,
                        snapshot_times,
                    ).fetchall()
                ],
                selected_pairs,
            )
            plan_rows = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM plan_snapshots
                        WHERE snapshot_time IN ({placeholders})
                        ORDER BY snapshot_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, ad_id ASC
                        """,
                        snapshot_times,
                    ).fetchall()
                ],
                selected_pairs,
            )
            latest_pairs = self._latest_snapshot_pairs_by_customer_center(selected_pairs)
            latest_snapshot_times = sorted({snapshot_time for _customer_center_id, snapshot_time in latest_pairs})
            latest_placeholders = ",".join("?" for _ in latest_snapshot_times)
            account_balance_items = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM account_balances
                        WHERE snapshot_time IN ({latest_placeholders})
                        ORDER BY snapshot_time DESC, advertiser_id ASC
                        """,
                        latest_snapshot_times,
                    ).fetchall()
                ],
                latest_pairs,
            )
            shared_wallet_items = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM shared_wallets
                        WHERE snapshot_time IN ({latest_placeholders})
                        ORDER BY snapshot_time DESC, main_wallet_id ASC
                        """,
                        latest_snapshot_times,
                    ).fetchall()
                ],
                latest_pairs,
            )
            wallet_relation_items = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM shared_wallet_account_relations
                        WHERE snapshot_time IN ({latest_placeholders})
                        ORDER BY snapshot_time DESC, main_wallet_id ASC, advertiser_id ASC
                        """,
                        latest_snapshot_times,
                    ).fetchall()
                ],
                latest_pairs,
            )

        account_items = self.performance_access.aggregate_account_snapshots(account_rows)
        plan_items = self._apply_employee_attribution(
            [self._decorate_plan_item(item) for item in self.performance_access.aggregate_plan_snapshots(plan_rows)],
            account_items,
        )
        summary_payload, products, employees, operators = self._rankings_bundle(
            self._scoped_summary(account_items, plan_items),
            account_items,
            plan_items,
        )
        summary_payload["wallet_count"] = len(shared_wallet_items)
        summary_payload["account_balance_count"] = len(account_balance_items)
        payload = {
            "snapshot_time": max(snapshot_times) if snapshot_times else "",
            "summary": summary_payload,
            "accounts": account_items,
            "plans": plan_items,
            "accountBalances": account_balance_items,
            "sharedWallets": shared_wallet_items,
            "walletRelations": wallet_relation_items,
            "products": products,
            "employees": employees,
            "operators": operators,
            "extendedSync": self._latest_extended_sync_all_customer_centers(),
            "customer_center_count": len(latest_pairs),
        }
        return self._apply_account_scope(payload, allowed_advertiser_ids)

    def _compute_latest_snapshot(
        self,
        allowed_advertiser_ids: set[int] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> dict[str, Any] | None:
        if self._display_scope_uses_all_customer_centers(display_scope):
            payload = self._latest_snapshot_all_customer_centers(allowed_advertiser_ids)
            if not payload:
                return payload
            return self._safe_apply_material_operator_rankings(
                payload,
                allowed_advertiser_ids=allowed_advertiser_ids,
                snapshot_time=str(payload.get("snapshot_time") or "").strip(),
            )
        payload = self.performance_access.latest_snapshot(allowed_advertiser_ids)
        if not payload:
            return payload
        return self._safe_apply_material_operator_rankings(
            payload,
            allowed_advertiser_ids=allowed_advertiser_ids,
        )

    def _store_latest_snapshot_cache(self, cache_key: str, payload: dict[str, Any] | None) -> None:
        with self._latest_snapshot_cache_lock:
            self._latest_snapshot_cache[cache_key] = {
                "_cached_at": time.time(),
                "payload": copy.deepcopy(payload),
            }

    def _refresh_latest_snapshot_cache(
        self,
        cache_key: str,
        raw_cache_key: str,
        cache_version: str,
        allowed_advertiser_ids: set[int] | None,
        display_scope: str,
    ) -> None:
        try:
            payload = self._compute_latest_snapshot(allowed_advertiser_ids, display_scope)
            self._store_latest_snapshot_cache(cache_key, payload)
            if isinstance(payload, dict):
                self._shared_dict_cache_set(
                    "latest-snapshot",
                    raw_cache_key,
                    cache_version,
                    payload,
                    LATEST_SNAPSHOT_STALE_SECONDS,
                )
        except Exception:
            pass
        finally:
            with self._latest_snapshot_cache_lock:
                self._latest_snapshot_refreshing.discard(cache_key)

    def _schedule_latest_snapshot_refresh(
        self,
        cache_key: str,
        raw_cache_key: str,
        cache_version: str,
        allowed_advertiser_ids: set[int] | None,
        display_scope: str,
    ) -> None:
        with self._latest_snapshot_cache_lock:
            if cache_key in self._latest_snapshot_refreshing:
                return
            self._latest_snapshot_refreshing.add(cache_key)
        threading.Thread(
            target=self._refresh_latest_snapshot_cache,
            args=(cache_key, raw_cache_key, cache_version, allowed_advertiser_ids, display_scope),
            daemon=True,
            name=f"latest-snapshot-refresh-{display_scope}",
        ).start()

    def latest_snapshot(
        self,
        allowed_advertiser_ids: set[int] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> dict[str, Any] | None:
        cache_version = self._shared_cache_version("latest-snapshot")
        raw_cache_key = build_latest_snapshot_cache_key(
            allowed_advertiser_ids,
            display_scope,
            self._current_customer_center_id(),
        )
        cache_key = self._versioned_cache_key(cache_version, raw_cache_key)
        now_ts = time.time()
        with self._latest_snapshot_cache_lock:
            cached = copy.deepcopy(self._latest_snapshot_cache.get(cache_key))
        if cached:
            cached_payload = cached.get("payload")
            cached_at = float(cached.get("_cached_at", 0.0) or 0.0)
            age = max(now_ts - cached_at, 0.0)
            if age < LATEST_SNAPSHOT_CACHE_SECONDS:
                return cached_payload
            if age < LATEST_SNAPSHOT_STALE_SECONDS:
                self._schedule_latest_snapshot_refresh(
                    cache_key,
                    raw_cache_key,
                    cache_version,
                    allowed_advertiser_ids,
                    display_scope,
                )
                return cached_payload
        shared_payload = self._shared_dict_cache_get("latest-snapshot", raw_cache_key, cache_version)
        if shared_payload is not None:
            self._store_latest_snapshot_cache(cache_key, shared_payload)
            return copy.deepcopy(shared_payload)
        payload = self._compute_latest_snapshot(allowed_advertiser_ids, display_scope)
        self._store_latest_snapshot_cache(cache_key, payload)
        if isinstance(payload, dict):
            self._shared_dict_cache_set("latest-snapshot", raw_cache_key, cache_version, payload, LATEST_SNAPSHOT_STALE_SECONDS)
        return copy.deepcopy(payload)

    def clear_runtime_caches(self) -> None:
        self._performance_cache.clear()
        self._material_cache.clear()
        self._material_preview_refresh_cache.clear()
        self._preview_video_resolve_cache.clear()
        self._comment_cache.clear()
        self._backfill_queue_marks.clear()
        with self._latest_snapshot_cache_lock:
            self._latest_snapshot_cache.clear()
            self._latest_snapshot_refreshing.clear()
        self._invalidate_cache_namespaces(
            "dashboard-overview",
            "performance",
            "material",
            "comment",
            "latest-snapshot",
        )

    def _clear_comment_caches(self) -> None:
        self._comment_cache.clear()
        self._invalidate_cache_namespaces("comment")

    def _build_dashboard_overview_payload(
        self,
        allowed_advertiser_ids: set[int] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        config = self.read_config()
        start_dt, end_dt, _range_label = build_performance_window("day", str(config.get("timezone") or TIMEZONE))
        if self._display_scope_uses_all_customer_centers(display_scope):
            payload = self._performance_snapshot_from_db_all_customer_centers(start_dt, end_dt)
        else:
            payload = self._performance_snapshot_from_db(start_dt, end_dt)

        accounts = [dict(item) for item in payload.get("accounts", [])]
        plans = self._apply_employee_attribution([dict(item) for item in payload.get("plans", [])], accounts)
        scoped_payload = dict(payload)
        scoped_payload["accounts"] = accounts
        scoped_payload["plans"] = plans
        scoped_payload["summary"], scoped_payload["products"], scoped_payload["employees"], scoped_payload["operators"] = self._rankings_bundle(
            dict(scoped_payload.get("summary") or {}),
            accounts,
            plans,
        )
        if allowed_advertiser_ids is not None:
            scoped_payload = self._apply_account_scope(scoped_payload, allowed_advertiser_ids)
        if str((user or {}).get("role") or "").strip() == ROLE_OPERATOR:
            scoped_payload = self._apply_operator_scope(scoped_payload, user or {})
        return {
            "snapshot_time": str(scoped_payload.get("snapshot_time") or "").strip(),
            "window_start": str(scoped_payload.get("window_start") or "").strip(),
            "window_end": str(scoped_payload.get("window_end") or "").strip(),
            "summary": dict(scoped_payload.get("summary") or {}),
            "snapshot_count": int(scoped_payload.get("snapshot_count", 0) or 0),
            "customer_center_count": int(scoped_payload.get("customer_center_count", 0) or 0),
        }

    def dashboard_overview_payload(
        self,
        allowed_advertiser_ids: set[int] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        display_scope_key = str(display_scope or DISPLAY_SCOPE_CURRENT).strip().lower()
        customer_center_id = (
            "__all_customer_centers__"
            if self._display_scope_uses_all_customer_centers(display_scope_key)
            else self._current_customer_center_id()
        )
        role = str((user or {}).get("role") or "").strip().lower()
        user_id = int((user or {}).get("id", 0) or 0)
        cache_version = self._shared_cache_version("dashboard-overview")
        cache_key = build_dashboard_overview_cache_key(
            allowed_advertiser_ids,
            display_scope_key,
            customer_center_id,
            role,
            user_id,
            cache_version,
        )
        cached = self._shared_json_cache_get(cache_key)
        if isinstance(cached, dict):
            return copy.deepcopy(cached)
        payload = self._build_dashboard_overview_payload(allowed_advertiser_ids, display_scope_key, user)
        self._shared_json_cache_set(cache_key, payload, RANGE_CACHE_SECONDS)
        return copy.deepcopy(payload)

    def _performance_snapshot_from_db_all_customer_centers(
        self,
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict[str, Any]:
        with self.db() as conn:
            snapshots = self._latest_rows_by_customer_center_day(
                [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT snapshot_time, customer_center_id, window_start, window_end
                        FROM summary_snapshots
                        WHERE COALESCE(customer_center_id, '') <> ''
                          AND snapshot_time >= ?
                          AND snapshot_time <= ?
                        ORDER BY snapshot_time DESC, customer_center_id ASC
                        """,
                        (
                            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                            end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        ),
                    ).fetchall()
                ]
            )
            if not snapshots:
                return self.performance_access._empty_performance_snapshot(start_dt, end_dt)

            selected_pairs = self._snapshot_pairs_from_rows(snapshots)
            snapshot_times = sorted({snapshot_time for _customer_center_id, snapshot_time in selected_pairs})
            placeholders = ",".join("?" for _ in snapshot_times)
            account_rows = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM account_snapshots
                        WHERE snapshot_time IN ({placeholders})
                        ORDER BY snapshot_time DESC, stat_cost DESC, advertiser_id ASC
                        """,
                        snapshot_times,
                    ).fetchall()
                ],
                selected_pairs,
            )
            plan_rows = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM plan_snapshots
                        WHERE snapshot_time IN ({placeholders})
                        ORDER BY snapshot_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, ad_id ASC
                        """,
                        snapshot_times,
                    ).fetchall()
                ],
                selected_pairs,
            )
            latest_pairs = self._latest_snapshot_pairs_by_customer_center(selected_pairs)
            latest_snapshot_times = sorted({snapshot_time for _customer_center_id, snapshot_time in latest_pairs})
            latest_placeholders = ",".join("?" for _ in latest_snapshot_times)
            account_balance_items = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM account_balances
                        WHERE snapshot_time IN ({latest_placeholders})
                        ORDER BY snapshot_time DESC, advertiser_id ASC
                        """,
                        latest_snapshot_times,
                    ).fetchall()
                ],
                latest_pairs,
            )
            shared_wallet_items = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM shared_wallets
                        WHERE snapshot_time IN ({latest_placeholders})
                        ORDER BY snapshot_time DESC, main_wallet_id ASC
                        """,
                        latest_snapshot_times,
                    ).fetchall()
                ],
                latest_pairs,
            )
            wallet_relation_items = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM shared_wallet_account_relations
                        WHERE snapshot_time IN ({latest_placeholders})
                        ORDER BY snapshot_time DESC, main_wallet_id ASC, advertiser_id ASC
                        """,
                        latest_snapshot_times,
                    ).fetchall()
                ],
                latest_pairs,
            )

        account_items = self.performance_access.aggregate_account_snapshots(account_rows)
        plan_items = [self._decorate_plan_item(item) for item in self.performance_access.aggregate_plan_snapshots(plan_rows)]
        total_cost = round(
            sum(float(item.get("stat_cost", 0.0) or 0.0) for item in account_items if bool(item.get("ok", True))),
            2,
        )
        total_pay = round(
            sum(float(item.get("pay_amount", 0.0) or 0.0) for item in account_items if bool(item.get("ok", True))),
            2,
        )
        total_orders = int(
            sum(int(float(item.get("order_count", 0.0) or 0.0)) for item in account_items if bool(item.get("ok", True)))
        )
        active_accounts = sum(
            1 for item in account_items if bool(item.get("ok", True)) and float(item.get("stat_cost", 0.0) or 0.0) > 0
        )
        active_plans = sum(1 for item in plan_items if float(item.get("stat_cost", 0.0) or 0.0) > 0)
        return {
            "snapshot_time": max(snapshot_times) if snapshot_times else "",
            "window_start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "window_end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "account_count": len(account_items),
                "active_account_count": active_accounts,
                "plan_count": len(plan_items),
                "active_plan_count": active_plans,
                "stat_cost": total_cost,
                "pay_amount": total_pay,
                "order_count": total_orders,
                "roi": round(total_pay / total_cost, 2) if total_cost > 0 else 0.0,
                "account_failures": sum(1 for item in account_items if not bool(item.get("ok", True))),
                "plan_failures": 0,
                "wallet_count": len(shared_wallet_items),
                "balance_failures": 0,
            },
            "accounts": account_items,
            "plans": plan_items,
            "accountBalances": account_balance_items,
            "sharedWallets": shared_wallet_items,
            "walletRelations": wallet_relation_items,
            "errors": {
                "accounts": [dict(item) for item in account_items if not bool(item.get("ok", True))],
                "plans": [],
                "balances": [],
            },
            "snapshot_count": len(snapshot_times),
            "customer_center_count": len(latest_pairs),
        }

    def _latest_extended_sync_run(self, conn: Any) -> Any:
        return self.history_access.latest_extended_sync_run(conn)

    def _plan_assets_all_customer_centers(
        self,
        ad_id: int,
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        target_snapshot = str(snapshot_time or "").strip()
        with self.db() as conn:
            if target_snapshot:
                summary_rows = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT snapshot_time, customer_center_id
                        FROM summary_snapshots
                        WHERE COALESCE(customer_center_id, '') <> ''
                          AND snapshot_time = ?
                        ORDER BY customer_center_id ASC
                        """,
                        (target_snapshot,),
                    ).fetchall()
                ]
            else:
                summary_rows = self._latest_rows_by_customer_center(
                    [
                        dict(row)
                        for row in conn.execute(
                            """
                            SELECT snapshot_time, customer_center_id
                            FROM summary_snapshots
                            WHERE COALESCE(customer_center_id, '') <> ''
                            ORDER BY snapshot_time DESC, customer_center_id ASC
                            """
                        ).fetchall()
                    ]
                )
            selected_pairs = self._snapshot_pairs_from_rows(summary_rows)
            if not selected_pairs:
                return {"snapshot_time": target_snapshot, "plan": None, "detail": None, "products": [], "materials": []}

            snapshot_times = sorted({snapshot_time for _customer_center_id, snapshot_time in selected_pairs})
            placeholders = ",".join("?" for _ in snapshot_times)
            plan_rows = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM plan_snapshots
                        WHERE snapshot_time IN ({placeholders})
                          AND ad_id = ?
                        ORDER BY snapshot_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC
                        """,
                        [*snapshot_times, ad_id],
                    ).fetchall()
                ],
                selected_pairs,
            )
            if not plan_rows:
                return {
                    "snapshot_time": max(snapshot_times) if snapshot_times else target_snapshot,
                    "plan": None,
                    "detail": None,
                    "products": [],
                    "materials": [],
                }
            if allowed_advertiser_ids is not None:
                allowed = {int(item) for item in allowed_advertiser_ids}
                plan_rows = [row for row in plan_rows if int(row.get("advertiser_id", 0) or 0) in allowed]
                if not plan_rows:
                    return {
                        "snapshot_time": max(snapshot_times) if snapshot_times else target_snapshot,
                        "plan": None,
                        "detail": None,
                        "products": [],
                        "materials": [],
                    }

            plan_pairs = {
                (
                    str(row.get("customer_center_id") or "").strip(),
                    str(row.get("snapshot_time") or "").strip(),
                )
                for row in plan_rows
            }
            detail_rows = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM plan_detail_snapshots
                        WHERE snapshot_time IN ({placeholders})
                          AND ad_id = ?
                        ORDER BY snapshot_time DESC
                        """,
                        [*snapshot_times, ad_id],
                    ).fetchall()
                ],
                plan_pairs,
            )
            product_rows = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM product_snapshots
                        WHERE snapshot_time IN ({placeholders})
                          AND ad_id = ?
                        ORDER BY snapshot_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, product_key ASC
                        """,
                        [*snapshot_times, ad_id],
                    ).fetchall()
                ],
                plan_pairs,
            )
            material_rows = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT *
                        FROM material_snapshots
                        WHERE snapshot_time IN ({placeholders})
                          AND ad_id = ?
                        ORDER BY snapshot_time DESC, create_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, material_type ASC, material_key ASC
                        """,
                        [*snapshot_times, ad_id],
                    ).fetchall()
                ],
                plan_pairs,
            )
            original_flag_rows = self._filter_rows_for_snapshot_pairs(
                [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT snapshot_time, customer_center_id, advertiser_id, material_id, is_original
                        FROM video_origin_flags
                        WHERE snapshot_time IN ({placeholders})
                        ORDER BY snapshot_time DESC
                        """,
                        snapshot_times,
                    ).fetchall()
                ],
                plan_pairs,
            )

        aggregated_plan_rows = self.performance_access.aggregate_plan_snapshots(plan_rows)
        plan_payload = self._decorate_plan_item(aggregated_plan_rows[0]) if aggregated_plan_rows else None
        detail_payload = dict(detail_rows[0]) if detail_rows else None
        if detail_payload:
            detail_payload["marketing_goal_label"] = plan_marketing_goal_label(detail_payload["marketing_goal"])
            detail_payload["status_text"] = format_plan_status_text(
                detail_payload["status"],
                detail_payload["opt_status"],
            )
        original_flags = {
            (
                str(row.get("snapshot_time") or "").strip(),
                str(row.get("customer_center_id") or "").strip(),
                int(row.get("advertiser_id", 0) or 0),
                str(row.get("material_id") or ""),
            ): bool(row.get("is_original"))
            for row in original_flag_rows
        }
        material_items: list[dict[str, Any]] = []
        for row in material_rows:
            item = dict(row)
            material_key = (
                str(item.get("snapshot_time") or "").strip(),
                str(item.get("customer_center_id") or "").strip(),
                int(item.get("advertiser_id", 0) or 0),
                str(item.get("material_id") or ""),
            )
            item["is_original"] = bool(original_flags.get(material_key, False))
            material_items.append(item)
        return {
            "snapshot_time": max(snapshot_times) if snapshot_times else target_snapshot,
            "plan": plan_payload,
            "detail": detail_payload,
            "products": product_rows,
            "materials": material_items,
            "originalVideoCount": sum(1 for item in material_items if item["is_original"]),
        }

    def _latest_extended_sync_runs_for_window(
        self, conn: Any, start_dt: datetime, end_dt: datetime
    ) -> list[dict[str, Any]]:
        return self.history_access.latest_extended_sync_runs_for_window(conn, start_dt, end_dt)

    def _summary_meta_for_day(self, conn: Any, target_day: datetime) -> dict[str, Any] | None:
        return self.history_access.summary_meta_for_day(conn, target_day)

    def _summary_meta_for_customer_center_day(
        self,
        conn: Any,
        target_day: datetime,
        customer_center_id: str,
    ) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT snapshot_time, window_start, window_end
            FROM summary_snapshots
            WHERE customer_center_id = ?
              AND snapshot_time >= ?
              AND snapshot_time <= ?
            ORDER BY snapshot_time DESC
            LIMIT 1
            """,
            (
                str(customer_center_id or "").strip(),
                target_day.strftime("%Y-%m-%d 00:00:00"),
                target_day.strftime("%Y-%m-%d 23:59:59"),
            ),
        ).fetchone()
        return dict(row) if row else None

    def _missing_extended_days(self, conn: Any, start_dt: datetime, end_dt: datetime) -> list[datetime]:
        return self.history_access.missing_extended_days(conn, start_dt, end_dt)

    def latest_account_catalog(
        self,
        allowed_advertiser_ids: set[int] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]]
        with self.db() as conn:
            if self._display_scope_uses_all_customer_centers(display_scope):
                summary_rows = self._latest_rows_by_customer_center(
                    [
                        dict(row)
                        for row in conn.execute(
                            """
                            SELECT snapshot_time, customer_center_id
                            FROM summary_snapshots
                            WHERE COALESCE(customer_center_id, '') <> ''
                            ORDER BY snapshot_time DESC, customer_center_id ASC
                            """
                        ).fetchall()
                    ]
                )
                selected_pairs = self._snapshot_pairs_from_rows(summary_rows)
                if not selected_pairs:
                    return []
                snapshot_times = sorted({snapshot_time for _customer_center_id, snapshot_time in selected_pairs})
                placeholders = ",".join("?" for _ in snapshot_times)
                items = self._filter_rows_for_snapshot_pairs(
                    [
                        dict(row)
                        for row in conn.execute(
                            f"""
                            SELECT snapshot_time, customer_center_id, advertiser_id, advertiser_name
                            FROM account_snapshots
                            WHERE snapshot_time IN ({placeholders})
                            ORDER BY snapshot_time DESC, advertiser_name ASC, advertiser_id ASC
                            """,
                            snapshot_times,
                        ).fetchall()
                    ],
                    selected_pairs,
                )
            else:
                customer_center_id = self._current_customer_center_id()
                latest = conn.execute(
                    """
                    SELECT snapshot_time
                    FROM summary_snapshots
                    WHERE customer_center_id = ?
                    ORDER BY snapshot_time DESC
                    LIMIT 1
                    """,
                    (customer_center_id,),
                ).fetchone()
                if not latest:
                    return []
                items = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT advertiser_id, advertiser_name
                        FROM account_snapshots
                        WHERE snapshot_time = ?
                          AND customer_center_id = ?
                        ORDER BY advertiser_name ASC, advertiser_id ASC
                        """,
                        (str(latest["snapshot_time"] or ""), customer_center_id),
                    ).fetchall()
                ]
        if allowed_advertiser_ids is not None:
            allowed = {int(item) for item in allowed_advertiser_ids}
            items = [item for item in items if int(item.get("advertiser_id", 0) or 0) in allowed]
        deduped: dict[int, dict[str, Any]] = {}
        for item in items:
            advertiser_id = int(item.get("advertiser_id", 0) or 0)
            if not advertiser_id or advertiser_id in deduped:
                continue
            deduped[advertiser_id] = {
                "advertiser_id": advertiser_id,
                "advertiser_name": str(item.get("advertiser_name") or "").strip(),
            }
        return sorted(
            deduped.values(),
            key=lambda item: (str(item.get("advertiser_name") or ""), int(item.get("advertiser_id", 0) or 0)),
        )

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
        return self._merge_runtime_config_override(self._base_runtime_config(), self._runtime_config_override_row())

    def build_client(self, config: dict[str, Any]) -> OceanEngineClient:
        return OceanEngineClient(
            config=config,
            token_cache_path=TOKEN_CACHE_PATH,
            latest_token_path=LATEST_TOKEN_PATH,
            token_persist_callback=self.persist_token_record,
        )

    def _scoped_config_for_customer_center(self, customer_center_id: str) -> dict[str, Any]:
        target_customer_center_id = str(customer_center_id or "").strip()
        if not target_customer_center_id:
            raise ValueError("customer_center_id is required")
        config = dict(self.read_config())
        config["customer_center_id"] = target_customer_center_id
        stored_payload = self._stored_token_payload_for_config(config) or {}
        stored_refresh_token = str(stored_payload.get("refresh_token") or "").strip()
        if stored_refresh_token:
            config["refresh_token"] = stored_refresh_token
        return config

    def _build_scoped_customer_center_client(self, customer_center_id: str) -> OceanEngineClient:
        target_customer_center_id = str(customer_center_id or "").strip()
        config = self._scoped_config_for_customer_center(target_customer_center_id)
        token_dir = DATA_DIR / "preview_token_cache"
        token_dir.mkdir(parents=True, exist_ok=True)
        token_cache_path = token_dir / f"{target_customer_center_id}.json"
        latest_token_path = token_dir / f"{target_customer_center_id}.latest.json"
        stored_payload = self._stored_token_payload_for_config(config) or {}
        if stored_payload.get("access_token") or stored_payload.get("refresh_token"):
            existing_payload: dict[str, Any] = {}
            try:
                if latest_token_path.exists():
                    existing_payload = load_json(latest_token_path)
                elif token_cache_path.exists():
                    existing_payload = load_json(token_cache_path)
            except Exception:
                existing_payload = {}
            stored_updated_at = int(stored_payload.get("updated_at") or 0)
            existing_updated_at = int(existing_payload.get("updated_at") or 0)
            stored_refresh_token = str(stored_payload.get("refresh_token") or "").strip()
            existing_refresh_token = str(existing_payload.get("refresh_token") or "").strip()
            if (
                not existing_payload
                or stored_updated_at > existing_updated_at
                or (stored_refresh_token and stored_refresh_token != existing_refresh_token)
            ):
                normalized_payload = dict(stored_payload)
                normalized_payload["app_id"] = str(config.get("app_id") or "")
                normalized_payload["customer_center_id"] = target_customer_center_id
                dump_json(token_cache_path, normalized_payload)
                try:
                    os.chmod(token_cache_path, 0o600)
                except OSError:
                    pass
                if latest_token_path != token_cache_path:
                    dump_json(latest_token_path, normalized_payload)
                    try:
                        os.chmod(latest_token_path, 0o600)
                    except OSError:
                        pass
        return OceanEngineClient(
            config=config,
            token_cache_path=token_cache_path,
            latest_token_path=latest_token_path,
            token_persist_callback=self.persist_token_record,
        )

    @staticmethod
    def _decorate_plan_item(row: Any) -> dict[str, Any]:
        item = dict(row)
        item["plan_source"] = str(item.get("plan_source") or PLAN_SOURCE_UNI_PROMOTION).strip().upper()
        delivery_type = str(item.get("plan_delivery_type") or PLAN_DELIVERY_TYPE_GLOBAL).strip().upper()
        if delivery_type not in {PLAN_DELIVERY_TYPE_GLOBAL, PLAN_DELIVERY_TYPE_CUBIC}:
            delivery_type = PLAN_DELIVERY_TYPE_GLOBAL
        item["plan_delivery_type"] = delivery_type
        item["plan_source_text"] = "乘方投放" if delivery_type == PLAN_DELIVERY_TYPE_CUBIC else "全域投放"
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
    def _customer_center_second(customer_center_id: str) -> int:
        return DashboardService._customer_center_slot(customer_center_id, 60)

    @staticmethod
    def _customer_center_slot(customer_center_id: str, slot_count: int) -> int:
        normalized_customer_center_id = str(customer_center_id or "").strip()
        normalized_slot_count = max(int(slot_count or 0), 1)
        if not normalized_customer_center_id:
            return normalized_slot_count - 1
        digest = hashlib.sha1(normalized_customer_center_id.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") % normalized_slot_count

    def _scoped_day_snapshot_time(self, target_day: datetime, customer_center_id: str) -> str:
        scoped_offset = self._customer_center_slot(customer_center_id, 3600)
        return datetime(
            target_day.year,
            target_day.month,
            target_day.day,
            23,
            scoped_offset // 60,
            scoped_offset % 60,
        ).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _snapshot_time_owner(conn: Any, table_name: str, snapshot_time: str) -> str:
        row = conn.execute(
            f"SELECT customer_center_id FROM {table_name} WHERE snapshot_time = ? LIMIT 1",
            (snapshot_time,),
        ).fetchone()
        if not row:
            return ""
        try:
            return str(row["customer_center_id"] or "").strip()
        except Exception:
            return str(row[0] or "").strip()

    def _next_available_snapshot_time(
        self,
        conn: Any,
        table_name: str,
        snapshot_time: str,
        customer_center_id: str,
    ) -> str:
        candidate = str(snapshot_time or "").strip()
        normalized_customer_center_id = str(customer_center_id or "").strip()
        if not candidate:
            return candidate
        current_owner = self._snapshot_time_owner(conn, table_name, candidate)
        if not current_owner or current_owner == normalized_customer_center_id:
            return candidate

        try:
            base_dt = datetime.strptime(candidate, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return candidate

        for offset_seconds in range(1, 86400):
            for direction in (1, -1):
                candidate_dt = base_dt + timedelta(seconds=offset_seconds * direction)
                if candidate_dt.date() != base_dt.date():
                    continue
                shifted_candidate = candidate_dt.strftime("%Y-%m-%d %H:%M:%S")
                shifted_owner = self._snapshot_time_owner(conn, table_name, shifted_candidate)
                if not shifted_owner or shifted_owner == normalized_customer_center_id:
                    return shifted_candidate
        raise RuntimeError(f"no available snapshot_time slot for {table_name} on {candidate[:10]}")

    @staticmethod
    def _replace_snapshot_time_in_rows(rows: list[tuple[Any, ...]], snapshot_time: str) -> list[tuple[Any, ...]]:
        if not rows:
            return rows
        return [(snapshot_time, *tuple(row)[1:]) for row in rows]

    @staticmethod
    def _employee_name(value: Any) -> str:
        text = str(value or "").strip()
        return text or "未归属"

    @staticmethod
    def _comment_type_label(value: Any) -> str:
        text = str(value or "").strip().upper()
        return COMMENT_TYPE_LABELS.get(text, text or "-")

    @staticmethod
    def _comment_hide_status_label(value: Any) -> str:
        text = str(value or "").strip().upper()
        return COMMENT_HIDE_STATUS_LABELS.get(text, text or "未隐藏")

    @staticmethod
    def _comment_level_label(value: Any) -> str:
        text = str(value or "").strip().upper()
        return COMMENT_LEVEL_LABELS.get(text, text or "-")

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
    def _format_unix_time_text(value: Any) -> str:
        try:
            epoch = float(value or 0.0)
        except (TypeError, ValueError):
            return ""
        if epoch <= 0:
            return ""
        if epoch >= 1_000_000_000_000:
            epoch = epoch / 1000.0
        try:
            return datetime.fromtimestamp(epoch, ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            return ""

    @classmethod
    def _normalize_datetime_text(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (int, float)):
            return cls._format_unix_time_text(value)

        text = str(value or "").strip()
        if not text:
            return ""
        if text.isdigit():
            unix_text = cls._format_unix_time_text(text)
            if unix_text:
                return unix_text

        normalized = text.replace("/", "-")
        iso_candidate = normalized
        if iso_candidate.endswith("Z"):
            iso_candidate = f"{iso_candidate[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(iso_candidate)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(ZoneInfo(TIMEZONE))
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                if fmt == "%Y-%m-%d":
                    return parsed.strftime("%Y-%m-%d 00:00:00")
                if fmt == "%Y-%m-%d %H:%M":
                    return parsed.strftime("%Y-%m-%d %H:%M:00")
                return parsed.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
        return text.replace("T", " ")[:19]

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
                    "video_material_id",
                    "image_material_id",
                    "title_material_id",
                    "carousel_material_id",
                    "live_room_material_id",
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
            chosen.get("video_material_id"),
            chosen.get("image_material_id"),
            chosen.get("title_material_id"),
            chosen.get("carousel_material_id"),
            chosen.get("live_room_material_id"),
            chosen.get("id"),
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
    def _extract_material_create_time(cls, material_type: str, row: dict[str, Any]) -> str:
        material_info = cls._json_object(row.get("material_info"))
        preferred_keys = {
            "VIDEO": ["video_material"],
            "IMAGE": ["image_material"],
            "TITLE": ["title_material"],
            "CAROUSEL": ["carousel_material"],
            "LIVE_ROOM": ["live_room_material", "room_material"],
        }
        candidate_sections: list[dict[str, Any]] = []
        for key in preferred_keys.get(material_type, []):
            value = material_info.get(key)
            if isinstance(value, dict):
                candidate_sections.append(value)
        for value in material_info.values():
            if isinstance(value, dict) and value not in candidate_sections:
                candidate_sections.append(value)

        for item in [row, material_info, *candidate_sections]:
            if not isinstance(item, dict):
                continue
            create_time = cls._normalize_datetime_text(
                cls._first_text(
                    item.get("create_time"),
                    item.get("createTime"),
                    item.get("created_time"),
                    item.get("createdTime"),
                    item.get("created_at"),
                    item.get("createdAt"),
                    item.get("material_create_time"),
                    item.get("materialCreateTime"),
                )
            )
            if create_time:
                return create_time
        return ""

    @classmethod
    def _extract_material_product_names(cls, raw_payload: Any) -> list[str]:
        payload = cls._json_object(raw_payload)
        product_info = payload.get("product_info")
        if isinstance(product_info, dict):
            items = [product_info]
        elif isinstance(product_info, list):
            items = [item for item in product_info if isinstance(item, dict)]
        else:
            items = []
        names: list[str] = []
        for item in items:
            product_name = cls._first_text(item.get("product_name"), item.get("name"))
            if product_name and product_name not in names:
                names.append(product_name)
        return names

    @staticmethod
    def _summarize_material_product_names(names: list[str]) -> str:
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        summary = " / ".join(names[:2])
        if len(names) > 2:
            return f"{summary} 等{len(names)}个商品"
        return summary

    @classmethod
    def _extract_material_library_image_id(cls, raw_payload: Any) -> str:
        payload = cls._json_object(raw_payload)
        material_info = cls._json_object(payload.get("material_info"))
        image_material = cls._json_object(material_info.get("image_material"))
        return cls._first_text(image_material.get("image_id"), image_material.get("imageId"))

    @classmethod
    def _normalize_image_material_payload(cls, payload: Any) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            candidates = [payload]
        elif isinstance(payload, list):
            candidates = [item for item in payload if isinstance(item, dict)]
        normalized: list[dict[str, Any]] = []
        for item in candidates:
            image_ids: list[str] = []
            raw_image_ids = item.get("image_ids")
            if isinstance(raw_image_ids, list):
                for value in raw_image_ids:
                    text = str(value or "").strip()
                    if text and text not in image_ids:
                        image_ids.append(text)
            single_image_id = cls._first_text(item.get("image_id"), item.get("imageId"))
            if single_image_id and single_image_id not in image_ids:
                image_ids.append(single_image_id)
            if not image_ids:
                nested_image = cls._json_object(item.get("image_material"))
                nested_image_id = cls._first_text(nested_image.get("image_id"), nested_image.get("imageId"))
                if nested_image_id:
                    image_ids.append(nested_image_id)
            if not image_ids:
                continue
            normalized_item: dict[str, Any] = {"image_ids": image_ids}
            image_mode = cls._first_text(item.get("image_mode"), item.get("imageMode"))
            if image_mode:
                normalized_item["image_mode"] = image_mode
            normalized.append(normalized_item)
        return normalized

    @classmethod
    def _extract_plan_image_material(cls, plan_context: dict[str, Any]) -> list[dict[str, Any]]:
        raw_payload = cls._json_object(plan_context.get("raw_json"))
        if not raw_payload:
            return []
        product_id = cls._first_text(plan_context.get("product_id"))
        creative_list = raw_payload.get("multi_product_creative_list")
        if isinstance(creative_list, list):
            entries = [item for item in creative_list if isinstance(item, dict)]
            if product_id:
                matched_entries = [
                    item for item in entries
                    if cls._first_text(item.get("product_id")) == product_id
                ]
                if matched_entries:
                    entries = matched_entries
            for item in entries:
                normalized = cls._normalize_image_material_payload(item.get("image_material"))
                if normalized:
                    return normalized
        programmatic = cls._json_object(raw_payload.get("programmatic_creative_media_list"))
        if programmatic:
            return cls._normalize_image_material_payload(programmatic.get("image_material"))
        return []

    @classmethod
    def _extract_plan_video_material_defaults(cls, plan_context: dict[str, Any]) -> dict[str, str]:
        raw_payload = cls._json_object(plan_context.get("raw_json"))
        if not raw_payload:
            return {}
        product_id = cls._first_text(plan_context.get("product_id"))
        candidate_entries: list[dict[str, Any]] = []
        creative_list = raw_payload.get("multi_product_creative_list")
        if isinstance(creative_list, list):
            entries = [item for item in creative_list if isinstance(item, dict)]
            if product_id:
                matched_entries = [
                    item for item in entries
                    if cls._first_text(item.get("product_id")) == product_id
                ]
                if matched_entries:
                    entries = matched_entries
            candidate_entries.extend(entries)
        programmatic = cls._json_object(raw_payload.get("programmatic_creative_media_list"))
        if programmatic:
            candidate_entries.append(programmatic)
        for item in candidate_entries:
            video_material = item.get("video_material")
            if not isinstance(video_material, list):
                continue
            for video_item in video_material:
                if not isinstance(video_item, dict):
                    continue
                defaults: dict[str, str] = {}
                image_mode = cls._first_text(video_item.get("image_mode"), video_item.get("imageMode"))
                if image_mode:
                    defaults["image_mode"] = image_mode
                video_cover_id = cls._first_text(video_item.get("video_cover_id"), video_item.get("videoCoverId"))
                if video_cover_id:
                    defaults["video_cover_id"] = video_cover_id
                if defaults:
                    return defaults
        return {}

    @staticmethod
    def _resolve_ffmpeg_executable() -> str:
        binary = shutil.which("ffmpeg")
        if binary:
            return binary
        try:
            import imageio_ffmpeg  # type: ignore

            resolved = str(imageio_ffmpeg.get_ffmpeg_exe() or "").strip()
        except Exception:  # noqa: BLE001
            resolved = ""
        if resolved:
            return resolved
        raise RuntimeError("未找到可用的 ffmpeg/imageio_ffmpeg，无法从视频截帧生成图片素材。")

    @classmethod
    def _extract_cover_frame_image(cls, video_path: Path, output_path: Path, image_mode: str = "") -> None:
        ffmpeg = cls._resolve_ffmpeg_executable()
        max_bytes = 1_450_000
        desired_mode = str(image_mode or "").strip().upper()
        seek_seconds = 1.0
        try:
            probe_result = probe_video_file(video_path)
            duration_seconds = float(getattr(probe_result, "duration_seconds", 0.0) or 0.0)
            if duration_seconds > 0:
                seek_seconds = max(0.0, min(1.0, duration_seconds / 2.0))
        except Exception:  # noqa: BLE001
            pass
        filter_args: list[str] = []
        if desired_mode == "SQUARE":
            filter_args = ["-vf", "crop='min(iw,ih)':'min(iw,ih)'"]
        attempts = [
            ["-ss", f"{seek_seconds:.2f}", "-i", str(video_path), *filter_args, "-frames:v", "1", "-q:v", "6", str(output_path)],
            ["-ss", f"{seek_seconds:.2f}", "-i", str(video_path), *filter_args, "-frames:v", "1", "-q:v", "10", str(output_path)],
            ["-ss", "0.00", "-i", str(video_path), *filter_args, "-frames:v", "1", "-q:v", "12", str(output_path)],
        ]
        last_error = ""
        for args in attempts:
            if output_path.exists():
                output_path.unlink()
            completed = subprocess.run(
                [ffmpeg, "-y", *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if (
                completed.returncode == 0
                and output_path.exists()
                and output_path.stat().st_size > 0
                and output_path.stat().st_size <= max_bytes
            ):
                return
            last_error = completed.stderr.strip() or completed.stdout.strip() or f"ffmpeg exit code {completed.returncode}"
            if output_path.exists() and output_path.stat().st_size > max_bytes:
                last_error = f"封面图超过图片上传限制: {output_path.stat().st_size} bytes"
        raise RuntimeError(f"从视频截取封面失败: {last_error}")

    def _build_cover_image_material(
        self,
        client: OceanEngineClient,
        advertiser_id: int,
        file_path: Path,
        plan_context: dict[str, Any],
        material_title: str,
        cache: dict[tuple[int, str], list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        cache_key = (int(advertiser_id), str(file_path))
        cached = cache.get(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]
        if not file_path.exists():
            return []
        generated_image_mode = "SQUARE"
        with tempfile.TemporaryDirectory(prefix="upload-cover-") as temp_dir:
            cover_path = Path(temp_dir) / f"{file_path.stem}_cover.jpg"
            self._extract_cover_frame_image(file_path, cover_path, generated_image_mode)
            image_upload = client.upload_image_file(
                advertiser_id=advertiser_id,
                material_name=f"{material_title}-cover",
                file_path=cover_path,
            )
        data = image_upload.get("data") or {}
        image_id = self._first_text(data.get("image_id"), data.get("id"))
        if not image_id:
            return []
        image_material: list[dict[str, Any]] = [{"image_ids": [image_id], "image_mode": generated_image_mode}]
        cache[cache_key] = [dict(item) for item in image_material]
        return image_material

    @staticmethod
    def _append_upload_probe_summary(message: str, probe_summary: str) -> str:
        base = str(message or "").strip()
        summary = str(probe_summary or "").strip()
        if not summary:
            return base
        if summary in base:
            return base
        if not base:
            return summary
        return f"{base}; {summary}"

    @classmethod
    def _probe_upload_video(cls, file_row: dict[str, Any], file_path: Path) -> tuple[str, str]:
        material_name = str(file_row.get("original_name") or file_row.get("stored_name") or file_path.name)
        try:
            probe_result = probe_video_file(file_path)
        except VideoProbeError as exc:
            summary = f"\u89c6\u9891\u5143\u6570\u636e\u63a2\u6d4b\u5931\u8d25: {exc}"
            print(f"[upload-video-probe] {material_name} | {summary}", file=sys.stderr)
            return summary, ""
        summary = format_video_probe_summary(probe_result)
        print(f"[upload-video-probe] {material_name} | {summary}", file=sys.stderr)
        problems = validate_video_probe_for_upload(probe_result)
        if not problems:
            return summary, ""
        failure_message = (
            "\u89c6\u9891\u5143\u6570\u636e\u9884\u68c0\u5931\u8d25: "
            + "; ".join(problems)
            + ". "
            + summary
        )
        return summary, failure_message

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
        create_time = cls._extract_material_create_time(material_type, row)
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
            create_time,
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

    @staticmethod
    def _operator_keyword_map(
        operators: dict[int, dict[str, Any]],
        keywords: list[dict[str, Any]],
    ) -> dict[int, list[str]]:
        keyword_map: dict[int, set[str]] = {}
        for row in keywords:
            operator_id = int(row.get("user_id", 0) or 0)
            if operator_id not in operators:
                continue
            keyword_text = str(row.get("keyword") or "").strip()
            if not keyword_text:
                continue
            keyword_map.setdefault(operator_id, set()).add(keyword_text)
        return {
            operator_id: sorted(values)
            for operator_id, values in keyword_map.items()
            if values
        }

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
        configured_keywords_by_user = self._operator_keyword_map(operators, keywords)
        if not configured_keywords_by_user:
            return []
        groups: dict[int, dict[str, Any]] = {
            operator_id: {
                "operator_id": operator_id,
                "operator_name": str(operator["display_name"]),
                "operator_username": str(operator["username"]),
                "stat_cost": 0.0,
                "pay_amount": 0.0,
                "order_count": 0,
                "plan_ids": set(),
                "advertiser_ids": set(),
                "matched_keywords": set(),
                "configured_keywords": set(configured_keywords_by_user.get(operator_id, [])),
                "top_plan_name": "",
                "top_plan_orders": -1,
                "top_plan_pay_amount": -1.0,
            }
            for operator_id, operator in operators.items()
            if configured_keywords_by_user.get(operator_id)
        }
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
                        "configured_keywords": set(configured_keywords_by_user.get(operator_id, [])),
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
                    "keyword_count": len(group["configured_keywords"]),
                    "matched_keyword_count": len(group["matched_keywords"]),
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

    def _build_operator_rankings_from_materials(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        operators, keywords = self._active_operator_config()
        if not operators or not keywords:
            return []
        configured_keywords_by_user = self._operator_keyword_map(operators, keywords)
        if not configured_keywords_by_user:
            return []
        groups: dict[int, dict[str, Any]] = {
            operator_id: {
                "operator_id": operator_id,
                "operator_name": str(operator["display_name"]),
                "operator_username": str(operator["username"]),
                "stat_cost": 0.0,
                "pay_amount": 0.0,
                "total_pay_amount": 0.0,
                "settled_pay_amount": 0.0,
                "refund_amount_1h": 0.0,
                "order_count": 0,
                "settled_order_count": 0,
                "material_keys": set(),
                "plan_ids": set(),
                "advertiser_ids": set(),
                "matched_keywords": set(),
                "configured_keywords": set(configured_keywords_by_user.get(operator_id, [])),
                "has_refund_rate_1h": False,
                "top_material_name": "",
                "top_account_name": "",
                "top_material_orders": -1,
                "top_material_pay_amount": -1.0,
            }
            for operator_id, operator in operators.items()
            if configured_keywords_by_user.get(operator_id)
        }
        for row in items:
            matches = self._matched_operators_for_material(row, operators, keywords)
            if not matches:
                continue
            stat_cost = round(float(row.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(row.get("pay_amount", 0.0) or 0.0), 2)
            total_pay_amount = round(float(row.get("total_pay_amount", 0.0) or 0.0), 2)
            settled_pay_amount = round(float(row.get("settled_pay_amount", 0.0) or 0.0), 2)
            refund_amount_1h = round(float(row.get("refund_amount_1h", 0.0) or 0.0), 2)
            order_count = int(float(row.get("order_count", 0.0) or 0.0))
            settled_order_count = int(float(row.get("settled_order_count", 0.0) or 0.0))
            material_key = str(row.get("material_key") or "").strip()
            material_name = str(row.get("material_name") or "").strip()
            advertiser_ids = {int(item) for item in row.get("advertiser_ids", []) if int(item or 0)}
            plan_ids = {int(item) for item in row.get("plan_ids", []) if int(item or 0)}
            top_account_name = str(row.get("top_account_name") or "").strip()
            has_refund_metric = "refund_amount_1h" in row or "refund_rate_1h" in row
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
                        "total_pay_amount": 0.0,
                        "settled_pay_amount": 0.0,
                        "refund_amount_1h": 0.0,
                        "order_count": 0,
                        "settled_order_count": 0,
                        "material_keys": set(),
                        "plan_ids": set(),
                        "advertiser_ids": set(),
                        "matched_keywords": set(),
                        "configured_keywords": set(configured_keywords_by_user.get(operator_id, [])),
                        "has_refund_rate_1h": False,
                        "top_material_name": "",
                        "top_account_name": "",
                        "top_material_orders": -1,
                        "top_material_pay_amount": -1.0,
                    },
                )
                group["stat_cost"] = round(group["stat_cost"] + stat_cost, 2)
                group["pay_amount"] = round(group["pay_amount"] + pay_amount, 2)
                group["total_pay_amount"] = round(group["total_pay_amount"] + total_pay_amount, 2)
                group["settled_pay_amount"] = round(group["settled_pay_amount"] + settled_pay_amount, 2)
                group["refund_amount_1h"] = round(group["refund_amount_1h"] + refund_amount_1h, 2)
                group["order_count"] += order_count
                group["settled_order_count"] += settled_order_count
                if material_key:
                    group["material_keys"].add(material_key)
                group["plan_ids"].update(plan_ids)
                group["advertiser_ids"].update(advertiser_ids)
                group["matched_keywords"].update(match["matched_keywords"])
                group["has_refund_rate_1h"] = bool(group["has_refund_rate_1h"]) or has_refund_metric
                if (
                    order_count > group["top_material_orders"]
                    or (order_count == group["top_material_orders"] and pay_amount > group["top_material_pay_amount"])
                ):
                    group["top_material_name"] = material_name
                    group["top_account_name"] = top_account_name
                    group["top_material_orders"] = order_count
                    group["top_material_pay_amount"] = pay_amount

        rows: list[dict[str, Any]] = []
        for group in groups.values():
            stat_cost = round(float(group["stat_cost"] or 0.0), 2)
            pay_amount = round(float(group["pay_amount"] or 0.0), 2)
            total_pay_amount = round(float(group["total_pay_amount"] or 0.0), 2)
            settled_pay_amount = round(float(group["settled_pay_amount"] or 0.0), 2)
            refund_amount_1h = round(float(group["refund_amount_1h"] or 0.0), 2)
            order_count = int(group["order_count"] or 0)
            settled_order_count = int(group["settled_order_count"] or 0)
            settled_amount_rate = round(settled_pay_amount / total_pay_amount * 100.0, 2) if total_pay_amount > 0 else 0.0
            pay_order_cost = round(stat_cost / order_count, 2) if order_count > 0 else 0.0
            refund_rate_1h = (
                round(refund_amount_1h / total_pay_amount * 100.0, 2)
                if total_pay_amount > 0 and bool(group["has_refund_rate_1h"])
                else None
            )
            rows.append(
                {
                    "operator_id": group["operator_id"],
                    "operator_name": group["operator_name"],
                    "operator_username": group["operator_username"],
                    "stat_cost": stat_cost,
                    "pay_amount": pay_amount,
                    "total_pay_amount": total_pay_amount,
                    "settled_pay_amount": settled_pay_amount,
                    "refund_amount_1h": refund_amount_1h,
                    "refund_rate_1h": refund_rate_1h,
                    "order_count": order_count,
                    "settled_order_count": settled_order_count,
                    "material_count": len(group["material_keys"]),
                    "plan_count": len(group["plan_ids"]),
                    "advertiser_count": len(group["advertiser_ids"]),
                    "keyword_count": len(group["configured_keywords"]),
                    "matched_keyword_count": len(group["matched_keywords"]),
                    "top_material_name": group["top_material_name"],
                    "top_account_name": group["top_account_name"],
                    "roi": round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                    "settled_roi": round(settled_pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                    "pay_order_cost": pay_order_cost,
                    "settled_amount_rate": settled_amount_rate,
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
                    "create_time": str(row.get("create_time") or "").strip(),
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
                    "top_anchor_name": str(row.get("top_anchor_name") or row.get("anchor_name") or "").strip(),
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
            row_create_time = str(row.get("create_time") or "").strip()
            if row_create_time and (
                not str(group.get("create_time") or "").strip()
                or row_create_time < str(group.get("create_time") or "").strip()
            ):
                group["create_time"] = row_create_time
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
                group["top_anchor_name"] = str(row.get("top_anchor_name") or row.get("anchor_name") or "").strip()

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
                    "create_time": str(group.get("create_time") or ""),
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
                    "top_anchor_name": str(group.get("top_anchor_name") or ""),
                    "roi": roi,
                    "settled_roi": settled_roi,
                    "pay_order_cost": pay_order_cost,
                    "settled_amount_rate": settled_amount_rate,
                    "product_info_text": "",
                    "overall_show_count": 0,
                    "overall_click_count": 0,
                    "overall_ctr": 0.0,
                }
            )
        material_rows.sort(
            key=lambda item: (
                str(item.get("create_time") or ""),
                int(item["order_count"]),
                float(item["pay_amount"]),
                float(item["roi"]),
                float(item["stat_cost"]),
            ),
            reverse=True,
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
                    str(group.get("create_time") or ""),
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
        requested_keys = {str(item or "").strip() for item in material_keys if str(item or "").strip()}
        if not requested_keys:
            return {}
        preview_map: dict[str, dict[str, str]] = {}
        for table_name in ("material_rollups", "material_snapshots"):
            rows = conn.execute(
                f"""
                SELECT material_key, video_id, cover_url, aweme_item_id, video_url
                FROM {table_name}
                WHERE snapshot_time = (SELECT MAX(snapshot_time) FROM {table_name})
                ORDER BY material_key ASC
                """
            ).fetchall()
            for raw_row in rows:
                row = dict(raw_row)
                material_key = str(row.get("material_key") or "").strip()
                if not material_key or material_key not in requested_keys:
                    continue
                preview = preview_map.setdefault(material_key, self._empty_material_preview_fields())
                self._merge_material_preview_fields(preview, row)
        return {
            key: value
            for key, value in preview_map.items()
            if self._material_preview_available(value) or str(value.get("video_id") or "").strip()
        }

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

    def _sanitize_material_preview_fields_for_payload(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not items:
            return items
        sanitized_items: list[dict[str, Any]] = []
        for raw_item in items:
            item = dict(raw_item)
            cover_url = self._normalize_media_url(item.get("cover_url"))
            video_url = self._normalize_media_url(item.get("video_url"))
            item["cover_url"] = self._coerce_public_preview_cover_url(cover_url)
            item["video_url"] = (
                video_url
                if self._is_public_preview_video_url(video_url) and not self._needs_preview_video_redirect_resolution(video_url)
                else ""
            )
            item["preview_available"] = bool(
                item["cover_url"]
                or item["video_url"]
                or str(item.get("aweme_item_id") or "").strip()
                or str(item.get("video_id") or "").strip()
                or str(item.get("material_id") or "").strip()
                or str(item.get("material_key") or "").strip()
            )
            sanitized_items.append(item)
        return sanitized_items

    @staticmethod
    def _preview_url_expires_at(url: str) -> int:
        text = str(url or "").strip()
        if not text:
            return 0
        try:
            query = parse_qs(urlsplit(text).query)
        except ValueError:
            return 0
        values = query.get("x-expires") or query.get("expires") or []
        if not values:
            return 0
        raw_value = str(values[0] or "").strip()
        return int(raw_value) if raw_value.isdigit() else 0

    @classmethod
    def _preview_url_needs_refresh(cls, url: str, *, leeway_seconds: int = 300) -> bool:
        text = str(url or "").strip()
        if not text:
            return True
        expires_at = cls._preview_url_expires_at(text)
        if expires_at <= 0:
            return False
        return expires_at <= int(time.time()) + max(leeway_seconds, 0)

    @staticmethod
    def _normalize_media_url(url: Any) -> str:
        text = str(url or "").strip()
        if text.startswith("//"):
            return f"https:{text}"
        return text

    @classmethod
    def _coerce_public_preview_cover_url(cls, url: Any) -> str:
        text = cls._normalize_media_url(url)
        if not text:
            return ""
        if cls._is_public_preview_cover_url(text):
            return text
        try:
            parsed = urlsplit(text)
        except ValueError:
            return ""
        host = str(parsed.netloc or "").strip().lower()
        if not host.endswith("creativityeco.com"):
            return ""
        host_prefix = host.split(".", 1)[0]
        cdn_prefix = host_prefix.split("-", 1)[0] if host_prefix.startswith("p") else "p3"
        path = str(parsed.path or "").strip()
        if not path:
            return ""
        path = re.sub(r"~tplv-[^.]+\.image$", "~tplv-noop.image", path)
        if "~tplv-" not in path and path.endswith(".image"):
            path = f"{path[:-6]}~tplv-noop.image"
        converted = urlunsplit(("https", f"{cdn_prefix}.douyinpic.com", path, "", ""))
        return converted if cls._is_public_preview_cover_url(converted) else ""

    @staticmethod
    def _preview_proxy_signature(target_url: str, expires_at: int) -> str:
        payload = f"{int(expires_at)}:{str(target_url or '').strip()}".encode("utf-8")
        return hmac.new(str(SESSION_SECRET or "preview-proxy").encode("utf-8"), payload, hashlib.sha256).hexdigest()

    @classmethod
    def _preview_proxy_allowed(cls, target_url: Any) -> bool:
        text = cls._normalize_media_url(target_url)
        if not text:
            return False
        return cls._needs_preview_video_redirect_resolution(text) or cls._is_internal_preview_video_url(text)

    def build_material_preview_proxy_url(self, target_url: Any, expires_in_seconds: int = 3600) -> str:
        normalized_url = self._normalize_media_url(target_url)
        if not self._preview_proxy_allowed(normalized_url):
            return ""
        expires_at = int(time.time()) + max(int(expires_in_seconds or 0), 60)
        signature = self._preview_proxy_signature(normalized_url, expires_at)
        encoded_target = quote(normalized_url, safe="")
        return f"/api/material-preview-stream?target={encoded_target}&expires={expires_at}&sig={signature}"

    def resolve_material_preview_proxy_target(self, target: str, expires: int, sig: str) -> str:
        normalized_target = self._normalize_media_url(unquote(str(target or "").strip()))
        if not normalized_target or not self._preview_proxy_allowed(normalized_target):
            raise ValueError("preview proxy target is not allowed")
        expires_at = int(expires or 0)
        if expires_at <= int(time.time()):
            raise ValueError("preview proxy url expired")
        expected_sig = self._preview_proxy_signature(normalized_target, expires_at)
        if not secrets.compare_digest(str(sig or "").strip(), expected_sig):
            raise ValueError("preview proxy signature invalid")
        return normalized_target

    @classmethod
    def _is_internal_preview_video_url(cls, url: Any) -> bool:
        text = cls._normalize_media_url(url)
        if not text:
            return False
        try:
            parsed = urlsplit(text)
        except ValueError:
            return False
        host = str(parsed.netloc or "").strip().lower()
        return host in {"localhost", "127.0.0.1"} or host.endswith(".local")

    @classmethod
    def _is_public_preview_cover_url(cls, url: Any) -> bool:
        text = cls._normalize_media_url(url)
        if not text:
            return False
        try:
            parsed = urlsplit(text)
        except ValueError:
            return False
        host = str(parsed.netloc or "").strip().lower()
        if parsed.scheme not in {"http", "https"} or not host:
            return False
        # creativityeco signed cover URLs are blocked for direct browser access.
        return not host.endswith("creativityeco.com")

    @classmethod
    def _is_public_preview_video_url(cls, url: Any) -> bool:
        text = cls._normalize_media_url(url)
        if not text:
            return False
        try:
            parsed = urlsplit(text)
        except ValueError:
            return False
        host = str(parsed.netloc or "").strip().lower()
        if parsed.scheme not in {"http", "https"} or not host:
            return False
        if cls._is_internal_preview_video_url(text):
            return False
        # cc.oceanengine.com is only a platform preview address, not a direct public file.
        return not host.endswith("cc.oceanengine.com")

    @classmethod
    def _needs_preview_video_redirect_resolution(cls, url: Any) -> bool:
        text = cls._normalize_media_url(url)
        if not text:
            return False
        try:
            parsed = urlsplit(text)
        except ValueError:
            return False
        host = str(parsed.netloc or "").strip().lower()
        return host.endswith("cc.oceanengine.com")

    @classmethod
    def _preferred_video_url_from_values(cls, *values: Any) -> str:
        candidates: list[str] = []
        seen: set[str] = set()
        for value in values:
            if isinstance(value, (list, tuple, set)):
                nested = list(value)
            else:
                nested = [value]
            for item in nested:
                text = cls._normalize_media_url(item)
                if not text or text in seen:
                    continue
                seen.add(text)
                candidates.append(text)
        for text in candidates:
            if cls._is_public_preview_video_url(text):
                return text
        return candidates[0] if candidates else ""

    def _resolve_preview_video_url(self, url: Any, *, timeout: int = 20) -> str:
        text = self._normalize_media_url(url)
        if not text:
            return ""
        if not self._needs_preview_video_redirect_resolution(text):
            return text
        now_ts = time.time()
        cached = self._preview_video_resolve_cache.get(text)
        if cached and now_ts - float(cached.get("_cached_at", 0.0)) < PREVIEW_VIDEO_RESOLVE_CACHE_SECONDS:
            cached_url = self._normalize_media_url(cached.get("resolved_url"))
            if cached_url and not self._preview_url_needs_refresh(cached_url, leeway_seconds=60):
                return cached_url
        request = urllib.request.Request(
            text,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Range": "bytes=0-0",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                resolved_url = self._normalize_media_url(response.geturl())
                content_type = str(response.headers.get("Content-Type") or "").strip().lower()
                response.read(1)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError):
            return text
        if not resolved_url or not self._is_public_preview_video_url(resolved_url):
            return text
        if content_type and not content_type.startswith("video/"):
            return text
        self._preview_video_resolve_cache[text] = {
            "_cached_at": now_ts,
            "resolved_url": resolved_url,
        }
        return resolved_url

    @classmethod
    def _video_url_candidates_from_payload(cls, payload: Any) -> list[str]:
        if not isinstance(payload, dict):
            return []
        values: list[Any] = []
        for key in (
            "video_url",
            "videoUrl",
            "url",
            "play_url",
            "playUrl",
            "download_url",
            "downloadUrl",
            "download_url_https",
            "downloadUrlHttps",
            "material_url",
            "materialUrl",
            "origin_url",
            "originUrl",
            "file_url",
            "fileUrl",
        ):
            if payload.get(key) not in (None, ""):
                values.append(payload.get(key))
        return [text for text in [cls._preferred_video_url_from_values(values)] if text]

    @staticmethod
    def _material_preview_refresh_cache_key(
        customer_center_id: str,
        advertiser_id: int,
        ad_id: int,
        material_type: str,
    ) -> str:
        return ":".join(
            [
                str(customer_center_id or "").strip(),
                str(int(advertiser_id or 0)),
                str(int(ad_id or 0)),
                str(material_type or "").strip().upper(),
            ]
        )

    def _plan_material_rows_for_preview_refresh(
        self,
        customer_center_id: str,
        advertiser_id: int,
        ad_id: int,
        material_type: str,
    ) -> list[dict[str, Any]]:
        cache_key = self._material_preview_refresh_cache_key(customer_center_id, advertiser_id, ad_id, material_type)
        now_ts = time.time()
        cached = self._material_preview_refresh_cache.get(cache_key)
        if cached and now_ts - float(cached.get("_cached_at", 0.0)) < MATERIAL_PREVIEW_REFRESH_CACHE_SECONDS:
            return [dict(row) for row in cached.get("rows", [])]
        client = self._build_scoped_customer_center_client(customer_center_id)
        rows = client.list_plan_materials(
            int(advertiser_id),
            int(ad_id),
            {"material_type": str(material_type or "").strip().upper()},
        )
        normalized_rows = [dict(row) for row in rows if isinstance(row, dict)]
        self._material_preview_refresh_cache[cache_key] = {
            "_cached_at": now_ts,
            "rows": normalized_rows,
        }
        return [dict(row) for row in normalized_rows]

    @classmethod
    def _material_preview_candidate_indexes(
        cls,
        rows: list[dict[str, Any]],
        material_type: str,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        indexes = {
            "material_id": {},
            "material_key": {},
            "video_id": {},
            "aweme_item_id": {},
        }
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_material_info = cls._json_object(row.get("material_info"))
            resolved_material_type = str(
                row.get("material_type")
                or raw_material_info.get("material_type")
                or material_type
                or "VIDEO"
            ).strip().upper()
            identity = cls._extract_material_identity(resolved_material_type, row)
            preview = cls._extract_material_preview(resolved_material_type, row)
            if not cls._material_preview_available(preview):
                continue
            candidate = {
                "material_type": resolved_material_type,
                "identity": identity,
                "preview": preview,
            }
            material_id = cls._numeric_material_id_text(identity.get("material_id"))
            if material_id and material_id not in indexes["material_id"]:
                indexes["material_id"][material_id] = candidate
            material_key = str(identity.get("material_key") or "").strip()
            if material_key and material_key not in indexes["material_key"]:
                indexes["material_key"][material_key] = candidate
            video_id = str(identity.get("video_id") or "").strip()
            if video_id and video_id not in indexes["video_id"]:
                indexes["video_id"][video_id] = candidate
            aweme_item_id = str(preview.get("aweme_item_id") or "").strip()
            if aweme_item_id and aweme_item_id not in indexes["aweme_item_id"]:
                indexes["aweme_item_id"][aweme_item_id] = candidate
        return indexes

    @classmethod
    def _match_refreshed_material_preview(
        cls,
        item: dict[str, Any],
        source: dict[str, Any],
        indexes: dict[str, dict[str, dict[str, Any]]],
    ) -> dict[str, Any] | None:
        material_id = cls._numeric_material_id_text(source.get("material_id"), item.get("material_id"))
        if material_id:
            candidate = indexes["material_id"].get(material_id)
            if candidate:
                return candidate
        video_id = cls._first_text(source.get("video_id"), item.get("video_id"))
        if video_id:
            candidate = indexes["video_id"].get(video_id)
            if candidate:
                return candidate
        aweme_item_id = cls._first_text(source.get("aweme_item_id"), item.get("aweme_item_id"))
        if aweme_item_id:
            candidate = indexes["aweme_item_id"].get(aweme_item_id)
            if candidate:
                return candidate
        material_key = cls._first_text(source.get("material_key"), item.get("material_key"))
        if material_key:
            return indexes["material_key"].get(material_key)
        return None

    def _refresh_stale_material_previews(
        self,
        items: list[dict[str, Any]],
        start_date: str,
        end_date: str,
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
        *,
        search_all_customer_centers: bool = False,
    ) -> list[dict[str, Any]]:
        if not items:
            return items
        refresh_targets: dict[tuple[str, int, int, str], list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        current_customer_center_id = self._current_customer_center_id()
        for item in items:
            material_type = str(item.get("material_type") or "VIDEO").strip().upper()
            cover_needs_refresh = self._preview_url_needs_refresh(str(item.get("cover_url") or ""))
            video_needs_refresh = self._preview_url_needs_refresh(str(item.get("video_url") or ""))
            if material_type == "VIDEO":
                should_refresh = video_needs_refresh or cover_needs_refresh
            else:
                should_refresh = cover_needs_refresh
            if not should_refresh:
                continue
            source = self._resolve_material_curve_source(
                item,
                start_date,
                end_date,
                snapshot_time,
                allowed_advertiser_ids,
                search_all_customer_centers=search_all_customer_centers,
            )
            if not source:
                continue
            customer_center_id = str(source.get("customer_center_id") or current_customer_center_id).strip()
            advertiser_id = int(source.get("advertiser_id", 0) or 0)
            ad_id = int(source.get("ad_id", 0) or 0)
            material_type = str(source.get("material_type") or item.get("material_type") or "VIDEO").strip().upper()
            if not customer_center_id or advertiser_id <= 0 or ad_id <= 0 or material_type not in PLAN_MATERIAL_TYPES:
                continue
            refresh_targets.setdefault(
                (customer_center_id, advertiser_id, ad_id, material_type),
                [],
            ).append((item, source))
        if not refresh_targets:
            return items

        refreshed_rows: dict[tuple[str, int, int, str], list[dict[str, Any]]] = {}
        with ThreadPoolExecutor(max_workers=min(len(refresh_targets), 4)) as executor:
            future_map = {
                executor.submit(
                    self._plan_material_rows_for_preview_refresh,
                    customer_center_id,
                    advertiser_id,
                    ad_id,
                    material_type,
                ): (customer_center_id, advertiser_id, ad_id, material_type)
                for customer_center_id, advertiser_id, ad_id, material_type in refresh_targets
            }
            for future in as_completed(future_map):
                group_key = future_map[future]
                try:
                    refreshed_rows[group_key] = future.result()
                except Exception:
                    refreshed_rows[group_key] = []

        for group_key, targets in refresh_targets.items():
            customer_center_id, advertiser_id, ad_id, material_type = group_key
            candidate_rows = refreshed_rows.get(group_key) or []
            if not candidate_rows:
                continue
            indexes = self._material_preview_candidate_indexes(candidate_rows, material_type)
            for item, source in targets:
                candidate = self._match_refreshed_material_preview(item, source, indexes)
                if not candidate:
                    continue
                preview = candidate.get("preview") or {}
                identity = candidate.get("identity") or {}
                cover_url = str(preview.get("cover_url") or "").strip()
                if cover_url:
                    item["cover_url"] = cover_url
                aweme_item_id = str(preview.get("aweme_item_id") or "").strip()
                if aweme_item_id:
                    item["aweme_item_id"] = aweme_item_id
                video_url = str(preview.get("video_url") or "").strip()
                if video_url:
                    item["video_url"] = video_url
                video_id = str(identity.get("video_id") or "").strip()
                if video_id:
                    item["video_id"] = video_id
                item["_preview_refreshed"] = True
                item["_preview_refresh_customer_center_id"] = customer_center_id
                item["_preview_refresh_advertiser_id"] = advertiser_id
                item["_preview_refresh_ad_id"] = ad_id
        return items

    def _apply_material_top_anchor_names(
        self,
        conn: Any,
        items: list[dict[str, Any]],
        snapshot_times: list[str],
    ) -> list[dict[str, Any]]:
        if not items or not snapshot_times:
            return items
        unresolved_keys = {
            (
                str(item.get("top_account_name") or "").strip(),
                str(item.get("top_plan_name") or "").strip(),
            )
            for item in items
            if not str(item.get("top_anchor_name") or "").strip()
            and str(item.get("top_account_name") or "").strip()
            and str(item.get("top_plan_name") or "").strip()
        }
        if not unresolved_keys:
            return items
        placeholders = ",".join("?" for _ in snapshot_times)
        customer_center_id = self._current_customer_center_id()
        rows = conn.execute(
            f"""
            SELECT snapshot_time, advertiser_name, ad_name, anchor_name
            FROM plan_snapshots
            WHERE snapshot_time IN ({placeholders})
              AND customer_center_id = ?
              AND COALESCE(anchor_name, '') <> ''
            ORDER BY snapshot_time DESC, ad_id DESC
            """,
            [*snapshot_times, customer_center_id],
        ).fetchall()
        anchor_map: dict[tuple[str, str], str] = {}
        for row in rows:
            row = dict(row)
            key = (
                str(row.get("advertiser_name") or "").strip(),
                str(row.get("ad_name") or "").strip(),
            )
            if key not in unresolved_keys or key in anchor_map:
                continue
            anchor_name = str(row.get("anchor_name") or "").strip()
            if anchor_name:
                anchor_map[key] = anchor_name
        if not anchor_map:
            return items
        enriched_items: list[dict[str, Any]] = []
        for item in items:
            enriched = dict(item)
            if not str(enriched.get("top_anchor_name") or "").strip():
                enriched["top_anchor_name"] = anchor_map.get(
                    (
                        str(enriched.get("top_account_name") or "").strip(),
                        str(enriched.get("top_plan_name") or "").strip(),
                    ),
                    "",
                )
            enriched_items.append(enriched)
        return enriched_items

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
                group["top_anchor_name"] = str(group.get("top_anchor_name") or row.get("top_anchor_name") or row.get("anchor_name") or "")
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
            row_create_time = str(row.get("create_time") or "").strip()
            if row_create_time and (
                not str(group.get("create_time") or "").strip()
                or row_create_time < str(group.get("create_time") or "").strip()
            ):
                group["create_time"] = row_create_time
            if (
                order_count > int(group.get("_top_plan_orders", -1))
                or (
                    order_count == int(group.get("_top_plan_orders", -1))
                    and pay_amount > float(group.get("_top_plan_pay_amount", -1.0))
                )
            ):
                group["top_plan_name"] = str(row.get("top_plan_name") or "")
                group["top_account_name"] = str(row.get("top_account_name") or "")
                group["top_anchor_name"] = str(row.get("top_anchor_name") or row.get("anchor_name") or "")
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
                    "create_time": str(group.get("create_time") or ""),
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
                    "top_anchor_name": str(group.get("top_anchor_name") or ""),
                    "roi": round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                    "settled_roi": round(settled_pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                    "pay_order_cost": round(stat_cost / order_count, 2) if order_count > 0 else 0.0,
                    "settled_amount_rate": round(settled_pay_amount / total_pay_amount * 100.0, 2) if total_pay_amount > 0 else 0.0,
                    "product_info_text": "",
                    "overall_show_count": 0,
                    "overall_click_count": 0,
                    "overall_ctr": 0.0,
                }
            )
        rankings.sort(
            key=lambda item: (
                str(item.get("create_time") or ""),
                int(item["order_count"]),
                float(item["pay_amount"]),
                float(item["roi"]),
                float(item["stat_cost"]),
            ),
            reverse=True,
        )
        return rankings

    def _filter_material_rows_by_create_time_window(
        self,
        rows: list[dict[str, Any]],
        start_dt: datetime | None,
        end_dt: datetime | None,
        tz_name: str,
    ) -> list[dict[str, Any]]:
        if start_dt is None or end_dt is None:
            return rows
        tz = ZoneInfo(str(tz_name or TIMEZONE))
        start_text = start_dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
        end_text = end_dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
        filtered_rows: list[dict[str, Any]] = []
        for raw_row in rows:
            row = dict(raw_row)
            create_time = self._normalize_datetime_text(row.get("create_time"))
            if not create_time:
                continue
            row["create_time"] = create_time
            if start_text <= create_time <= end_text:
                filtered_rows.append(row)
        return filtered_rows

    def _apply_material_snapshot_context(
        self,
        conn: Any,
        items: list[dict[str, Any]],
        snapshot_times: list[str],
        allowed_advertiser_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        if not items or not snapshot_times:
            return items
        placeholders = ",".join("?" for _ in snapshot_times)
        clauses = [f"snapshot_time IN ({placeholders})"]
        params: list[Any] = list(snapshot_times)
        if allowed_advertiser_ids:
            allowed = sorted(int(item) for item in allowed_advertiser_ids if int(item or 0))
            if allowed:
                clauses.append(f"advertiser_id IN ({','.join('?' for _ in allowed)})")
                params.extend(allowed)
        clauses.append("customer_center_id = ?")
        params.append(self._current_customer_center_id())
        rows = conn.execute(
            f"""
            SELECT material_key, product_show_count, product_click_count, raw_json
            FROM material_snapshots
            WHERE {" AND ".join(clauses)}
            """,
            params,
        ).fetchall()
        context_by_key: dict[str, dict[str, Any]] = {}
        for raw_row in rows:
            row = dict(raw_row)
            material_key = str(row.get("material_key") or "").strip()
            if not material_key:
                continue
            group = context_by_key.setdefault(
                material_key,
                {
                    "product_show_count": 0,
                    "product_click_count": 0,
                    "product_names": [],
                },
            )
            group["product_show_count"] += int(row.get("product_show_count", 0) or 0)
            group["product_click_count"] += int(row.get("product_click_count", 0) or 0)
            for name in self._extract_material_product_names(row.get("raw_json")):
                if name not in group["product_names"]:
                    group["product_names"].append(name)
        for item in items:
            context = context_by_key.get(str(item.get("material_key") or "").strip())
            if not context:
                continue
            show_count = int(context.get("product_show_count", 0) or 0)
            click_count = int(context.get("product_click_count", 0) or 0)
            item["product_info_text"] = self._summarize_material_product_names(list(context.get("product_names") or []))
            item["overall_show_count"] = show_count
            item["overall_click_count"] = click_count
            item["overall_ctr"] = round(click_count / show_count * 100.0, 2) if show_count > 0 else 0.0
        return items

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
        next_payload["operators"] = [dict(item) for item in payload.get("operators", [])]
        next_payload["summary"]["operator_count"] = len(next_payload["operators"])
        next_payload["summary"]["active_operator_count"] = sum(
            1 for item in next_payload["operators"] if float(item.get("stat_cost", 0.0) or 0.0) > 0
        )
        return next_payload

    def _apply_material_scope(self, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        if str(user.get("role") or "") != ROLE_OPERATOR:
            return payload
        next_payload = dict(payload)
        next_payload["items"] = self._filter_material_items_for_operator(payload.get("items", []), int(user.get("id", 0) or 0))
        return next_payload

    def _apply_comment_scope(self, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        if str(user.get("role") or "") != ROLE_OPERATOR:
            return payload
        user_id = int(user.get("id", 0) or 0)
        scoped_items = self._filter_material_items_for_operator(payload.get("items", []), user_id)
        account_map: dict[int, dict[str, Any]] = {}
        for row in scoped_items:
            advertiser_id = int(row.get("advertiser_id", 0) or 0)
            if not advertiser_id or advertiser_id in account_map:
                continue
            account_map[advertiser_id] = {
                "advertiser_id": advertiser_id,
                "advertiser_name": str(row.get("advertiser_name") or advertiser_id),
            }
        next_payload = dict(payload)
        next_payload["items"] = scoped_items
        next_payload["accounts"] = sorted(account_map.values(), key=lambda item: (str(item["advertiser_name"]), item["advertiser_id"]))
        meta = dict(next_payload.get("meta") or {})
        meta["visible_count"] = len(scoped_items)
        next_payload["meta"] = meta
        return next_payload

    @staticmethod
    def _comment_account_candidates(
        client: OceanEngineClient,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        accounts: list[dict[str, Any]] = []
        allowed = {int(item) for item in allowed_advertiser_ids} if allowed_advertiser_ids is not None else None
        for item in client.list_accounts():
            advertiser_id = int(item.get("advertiser_id") or item.get("account_id") or 0)
            if not advertiser_id:
                continue
            if allowed is not None and advertiser_id not in allowed:
                continue
            advertiser_name = str(
                item.get("advertiser_name")
                or item.get("account_name")
                or item.get("name")
                or advertiser_id
            ).strip()
            accounts.append(
                {
                    "advertiser_id": advertiser_id,
                    "advertiser_name": advertiser_name,
                }
            )
        accounts.sort(key=lambda item: (str(item["advertiser_name"]), int(item["advertiser_id"])))
        return accounts

    def _fetch_account_comments(
        self,
        client: OceanEngineClient,
        advertiser_id: int,
        advertiser_name: str,
        start_date: str,
        end_date: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        try:
            rows = client.list_comments(
                advertiser_id=advertiser_id,
                start_time=start_date,
                end_time=end_date,
                page_size=100,
            )
        except Exception as exc:  # noqa: BLE001
            return [], {
                "advertiser_id": int(advertiser_id),
                "advertiser_name": str(advertiser_name or advertiser_id),
                "error": str(exc),
            }

        items: list[dict[str, Any]] = []
        for row in rows:
            reply_count = int(float(row.get("reply_count", 0) or 0))
            like_count = int(float(row.get("like_count", 0) or 0))
            hide_status = str(row.get("hide_status") or "NOT_HIDE").strip().upper()
            level_type = str(row.get("level_type") or "").strip().upper()
            comment_type = str(row.get("comment_type") or "").strip().upper()
            material_id = str(row.get("material_id") or "").strip()
            promotion_id = str(row.get("promotion_id") or "").strip()
            item_payload = {
                "comment_id": str(row.get("comment_id") or "").strip(),
                "advertiser_id": int(advertiser_id),
                "advertiser_name": str(advertiser_name or advertiser_id),
                "text": str(row.get("text") or "").strip(),
                "reply_count": reply_count,
                "is_replied": reply_count > 0,
                "reply_status_text": "已回复" if reply_count > 0 else "未回复",
                "hide_status": hide_status,
                "hide_status_text": self._comment_hide_status_label(hide_status),
                "level_type": level_type,
                "level_type_text": self._comment_level_label(level_type),
                "comment_user_name": str(row.get("aweme_name") or "").strip(),
                "comment_user_id": str(row.get("aweme_id") or "").strip(),
                "create_time": str(row.get("create_time") or "").strip(),
                "reply_count_text": reply_count,
                "like_count": like_count,
                "item_title": str(row.get("item_title") or "").strip(),
                "video_owner_aweme_id": "",
                "comment_type": comment_type,
                "comment_type_text": self._comment_type_label(comment_type),
                "promotion_id": promotion_id,
                "promotion_name": "",
                "promotion_display_name": f"计划 {promotion_id}" if promotion_id else "-",
                "material_id": material_id,
                "material_name": "",
                "material_display_name": f"素材 {material_id}" if material_id else "-",
                "item_id": str(row.get("item_id") or "").strip(),
            }
            item_payload["material_name"] = item_payload["material_name"]
            items.append(item_payload)
        return items, None

    def _comment_plan_name_maps(
        self,
        conn: Any,
        advertiser_ids: set[int],
        promotion_ids: set[int],
    ) -> tuple[dict[tuple[int, int], str], dict[int, str]]:
        if not advertiser_ids or not promotion_ids:
            return {}, {}
        advertiser_placeholders = ",".join("?" for _ in advertiser_ids)
        promotion_placeholders = ",".join("?" for _ in promotion_ids)
        params: list[Any] = [*sorted(promotion_ids), *sorted(advertiser_ids), self._current_customer_center_id()]
        rows = conn.execute(
            f"""
            SELECT snapshot_time, advertiser_id, ad_id, ad_name
            FROM plan_snapshots
            WHERE ad_id IN ({promotion_placeholders})
              AND advertiser_id IN ({advertiser_placeholders})
              AND customer_center_id = ?
            ORDER BY snapshot_time DESC
            """,
            params,
        ).fetchall()
        exact: dict[tuple[int, int], str] = {}
        fallback: dict[int, str] = {}
        for row in rows:
            advertiser_id = int(row["advertiser_id"])
            ad_id = int(row["ad_id"])
            ad_name = str(row["ad_name"] or ad_id).strip()
            exact.setdefault((advertiser_id, ad_id), ad_name)
            fallback.setdefault(ad_id, ad_name)
        return exact, fallback

    def _comment_material_name_maps(
        self,
        conn: Any,
        advertiser_ids: set[int],
        material_ids: set[str],
    ) -> tuple[dict[tuple[int, str], str], dict[str, str]]:
        normalized_material_ids = sorted(str(item).strip() for item in material_ids if str(item).strip())
        if not advertiser_ids or not normalized_material_ids:
            return {}, {}
        advertiser_placeholders = ",".join("?" for _ in advertiser_ids)
        material_placeholders = ",".join("?" for _ in normalized_material_ids)
        params: list[Any] = [*normalized_material_ids, *sorted(advertiser_ids), self._current_customer_center_id()]
        rows = conn.execute(
            f"""
            SELECT snapshot_time, advertiser_id, material_id, material_name
            FROM material_snapshots
            WHERE material_id IN ({material_placeholders})
              AND advertiser_id IN ({advertiser_placeholders})
              AND customer_center_id = ?
              AND COALESCE(material_id, '') <> ''
            ORDER BY snapshot_time DESC
            """,
            params,
        ).fetchall()
        exact: dict[tuple[int, str], str] = {}
        fallback: dict[str, str] = {}
        for row in rows:
            advertiser_id = int(row["advertiser_id"])
            material_id = str(row["material_id"] or "").strip()
            material_name = str(row["material_name"] or material_id).strip()
            if not material_id:
                continue
            exact.setdefault((advertiser_id, material_id), material_name)
            fallback.setdefault(material_id, material_name)
        return exact, fallback

    @classmethod
    def _comment_record_from_item(
        cls,
        item: dict[str, Any],
        fetched_at: str,
        fallback_date: str = "",
    ) -> dict[str, Any]:
        create_time = cls._normalize_datetime_text(item.get("create_time"))
        return {
            "comment_id": str(item.get("comment_id") or "").strip(),
            "advertiser_id": int(item.get("advertiser_id", 0) or 0),
            "advertiser_name": str(item.get("advertiser_name") or item.get("advertiser_id") or "").strip(),
            "comment_date": create_time[:10] if len(create_time) >= 10 else str(fallback_date or "").strip(),
            "create_time": create_time,
            "text": str(item.get("text") or "").strip(),
            "reply_count": cls._safe_int(item.get("reply_count", 0)),
            "hide_status": str(item.get("hide_status") or "NOT_HIDE").strip().upper(),
            "level_type": str(item.get("level_type") or "").strip().upper(),
            "comment_user_name": str(item.get("comment_user_name") or "").strip(),
            "comment_user_id": str(item.get("comment_user_id") or "").strip(),
            "like_count": cls._safe_int(item.get("like_count", 0)),
            "item_title": str(item.get("item_title") or "").strip(),
            "comment_type": str(item.get("comment_type") or "").strip().upper(),
            "promotion_id": str(item.get("promotion_id") or "").strip(),
            "material_id": str(item.get("material_id") or "").strip(),
            "item_id": str(item.get("item_id") or "").strip(),
            "raw_json": cls._json_text(item if isinstance(item, dict) else {}),
            "fetched_at": str(fetched_at or "").strip(),
            "updated_at": str(fetched_at or "").strip(),
        }

    def _comment_item_from_record(self, row: dict[str, Any]) -> dict[str, Any]:
        reply_count = self._safe_int(row.get("reply_count", 0))
        hide_status = str(row.get("hide_status") or "NOT_HIDE").strip().upper()
        level_type = str(row.get("level_type") or "").strip().upper()
        comment_type = str(row.get("comment_type") or "").strip().upper()
        promotion_id = str(row.get("promotion_id") or "").strip()
        material_id = str(row.get("material_id") or "").strip()
        advertiser_id = int(row.get("advertiser_id", 0) or 0)
        advertiser_name = str(row.get("advertiser_name") or advertiser_id).strip()
        return {
            "comment_id": str(row.get("comment_id") or "").strip(),
            "advertiser_id": advertiser_id,
            "advertiser_name": advertiser_name,
            "text": str(row.get("text") or "").strip(),
            "reply_count": reply_count,
            "is_replied": reply_count > 0,
            "reply_status_text": "已回复" if reply_count > 0 else "未回复",
            "hide_status": hide_status,
            "hide_status_text": self._comment_hide_status_label(hide_status),
            "level_type": level_type,
            "level_type_text": self._comment_level_label(level_type),
            "comment_user_name": str(row.get("comment_user_name") or "").strip(),
            "comment_user_id": str(row.get("comment_user_id") or "").strip(),
            "create_time": self._normalize_datetime_text(row.get("create_time")),
            "reply_count_text": reply_count,
            "like_count": self._safe_int(row.get("like_count", 0)),
            "item_title": str(row.get("item_title") or "").strip(),
            "video_owner_aweme_id": "",
            "comment_type": comment_type,
            "comment_type_text": self._comment_type_label(comment_type),
            "promotion_id": promotion_id,
            "promotion_name": "",
            "promotion_display_name": f"计划 {promotion_id}" if promotion_id else "-",
            "material_id": material_id,
            "material_name": "",
            "material_display_name": f"素材 {material_id}" if material_id else "-",
            "item_id": str(row.get("item_id") or "").strip(),
        }

    @staticmethod
    def _comment_requested_dates(start_dt: datetime, end_dt: datetime) -> list[str]:
        current = start_dt.date()
        end_day = end_dt.date()
        items: list[str] = []
        while current <= end_day:
            items.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        return items

    @classmethod
    def _parse_normalized_datetime_text(cls, value: Any) -> datetime | None:
        text = cls._normalize_datetime_text(value)
        if not text:
            return None
        try:
            return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    @staticmethod
    def _comment_sync_ranges(sync_dates: list[str]) -> list[tuple[str, str]]:
        if not sync_dates:
            return []
        parsed_days = sorted(
            {
                datetime.strptime(str(item).strip(), "%Y-%m-%d").date()
                for item in sync_dates
                if str(item).strip()
            }
        )
        if not parsed_days:
            return []
        ranges: list[tuple[str, str]] = []
        start_day = parsed_days[0]
        end_day = parsed_days[0]
        for current_day in parsed_days[1:]:
            if current_day == end_day + timedelta(days=1):
                end_day = current_day
                continue
            ranges.append((start_day.strftime("%Y-%m-%d"), end_day.strftime("%Y-%m-%d")))
            start_day = current_day
            end_day = current_day
        ranges.append((start_day.strftime("%Y-%m-%d"), end_day.strftime("%Y-%m-%d")))
        return ranges

    def _comment_sync_state_map(
        self,
        conn: Any,
        advertiser_ids: set[int],
        sync_dates: list[str],
    ) -> dict[tuple[int, str], dict[str, Any]]:
        normalized_dates = [str(item).strip() for item in sync_dates if str(item).strip()]
        if not advertiser_ids or not normalized_dates:
            return {}
        advertiser_placeholders = ",".join("?" for _ in advertiser_ids)
        date_placeholders = ",".join("?" for _ in normalized_dates)
        params: list[Any] = [*normalized_dates, *sorted(advertiser_ids), self._current_customer_center_id()]
        rows = conn.execute(
            f"""
            SELECT advertiser_id, sync_date, advertiser_name, status, comment_count, last_attempt_at, last_success_at, error_message
            FROM comment_sync_states
            WHERE sync_date IN ({date_placeholders})
              AND advertiser_id IN ({advertiser_placeholders})
              AND customer_center_id = ?
            """,
            params,
        ).fetchall()
        return {
            (int(row["advertiser_id"]), str(row["sync_date"] or "").strip()): dict(row)
            for row in rows
        }

    def _should_sync_comment_date(
        self,
        state_row: dict[str, Any] | None,
        sync_date: str,
        hot_cutoff_date: str,
        now_local: datetime,
        force_refresh: bool = False,
    ) -> bool:
        if force_refresh:
            return True
        if not state_row:
            return True
        status = str(state_row.get("status") or "").strip().lower()
        last_success_at = self._parse_normalized_datetime_text(state_row.get("last_success_at"))
        last_attempt_at = self._parse_normalized_datetime_text(state_row.get("last_attempt_at"))
        if status != "ok":
            if last_attempt_at is None:
                return True
            return max((now_local - last_attempt_at).total_seconds(), 0.0) >= COMMENT_SYNC_ERROR_RETRY_SECONDS
        if sync_date >= hot_cutoff_date:
            if last_success_at is None:
                return True
            return max((now_local - last_success_at).total_seconds(), 0.0) >= COMMENT_SYNC_SUCCESS_TTL_SECONDS
        return False

    def _comment_sync_plans(
        self,
        conn: Any,
        accounts: list[dict[str, Any]],
        start_dt: datetime,
        end_dt: datetime,
        tz_name: str,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        requested_dates = self._comment_requested_dates(start_dt, end_dt)
        advertiser_ids = {int(item["advertiser_id"]) for item in accounts if int(item.get("advertiser_id", 0) or 0)}
        state_map = self._comment_sync_state_map(conn, advertiser_ids, requested_dates)
        now_local = datetime.now(ZoneInfo(tz_name)).replace(tzinfo=None)
        hot_cutoff_date = (now_local.date() - timedelta(days=max(COMMENT_INCREMENTAL_HOT_DAYS - 1, 0))).strftime(
            "%Y-%m-%d"
        )
        plans: list[dict[str, Any]] = []
        for account in accounts:
            advertiser_id = int(account.get("advertiser_id", 0) or 0)
            if not advertiser_id:
                continue
            advertiser_name = str(account.get("advertiser_name") or advertiser_id).strip()
            required_dates = [
                sync_date
                for sync_date in requested_dates
                if self._should_sync_comment_date(
                    state_map.get((advertiser_id, sync_date)),
                    sync_date,
                    hot_cutoff_date,
                    now_local,
                    force_refresh=force_refresh,
                )
            ]
            for range_start, range_end in self._comment_sync_ranges(required_dates):
                plans.append(
                    {
                        "advertiser_id": advertiser_id,
                        "advertiser_name": advertiser_name,
                        "start_date": range_start,
                        "end_date": range_end,
                    }
                )
        return plans

    def _comment_has_sync_coverage(
        self,
        conn: Any,
        advertiser_ids: set[int],
        sync_dates: list[str],
    ) -> bool:
        normalized_dates = [str(item).strip() for item in sync_dates if str(item).strip()]
        normalized_advertiser_ids = {int(item) for item in advertiser_ids if int(item or 0)}
        if not normalized_advertiser_ids or not normalized_dates:
            return True
        state_map = self._comment_sync_state_map(conn, normalized_advertiser_ids, normalized_dates)
        for advertiser_id in normalized_advertiser_ids:
            for sync_date in normalized_dates:
                if (advertiser_id, sync_date) not in state_map:
                    return False
        return True

    def _execute_comment_sync_plans(
        self,
        config: dict[str, Any],
        sync_plans: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not sync_plans:
            return {
                "sync_plan_count": 0,
                "synced_plan_count": 0,
                "synced_comment_count": 0,
                "error_count": 0,
                "errors": [],
            }

        client = self.build_client(config)
        client.get_access_token()
        max_workers = max(1, min(int(config.get("comment_max_workers", 4) or 4), len(sync_plans)))
        errors: list[dict[str, Any]] = []
        sync_results: list[tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map = {
                pool.submit(
                    self._fetch_account_comments,
                    client,
                    int(plan["advertiser_id"]),
                    str(plan["advertiser_name"]),
                    str(plan["start_date"]),
                    str(plan["end_date"]),
                ): plan
                for plan in sync_plans
            }
            for future in as_completed(future_map):
                plan = future_map[future]
                account_items, error_payload = future.result()
                sync_results.append((plan, account_items, error_payload))
                if error_payload:
                    errors.append(error_payload)

        with self.db() as conn:
            for plan, account_items, error_payload in sync_results:
                attempted_at = now_text(config["timezone"])
                if error_payload:
                    self._persist_comment_sync_error(
                        conn,
                        int(plan["advertiser_id"]),
                        str(plan["advertiser_name"]),
                        str(plan["start_date"]),
                        str(plan["end_date"]),
                        str(error_payload.get("error") or ""),
                        attempted_at,
                    )
                    continue
                records = [
                    self._comment_record_from_item(item, attempted_at, str(plan["start_date"]))
                    for item in account_items
                    if str(item.get("comment_id") or "").strip()
                ]
                self._persist_comment_sync_success(
                    conn,
                    int(plan["advertiser_id"]),
                    str(plan["advertiser_name"]),
                    str(plan["start_date"]),
                    str(plan["end_date"]),
                    records,
                    attempted_at,
                )
        self._clear_comment_caches()
        return {
            "sync_plan_count": len(sync_plans),
            "synced_plan_count": sum(1 for _plan, _items, error_payload in sync_results if error_payload is None),
            "synced_comment_count": sum(
                len(account_items) for _plan, account_items, error_payload in sync_results if error_payload is None
            ),
            "error_count": len(errors),
            "errors": errors,
        }

    def sync_comments_for_dates(
        self,
        start_date: str,
        end_date: str,
        advertiser_id: int | None = None,
        allowed_advertiser_ids: set[int] | list[int] | tuple[int, ...] | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        normalized_start_date = str(start_date or "").strip()
        normalized_end_date = str(end_date or "").strip()
        if not normalized_start_date or not normalized_end_date:
            raise ValueError("comment sync start_date and end_date are required")
        try:
            start_dt = datetime.strptime(normalized_start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(normalized_end_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("comment sync dates must use YYYY-MM-DD") from exc
        if start_dt > end_dt:
            raise ValueError("comment sync start_date must be <= end_date")

        normalized_allowed = self._normalize_allowed_advertiser_ids(allowed_advertiser_ids)
        selected_advertiser_id = int(advertiser_id or 0)
        lock_key = self._comment_sync_dedupe_key(
            normalized_start_date,
            normalized_end_date,
            advertiser_id=selected_advertiser_id,
            allowed_advertiser_ids=normalized_allowed,
        )
        with self._distributed_runtime_lock(
            lock_key,
            timeout_seconds=max(COMMENT_SYNC_SUCCESS_TTL_SECONDS, 300),
        ) as acquired:
            if not acquired:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "comment sync already running",
                    "start_date": normalized_start_date,
                    "end_date": normalized_end_date,
                    "advertiser_id": selected_advertiser_id,
                    "sync_plan_count": 0,
                    "synced_plan_count": 0,
                    "synced_comment_count": 0,
                    "error_count": 0,
                    "errors": [],
                }

            config = self.read_config()
            all_accounts = self.latest_account_catalog(normalized_allowed)
            accounts = list(all_accounts)
            if selected_advertiser_id:
                accounts = [item for item in accounts if int(item["advertiser_id"]) == selected_advertiser_id]
            if not accounts:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "no comment accounts available",
                    "start_date": normalized_start_date,
                    "end_date": normalized_end_date,
                    "advertiser_id": selected_advertiser_id,
                    "sync_plan_count": 0,
                    "synced_plan_count": 0,
                    "synced_comment_count": 0,
                    "error_count": 0,
                    "errors": [],
                }

            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            with self.db() as conn:
                sync_plans = self._comment_sync_plans(
                    conn,
                    accounts,
                    start_dt,
                    end_dt,
                    config["timezone"],
                    force_refresh=force_refresh,
                )
            if not sync_plans:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "comment sync already up to date",
                    "start_date": normalized_start_date,
                    "end_date": normalized_end_date,
                    "advertiser_id": selected_advertiser_id,
                    "sync_plan_count": 0,
                    "synced_plan_count": 0,
                    "synced_comment_count": 0,
                    "error_count": 0,
                    "errors": [],
                }

            sync_result = self._execute_comment_sync_plans(config, sync_plans)
            return {
                "ok": True,
                "skipped": False,
                "reason": "",
                "start_date": normalized_start_date,
                "end_date": normalized_end_date,
                "advertiser_id": selected_advertiser_id,
                **sync_result,
            }

    def _persist_comment_sync_success(
        self,
        conn: Any,
        advertiser_id: int,
        advertiser_name: str,
        start_date: str,
        end_date: str,
        records: list[dict[str, Any]],
        attempted_at: str,
    ) -> None:
        customer_center_id = self._current_customer_center_id()
        conn.execute(
            """
            DELETE FROM comment_records
            WHERE customer_center_id = ?
              AND advertiser_id = ?
              AND comment_date >= ?
              AND comment_date <= ?
            """,
            (customer_center_id, int(advertiser_id), str(start_date).strip(), str(end_date).strip()),
        )
        if records:
            conn.executemany(
                """
                INSERT INTO comment_records (
                    customer_center_id, advertiser_id, comment_id, comment_date, create_time, advertiser_name, text,
                    reply_count, hide_status, level_type, comment_user_name, comment_user_id, like_count, item_title,
                    comment_type, promotion_id, material_id, item_id, raw_json, fetched_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (customer_center_id, advertiser_id, comment_id) DO UPDATE SET
                    comment_date = excluded.comment_date,
                    create_time = excluded.create_time,
                    advertiser_name = excluded.advertiser_name,
                    text = excluded.text,
                    reply_count = excluded.reply_count,
                    hide_status = excluded.hide_status,
                    level_type = excluded.level_type,
                    comment_user_name = excluded.comment_user_name,
                    comment_user_id = excluded.comment_user_id,
                    like_count = excluded.like_count,
                    item_title = excluded.item_title,
                    comment_type = excluded.comment_type,
                    promotion_id = excluded.promotion_id,
                    material_id = excluded.material_id,
                    item_id = excluded.item_id,
                    raw_json = excluded.raw_json,
                    fetched_at = excluded.fetched_at,
                    updated_at = excluded.updated_at
                """,
                [
                    (
                        customer_center_id,
                        int(record["advertiser_id"]),
                        str(record["comment_id"]),
                        str(record["comment_date"] or ""),
                        self._db_optional_timestamp_value(record.get("create_time")),
                        str(record["advertiser_name"] or advertiser_name or advertiser_id),
                        str(record["text"] or ""),
                        self._safe_int(record.get("reply_count", 0)),
                        str(record["hide_status"] or "NOT_HIDE"),
                        str(record["level_type"] or ""),
                        str(record["comment_user_name"] or ""),
                        str(record["comment_user_id"] or ""),
                        self._safe_int(record.get("like_count", 0)),
                        str(record["item_title"] or ""),
                        str(record["comment_type"] or ""),
                        str(record["promotion_id"] or ""),
                        str(record["material_id"] or ""),
                        str(record["item_id"] or ""),
                        str(record["raw_json"] or "{}"),
                        self._db_optional_timestamp_value(record.get("fetched_at") or attempted_at),
                        self._db_optional_timestamp_value(record.get("updated_at") or attempted_at),
                    )
                    for record in records
                ],
            )
        requested_dates = self._comment_requested_dates(
            datetime.strptime(str(start_date).strip(), "%Y-%m-%d"),
            datetime.strptime(str(end_date).strip(), "%Y-%m-%d"),
        )
        date_counts = {sync_date: 0 for sync_date in requested_dates}
        for record in records:
            sync_date = str(record.get("comment_date") or "").strip()
            if sync_date in date_counts:
                date_counts[sync_date] += 1
        conn.executemany(
            """
            INSERT INTO comment_sync_states (
                customer_center_id, advertiser_id, sync_date, advertiser_name, status, comment_count,
                last_attempt_at, last_success_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (customer_center_id, advertiser_id, sync_date) DO UPDATE SET
                advertiser_name = excluded.advertiser_name,
                status = excluded.status,
                comment_count = excluded.comment_count,
                last_attempt_at = excluded.last_attempt_at,
                last_success_at = excluded.last_success_at,
                error_message = excluded.error_message
            """,
            [
                (
                    customer_center_id,
                    int(advertiser_id),
                    sync_date,
                    str(advertiser_name or advertiser_id),
                    "ok",
                    int(date_counts.get(sync_date, 0)),
                    attempted_at,
                    attempted_at,
                    "",
                )
                for sync_date in requested_dates
            ],
        )

    def _persist_comment_sync_error(
        self,
        conn: Any,
        advertiser_id: int,
        advertiser_name: str,
        start_date: str,
        end_date: str,
        error_message: str,
        attempted_at: str,
    ) -> None:
        customer_center_id = self._current_customer_center_id()
        requested_dates = self._comment_requested_dates(
            datetime.strptime(str(start_date).strip(), "%Y-%m-%d"),
            datetime.strptime(str(end_date).strip(), "%Y-%m-%d"),
        )
        conn.executemany(
            """
            INSERT INTO comment_sync_states (
                customer_center_id, advertiser_id, sync_date, advertiser_name, status, comment_count,
                last_attempt_at, last_success_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (customer_center_id, advertiser_id, sync_date) DO UPDATE SET
                advertiser_name = excluded.advertiser_name,
                status = excluded.status,
                comment_count = excluded.comment_count,
                last_attempt_at = excluded.last_attempt_at,
                error_message = excluded.error_message
            """,
            [
                (
                    customer_center_id,
                    int(advertiser_id),
                    sync_date,
                    str(advertiser_name or advertiser_id),
                    "error",
                    0,
                    attempted_at,
                    None,
                    str(error_message or ""),
                )
                for sync_date in requested_dates
            ],
        )

    def _stored_comment_records(
        self,
        conn: Any,
        advertiser_ids: set[int],
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        if not advertiser_ids:
            return []
        advertiser_placeholders = ",".join("?" for _ in advertiser_ids)
        params: list[Any] = [
            self._current_customer_center_id(),
            str(start_date).strip(),
            str(end_date).strip(),
            *sorted(advertiser_ids),
        ]
        rows = conn.execute(
            f"""
            SELECT
                advertiser_id, advertiser_name, comment_id, comment_date, create_time, text, reply_count, hide_status,
                level_type, comment_user_name, comment_user_id, like_count, item_title, comment_type, promotion_id,
                material_id, item_id, raw_json, fetched_at, updated_at
            FROM comment_records
            WHERE customer_center_id = ?
              AND comment_date >= ?
              AND comment_date <= ?
              AND advertiser_id IN ({advertiser_placeholders})
            ORDER BY create_time DESC, like_count DESC, reply_count DESC, comment_id DESC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _mark_comment_replied(self, conn: Any, advertiser_id: int, comment_id: str, updated_at: str) -> None:
        row = conn.execute(
            """
            SELECT reply_count
            FROM comment_records
            WHERE customer_center_id = ?
              AND advertiser_id = ?
              AND comment_id = ?
            LIMIT 1
            """,
            (self._current_customer_center_id(), int(advertiser_id), str(comment_id).strip()),
        ).fetchone()
        if not row:
            return
        next_reply_count = max(1, self._safe_int(row["reply_count"]))
        conn.execute(
            """
            UPDATE comment_records
            SET reply_count = ?, updated_at = ?, fetched_at = ?
            WHERE customer_center_id = ?
              AND advertiser_id = ?
              AND comment_id = ?
            """,
            (
                next_reply_count,
                self._db_optional_timestamp_value(updated_at),
                self._db_optional_timestamp_value(updated_at),
                self._current_customer_center_id(),
                int(advertiser_id),
                str(comment_id).strip(),
            ),
        )

    def _mark_comment_hidden(self, conn: Any, advertiser_id: int, comment_id: str, updated_at: str) -> None:
        conn.execute(
            """
            UPDATE comment_records
            SET hide_status = 'HIDE', updated_at = ?, fetched_at = ?
            WHERE customer_center_id = ?
              AND advertiser_id = ?
              AND comment_id = ?
            """,
            (
                self._db_optional_timestamp_value(updated_at),
                self._db_optional_timestamp_value(updated_at),
                self._current_customer_center_id(),
                int(advertiser_id),
                str(comment_id).strip(),
            ),
        )

    def comment_items(
        self,
        range_key: str = "day",
        start_date: str = "",
        end_date: str = "",
        advertiser_id: int | None = None,
        allowed_advertiser_ids: set[int] | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        normalized = str(range_key or "day").strip().lower()
        if normalized not in PERFORMANCE_RANGES:
            raise ValueError("range must be one of day/yesterday/week/month/custom")
        config = self.read_config()
        if normalized == "custom":
            start_dt, end_dt, range_label = build_custom_performance_window(start_date, end_date, config["timezone"])
        else:
            start_dt, end_dt, range_label = build_performance_window(normalized, config["timezone"])
        selected_advertiser_id = int(advertiser_id or 0)
        cache_key = build_comment_cache_key(
            normalized,
            start_date,
            end_date,
            selected_advertiser_id,
            allowed_advertiser_ids,
            self._current_customer_center_id(),
        )
        cache_version = self._shared_cache_version("comment")
        versioned_cache_key = self._versioned_cache_key(cache_version, cache_key)
        now_ts = time.time()
        if not force_refresh:
            cached_payload = self._local_dict_cache_get(self._comment_cache, versioned_cache_key, RANGE_CACHE_SECONDS)
            if cached_payload is not None:
                if cached_payload.get("comment_sync_pending"):
                    cached_payload["comment_sync_queued"] = self._queue_comment_sync_if_needed(
                        str(cached_payload.get("query_start_date") or start_dt.strftime("%Y-%m-%d")),
                        str(cached_payload.get("query_end_date") or end_dt.strftime("%Y-%m-%d")),
                        advertiser_id=selected_advertiser_id,
                        allowed_advertiser_ids=allowed_advertiser_ids,
                    )
                return cached_payload
            shared_payload = self._shared_dict_cache_get("comment", cache_key, cache_version)
            if shared_payload is not None:
                if shared_payload.get("comment_sync_pending"):
                    shared_payload["comment_sync_queued"] = self._queue_comment_sync_if_needed(
                        str(shared_payload.get("query_start_date") or start_dt.strftime("%Y-%m-%d")),
                        str(shared_payload.get("query_end_date") or end_dt.strftime("%Y-%m-%d")),
                        advertiser_id=selected_advertiser_id,
                        allowed_advertiser_ids=allowed_advertiser_ids,
                    )
                self._local_dict_cache_set(self._comment_cache, versioned_cache_key, shared_payload)
                return shared_payload

        all_accounts = self.latest_account_catalog(allowed_advertiser_ids)
        accounts = list(all_accounts)
        if selected_advertiser_id:
            accounts = [item for item in accounts if int(item["advertiser_id"]) == selected_advertiser_id]
        if not accounts:
            payload = {
                "items": [],
                "accounts": all_accounts,
                "meta": {
                    "comment_count": 0,
                    "account_count": 0,
                    "error_count": 0,
                    "errors": [],
                },
                "range_key": normalized,
                "range_label": range_label,
                "query_start_date": start_dt.strftime("%Y-%m-%d"),
                "query_end_date": end_dt.strftime("%Y-%m-%d"),
                "window_start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "window_end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "selected_advertiser_id": selected_advertiser_id,
                "comment_sync_pending": False,
                "comment_sync_queued": False,
                "fetched_at": now_text(config["timezone"]),
            }
            self._local_dict_cache_set(self._comment_cache, versioned_cache_key, payload)
            self._shared_dict_cache_set("comment", cache_key, cache_version, payload, RANGE_CACHE_SECONDS)
            return payload

        comment_start_date = start_dt.strftime("%Y-%m-%d")
        comment_end_date = end_dt.strftime("%Y-%m-%d")
        window_start = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        window_end = end_dt.strftime("%Y-%m-%d %H:%M:%S")
        errors: list[dict[str, Any]] = []
        account_ids = {int(account["advertiser_id"]) for account in accounts if int(account.get("advertiser_id", 0) or 0)}
        sync_plans: list[dict[str, Any]] = []
        with self.db() as conn:
            sync_plans = self._comment_sync_plans(
                conn,
                accounts,
                start_dt,
                end_dt,
                config["timezone"],
                force_refresh=force_refresh,
            )

        comment_sync_pending = bool(sync_plans)
        comment_sync_queued = False
        if sync_plans:
            if force_refresh:
                sync_result = self._execute_comment_sync_plans(config, sync_plans)
                errors = list(sync_result.get("errors") or [])
                comment_sync_pending = False
            else:
                comment_sync_queued = self._queue_comment_sync_if_needed(
                    comment_start_date,
                    comment_end_date,
                    advertiser_id=selected_advertiser_id,
                    allowed_advertiser_ids=allowed_advertiser_ids,
                )

        items: list[dict[str, Any]] = []
        advertiser_ids: set[int] = set()
        promotion_ids: set[int] = set()
        material_ids: set[str] = set()
        with self.db() as conn:
            stored_rows = self._stored_comment_records(conn, account_ids, comment_start_date, comment_end_date)
            items = [self._comment_item_from_record(row) for row in stored_rows]
            advertiser_ids = {int(item["advertiser_id"]) for item in items if int(item.get("advertiser_id", 0) or 0)}
            promotion_ids = {
                int(str(item.get("promotion_id") or "").strip())
                for item in items
                if str(item.get("promotion_id") or "").strip().isdigit()
            }
            material_ids = {
                str(item.get("material_id") or "").strip()
                for item in items
                if str(item.get("material_id") or "").strip()
            }
            plan_map, fallback_plan_map = self._comment_plan_name_maps(conn, advertiser_ids, promotion_ids)
            material_map, fallback_material_map = self._comment_material_name_maps(conn, advertiser_ids, material_ids)

        for item in items:
            advertiser_id_value = int(item.get("advertiser_id", 0) or 0)
            promotion_text = str(item.get("promotion_id") or "").strip()
            material_text = str(item.get("material_id") or "").strip()
            promotion_name = ""
            if promotion_text.isdigit():
                promotion_id_value = int(promotion_text)
                promotion_name = plan_map.get((advertiser_id_value, promotion_id_value), "") or fallback_plan_map.get(
                    promotion_id_value,
                    "",
                )
            material_name = material_map.get((advertiser_id_value, material_text), "") or fallback_material_map.get(
                material_text,
                "",
            )
            item["promotion_name"] = promotion_name
            item["promotion_display_name"] = promotion_name or (f"计划 {promotion_text}" if promotion_text else "-")
            item["material_name"] = material_name
            item["material_display_name"] = material_name or (f"素材 {material_text}" if material_text else "-")

        items.sort(
            key=lambda item: (
                str(item.get("create_time") or ""),
                int(item.get("like_count", 0) or 0),
                int(item.get("reply_count", 0) or 0),
                str(item.get("comment_id") or ""),
            ),
            reverse=True,
        )
        payload = {
            "items": items,
            "accounts": all_accounts,
            "meta": {
                "comment_count": len(items),
                "account_count": len(accounts),
                "error_count": len(errors),
                "errors": errors,
            },
            "range_key": normalized,
            "range_label": range_label,
            "query_start_date": start_dt.strftime("%Y-%m-%d"),
            "query_end_date": end_dt.strftime("%Y-%m-%d"),
            "window_start": window_start,
            "window_end": window_end,
            "selected_advertiser_id": selected_advertiser_id,
            "comment_sync_pending": comment_sync_pending,
            "comment_sync_queued": comment_sync_queued,
            "fetched_at": now_text(config["timezone"]),
        }
        self._local_dict_cache_set(self._comment_cache, versioned_cache_key, payload)
        self._shared_dict_cache_set("comment", cache_key, cache_version, payload, RANGE_CACHE_SECONDS)
        return payload

    def reply_comment(
        self,
        advertiser_id: int,
        comment_id: str,
        reply_text: str,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        advertiser_id_value = int(advertiser_id or 0)
        if advertiser_id_value <= 0:
            raise ValueError("advertiser_id is required")
        if allowed_advertiser_ids is not None and advertiser_id_value not in {int(item) for item in allowed_advertiser_ids}:
            raise PermissionError("advertiser is not allowed")
        comment_text = str(comment_id or "").strip()
        if not comment_text:
            raise ValueError("comment_id is required")
        reply_body = str(reply_text or "").strip()
        if not reply_body:
            raise ValueError("reply_text is required")
        if len(reply_body) > COMMENT_REPLY_MAX_LENGTH:
            raise ValueError(f"reply_text must be <= {COMMENT_REPLY_MAX_LENGTH} chars")
        client = self.build_client(self.read_config())
        response = client.reply_comments(advertiser_id_value, [comment_text], reply_body)
        updated_at = now_text(self.read_config()["timezone"])
        with self.db() as conn:
            self._mark_comment_replied(conn, advertiser_id_value, comment_text, updated_at)
        self._clear_comment_caches()
        return {
            "ok": True,
            "advertiser_id": advertiser_id_value,
            "comment_id": comment_text,
            "reply_text": reply_body,
            "response": response,
        }

    def hide_comment(
        self,
        advertiser_id: int,
        comment_id: str,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        advertiser_id_value = int(advertiser_id or 0)
        if advertiser_id_value <= 0:
            raise ValueError("advertiser_id is required")
        if allowed_advertiser_ids is not None and advertiser_id_value not in {int(item) for item in allowed_advertiser_ids}:
            raise PermissionError("advertiser is not allowed")
        comment_text = str(comment_id or "").strip()
        if not comment_text:
            raise ValueError("comment_id is required")
        client = self.build_client(self.read_config())
        response = client.hide_comments(advertiser_id_value, [comment_text])
        updated_at = now_text(self.read_config()["timezone"])
        with self.db() as conn:
            self._mark_comment_hidden(conn, advertiser_id_value, comment_text, updated_at)
        self._clear_comment_caches()
        return {
            "ok": True,
            "advertiser_id": advertiser_id_value,
            "comment_id": comment_text,
            "response": response,
        }

    def matched_materials_for_user(
        self,
        user_id: int,
        range_key: str = "month",
        start_date: str = "",
        end_date: str = "",
        query: str = "",
    ) -> dict[str, Any]:
        user = self.get_user_by_id(user_id, include_disabled=True)
        if not user or str(user.get("role") or "") != ROLE_OPERATOR:
            return {"items": [], "range_key": range_key, "query": str(query or "").strip()}
        operators, keywords = self._operator_config(include_disabled=True, only_user_id=user_id)
        payload = self._cross_customer_center_material_payload(range_key, start_date, end_date, "", None)
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
            "items": items,
            "range_key": payload.get("range_key", range_key),
            "range_label": payload.get("range_label", RANGE_LABEL_MAP.get(range_key, "今日")),
            "query": str(query or "").strip(),
            "snapshot_time": payload.get("snapshot_time", ""),
            "snapshot_count": int(payload.get("snapshot_count") or 0),
            "customer_center_count": int(payload.get("customer_center_count") or 0),
        }

    def process_material_upload_job(self, job_id: int) -> dict[str, Any]:
        running_note = "\u6b63\u5728\u4e0a\u4f20\u7d20\u6750\u5e76\u7ed1\u5b9a\u8ba1\u5212\u3002"
        missing_file_message = "\u6587\u4ef6\u4e0d\u5b58\u5728\uff0c\u65e0\u6cd5\u6267\u884c\u4e0a\u4f20\u3002"
        reuse_message = "\u590d\u7528\u8d26\u6237\u5df2\u6709\u7d20\u6750\u3002"
        upload_success_message = "\u4e0a\u4f20\u6210\u529f\u3002"
        no_target_material_message = "\u8ba1\u5212\u6ca1\u6709\u5339\u914d\u5230\u5f85\u5904\u7406\u7d20\u6750\u3002"
        missing_context_message = "\u8ba1\u5212\u4e0a\u4e0b\u6587\u4e0d\u5b58\u5728\uff0c\u65e0\u6cd5\u7ed1\u5b9a\u7d20\u6750\u3002"
        missing_asset_message = "\u672a\u4e0a\u4f20\u5230\u8d26\u6237\u7d20\u6750\u5e93\u3002"
        bind_success_message = "\u7ed1\u5b9a\u6210\u529f\u3002"
        final_success_note = "\u7d20\u6750\u4e0a\u4f20\u5b8c\u6210\u3002"
        final_failure_note = "\u7d20\u6750\u4e0a\u4f20\u5df2\u7ed3\u675f\uff0c\u5b58\u5728\u5931\u8d25\u9879\u3002"

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
                note=running_note,
                updated_at=now,
            )
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
            target_asset_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT target_id, file_id
                    FROM material_upload_job_target_assets
                    WHERE job_id = ?
                    ORDER BY target_id ASC, file_id ASC
                    """,
                    (int(job_id),),
                ).fetchall()
            ]

        plan_context_map = self._latest_plan_context_map([int(item["ad_id"]) for item in target_rows])
        advertiser_plan_map: dict[int, list[dict[str, Any]]] = {}
        target_lookup = {int(item["id"]): item for item in target_rows}
        for target in target_rows:
            advertiser_plan_map.setdefault(int(target["advertiser_id"]), []).append(target)

        target_file_id_map: dict[int, set[int]] = {}
        file_advertiser_id_map: dict[int, set[int]] = {}
        if target_asset_rows:
            for row in target_asset_rows:
                target_id = int(row.get("target_id", 0) or 0)
                file_id = int(row.get("file_id", 0) or 0)
                if not target_id or not file_id:
                    continue
                target_file_id_map.setdefault(target_id, set()).add(file_id)
                target = target_lookup.get(target_id)
                if target:
                    file_advertiser_id_map.setdefault(file_id, set()).add(int(target["advertiser_id"]))
        else:
            all_advertiser_ids = {int(item["advertiser_id"]) for item in target_rows}
            for file_row in file_rows:
                file_advertiser_id_map[int(file_row["id"])] = set(all_advertiser_ids)

        file_assets: dict[tuple[int, int], dict[str, str]] = {}
        for file_row in file_rows:
            file_id = int(file_row["id"])
            file_path = UPLOAD_DIR / str(file_row.get("relative_path") or "")
            retry_advertiser_ids = sorted(file_advertiser_id_map.get(file_id) or advertiser_plan_map.keys())
            if not file_path.exists():
                with self.db() as conn:
                    for advertiser_id in retry_advertiser_ids:
                        targets = advertiser_plan_map.get(advertiser_id) or []
                        advertiser_name = str(targets[0].get("advertiser_name") or "") if targets else ""
                        self._upsert_material_upload_file_asset_locked(
                            conn,
                            int(job_id),
                            file_id,
                            advertiser_id,
                            advertiser_name,
                            "failed",
                            message=missing_file_message,
                        )
                    conn.execute(
                        """
                        UPDATE material_upload_job_files
                        SET status = 'failed', message = ?, processed_advertisers = ?, success_advertisers = 0, failed_advertisers = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            missing_file_message,
                            len(retry_advertiser_ids),
                            len(retry_advertiser_ids),
                            now_text(),
                            file_id,
                        ),
                    )
                    self._recompute_material_upload_job_locked(conn, int(job_id))
                continue

            probe_summary, preflight_failure_message = self._probe_upload_video(file_row, file_path)
            success_advertisers = 0
            failed_advertisers = 0
            first_asset: dict[str, str] | None = None
            file_errors: list[str] = []
            for advertiser_id in retry_advertiser_ids:
                targets = advertiser_plan_map.get(advertiser_id) or []
                if not targets:
                    continue
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
                            message=reuse_message,
                        )
                    continue
                if preflight_failure_message:
                    failed_advertisers += 1
                    message = preflight_failure_message
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
                        raise RuntimeError(f"upload response missing video_id: {upload_response}")
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
                            message=upload_success_message,
                        )
                except Exception as exc:
                    failed_advertisers += 1
                    message = self._append_upload_probe_summary(str(exc), probe_summary)
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

            file_status = "success" if failed_advertisers == 0 and success_advertisers > 0 else "failed"
            if success_advertisers > 0 and failed_advertisers > 0:
                file_status = "partial"
            file_message = upload_success_message if file_status == "success" else "?".join(file_errors[:3]) or "\u4e0a\u4f20\u5931\u8d25\u3002"
            if probe_summary and (
                file_status != "success"
                or not probe_summary.startswith("\u89c6\u9891\u5143\u6570\u636e\u63a2\u6d4b\u5931\u8d25")
            ):
                file_message = self._append_upload_probe_summary(file_message, probe_summary)
            with self.db() as conn:
                conn.execute(
                    """
                    UPDATE material_upload_job_files
                    SET status = ?, message = ?, material_id = ?, video_id = ?, video_url = ?,
                        processed_advertisers = ?, success_advertisers = ?, failed_advertisers = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        file_status,
                        file_message,
                        str((first_asset or {}).get("material_id") or ""),
                        str((first_asset or {}).get("video_id") or ""),
                        str((first_asset or {}).get("video_url") or ""),
                        success_advertisers + failed_advertisers,
                        success_advertisers,
                        failed_advertisers,
                        now_text(),
                        file_id,
                    ),
                )
                self._recompute_material_upload_job_locked(conn, int(job_id))

        for target in target_rows:
            target_id = int(target["id"])
            advertiser_id = int(target["advertiser_id"])
            ad_id = int(target["ad_id"])
            allowed_file_ids = target_file_id_map.get(target_id)
            candidate_file_rows = [
                row for row in file_rows
                if not allowed_file_ids or int(row.get("id", 0) or 0) in allowed_file_ids
            ]
            if not candidate_file_rows:
                with self.db() as conn:
                    conn.execute(
                        """
                        UPDATE material_upload_job_targets
                        SET status = 'failed', message = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (no_target_material_message, now_text(), target_id),
                    )
                    self._recompute_material_upload_job_locked(conn, int(job_id))
                continue

            context = plan_context_map.get(ad_id) or {}
            if not context:
                with self.db() as conn:
                    for file_row in candidate_file_rows:
                        self._upsert_material_upload_target_asset_locked(
                            conn,
                            int(job_id),
                            target_id,
                            int(file_row["id"]),
                            "failed",
                            missing_context_message,
                        )
                    conn.execute(
                        """
                        UPDATE material_upload_job_targets
                        SET status = 'failed', message = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (missing_context_message, now_text(), target_id),
                    )
                    self._recompute_material_upload_job_locked(conn, int(job_id))
                continue

            success_count = 0
            failed_count = 0
            bind_errors: list[str] = []
            marketing_goal = str(context.get("marketing_goal") or "").strip()
            reused_image_material = self._extract_plan_image_material(context)
            video_material_defaults = self._extract_plan_video_material_defaults(context)
            for file_row in candidate_file_rows:
                file_id = int(file_row["id"])
                asset = file_assets.get((file_id, advertiser_id))
                if not asset or not str(asset.get("video_id") or ""):
                    failed_count += 1
                    bind_errors.append(f"{file_row.get('original_name') or file_row.get('stored_name')}: {missing_asset_message}")
                    with self.db() as conn:
                        self._upsert_material_upload_target_asset_locked(
                            conn,
                            int(job_id),
                            target_id,
                            file_id,
                            "failed",
                            missing_asset_message,
                        )
                    continue
                try:
                    material_title = self._material_title_from_filename(str(file_row.get("original_name") or ""))
                    bind_image_material = [] if marketing_goal == "VIDEO_PROM_GOODS" else [dict(item) for item in reused_image_material]
                    bind_video_cover_id = str(video_material_defaults.get("video_cover_id") or "")
                    client.add_plan_material(
                        advertiser_id=advertiser_id,
                        ad_id=ad_id,
                        material_title=material_title,
                        video_id=str(asset.get("video_id") or ""),
                        marketing_goal=marketing_goal,
                        product_id=str(context.get("product_id") or ""),
                        image_material=bind_image_material,
                        video_image_mode=str(video_material_defaults.get("image_mode") or ""),
                        video_cover_id=bind_video_cover_id,
                    )
                    success_count += 1
                    with self.db() as conn:
                        self._upsert_material_upload_target_asset_locked(
                            conn,
                            int(job_id),
                            target_id,
                            file_id,
                            "success",
                            bind_success_message,
                        )
                except Exception as exc:
                    failed_count += 1
                    message = str(exc)
                    bind_errors.append(f"{file_row.get('original_name') or file_row.get('stored_name')}: {message}")
                    with self.db() as conn:
                        self._upsert_material_upload_target_asset_locked(
                            conn,
                            int(job_id),
                            target_id,
                            file_id,
                            "failed",
                            message,
                        )

            target_status = "success" if failed_count == 0 and success_count > 0 else "failed"
            if success_count > 0 and failed_count > 0:
                target_status = "partial"
            summary = f"\u6210\u529f {success_count} / \u5931\u8d25 {failed_count}"
            if bind_errors:
                summary = f"{summary}\uff1b{bind_errors[0]}"
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
            target_status_rows = conn.execute(
                "SELECT status FROM material_upload_job_targets WHERE job_id = ?",
                (int(job_id),),
            ).fetchall()
            statuses = {str(row["status"] or "") for row in target_status_rows}
            final_status = "success" if statuses == {"success"} else "failed"
            if "partial" in statuses or ("success" in statuses and "failed" in statuses):
                final_status = "partial"
            if not statuses:
                final_status = "failed"
            self._update_material_upload_job(
                conn,
                int(job_id),
                status=final_status,
                note=final_success_note if final_status == "success" else final_failure_note,
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
        customer_center_id = self._current_customer_center_id()
        previous = conn.execute(
            """
            SELECT snapshot_time
            FROM summary_snapshots
            WHERE customer_center_id = ?
              AND snapshot_time < ?
            ORDER BY snapshot_time DESC
            LIMIT 1
            """,
            (customer_center_id, snapshot_time),
        ).fetchone()
        if not previous:
            return {}
        rows = conn.execute(
            """
            SELECT ad_id, order_count
            FROM plan_snapshots
            WHERE snapshot_time = ?
              AND customer_center_id = ?
            """,
            (str(previous["snapshot_time"]), customer_center_id),
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

    def _latest_summary_meta(self, conn: Any, customer_center_id: str | None = None) -> Any:
        target_customer_center_id = str(customer_center_id or self._current_customer_center_id() or "").strip()
        return conn.execute(
            """
            SELECT snapshot_time, window_start, window_end
            FROM summary_snapshots
            WHERE customer_center_id = ?
            ORDER BY snapshot_time DESC
            LIMIT 1
            """,
            (target_customer_center_id,),
        ).fetchone()

    def _snapshot_plans(self, conn: Any, snapshot_time: str, customer_center_id: str | None = None) -> list[dict[str, Any]]:
        target_customer_center_id = str(customer_center_id or self._current_customer_center_id() or "").strip()
        rows = conn.execute(
            """
            SELECT *
            FROM plan_snapshots
            WHERE snapshot_time = ?
              AND customer_center_id = ?
            ORDER BY order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, ad_id ASC
            """,
            (snapshot_time, target_customer_center_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def _collect_window_snapshot(
        self,
        start_dt: datetime,
        end_dt: datetime,
        *,
        include_balances: bool = True,
        config: dict[str, Any] | None = None,
        client: OceanEngineClient | None = None,
    ) -> dict[str, Any]:
        effective_config = dict(config or self.read_config())
        effective_client = client or self.build_client(effective_config)
        accounts = effective_client.list_accounts()
        if include_balances:
            balance_snapshot = self._collect_balance_snapshot(effective_client, accounts)
        else:
            balance_snapshot = {
                "account_balances": [],
                "shared_wallets": [],
                "wallet_relations": [],
                "errors": [],
            }
        account_workers = int(effective_config.get("max_workers", 6) or 6)
        plan_workers = int(effective_config.get("plan_max_workers", 2) or 2)

        summaries: list[AccountSummary] = []
        plans: list[PlanSummary] = []
        failures: list[AccountSummary] = []
        plan_failures: list[str] = []
        plan_failure_ids: set[int] = set()

        with ThreadPoolExecutor(max_workers=account_workers) as pool:
            future_map = {
                pool.submit(fetch_account_bundle, effective_client, item, start_dt, end_dt): item
                for item in accounts
            }
            for future in as_completed(future_map):
                summary = future.result()
                summaries.append(summary)
                if not summary.ok:
                    failures.append(summary)

        with ThreadPoolExecutor(max_workers=plan_workers) as pool:
            future_map = {
                pool.submit(fetch_plan_bundle, effective_client, item, start_dt, end_dt): item
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
        snapshot_time = datetime.now(ZoneInfo(effective_config["timezone"])).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "customer_center_id": str(effective_config.get("customer_center_id") or "").strip(),
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

    def _collect_window_snapshot_for_customer_center(
        self,
        customer_center_id: str,
        start_dt: datetime,
        end_dt: datetime,
        *,
        include_balances: bool = True,
    ) -> dict[str, Any]:
        scoped_config = self._scoped_config_for_customer_center(customer_center_id)
        return self._collect_window_snapshot(
            start_dt,
            end_dt,
            config=scoped_config,
            client=self._build_scoped_customer_center_client(customer_center_id),
            include_balances=include_balances,
        )

    def collect_snapshot_for_customer_center(self, customer_center_id: str) -> dict[str, Any]:
        scoped_config = self._scoped_config_for_customer_center(customer_center_id)
        start_dt, end_dt, _title, _label = build_window("intraday", str(scoped_config.get("timezone") or TIMEZONE))
        return self._collect_window_snapshot_for_customer_center(customer_center_id, start_dt, end_dt)

    def bound_customer_center_ids(self) -> list[str]:
        current_customer_center_id = self._current_customer_center_id()
        items = self.list_bound_customer_centers()
        ordered_ids = [
            str(item.get("customer_center_id") or "").strip()
            for item in items
            if str(item.get("customer_center_id") or "").strip() and bool(item.get("has_saved_token"))
        ]
        deduped_ids: list[str] = []
        seen_ids: set[str] = set()
        if current_customer_center_id:
            deduped_ids.append(current_customer_center_id)
            seen_ids.add(current_customer_center_id)
        for customer_center_id in ordered_ids:
            if customer_center_id in seen_ids:
                continue
            deduped_ids.append(customer_center_id)
            seen_ids.add(customer_center_id)
        return deduped_ids

    def collect_and_store_all_customer_centers(self) -> dict[str, Any]:
        current_customer_center_id = self._current_customer_center_id()
        with self._distributed_runtime_lock("sync", timeout_seconds=300) as acquired:
            if not acquired:
                return {
                    "snapshot_time": "",
                    "current_customer_center_id": current_customer_center_id,
                    "synced_customer_center_count": 0,
                    "synced_customer_centers": [],
                    "error_count": 0,
                    "errors": [],
                    "skipped": True,
                    "reason": "sync already running",
                }

            customer_center_ids = self.bound_customer_center_ids()
            if not customer_center_ids:
                payload = self.collect_and_store()
                return {
                    "snapshot_time": str(payload.get("snapshot_time") or "").strip(),
                    "current_customer_center_id": str(payload.get("customer_center_id") or current_customer_center_id or "").strip(),
                    "synced_customer_center_count": 1 if payload else 0,
                    "synced_customer_centers": [
                        {
                            "customer_center_id": str(payload.get("customer_center_id") or current_customer_center_id or "").strip(),
                            "snapshot_time": str(payload.get("snapshot_time") or "").strip(),
                            "account_count": int((payload.get("summary") or {}).get("account_count") or 0),
                            "active_account_count": int((payload.get("summary") or {}).get("active_account_count") or 0),
                        }
                    ] if payload else [],
                    "error_count": 0,
                    "errors": [],
                    "skipped": False,
                }

            synced_customer_centers: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []
            current_payload: dict[str, Any] | None = None

            for customer_center_id in customer_center_ids:
                try:
                    payload = (
                        self.collect_snapshot()
                        if customer_center_id == current_customer_center_id
                        else self.collect_snapshot_for_customer_center(customer_center_id)
                    )
                    self.persist_snapshot(payload)
                    synced_customer_centers.append(
                        {
                            "customer_center_id": customer_center_id,
                            "snapshot_time": str(payload.get("snapshot_time") or "").strip(),
                            "account_count": int((payload.get("summary") or {}).get("account_count") or 0),
                            "active_account_count": int((payload.get("summary") or {}).get("active_account_count") or 0),
                        }
                    )
                    if customer_center_id == current_customer_center_id:
                        current_payload = payload
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "customer_center_id": customer_center_id,
                            "error": str(exc),
                        }
                    )

            if current_payload:
                self.evaluate_alerts(current_payload)
            self.cleanup_history()
            self.clear_runtime_caches()

            snapshot_time = ""
            if current_payload:
                snapshot_time = str(current_payload.get("snapshot_time") or "").strip()
            elif synced_customer_centers:
                snapshot_time = max(str(item.get("snapshot_time") or "").strip() for item in synced_customer_centers)

            return {
                "snapshot_time": snapshot_time,
                "current_customer_center_id": current_customer_center_id,
                "synced_customer_center_count": len(synced_customer_centers),
                "synced_customer_centers": synced_customer_centers,
                "error_count": len(errors),
                "errors": errors,
                "skipped": False,
            }

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
            payload["snapshot_time"] = self._scoped_day_snapshot_time(
                day_end,
                str(payload.get("customer_center_id") or self._current_customer_center_id() or "").strip(),
            )
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
            self.clear_runtime_caches()
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
            self.persist_extended_snapshot(payload, replace_same_day=True)
            backfilled += 1
        if backfilled:
            self.clear_runtime_caches()
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

    def refresh_recent_performance_history(
        self,
        days: int = HISTORY_BACKFILL_DAYS,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        tz = ZoneInfo(self.read_config()["timezone"])
        refresh_days = max(int(days or HISTORY_BACKFILL_DAYS), 1)
        today = datetime.now(tz).date()
        start_day = today - timedelta(days=refresh_days)
        refreshed = 0
        error_count = 0
        errors: list[dict[str, Any]] = []
        customer_center_ids = self.bound_customer_center_ids() or [self._current_customer_center_id()]
        total_steps = len(customer_center_ids) * refresh_days
        completed_steps = 0
        customer_center_results: list[dict[str, Any]] = []
        for customer_center_id in customer_center_ids:
            center_refreshed = 0
            center_error_count = 0
            for offset in range(refresh_days, 0, -1):
                target_day = today - timedelta(days=offset)
                day_start = datetime(target_day.year, target_day.month, target_day.day, 0, 0, 0, tzinfo=tz)
                day_end = datetime(target_day.year, target_day.month, target_day.day, 23, 59, 59, tzinfo=tz)
                if callable(progress_callback):
                    progress_callback(
                        {
                            "customer_center_id": customer_center_id,
                            "target_day": target_day.strftime("%Y-%m-%d"),
                            "completed_steps": completed_steps,
                            "total_steps": total_steps,
                        }
                    )
                try:
                    payload = self._collect_window_snapshot_for_customer_center(
                        customer_center_id,
                        day_start,
                        day_end,
                        include_balances=False,
                    )
                    payload["snapshot_time"] = self._scoped_day_snapshot_time(day_end, customer_center_id)
                    payload["window_start"] = day_start.strftime("%Y-%m-%d %H:%M:%S")
                    payload["window_end"] = day_end.strftime("%Y-%m-%d %H:%M:%S")
                    payload["accountBalances"] = []
                    payload["sharedWallets"] = []
                    payload["walletRelations"] = []
                    if "errors" not in payload or not isinstance(payload["errors"], dict):
                        payload["errors"] = {"accounts": [], "plans": [], "balances": []}
                    else:
                        payload["errors"]["balances"] = []
                    account_error_count = len(payload["errors"].get("accounts") or [])
                    plan_error_count = len(payload["errors"].get("plans") or [])
                    error_count += account_error_count + plan_error_count
                    center_error_count += account_error_count + plan_error_count
                    self.persist_snapshot(payload)
                    refreshed += 1
                    center_refreshed += 1
                except Exception as exc:  # noqa: BLE001
                    error_count += 1
                    center_error_count += 1
                    errors.append(
                        {
                            "customer_center_id": customer_center_id,
                            "target_day": target_day.strftime("%Y-%m-%d"),
                            "stage": "performance_refresh",
                            "error": str(exc),
                        }
                    )
                completed_steps += 1
                if callable(progress_callback):
                    progress_callback(
                        {
                            "customer_center_id": customer_center_id,
                            "target_day": target_day.strftime("%Y-%m-%d"),
                            "completed_steps": completed_steps,
                            "total_steps": total_steps,
                        }
                    )
            customer_center_results.append(
                {
                    "customer_center_id": customer_center_id,
                    "refreshed_days": center_refreshed,
                    "error_count": center_error_count,
                }
            )
        if refreshed:
            self.clear_runtime_caches()
        return {
            "refresh_days": refresh_days,
            "refreshed_days": refreshed,
            "skipped_current_day": 1,
            "error_count": error_count,
            "customer_center_count": len(customer_center_ids),
            "customer_centers": customer_center_results,
            "errors": errors,
            "range_start": start_day.strftime("%Y-%m-%d"),
            "range_end": (today - timedelta(days=1)).strftime("%Y-%m-%d"),
        }

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

    def refresh_recent_extended_history(
        self,
        days: int = EXTENDED_HISTORY_REFRESH_DAYS,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        tz = ZoneInfo(self.read_config()["timezone"])
        refresh_days = max(int(days or EXTENDED_HISTORY_REFRESH_DAYS), 1)
        today = datetime.now(tz).date()
        start_day = today - timedelta(days=max(refresh_days - 1, 0))
        refreshed = 0
        skipped_current_day = 0
        missing_summary_days = 0
        detail_errors = 0
        customer_center_ids = self.bound_customer_center_ids() or [self._current_customer_center_id()]
        total_steps = len(customer_center_ids) * refresh_days
        completed_steps = 0
        errors: list[dict[str, Any]] = []
        customer_center_results: list[dict[str, Any]] = []
        for customer_center_id in customer_center_ids:
            center_refreshed = 0
            center_missing_summary_days = 0
            center_error_count = 0
            for offset in range(refresh_days):
                target_day = start_day + timedelta(days=offset)
                if target_day >= today:
                    skipped_current_day += 1
                    continue
                if callable(progress_callback):
                    progress_callback(
                        {
                            "customer_center_id": customer_center_id,
                            "target_day": target_day.strftime("%Y-%m-%d"),
                            "completed_steps": completed_steps,
                            "total_steps": total_steps,
                        }
                    )
                day_marker = datetime(target_day.year, target_day.month, target_day.day)
                with self.db() as conn:
                    meta = self._summary_meta_for_customer_center_day(conn, day_marker, customer_center_id)
                if not meta:
                    missing_summary_days += 1
                    center_missing_summary_days += 1
                    completed_steps += 1
                    if callable(progress_callback):
                        progress_callback(
                            {
                                "customer_center_id": customer_center_id,
                                "target_day": target_day.strftime("%Y-%m-%d"),
                                "completed_steps": completed_steps,
                                "total_steps": total_steps,
                            }
                        )
                    continue
                try:
                    payload = self._collect_extended_snapshot_for_meta(meta, customer_center_id)
                    if payload.get("skipped"):
                        completed_steps += 1
                        if callable(progress_callback):
                            progress_callback(
                                {
                                    "customer_center_id": customer_center_id,
                                    "target_day": target_day.strftime("%Y-%m-%d"),
                                    "completed_steps": completed_steps,
                                    "total_steps": total_steps,
                                }
                            )
                        continue
                    payload_errors = len(payload.get("errors") or [])
                    detail_errors += payload_errors
                    center_error_count += payload_errors
                    self.persist_extended_snapshot(payload, replace_same_day=True)
                    refreshed += 1
                    center_refreshed += 1
                except Exception as exc:  # noqa: BLE001
                    detail_errors += 1
                    center_error_count += 1
                    errors.append(
                        {
                            "customer_center_id": customer_center_id,
                            "target_day": target_day.strftime("%Y-%m-%d"),
                            "stage": "detail_history_refresh",
                            "error": str(exc),
                        }
                    )
                completed_steps += 1
                if callable(progress_callback):
                    progress_callback(
                        {
                            "customer_center_id": customer_center_id,
                            "target_day": target_day.strftime("%Y-%m-%d"),
                            "completed_steps": completed_steps,
                            "total_steps": total_steps,
                        }
                    )
            customer_center_results.append(
                {
                    "customer_center_id": customer_center_id,
                    "refreshed_days": center_refreshed,
                    "missing_summary_days": center_missing_summary_days,
                    "error_count": center_error_count,
                }
            )
        if refreshed:
            self.clear_runtime_caches()
        return {
            "refresh_days": refresh_days,
            "refreshed_days": refreshed,
            "skipped_current_day": skipped_current_day,
            "missing_summary_days": missing_summary_days,
            "error_count": detail_errors,
            "customer_center_count": len(customer_center_ids),
            "customer_centers": customer_center_results,
            "errors": errors,
            "range_start": start_day.strftime("%Y-%m-%d"),
            "range_end": today.strftime("%Y-%m-%d"),
        }

    def persist_snapshot(self, payload: dict[str, Any]) -> None:
        customer_center_id = str(payload.get("customer_center_id") or self._current_customer_center_id() or "").strip()
        with self.db() as conn:
            resolved_snapshot_time = self._next_available_snapshot_time(
                conn,
                "summary_snapshots",
                str(payload.get("snapshot_time") or "").strip(),
                customer_center_id,
            )
            payload["snapshot_time"] = resolved_snapshot_time
            conn.execute(
                """
                INSERT INTO summary_snapshots (
                    snapshot_time, customer_center_id, window_start, window_end, account_count, active_account_count,
                    plan_count, active_plan_count, stat_cost, pay_amount, order_count, roi,
                    account_failures, plan_failures
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (customer_center_id, snapshot_time) DO UPDATE SET
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
                    resolved_snapshot_time,
                    customer_center_id,
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
            conn.execute(
                "DELETE FROM account_snapshots WHERE snapshot_time = ? AND customer_center_id = ?",
                (resolved_snapshot_time, customer_center_id),
            )
            conn.execute(
                "DELETE FROM plan_snapshots WHERE snapshot_time = ? AND customer_center_id = ?",
                (resolved_snapshot_time, customer_center_id),
            )
            conn.execute(
                "DELETE FROM account_balances WHERE snapshot_time = ? AND customer_center_id = ?",
                (resolved_snapshot_time, customer_center_id),
            )
            conn.execute(
                "DELETE FROM shared_wallets WHERE snapshot_time = ? AND customer_center_id = ?",
                (resolved_snapshot_time, customer_center_id),
            )
            conn.execute(
                "DELETE FROM shared_wallet_account_relations WHERE snapshot_time = ? AND customer_center_id = ?",
                (resolved_snapshot_time, customer_center_id),
            )
            conn.executemany(
                """
                INSERT INTO account_snapshots (
                    snapshot_time, customer_center_id, advertiser_id, advertiser_name, stat_cost, roi,
                    order_count, pay_amount, ok, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        resolved_snapshot_time,
                        customer_center_id,
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
                    snapshot_time, customer_center_id, advertiser_id, advertiser_name, ad_id, ad_name,
                    product_id, product_name, anchor_name, marketing_goal, plan_source, plan_delivery_type, status,
                    opt_status, roi_goal, stat_cost, roi, order_count, pay_amount,
                    total_pay_amount, settled_pay_amount, settled_roi, settled_order_count,
                    pay_order_cost, settled_amount_rate, refund_rate_1h, refund_amount_1h
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        resolved_snapshot_time,
                        customer_center_id,
                        item["advertiser_id"],
                        item["advertiser_name"],
                        item["ad_id"],
                        item["ad_name"],
                        item["product_id"],
                        item["product_name"],
                        item["anchor_name"],
                        item["marketing_goal"],
                        item.get("plan_source", PLAN_SOURCE_UNI_PROMOTION),
                        item.get("plan_delivery_type", PLAN_DELIVERY_TYPE_GLOBAL),
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
                        snapshot_time, customer_center_id, advertiser_id, advertiser_name, account_balance,
                        available_balance, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            resolved_snapshot_time,
                            customer_center_id,
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
                        snapshot_time, customer_center_id, main_wallet_id, wallet_name, total_balance,
                        valid_balance, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            resolved_snapshot_time,
                            customer_center_id,
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
                        snapshot_time, customer_center_id, main_wallet_id, advertiser_id, child_wallet_id,
                        wallet_name, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            resolved_snapshot_time,
                            customer_center_id,
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

    def _enrich_material_rows_with_library_create_time(
        self,
        client: OceanEngineClient,
        material_rows: list[tuple[Any, ...]],
    ) -> tuple[list[tuple[Any, ...]], list[dict[str, Any]]]:
        if not material_rows:
            return material_rows, []

        mutable_rows = [list(row) for row in material_rows]
        errors: list[dict[str, Any]] = []
        video_ids_by_advertiser: dict[int, dict[str, list[int]]] = {}
        video_material_ids_by_advertiser: dict[int, dict[str, list[int]]] = {}
        image_ids_by_advertiser: dict[int, dict[str, list[int]]] = {}
        image_material_ids_by_advertiser: dict[int, dict[str, list[int]]] = {}
        carousel_material_ids_by_advertiser: dict[int, dict[str, list[int]]] = {}

        for row_index, row in enumerate(mutable_rows):
            if str(row[11] or "").strip():
                continue
            advertiser_id = int(row[3] or 0)
            if advertiser_id <= 0:
                continue
            material_type = str(row[7] or "").strip().upper()
            material_id = self._numeric_material_id_text(row[9])
            if material_type == "VIDEO":
                video_id = str(row[12] or "").strip()
                if video_id:
                    video_ids_by_advertiser.setdefault(advertiser_id, {}).setdefault(video_id, []).append(row_index)
                if material_id:
                    video_material_ids_by_advertiser.setdefault(advertiser_id, {}).setdefault(material_id, []).append(row_index)
                continue
            if material_type == "IMAGE":
                image_id = self._extract_material_library_image_id(row[22])
                if image_id:
                    image_ids_by_advertiser.setdefault(advertiser_id, {}).setdefault(image_id, []).append(row_index)
                if material_id:
                    image_material_ids_by_advertiser.setdefault(advertiser_id, {}).setdefault(material_id, []).append(row_index)
                continue
            if material_type == "CAROUSEL" and material_id:
                carousel_material_ids_by_advertiser.setdefault(advertiser_id, {}).setdefault(material_id, []).append(row_index)

        def apply_create_time(indexes: list[int], value: Any) -> None:
            normalized = self._normalize_datetime_text(value)
            if not normalized:
                return
            for row_index in indexes:
                current = str(mutable_rows[row_index][11] or "").strip()
                if not current or normalized < current:
                    mutable_rows[row_index][11] = normalized

        def apply_cover_url(indexes: list[int], value: Any) -> None:
            normalized = self._normalize_media_url(value)
            if not self._is_public_preview_cover_url(normalized):
                return
            for row_index in indexes:
                current = self._normalize_media_url(mutable_rows[row_index][13])
                if not self._is_public_preview_cover_url(current):
                    mutable_rows[row_index][13] = normalized

        for advertiser_id, id_map in video_ids_by_advertiser.items():
            material_id_map = video_material_ids_by_advertiser.get(advertiser_id, {})
            ids = sorted(id_map)
            for start in range(0, len(ids), 100):
                batch = ids[start : start + 100]
                try:
                    rows = client.list_qianchuan_videos(
                        advertiser_id=advertiser_id,
                        filtering={"video_ids": batch},
                        page_size=max(20, min(100, len(batch))),
                    )
                    for item in rows:
                        resolved_video_id = str(item.get("id") or "").strip()
                        resolved_material_id = self._numeric_material_id_text(item.get("material_id"))
                        create_time = item.get("create_time")
                        poster_url = item.get("poster_url") or item.get("posterUrl")
                        if resolved_video_id:
                            apply_create_time(id_map.get(resolved_video_id, []), create_time)
                            apply_cover_url(id_map.get(resolved_video_id, []), poster_url)
                        if resolved_material_id:
                            apply_create_time(material_id_map.get(resolved_material_id, []), create_time)
                            apply_cover_url(material_id_map.get(resolved_material_id, []), poster_url)
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "stage": "material_library_video",
                            "advertiser_id": advertiser_id,
                            "video_ids": batch,
                            "error": str(exc),
                        }
                    )

        for advertiser_id, id_map in image_ids_by_advertiser.items():
            material_id_map = image_material_ids_by_advertiser.get(advertiser_id, {})
            ids = sorted(id_map)
            for start in range(0, len(ids), 100):
                batch = ids[start : start + 100]
                try:
                    rows = client.list_qianchuan_images(
                        advertiser_id=advertiser_id,
                        filtering={"image_ids": batch},
                        page_size=max(20, min(100, len(batch))),
                    )
                    for item in rows:
                        resolved_image_id = str(item.get("id") or "").strip()
                        resolved_material_id = self._numeric_material_id_text(item.get("material_id"))
                        create_time = item.get("create_time")
                        if resolved_image_id:
                            apply_create_time(id_map.get(resolved_image_id, []), create_time)
                        if resolved_material_id:
                            apply_create_time(material_id_map.get(resolved_material_id, []), create_time)
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "stage": "material_library_image",
                            "advertiser_id": advertiser_id,
                            "image_ids": batch,
                            "error": str(exc),
                        }
                    )

            unresolved_material_ids = [
                material_id
                for material_id, indexes in material_id_map.items()
                if any(not str(mutable_rows[row_index][11] or "").strip() for row_index in indexes)
            ]
            for start in range(0, len(unresolved_material_ids), 100):
                batch = unresolved_material_ids[start : start + 100]
                try:
                    rows = client.list_qianchuan_images(
                        advertiser_id=advertiser_id,
                        filtering={"material_ids": [int(item) for item in batch]},
                        page_size=max(20, min(100, len(batch))),
                    )
                    for item in rows:
                        resolved_image_id = str(item.get("id") or "").strip()
                        resolved_material_id = self._numeric_material_id_text(item.get("material_id"))
                        create_time = item.get("create_time")
                        if resolved_image_id:
                            apply_create_time(id_map.get(resolved_image_id, []), create_time)
                        if resolved_material_id:
                            apply_create_time(material_id_map.get(resolved_material_id, []), create_time)
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "stage": "material_library_image_material_id",
                            "advertiser_id": advertiser_id,
                            "material_ids": batch,
                            "error": str(exc),
                        }
                    )

        for advertiser_id, id_map in carousel_material_ids_by_advertiser.items():
            ids = sorted(id_map)
            for start in range(0, len(ids), 100):
                batch = ids[start : start + 100]
                try:
                    rows = client.list_qianchuan_carousels(
                        advertiser_id=advertiser_id,
                        filtering={"material_ids": [int(item) for item in batch]},
                        page_size=max(20, min(100, len(batch))),
                    )
                    for item in rows:
                        resolved_material_id = self._numeric_material_id_text(item.get("material_id"))
                        if resolved_material_id:
                            apply_create_time(id_map.get(resolved_material_id, []), item.get("create_time"))
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "stage": "material_library_carousel",
                            "advertiser_id": advertiser_id,
                            "material_ids": batch,
                            "error": str(exc),
                        }
                    )

        return [tuple(row) for row in mutable_rows], errors

    def _collect_extended_snapshot_for_meta(
        self,
        meta: dict[str, Any],
        customer_center_id: str | None = None,
    ) -> dict[str, Any]:
        target_customer_center_id = str(customer_center_id or self._current_customer_center_id() or "").strip()
        config = self.read_config() if not customer_center_id else self._scoped_config_for_customer_center(target_customer_center_id)
        with self.db() as conn:
            plans = self._snapshot_plans(conn, str(meta["snapshot_time"]), target_customer_center_id)
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

        client = self.build_client(config) if not customer_center_id else self._build_scoped_customer_center_client(target_customer_center_id)
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

        material_rows, library_errors = self._enrich_material_rows_with_library_create_time(client, material_rows)
        errors.extend(library_errors)

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
            "customer_center_id": target_customer_center_id,
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

    def collect_extended_snapshot(
        self,
        force_refresh: bool = False,
        customer_center_id: str | None = None,
    ) -> dict[str, Any]:
        target_customer_center_id = str(customer_center_id or self._current_customer_center_id() or "").strip()
        with self.db() as conn:
            meta = self._latest_summary_meta(conn, target_customer_center_id)
            if not meta:
                return {
                    "ok": False,
                    "skipped": True,
                    "reason": "missing summary snapshot",
                }
            existing = conn.execute(
                "SELECT status FROM extended_sync_runs WHERE snapshot_time = ? AND customer_center_id = ?",
                (meta["snapshot_time"], target_customer_center_id),
            ).fetchone()
            if not force_refresh and existing and str(existing["status"]) == "ok":
                return {
                    "ok": True,
                    "skipped": True,
                    "snapshot_time": meta["snapshot_time"],
                    "reason": "already synced",
                }
        return self._collect_extended_snapshot_for_meta(dict(meta), target_customer_center_id)

    def persist_extended_snapshot(self, payload: dict[str, Any], replace_same_day: bool = False) -> None:
        if payload.get("skipped"):
            return
        customer_center_id = str(payload.get("customer_center_id") or self._current_customer_center_id() or "").strip()
        with self.db() as conn:
            resolved_snapshot_time = self._next_available_snapshot_time(
                conn,
                "extended_sync_runs",
                str(payload.get("snapshot_time") or "").strip(),
                customer_center_id,
            )
            if resolved_snapshot_time != str(payload.get("snapshot_time") or "").strip():
                payload["snapshot_time"] = resolved_snapshot_time
                payload["detail_rows"] = self._replace_snapshot_time_in_rows(list(payload.get("detail_rows") or []), resolved_snapshot_time)
                payload["product_rows"] = self._replace_snapshot_time_in_rows(list(payload.get("product_rows") or []), resolved_snapshot_time)
                payload["material_rows"] = self._replace_snapshot_time_in_rows(list(payload.get("material_rows") or []), resolved_snapshot_time)
                payload["video_flag_rows"] = self._replace_snapshot_time_in_rows(list(payload.get("video_flag_rows") or []), resolved_snapshot_time)
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
                    "create_time": row[11],
                    "video_id": row[12],
                    "cover_url": row[13],
                    "aweme_item_id": row[14],
                    "video_url": row[15],
                    "stat_cost": row[18],
                    "pay_amount": row[19],
                    "order_count": row[20],
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
        day_key = str(payload["snapshot_time"] or "")[:10]
        with self.db() as conn:
            if replace_same_day and day_key:
                conn.execute(
                    "DELETE FROM plan_detail_snapshots WHERE substr(snapshot_time, 1, 10) = ? AND customer_center_id = ?",
                    (day_key, customer_center_id),
                )
                conn.execute(
                    "DELETE FROM product_snapshots WHERE substr(snapshot_time, 1, 10) = ? AND customer_center_id = ?",
                    (day_key, customer_center_id),
                )
                conn.execute(
                    "DELETE FROM material_snapshots WHERE substr(snapshot_time, 1, 10) = ? AND customer_center_id = ?",
                    (day_key, customer_center_id),
                )
                conn.execute(
                    "DELETE FROM material_rollups WHERE substr(snapshot_time, 1, 10) = ? AND customer_center_id = ?",
                    (day_key, customer_center_id),
                )
                conn.execute(
                    "DELETE FROM video_origin_flags WHERE substr(snapshot_time, 1, 10) = ? AND customer_center_id = ?",
                    (day_key, customer_center_id),
                )
                conn.execute(
                    "DELETE FROM extended_sync_runs WHERE substr(snapshot_time, 1, 10) = ? AND customer_center_id = ?",
                    (day_key, customer_center_id),
                )
            else:
                conn.execute(
                    "DELETE FROM plan_detail_snapshots WHERE snapshot_time = ? AND customer_center_id = ?",
                    (payload["snapshot_time"], customer_center_id),
                )
                conn.execute(
                    "DELETE FROM product_snapshots WHERE snapshot_time = ? AND customer_center_id = ?",
                    (payload["snapshot_time"], customer_center_id),
                )
                conn.execute(
                    "DELETE FROM material_snapshots WHERE snapshot_time = ? AND customer_center_id = ?",
                    (payload["snapshot_time"], customer_center_id),
                )
                conn.execute(
                    "DELETE FROM material_rollups WHERE snapshot_time = ? AND customer_center_id = ?",
                    (payload["snapshot_time"], customer_center_id),
                )
                conn.execute(
                    "DELETE FROM video_origin_flags WHERE snapshot_time = ? AND customer_center_id = ?",
                    (payload["snapshot_time"], customer_center_id),
                )
                conn.execute(
                    "DELETE FROM extended_sync_runs WHERE snapshot_time = ? AND customer_center_id = ?",
                    (payload["snapshot_time"], customer_center_id),
                )
            if payload["detail_rows"]:
                conn.executemany(
                    """
                    INSERT INTO plan_detail_snapshots (
                        snapshot_time, customer_center_id, advertiser_id, advertiser_name, ad_id, ad_name,
                        product_id, product_name, anchor_name, marketing_goal, status,
                        opt_status, roi_goal, modify_time, product_count, room_count,
                        has_delivery_setting, has_creative_setting, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [(row[0], customer_center_id, *row[1:]) for row in payload["detail_rows"]],
                )
            if payload["product_rows"]:
                conn.executemany(
                    """
                    INSERT INTO product_snapshots (
                        snapshot_time, customer_center_id, window_start, window_end, advertiser_id, advertiser_name,
                        ad_id, ad_name, product_key, product_id, product_name,
                        product_show_count, product_click_count, stat_cost, pay_amount,
                        order_count, roi, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [(row[0], customer_center_id, *row[1:]) for row in payload["product_rows"]],
                )
            if payload["material_rows"]:
                conn.executemany(
                    """
                    INSERT INTO material_snapshots (
                        snapshot_time, customer_center_id, window_start, window_end, advertiser_id, advertiser_name,
                        ad_id, ad_name, material_type, material_key, material_id, material_name, create_time,
                        video_id, cover_url, aweme_item_id, video_url, product_show_count,
                        product_click_count, stat_cost, pay_amount, order_count, roi, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [(row[0], customer_center_id, *row[1:]) for row in payload["material_rows"]],
                )
            if material_rollup_rows:
                conn.executemany(
                    """
                    INSERT INTO material_rollups (
                        snapshot_time, customer_center_id, window_start, window_end, material_key, material_id,
                        material_name, create_time, material_type, video_id, cover_url, aweme_item_id, video_url, stat_cost, pay_amount,
                        total_pay_amount, settled_pay_amount, order_count, settled_order_count, plan_count, advertiser_count,
                        plan_ids_json, advertiser_ids_json, is_original, top_plan_name, top_account_name, roi
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [(row[0], customer_center_id, *row[1:]) for row in material_rollup_rows],
                )
            if payload["video_flag_rows"]:
                conn.executemany(
                    """
                    INSERT INTO video_origin_flags (
                        snapshot_time, customer_center_id, advertiser_id, material_id, is_original, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [(row[0], customer_center_id, *row[1:]) for row in payload["video_flag_rows"]],
                )
            conn.execute(
                """
                INSERT INTO extended_sync_runs (
                    snapshot_time, customer_center_id, window_start, window_end, status, plan_count, detail_count,
                    product_row_count, material_row_count, original_video_row_count,
                    error_count, error_json, created_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (customer_center_id, snapshot_time) DO UPDATE SET
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
                    customer_center_id,
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
        base_cutoff = (datetime.now(ZoneInfo(TIMEZONE)) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        base_cutoff_date = (datetime.now(ZoneInfo(TIMEZONE)) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
        extended_cutoff = (datetime.now(ZoneInfo(TIMEZONE)) - timedelta(days=EXTENDED_RETENTION_DAYS)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        with self.db() as conn:
            conn.execute("DELETE FROM summary_snapshots WHERE snapshot_time < ?", (base_cutoff,))
            conn.execute("DELETE FROM account_snapshots WHERE snapshot_time < ?", (base_cutoff,))
            conn.execute("DELETE FROM plan_snapshots WHERE snapshot_time < ?", (base_cutoff,))
            conn.execute("DELETE FROM account_balances WHERE snapshot_time < ?", (base_cutoff,))
            conn.execute("DELETE FROM shared_wallets WHERE snapshot_time < ?", (base_cutoff,))
            conn.execute("DELETE FROM shared_wallet_account_relations WHERE snapshot_time < ?", (base_cutoff,))
            conn.execute("DELETE FROM comment_records WHERE comment_date < ?", (base_cutoff_date,))
            conn.execute("DELETE FROM comment_sync_states WHERE sync_date < ?", (base_cutoff_date,))
            conn.execute("DELETE FROM plan_detail_snapshots WHERE snapshot_time < ?", (extended_cutoff,))
            conn.execute("DELETE FROM product_snapshots WHERE snapshot_time < ?", (extended_cutoff,))
            conn.execute("DELETE FROM material_snapshots WHERE snapshot_time < ?", (extended_cutoff,))
            conn.execute("DELETE FROM material_rollups WHERE snapshot_time < ?", (extended_cutoff,))
            conn.execute("DELETE FROM video_origin_flags WHERE snapshot_time < ?", (extended_cutoff,))
            conn.execute("DELETE FROM extended_sync_runs WHERE snapshot_time < ?", (extended_cutoff,))

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

    @staticmethod
    def _material_curve_metric_value(row: dict[str, Any], field: str) -> float:
        candidates: list[dict[str, Any]] = [row]
        for key in ("fields", "metrics", "stats", "values", "data"):
            nested = row.get(key)
            if isinstance(nested, dict):
                candidates.append(nested)
        for candidate in candidates:
            if field not in candidate:
                continue
            value = candidate.get(field)
            if isinstance(value, dict):
                value = (
                    value.get("Value")
                    or value.get("value")
                    or value.get("ValueStr")
                    or value.get("value_str")
                    or value.get("val")
                )
            try:
                return float(value or 0.0)
            except (TypeError, ValueError):
                continue
        return 0.0

    @staticmethod
    def _material_curve_second_value(row: dict[str, Any]) -> int:
        candidates: list[Any] = [
            row.get("h_sec"),
            row.get("second"),
            row.get("sec"),
            row.get("progress_second"),
            row.get("play_second"),
        ]
        dimensions = row.get("dimensions")
        if isinstance(dimensions, dict):
            candidates.extend(
                [
                    dimensions.get("h_sec"),
                    dimensions.get("second"),
                    dimensions.get("sec"),
                ]
            )
        for value in candidates:
            try:
                second = int(float(value or 0))
            except (TypeError, ValueError):
                continue
            if second >= 0:
                return second
        return -1

    def _normalize_video_user_lose_rows(self, response: dict[str, Any]) -> list[dict[str, float]]:
        data = response.get("data") or {}
        raw_rows: list[Any] = []
        if isinstance(data, list):
            raw_rows = data
        elif isinstance(data, dict):
            for key in ("list", "rows", "items", "stats_list", "series", "result"):
                value = data.get(key)
                if isinstance(value, list):
                    raw_rows = value
                    break
        grouped: dict[int, dict[str, float]] = {}
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                continue
            second = self._material_curve_second_value(raw_row)
            if second < 0:
                continue
            point = grouped.setdefault(
                second,
                {
                    "second": float(second),
                    "click_cnt": 0.0,
                    "user_lose_cnt": 0.0,
                },
            )
            point["click_cnt"] += self._material_curve_metric_value(raw_row, "click_cnt")
            point["user_lose_cnt"] += self._material_curve_metric_value(raw_row, "user_lose_cnt")
        return [grouped[key] for key in sorted(grouped)]

    def _material_preview_requested_window(
        self,
        range_key: str,
        start_date: str,
        end_date: str,
        snapshot_time: str,
    ) -> tuple[datetime, datetime, str]:
        config = self.read_config()
        tz_name = str(config.get("timezone") or TIMEZONE)
        target_snapshot = str(snapshot_time or "").strip()
        if target_snapshot:
            snapshot_day = _parse_date_input(target_snapshot[:10], "snapshot_time")
            tz = ZoneInfo(tz_name)
            start_dt = datetime(snapshot_day.year, snapshot_day.month, snapshot_day.day, 0, 0, 0, tzinfo=tz)
            end_dt = datetime(snapshot_day.year, snapshot_day.month, snapshot_day.day, 23, 59, 59, tzinfo=tz)
            return start_dt, end_dt, "指定快照"
        normalized = str(range_key or "day").strip().lower()
        if normalized not in PERFORMANCE_RANGES:
            raise ValueError("range must be one of day/yesterday/week/month/custom")
        if normalized == "custom":
            return build_custom_performance_window(start_date, end_date, tz_name)
        return build_performance_window(normalized, tz_name)

    @staticmethod
    def _numeric_material_id_text(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text.isdigit():
                return text
        return ""

    def _material_snapshot_rows_for_curve(
        self,
        material_key: str,
        start_date: str,
        end_date: str,
        snapshot_time: str,
        allowed_advertiser_ids: set[int] | None = None,
        *,
        search_all_customer_centers: bool = False,
    ) -> list[dict[str, Any]]:
        material_key_text = str(material_key or "").strip()
        if not material_key_text:
            return []
        clauses = ["material_key = ?"]
        params: list[Any] = [material_key_text]
        if not search_all_customer_centers:
            clauses.append("customer_center_id = ?")
            params.append(self._current_customer_center_id())
        target_snapshot = str(snapshot_time or "").strip()
        if target_snapshot:
            clauses.append("snapshot_time = ?")
            params.append(target_snapshot)
        else:
            clauses.append("substr(snapshot_time, 1, 10) >= ?")
            params.append(str(start_date or "").strip())
            clauses.append("substr(snapshot_time, 1, 10) <= ?")
            params.append(str(end_date or "").strip())
        if allowed_advertiser_ids is not None:
            allowed = sorted(int(item) for item in allowed_advertiser_ids if int(item or 0))
            if not allowed:
                return []
            placeholders = ",".join("?" for _ in allowed)
            clauses.append(f"advertiser_id IN ({placeholders})")
            params.extend(allowed)
        with self.db() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    snapshot_time,
                    customer_center_id,
                    advertiser_id,
                    advertiser_name,
                    ad_id,
                    ad_name,
                    material_type,
                    material_key,
                    material_id,
                    material_name,
                    video_id,
                    aweme_item_id,
                    cover_url,
                    video_url,
                    stat_cost,
                    pay_amount,
                    order_count,
                    raw_json
                FROM material_snapshots
                WHERE {" AND ".join(clauses)}
                ORDER BY snapshot_time DESC, order_count DESC, pay_amount DESC, stat_cost DESC
                LIMIT 200
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    @classmethod
    def _material_curve_source_from_snapshot_row(cls, row: dict[str, Any]) -> dict[str, Any] | None:
        raw_payload = cls._json_object(row.get("raw_json"))
        material_type = str(row.get("material_type") or raw_payload.get("material_type") or "VIDEO").strip().upper()
        identity = cls._extract_material_identity(material_type, raw_payload) if raw_payload else {}
        preview = cls._extract_material_preview(material_type, raw_payload) if raw_payload else {}
        resolved_material_id = cls._numeric_material_id_text(
            identity.get("material_id"),
            row.get("material_id"),
        )
        if not resolved_material_id:
            return None
        resolved_video_id = cls._first_text(
            identity.get("video_id"),
            row.get("video_id"),
        )
        resolved_aweme_item_id = cls._first_text(
            preview.get("aweme_item_id"),
            row.get("aweme_item_id"),
        )
        return {
            "snapshot_time": str(row.get("snapshot_time") or ""),
            "customer_center_id": str(row.get("customer_center_id") or "").strip(),
            "advertiser_id": int(row.get("advertiser_id", 0) or 0),
            "advertiser_name": str(row.get("advertiser_name") or "").strip(),
            "ad_id": int(row.get("ad_id", 0) or 0),
            "ad_name": str(row.get("ad_name") or "").strip(),
            "material_type": material_type,
            "material_key": str(row.get("material_key") or "").strip(),
            "material_id": resolved_material_id,
            "video_id": resolved_video_id,
            "aweme_item_id": resolved_aweme_item_id,
            "order_count": int(float(row.get("order_count", 0) or 0)),
            "pay_amount": round(float(row.get("pay_amount", 0.0) or 0.0), 2),
            "stat_cost": round(float(row.get("stat_cost", 0.0) or 0.0), 2),
            "source": "material_snapshots.raw_json",
        }

    def _material_curve_source_candidates(
        self,
        row: dict[str, Any],
        start_date: str,
        end_date: str,
        snapshot_time: str,
        allowed_advertiser_ids: set[int] | None = None,
        *,
        search_all_customer_centers: bool = False,
    ) -> list[dict[str, Any]]:
        ranking_material_id = self._numeric_material_id_text(row.get("material_id"))
        ranking_video_id = str(row.get("video_id") or "").strip()
        ranking_aweme_item_id = str(row.get("aweme_item_id") or "").strip()
        top_account_name = str(row.get("top_account_name") or "").strip()
        top_plan_name = str(row.get("top_plan_name") or "").strip()

        candidates: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        seen: set[tuple[int, int, str]] = set()
        for snapshot_row in self._material_snapshot_rows_for_curve(
            str(row.get("material_key") or ""),
            start_date,
            end_date,
            snapshot_time,
            allowed_advertiser_ids,
            search_all_customer_centers=search_all_customer_centers,
        ):
            candidate = self._material_curve_source_from_snapshot_row(snapshot_row)
            if not candidate:
                continue
            dedupe_key = (
                int(candidate["advertiser_id"]),
                int(candidate["ad_id"]),
                str(candidate["material_id"]),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            score = (
                0 if ranking_material_id and candidate["material_id"] == ranking_material_id else 1,
                0 if ranking_aweme_item_id and candidate["aweme_item_id"] == ranking_aweme_item_id else 1,
                0 if ranking_video_id and candidate["video_id"] == ranking_video_id else 1,
                0 if top_account_name and candidate["advertiser_name"] == top_account_name else 1,
                0 if top_plan_name and candidate["ad_name"] == top_plan_name else 1,
                -int(candidate["order_count"]),
                -float(candidate["pay_amount"]),
                -float(candidate["stat_cost"]),
            )
            candidates.append((score, candidate))

        if candidates:
            candidates.sort(key=lambda item: item[0])
            return [dict(item[1]) for item in candidates]

        advertiser_ids = [int(item) for item in row.get("advertiser_ids", []) if int(item or 0)]
        advertiser_id = advertiser_ids[0] if advertiser_ids else 0
        if ranking_material_id and advertiser_id:
            return [{
                "snapshot_time": "",
                "customer_center_id": self._current_customer_center_id(),
                "advertiser_id": advertiser_id,
                "advertiser_name": str(row.get("top_account_name") or "").strip(),
                "ad_id": 0,
                "ad_name": str(row.get("top_plan_name") or "").strip(),
                "material_type": str(row.get("material_type") or "VIDEO").strip().upper(),
                "material_key": str(row.get("material_key") or "").strip(),
                "material_id": ranking_material_id,
                "video_id": ranking_video_id,
                "aweme_item_id": ranking_aweme_item_id,
                "order_count": int(float(row.get("order_count", 0) or 0)),
                "pay_amount": round(float(row.get("pay_amount", 0.0) or 0.0), 2),
                "stat_cost": round(float(row.get("stat_cost", 0.0) or 0.0), 2),
                "source": "material_rankings.material_id",
            }]
        return []

    def _resolve_material_curve_source(
        self,
        row: dict[str, Any],
        start_date: str,
        end_date: str,
        snapshot_time: str,
        allowed_advertiser_ids: set[int] | None = None,
        *,
        search_all_customer_centers: bool = False,
    ) -> dict[str, Any] | None:
        candidates = self._material_curve_source_candidates(
            row,
            start_date,
            end_date,
            snapshot_time,
            allowed_advertiser_ids,
            search_all_customer_centers=search_all_customer_centers,
        )
        return dict(candidates[0]) if candidates else None

    def _material_preview_row_for_request(
        self,
        material_key: str,
        range_key: str = "day",
        start_date: str = "",
        end_date: str = "",
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
        user: dict[str, Any] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> tuple[dict[str, Any], bool]:
        material_key_text = str(material_key or "").strip()
        if not material_key_text:
            raise ValueError("material_key is required")

        role = str((user or {}).get("role") or "")
        search_all_customer_centers = self._display_scope_uses_all_customer_centers(display_scope)
        if role == ROLE_OPERATOR or search_all_customer_centers:
            rankings_payload = self._cross_customer_center_material_payload(
                range_key,
                start_date,
                end_date,
                snapshot_time,
                allowed_advertiser_ids,
            )
            search_all_customer_centers = True
            if role == ROLE_OPERATOR:
                scoped_payload = self._apply_material_scope(rankings_payload, user or {})
                row = next(
                    (
                        dict(item)
                        for item in scoped_payload.get("items", [])
                        if str(item.get("material_key") or "").strip() == material_key_text
                    ),
                    None,
                )
                if row is None:
                    row = next(
                        (
                            dict(item)
                            for item in rankings_payload.get("items", [])
                            if str(item.get("material_key") or "").strip() == material_key_text
                        ),
                        None,
                    )
            else:
                row = next(
                    (
                        dict(item)
                        for item in rankings_payload.get("items", [])
                        if str(item.get("material_key") or "").strip() == material_key_text
                    ),
                    None,
                )
        else:
            rankings_payload = self.material_rankings(range_key, start_date, end_date, snapshot_time, allowed_advertiser_ids)
            row = next(
                (
                    dict(item)
                    for item in rankings_payload.get("items", [])
                    if str(item.get("material_key") or "").strip() == material_key_text
                ),
                None,
            )
            if row is None:
                rankings_payload = self._cross_customer_center_material_payload(
                    range_key,
                    start_date,
                    end_date,
                    snapshot_time,
                    allowed_advertiser_ids,
                )
                search_all_customer_centers = True
                row = next(
                    (
                        dict(item)
                        for item in rankings_payload.get("items", [])
                        if str(item.get("material_key") or "").strip() == material_key_text
                    ),
                    None,
                )
        if row is None:
            raise ValueError("material not found in current material rankings")
        return row, search_all_customer_centers

    def material_preview_source(
        self,
        row: dict[str, Any] | None,
        range_key: str = "day",
        start_date: str = "",
        end_date: str = "",
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
        user: dict[str, Any] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> dict[str, Any]:
        seed_row = dict(row or {})
        material_key_text = str(seed_row.get("material_key") or "").strip()
        resolved_row: dict[str, Any]
        search_all_customer_centers = self._display_scope_uses_all_customer_centers(display_scope) or str((user or {}).get("role") or "") == ROLE_OPERATOR
        if material_key_text:
            try:
                resolved_row, search_all_customer_centers = self._material_preview_row_for_request(
                    material_key_text,
                    range_key,
                    start_date,
                    end_date,
                    snapshot_time,
                    allowed_advertiser_ids,
                    user,
                    display_scope,
                )
            except ValueError:
                if not seed_row:
                    raise
                resolved_row = seed_row
        elif seed_row:
            resolved_row = seed_row
        else:
            raise ValueError("material_key is required")

        merged_row = dict(resolved_row)
        for key, value in seed_row.items():
            if key not in merged_row or merged_row.get(key) in (None, ""):
                merged_row[key] = value

        current_video_url = self._normalize_media_url(merged_row.get("video_url"))
        resolved_current_video_url = self._resolve_preview_video_url(current_video_url)
        cover_url = self._normalize_media_url(merged_row.get("cover_url"))
        public_cover_url = self._coerce_public_preview_cover_url(cover_url)
        aweme_item_id = str(merged_row.get("aweme_item_id") or "").strip()
        video_id = str(merged_row.get("video_id") or "").strip()
        material_id = str(merged_row.get("material_id") or "").strip()
        result = {
            "material_key": str(merged_row.get("material_key") or "").strip(),
            "material_id": material_id,
            "video_id": video_id,
            "cover_url": public_cover_url,
            "aweme_item_id": aweme_item_id,
            "video_url": (
                resolved_current_video_url or current_video_url
                if self._is_public_preview_video_url(resolved_current_video_url or current_video_url)
                else ""
            ),
            "public_video_url": (resolved_current_video_url or current_video_url)
            if self._is_public_preview_video_url(resolved_current_video_url or current_video_url)
            else "",
            "is_public_video_url": self._is_public_preview_video_url(resolved_current_video_url or current_video_url),
            "source": "current_material_payload",
            "reason": "",
        }
        if result["is_public_video_url"]:
            return result
        current_proxy_video_url = self.build_material_preview_proxy_url(public_video_url)
        if current_proxy_video_url:
            result["video_url"] = current_proxy_video_url
            result["public_video_url"] = current_proxy_video_url
            result["is_public_video_url"] = True
            result["source"] = "current_material_payload_proxy"
            return result

        start_text = str(start_date or "").strip()
        end_text = str(end_date or "").strip()
        if not snapshot_time and (not start_text or not end_text):
            if str(range_key or "").strip().lower() == "custom":
                start_text = start_text or str(merged_row.get("create_time") or "")[:10]
                end_text = end_text or str(merged_row.get("create_time") or "")[:10]
            else:
                requested_start_dt, requested_end_dt, _label = self._material_preview_requested_window(
                    range_key,
                    start_date,
                    end_date,
                    snapshot_time,
                )
                start_text = requested_start_dt.strftime("%Y-%m-%d")
                end_text = requested_end_dt.strftime("%Y-%m-%d")
        resolved_source = self._resolve_material_curve_source(
            merged_row,
            start_text,
            end_text,
            snapshot_time,
            allowed_advertiser_ids,
            search_all_customer_centers=search_all_customer_centers,
        )
        if not resolved_source:
            result["reason"] = "当前素材未定位到可解析的视频来源。"
            if current_video_url and self._is_internal_preview_video_url(current_video_url):
                result["reason"] = "当前素材只返回千川站内预览地址，无法在外部页面直连播放。"
                result["source"] = "internal_video_url"
            elif not current_video_url and cover_url:
                result["reason"] = "当前素材仅返回封面图，未返回可直连视频地址。"
                result["source"] = "cover_only"
            return result

        customer_center_id = str(resolved_source.get("customer_center_id") or "").strip()
        advertiser_id = int(resolved_source.get("advertiser_id", 0) or 0)
        source_video_id = str(resolved_source.get("video_id") or video_id).strip()
        source_material_id = str(resolved_source.get("material_id") or material_id).strip()
        if not customer_center_id or advertiser_id <= 0:
            result["reason"] = "当前素材缺少可解析的视频来源配置。"
            return result

        client = self._build_scoped_customer_center_client(customer_center_id)
        if source_video_id:
            try:
                uploaded_video = client.get_uploaded_video(advertiser_id, source_video_id)
                public_video_url = self._preferred_video_url_from_values(
                    uploaded_video.get("url"),
                    uploaded_video.get("video_url"),
                    uploaded_video.get("videoUrl"),
                    uploaded_video.get("play_url"),
                    uploaded_video.get("playUrl"),
                    uploaded_video.get("download_url"),
                    uploaded_video.get("downloadUrl"),
                    uploaded_video.get("download_url_https"),
                    uploaded_video.get("downloadUrlHttps"),
                    uploaded_video.get("material_url"),
                    uploaded_video.get("materialUrl"),
                    current_video_url,
                )
                resolved_public_video_url = self._resolve_preview_video_url(public_video_url)
                if self._is_public_preview_video_url(resolved_public_video_url):
                    result["video_url"] = resolved_public_video_url
                    result["public_video_url"] = resolved_public_video_url
                    result["is_public_video_url"] = True
                    result["source"] = "file_video_ad_get"
                    poster_url = self._normalize_media_url(uploaded_video.get("poster_url") or uploaded_video.get("posterUrl"))
                    if poster_url:
                        result["cover_url"] = poster_url
                    return result
            except Exception as exc:  # noqa: BLE001
                if "permission" in str(exc).lower():
                    result["reason"] = "当前账号未授权公开视频文件接口，无法优先返回公网直链。"
                    result["source"] = "file_video_ad_get_permission_denied"

        if current_video_url and self._is_internal_preview_video_url(current_video_url):
            result["reason"] = result["reason"] or "当前素材只返回千川站内预览地址，无法在外部页面直连播放。"
            result["source"] = "internal_video_url"
        elif not current_video_url and cover_url:
            result["reason"] = result["reason"] or "当前素材仅返回封面图，未返回可直连视频地址。"
            result["source"] = "cover_only"
        elif source_material_id:
            result["reason"] = result["reason"] or "已尝试解析公网直链，但当前接口未返回可外部直连的视频文件地址。"
        return result

    def material_preview_source_v2(
        self,
        row: dict[str, Any] | None,
        range_key: str = "day",
        start_date: str = "",
        end_date: str = "",
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
        user: dict[str, Any] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> dict[str, Any]:
        seed_row = dict(row or {})
        material_key_text = str(seed_row.get("material_key") or "").strip()
        search_all_customer_centers = (
            self._display_scope_uses_all_customer_centers(display_scope)
            or str((user or {}).get("role") or "") == ROLE_OPERATOR
        )
        if material_key_text:
            try:
                resolved_row, search_all_customer_centers = self._material_preview_row_for_request(
                    material_key_text,
                    range_key,
                    start_date,
                    end_date,
                    snapshot_time,
                    allowed_advertiser_ids,
                    user,
                    display_scope,
                )
            except ValueError:
                if not seed_row:
                    raise
                resolved_row = seed_row
        elif seed_row:
            resolved_row = seed_row
        else:
            raise ValueError("material_key is required")

        merged_row = dict(resolved_row)
        for key, value in seed_row.items():
            if key not in merged_row or merged_row.get(key) in (None, ""):
                merged_row[key] = value

        current_video_url = self._normalize_media_url(merged_row.get("video_url"))
        resolved_current_video_url = self._resolve_preview_video_url(current_video_url)
        cover_url = self._normalize_media_url(merged_row.get("cover_url"))
        aweme_item_id = str(merged_row.get("aweme_item_id") or "").strip()
        video_id = str(merged_row.get("video_id") or "").strip()
        material_id = str(merged_row.get("material_id") or "").strip()
        public_video_url = resolved_current_video_url or current_video_url
        result = {
            "material_key": str(merged_row.get("material_key") or "").strip(),
            "material_id": material_id,
            "video_id": video_id,
            "cover_url": cover_url if self._is_public_preview_cover_url(cover_url) else "",
            "aweme_item_id": aweme_item_id,
            "video_url": public_video_url if self._is_public_preview_video_url(public_video_url) else "",
            "public_video_url": public_video_url if self._is_public_preview_video_url(public_video_url) else "",
            "is_public_video_url": self._is_public_preview_video_url(public_video_url),
            "source": "current_material_payload",
            "reason": "",
        }
        if result["is_public_video_url"]:
            return result

        start_text = str(start_date or "").strip()
        end_text = str(end_date or "").strip()
        if not snapshot_time and (not start_text or not end_text):
            if str(range_key or "").strip().lower() == "custom":
                start_text = start_text or str(merged_row.get("create_time") or "")[:10]
                end_text = end_text or str(merged_row.get("create_time") or "")[:10]
            else:
                requested_start_dt, requested_end_dt, _label = self._material_preview_requested_window(
                    range_key,
                    start_date,
                    end_date,
                    snapshot_time,
                )
                start_text = requested_start_dt.strftime("%Y-%m-%d")
                end_text = requested_end_dt.strftime("%Y-%m-%d")

        resolved_sources = self._material_curve_source_candidates(
            merged_row,
            start_text,
            end_text,
            snapshot_time,
            allowed_advertiser_ids,
            search_all_customer_centers=search_all_customer_centers,
        )
        if not resolved_sources:
            result["reason"] = "当前素材未定位到可解析的预览来源。"
            if current_video_url and self._needs_preview_video_redirect_resolution(current_video_url):
                result["reason"] = "当前素材返回的是千川中转预览地址，无法直接在浏览器中播放。"
                result["source"] = "redirect_preview_video_url"
            elif current_video_url and self._is_internal_preview_video_url(current_video_url):
                result["reason"] = "当前素材只返回站内预览地址，无法在外部页面直接播放。"
                result["source"] = "internal_video_url"
            elif cover_url and not self._is_public_preview_cover_url(cover_url):
                result["reason"] = "当前素材仅返回受限封面图地址，浏览器无法直接加载。"
                result["source"] = "restricted_cover_url"
            elif not current_video_url and cover_url:
                result["reason"] = "当前素材仅返回封面图，未返回可直接播放的视频地址。"
                result["source"] = "cover_only"
            return result

        attempted_sources = 0
        any_source_material_id = False
        for resolved_source in resolved_sources:
            customer_center_id = str(resolved_source.get("customer_center_id") or "").strip()
            advertiser_id = int(resolved_source.get("advertiser_id", 0) or 0)
            source_video_id = str(resolved_source.get("video_id") or video_id).strip()
            source_material_id = str(resolved_source.get("material_id") or material_id).strip()
            if source_material_id:
                any_source_material_id = True
            if not customer_center_id or advertiser_id <= 0:
                continue
            attempted_sources += 1
            client = self._build_scoped_customer_center_client(customer_center_id)
            if source_video_id:
                try:
                    uploaded_video = client.get_uploaded_video(advertiser_id, source_video_id)
                    candidate_video_url = self._preferred_video_url_from_values(
                        uploaded_video.get("url"),
                        uploaded_video.get("video_url"),
                        uploaded_video.get("videoUrl"),
                        uploaded_video.get("play_url"),
                        uploaded_video.get("playUrl"),
                        uploaded_video.get("download_url"),
                        uploaded_video.get("downloadUrl"),
                        uploaded_video.get("download_url_https"),
                        uploaded_video.get("downloadUrlHttps"),
                        uploaded_video.get("material_url"),
                        uploaded_video.get("materialUrl"),
                        current_video_url,
                    )
                    resolved_public_video_url = self._resolve_preview_video_url(candidate_video_url)
                    if self._is_public_preview_video_url(resolved_public_video_url):
                        result["video_url"] = resolved_public_video_url
                        result["public_video_url"] = resolved_public_video_url
                        result["is_public_video_url"] = True
                        result["source"] = "file_video_ad_get"
                        result["reason"] = ""
                        poster_url = self._coerce_public_preview_cover_url(
                            uploaded_video.get("poster_url") or uploaded_video.get("posterUrl")
                        )
                        if poster_url:
                            result["cover_url"] = poster_url
                        return result
                    proxy_video_url = self.build_material_preview_proxy_url(candidate_video_url)
                    if proxy_video_url:
                        result["video_url"] = proxy_video_url
                        result["public_video_url"] = proxy_video_url
                        result["is_public_video_url"] = True
                        result["source"] = "file_video_ad_get_proxy"
                        result["reason"] = ""
                        poster_url = self._coerce_public_preview_cover_url(
                            uploaded_video.get("poster_url") or uploaded_video.get("posterUrl")
                        )
                        if poster_url:
                            result["cover_url"] = poster_url
                        return result
                except Exception as exc:  # noqa: BLE001
                    message = str(exc)
                    lowered = message.lower()
                    if "permission" in lowered and not result["reason"]:
                        result["reason"] = "当前账号未授权公开视频接口，无法优先返回公网直链。"
                        result["source"] = "file_video_ad_get_permission_denied"
                    elif ("refresh_token" in lowered or "40103" in message or "已过期" in message) and not result["reason"]:
                        result["reason"] = "素材所属客服中心授权已过期，当前无法解析可外部访问的预览地址。"
                        result["source"] = "file_video_ad_get_token_expired"
                try:
                    video_rows = client.list_qianchuan_videos(
                        advertiser_id=advertiser_id,
                        filtering={"video_ids": [source_video_id]},
                        page_size=20,
                        max_pages=1,
                    )
                    for item in video_rows:
                        resolved_library_video_id = str(item.get("id") or item.get("video_id") or item.get("videoId") or "").strip()
                        if resolved_library_video_id and resolved_library_video_id != source_video_id:
                            continue
                        candidate_video_url = self._preferred_video_url_from_values(
                            item.get("url"),
                            item.get("video_url"),
                            item.get("videoUrl"),
                            item.get("play_url"),
                            item.get("playUrl"),
                            current_video_url,
                        )
                        resolved_library_video_url = self._resolve_preview_video_url(candidate_video_url)
                        if self._is_public_preview_video_url(resolved_library_video_url):
                            result["video_url"] = resolved_library_video_url
                            result["public_video_url"] = resolved_library_video_url
                            result["is_public_video_url"] = True
                            result["source"] = "qianchuan_video_get"
                            result["reason"] = ""
                            poster_url = self._coerce_public_preview_cover_url(
                                item.get("poster_url") or item.get("posterUrl") or cover_url
                            )
                            if poster_url:
                                result["cover_url"] = poster_url
                            return result
                        proxy_video_url = self.build_material_preview_proxy_url(candidate_video_url)
                        if proxy_video_url:
                            result["video_url"] = proxy_video_url
                            result["public_video_url"] = proxy_video_url
                            result["is_public_video_url"] = True
                            result["source"] = "qianchuan_video_get_proxy"
                            result["reason"] = ""
                            poster_url = self._coerce_public_preview_cover_url(
                                item.get("poster_url") or item.get("posterUrl") or cover_url
                            )
                            if poster_url:
                                result["cover_url"] = poster_url
                            return result
                        poster_url = self._coerce_public_preview_cover_url(
                            item.get("poster_url") or item.get("posterUrl") or cover_url
                        )
                        if poster_url and not result["cover_url"]:
                            result["cover_url"] = poster_url
                except Exception:
                    pass

        if attempted_sources <= 0:
            result["reason"] = "当前素材缺少可解析的预览来源配置。"
            return result

        if current_video_url and self._needs_preview_video_redirect_resolution(current_video_url):
            result["reason"] = result["reason"] or "当前素材返回的是千川中转预览地址，无法直接在浏览器中播放。"
            result["source"] = "redirect_preview_video_url"
        elif current_video_url and self._is_internal_preview_video_url(current_video_url):
            result["reason"] = result["reason"] or "当前素材只返回站内预览地址，无法在外部页面直接播放。"
            result["source"] = "internal_video_url"
        elif cover_url and not self._is_public_preview_cover_url(cover_url):
            result["reason"] = result["reason"] or "当前素材仅返回受限封面图地址，浏览器无法直接加载。"
            result["source"] = "restricted_cover_url"
        elif not current_video_url and cover_url:
            result["reason"] = result["reason"] or "当前素材仅返回封面图，未返回可直接播放的视频地址。"
            result["source"] = "cover_only"
        elif any_source_material_id:
            result["reason"] = result["reason"] or "已尝试解析公网直链，但当前接口未返回可外部访问的视频文件地址。"
        return result

    def material_preview_curve(
        self,
        material_key: str,
        range_key: str = "day",
        start_date: str = "",
        end_date: str = "",
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
        user: dict[str, Any] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> dict[str, Any]:
        material_key_text = str(material_key or "").strip()
        row, search_all_customer_centers = self._material_preview_row_for_request(
            material_key_text,
            range_key,
            start_date,
            end_date,
            snapshot_time,
            allowed_advertiser_ids,
            user,
            display_scope,
        )

        material_type = str(row.get("material_type") or "").strip().upper()
        advertiser_ids = [int(item) for item in row.get("advertiser_ids", []) if int(item or 0)]
        advertiser_id = advertiser_ids[0] if advertiser_ids else 0

        requested_start_dt, requested_end_dt, requested_range_label = self._material_preview_requested_window(
            range_key,
            start_date,
            end_date,
            snapshot_time,
        )
        config = self.read_config()
        tz = ZoneInfo(str(config.get("timezone") or TIMEZONE))
        latest_available_day = (datetime.now(tz) - timedelta(days=1)).date()
        latest_available_start = datetime(
            latest_available_day.year,
            latest_available_day.month,
            latest_available_day.day,
            0,
            0,
            0,
            tzinfo=tz,
        )
        latest_available_end = datetime(
            latest_available_day.year,
            latest_available_day.month,
            latest_available_day.day,
            23,
            59,
            59,
            tzinfo=tz,
        )

        response_payload: dict[str, Any] = {
            "material_key": material_key_text,
            "material_id": str(row.get("material_id") or ""),
            "material_name": str(row.get("material_name") or ""),
            "material_type": material_type,
            "advertiser_id": advertiser_id,
            "curve_material_id": "",
            "curve_advertiser_id": 0,
            "curve_ad_id": 0,
            "material_id_source": "",
            "advertiser_count": len(advertiser_ids),
            "top_account_name": str(row.get("top_account_name") or ""),
            "supported": material_type == "VIDEO",
            "t_plus_one_only": True,
            "range_key": str(range_key or "day"),
            "range_label": str(requested_range_label or ""),
            "requested_start_date": requested_start_dt.strftime("%Y-%m-%d"),
            "requested_end_date": requested_end_dt.strftime("%Y-%m-%d"),
            "query_start_date": "",
            "query_end_date": "",
            "is_clamped_to_yesterday": False,
            "notice": "",
            "message": "",
            "series": [],
            "totals": {
                "click_cnt": 0,
                "user_lose_cnt": 0,
            },
            "peak": {
                "second": 0,
                "click_cnt": 0,
                "user_lose_cnt": 0,
            },
            "duration_seconds": 0,
            "point_count": 0,
        }

        if material_type != "VIDEO":
            response_payload["message"] = "仅视频素材支持互动峰形图。"
            return response_payload

        query_start_dt = requested_start_dt
        query_end_dt = min(requested_end_dt, latest_available_end)
        clamped = query_end_dt < requested_end_dt
        target_snapshot = str(snapshot_time or "").strip()
        normalized_range = str(range_key or "day").strip().lower()
        if query_start_dt > query_end_dt:
            if not target_snapshot and normalized_range == "day":
                query_start_dt = latest_available_start
                query_end_dt = latest_available_end
                clamped = True
            else:
                response_payload["query_start_date"] = requested_start_dt.strftime("%Y-%m-%d")
                response_payload["query_end_date"] = requested_end_dt.strftime("%Y-%m-%d")
                response_payload["is_clamped_to_yesterday"] = clamped
                response_payload["message"] = "当前筛选范围内没有可查询的 T+1 数据。"
                if clamped:
                    response_payload["notice"] = f"该接口仅支持 T+1 数据，最近可查询日期为 {latest_available_day.isoformat()}。"
                return response_payload

        response_payload["query_start_date"] = query_start_dt.strftime("%Y-%m-%d")
        response_payload["query_end_date"] = query_end_dt.strftime("%Y-%m-%d")
        response_payload["is_clamped_to_yesterday"] = clamped

        resolved_source = self._resolve_material_curve_source(
            row,
            response_payload["query_start_date"],
            response_payload["query_end_date"],
            snapshot_time,
            allowed_advertiser_ids,
            search_all_customer_centers=search_all_customer_centers,
        )
        if resolved_source:
            response_payload["curve_material_id"] = str(resolved_source.get("material_id") or "")
            response_payload["curve_advertiser_id"] = int(resolved_source.get("advertiser_id", 0) or 0)
            response_payload["curve_ad_id"] = int(resolved_source.get("ad_id", 0) or 0)
            response_payload["material_id_source"] = str(resolved_source.get("source") or "")
        if not response_payload["curve_material_id"]:
            response_payload["message"] = "未找到可用于峰形图查询的素材唯一 ID。"
            return response_payload
        if not response_payload["curve_advertiser_id"]:
            response_payload["message"] = "未找到可用于峰形图查询的投放账户 ID。"
            return response_payload

        notices: list[str] = []
        if clamped:
            notices.append(f"该接口仅支持 T+1 数据，当前展示截至 {latest_available_day.isoformat()} 的数据。")
        if len(advertiser_ids) > 1:
            account_name = str(row.get("top_account_name") or "").strip()
            if account_name:
                notices.append(f"该素材被多个账户复用，当前仅展示账户 {account_name} 的曲线。")
            else:
                notices.append("该素材被多个账户复用，当前仅展示其中一个账户的曲线。")

        client = self.build_client(config)
        response = client.get_video_user_lose(
            advertiser_id=int(response_payload["curve_advertiser_id"]),
            material_id=response_payload["curve_material_id"],
            start_date=response_payload["query_start_date"],
            end_date=response_payload["query_end_date"],
        )
        points = self._normalize_video_user_lose_rows(response)
        response_payload["series"] = [
            {
                "second": int(point["second"]),
                "click_cnt": int(round(point["click_cnt"])),
                "user_lose_cnt": int(round(point["user_lose_cnt"])),
            }
            for point in points
        ]
        response_payload["duration_seconds"] = int(max((point["second"] for point in points), default=0))
        response_payload["point_count"] = len(points)
        response_payload["totals"] = {
            "click_cnt": int(round(sum(point["click_cnt"] for point in points))),
            "user_lose_cnt": int(round(sum(point["user_lose_cnt"] for point in points))),
        }
        peak_point = max(
            response_payload["series"],
            key=lambda item: (int(item["user_lose_cnt"]), int(item["click_cnt"]), -int(item["second"])),
            default={"second": 0, "click_cnt": 0, "user_lose_cnt": 0},
        )
        response_payload["peak"] = {
            "second": int(peak_point["second"]),
            "click_cnt": int(peak_point["click_cnt"]),
            "user_lose_cnt": int(peak_point["user_lose_cnt"]),
        }
        if not response_payload["series"]:
            response_payload["message"] = "接口未返回该素材的秒级互动分布数据。"
        if notices:
            response_payload["notice"] = " ".join(notices)
        return response_payload

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
        config = self.read_config()
        if not target_snapshot:
            if normalized not in PERFORMANCE_RANGES:
                raise ValueError("range must be one of day/yesterday/week/month/custom")
            if normalized == "custom":
                start_dt, end_dt, range_label = build_custom_performance_window(start_date, end_date, config["timezone"])
            else:
                start_dt, end_dt, range_label = build_performance_window(normalized, config["timezone"])
        cache_key = build_material_cache_key(
            range_key,
            start_date,
            end_date,
            snapshot_time,
            allowed_advertiser_ids,
            self._current_customer_center_id(),
        )
        cache_version = self._shared_cache_version("material")
        versioned_cache_key = self._versioned_cache_key(cache_version, cache_key)
        now_ts = time.time()
        cached_payload = self._local_dict_cache_get(self._material_cache, versioned_cache_key, RANGE_CACHE_SECONDS)
        if cached_payload is None:
            cached_payload = self._shared_dict_cache_get("material", cache_key, cache_version)
            if cached_payload is not None:
                self._local_dict_cache_set(self._material_cache, versioned_cache_key, cached_payload)
        if cached_payload is not None:
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
            customer_center_id = self._current_customer_center_id()
            if not target_snapshot:
                assert start_dt is not None and end_dt is not None
                if normalized in {"yesterday", "week", "month", "custom"}:
                    missing_days = len(self._missing_extended_days(conn, start_dt, end_dt))
                runs = self._latest_extended_sync_runs_for_window(conn, start_dt, end_dt)
                if not runs:
                    latest_run = self._latest_extended_sync_run(conn)
                    if latest_run:
                        runs = [dict(latest_run)]
                    else:
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
                    "snapshot_fallback_used": False,
                }
            else:
                latest_meta_row = conn.execute(
                    """
                    SELECT *
                    FROM extended_sync_runs
                    WHERE snapshot_time = ?
                      AND customer_center_id = ?
                    LIMIT 1
                    """,
                    (target_snapshot, customer_center_id),
                ).fetchone()
                latest_meta = dict(latest_meta_row) if latest_meta_row else None
                snapshot_times = [target_snapshot]
                normalized = "custom" if snapshot_time else str(range_key or "day").strip().lower()
                range_label = "指定快照" if snapshot_time else ""

            def load_items_for_snapshot_times(selected_snapshot_times: list[str]) -> list[dict[str, Any]]:
                placeholders = ",".join("?" for _ in selected_snapshot_times)
                rollup_rows = conn.execute(
                    f"""
                    SELECT
                        *
                    FROM material_rollups
                    WHERE snapshot_time IN ({placeholders})
                      AND customer_center_id = ?
                    ORDER BY snapshot_time DESC, create_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC
                    """,
                    [*selected_snapshot_times, customer_center_id],
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
                            m.create_time,
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
                         AND v.customer_center_id = m.customer_center_id
                         AND v.advertiser_id = m.advertiser_id
                         AND v.material_id = m.material_id
                        WHERE m.snapshot_time IN ({placeholders})
                          AND m.customer_center_id = ?
                        ORDER BY m.snapshot_time DESC, m.create_time DESC, m.order_count DESC, m.pay_amount DESC, m.roi DESC, m.stat_cost DESC
                        """,
                        [*selected_snapshot_times, customer_center_id],
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
                    if not target_snapshot:
                        scoped_rollup_rows = self._filter_material_rows_by_create_time_window(
                            scoped_rollup_rows,
                            start_dt,
                            end_dt,
                            str(config.get("timezone") or TIMEZONE),
                        )
                    return self._aggregate_material_rollups(scoped_rollup_rows)
                scoped_rows = [dict(row) for row in fallback_rows]
                if allowed_advertiser_ids is not None:
                    allowed = {int(item) for item in allowed_advertiser_ids}
                    scoped_rows = [row for row in scoped_rows if int(row.get("advertiser_id", 0) or 0) in allowed]
                if not target_snapshot:
                    scoped_rows = self._filter_material_rows_by_create_time_window(
                        scoped_rows,
                        start_dt,
                        end_dt,
                        str(config.get("timezone") or TIMEZONE),
                    )
                return self._build_material_rankings(scoped_rows)

            items = load_items_for_snapshot_times(snapshot_times)
            if not target_snapshot and not items:
                latest_run = self._latest_extended_sync_run(conn)
                latest_snapshot = str(dict(latest_run).get("snapshot_time") or "").strip() if latest_run else ""
                if latest_snapshot and latest_snapshot not in snapshot_times:
                    fallback_items = load_items_for_snapshot_times([latest_snapshot])
                    if fallback_items:
                        snapshot_times = [latest_snapshot]
                        items = fallback_items
                        latest_meta = dict(latest_run)
                        latest_meta["snapshot_fallback_used"] = True
        if items:
            with self.db() as preview_conn:
                items = self._apply_material_snapshot_context(preview_conn, items, snapshot_times, allowed_advertiser_ids)
                items = self._apply_latest_material_previews(preview_conn, items)
                items = self._apply_material_top_anchor_names(preview_conn, items, snapshot_times)
            items = self._sanitize_material_preview_fields_for_payload(items)
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
        self._local_dict_cache_set(self._material_cache, versioned_cache_key, payload)
        self._shared_dict_cache_set("material", cache_key, cache_version, payload, RANGE_CACHE_SECONDS)
        return payload

    def material_rankings_for_user(
        self,
        user: dict[str, Any] | None,
        range_key: str = "day",
        start_date: str = "",
        end_date: str = "",
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> dict[str, Any]:
        role = str((user or {}).get("role") or "")
        if role == ROLE_OPERATOR or self._display_scope_uses_all_customer_centers(display_scope):
            payload = self._cross_customer_center_material_payload(
                range_key,
                start_date,
                end_date,
                snapshot_time,
                allowed_advertiser_ids,
            )
            return self._apply_material_scope(payload, user or {}) if role == ROLE_OPERATOR else payload
        return self.material_rankings(range_key, start_date, end_date, snapshot_time, allowed_advertiser_ids)

    def team_material_rankings_for_user(
        self,
        user: dict[str, Any] | None,
        range_key: str = "day",
        start_date: str = "",
        end_date: str = "",
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> dict[str, Any]:
        role = str((user or {}).get("role") or "")
        if role == ROLE_OPERATOR or self._display_scope_uses_all_customer_centers(display_scope):
            return self._cross_customer_center_material_payload(
                range_key,
                start_date,
                end_date,
                snapshot_time,
                allowed_advertiser_ids,
            )
        return self.material_rankings(range_key, start_date, end_date, snapshot_time, allowed_advertiser_ids)

    def _apply_material_snapshot_context_for_pairs(
        self,
        conn: Any,
        items: list[dict[str, Any]],
        selected_pairs: set[tuple[str, str]],
        allowed_advertiser_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        if not items or not selected_pairs:
            return items
        snapshot_times = sorted(
            {
                str(snapshot_time or "").strip()
                for _customer_center_id, snapshot_time in selected_pairs
                if str(snapshot_time or "").strip()
            }
        )
        material_keys = sorted(
            {
                str(item.get("material_key") or "").strip()
                for item in items
                if str(item.get("material_key") or "").strip()
            }
        )
        if not snapshot_times or not material_keys:
            return items
        clauses = [
            f"snapshot_time IN ({','.join('?' for _ in snapshot_times)})",
            f"material_key IN ({','.join('?' for _ in material_keys)})",
        ]
        params: list[Any] = [*snapshot_times, *material_keys]
        if allowed_advertiser_ids is not None:
            allowed = sorted(int(item) for item in allowed_advertiser_ids if int(item or 0))
            if allowed:
                clauses.append(f"advertiser_id IN ({','.join('?' for _ in allowed)})")
                params.extend(allowed)
        rows = conn.execute(
            f"""
            SELECT snapshot_time, customer_center_id, material_key, product_show_count, product_click_count, raw_json
            FROM material_snapshots
            WHERE {" AND ".join(clauses)}
            """,
            params,
        ).fetchall()
        context_by_key: dict[str, dict[str, Any]] = {}
        for raw_row in rows:
            row = dict(raw_row)
            pair = (
                str(row.get("customer_center_id") or "").strip(),
                str(row.get("snapshot_time") or "").strip(),
            )
            if pair not in selected_pairs:
                continue
            material_key = str(row.get("material_key") or "").strip()
            if not material_key:
                continue
            group = context_by_key.setdefault(
                material_key,
                {
                    "product_show_count": 0,
                    "product_click_count": 0,
                    "product_names": [],
                },
            )
            group["product_show_count"] += int(row.get("product_show_count", 0) or 0)
            group["product_click_count"] += int(row.get("product_click_count", 0) or 0)
            for name in self._extract_material_product_names(row.get("raw_json")):
                if name not in group["product_names"]:
                    group["product_names"].append(name)
        for item in items:
            context = context_by_key.get(str(item.get("material_key") or "").strip())
            if not context:
                continue
            show_count = int(context.get("product_show_count", 0) or 0)
            click_count = int(context.get("product_click_count", 0) or 0)
            item["product_info_text"] = self._summarize_material_product_names(list(context.get("product_names") or []))
            item["overall_show_count"] = show_count
            item["overall_click_count"] = click_count
            item["overall_ctr"] = round(click_count / show_count * 100.0, 2) if show_count > 0 else 0.0
        return items

    def _apply_material_top_anchor_names_for_pairs(
        self,
        conn: Any,
        items: list[dict[str, Any]],
        selected_pairs: set[tuple[str, str]],
    ) -> list[dict[str, Any]]:
        if not items or not selected_pairs:
            return items
        unresolved_keys = {
            (
                str(item.get("top_account_name") or "").strip(),
                str(item.get("top_plan_name") or "").strip(),
            )
            for item in items
            if not str(item.get("top_anchor_name") or "").strip()
            and str(item.get("top_account_name") or "").strip()
            and str(item.get("top_plan_name") or "").strip()
        }
        if not unresolved_keys:
            return items
        snapshot_times = sorted(
            {
                str(snapshot_time or "").strip()
                for _customer_center_id, snapshot_time in selected_pairs
                if str(snapshot_time or "").strip()
            }
        )
        if not snapshot_times:
            return items
        placeholders = ",".join("?" for _ in snapshot_times)
        rows = conn.execute(
            f"""
            SELECT snapshot_time, customer_center_id, advertiser_name, ad_name, anchor_name, ad_id
            FROM plan_snapshots
            WHERE snapshot_time IN ({placeholders})
              AND COALESCE(anchor_name, '') <> ''
            ORDER BY snapshot_time DESC, ad_id DESC
            """,
            snapshot_times,
        ).fetchall()
        anchor_map: dict[tuple[str, str], str] = {}
        for raw_row in rows:
            row = dict(raw_row)
            pair = (
                str(row.get("customer_center_id") or "").strip(),
                str(row.get("snapshot_time") or "").strip(),
            )
            if pair not in selected_pairs:
                continue
            key = (
                str(row.get("advertiser_name") or "").strip(),
                str(row.get("ad_name") or "").strip(),
            )
            if key not in unresolved_keys or key in anchor_map:
                continue
            anchor_name = str(row.get("anchor_name") or "").strip()
            if anchor_name:
                anchor_map[key] = anchor_name
        if not anchor_map:
            return items
        enriched_items: list[dict[str, Any]] = []
        for item in items:
            enriched = dict(item)
            if not str(enriched.get("top_anchor_name") or "").strip():
                enriched["top_anchor_name"] = anchor_map.get(
                    (
                        str(enriched.get("top_account_name") or "").strip(),
                        str(enriched.get("top_plan_name") or "").strip(),
                    ),
                    "",
                )
            enriched_items.append(enriched)
        return enriched_items

    def _cross_customer_center_material_payload(
        self,
        range_key: str = "day",
        start_date: str = "",
        end_date: str = "",
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        target_snapshot = str(snapshot_time or "").strip()
        normalized = str(range_key or "day").strip().lower()
        config = self.read_config()
        tz_name = str(config.get("timezone") or TIMEZONE)
        if target_snapshot:
            snapshot_day = _parse_date_input(target_snapshot[:10], "snapshot_time")
            tz = ZoneInfo(tz_name)
            start_dt = datetime(snapshot_day.year, snapshot_day.month, snapshot_day.day, 0, 0, 0, tzinfo=tz)
            end_dt = datetime(snapshot_day.year, snapshot_day.month, snapshot_day.day, 23, 59, 59, tzinfo=tz)
            range_label = "鎸囧畾蹇収"
            range_label = "Specified snapshot"
            normalized = "custom"
        else:
            if normalized not in PERFORMANCE_RANGES:
                raise ValueError("range must be one of day/yesterday/week/month/custom")
            if normalized == "custom":
                start_dt, end_dt, range_label = build_custom_performance_window(start_date, end_date, tz_name)
            else:
                start_dt, end_dt, range_label = build_performance_window(normalized, tz_name)

        cache_key = build_material_cache_key(
            normalized,
            start_dt.strftime("%Y-%m-%d"),
            end_dt.strftime("%Y-%m-%d"),
            target_snapshot,
            allowed_advertiser_ids,
            "__all_customer_centers__",
        )
        cache_version = self._shared_cache_version("material")
        versioned_cache_key = self._versioned_cache_key(cache_version, cache_key)
        now_ts = time.time()
        cached_payload = self._local_dict_cache_get(self._material_cache, versioned_cache_key, RANGE_CACHE_SECONDS)
        if cached_payload is None:
            cached_payload = self._shared_dict_cache_get("material", cache_key, cache_version)
            if cached_payload is not None:
                self._local_dict_cache_set(self._material_cache, versioned_cache_key, cached_payload)
        if cached_payload is not None:
            return cached_payload

        with self.db() as conn:
            run_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT
                        customer_center_id,
                        snapshot_time,
                        status,
                        plan_count,
                        detail_count,
                        product_row_count,
                        material_row_count,
                        original_video_row_count,
                        error_count
                    FROM extended_sync_runs
                    WHERE status IN ('ok', 'partial')
                      AND snapshot_time >= ?
                      AND snapshot_time <= ?
                    ORDER BY snapshot_time DESC, customer_center_id ASC
                    """,
                    (
                        start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                ).fetchall()
            ]
            runs = self._latest_rows_by_customer_center_day(run_rows)
            if not runs:
                payload = {
                    "snapshot_time": target_snapshot,
                    "items": [],
                    "meta": None,
                    "snapshot_count": 0,
                    "customer_center_count": 0,
                    "range_key": normalized,
                    "range_label": range_label,
                    "query_start_date": start_dt.strftime("%Y-%m-%d"),
                    "query_end_date": end_dt.strftime("%Y-%m-%d"),
                }
                self._local_dict_cache_set(self._material_cache, versioned_cache_key, payload)
                self._shared_dict_cache_set("material", cache_key, cache_version, payload, RANGE_CACHE_SECONDS)
                return payload

            selected_pairs = {
                (
                    str(item.get("customer_center_id") or "").strip(),
                    str(item.get("snapshot_time") or "").strip(),
                )
                for item in runs
                if str(item.get("customer_center_id") or "").strip() and str(item.get("snapshot_time") or "").strip()
            }
            snapshot_times = sorted({snapshot for _customer_center_id, snapshot in selected_pairs})
            meta = {
                "snapshot_time": str(runs[-1].get("snapshot_time") or target_snapshot) if runs else target_snapshot,
                "status": "partial" if any(str(item.get("status") or "") != "ok" for item in runs) else "ok",
                "plan_count": sum(int(item.get("plan_count") or 0) for item in runs),
                "detail_count": sum(int(item.get("detail_count") or 0) for item in runs),
                "product_count": sum(int(item.get("product_count") or item.get("product_row_count") or 0) for item in runs),
                "material_count": sum(int(item.get("material_count") or item.get("material_row_count") or 0) for item in runs),
                "video_count": sum(int(item.get("video_count") or item.get("original_video_row_count") or 0) for item in runs),
                "error_count": sum(int(item.get("error_count") or 0) for item in runs),
                "snapshot_dates": sorted(
                    {
                        str(item.get("snapshot_time") or "")[:10]
                        for item in runs
                        if str(item.get("snapshot_time") or "").strip()
                    }
                ),
                "snapshot_fallback_used": False,
            }
            placeholders = ",".join("?" for _ in snapshot_times)

            rollup_rows = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT *
                    FROM material_rollups
                    WHERE snapshot_time IN ({placeholders})
                    ORDER BY snapshot_time DESC, create_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC
                    """,
                    snapshot_times,
                ).fetchall()
            ]
            scoped_rollup_rows = [
                row
                for row in rollup_rows
                if (
                    str(row.get("customer_center_id") or "").strip(),
                    str(row.get("snapshot_time") or "").strip(),
                )
                in selected_pairs
            ]
            if allowed_advertiser_ids is not None:
                allowed = {int(item) for item in allowed_advertiser_ids}
                scoped_rollup_rows = [
                    row
                    for row in scoped_rollup_rows
                    if any(int(item) in allowed for item in json.loads(str(row.get("advertiser_ids_json") or "[]")))
                ]
            if not target_snapshot:
                scoped_rollup_rows = self._filter_material_rows_by_create_time_window(
                    scoped_rollup_rows,
                    start_dt,
                    end_dt,
                    tz_name,
                )

            if scoped_rollup_rows:
                items = self._aggregate_material_rollups(scoped_rollup_rows)
            else:
                snapshot_rows = [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT
                            m.snapshot_time,
                            m.customer_center_id,
                            m.advertiser_id,
                            m.advertiser_name,
                            m.ad_id,
                            m.ad_name,
                            m.material_type,
                            m.material_key,
                            m.material_id,
                            m.material_name,
                            m.create_time,
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
                         AND v.customer_center_id = m.customer_center_id
                         AND v.advertiser_id = m.advertiser_id
                         AND v.material_id = m.material_id
                        WHERE m.snapshot_time IN ({placeholders})
                        ORDER BY m.snapshot_time DESC, m.create_time DESC, m.order_count DESC, m.pay_amount DESC, m.roi DESC, m.stat_cost DESC
                        """,
                        snapshot_times,
                    ).fetchall()
                ]
                scoped_snapshot_rows = [
                    row
                    for row in snapshot_rows
                    if (
                        str(row.get("customer_center_id") or "").strip(),
                        str(row.get("snapshot_time") or "").strip(),
                    )
                    in selected_pairs
                ]
                if allowed_advertiser_ids is not None:
                    allowed = {int(item) for item in allowed_advertiser_ids}
                    scoped_snapshot_rows = [
                        row for row in scoped_snapshot_rows if int(row.get("advertiser_id", 0) or 0) in allowed
                    ]
                if not target_snapshot:
                    scoped_snapshot_rows = self._filter_material_rows_by_create_time_window(
                        scoped_snapshot_rows,
                        start_dt,
                        end_dt,
                        tz_name,
                    )
                items = self._build_material_rankings(scoped_snapshot_rows)

        if items:
            with self.db() as preview_conn:
                items = self._apply_material_snapshot_context_for_pairs(
                    preview_conn,
                    items,
                    selected_pairs,
                    allowed_advertiser_ids,
                )
                items = self._apply_latest_material_previews(preview_conn, items)
                items = self._apply_material_top_anchor_names_for_pairs(preview_conn, items, selected_pairs)
            items = self._sanitize_material_preview_fields_for_payload(items)

        payload = {
            "snapshot_time": str(runs[-1].get("snapshot_time") or target_snapshot) if runs else target_snapshot,
            "items": items,
            "meta": meta,
            "snapshot_count": len(selected_pairs),
            "customer_center_count": len({customer_center_id for customer_center_id, _snapshot in selected_pairs}),
            "range_key": normalized,
            "range_label": range_label,
            "query_start_date": start_dt.strftime("%Y-%m-%d"),
            "query_end_date": end_dt.strftime("%Y-%m-%d"),
        }
        self._local_dict_cache_set(self._material_cache, versioned_cache_key, payload)
        self._shared_dict_cache_set("material", cache_key, cache_version, payload, RANGE_CACHE_SECONDS)
        return payload

    def _apply_material_operator_rankings(
        self,
        payload: dict[str, Any],
        *,
        allowed_advertiser_ids: set[int] | None = None,
        range_key: str = "",
        start_date: str = "",
        end_date: str = "",
        snapshot_time: str = "",
    ) -> dict[str, Any]:
        if not payload:
            return payload
        normalized_range = str(range_key or payload.get("range_key") or "").strip().lower()
        query_start_date = str(start_date or payload.get("query_start_date") or "").strip()
        query_end_date = str(end_date or payload.get("query_end_date") or "").strip()
        target_snapshot = str(snapshot_time or "").strip()
        material_payload: dict[str, Any]
        if normalized_range:
            material_payload = self._cross_customer_center_material_payload(
                normalized_range,
                query_start_date,
                query_end_date,
                "",
                allowed_advertiser_ids,
            )
        else:
            target_snapshot = target_snapshot or str(payload.get("snapshot_time") or "").strip()
            if not target_snapshot:
                return payload
            material_payload = self._cross_customer_center_material_payload(
                "day",
                "",
                "",
                target_snapshot,
                allowed_advertiser_ids,
            )
        operators = self._build_operator_rankings_from_materials(material_payload.get("items", []))
        next_payload = dict(payload)
        next_payload["operators"] = operators
        summary = dict(next_payload.get("summary") or {})
        summary["operator_count"] = len(operators)
        summary["active_operator_count"] = sum(1 for item in operators if float(item.get("stat_cost", 0.0) or 0.0) > 0)
        next_payload["summary"] = summary
        return next_payload

    def _safe_apply_material_operator_rankings(
        self,
        payload: dict[str, Any],
        *,
        allowed_advertiser_ids: set[int] | None = None,
        range_key: str = "",
        start_date: str = "",
        end_date: str = "",
        snapshot_time: str = "",
    ) -> dict[str, Any]:
        try:
            return self._apply_material_operator_rankings(
                payload,
                allowed_advertiser_ids=allowed_advertiser_ids,
                range_key=range_key,
                start_date=start_date,
                end_date=end_date,
                snapshot_time=snapshot_time,
            )
        except Exception:  # noqa: BLE001
            degraded_payload = dict(payload or {})
            degraded_payload["material_operator_rankings_skipped"] = True
            return degraded_payload

    def get_performance_snapshot(
        self,
        range_key: str,
        start_date: str = "",
        end_date: str = "",
        force_refresh: bool = False,
        allowed_advertiser_ids: set[int] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> dict[str, Any]:
        normalized = str(range_key or "day").strip().lower()
        if normalized not in PERFORMANCE_RANGES:
            raise ValueError("range must be one of day/yesterday/week/month/custom")
        config = self.read_config()
        if normalized == "custom":
            start_dt, end_dt, range_label = build_custom_performance_window(start_date, end_date, config["timezone"])
        else:
            start_dt, end_dt, range_label = build_performance_window(normalized, config["timezone"])
        cache_customer_center_id = "__all_customer_centers__" if self._display_scope_uses_all_customer_centers(display_scope) else self._current_customer_center_id()
        cache_key = build_performance_cache_key(normalized, start_date, end_date, cache_customer_center_id)
        cache_version = self._shared_cache_version("performance")
        versioned_cache_key = self._versioned_cache_key(cache_version, cache_key)
        now_ts = time.time()
        cached_payload = None
        if not force_refresh:
            cached_payload = self._local_dict_cache_get(self._performance_cache, versioned_cache_key, RANGE_CACHE_SECONDS)
            if cached_payload is None:
                cached_payload = self._shared_dict_cache_get("performance", cache_key, cache_version)
                if cached_payload is not None:
                    self._local_dict_cache_set(self._performance_cache, versioned_cache_key, cached_payload)
        if cached_payload is not None:
            if (
                not self._display_scope_uses_all_customer_centers(display_scope)
                and cached_payload.get("history_backfill_pending")
                and int(cached_payload.get("missing_history_days", 0) or 0) > 0
            ):
                cached_payload["history_backfill_queued"] = self._queue_history_backfill_if_needed(
                    "performance", start_dt, end_dt, int(cached_payload.get("missing_history_days", 0) or 0)
                )
            return self._apply_account_scope(cached_payload, allowed_advertiser_ids)
        missing_days = 0
        if normalized in {"week", "month", "custom", "yesterday"} and not self._display_scope_uses_all_customer_centers(display_scope):
            with self.db() as conn:
                missing_days = len(self._missing_summary_days(conn, start_dt, end_dt))
        backfill_queued = (
            self._queue_history_backfill_if_needed("performance", start_dt, end_dt, missing_days)
            if not self._display_scope_uses_all_customer_centers(display_scope)
            else False
        )
        if self._display_scope_uses_all_customer_centers(display_scope):
            payload = self._performance_snapshot_from_db_all_customer_centers(start_dt, end_dt)
        else:
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
        payload = self._safe_apply_material_operator_rankings(
            payload,
            range_key=normalized,
            start_date=start_dt.strftime("%Y-%m-%d"),
            end_date=end_dt.strftime("%Y-%m-%d"),
        )
        self._local_dict_cache_set(self._performance_cache, versioned_cache_key, payload)
        self._shared_dict_cache_set("performance", cache_key, cache_version, payload, RANGE_CACHE_SECONDS)
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
            payload = await asyncio.to_thread(self.collect_and_store_all_customer_centers)
            return {
                "ok": True,
                "manual": manual,
                "skipped": bool(payload.get("skipped", False)),
                "reason": str(payload.get("reason") or ""),
                "snapshot_time": payload.get("snapshot_time", ""),
                "current_customer_center_id": payload.get("current_customer_center_id", ""),
                "synced_customer_center_count": int(payload.get("synced_customer_center_count", 0) or 0),
                "error_count": int(payload.get("error_count", 0) or 0),
            }

    async def run_detail_sync(self, manual: bool = False, force_refresh: bool = False) -> dict[str, Any]:
        async with self._detail_sync_lock:
            payload = await asyncio.to_thread(self.collect_extended_and_store, force_refresh)
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
        self.clear_runtime_caches()
        return payload

    def collect_extended_and_store_all_customer_centers(
        self,
        force_refresh: bool = False,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        with self._distributed_runtime_lock(
            "detail-sync",
            timeout_seconds=max(int(DETAIL_SYNC_INTERVAL_MINUTES or 1) * 120, 300),
        ) as acquired:
            if not acquired:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "detail sync already running",
                    "snapshot_time": "",
                    "synced_customer_center_count": 0,
                    "errors": [],
                }
            customer_center_ids = self.bound_customer_center_ids()
            if not customer_center_ids:
                payload = self.collect_extended_and_store(force_refresh=force_refresh)
                return {
                    "ok": bool(payload.get("ok", True)),
                    "skipped": bool(payload.get("skipped", False)),
                    "reason": str(payload.get("reason") or ""),
                    "snapshot_time": str(payload.get("snapshot_time") or "").strip(),
                    "synced_customer_center_count": 0 if payload.get("skipped") else 1,
                    "synced_customer_centers": [] if payload.get("skipped") else [payload],
                    "skipped_customer_center_count": 0 if not payload.get("skipped") else 1,
                    "skipped_customer_centers": [] if not payload.get("skipped") else [payload],
                    "error_count": len(payload.get("errors") or []),
                    "errors": list(payload.get("errors") or []),
                }

            synced_customer_centers: list[dict[str, Any]] = []
            skipped_customer_centers: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []
            snapshot_times: list[str] = []
            total_centers = len(customer_center_ids)

            for index, customer_center_id in enumerate(customer_center_ids, start=1):
                if callable(progress_callback):
                    progress_callback(
                        {
                            "customer_center_id": customer_center_id,
                            "completed_steps": index - 1,
                            "total_steps": total_centers,
                            "message": f"{customer_center_id} ({index}/{total_centers})",
                        }
                    )
                try:
                    payload = self.collect_extended_snapshot(
                        force_refresh=force_refresh,
                        customer_center_id=customer_center_id,
                    )
                    if payload.get("skipped"):
                        skipped_customer_centers.append(
                            {
                                "customer_center_id": customer_center_id,
                                "reason": str(payload.get("reason") or ""),
                                "snapshot_time": str(payload.get("snapshot_time") or "").strip(),
                            }
                        )
                        continue
                    self.persist_extended_snapshot(payload, replace_same_day=True)
                    snapshot_time = str(payload.get("snapshot_time") or "").strip()
                    if snapshot_time:
                        snapshot_times.append(snapshot_time)
                    synced_customer_centers.append(
                        {
                            "customer_center_id": customer_center_id,
                            "snapshot_time": snapshot_time,
                            "plan_count": int(payload.get("plan_count", 0) or 0),
                            "material_row_count": len(payload.get("material_rows") or []),
                            "error_count": len(payload.get("errors") or []),
                        }
                    )
                    for item in payload.get("errors") or []:
                        errors.append(
                            {
                                "customer_center_id": customer_center_id,
                                **dict(item),
                            }
                        )
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "customer_center_id": customer_center_id,
                            "stage": "detail_sync",
                            "error": str(exc),
                        }
                    )
                finally:
                    if callable(progress_callback):
                        progress_callback(
                            {
                                "customer_center_id": customer_center_id,
                                "completed_steps": index,
                                "total_steps": total_centers,
                                "message": f"{customer_center_id} ({index}/{total_centers})",
                            }
                        )

            self.cleanup_history()
            self.clear_runtime_caches()
            try:
                self.material_rankings("day")
            except Exception:
                pass
            return {
                "ok": not errors,
                "skipped": False,
                "reason": "" if not errors else f"{len(errors)} detail sync errors",
                "snapshot_time": max(snapshot_times) if snapshot_times else "",
                "synced_customer_center_count": len(synced_customer_centers),
                "synced_customer_centers": synced_customer_centers,
                "skipped_customer_center_count": len(skipped_customer_centers),
                "skipped_customer_centers": skipped_customer_centers,
                "error_count": len(errors),
                "errors": errors,
            }

    def collect_extended_and_store(self, force_refresh: bool = False) -> dict[str, Any]:
        with self._distributed_runtime_lock(
            "detail-sync",
            timeout_seconds=max(int(DETAIL_SYNC_INTERVAL_MINUTES or 1) * 120, 300),
        ) as acquired:
            if not acquired:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "detail sync already running",
                    "snapshot_time": "",
                    "errors": [],
                }
            payload = self.collect_extended_snapshot(force_refresh=force_refresh)
            if payload.get("skipped"):
                return payload
            self.persist_extended_snapshot(payload, replace_same_day=True)
            self.cleanup_history()
            self.clear_runtime_caches()
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
