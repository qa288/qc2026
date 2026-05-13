#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for candidate in (ROOT_DIR, TOOLS_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from dashboard.main import service  # noqa: E402
from tools.material_plan_day_repair import (  # noqa: E402
    active_plan_rows_for_day,
    mismatched_plan_rows_for_day,
)
from tools.official_daily_align import (  # noqa: E402
    add_unattributed_material_residuals,
    material_counts,
    official_plan_ids,
    performance_counts,
    prune_table_to_official_plans,
    rebuild_material_daily_from_relations,
    rebuild_material_prefix_indexes,
    resolve_customer_center_ids,
)


def log(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False, sort_keys=True), flush=True)


def parse_day(value: str, name: str) -> datetime.date:
    text = str(value or "").strip()[:10]
    if not text:
        raise ValueError(f"{name} is required")
    return datetime.strptime(text, "%Y-%m-%d").date()


def iter_days(start_date: str, end_date: str) -> list[str]:
    start_day = parse_day(start_date, "start_date")
    end_day = parse_day(end_date, "end_date")
    if end_day < start_day:
        raise ValueError("end_date must be greater than or equal to start_date")
    days: list[str] = []
    current = start_day
    while current <= end_day:
        days.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return days


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fast material history repair for a date range. It fetches official material data only "
            "for plan_daily plans that can carry material cost, then prunes stale rows, adds official "
            "unattributed residual rows, rebuilds material_daily, and rebuilds indexes once at the end."
        )
    )
    parser.add_argument("--start-date", required=True, help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument(
        "--customer-center-id",
        action="append",
        default=[],
        help="Customer center id. May be supplied more than once; defaults to bound centers.",
    )
    parser.add_argument(
        "--plan-scope",
        choices=("mismatch", "all"),
        default="all",
        help="all fetches every active real plan with metrics; mismatch fetches only plans currently out of alignment.",
    )
    parser.add_argument("--workers", type=int, default=10, help="Per-day official plan-material worker count.")
    parser.add_argument("--requests-per-minute", type=int, default=900, help="Plan-material request rate limit.")
    parser.add_argument("--batch-size", type=int, default=16, help="Plan-material batch size.")
    parser.add_argument("--batch-sleep-seconds", type=float, default=0.0, help="Sleep between plan batches.")
    parser.add_argument(
        "--day-workers",
        type=int,
        default=1,
        help="Number of days to repair in parallel. Keep low unless official/API limits are known.",
    )
    parser.add_argument(
        "--with-title-video-alignment",
        action="store_true",
        help="Also run creative title/video alignment after each day. This is slower and not required for spend parity.",
    )
    parser.add_argument(
        "--title-video-alignment-scope",
        choices=("selected", "all"),
        default="selected",
        help="When title/video alignment is enabled, align only days with fetched plans or every processed day.",
    )
    parser.add_argument("--skip-residual", action="store_true", help="Do not add unattributed residual material rows.")
    parser.add_argument("--skip-index", action="store_true", help="Do not rebuild material ranking prefix indexes.")
    parser.add_argument("--dry-run", action="store_true", help="Select days/plans without writing.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop at the first day error.")
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    return parser.parse_args()


def money(value: Any) -> float:
    try:
        return round(float(value or 0.0), 2)
    except Exception:
        return 0.0


def day_window(day_key: str, customer_center_id: str) -> tuple[str, str, str]:
    try:
        config = service._scoped_config_for_customer_center(customer_center_id)
    except Exception:
        config = {}
    tz_name = str(config.get("timezone") or service.read_config().get("timezone") or "Asia/Shanghai")
    tz = ZoneInfo(tz_name)
    target_day = datetime.strptime(day_key, "%Y-%m-%d").date()
    start_dt = datetime(target_day.year, target_day.month, target_day.day, 0, 0, 0, tzinfo=tz)
    end_dt = datetime(target_day.year, target_day.month, target_day.day, 23, 59, 59, tzinfo=tz)
    return (
        service._closed_day_snapshot_time(end_dt),
        start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        end_dt.strftime("%Y-%m-%d %H:%M:%S"),
    )


def selected_plan_rows(conn: Any, customer_center_id: str, day_key: str, plan_scope: str) -> list[dict[str, Any]]:
    if str(plan_scope or "").strip().lower() == "mismatch":
        return mismatched_plan_rows_for_day(conn, customer_center_id, day_key)
    return active_plan_rows_for_day(conn, customer_center_id, day_key)


def normalized_material_counts(counts: dict[str, Any]) -> dict[str, Any]:
    return {
        "material_daily_rows": int((counts.get("material_daily") or {}).get("row_count") or 0),
        "material_daily_cost": money((counts.get("material_daily") or {}).get("stat_cost")),
        "relation_rows": int((counts.get("material_relation_daily") or {}).get("row_count") or 0),
        "relation_non_title_rows": int((counts.get("material_relation_daily_non_title") or {}).get("row_count") or 0),
        "relation_non_title_cost": money((counts.get("material_relation_daily_non_title") or {}).get("stat_cost")),
        "snapshot_rows": int((counts.get("material_snapshots") or {}).get("row_count") or 0),
    }


def validate_day(conn: Any, customer_center_id: str, day_key: str) -> dict[str, Any]:
    perf = performance_counts(conn, customer_center_id, day_key)
    mats = material_counts(conn, customer_center_id, day_key)
    plan_cost = money((perf.get("plan_daily") or {}).get("stat_cost"))
    material_cost = money((mats.get("material_relation_daily_non_title") or {}).get("stat_cost"))
    daily_cost = money((mats.get("material_daily") or {}).get("stat_cost"))
    return {
        "plan_cost": plan_cost,
        "material_relation_non_title_cost": material_cost,
        "material_daily_cost": daily_cost,
        "relation_diff": money(material_cost - plan_cost),
        "daily_diff": money(daily_cost - plan_cost),
        "ok": abs(material_cost - plan_cost) < 1.0 and abs(daily_cost - plan_cost) < 1.0,
    }


def force_material_daily_window(conn: Any, customer_center_id: str, day_key: str, snapshot_time: str) -> int:
    cursor = conn.execute(
        """
        UPDATE material_daily
        SET snapshot_time = CASE WHEN COALESCE(snapshot_time, '') = '' THEN ? ELSE snapshot_time END,
            window_start = CASE WHEN COALESCE(window_start, '') = '' THEN ? ELSE window_start END,
            window_end = CASE WHEN COALESCE(window_end, '') = '' THEN ? ELSE window_end END
        WHERE customer_center_id = ?
          AND biz_date = ?
          AND (
                COALESCE(snapshot_time, '') = ''
             OR COALESCE(window_start, '') = ''
             OR COALESCE(window_end, '') = ''
          )
        """,
        (snapshot_time, f"{day_key} 00:00:00", f"{day_key} 23:59:59", customer_center_id, day_key),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def repair_day(args: argparse.Namespace, customer_center_id: str, day_key: str) -> dict[str, Any]:
    started = time.monotonic()
    snapshot_time, window_start, window_end = day_window(day_key, customer_center_id)
    result: dict[str, Any] = {
        "customer_center_id": customer_center_id,
        "day": day_key,
        "plan_scope": args.plan_scope,
        "updated": False,
        "timings": {},
    }
    with service.db() as conn:
        perf_before = performance_counts(conn, customer_center_id, day_key)
        mat_before = material_counts(conn, customer_center_id, day_key)
        plans = selected_plan_rows(conn, customer_center_id, day_key, args.plan_scope)
    plan_ids = sorted({int(row.get("ad_id") or 0) for row in plans if int(row.get("ad_id") or 0) > 0})
    result["performance_before"] = perf_before
    result["material_before"] = normalized_material_counts(mat_before)
    result["selected_plan_count"] = len(plan_ids)
    result["selected_plan_cost"] = money(sum(float(row.get("stat_cost") or 0.0) for row in plans))
    log(
        "day_selected",
        customer_center_id=customer_center_id,
        day=day_key,
        plan_scope=args.plan_scope,
        selected_plan_count=len(plan_ids),
        selected_plan_cost=result["selected_plan_cost"],
    )
    if args.dry_run:
        with service.db() as conn:
            result["validation_after"] = validate_day(conn, customer_center_id, day_key)
        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
        return result

    if plan_ids:
        client = service._build_scoped_customer_center_client(customer_center_id)
        scoped_config = service._scoped_config_for_customer_center(customer_center_id)
        refresh_started = time.monotonic()
        result["history_result"] = service._refresh_material_history_for_changed_plans(
            client=client,
            customer_center_id=customer_center_id,
            target_date=day_key,
            snapshot_time=snapshot_time,
            window_start=window_start,
            window_end=window_end,
            scoped_config=scoped_config,
            changed_plan_ids=plan_ids,
            changed_plan_rows=plans,
            workers_override=max(int(args.workers or 1), 1),
            plan_material_requests_per_minute_override=max(int(args.requests_per_minute or 0), 0),
            plan_material_batch_size_override=max(int(args.batch_size or 0), 0),
            plan_material_batch_sleep_seconds_override=max(float(args.batch_sleep_seconds or 0.0), 0.0),
        )
        result["timings"]["refresh_materials"] = round(time.monotonic() - refresh_started, 2)
        log(
            "day_refreshed",
            customer_center_id=customer_center_id,
            day=day_key,
            material_plan_fetch_count=result["history_result"].get("material_plan_fetch_count"),
            material_row_count=result["history_result"].get("material_row_count"),
            error_count=result["history_result"].get("error_count"),
            elapsed_seconds=result["timings"]["refresh_materials"],
        )
    else:
        result["history_result"] = {"skipped": True, "reason": "no_selected_plans"}
        result["timings"]["refresh_materials"] = 0.0

    post_started = time.monotonic()
    with service.db() as conn:
        allowed_ad_ids = official_plan_ids(conn, customer_center_id, day_key)
        pruned_relation_rows = prune_table_to_official_plans(
            conn,
            table="material_relation_daily",
            customer_center_id=customer_center_id,
            day_key=day_key,
            allowed_ad_ids=allowed_ad_ids,
        )
        pruned_snapshot_rows = prune_table_to_official_plans(
            conn,
            table="material_snapshots",
            customer_center_id=customer_center_id,
            day_key=day_key,
            allowed_ad_ids=allowed_ad_ids,
            snapshot_table=True,
        )
        residual_result = (
            {"skipped": True}
            if args.skip_residual
            else add_unattributed_material_residuals(conn, customer_center_id, day_key)
        )
        rebuilt_rows = rebuild_material_daily_from_relations(conn, customer_center_id, day_key)
        window_fixed_rows = force_material_daily_window(conn, customer_center_id, day_key, snapshot_time)
        validation_after = validate_day(conn, customer_center_id, day_key)
        mat_after = normalized_material_counts(material_counts(conn, customer_center_id, day_key))
    result["postprocess"] = {
        "pruned_relation_rows": pruned_relation_rows,
        "pruned_snapshot_rows": pruned_snapshot_rows,
        "unattributed_residual": residual_result,
        "rebuilt_material_daily_rows": rebuilt_rows,
        "fixed_material_daily_window_rows": window_fixed_rows,
    }
    result["validation_after"] = validation_after
    result["material_after"] = mat_after
    result["timings"]["postprocess"] = round(time.monotonic() - post_started, 2)
    log(
        "day_postprocessed",
        customer_center_id=customer_center_id,
        day=day_key,
        plan_cost=validation_after["plan_cost"],
        material_cost=validation_after["material_relation_non_title_cost"],
        material_daily_cost=validation_after["material_daily_cost"],
        relation_diff=validation_after["relation_diff"],
        ok=validation_after["ok"],
        elapsed_seconds=result["timings"]["postprocess"],
    )

    should_align_title_video = bool(args.with_title_video_alignment) and (
        str(args.title_video_alignment_scope or "selected") == "all" or bool(plan_ids)
    )
    if should_align_title_video:
        align_started = time.monotonic()
        result["title_video_alignment"] = service.repair_material_title_video_alignment_day(
            customer_center_id,
            day_key,
            fetch_creative=True,
            dry_run=False,
            ad_ids=plan_ids if str(args.title_video_alignment_scope or "selected") == "selected" else None,
        )
        result["timings"]["title_video_alignment"] = round(time.monotonic() - align_started, 2)
    else:
        result["title_video_alignment"] = {
            "skipped": True,
            "reason": "disabled_for_fast_repair" if not args.with_title_video_alignment else "no_selected_plans",
        }

    result["updated"] = True
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return result


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [item for item in results if item.get("error")]
    validation_failed = [
        item
        for item in results
        if not item.get("error") and not bool((item.get("validation_after") or {}).get("ok", False))
    ]
    total_plan_cost = money(sum(float((item.get("validation_after") or {}).get("plan_cost") or 0.0) for item in results))
    total_material_cost = money(
        sum(float((item.get("validation_after") or {}).get("material_relation_non_title_cost") or 0.0) for item in results)
    )
    return {
        "day_count": len(results),
        "updated_day_count": sum(1 for item in results if bool(item.get("updated"))),
        "failed_day_count": len(failed),
        "validation_failed_day_count": len(validation_failed),
        "total_plan_cost": total_plan_cost,
        "total_material_relation_non_title_cost": total_material_cost,
        "total_diff": money(total_material_cost - total_plan_cost),
        "failed_days": [{"day": item.get("day"), "error": item.get("error")} for item in failed],
        "validation_failed_days": [
            {
                "day": item.get("day"),
                "validation_after": item.get("validation_after"),
            }
            for item in validation_failed[:50]
        ],
    }


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    service.init_db_once()
    service.bootstrap_token_store()
    service.assert_runtime_client_compatibility()

    days = iter_days(args.start_date, args.end_date)
    customer_center_ids = resolve_customer_center_ids([str(item).strip() for item in args.customer_center_id])
    if not customer_center_ids:
        raise RuntimeError("No customer_center_id is available")

    tasks = [(customer_center_id, day_key) for customer_center_id in customer_center_ids for day_key in days]
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    day_workers = max(int(args.day_workers or 1), 1)
    log(
        "range_start",
        start_date=days[0],
        end_date=days[-1],
        customer_center_ids=customer_center_ids,
        task_count=len(tasks),
        plan_scope=args.plan_scope,
        day_workers=day_workers,
        workers=args.workers,
        requests_per_minute=args.requests_per_minute,
        batch_size=args.batch_size,
        with_title_video_alignment=bool(args.with_title_video_alignment),
        title_video_alignment_scope=str(args.title_video_alignment_scope or "selected"),
        skip_index=bool(args.skip_index),
        dry_run=bool(args.dry_run),
    )

    if day_workers == 1 or args.stop_on_error:
        for customer_center_id, day_key in tasks:
            try:
                results.append(repair_day(args, customer_center_id, day_key))
            except Exception as exc:  # noqa: BLE001
                error_item = {"customer_center_id": customer_center_id, "day": day_key, "error": str(exc)}
                errors.append(error_item)
                results.append(error_item)
                log("day_error", **error_item)
                if args.stop_on_error:
                    break
    else:
        with ThreadPoolExecutor(max_workers=day_workers) as pool:
            future_map = {
                pool.submit(repair_day, args, customer_center_id, day_key): (customer_center_id, day_key)
                for customer_center_id, day_key in tasks
            }
            for future in as_completed(future_map):
                customer_center_id, day_key = future_map[future]
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    error_item = {"customer_center_id": customer_center_id, "day": day_key, "error": str(exc)}
                    errors.append(error_item)
                    results.append(error_item)
                    log("day_error", **error_item)

    index_result: dict[str, Any]
    if args.skip_index or args.dry_run:
        index_result = {"skipped": True}
    else:
        index_started = time.monotonic()
        index_result = rebuild_material_prefix_indexes(days[0], days[-1], customer_center_ids)
        index_result["elapsed_seconds"] = round(time.monotonic() - index_started, 2)
        log("index_rebuilt", ok=index_result.get("ok"), elapsed_seconds=index_result["elapsed_seconds"])

    payload = {
        "args": vars(args),
        "customer_center_ids": customer_center_ids,
        "start_date": days[0],
        "end_date": days[-1],
        "summary": summarize(results),
        "index_result": index_result,
        "errors": errors,
        "results": sorted(results, key=lambda item: (str(item.get("customer_center_id") or ""), str(item.get("day") or ""))),
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }
    output = str(args.output or "").strip()
    if not output:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = str(ROOT_DIR / "data" / f"material_plan_range_repair_fast_{days[0]}_{days[-1]}_{stamp}.json")
    Path(output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log("range_done", output=output, elapsed_seconds=payload["elapsed_seconds"], **payload["summary"])
    return 1 if payload["summary"]["failed_day_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
