from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from dashboard.settings import settings

TIMEZONE = settings.timezone
MATERIAL_SYNC_INTERVAL_MINUTES = settings.material_sync_interval_minutes
COMMENT_SYNC_INTERVAL_MINUTES = settings.comment_sync_interval_minutes
CELERY_BROKER_URL = settings.celery_broker_url
CELERY_RESULT_BACKEND = settings.celery_result_backend

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
                    "task": "dashboard.detail_sync",
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
        "dashboard-nightly-full-refresh": {
            "task": "dashboard.nightly_history_refresh",
            "schedule": crontab(hour=2, minute=0),
            "options": {"queue": "history"},
        },
        "dashboard-oauth-token-refresh": {
            "task": "dashboard.oauth_token_refresh",
            "schedule": crontab(hour="*/12", minute=15),
        },
    },
)
