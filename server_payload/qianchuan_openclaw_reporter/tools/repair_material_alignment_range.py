#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dashboard.main import (  # noqa: E402
    MATERIAL_CACHE_SCOPE_HISTORY,
    PLAN_SOURCE_UNI_CUBIC,
    PLAN_SOURCE_UNI_PROMOTION,
    PLAN_SOURCE_UNI_REPORT,
    now_text,
    service,
)
from tools.official_daily_align import (  # noqa: E402
    add_unattributed_material_residuals,
    rebuild_material_daily_from_relations,
)


PLAN_SOURCE_SET = (
    PLAN_SOURCE_UNI_PROMOTION,
    PLAN_SOURCE_UNI_CUBIC,
    PLAN_SOURCE_UNI_REPORT,
)


def log(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False, sort_keys=True), flush=True)


def parse_day(value: str, name: str) -> datetime.date:
    text = str(value or "").strip()[:10]
    if not text:
        raise ValueError(f"{name} is required")
    return datetime.strptime(text, "%Y-%m-%d").date()


def day_range(start_day: str, end_day: str) -> list[str]:
    start = parse_day(start_day, "start_date")
    end = parse_day(end_day, "end_date")
    if end < start:
        raise ValueError("end_date must be >= start_date")
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return days


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repair material TITLE/VIDEO cost alignment and rebuild material ranking indexes "
            "for a closed-day range."
        )
    )
    parser.add_argument("--start-date", default="2026-04-30", help="Start day, YYYY-MM-DD.")
    parser.add_argument("--end-date", default="2026-05-06", help="End day, YYYY-MM-DD.")
    parser.add_argument(
        "--customer-center-id",
        action="append",
        default=[],
        help="Customer center id. May be provided more than once. Defaults to bound customer centers.",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Only rebuild from existing same-day material_snapshots; do not call official APIs as fallback.",
    )
    parser.add_argument(
        "--requests-per-minute",
        type=int,
        default=30,
        help="Slow official plan-material request rate used only for days without usable local material rows.",
    )
    parser.add_argument(
        "--fallback-workers",
        type=int,
        default=1,
        help="Worker count used only for slow official fallback days.",
    )
    parser.add_argument(
        "--plan-material-batch-size",
        type=int,
        default=1,
        help="Plan-material batch size used only for slow official fallback days.",
    )
    parser.add_argument(
        "--plan-material-batch-sleep-seconds",
        type=float,
        default=3.0,
        help="Sleep seconds between plan-material batches during slow official fallback days.",
    )
    parser.add_argument(
        "--no-creative-fetch",
        action="store_true",
        help="Do not call creative/detail/video APIs during title/video metadata alignment.",
    )
    parser.add_argument("--skip-index", action="store_true", help="Skip material ranking index rebuild.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and report without writing changes.")
    return parser.parse_args()


def resolve_customer_center_ids(requested: list[str]) -> list[str]:
    normalized = [str(item or "").strip() for item in requested if str(item or "").strip()]
    if not normalized:
        normalized = [str(item or "").strip() for item in service.bound_customer_center_ids()]
    if not normalized:
        normalized = [str(service._current_customer_center_id() or "").strip()]
    return [item for item in dict.fromkeys(normalized) if item]


def money(value: Any) -> float:
    try:
        return round(float(value or 0.0), 2)
    except Exception:
        return 0.0


def int_value(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def validate_day(customer_center_id: str, day_key: str) -> dict[str, Any]:
    with service.db() as conn:
        plan_row = conn.execute(
            """
            SELECT ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS stat_cost,
                   COUNT(*) AS row_count
            FROM plan_daily
            WHERE customer_center_id = ?
              AND biz_date = ?
              AND UPPER(COALESCE(plan_source, '')) IN (?, ?, ?)
            """,
            (customer_center_id, day_key, *PLAN_SOURCE_SET),
        ).fetchone()
        material_daily_row = conn.execute(
            """
            SELECT ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS stat_cost,
                   COUNT(*) AS row_count
            FROM material_daily
            WHERE customer_center_id = ?
              AND biz_date = ?
            """,
            (customer_center_id, day_key),
        ).fetchone()
        relation_row = conn.execute(
            """
            SELECT
                ROUND(COALESCE(SUM(CASE WHEN UPPER(COALESCE(material_type, '')) <> 'TITLE' THEN stat_cost ELSE 0 END), 0)::numeric, 2) AS non_title_stat_cost,
                ROUND(COALESCE(SUM(CASE WHEN UPPER(COALESCE(material_type, '')) = 'TITLE' THEN stat_cost ELSE 0 END), 0)::numeric, 2) AS title_stat_cost,
                ROUND(COALESCE(SUM(CASE WHEN UPPER(COALESCE(material_type, '')) = 'UNATTRIBUTED_DELETED' THEN stat_cost ELSE 0 END), 0)::numeric, 2) AS unattributed_stat_cost,
                COUNT(*) AS row_count,
                SUM(CASE WHEN UPPER(COALESCE(material_type, '')) = 'TITLE'
                           AND (COALESCE(stat_cost, 0) > 0 OR COALESCE(pay_amount, 0) > 0 OR COALESCE(order_count, 0) > 0)
                         THEN 1 ELSE 0 END) AS title_positive_rows,
                SUM(CASE WHEN UPPER(COALESCE(material_type, '')) = 'VIDEO'
                           AND COALESCE(stat_cost, 0) > 0
                           AND COALESCE(backend_material_name, '') = ''
                         THEN 1 ELSE 0 END) AS video_missing_backend_rows
            FROM material_relation_daily
            WHERE customer_center_id = ?
              AND biz_date = ?
            """,
            (customer_center_id, day_key),
        ).fetchone()
        snapshot_row = conn.execute(
            """
            SELECT COUNT(*) AS row_count
            FROM material_snapshots
            WHERE customer_center_id = ?
              AND substr(snapshot_time, 1, 10) = ?
            """,
            (customer_center_id, day_key),
        ).fetchone()

    plan_cost = money((plan_row or {}).get("stat_cost"))
    material_daily_cost = money((material_daily_row or {}).get("stat_cost"))
    relation_non_title_cost = money((relation_row or {}).get("non_title_stat_cost"))
    return {
        "customer_center_id": customer_center_id,
        "day": day_key,
        "plan_cost": plan_cost,
        "plan_rows": int_value((plan_row or {}).get("row_count")),
        "material_daily_cost": material_daily_cost,
        "material_daily_rows": int_value((material_daily_row or {}).get("row_count")),
        "relation_non_title_cost": relation_non_title_cost,
        "relation_rows": int_value((relation_row or {}).get("row_count")),
        "relation_title_cost": money((relation_row or {}).get("title_stat_cost")),
        "title_positive_rows": int_value((relation_row or {}).get("title_positive_rows")),
        "unattributed_cost": money((relation_row or {}).get("unattributed_stat_cost")),
        "video_missing_backend_rows": int_value((relation_row or {}).get("video_missing_backend_rows")),
        "snapshot_rows": int_value((snapshot_row or {}).get("row_count")),
        "daily_minus_plan": round(material_daily_cost - plan_cost, 2),
        "relation_minus_plan": round(relation_non_title_cost - plan_cost, 2),
    }


def validation_errors(payload: dict[str, Any]) -> list[str]:
    plan_cost = money(payload.get("plan_cost"))
    errors: list[str] = []
    if plan_cost > 0 and abs(money(payload.get("daily_minus_plan"))) > 1.0:
        errors.append("material_daily_cost_mismatch")
    if plan_cost > 0 and abs(money(payload.get("relation_minus_plan"))) > 1.0:
        errors.append("relation_non_title_cost_mismatch")
    if int_value(payload.get("title_positive_rows")) > 0:
        errors.append("title_rows_still_have_metrics")
    return errors


def should_use_official_fallback(before: dict[str, Any]) -> bool:
    if money(before.get("plan_cost")) <= 0:
        return False
    return (
        int_value(before.get("material_daily_rows")) <= 0
        or int_value(before.get("relation_rows")) <= 0
        or int_value(before.get("snapshot_rows")) <= 0
    )


def zero_positive_title_metrics(conn: Any, customer_center_id: str, day_key: str) -> dict[str, Any]:
    relation_cursor = conn.execute(
        """
        UPDATE material_relation_daily
        SET stat_cost = 0,
            pay_amount = 0,
            total_pay_amount = 0,
            settled_pay_amount = 0,
            order_count = 0,
            settled_order_count = 0,
            overall_show_count = 0,
            overall_click_count = 0
        WHERE customer_center_id = ?
          AND biz_date = ?
          AND UPPER(COALESCE(material_type, '')) = 'TITLE'
          AND (
              COALESCE(stat_cost, 0) <> 0
              OR COALESCE(pay_amount, 0) <> 0
              OR COALESCE(total_pay_amount, 0) <> 0
              OR COALESCE(settled_pay_amount, 0) <> 0
              OR COALESCE(order_count, 0) <> 0
              OR COALESCE(settled_order_count, 0) <> 0
              OR COALESCE(overall_show_count, 0) <> 0
              OR COALESCE(overall_click_count, 0) <> 0
          )
        """,
        (customer_center_id, day_key),
    )
    snapshot_cursor = conn.execute(
        """
        UPDATE material_snapshots
        SET product_show_count = 0,
            product_click_count = 0,
            stat_cost = 0,
            pay_amount = 0,
            total_pay_amount = 0,
            settled_pay_amount = 0,
            order_count = 0,
            settled_order_count = 0,
            roi = 0
        WHERE customer_center_id = ?
          AND substr(snapshot_time, 1, 10) = ?
          AND UPPER(COALESCE(material_type, '')) = 'TITLE'
          AND (
              COALESCE(product_show_count, 0) <> 0
              OR COALESCE(product_click_count, 0) <> 0
              OR COALESCE(stat_cost, 0) <> 0
              OR COALESCE(pay_amount, 0) <> 0
              OR COALESCE(total_pay_amount, 0) <> 0
              OR COALESCE(settled_pay_amount, 0) <> 0
              OR COALESCE(order_count, 0) <> 0
              OR COALESCE(settled_order_count, 0) <> 0
          )
        """,
        (customer_center_id, day_key),
    )
    return {
        "relation_title_rows_zeroed": int(getattr(relation_cursor, "rowcount", 0) or 0),
        "snapshot_title_rows_zeroed": int(getattr(snapshot_cursor, "rowcount", 0) or 0),
    }


def postprocess_material_day(
    *,
    customer_center_id: str,
    day_key: str,
    dry_run: bool,
) -> dict[str, Any]:
    before = validate_day(customer_center_id, day_key)
    if dry_run:
        return {
            "updated": False,
            "dry_run": True,
            "before": before,
            "after": before,
            "title_zero": {"skipped": True},
            "unattributed_residual": {"skipped": True},
            "rebuilt_material_daily_rows": int_value(before.get("material_daily_rows")),
        }
    with service.db() as conn:
        title_zero = zero_positive_title_metrics(conn, customer_center_id, day_key)
        residual = add_unattributed_material_residuals(conn, customer_center_id, day_key)
        rebuilt_count = rebuild_material_daily_from_relations(conn, customer_center_id, day_key)
        service._invalidate_material_ranking_indexes_for_day(conn, day_key, customer_center_id)
    after = validate_day(customer_center_id, day_key)
    return {
        "updated": True,
        "before": before,
        "after": after,
        "title_zero": title_zero,
        "unattributed_residual": residual,
        "rebuilt_material_daily_rows": rebuilt_count,
    }


def local_repair_day(
    *,
    customer_center_id: str,
    day_key: str,
    fetch_creative: bool,
    dry_run: bool,
) -> dict[str, Any]:
    if dry_run:
        alignment = service.repair_material_title_video_alignment_day(
            customer_center_id,
            day_key,
            fetch_creative=fetch_creative,
            dry_run=True,
        )
        return {
            "mode": "local_only",
            "dry_run": True,
            "alignment": alignment,
        }
    with service.db() as conn:
        before_counts = service._material_history_day_row_counts(conn, customer_center_id, day_key)
        rebuild_result = service._restore_material_history_day_from_all_snapshots(conn, customer_center_id, day_key)
        service._invalidate_material_ranking_indexes_for_day(conn, day_key, customer_center_id)
    alignment = service.repair_material_title_video_alignment_day(
        customer_center_id,
        day_key,
        fetch_creative=fetch_creative,
        dry_run=False,
    )
    return {
        "mode": "local_only",
        "before_counts": before_counts,
        "rebuild": rebuild_result,
        "alignment": alignment,
    }


def slow_official_repair_day(
    *,
    customer_center_id: str,
    day_key: str,
    requests_per_minute: int,
    workers: int,
    batch_size: int,
    batch_sleep_seconds: float,
    dry_run: bool,
) -> dict[str, Any]:
    target = {"customer_center_id": customer_center_id, "target_date": day_key}
    if dry_run:
        return {
            "mode": "slow_official_fallback",
            "dry_run": True,
            "target": target,
            "requests_per_minute": max(int(requests_per_minute or 0), 1),
            "workers": max(int(workers or 0), 1),
            "plan_material_batch_size": max(int(batch_size or 0), 1),
            "plan_material_batch_sleep_seconds": max(float(batch_sleep_seconds or 0.0), 0.0),
        }
    result = service.refresh_extended_history_targets(
        [target],
        material_collection_mode="full_snapshot",
        force_replace=False,
        workers_override=max(int(workers or 0), 1),
        plan_material_requests_per_minute_override=max(int(requests_per_minute or 0), 1),
        plan_material_batch_size_override=max(int(batch_size or 0), 1),
        plan_material_batch_sleep_seconds_override=max(float(batch_sleep_seconds or 0.0), 0.0),
    )
    return {
        "mode": "slow_official_fallback",
        "target": target,
        "requests_per_minute": max(int(requests_per_minute or 0), 1),
        "workers": max(int(workers or 0), 1),
        "plan_material_batch_size": max(int(batch_size or 0), 1),
        "plan_material_batch_sleep_seconds": max(float(batch_sleep_seconds or 0.0), 0.0),
        "result": result,
        "error_count": int(result.get("error_count", 0) or 0),
    }


def repair_customer_center_day(
    *,
    customer_center_id: str,
    day_key: str,
    before: dict[str, Any],
    local_only: bool,
    fetch_creative: bool,
    requests_per_minute: int,
    fallback_workers: int,
    batch_size: int,
    batch_sleep_seconds: float,
    dry_run: bool,
) -> dict[str, Any]:
    if local_only or not should_use_official_fallback(before):
        repair_result = local_repair_day(
            customer_center_id=customer_center_id,
            day_key=day_key,
            fetch_creative=fetch_creative,
            dry_run=dry_run,
        )
        repair_error_count = int((repair_result.get("alignment") or {}).get("error_count", 0) or 0)
    else:
        repair_result = slow_official_repair_day(
            customer_center_id=customer_center_id,
            day_key=day_key,
            requests_per_minute=requests_per_minute,
            workers=fallback_workers,
            batch_size=batch_size,
            batch_sleep_seconds=batch_sleep_seconds,
            dry_run=dry_run,
        )
        repair_error_count = int(repair_result.get("error_count", 0) or 0)
    postprocess_result = postprocess_material_day(
        customer_center_id=customer_center_id,
        day_key=day_key,
        dry_run=dry_run,
    )
    return {
        "customer_center_id": customer_center_id,
        "target_date": day_key,
        "mode": repair_result.get("mode") or "unknown",
        "repair": repair_result,
        "postprocess": postprocess_result,
        "error_count": repair_error_count,
    }


def finalize_repair_day(
    *,
    customer_center_ids: list[str],
    day_key: str,
    dry_run: bool,
) -> dict[str, Any]:
    targets = [{"customer_center_id": customer_center_id, "target_date": day_key} for customer_center_id in customer_center_ids]
    if dry_run:
        return {
            "mode": "official_closed_day_finalize",
            "dry_run": True,
            "targets": targets,
        }
    result, success_keys, snapshot_time_map = service._finalize_material_history_targets_from_local_snapshots(targets)
    return {
        "mode": "official_closed_day_finalize",
        "result": result,
        "success_keys": sorted([{"customer_center_id": item[0], "target_date": item[1]} for item in success_keys], key=lambda x: (x["customer_center_id"], x["target_date"])),
        "snapshot_time_map": {f"{key[0]}|{key[1]}": value for key, value in snapshot_time_map.items()},
    }


def rebuild_indexes(days: list[str], *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "target_days": days,
            "skipped": True,
        }
    return service._refresh_material_ranking_indexes_after_history_days(days)


def main() -> int:
    args = parse_args()
    days = day_range(args.start_date, args.end_date)
    customer_center_ids = resolve_customer_center_ids(args.customer_center_id)
    fetch_creative = not bool(args.no_creative_fetch)
    started_at = now_text()

    log(
        "repair_start",
        started_at=started_at,
        days=days,
        customer_center_ids=customer_center_ids,
        local_only=bool(args.local_only),
        fetch_creative=fetch_creative,
        dry_run=bool(args.dry_run),
        skip_index=bool(args.skip_index),
        requests_per_minute=int(args.requests_per_minute),
        fallback_workers=int(args.fallback_workers),
        plan_material_batch_size=int(args.plan_material_batch_size),
        plan_material_batch_sleep_seconds=float(args.plan_material_batch_sleep_seconds),
    )

    if not customer_center_ids:
        log("repair_done", ok=False, reason="no_customer_center_ids")
        return 2

    error_count = 0
    api_warning_count = 0
    day_results: list[dict[str, Any]] = []
    before_validations: list[dict[str, Any]] = []
    after_validations: list[dict[str, Any]] = []
    index_result: dict[str, Any] = {"ok": True, "skipped": True, "reason": "skip_index"}

    service.pause_hot_syncs("manual_material_alignment_range_repair")
    try:
        with service._distributed_runtime_lock(
            "manual-material-alignment-range-repair",
            timeout_seconds=21600,
            blocking_timeout_seconds=0,
        ) as acquired:
            if not acquired:
                log("repair_done", ok=False, reason="manual_material_alignment_repair_lock_busy")
                return 3

            for day_key in days:
                before_by_customer: dict[str, dict[str, Any]] = {}
                for customer_center_id in customer_center_ids:
                    before = validate_day(customer_center_id, day_key)
                    before_by_customer[customer_center_id] = before
                    before_validations.append(before)
                    log("day_before", **before)

                try:
                    per_customer_results = []
                    for customer_center_id in customer_center_ids:
                        per_customer_results.append(
                            repair_customer_center_day(
                                customer_center_id=customer_center_id,
                                day_key=day_key,
                                before=before_by_customer[customer_center_id],
                                local_only=bool(args.local_only),
                                fetch_creative=fetch_creative,
                                requests_per_minute=int(args.requests_per_minute),
                                fallback_workers=int(args.fallback_workers),
                                batch_size=int(args.plan_material_batch_size),
                                batch_sleep_seconds=float(args.plan_material_batch_sleep_seconds),
                                dry_run=bool(args.dry_run),
                            )
                        )
                    day_result = {
                        "day": day_key,
                        "mode": "per_customer_local_or_slow_official",
                        "customer_results": per_customer_results,
                        "error_count": sum(int(item.get("error_count", 0) or 0) for item in per_customer_results),
                    }
                    api_warning_count += int(day_result.get("error_count", 0) or 0)
                    day_results.append(day_result)
                    log("day_repair_result", **day_result)
                except Exception as exc:  # noqa: BLE001
                    error_count += 1
                    error_payload = {
                        "day": day_key,
                        "error": str(exc),
                        "traceback": traceback.format_exc(limit=5),
                    }
                    day_results.append({"day": day_key, "ok": False, **error_payload})
                    log("day_repair_error", **error_payload)

                for customer_center_id in customer_center_ids:
                    after = validate_day(customer_center_id, day_key)
                    after_validations.append(after)
                    log("day_after", **after)
                    validation_error_items = validation_errors(after)
                    if validation_error_items:
                        error_count += 1
                        log("day_validation_failed", errors=validation_error_items, **after)

            if not args.skip_index:
                try:
                    index_result = rebuild_indexes(days, dry_run=bool(args.dry_run))
                    if not bool(index_result.get("ok", True)):
                        error_count += 1
                    log("index_rebuild_result", **index_result)
                except Exception as exc:  # noqa: BLE001
                    error_count += 1
                    index_result = {
                        "ok": False,
                        "error": str(exc),
                        "traceback": traceback.format_exc(limit=5),
                    }
                    log("index_rebuild_error", **index_result)

            if not args.dry_run:
                service.clear_material_runtime_caches(scope=MATERIAL_CACHE_SCOPE_HISTORY)
                service.clear_material_runtime_caches(scope="all")

    finally:
        service.resume_hot_syncs()

    finished_at = now_text()
    summary = {
        "ok": error_count == 0,
        "started_at": started_at,
        "finished_at": finished_at,
        "days": days,
        "customer_center_ids": customer_center_ids,
        "error_count": error_count,
        "api_warning_count": api_warning_count,
        "day_result_count": len(day_results),
        "index_result": index_result,
        "before_validations": before_validations,
        "after_validations": after_validations,
    }
    log("repair_done", **summary)
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
