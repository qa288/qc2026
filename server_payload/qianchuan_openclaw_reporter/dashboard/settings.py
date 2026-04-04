from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_text(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    text = str(value).strip()
    return int(text or str(default))


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    text = str(value).strip()
    return float(text or str(default))


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip() == "1"


@dataclass(frozen=True)
class DashboardSettings:
    app_name: str
    config_path: Path
    data_dir: Path
    upload_dir: Path
    database_path: Path
    database_url: str
    token_cache_path: Path
    latest_token_path: Path
    timezone: str
    alert_cooldown_default: int
    retention_days: int
    extended_retention_days: int
    account_plan_retention_days: int
    material_history_start_date: str
    dashboard_username: str
    dashboard_password: str
    session_secret: str
    range_cache_seconds: int
    comment_sync_success_ttl_seconds: int
    comment_sync_error_retry_seconds: int
    comment_sync_interval_minutes: int
    backfill_queue_debounce_seconds: int
    performance_sync_workers: int
    performance_plan_sync_workers: int
    detail_sync_interval_minutes: int
    material_sync_interval_minutes: int
    material_sync_workers: int
    nightly_history_workers: int
    enable_hot_sync_schedules: bool
    nightly_history_plan_material_requests_per_minute: int
    nightly_history_plan_material_batch_size: int
    nightly_history_plan_material_batch_sleep_seconds: float
    enable_in_process_scheduler: bool
    history_backfill_days: int
    extended_history_refresh_days: int
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str


def load_settings() -> DashboardSettings:
    data_dir = Path(_env_text("DATA_DIR", "/app/data"))
    redis_url = str(os.environ.get("REDIS_URL") or "").strip()
    return DashboardSettings(
        app_name="Qianchuan",
        config_path=Path(_env_text("CONFIG_PATH", "/app/config/config.json")),
        data_dir=data_dir,
        upload_dir=data_dir / "material_uploads",
        database_path=Path(_env_text("DATABASE_PATH", str(data_dir / "dashboard.db"))),
        database_url=str(os.environ.get("DATABASE_URL", "")).strip(),
        token_cache_path=Path(_env_text("TOKEN_CACHE_PATH", str(data_dir / "token_cache.json"))),
        latest_token_path=Path(_env_text("LATEST_TOKEN_PATH", str(data_dir / "qianchuan_latest_token.json"))),
        timezone=_env_text("TIMEZONE", "Asia/Shanghai"),
        alert_cooldown_default=_env_int("ALERT_COOLDOWN_DEFAULT", 60),
        retention_days=_env_int("RETENTION_DAYS", 30),
        extended_retention_days=_env_int("EXTENDED_RETENTION_DAYS", 30),
        account_plan_retention_days=_env_int("ACCOUNT_PLAN_RETENTION_DAYS", 90),
        material_history_start_date=_env_text("MATERIAL_HISTORY_START_DATE", "2026-01-01"),
        dashboard_username=_env_text("DASHBOARD_USERNAME", "admin"),
        dashboard_password=str(os.environ.get("DASHBOARD_PASSWORD", "")).strip(),
        session_secret=_env_text("SESSION_SECRET", "replace-me"),
        range_cache_seconds=_env_int("RANGE_CACHE_SECONDS", 55),
        comment_sync_success_ttl_seconds=_env_int("COMMENT_SYNC_SUCCESS_TTL_SECONDS", 300),
        comment_sync_error_retry_seconds=_env_int("COMMENT_SYNC_ERROR_RETRY_SECONDS", 120),
        comment_sync_interval_minutes=_env_int("COMMENT_SYNC_INTERVAL_MINUTES", 30),
        backfill_queue_debounce_seconds=_env_int("BACKFILL_QUEUE_DEBOUNCE_SECONDS", 900),
        performance_sync_workers=_env_int("PERFORMANCE_SYNC_WORKERS", 3),
        performance_plan_sync_workers=_env_int("PERFORMANCE_PLAN_SYNC_WORKERS", 3),
        detail_sync_interval_minutes=_env_int("DETAIL_SYNC_INTERVAL_MINUTES", 10),
        material_sync_interval_minutes=_env_int("MATERIAL_SYNC_INTERVAL_MINUTES", 30),
        material_sync_workers=_env_int("MATERIAL_SYNC_WORKERS", 6),
        nightly_history_workers=_env_int("NIGHTLY_HISTORY_WORKERS", 6),
        enable_hot_sync_schedules=_env_bool("ENABLE_HOT_SYNC_SCHEDULES", True),
        nightly_history_plan_material_requests_per_minute=_env_int(
            "NIGHTLY_HISTORY_PLAN_MATERIAL_REQUESTS_PER_MINUTE",
            300,
        ),
        nightly_history_plan_material_batch_size=_env_int(
            "NIGHTLY_HISTORY_PLAN_MATERIAL_BATCH_SIZE",
            0,
        ),
        nightly_history_plan_material_batch_sleep_seconds=_env_float(
            "NIGHTLY_HISTORY_PLAN_MATERIAL_BATCH_SLEEP_SECONDS",
            0.0,
        ),
        enable_in_process_scheduler=_env_bool("ENABLE_IN_PROCESS_SCHEDULER", False),
        history_backfill_days=_env_int("HISTORY_BACKFILL_DAYS", 30),
        extended_history_refresh_days=_env_int("EXTENDED_HISTORY_REFRESH_DAYS", 30),
        redis_url=redis_url,
        celery_broker_url=str(os.environ.get("CELERY_BROKER_URL") or redis_url or "redis://redis:6379/1").strip(),
        celery_result_backend=str(os.environ.get("CELERY_RESULT_BACKEND") or redis_url or "redis://redis:6379/2").strip(),
    )


settings = load_settings()
