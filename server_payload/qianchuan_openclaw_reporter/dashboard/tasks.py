from __future__ import annotations

import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from bridge_send_alerts import dispatch_once
from dashboard.celery_app import celery_app
from dashboard.main import FULL_REFRESH_STAGE_LABELS, FULL_REFRESH_STAGE_SEQUENCE, now_text, service
from dashboard.settings import settings

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


def _hot_sync_pause_payload(reason: str) -> dict:
    return {
        "ok": True,
        "skipped": True,
        "reason": str(reason or "hot syncs paused"),
    }


def _configured_performance_days(days: int | None = None) -> int:
    if days is not None and int(days or 0) > 0:
        return max(int(days or 0), 1)
    return max(int(settings.account_plan_retention_days or 90), 1)


def _material_history_start_date() -> str:
    return str(settings.material_history_start_date or "2026-01-01").strip() or "2026-01-01"


def _material_history_days() -> int:
    start_day = datetime.strptime(_material_history_start_date(), "%Y-%m-%d").date()
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    return max((today - start_day).days + 1, 1)


@celery_app.task(name="dashboard.sync")
def sync_dashboard() -> dict:
    _prepare()
    if service.hot_syncs_paused():
        return _hot_sync_pause_payload("hot syncs paused for nightly history rebuild")
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
    if service.hot_syncs_paused():
        return _hot_sync_pause_payload("hot syncs paused for nightly history rebuild")
    payload = service.collect_material_and_store_all_customer_centers(force_refresh=bool(force_refresh))
    return {
        "snapshot_time": payload.get("snapshot_time", ""),
        "synced_customer_center_count": int(payload.get("synced_customer_center_count", 0) or 0),
        "skipped": bool(payload.get("skipped", False)),
        "reason": str(payload.get("reason") or ""),
        "error_count": int(payload.get("error_count", 0) or 0),
    }


@celery_app.task(name="dashboard.full_refresh")
def full_refresh_dashboard(
    performance_days: int = 0,
    detail_days: int = 0,
    force_detail_refresh: bool = True,
) -> dict:
    task_id = str(getattr(full_refresh_dashboard.request, "id", "") or "")
    return _history_refresh_dashboard_v3(
        task_id=task_id,
        performance_days=performance_days,
        detail_days=detail_days,
        force_detail_refresh=force_detail_refresh,
        trigger="manual",
    )


@celery_app.task(name="dashboard.nightly_history_refresh")
def nightly_history_refresh_dashboard(
    performance_days: int = 0,
    detail_days: int = 0,
    force_detail_refresh: bool = True,
) -> dict:
    task_id = str(getattr(nightly_history_refresh_dashboard.request, "id", "") or "")
    return _history_refresh_dashboard_v3(
        task_id=task_id,
        performance_days=performance_days,
        detail_days=detail_days,
        force_detail_refresh=force_detail_refresh,
        trigger="nightly",
    )


def _history_refresh_dashboard_v3(
    *,
    task_id: str,
    performance_days: int = 0,
    detail_days: int = 0,
    force_detail_refresh: bool = True,
    trigger: str = "manual",
) -> dict:
    _prepare()
    _ = int(detail_days or 0)
    _ = bool(force_detail_refresh)
    performance_days = _configured_performance_days(performance_days)
    material_history_days = _material_history_days()
    material_start_date = _material_history_start_date()
    trigger = str(trigger or "manual").strip().lower() or "manual"
    nightly_material_workers = None
    nightly_use_report_metrics = trigger == "nightly"
    nightly_plan_material_requests_per_minute = 0
    nightly_plan_material_batch_size = 0
    nightly_plan_material_batch_sleep_seconds = 0.0
    if trigger == "nightly":
        nightly_material_workers = max(
            1,
            min(int(settings.nightly_history_workers or settings.material_sync_workers or 6), 8),
        )
        nightly_plan_material_requests_per_minute = max(
            int(settings.nightly_history_plan_material_requests_per_minute or 300),
            0,
        )
        nightly_plan_material_batch_size = max(int(settings.nightly_history_plan_material_batch_size or 0), 0)
        nightly_plan_material_batch_sleep_seconds = max(
            float(settings.nightly_history_plan_material_batch_sleep_seconds or 0.0),
            0.0,
        )
    total_steps = len(FULL_REFRESH_STAGE_SEQUENCE)
    stage_labels = dict(FULL_REFRESH_STAGE_LABELS)
    return _execute_full_refresh_overwrite(
        task_id=task_id,
        total_steps=total_steps,
        stage_labels=stage_labels,
        performance_days=performance_days,
        material_history_days=material_history_days,
        material_start_date=material_start_date,
        nightly_material_workers=nightly_material_workers,
        nightly_use_report_metrics=nightly_use_report_metrics,
        nightly_plan_material_requests_per_minute=nightly_plan_material_requests_per_minute,
        nightly_plan_material_batch_size=nightly_plan_material_batch_size,
        nightly_plan_material_batch_sleep_seconds=nightly_plan_material_batch_sleep_seconds,
        trigger=trigger,
    )


def _execute_full_refresh_overwrite(
    *,
    task_id: str,
    total_steps: int,
    stage_labels: dict[str, str],
    performance_days: int,
    material_history_days: int,
    material_start_date: str,
    nightly_material_workers: int | None,
    nightly_use_report_metrics: bool,
    nightly_plan_material_requests_per_minute: int,
    nightly_plan_material_batch_size: int,
    nightly_plan_material_batch_sleep_seconds: float,
    trigger: str,
) -> dict:
    trigger = str(trigger or "manual").strip().lower() or "manual"
    trigger_label = "nightly history refresh" if trigger == "nightly" else "manual history refresh"

    def clear_dashboard_caches() -> dict:
        service.clear_runtime_caches()
        return {
            "cache_namespaces": [
                "dashboard-overview",
                "performance",
                "material",
                "comment",
                "latest-snapshot",
            ],
        }

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
            trigger=trigger,
            status=stage_status,
            stage=stage_name,
            stage_label=stage_labels.get(stage_name, FULL_REFRESH_STAGE_LABELS.get(stage_name, stage_name)),
            message=str(message or ""),
            queued_at=current_status.get("queued_at") or timestamp,
            started_at=current_status.get("started_at") or current_status.get("queued_at") or timestamp,
            updated_at=timestamp,
            progress={
                "completed_steps": completed_steps,
                "total_steps": total_steps,
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
            return {
                "ok": True,
                "result": callback(*args, **kwargs),
                "error": "",
                "stage_status": "completed",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "result": {},
                "error": str(exc),
                "stage_status": "failed",
            }

    def history_stage_progress_message(default_message: str, progress_payload: dict | None) -> str:
        payload = progress_payload if isinstance(progress_payload, dict) else {}
        target_day = str(payload.get("target_day") or "").strip()
        customer_center_id = str(payload.get("customer_center_id") or "").strip()
        detail_message = str(payload.get("message") or "").strip()
        parts = [str(default_message or "").strip()]
        if target_day:
            parts.append(target_day)
        if customer_center_id:
            parts.append(customer_center_id)
        if detail_message and detail_message not in parts:
            parts.append(detail_message)
        return " | ".join(part for part in parts if part)

    def build_stage_progress_callback(stage_name: str, completed_steps: int, default_message: str):
        def callback(progress_payload: dict[str, object]) -> None:
            payload = dict(progress_payload or {})
            update_stage_status(
                stage_name,
                stage_status="running",
                message=history_stage_progress_message(default_message, payload),
                completed_steps=completed_steps,
                stage_completed_steps=max(
                    int(payload.get("stage_completed_steps", payload.get("completed_steps", 0)) or 0),
                    0,
                ),
                stage_total_steps=max(
                    int(payload.get("stage_total_steps", payload.get("total_steps", 0)) or 0),
                    0,
                ),
                result=payload,
            )

        return callback

    with service._distributed_runtime_lock("full-refresh", timeout_seconds=21600) as acquired:
        if not acquired:
            status_payload = service.full_refresh_status()
            return {
                "ok": True,
                "skipped": True,
                "reason": "history refresh already running",
                "status": status_payload,
            }

        start_timestamp = now_text()
        queued_at = service.full_refresh_status().get("queued_at") or start_timestamp
        service.update_full_refresh_status(
            task_id=task_id,
            trigger=trigger,
            status="running",
            stage="performance",
            stage_label=stage_labels.get("performance", "performance"),
            message=f"{trigger_label} started; refreshing the last {performance_days} completed performance days",
            queued_at=queued_at,
            started_at=start_timestamp,
            updated_at=start_timestamp,
            finished_at="",
            progress={
                "completed_steps": 0,
                "total_steps": total_steps,
                "stage_completed_steps": 0,
                "stage_total_steps": 0,
            },
            stages={},
            result={},
        )

        service.pause_hot_syncs("nightly_history")
        try:
            performance_payload = run_stage(
                "performance",
                service.refresh_recent_performance_history,
                performance_days,
                progress_callback=build_stage_progress_callback(
                    "performance",
                    0,
                    f"refreshing the last {performance_days} completed performance days",
                ),
            )
            update_stage_status(
                "material_metrics",
                stage_status="running",
                message=str(
                    performance_payload.get("error")
                    or "recent performance history refreshed; refreshing current-plan material inventory"
                ),
                completed_steps=1,
                result=performance_payload.get("result") or {},
            )

            material_metrics_payload = run_stage(
                "material_metrics",
                service.refresh_recent_material_history,
                material_history_days,
                workers_override=nightly_material_workers,
                prefer_report_metrics=nightly_use_report_metrics,
                plan_material_requests_per_minute_override=nightly_plan_material_requests_per_minute,
                plan_material_batch_size_override=nightly_plan_material_batch_size,
                plan_material_batch_sleep_seconds_override=nightly_plan_material_batch_sleep_seconds,
                progress_callback=build_stage_progress_callback(
                    "material_metrics",
                    1,
                    "refreshing current-plan material inventory",
                ),
            )
            material_metrics_result = dict(material_metrics_payload.get("result") or {})
            material_metrics_result["start_date"] = material_start_date
            material_metrics_result["requested_days"] = material_history_days
            material_metrics_payload["result"] = material_metrics_result

            update_stage_status(
                "material_metadata",
                stage_status="running",
                message=str(
                    material_metrics_payload.get("error")
                    or "current-plan material inventory refreshed; rebuilding material metadata"
                ),
                completed_steps=2,
                result=material_metrics_payload.get("result") or {},
            )

            material_metadata_payload = run_stage(
                "material_metadata",
                service.refresh_material_metadata_history,
                material_start_date,
                progress_callback=build_stage_progress_callback(
                    "material_metadata",
                    2,
                    "rebuilding current-plan material metadata",
                ),
            )
            cache_clear_payload = run_stage("cache_clear", clear_dashboard_caches)
        finally:
            service.resume_hot_syncs()

        stage_errors = [
            payload["error"]
            for payload in (
                performance_payload,
                material_metrics_payload,
                material_metadata_payload,
                cache_clear_payload,
            )
            if str(payload.get("error") or "").strip()
        ]
        final_status = "completed"
        if any(
            not bool(payload.get("ok"))
            for payload in (
                performance_payload,
                material_metrics_payload,
                material_metadata_payload,
                cache_clear_payload,
            )
        ):
            final_status = "failed"

        finish_timestamp = now_text()
        service.update_full_refresh_status(
            task_id=task_id,
            trigger=trigger,
            status=final_status,
            stage="",
            stage_label="",
            message=(
                "; ".join(stage_errors)
                if stage_errors
                else (
                    f"{trigger_label} completed; recent {performance_days} completed performance days, "
                    "current-plan material inventory and material metadata were rebuilt from upstream"
                )
            ),
            queued_at=service.full_refresh_status().get("queued_at") or finish_timestamp,
            started_at=service.full_refresh_status().get("started_at") or finish_timestamp,
            updated_at=finish_timestamp,
            finished_at=finish_timestamp,
            progress={
                "completed_steps": total_steps,
                "total_steps": total_steps,
                "stage_completed_steps": 0,
                "stage_total_steps": 0,
            },
            stages={
                "performance": {
                    "status": performance_payload.get("stage_status", "completed"),
                    "message": str(performance_payload.get("error") or ""),
                    "result": performance_payload.get("result") or {},
                },
                "material_metrics": {
                    "status": material_metrics_payload.get("stage_status", "completed"),
                    "message": str(material_metrics_payload.get("error") or ""),
                    "result": material_metrics_payload.get("result") or {},
                },
                "material_metadata": {
                    "status": material_metadata_payload.get("stage_status", "completed"),
                    "message": str(material_metadata_payload.get("error") or ""),
                    "result": material_metadata_payload.get("result") or {},
                },
            },
            result={
                "performance": performance_payload,
                "material_metrics": material_metrics_payload,
                "material_metadata": material_metadata_payload,
                "cache_clear": cache_clear_payload,
            },
        )
        return {
            "ok": final_status == "completed",
            "skipped": False,
            "reason": "; ".join(stage_errors),
            "performance": performance_payload,
            "material_metrics": material_metrics_payload,
            "material_metadata": material_metadata_payload,
            "cache_clear": cache_clear_payload,
            "status": service.full_refresh_status(),
        }


@celery_app.task(name="dashboard.oauth_token_refresh")
def refresh_dashboard_oauth_tokens() -> dict:
    _prepare()
    return service.refresh_customer_center_tokens()


@celery_app.task(name="dashboard.oauth_authorization_audit")
def audit_dashboard_oauth_authorization(stale_hours: int = 12) -> dict:
    _prepare()
    _ = int(stale_hours or 12)
    return service.refresh_customer_center_tokens()


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


@celery_app.task(name="dashboard.comment_sync_hot")
def sync_dashboard_comments_hot() -> dict:
    _prepare()
    tz = ZoneInfo(service.read_config()["timezone"])
    today = datetime.now(tz).date().isoformat()
    return service.sync_comments_for_dates(
        today,
        today,
        advertiser_id=0,
        allowed_advertiser_ids=None,
        force_refresh=False,
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
