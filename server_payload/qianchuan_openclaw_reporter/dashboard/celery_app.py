from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

TIMEZONE = os.environ.get("TIMEZONE", "Asia/Shanghai")
DETAIL_SYNC_INTERVAL_MINUTES = int(os.environ.get("DETAIL_SYNC_INTERVAL_MINUTES", "10"))
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND") or os.environ.get(
    "REDIS_URL", "redis://redis:6379/2"
)

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
        "dashboard-sync-minute": {
            "task": "dashboard.sync",
            "schedule": crontab(minute="*"),
        },
        "dashboard-detail-sync": {
            "task": "dashboard.detail_sync",
            "schedule": crontab(minute=f"*/{DETAIL_SYNC_INTERVAL_MINUTES}"),
        },
        "dashboard-alert-dispatch": {
            "task": "dashboard.dispatch_alerts",
            "schedule": crontab(minute="*"),
        },
    },
)
