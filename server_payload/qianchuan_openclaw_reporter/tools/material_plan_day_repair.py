#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dashboard.main import (  # noqa: E402
    PLAN_SOURCE_UNI_CUBIC,
    PLAN_SOURCE_UNI_PROMOTION,
    PLAN_SOURCE_UNI_REPORT,
    service,
)
from tools.official_daily_align import (  # noqa: E402
    add_unattributed_material_residuals,
    material_counts,
    official_plan_ids,
    performance_counts,
    prune_table_to_official_plans,
    rebuild_material_daily_from_relations,
    rebuild_material_prefix_indexes,
)


REAL_PLAN_SOURCES = {
    PLAN_SOURCE_UNI_PROMOTION,
    PLAN_SOURCE_UNI_CUBIC,
    PLAN_SOURCE_UNI_REPORT,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repair one material history day by fetching materials for plan_daily plans only."
    )
    parser.add_argument("--date", required=True, help="Target day, YYYY-MM-DD.")
    parser.add_argument("--customer-center-id", default="", help="Customer center id.")
    parser.add_argument(
        "--plan-scope",
        default="mismatch",
        choices=("mismatch", "all"),
        help="Fetch only mismatched plans or all active real plans for the day.",
    )
    parser.add_argument("--workers", type=int, default=8, help="Plan material worker count.")
    parser.add_argument("--requests-per-minute", type=int, default=300, help="Plan material request rate limit.")
    parser.add_argument("--batch-size", type=int, default=0, help="Optional plan material batch size.")
    parser.add_argument("--batch-sleep-seconds", type=float, default=0.0, help="Sleep between batches.")
    parser.add_argument("--skip-title-video-alignment", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument("--no-prune", action="store_true", help="Do not prune material rows outside plan_daily.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect selected plans without writing.")
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    return parser.parse_args()


def log(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False, sort_keys=True), flush=True)


def resolve_customer_center_id(requested: str) -> str:
    requested = str(requested or "").strip()
    if requested:
        return requested
    cfg = service.read_config()
    configured = str(cfg.get("customer_center_id") or "").strip()
    if configured:
        return configured
    with service.db() as conn:
        row = conn.execute(
            "SELECT customer_center_id FROM summary_daily ORDER BY biz_date DESC LIMIT 1"
        ).fetchone()
    return str((row or {}).get("customer_center_id") or "").strip()


def active_plan_rows_for_day(conn: Any, customer_center_id: str, day_key: str) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM plan_daily
            WHERE customer_center_id = ?
              AND biz_date = ?
              AND ad_id > 0
              AND (
                    ABS(COALESCE(stat_cost, 0)) >= 0.005
                 OR ABS(COALESCE(pay_amount, 0)) >= 0.005
                 OR COALESCE(order_count, 0) <> 0
              )
            ORDER BY stat_cost DESC, ad_id ASC
            """,
            (customer_center_id, day_key),
        ).fetchall()
    ]
    return [
        row
        for row in rows
        if str(row.get("plan_source") or "").strip().upper() in REAL_PLAN_SOURCES
        and service._plan_row_has_material_activity(row)
    ]


def mismatched_plan_rows_for_day(conn: Any, customer_center_id: str, day_key: str) -> list[dict[str, Any]]:
    plan_rows = active_plan_rows_for_day(conn, customer_center_id, day_key)
    if not plan_rows:
        return []
    ad_ids = sorted({int(row.get("ad_id") or 0) for row in plan_rows if int(row.get("ad_id") or 0) > 0})
    material_by_ad: dict[int, dict[str, Any]] = {}
    for start in range(0, len(ad_ids), 400):
        chunk = ad_ids[start : start + 400]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT ad_id,
                   COUNT(*) AS row_count,
                   COALESCE(SUM(CASE WHEN COALESCE(material_type, '') <> 'TITLE' THEN stat_cost ELSE 0 END), 0) AS stat_cost,
                   COALESCE(SUM(CASE WHEN COALESCE(material_type, '') <> 'TITLE' THEN pay_amount ELSE 0 END), 0) AS pay_amount,
                   COALESCE(SUM(CASE WHEN COALESCE(material_type, '') <> 'TITLE' THEN order_count ELSE 0 END), 0) AS order_count
            FROM material_relation_daily
            WHERE customer_center_id = ?
              AND biz_date = ?
              AND ad_id IN ({placeholders})
            GROUP BY ad_id
            """,
            [customer_center_id, day_key, *chunk],
        ).fetchall()
        for row in rows:
            material_by_ad[int(row["ad_id"] or 0)] = dict(row)
    selected: list[dict[str, Any]] = []
    for row in plan_rows:
        ad_id = int(row.get("ad_id") or 0)
        material = material_by_ad.get(ad_id) or {}
        plan_cost = round(float(row.get("stat_cost") or 0.0), 2)
        plan_pay = round(float(row.get("pay_amount") or 0.0), 2)
        plan_orders = int(float(row.get("order_count") or 0))
        material_cost = round(float(material.get("stat_cost") or 0.0), 2)
        material_pay = round(float(material.get("pay_amount") or 0.0), 2)
        material_orders = int(float(material.get("order_count") or 0))
        row_count = int(material.get("row_count") or 0)
        if (
            row_count <= 0
            or abs(plan_cost - material_cost) >= 1.0
            or abs(plan_pay - material_pay) >= 1.0
            or abs(plan_orders - material_orders) >= 1
        ):
            selected.append(row)
    return selected


def timed(result: dict[str, Any], key: str, func: Any) -> Any:
    started = time.monotonic()
    try:
        return func()
    finally:
        result.setdefault("timings", {})[key] = round(time.monotonic() - started, 2)


def repair_day(args: argparse.Namespace) -> dict[str, Any]:
    service.init_db_once()
    service.bootstrap_token_store()
    service.assert_runtime_client_compatibility()

    day_key = str(args.date).strip()[:10]
    customer_center_id = resolve_customer_center_id(args.customer_center_id)
    if not customer_center_id:
        raise RuntimeError("customer_center_id is required")

    config = service.read_config()
    tz_name = str(config.get("timezone") or "Asia/Shanghai").strip() or "Asia/Shanghai"
    tz = ZoneInfo(tz_name)
    target_day = datetime.strptime(day_key, "%Y-%m-%d").date()
    day_start = datetime(target_day.year, target_day.month, target_day.day, 0, 0, 0, tzinfo=tz)
    day_end = datetime(target_day.year, target_day.month, target_day.day, 23, 59, 59, tzinfo=tz)
    window_start = day_start.strftime("%Y-%m-%d %H:%M:%S")
    window_end = day_end.strftime("%Y-%m-%d %H:%M:%S")
    snapshot_time = service._closed_day_snapshot_time(day_end)

    result: dict[str, Any] = {
        "customer_center_id": customer_center_id,
        "day": day_key,
        "plan_scope": str(args.plan_scope),
        "updated": False,
        "timings": {},
    }
    with service.db() as conn:
        result["performance_before"] = performance_counts(conn, customer_center_id, day_key)
        result["material_before"] = material_counts(conn, customer_center_id, day_key)
        if args.plan_scope == "all":
            selected_plan_rows = active_plan_rows_for_day(conn, customer_center_id, day_key)
        else:
            selected_plan_rows = mismatched_plan_rows_for_day(conn, customer_center_id, day_key)
    changed_plan_ids = sorted({int(row.get("ad_id") or 0) for row in selected_plan_rows if int(row.get("ad_id") or 0) > 0})
    result["selected_plan_count"] = len(changed_plan_ids)
    result["selected_plan_cost"] = round(sum(float(row.get("stat_cost") or 0.0) for row in selected_plan_rows), 2)
    result["selected_plan_samples"] = [
        {
            "advertiser_id": int(row.get("advertiser_id") or 0),
            "advertiser_name": str(row.get("advertiser_name") or ""),
            "ad_id": int(row.get("ad_id") or 0),
            "ad_name": str(row.get("ad_name") or ""),
            "stat_cost": round(float(row.get("stat_cost") or 0.0), 2),
        }
        for row in selected_plan_rows[:20]
    ]
    log(
        "selected_plans",
        day=day_key,
        customer_center_id=customer_center_id,
        plan_scope=args.plan_scope,
        selected_plan_count=len(changed_plan_ids),
        selected_plan_cost=result["selected_plan_cost"],
    )
    if args.dry_run or not changed_plan_ids:
        with service.db() as conn:
            result["material_after"] = material_counts(conn, customer_center_id, day_key)
            result["performance_after"] = performance_counts(conn, customer_center_id, day_key)
        return result

    client = service._build_scoped_customer_center_client(customer_center_id)
    scoped_config = service._scoped_config_for_customer_center(customer_center_id)

    def refresh_materials() -> dict[str, Any]:
        return service._refresh_material_history_for_changed_plans(
            client=client,
            customer_center_id=customer_center_id,
            target_date=day_key,
            snapshot_time=snapshot_time,
            window_start=window_start,
            window_end=window_end,
            scoped_config=scoped_config,
            changed_plan_ids=changed_plan_ids,
            changed_plan_rows=selected_plan_rows,
            workers_override=max(int(args.workers or 1), 1),
            plan_material_requests_per_minute_override=max(int(args.requests_per_minute or 0), 0),
            plan_material_batch_size_override=max(int(args.batch_size or 0), 0),
            plan_material_batch_sleep_seconds_override=max(float(args.batch_sleep_seconds or 0.0), 0.0),
        )

    log("refresh_materials_start", day=day_key, selected_plan_count=len(changed_plan_ids))
    result["history_result"] = timed(result, "refresh_materials", refresh_materials)
    log(
        "refresh_materials_done",
        day=day_key,
        changed_plan_count=result["history_result"].get("changed_plan_count"),
        material_row_count=result["history_result"].get("material_row_count"),
        error_count=result["history_result"].get("error_count"),
        elapsed_seconds=result["timings"]["refresh_materials"],
    )

    def postprocess() -> dict[str, Any]:
        with service.db() as conn:
            if args.no_prune:
                pruned_relation_rows = 0
                pruned_snapshot_rows = 0
            else:
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
            residual = add_unattributed_material_residuals(conn, customer_center_id, day_key)
            rebuilt_rows = rebuild_material_daily_from_relations(conn, customer_center_id, day_key)
        return {
            "pruned_relation_rows": pruned_relation_rows,
            "pruned_snapshot_rows": pruned_snapshot_rows,
            "unattributed_residual": residual,
            "rebuilt_material_daily_rows": rebuilt_rows,
        }

    log("postprocess_start", day=day_key)
    result["postprocess"] = timed(result, "postprocess", postprocess)
    log("postprocess_done", day=day_key, elapsed_seconds=result["timings"]["postprocess"], **result["postprocess"])

    if args.skip_title_video_alignment:
        result["title_video_alignment"] = {"skipped": True}
    else:
        log("title_video_alignment_start", day=day_key)
        result["title_video_alignment"] = timed(
            result,
            "title_video_alignment",
            lambda: service.repair_material_title_video_alignment_day(
                customer_center_id,
                day_key,
                fetch_creative=True,
                dry_run=False,
            ),
        )
        log(
            "title_video_alignment_done",
            day=day_key,
            elapsed_seconds=result["timings"]["title_video_alignment"],
            updated=result["title_video_alignment"].get("updated"),
            error_count=result["title_video_alignment"].get("error_count"),
        )

    if args.skip_index:
        result["index_result"] = {"skipped": True}
    else:
        log("index_rebuild_start", day=day_key)
        result["index_result"] = timed(
            result,
            "index_rebuild",
            lambda: rebuild_material_prefix_indexes(day_key, day_key, [customer_center_id]),
        )
        log(
            "index_rebuild_done",
            day=day_key,
            elapsed_seconds=result["timings"]["index_rebuild"],
            ok=result["index_result"].get("ok"),
        )

    with service.db() as conn:
        result["performance_after"] = performance_counts(conn, customer_center_id, day_key)
        result["material_after"] = material_counts(conn, customer_center_id, day_key)
    result["updated"] = True
    result["total_elapsed_seconds"] = round(sum(float(value or 0.0) for value in result["timings"].values()), 2)
    return result


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    result = repair_day(args)
    result["wall_elapsed_seconds"] = round(time.monotonic() - started, 2)
    output = str(args.output or "").strip()
    if not output:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = str(ROOT_DIR / "tools" / f"material_plan_day_repair_{result['day']}_{stamp}.json")
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log("finished", output=output, wall_elapsed_seconds=result["wall_elapsed_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
