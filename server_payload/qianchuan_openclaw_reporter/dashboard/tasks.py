from __future__ import annotations

import threading

from bridge_send_alerts import dispatch_once
from dashboard.celery_app import celery_app
from dashboard.main import DISPLAY_SCOPE_ALL, DISPLAY_SCOPE_CURRENT, FULL_REFRESH_STAGE_LABELS, now_text, service

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
    _ = (performance_days, detail_days, force_detail_refresh)
    total_steps = 4
    stage_labels = {
        "summary": "清理缓存",
        "performance": "首页概览",
        "detail_sync": "账户表现",
        "detail_history": "素材与快照",
    }

    def summarize_overview(payload: dict | None) -> dict:
        data = payload or {}
        summary = dict(data.get("summary") or {})
        return {
            "snapshot_time": str(data.get("snapshot_time") or "").strip(),
            "snapshot_count": int(data.get("snapshot_count", 0) or 0),
            "customer_center_count": int(data.get("customer_center_count", 0) or 0),
            "stat_cost": round(float(summary.get("stat_cost", 0.0) or 0.0), 2),
            "pay_amount": round(float(summary.get("pay_amount", 0.0) or 0.0), 2),
            "order_count": int(float(summary.get("order_count", 0.0) or 0.0)),
        }

    def summarize_performance(payload: dict | None) -> dict:
        data = payload or {}
        summary = dict(data.get("summary") or {})
        return {
            "snapshot_time": str(data.get("snapshot_time") or "").strip(),
            "account_count": len(data.get("accounts") or []),
            "plan_count": len(data.get("plans") or []),
            "customer_center_count": int(data.get("customer_center_count", 0) or 0),
            "stat_cost": round(float(summary.get("stat_cost", 0.0) or 0.0), 2),
            "pay_amount": round(float(summary.get("pay_amount", 0.0) or 0.0), 2),
            "order_count": int(float(summary.get("order_count", 0.0) or 0.0)),
        }

    def summarize_material(payload: dict | None) -> dict:
        data = payload or {}
        meta = dict(data.get("meta") or {})
        return {
            "snapshot_time": str(data.get("snapshot_time") or "").strip(),
            "item_count": len(data.get("items") or []),
            "snapshot_count": int(data.get("snapshot_count", 0) or 0),
            "customer_center_count": int(data.get("customer_center_count", 0) or 0),
            "error_count": int(meta.get("error_count", 0) or 0),
        }

    def summarize_latest_snapshot(payload: dict | None) -> dict:
        data = payload or {}
        summary = dict(data.get("summary") or {})
        return {
            "snapshot_time": str(data.get("snapshot_time") or "").strip(),
            "account_count": len(data.get("accounts") or []),
            "plan_count": len(data.get("plans") or []),
            "customer_center_count": int(data.get("customer_center_count", 0) or 0),
            "stat_cost": round(float(summary.get("stat_cost", 0.0) or 0.0), 2),
            "pay_amount": round(float(summary.get("pay_amount", 0.0) or 0.0), 2),
            "order_count": int(float(summary.get("order_count", 0.0) or 0.0)),
        }

    def clear_dashboard_caches() -> dict:
        service.clear_runtime_caches()
        return {
            "mode": "database_only",
            "cache_namespaces": [
                "dashboard-overview",
                "performance",
                "material",
                "comment",
                "latest-snapshot",
            ],
        }

    def warm_overview_payloads() -> dict:
        current_payload = service.dashboard_overview_payload(display_scope=DISPLAY_SCOPE_CURRENT)
        all_payload = service.dashboard_overview_payload(display_scope=DISPLAY_SCOPE_ALL)
        return {
            "mode": "database_only",
            "current": summarize_overview(current_payload),
            "all": summarize_overview(all_payload),
        }

    def warm_performance_payloads() -> dict:
        current_payload = service.get_performance_snapshot("day", display_scope=DISPLAY_SCOPE_CURRENT)
        all_payload = service.get_performance_snapshot("day", display_scope=DISPLAY_SCOPE_ALL)
        return {
            "mode": "database_only",
            "current": summarize_performance(current_payload),
            "all": summarize_performance(all_payload),
        }

    def warm_detail_payloads() -> dict:
        current_material_payload = service.material_rankings_for_user(
            None,
            range_key="day",
            display_scope=DISPLAY_SCOPE_CURRENT,
        )
        all_material_payload = service.material_rankings_for_user(
            None,
            range_key="day",
            display_scope=DISPLAY_SCOPE_ALL,
        )
        current_latest_snapshot = service.latest_snapshot(display_scope=DISPLAY_SCOPE_CURRENT)
        all_latest_snapshot = service.latest_snapshot(display_scope=DISPLAY_SCOPE_ALL)
        return {
            "mode": "database_only",
            "material": {
                "current": summarize_material(current_material_payload),
                "all": summarize_material(all_material_payload),
            },
            "latest_snapshot": {
                "current": summarize_latest_snapshot(current_latest_snapshot),
                "all": summarize_latest_snapshot(all_latest_snapshot),
            },
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
            stage_label=stage_labels["summary"],
            message="开始清理页面缓存，并准备按数据库最新快照回填。",
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

        summary_payload = run_stage("summary", clear_dashboard_caches)
        update_stage_status(
            "summary",
            stage_status="running",
            message=str(summary_payload.get("error") or "缓存已清理，开始回填首页概览。"),
            completed_steps=1,
            result=summary_payload.get("result") or {},
        )

        performance_payload = run_stage("performance", warm_overview_payloads)
        update_stage_status(
            "performance",
            stage_status="running",
            message=str(performance_payload.get("error") or "首页概览已回填，开始回填账户表现。"),
            completed_steps=2,
            result=performance_payload.get("result") or {},
        )

        detail_sync_payload = run_stage("detail_sync", warm_performance_payloads)
        update_stage_status(
            "detail_sync",
            stage_status="running",
            message=str(detail_sync_payload.get("error") or "账户表现已回填，开始回填素材与最新快照。"),
            completed_steps=3,
            result=detail_sync_payload.get("result") or {},
        )

        detail_history_payload = run_stage("detail_history", warm_detail_payloads)
        stage_errors = [
            payload["error"]
            for payload in (summary_payload, performance_payload, detail_sync_payload, detail_history_payload)
            if str(payload.get("error") or "").strip()
        ]
        final_status = "completed"
        if any(
            not bool(payload.get("ok"))
            for payload in (summary_payload, performance_payload, detail_sync_payload, detail_history_payload)
        ):
            final_status = "failed"
        finish_timestamp = now_text()
        service.update_full_refresh_status(
            task_id=task_id,
            status=final_status,
            stage="",
            stage_label="",
            message="; ".join(stage_errors) if stage_errors else "全量刷新已完成，结果已按数据库最新数据覆盖缓存。",
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
            "mode": "database_only",
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
