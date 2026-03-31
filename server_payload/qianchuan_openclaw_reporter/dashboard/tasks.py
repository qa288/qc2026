from __future__ import annotations

import threading

from dashboard.celery_app import celery_app
from dashboard.main import service
from bridge_send_alerts import dispatch_once

_PREPARE_LOCK = threading.Lock()
_PREPARED = False


def _prepare() -> None:
    global _PREPARED
    if _PREPARED:
        return
    with _PREPARE_LOCK:
        if _PREPARED:
            return
        service.init_db_once()
        service.bootstrap_token_store()
        _PREPARED = True


@celery_app.task(name="dashboard.sync")
def sync_dashboard() -> dict:
    _prepare()
    payload = service.collect_and_store_all_customer_centers()
    return {
        "snapshot_time": payload.get("snapshot_time", ""),
        "current_customer_center_id": payload.get("current_customer_center_id", ""),
        "synced_customer_center_count": int(payload.get("synced_customer_center_count", 0) or 0),
        "error_count": int(payload.get("error_count", 0) or 0),
        "skipped": bool(payload.get("skipped", False)),
        "reason": str(payload.get("reason") or ""),
    }


@celery_app.task(name="dashboard.detail_sync")
def sync_dashboard_detail(force_refresh: bool = False) -> dict:
    _prepare()
    payload = service.collect_extended_and_store(force_refresh=bool(force_refresh))
    return {
        "snapshot_time": payload.get("snapshot_time", ""),
        "skipped": bool(payload.get("skipped", False)),
        "error_count": len(payload.get("errors", [])),
    }


@celery_app.task(name="dashboard.performance_backfill")
def backfill_dashboard_performance(days: int = 30, job_key: str = "") -> dict:
    _prepare()
    task_id = str(getattr(backfill_dashboard_performance.request, "id", "") or "")
    service.mark_history_backfill_job_started(job_key, task_id)
    try:
        result = service.backfill_recent_performance_history(int(days or 30))
    except Exception as exc:
        service.mark_history_backfill_job_finished(job_key, "failed", message=str(exc))
        raise
    service.mark_history_backfill_job_finished(job_key, "success", result=result)
    return result


@celery_app.task(name="dashboard.performance_refresh_recent")
def refresh_dashboard_performance(days: int = 30) -> dict:
    _prepare()
    return service.refresh_recent_performance_history(int(days or 30))


@celery_app.task(name="dashboard.detail_backfill")
def backfill_dashboard_detail(days: int = 30, job_key: str = "") -> dict:
    _prepare()
    task_id = str(getattr(backfill_dashboard_detail.request, "id", "") or "")
    service.mark_history_backfill_job_started(job_key, task_id)
    try:
        result = service.backfill_recent_extended_history(int(days or 30))
    except Exception as exc:
        service.mark_history_backfill_job_finished(job_key, "failed", message=str(exc))
        raise
    service.mark_history_backfill_job_finished(job_key, "success", result=result)
    return result


@celery_app.task(name="dashboard.detail_refresh_recent")
def refresh_dashboard_detail(days: int = 35) -> dict:
    _prepare()
    return service.refresh_recent_extended_history(int(days or 35))


@celery_app.task(name="dashboard.dispatch_alerts")
def dispatch_dashboard_alerts() -> dict:
    _prepare()
    return dispatch_once()


@celery_app.task(name="dashboard.material_upload")
def process_material_upload(job_id: int) -> dict:
    _prepare()
    try:
        return service.process_material_upload_job(int(job_id))
    except Exception as exc:
        service.mark_material_upload_job_failed(int(job_id), f"上传任务失败：{exc}")
        raise
