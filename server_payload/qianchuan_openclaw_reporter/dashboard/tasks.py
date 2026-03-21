from __future__ import annotations

from dashboard.celery_app import celery_app
from dashboard.main import service
from bridge_send_alerts import dispatch_once


def _prepare() -> None:
    service.init_db()
    service.bootstrap_token_store()


@celery_app.task(name="dashboard.sync")
def sync_dashboard() -> dict:
    _prepare()
    payload = service.collect_and_store()
    return {"snapshot_time": payload["snapshot_time"]}


@celery_app.task(name="dashboard.detail_sync")
def sync_dashboard_detail() -> dict:
    _prepare()
    payload = service.collect_extended_and_store()
    return {
        "snapshot_time": payload.get("snapshot_time", ""),
        "skipped": bool(payload.get("skipped", False)),
        "error_count": len(payload.get("errors", [])),
    }


@celery_app.task(name="dashboard.dispatch_alerts")
def dispatch_dashboard_alerts() -> dict:
    _prepare()
    return dispatch_once()
