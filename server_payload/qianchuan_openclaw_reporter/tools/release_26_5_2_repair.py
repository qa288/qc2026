#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for candidate in (ROOT_DIR, TOOLS_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from dashboard.main import service  # noqa: E402
from tools.material_creative_title_backfill import run as run_creative_title_backfill  # noqa: E402
from tools.material_name_id_backfill import run as run_name_id_backfill  # noqa: E402
from tools.material_plan_day_repair import repair_day as run_material_plan_day_repair  # noqa: E402
from tools.official_daily_align import rebuild_material_prefix_indexes, replace_performance_day  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Release 26.5.2 repair runner: align closed-day account/plan data, "
            "refetch material by plan, align material names/title/video metadata, "
            "and rebuild material day-prefix ranking indexes."
        )
    )
    parser.add_argument("--date", default="2026-05-01", help="Closed day to repair, YYYY-MM-DD.")
    parser.add_argument("--customer-center-id", default="", help="Customer center id. Defaults to config.")
    parser.add_argument("--index-start-date", default="2026-01-01", help="Prefix index start date.")
    parser.add_argument("--workers", type=int, default=8, help="Plan material worker count.")
    parser.add_argument("--requests-per-minute", type=int, default=300, help="Plan material request limit.")
    parser.add_argument("--name-workers", type=int, default=2, help="Video/name id backfill worker count.")
    parser.add_argument("--creative-workers", type=int, default=4, help="Creative detail worker count.")
    parser.add_argument("--skip-performance", action="store_true")
    parser.add_argument("--skip-material", action="store_true")
    parser.add_argument("--skip-name-id", action="store_true")
    parser.add_argument("--skip-creative-title", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument("--allow-performance-errors", action="store_true")
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    return parser.parse_args()


def resolve_customer_center_id(requested: str) -> str:
    requested = str(requested or "").strip()
    if requested:
        return requested
    configured = str(service.read_config().get("customer_center_id") or "").strip()
    if configured:
        return configured
    with service.db() as conn:
        row = conn.execute("SELECT customer_center_id FROM summary_daily ORDER BY biz_date DESC LIMIT 1").fetchone()
    return str((row or {}).get("customer_center_id") or "").strip()


def timed(result: dict[str, Any], key: str, callback: Any) -> Any:
    started = time.monotonic()
    try:
        return callback()
    finally:
        result.setdefault("timings", {})[key] = round(time.monotonic() - started, 2)


def table_totals(customer_center_id: str, day_key: str) -> list[dict[str, Any]]:
    statements = [
        ("summary_daily", "summary_daily"),
        ("account_daily", "account_daily"),
        ("plan_daily", "plan_daily"),
        ("material_relation_daily", "material_relation_daily"),
        ("material_daily", "material_daily"),
    ]
    rows: list[dict[str, Any]] = []
    with service.db() as conn:
        for label, table_name in statements:
            row = dict(
                conn.execute(
                    f"""
                    SELECT
                        ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS stat_cost,
                        ROUND(COALESCE(SUM(pay_amount), 0)::numeric, 2) AS pay_amount,
                        COALESCE(SUM(order_count), 0) AS order_count,
                        COUNT(*) AS rows
                    FROM {table_name}
                    WHERE customer_center_id = ?
                      AND biz_date = ?
                    """,
                    (customer_center_id, day_key),
                ).fetchone()
                or {}
            )
            rows.append(
                {
                    "table_name": label,
                    "stat_cost": round(float(row.get("stat_cost") or 0.0), 2),
                    "pay_amount": round(float(row.get("pay_amount") or 0.0), 2),
                    "order_count": int(row.get("order_count") or 0),
                    "rows": int(row.get("rows") or 0),
                }
            )
    return rows


def plan_material_gap_summary(customer_center_id: str, day_key: str) -> dict[str, Any]:
    with service.db() as conn:
        row = dict(
            conn.execute(
                """
                WITH plan_roll AS (
                    SELECT advertiser_id, ad_id, ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS plan_cost
                    FROM plan_daily
                    WHERE customer_center_id = ?
                      AND biz_date = ?
                      AND ad_id > 0
                    GROUP BY advertiser_id, ad_id
                ),
                rel_roll AS (
                    SELECT advertiser_id, ad_id,
                           ROUND(COALESCE(SUM(CASE WHEN UPPER(COALESCE(material_type, '')) <> 'TITLE' THEN stat_cost ELSE 0 END), 0)::numeric, 2) AS relation_cost
                    FROM material_relation_daily
                    WHERE customer_center_id = ?
                      AND biz_date = ?
                      AND ad_id > 0
                    GROUP BY advertiser_id, ad_id
                ),
                cmp AS (
                    SELECT ROUND((p.plan_cost - COALESCE(r.relation_cost, 0))::numeric, 2) AS gap
                    FROM plan_roll p
                    LEFT JOIN rel_roll r ON r.advertiser_id = p.advertiser_id AND r.ad_id = p.ad_id
                )
                SELECT COUNT(*) AS plan_count,
                       COUNT(*) FILTER (WHERE ABS(gap) >= 1) AS over_1_count,
                       ROUND(COALESCE(MAX(ABS(gap)), 0)::numeric, 2) AS max_abs_gap
                FROM cmp
                """,
                (customer_center_id, day_key, customer_center_id, day_key),
            ).fetchone()
            or {}
        )
    return {
        "plan_count": int(row.get("plan_count") or 0),
        "over_1_count": int(row.get("over_1_count") or 0),
        "max_abs_gap": round(float(row.get("max_abs_gap") or 0.0), 2),
    }


def material_name_summary(customer_center_id: str, day_key: str) -> dict[str, Any]:
    with service.db() as conn:
        relation = dict(
            conn.execute(
                """
                SELECT COUNT(*) AS relation_rows,
                       COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO') AS video_rows,
                       COUNT(*) FILTER (
                           WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO'
                             AND COALESCE(backend_material_name, '') <> ''
                       ) AS video_backend_filled,
                       COUNT(*) FILTER (WHERE COALESCE(publish_title, '') <> '') AS publish_title_filled,
                       COUNT(*) FILTER (WHERE creative_source = 'creative_detail') AS creative_detail_rows
                FROM material_relation_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                """,
                (customer_center_id, day_key),
            ).fetchone()
            or {}
        )
        daily = dict(
            conn.execute(
                """
                SELECT COUNT(*) AS daily_rows,
                       COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO') AS video_rows,
                       COUNT(*) FILTER (
                           WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO'
                             AND COALESCE(backend_material_name, '') <> ''
                       ) AS video_backend_filled,
                       COUNT(*) FILTER (WHERE COALESCE(publish_title, '') <> '') AS publish_title_filled,
                       COUNT(*) FILTER (WHERE creative_source = 'creative_detail') AS creative_detail_rows
                FROM material_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                """,
                (customer_center_id, day_key),
            ).fetchone()
            or {}
        )
    return {
        "relation": {key: int(value or 0) for key, value in relation.items()},
        "daily": {key: int(value or 0) for key, value in daily.items()},
    }


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    service.init_db_once()
    service.bootstrap_token_store()
    service.assert_runtime_client_compatibility()

    day_key = str(args.date).strip()[:10]
    customer_center_id = resolve_customer_center_id(args.customer_center_id)
    if not customer_center_id:
        raise RuntimeError("customer_center_id is required")

    result: dict[str, Any] = {
        "kind": "release_26_5_2_repair",
        "day": day_key,
        "customer_center_id": customer_center_id,
        "index_start_date": str(args.index_start_date).strip()[:10],
        "timings": {},
        "before": {
            "totals": table_totals(customer_center_id, day_key),
            "plan_material_gap": plan_material_gap_summary(customer_center_id, day_key),
            "material_names": material_name_summary(customer_center_id, day_key),
        },
    }

    if args.skip_performance:
        result["performance"] = {"skipped": True}
    else:
        result["performance"] = timed(
            result,
            "performance",
            lambda: replace_performance_day(
                customer_center_id=customer_center_id,
                day_key=day_key,
                dry_run=False,
                allow_errors=bool(args.allow_performance_errors),
            ),
        )

    if args.skip_material:
        result["material_plan_repair"] = {"skipped": True}
    else:
        result["material_plan_repair"] = timed(
            result,
            "material_plan_repair",
            lambda: run_material_plan_day_repair(
                argparse.Namespace(
                    date=day_key,
                    customer_center_id=customer_center_id,
                    plan_scope="all",
                    workers=int(args.workers or 8),
                    requests_per_minute=int(args.requests_per_minute or 300),
                    batch_size=0,
                    batch_sleep_seconds=0.0,
                    skip_title_video_alignment=True,
                    skip_index=True,
                    no_prune=False,
                    dry_run=False,
                    output="",
                )
            ),
        )

    if args.skip_name_id:
        result["name_id_backfill"] = {"skipped": True}
    else:
        result["name_id_backfill"] = timed(
            result,
            "name_id_backfill",
            lambda: run_name_id_backfill(
                argparse.Namespace(
                    date=day_key,
                    customer_center_id=customer_center_id,
                    workers=int(args.name_workers or 2),
                    batch_size=100,
                    timeout=20,
                    attempts=2,
                    skip_profile_cache=False,
                    skip_index=True,
                    dry_run=False,
                    output="",
                )
            ),
        )

    if args.skip_creative_title:
        result["creative_title_backfill"] = {"skipped": True}
    else:
        result["creative_title_backfill"] = timed(
            result,
            "creative_title_backfill",
            lambda: run_creative_title_backfill(
                argparse.Namespace(
                    date=day_key,
                    customer_center_id=customer_center_id,
                    workers=int(args.creative_workers or 4),
                    dry_run=False,
                    output="",
                )
            ),
        )

    if args.skip_index:
        result["index_rebuild"] = {"skipped": True}
    else:
        result["index_rebuild"] = timed(
            result,
            "index_rebuild",
            lambda: rebuild_material_prefix_indexes(
                str(args.index_start_date).strip()[:10],
                day_key,
                [customer_center_id],
            ),
        )

    result["after"] = {
        "totals": table_totals(customer_center_id, day_key),
        "plan_material_gap": plan_material_gap_summary(customer_center_id, day_key),
        "material_names": material_name_summary(customer_center_id, day_key),
    }
    result["wall_elapsed_seconds"] = round(time.monotonic() - started, 2)
    output = str(args.output or "").strip()
    if output:
        Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    over_1_count = int((result["after"].get("plan_material_gap") or {}).get("over_1_count") or 0)
    index_ok = bool((result.get("index_rebuild") or {}).get("ok", True))
    return 0 if over_1_count == 0 and index_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
