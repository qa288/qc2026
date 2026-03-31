from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from dashboard.settings import settings

TIMEZONE = settings.timezone
DETAIL_SYNC_INTERVAL_MINUTES = settings.detail_sync_interval_minutes
HISTORY_BACKFILL_DAYS = settings.history_backfill_days
EXTENDED_HISTORY_REFRESH_DAYS = settings.extended_history_refresh_days
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
        "dashboard-performance-history-refresh": {
            "task": "dashboard.performance_refresh_recent",
            "schedule": crontab(hour=0, minute=5),
            "args": (HISTORY_BACKFILL_DAYS,),
        },
        "dashboard-performance-history-backfill": {
            "task": "dashboard.performance_backfill",
            "schedule": crontab(hour=2, minute=10),
            "args": (HISTORY_BACKFILL_DAYS,),
        },
        "dashboard-detail-history-backfill": {
            "task": "dashboard.detail_backfill",
            "schedule": crontab(hour=2, minute=30),
            "args": (HISTORY_BACKFILL_DAYS,),
        },
        "dashboard-detail-history-refresh": {
            "task": "dashboard.detail_refresh_recent",
            "schedule": crontab(hour=0, minute=20),
            "args": (EXTENDED_HISTORY_REFRESH_DAYS,),
        },
        "dashboard-oauth-authorization-audit": {
            "task": "dashboard.oauth_authorization_audit",
            "schedule": crontab(hour="*/12", minute=15),
            "args": (12,),
        },
    },
)
