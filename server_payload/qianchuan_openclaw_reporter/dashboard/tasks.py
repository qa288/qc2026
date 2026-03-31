from __future__ import annotations

import threading

from dashboard.celery_app import celery_app
from dashboard.main import FULL_REFRESH_STAGE_LABELS, now_text, service
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
    payload = service.collect_extended_and_store_all_customer_centers(force_refresh=bool(force_refresh))
    return {
        "snapshot_time": payload.get("snapshot_time", ""),
        "synced_customer_center_count": int(payload.get("synced_customer_center_count", 0) or 0),
        "skipped": bool(payload.get("skipped", False)),
        "error_count": int(payload.get("error_count", 0) or 0),
    }


@celery_app.task(name="dashboard.full_refresh")
def full_refresh_dashboard(
    performance_days: int = 30,
    detail_days: int = 35,
    force_detail_refresh: bool = True,
) -> dict:
    _prepare()
    task_id = str(getattr(full_refresh_dashboard.request, "id", "") or "")

    def stage_error_count(payload: dict) -> int:
        if not isinstance(payload, dict):
            return 1
        if "error_count" in payload:
            return int(payload.get("error_count", 0) or 0)
        return len(payload.get("errors") or [])

    def update_stage_status(
        stage_name: str,
        *,
        stage_status: str,
        message: str,
        completed_steps: int,
        stage_completed_steps: int = 0,
        stage_total_steps: int = 0,
        result: dict | None = None,
    ) -> None:
        current_status = service.full_refresh_status()
        timestamp = now_text()
        service.update_full_refresh_status(
            task_id=task_id,
            status=stage_status,
            stage=stage_name,
            stage_label=FULL_REFRESH_STAGE_LABELS.get(stage_name, stage_name),
            message=str(message or ""),
            queued_at=current_status.get("queued_at") or timestamp,
            started_at=current_status.get("started_at") or current_status.get("queued_at") or timestamp,
            updated_at=timestamp,
            progress={
                "completed_steps": completed_steps,
                "total_steps": 4,
                "stage_completed_steps": stage_completed_steps,
                "stage_total_steps": stage_total_steps,
            },
            stages={
                stage_name: {
                    "status": stage_status,
                    "message": str(message or ""),
                    "result": result or {},
                }
            },
        )

    def run_stage(stage_name: str, callback, *args, **kwargs) -> dict:
        try:
            result = callback(*args, **kwargs)
            error_count = stage_error_count(result)
            message = ""
            if bool(result.get("skipped")):
                message = str(result.get("reason") or "skipped")
            elif error_count > 0:
                message = str(result.get("reason") or f"{error_count} errors")
            return {
                "ok": True,
                "result": result,
                "error": message,
                "stage_status": "skipped" if bool(result.get("skipped")) else ("partial" if error_count > 0 else "completed"),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "result": {},
                "error": str(exc),
                "stage_status": "failed",
            }

    with service._distributed_runtime_lock("full-refresh", timeout_seconds=3600) as acquired:
        if not acquired:
            status_payload = service.full_refresh_status()
            return {
                "ok": True,
                "skipped": True,
                "reason": "full refresh already running",
                "summary": {},
                "performance": {},
                "detail_sync": {},
                "detail_history": {},
                "status": status_payload,
            }
        start_timestamp = now_text()
        queued_at = service.full_refresh_status().get("queued_at") or start_timestamp
        service.update_full_refresh_status(
            task_id=task_id,
            status="running",
            stage="summary",
            stage_label=FULL_REFRESH_STAGE_LABELS["summary"],
            message="开始刷新全部客服中心的今日汇总。",
            queued_at=queued_at,
            started_at=start_timestamp,
            updated_at=start_timestamp,
            finished_at="",
            progress={
                "completed_steps": 0,
                "total_steps": 4,
                "stage_completed_steps": 0,
                "stage_total_steps": 0,
            },
            stages={},
            result={},
        )

        summary_payload = run_stage("summary", service.collect_and_store_all_customer_centers)
        update_stage_status(
            "summary",
            stage_status="running",
            message=str(summary_payload.get("error") or "今日汇总已完成，开始刷新历史表现。"),
            completed_steps=1,
            result=summary_payload.get("result") or {},
        )

        performance_payload = run_stage(
            "performance",
            service.refresh_recent_performance_history,
            int(performance_days or 30),
            progress_callback=lambda progress: update_stage_status(
                "performance",
                stage_status="running",
                message=f"{progress.get('customer_center_id', '')} {progress.get('target_day', '')} ({progress.get('completed_steps', 0)}/{progress.get('total_steps', 0)})".strip(),
                completed_steps=1,
                stage_completed_steps=int(progress.get("completed_steps", 0) or 0),
                stage_total_steps=int(progress.get("total_steps", 0) or 0),
                result=performance_payload["result"] if "performance_payload" in locals() else {},
            ),
        )
        update_stage_status(
            "performance",
            stage_status="running",
            message=str(performance_payload.get("error") or "历史表现已完成，开始刷新今日明细。"),
            completed_steps=2,
            result=performance_payload.get("result") or {},
        )

        detail_sync_payload = run_stage(
            "detail_sync",
            service.collect_extended_and_store_all_customer_centers,
            force_refresh=bool(force_detail_refresh),
            progress_callback=lambda progress: update_stage_status(
                "detail_sync",
                stage_status="running",
                message=str(progress.get("message") or ""),
                completed_steps=2,
                stage_completed_steps=int(progress.get("completed_steps", 0) or 0),
                stage_total_steps=int(progress.get("total_steps", 0) or 0),
                result=detail_sync_payload["result"] if "detail_sync_payload" in locals() else {},
            ),
        )
        update_stage_status(
            "detail_sync",
            stage_status="running",
            message=str(detail_sync_payload.get("error") or "今日明细已完成，开始刷新历史明细。"),
            completed_steps=3,
            result=detail_sync_payload.get("result") or {},
        )

        detail_history_payload = run_stage(
            "detail_history",
            service.refresh_recent_extended_history,
            int(detail_days or 35),
            progress_callback=lambda progress: update_stage_status(
                "detail_history",
                stage_status="running",
                message=f"{progress.get('customer_center_id', '')} {progress.get('target_day', '')} ({progress.get('completed_steps', 0)}/{progress.get('total_steps', 0)})".strip(),
                completed_steps=3,
                stage_completed_steps=int(progress.get("completed_steps", 0) or 0),
                stage_total_steps=int(progress.get("total_steps", 0) or 0),
                result=detail_history_payload["result"] if "detail_history_payload" in locals() else {},
            ),
        )
        stage_errors = [
            payload["error"]
            for payload in (summary_payload, performance_payload, detail_sync_payload, detail_history_payload)
            if str(payload.get("error") or "").strip()
        ]
        final_status = "completed"
        if any(not bool(payload.get("ok")) for payload in (summary_payload, performance_payload, detail_sync_payload, detail_history_payload)):
            final_status = "failed"
        elif stage_errors:
            final_status = "partial"
        finish_timestamp = now_text()
        service.update_full_refresh_status(
            task_id=task_id,
            status=final_status,
            stage="",
            stage_label="",
            message="; ".join(stage_errors) if stage_errors else "全量刷新已完成。",
            queued_at=service.full_refresh_status().get("queued_at") or finish_timestamp,
            started_at=service.full_refresh_status().get("started_at") or finish_timestamp,
            updated_at=finish_timestamp,
            finished_at=finish_timestamp,
            progress={
                "completed_steps": 4,
                "total_steps": 4,
                "stage_completed_steps": 0,
                "stage_total_steps": 0,
            },
            stages={
                "summary": {
                    "status": summary_payload.get("stage_status", "completed"),
                    "message": str(summary_payload.get("error") or ""),
                    "result": summary_payload.get("result") or {},
                },
                "performance": {
                    "status": performance_payload.get("stage_status", "completed"),
                    "message": str(performance_payload.get("error") or ""),
                    "result": performance_payload.get("result") or {},
                },
                "detail_sync": {
                    "status": detail_sync_payload.get("stage_status", "completed"),
                    "message": str(detail_sync_payload.get("error") or ""),
                    "result": detail_sync_payload.get("result") or {},
                },
                "detail_history": {
                    "status": detail_history_payload.get("stage_status", "completed"),
                    "message": str(detail_history_payload.get("error") or ""),
                    "result": detail_history_payload.get("result") or {},
                },
            },
            result={
                "summary": summary_payload,
                "performance": performance_payload,
                "detail_sync": detail_sync_payload,
                "detail_history": detail_history_payload,
            },
        )
        return {
            "ok": final_status == "completed",
            "skipped": False,
            "reason": "; ".join(stage_errors),
            "summary": summary_payload,
            "performance": performance_payload,
            "detail_sync": detail_sync_payload,
            "detail_history": detail_history_payload,
            "status": service.full_refresh_status(),
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


@celery_app.task(name="dashboard.oauth_authorization_audit")
def audit_dashboard_oauth_authorization(stale_hours: int = 12) -> dict:
    _prepare()
    return service.audit_customer_center_authorizations(int(stale_hours or 12))


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
