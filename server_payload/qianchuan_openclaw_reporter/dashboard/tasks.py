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
@celery_app.task(name="dashboard.full_refresh")
def full_refresh_dashboard(
    performance_days: int = 30,
    detail_days: int = 35,
    force_detail_refresh: bool = True,
) -> dict:
    _prepare()

    def run_stage(callback, *args, **kwargs) -> dict:
        try:
            return {
                "ok": True,
                "result": callback(*args, **kwargs),
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "result": {},
                "error": str(exc),
            }

    with service._distributed_runtime_lock("full-refresh", timeout_seconds=3600) as acquired:
        if not acquired:
            return {
                "ok": True,
                "skipped": True,
                "reason": "full refresh already running",
                "summary": {},
                "performance": {},
                "detail_sync": {},
                "detail_history": {},
            }
        summary_payload = run_stage(service.collect_and_store_all_customer_centers)
        performance_payload = run_stage(service.refresh_recent_performance_history, int(performance_days or 30))
        detail_sync_payload = run_stage(service.collect_extended_and_store, force_refresh=bool(force_detail_refresh))
        detail_history_payload = run_stage(service.refresh_recent_extended_history, int(detail_days or 35))
        stage_errors = [
            payload["error"]
            for payload in (summary_payload, performance_payload, detail_sync_payload, detail_history_payload)
            if str(payload.get("error") or "").strip()
        ]
        return {
            "ok": not stage_errors,
            "skipped": False,
            "reason": "; ".join(stage_errors),
            "summary": summary_payload,
            "performance": performance_payload,
            "detail_sync": detail_sync_payload,
            "detail_history": detail_history_payload,
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


@celery_app.task(name="dashboard.comment_sync_recent")
def sync_dashboard_comments(
    start_date: str,
    end_date: str,
    advertiser_id: int = 0,
    allowed_advertiser_ids: list[int] | None = None,
    force_refresh: bool = False,
) -> dict:
    _prepare()
    return service.sync_comments_for_dates(
        start_date,
        end_date,
        advertiser_id=int(advertiser_id or 0),
        allowed_advertiser_ids=allowed_advertiser_ids,
        force_refresh=bool(force_refresh),
    )


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
