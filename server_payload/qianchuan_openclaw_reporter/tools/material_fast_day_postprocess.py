#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dashboard.main import service  # noqa: E402
from tools.official_daily_align import (  # noqa: E402
    add_unattributed_material_residuals,
    material_counts,
    official_plan_ids,
    performance_counts,
    prune_table_to_official_plans,
    rebuild_material_daily_from_relations,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fast material day closeout: prune rows outside plan_daily, add unattributed residuals, rebuild material_daily."
    )
    parser.add_argument("--dates", default="", help="Comma-separated YYYY-MM-DD dates.")
    parser.add_argument("--start-date", default="", help="Start day, YYYY-MM-DD.")
    parser.add_argument("--end-date", default="", help="End day, YYYY-MM-DD.")
    parser.add_argument("--customer-center-id", default="", help="Customer center id.")
    parser.add_argument("--threshold", type=float, default=1.0, help="Report remaining gaps at or above this amount.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect only, no writes.")
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    return parser.parse_args()


def log(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False, sort_keys=True, default=json_default), flush=True)


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def parse_day(value: str) -> date:
    return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()


def iter_days(start_day: date, end_day: date) -> list[str]:
    days: list[str] = []
    current = start_day
    while current <= end_day:
        days.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return days


def requested_days(args: argparse.Namespace) -> list[str]:
    explicit = [item.strip()[:10] for item in str(args.dates or "").split(",") if item.strip()]
    if explicit:
        return sorted({day for day in explicit})
    if args.start_date and args.end_date:
        return iter_days(parse_day(args.start_date), parse_day(args.end_date))
    raise RuntimeError("Either --dates or --start-date/--end-date is required")


def resolve_customer_center_id(requested: str) -> str:
    requested = str(requested or "").strip()
    if requested:
        return requested
    cfg = service.read_config()
    configured = str(cfg.get("customer_center_id") or "").strip()
    if configured:
        return configured
    with service.db() as conn:
        row = conn.execute("SELECT customer_center_id FROM summary_daily ORDER BY biz_date DESC LIMIT 1").fetchone()
    return str((row or {}).get("customer_center_id") or "").strip()


def day_gap(performance: dict[str, Any], material: dict[str, Any]) -> dict[str, float]:
    plan_cost = round(float(performance.get("plan_daily", {}).get("stat_cost") or 0.0), 2)
    relation_cost = round(float(material.get("material_relation_daily", {}).get("stat_cost") or 0.0), 2)
    relation_non_title_cost = round(
        float(material.get("material_relation_daily_non_title", {}).get("stat_cost") or 0.0),
        2,
    )
    daily_cost = round(float(material.get("material_daily", {}).get("stat_cost") or 0.0), 2)
    return {
        "plan_cost": plan_cost,
        "relation_cost": relation_cost,
        "relation_non_title_cost": relation_non_title_cost,
        "material_daily_cost": daily_cost,
        "plan_minus_relation": round(plan_cost - relation_cost, 2),
        "plan_minus_relation_non_title": round(plan_cost - relation_non_title_cost, 2),
        "plan_minus_material_daily": round(plan_cost - daily_cost, 2),
    }


def stale_relation_summary(conn: Any, customer_center_id: str, day_key: str, allowed_ad_ids: list[int]) -> dict[str, Any]:
    if allowed_ad_ids:
        placeholders = ",".join("?" for _ in allowed_ad_ids)
        params: list[Any] = [customer_center_id, day_key, *allowed_ad_ids]
        rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT ad_id,
                       MAX(ad_name) AS ad_name,
                       ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS stat_cost,
                       COUNT(*) AS row_count
                FROM material_relation_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                  AND ad_id NOT IN ({placeholders})
                GROUP BY ad_id
                ORDER BY ABS(COALESCE(SUM(stat_cost), 0)) DESC, ad_id ASC
                LIMIT 20
                """,
                params,
            ).fetchall()
        ]
        aggregate_row = conn.execute(
            f"""
            SELECT COUNT(*) AS row_count,
                   COUNT(DISTINCT ad_id) AS plan_count,
                   ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS stat_cost
            FROM material_relation_daily
            WHERE customer_center_id = ?
              AND biz_date = ?
              AND ad_id NOT IN ({placeholders})
            """,
            params,
        ).fetchone()
    else:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT ad_id,
                       MAX(ad_name) AS ad_name,
                       ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS stat_cost,
                       COUNT(*) AS row_count
                FROM material_relation_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                GROUP BY ad_id
                ORDER BY ABS(COALESCE(SUM(stat_cost), 0)) DESC, ad_id ASC
                LIMIT 20
                """,
                (customer_center_id, day_key),
            ).fetchall()
        ]
        aggregate_row = conn.execute(
            """
            SELECT COUNT(*) AS row_count,
                   COUNT(DISTINCT ad_id) AS plan_count,
                   ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS stat_cost
            FROM material_relation_daily
            WHERE customer_center_id = ?
              AND biz_date = ?
            """,
            (customer_center_id, day_key),
        ).fetchone()
    aggregate = dict(aggregate_row or {})
    return {
        "row_count": int(aggregate.get("row_count") or 0),
        "plan_count": int(aggregate.get("plan_count") or 0),
        "stat_cost": round(float(aggregate.get("stat_cost") or 0.0), 2),
        "samples": rows,
    }


def active_mismatch_summary(conn: Any, customer_center_id: str, day_key: str, threshold: float) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in conn.execute(
            """
            WITH relation_rollup AS (
                SELECT ad_id,
                       ROUND(COALESCE(SUM(CASE WHEN COALESCE(material_type, '') <> 'TITLE' THEN stat_cost ELSE 0 END), 0)::numeric, 2) AS stat_cost,
                       COUNT(*) AS row_count
                FROM material_relation_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                GROUP BY ad_id
            )
            SELECT p.advertiser_id,
                   p.advertiser_name,
                   p.ad_id,
                   p.ad_name,
                   ROUND(COALESCE(p.stat_cost, 0)::numeric, 2) AS plan_cost,
                   ROUND(COALESCE(r.stat_cost, 0)::numeric, 2) AS relation_cost,
                   ROUND((COALESCE(p.stat_cost, 0) - COALESCE(r.stat_cost, 0))::numeric, 2) AS gap,
                   COALESCE(r.row_count, 0) AS relation_row_count
            FROM plan_daily p
            LEFT JOIN relation_rollup r ON r.ad_id = p.ad_id
            WHERE p.customer_center_id = ?
              AND p.biz_date = ?
              AND p.ad_id > 0
              AND ABS(ROUND((COALESCE(p.stat_cost, 0) - COALESCE(r.stat_cost, 0))::numeric, 2)) >= ?
            ORDER BY ABS(COALESCE(p.stat_cost, 0) - COALESCE(r.stat_cost, 0)) DESC, p.ad_id ASC
            LIMIT 50
            """,
            (customer_center_id, day_key, customer_center_id, day_key, float(threshold)),
        ).fetchall()
    ]
    return {"count": len(rows), "samples": rows[:20]}


def process_day(customer_center_id: str, day_key: str, *, threshold: float, dry_run: bool) -> dict[str, Any]:
    started = time.monotonic()
    with service.db() as conn:
        before_performance = performance_counts(conn, customer_center_id, day_key)
        before_material = material_counts(conn, customer_center_id, day_key)
        allowed_ad_ids = official_plan_ids(conn, customer_center_id, day_key)
        stale_before = stale_relation_summary(conn, customer_center_id, day_key, allowed_ad_ids)

    result: dict[str, Any] = {
        "day": day_key,
        "updated": False,
        "allowed_plan_count": len(allowed_ad_ids),
        "before": {
            "performance": before_performance,
            "material": before_material,
            "gap": day_gap(before_performance, before_material),
            "stale_relation": stale_before,
        },
        "actions": {},
    }
    log("day_start", day=day_key, **result["before"]["gap"], stale_relation_cost=stale_before["stat_cost"])

    if dry_run:
        result["after"] = result["before"]
        result["remaining_mismatches"] = {"skipped": True}
        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
        return result

    with service.db() as conn:
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
        after_performance = performance_counts(conn, customer_center_id, day_key)
        after_material = material_counts(conn, customer_center_id, day_key)
        active_mismatches = active_mismatch_summary(conn, customer_center_id, day_key, threshold)

    result["actions"] = {
        "pruned_relation_rows": pruned_relation_rows,
        "pruned_snapshot_rows": pruned_snapshot_rows,
        "unattributed_residual": residual,
        "rebuilt_material_daily_rows": rebuilt_rows,
    }
    result["after"] = {
        "performance": after_performance,
        "material": after_material,
        "gap": day_gap(after_performance, after_material),
    }
    result["remaining_mismatches"] = active_mismatches
    result["updated"] = True
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    log(
        "day_done",
        day=day_key,
        elapsed_seconds=result["elapsed_seconds"],
        pruned_relation_rows=pruned_relation_rows,
        residual_cost=residual.get("stat_cost"),
        **result["after"]["gap"],
        remaining_mismatch_count=active_mismatches["count"],
    )
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    service.init_db_once()
    customer_center_id = resolve_customer_center_id(args.customer_center_id)
    if not customer_center_id:
        raise RuntimeError("customer_center_id is required")
    days = requested_days(args)
    result: dict[str, Any] = {
        "kind": "material_fast_day_postprocess",
        "customer_center_id": customer_center_id,
        "dry_run": bool(args.dry_run),
        "threshold": float(args.threshold),
        "day_count": len(days),
        "days": [],
    }
    started = time.monotonic()
    for day_key in days:
        result["days"].append(
            process_day(customer_center_id, day_key, threshold=float(args.threshold), dry_run=bool(args.dry_run))
        )
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    result["remaining_gap_days"] = [
        {
            "day": item["day"],
            **item.get("after", {}).get("gap", {}),
            "remaining_mismatch_count": item.get("remaining_mismatches", {}).get("count", 0),
        }
        for item in result["days"]
        if any(
            abs(float(item.get("after", {}).get("gap", {}).get(key) or 0.0)) >= float(args.threshold)
            for key in ("plan_minus_relation", "plan_minus_material_daily")
        )
        or int(item.get("remaining_mismatches", {}).get("count") or 0) > 0
    ]
    return result


def main() -> int:
    args = parse_args()
    result = run(args)
    output = str(args.output or "").strip()
    if not output:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = str(ROOT_DIR / "tools" / f"material_fast_day_postprocess_{stamp}.json")
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    log(
        "finished",
        output=output,
        elapsed_seconds=result["elapsed_seconds"],
        day_count=result["day_count"],
        remaining_gap_days=len(result["remaining_gap_days"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
