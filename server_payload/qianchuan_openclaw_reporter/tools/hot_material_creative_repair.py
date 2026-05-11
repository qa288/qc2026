from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dashboard.main import service  # noqa: E402
from tools.material_creative_title_backfill import run as run_creative_title_backfill  # noqa: E402
from tools.material_name_id_backfill import run as run_name_id_backfill  # noqa: E402
from tools.material_plan_day_repair import repair_day as run_material_plan_day_repair  # noqa: E402
from tools.official_daily_align import iter_days, parse_day, rebuild_material_prefix_indexes, replace_performance_day  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Force current material hot-chain collection, align creative/title/video metadata, "
            "restore current/daily material read models, and rebuild material ranking indexes."
        )
    )
    parser.add_argument("--customer-center-id", action="append", default=[], help="Limit to one or more customer centers.")
    parser.add_argument("--no-full-plan-scan", action="store_true", help="Use normal hot/warm/cold selection instead of all plans.")
    parser.add_argument("--skip-title-video-alignment", action="store_true", help="Skip explicit creative/title/video alignment pass.")
    parser.add_argument("--history-start-date", default="2026-04-30", help="Closed-day repair start date, YYYY-MM-DD.")
    parser.add_argument("--history-end-date", default="2026-05-05", help="Closed-day repair end date, YYYY-MM-DD.")
    parser.add_argument("--skip-history", action="store_true", help="Skip closed-day history repair.")
    parser.add_argument("--history-workers", type=int, default=8, help="Plan material repair workers for closed days.")
    parser.add_argument("--history-requests-per-minute", type=int, default=300, help="Plan material request rate limit.")
    parser.add_argument("--name-workers", type=int, default=2, help="Video/name ID backfill workers.")
    parser.add_argument("--creative-workers", type=int, default=4, help="Creative detail title/video alignment workers.")
    parser.add_argument("--allow-performance-errors", action="store_true", help="Continue if closed-day official performance has API errors.")
    parser.add_argument("--skip-index", action="store_true", help="Skip material ranking index rebuild.")
    parser.add_argument("--output", default="", help="Write JSON result to this path.")
    return parser.parse_args()


def target_customer_centers(args: argparse.Namespace) -> list[str]:
    explicit = [str(item or "").strip() for item in (args.customer_center_id or []) if str(item or "").strip()]
    if explicit:
        return list(dict.fromkeys(explicit))
    bound = [str(item or "").strip() for item in service.bound_customer_center_ids() if str(item or "").strip()]
    if bound:
        return bound
    current = str(service._current_customer_center_id() or "").strip()
    return [current] if current else []


def material_alignment_counts(customer_center_id: str, day_key: str) -> dict[str, Any]:
    with service.db() as conn:
        current = dict(
            conn.execute(
                """
                SELECT
                    ROUND(COALESCE(SUM(stat_cost), 0), 2) AS stat_cost,
                    COUNT(*) AS row_count,
                    COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO') AS video_rows,
                    COUNT(*) FILTER (
                        WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO'
                          AND COALESCE(backend_material_name, '') <> ''
                    ) AS video_backend_rows,
                    COUNT(*) FILTER (WHERE COALESCE(publish_title, '') <> '') AS publish_title_rows,
                    COUNT(*) FILTER (WHERE COALESCE(creative_source, '') = 'creative_detail') AS creative_detail_rows
                FROM material_relation_current
                WHERE customer_center_id = ?
                """,
                (customer_center_id,),
            ).fetchone()
            or {}
        )
        daily_relation = dict(
            conn.execute(
                """
                SELECT
                    ROUND(COALESCE(SUM(stat_cost), 0), 2) AS stat_cost,
                    COUNT(*) AS row_count,
                    COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO') AS video_rows,
                    COUNT(*) FILTER (
                        WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO'
                          AND COALESCE(backend_material_name, '') <> ''
                    ) AS video_backend_rows,
                    COUNT(*) FILTER (WHERE COALESCE(publish_title, '') <> '') AS publish_title_rows,
                    COUNT(*) FILTER (WHERE COALESCE(creative_source, '') = 'creative_detail') AS creative_detail_rows
                FROM material_relation_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                """,
                (customer_center_id, day_key),
            ).fetchone()
            or {}
        )
        daily_material = dict(
            conn.execute(
                """
                SELECT
                    ROUND(COALESCE(SUM(stat_cost), 0), 2) AS stat_cost,
                    COUNT(*) AS row_count,
                    COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO') AS video_rows,
                    COUNT(*) FILTER (
                        WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO'
                          AND COALESCE(backend_material_name, '') <> ''
                    ) AS video_backend_rows,
                    COUNT(*) FILTER (WHERE COALESCE(publish_title, '') <> '') AS publish_title_rows,
                    COUNT(*) FILTER (WHERE COALESCE(creative_source, '') = 'creative_detail') AS creative_detail_rows
                FROM material_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                """,
                (customer_center_id, day_key),
            ).fetchone()
            or {}
        )
        plan = dict(
            conn.execute(
                """
                SELECT ROUND(COALESCE(SUM(stat_cost), 0), 2) AS stat_cost, COUNT(*) AS row_count
                FROM plan_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                """,
                (customer_center_id, day_key),
            ).fetchone()
            or {}
        )
    return {
        "plan_daily": plan,
        "material_relation_current": current,
        "material_relation_daily": daily_relation,
        "material_daily": daily_material,
    }


def plan_material_gap_summary(customer_center_id: str, day_key: str) -> dict[str, Any]:
    with service.db() as conn:
        row = dict(
            conn.execute(
                """
                WITH plan_roll AS (
                    SELECT advertiser_id, ad_id, ROUND(COALESCE(SUM(stat_cost), 0), 2) AS plan_cost
                    FROM plan_daily
                    WHERE customer_center_id = ?
                      AND biz_date = ?
                      AND ad_id > 0
                    GROUP BY advertiser_id, ad_id
                ),
                rel_roll AS (
                    SELECT advertiser_id, ad_id,
                           ROUND(COALESCE(SUM(
                               CASE WHEN UPPER(COALESCE(material_type, '')) <> 'TITLE'
                                    THEN stat_cost ELSE 0 END
                           ), 0), 2) AS relation_cost
                    FROM material_relation_daily
                    WHERE customer_center_id = ?
                      AND biz_date = ?
                      AND ad_id > 0
                    GROUP BY advertiser_id, ad_id
                ),
                cmp AS (
                    SELECT ROUND((p.plan_cost - COALESCE(r.relation_cost, 0)), 2) AS gap
                    FROM plan_roll p
                    LEFT JOIN rel_roll r ON r.advertiser_id = p.advertiser_id AND r.ad_id = p.ad_id
                )
                SELECT COUNT(*) AS plan_count,
                       COUNT(*) FILTER (WHERE ABS(gap) >= 1) AS over_1_count,
                       ROUND(COALESCE(MAX(ABS(gap)), 0), 2) AS max_abs_gap
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


def run_history_day(customer_center_id: str, day_key: str, args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {
        "customer_center_id": customer_center_id,
        "day": day_key,
        "before": {
            "counts": material_alignment_counts(customer_center_id, day_key),
            "plan_material_gap": plan_material_gap_summary(customer_center_id, day_key),
        },
        "performance": {},
        "material_plan_repair": {},
        "name_id_backfill": {},
        "creative_title_backfill": {},
        "after": {},
        "elapsed_seconds": 0.0,
    }
    result["performance"] = replace_performance_day(
        customer_center_id=customer_center_id,
        day_key=day_key,
        dry_run=False,
        allow_errors=bool(args.allow_performance_errors),
    )
    result["material_plan_repair"] = run_material_plan_day_repair(
        argparse.Namespace(
            date=day_key,
            customer_center_id=customer_center_id,
            plan_scope="all",
            workers=int(args.history_workers or 8),
            requests_per_minute=int(args.history_requests_per_minute or 300),
            batch_size=0,
            batch_sleep_seconds=0.0,
            skip_title_video_alignment=True,
            skip_index=True,
            no_prune=False,
            dry_run=False,
            output="",
        )
    )
    result["name_id_backfill"] = run_name_id_backfill(
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
    )
    if args.skip_title_video_alignment:
        result["creative_title_backfill"] = {"skipped": True, "reason": "skip_title_video_alignment"}
    else:
        result["creative_title_backfill"] = run_creative_title_backfill(
            argparse.Namespace(
                date=day_key,
                customer_center_id=customer_center_id,
                workers=int(args.creative_workers or 4),
                dry_run=False,
                output="",
            )
        )
    result["after"] = {
        "counts": material_alignment_counts(customer_center_id, day_key),
        "plan_material_gap": plan_material_gap_summary(customer_center_id, day_key),
    }
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return result


def history_days(args: argparse.Namespace) -> list[str]:
    if args.skip_history:
        return []
    return iter_days(parse_day(str(args.history_start_date).strip()), parse_day(str(args.history_end_date).strip()))


def run_for_customer_center(customer_center_id: str, args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    payload = service.collect_material_snapshot(
        force_refresh=True,
        customer_center_id=customer_center_id,
        full_plan_scan=not bool(args.no_full_plan_scan),
        prefer_library_media_enrichment=True,
        prefer_library_create_time_enrichment=True,
    )
    if not payload.get("skipped"):
        service.persist_material_current(payload)
    snapshot_time = str(payload.get("snapshot_time") or "").strip()
    day_key = snapshot_time[:10]
    result: dict[str, Any] = {
        "customer_center_id": customer_center_id,
        "snapshot_time": snapshot_time,
        "day": day_key,
        "hot_sync": {
            "ok": bool(payload.get("ok", True)),
            "skipped": bool(payload.get("skipped", False)),
            "reason": str(payload.get("reason") or ""),
            "plan_count": int(payload.get("plan_count", 0) or 0),
            "selected_hot_plan_count": int(payload.get("selected_hot_plan_count", 0) or 0),
            "selected_warm_plan_count": int(payload.get("selected_warm_plan_count", 0) or 0),
            "selected_cold_plan_count": int(payload.get("selected_cold_plan_count", 0) or 0),
            "material_row_count": len(payload.get("material_rows") or []),
            "error_count": len(payload.get("errors") or []),
            "errors": list(payload.get("errors") or [])[:20],
        },
        "title_video_alignment": {},
        "history_restore": {},
        "current_restore": {},
        "post_check": {},
        "elapsed_seconds": 0.0,
    }
    if not day_key:
        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
        return result

    if not args.skip_title_video_alignment:
        result["title_video_alignment"] = service.repair_material_title_video_alignment_day(
            customer_center_id,
            day_key,
            fetch_creative=True,
        )

    with service.db() as conn:
        result["history_restore"] = service._restore_material_history_day_from_all_snapshots(
            conn,
            customer_center_id,
            day_key,
        )
        result["current_restore"] = service._restore_material_current_from_all_same_day_snapshots(
            conn,
            customer_center_id,
            day_key,
        )

    result["post_check"] = material_alignment_counts(customer_center_id, day_key)
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return result


def main() -> int:
    args = parse_args()
    service.init_db_once()
    centers = target_customer_centers(args)
    started = time.monotonic()
    result: dict[str, Any] = {
        "ok": True,
        "customer_center_ids": centers,
        "history_start_date": "" if args.skip_history else str(args.history_start_date).strip()[:10],
        "history_end_date": "" if args.skip_history else str(args.history_end_date).strip()[:10],
        "history_results": [],
        "results": [],
        "index_result": {},
        "elapsed_seconds": 0.0,
    }
    days: list[str] = []
    for customer_center_id in centers:
        for day_key in history_days(args):
            history_item = run_history_day(customer_center_id, day_key, args)
            result["history_results"].append(history_item)
            days.append(day_key)
            if int(((history_item.get("after") or {}).get("plan_material_gap") or {}).get("over_1_count") or 0) > 0:
                result["ok"] = False
        item = run_for_customer_center(customer_center_id, args)
        result["results"].append(item)
        day_key = str(item.get("day") or "").strip()
        if day_key:
            days.append(day_key)
        if not bool((item.get("hot_sync") or {}).get("ok", True)):
            result["ok"] = False

    if days and centers and not args.skip_index:
        result["index_result"] = rebuild_material_prefix_indexes(min(days), max(days), centers)

    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    print(text)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    return 0 if bool(result.get("ok", True)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
