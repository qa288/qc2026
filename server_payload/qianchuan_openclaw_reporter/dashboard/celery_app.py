from __future__ import annotations

import os
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready
from redis import Redis

from dashboard.settings import settings

TIMEZONE = settings.timezone
MATERIAL_SYNC_INTERVAL_MINUTES = settings.material_sync_interval_minutes
COMMENT_SYNC_INTERVAL_MINUTES = settings.comment_sync_interval_minutes
HISTORY_CATCHUP_PROBE_INTERVAL_MINUTES = settings.history_catchup_probe_interval_minutes
CELERY_BROKER_URL = settings.celery_broker_url
CELERY_RESULT_BACKEND = settings.celery_result_backend
RUNTIME_LOCK_SCOPE = str(os.environ.get("DASHBOARD_RUNTIME_LOCK_SCOPE") or "").strip().lower()

RUNTIME_LOCKS_BY_SCOPE = {
    "hot": (
        "sync",
        "detail-sync",
        "oauth-token-refresh",
        "oauth-audit",
        "plan-delivery-type-metadata",
    ),
    "history": (
        "full-refresh",
    ),
}

celery_app = Celery(
    "qianchuan_dashboard",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    timezone=TIMEZONE,
    enable_utc=False,
    task_ignore_result=True,
    imports=("dashboard.tasks",),
    beat_schedule={
        **(
            {
                "dashboard-sync-minute": {
                    "task": "dashboard.sync",
                    "schedule": crontab(minute="*"),
                },
                "dashboard-detail-sync": {
                    "task": "dashboard.material_hot_sync",
                    "schedule": crontab(minute=f"*/{MATERIAL_SYNC_INTERVAL_MINUTES}"),
                },
            }
            if settings.enable_hot_sync_schedules
            else {}
        ),
        "dashboard-comment-sync": {
            "task": "dashboard.comment_sync_hot",
            "schedule": crontab(minute=f"*/{COMMENT_SYNC_INTERVAL_MINUTES}"),
        },
        "dashboard-alert-dispatch": {
            "task": "dashboard.dispatch_alerts",
            "schedule": crontab(minute="*"),
        },
        "dashboard-finalize-yesterday-daily": {
            "task": "dashboard.finalize_yesterday_daily",
            "schedule": crontab(hour=0, minute=5),
            "options": {"queue": "history"},
        },
        "dashboard-nightly-full-refresh": {
            "task": "dashboard.nightly_history_refresh",
            "schedule": crontab(hour=2, minute=0),
            "options": {"queue": "history"},
        },
        **(
            {
                "dashboard-history-catchup-probe": {
                    "task": "dashboard.history_catchup_probe",
                    "schedule": timedelta(minutes=HISTORY_CATCHUP_PROBE_INTERVAL_MINUTES),
                    "options": {"queue": "history"},
                },
            }
            if HISTORY_CATCHUP_PROBE_INTERVAL_MINUTES > 0
            else {}
        ),
        "dashboard-oauth-token-refresh": {
            "task": "dashboard.oauth_token_refresh",
            "schedule": crontab(hour="*/12", minute=15),
        },
    },
)


def _runtime_lock_key(lock_name: str) -> str:
    return f"dashboard:runtime-lock:{str(lock_name or '').strip()}"


@worker_ready.connect
def _clear_restarted_worker_runtime_locks(**_: object) -> None:
    lock_names = RUNTIME_LOCKS_BY_SCOPE.get(RUNTIME_LOCK_SCOPE, ())
    if not lock_names:
        return
    redis_url = str(settings.redis_url or "").strip()
    if not redis_url:
        return
    try:
        client = Redis.from_url(redis_url, decode_responses=True)
        keys = [_runtime_lock_key(lock_name) for lock_name in lock_names if str(lock_name or "").strip()]
        if keys:
            client.delete(*keys)
    except Exception:
        return
