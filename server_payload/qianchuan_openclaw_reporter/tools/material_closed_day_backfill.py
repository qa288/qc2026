#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dashboard.main import material_ranking_index, now_text, service  # noqa: E402
from tools.material_name_id_backfill import run as run_material_name_id_backfill  # noqa: E402
from tools.official_daily_align import rebuild_material_daily_from_relations  # noqa: E402


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
        raise ValueError("end_date must be >= start_date")
    days: list[str] = []
    current = start_day
    while current <= end_day:
        days.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return days


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill closed-day material history from official full snapshots, align creative "
            "title/video metadata, force backend material names, and rebuild material indexes. "
            "This intentionally does not insert unattributed residual rows."
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
    parser.add_argument("--workers", type=int, default=1, help="Official full snapshot worker count.")
    parser.add_argument("--requests-per-minute", type=int, default=30, help="Plan-material request rate.")
    parser.add_argument("--batch-size", type=int, default=1, help="Plan-material batch size.")
    parser.add_argument("--batch-sleep-seconds", type=float, default=3.0, help="Sleep between batches.")
    parser.add_argument("--backend-workers", type=int, default=4, help="Backend material name lookup workers.")
    parser.add_argument("--backend-batch-size", type=int, default=100, help="Backend name lookup batch size.")
    parser.add_argument("--skip-backend-name", action="store_true", help="Skip backend material name API lookup.")
    parser.add_argument("--skip-index", action="store_true", help="Skip material ranking index rebuild.")
    parser.add_argument("--dry-run", action="store_true", help="Report intended work without writing.")
    parser.add_argument("--output", default="", help="Optional JSON output path.")
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


def count_state(customer_center_id: str, day_key: str) -> dict[str, Any]:
    with service.db() as conn:
        plan = dict(
            conn.execute(
                """
                SELECT COUNT(*) AS row_count,
                       ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS stat_cost
                FROM plan_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                """,
                (customer_center_id, day_key),
            ).fetchone()
            or {}
        )
        relation = dict(
            conn.execute(
                """
                SELECT COUNT(*) AS row_count,
                       COUNT(DISTINCT material_key) AS material_key_count,
                       ROUND(COALESCE(SUM(CASE WHEN UPPER(COALESCE(material_type, '')) <> 'TITLE' THEN stat_cost ELSE 0 END), 0)::numeric, 2) AS non_title_cost,
                       COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'TITLE'
                                          AND (COALESCE(stat_cost, 0) <> 0 OR COALESCE(pay_amount, 0) <> 0 OR COALESCE(order_count, 0) <> 0)) AS title_positive_rows,
                       COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO') AS video_rows,
                       COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO'
                                          AND COALESCE(backend_material_name, '') <> '') AS video_backend_rows,
                       COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO'
                                          AND COALESCE(backend_material_name, '') <> ''
                                          AND COALESCE(material_name, '') <> COALESCE(backend_material_name, '')) AS video_name_not_backend_rows,
                       COUNT(*) FILTER (WHERE COALESCE(creative_source, '') = 'creative_detail') AS creative_detail_rows,
                       COUNT(*) FILTER (WHERE COALESCE(publish_title, '') <> '') AS publish_title_rows
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
                SELECT COUNT(*) AS row_count,
                       ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS stat_cost,
                       COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO'
                                          AND COALESCE(backend_material_name, '') <> ''
                                          AND COALESCE(material_name, '') <> COALESCE(backend_material_name, '')) AS video_name_not_backend_rows
                FROM material_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                """,
                (customer_center_id, day_key),
            ).fetchone()
            or {}
        )
        snapshot = dict(
            conn.execute(
                """
                SELECT COUNT(*) AS row_count,
                       COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO'
                                          AND COALESCE(backend_material_name, '') <> ''
                                          AND COALESCE(material_name, '') <> COALESCE(backend_material_name, '')) AS video_name_not_backend_rows
                FROM material_snapshots
                WHERE customer_center_id = ?
                  AND substr(snapshot_time, 1, 10) = ?
                """,
                (customer_center_id, day_key),
            ).fetchone()
            or {}
        )
    return {
        "customer_center_id": customer_center_id,
        "day": day_key,
        "plan_rows": int(plan.get("row_count") or 0),
        "plan_cost": money(plan.get("stat_cost")),
        "relation_rows": int(relation.get("row_count") or 0),
        "relation_material_keys": int(relation.get("material_key_count") or 0),
        "relation_non_title_cost": money(relation.get("non_title_cost")),
        "title_positive_rows": int(relation.get("title_positive_rows") or 0),
        "video_rows": int(relation.get("video_rows") or 0),
        "video_backend_rows": int(relation.get("video_backend_rows") or 0),
        "relation_video_name_not_backend_rows": int(relation.get("video_name_not_backend_rows") or 0),
        "creative_detail_rows": int(relation.get("creative_detail_rows") or 0),
        "publish_title_rows": int(relation.get("publish_title_rows") or 0),
        "material_daily_rows": int(daily.get("row_count") or 0),
        "material_daily_cost": money(daily.get("stat_cost")),
        "daily_video_name_not_backend_rows": int(daily.get("video_name_not_backend_rows") or 0),
        "snapshot_rows": int(snapshot.get("row_count") or 0),
        "snapshot_video_name_not_backend_rows": int(snapshot.get("video_name_not_backend_rows") or 0),
    }


def enforce_backend_material_names(customer_center_id: str, day_key: str) -> dict[str, int]:
    updated_at = now_text()
    with service.db() as conn:
        relation_cursor = conn.execute(
            """
            UPDATE material_relation_daily
            SET material_name = backend_material_name
            WHERE customer_center_id = ?
              AND biz_date = ?
              AND UPPER(COALESCE(material_type, '')) = 'VIDEO'
              AND COALESCE(backend_material_name, '') <> ''
              AND COALESCE(material_name, '') <> COALESCE(backend_material_name, '')
            """,
            (customer_center_id, day_key),
        )
        snapshot_cursor = conn.execute(
            """
            UPDATE material_snapshots
            SET material_name = backend_material_name
            WHERE customer_center_id = ?
              AND substr(snapshot_time, 1, 10) = ?
              AND UPPER(COALESCE(material_type, '')) = 'VIDEO'
              AND COALESCE(backend_material_name, '') <> ''
              AND COALESCE(material_name, '') <> COALESCE(backend_material_name, '')
            """,
            (customer_center_id, day_key),
        )
        daily_cursor = conn.execute(
            """
            UPDATE material_daily
            SET material_name = backend_material_name
            WHERE customer_center_id = ?
              AND biz_date = ?
              AND UPPER(COALESCE(material_type, '')) = 'VIDEO'
              AND COALESCE(backend_material_name, '') <> ''
              AND COALESCE(material_name, '') <> COALESCE(backend_material_name, '')
            """,
            (customer_center_id, day_key),
        )
        rollup_cursor = conn.execute(
            """
            UPDATE material_rollups
            SET material_name = backend_material_name
            WHERE customer_center_id = ?
              AND substr(snapshot_time, 1, 10) = ?
              AND UPPER(COALESCE(material_type, '')) = 'VIDEO'
              AND COALESCE(backend_material_name, '') <> ''
              AND COALESCE(material_name, '') <> COALESCE(backend_material_name, '')
            """,
            (customer_center_id, day_key),
        )
        profile_cursor = conn.execute(
            """
            UPDATE material_profile
            SET material_name = backend_material_name,
                updated_at = ?
            WHERE customer_center_id = ?
              AND UPPER(COALESCE(material_type, '')) = 'VIDEO'
              AND COALESCE(backend_material_name, '') <> ''
              AND COALESCE(material_name, '') <> COALESCE(backend_material_name, '')
            """,
            (updated_at, customer_center_id),
        )
    return {
        "relation_rows": int(getattr(relation_cursor, "rowcount", 0) or 0),
        "snapshot_rows": int(getattr(snapshot_cursor, "rowcount", 0) or 0),
        "daily_rows": int(getattr(daily_cursor, "rowcount", 0) or 0),
        "rollup_rows": int(getattr(rollup_cursor, "rowcount", 0) or 0),
        "profile_rows": int(getattr(profile_cursor, "rowcount", 0) or 0),
    }


def rebuild_indexes(start_date: str, end_date: str, customer_center_ids: list[str]) -> dict[str, Any]:
    days = iter_days(start_date, end_date)
    if not days:
        return {"ok": True, "skipped": True}
    prefix_end_day = service._material_history_index_refresh_end_day(days)
    results: list[dict[str, Any]] = []
    for customer_center_id in customer_center_ids:
        results.append(
            material_ranking_index.rebuild_day_prefix_range(
                service,
                start_day=days[0],
                end_day=prefix_end_day,
                all_customer_centers=False,
                force_scope_key=customer_center_id,
                force_customer_center_id=customer_center_id,
            )
        )
    results.append(
        material_ranking_index.rebuild_day_prefix_range(
            service,
            start_day=days[0],
            end_day=prefix_end_day,
            all_customer_centers=True,
            force_scope_key=material_ranking_index.SCOPE_ALL,
        )
    )
    service.clear_material_runtime_caches(scope="all")
    return {
        "ok": all(bool(item.get("ok")) for item in results),
        "start_day": days[0],
        "end_day": prefix_end_day,
        "results": results,
    }


def timed(result: dict[str, Any], key: str, func: Any) -> Any:
    started = time.monotonic()
    try:
        return func()
    finally:
        result.setdefault("timings", {})[key] = round(time.monotonic() - started, 2)


def run(args: argparse.Namespace) -> dict[str, Any]:
    service.init_db_once()
    service.bootstrap_token_store()
    service.assert_runtime_client_compatibility()

    days = iter_days(args.start_date, args.end_date)
    customer_center_ids = resolve_customer_center_ids(args.customer_center_id)
    targets = [
        {"customer_center_id": customer_center_id, "target_date": day_key}
        for customer_center_id in customer_center_ids
        for day_key in days
    ]
    result: dict[str, Any] = {
        "start_date": days[0] if days else "",
        "end_date": days[-1] if days else "",
        "customer_center_ids": customer_center_ids,
        "dry_run": bool(args.dry_run),
        "timings": {},
        "before": [count_state(target["customer_center_id"], target["target_date"]) for target in targets],
    }
    if args.dry_run:
        result["history_result"] = {"skipped": True, "reason": "dry_run"}
        result["after"] = result["before"]
        return result

    log("official_full_snapshot_start", target_count=len(targets), days=days)
    result["history_result"] = timed(
        result,
        "official_full_snapshot",
        lambda: service.refresh_extended_history_targets(
            targets,
            material_collection_mode="full_snapshot",
            force_replace=True,
            workers_override=max(int(args.workers or 1), 1),
            plan_material_requests_per_minute_override=max(int(args.requests_per_minute or 0), 0),
            plan_material_batch_size_override=max(int(args.batch_size or 0), 0),
            plan_material_batch_sleep_seconds_override=max(float(args.batch_sleep_seconds or 0.0), 0.0),
        ),
    )
    log(
        "official_full_snapshot_done",
        elapsed_seconds=result["timings"]["official_full_snapshot"],
        refreshed_days=result["history_result"].get("refreshed_days"),
        error_count=result["history_result"].get("error_count"),
    )

    day_results: list[dict[str, Any]] = []
    for target in targets:
        customer_center_id = target["customer_center_id"]
        day_key = target["target_date"]
        day_result: dict[str, Any] = {
            "customer_center_id": customer_center_id,
            "day": day_key,
            "timings": {},
        }
        log("title_video_alignment_start", customer_center_id=customer_center_id, day=day_key)
        day_result["title_video_alignment"] = timed(
            day_result,
            "title_video_alignment",
            lambda cc=customer_center_id, day=day_key: service.repair_material_title_video_alignment_day(
                cc,
                day,
                fetch_creative=True,
                dry_run=False,
            ),
        )
        log(
            "title_video_alignment_done",
            customer_center_id=customer_center_id,
            day=day_key,
            elapsed_seconds=day_result["timings"]["title_video_alignment"],
            error_count=day_result["title_video_alignment"].get("error_count"),
        )
        if args.skip_backend_name:
            day_result["backend_name_backfill"] = {"skipped": True}
        else:
            log("backend_name_backfill_start", customer_center_id=customer_center_id, day=day_key)
            day_result["backend_name_backfill"] = timed(
                day_result,
                "backend_name_backfill",
                lambda cc=customer_center_id, day=day_key: run_material_name_id_backfill(
                    argparse.Namespace(
                        date=day,
                        customer_center_id=cc,
                        workers=max(int(args.backend_workers or 1), 1),
                        batch_size=max(int(args.backend_batch_size or 1), 1),
                        timeout=20,
                        attempts=2,
                        skip_profile_cache=False,
                        skip_index=True,
                        dry_run=False,
                        output="",
                    )
                ),
            )
            log(
                "backend_name_backfill_done",
                customer_center_id=customer_center_id,
                day=day_key,
                elapsed_seconds=day_result["timings"]["backend_name_backfill"],
                selected_material_id_count=day_result["backend_name_backfill"].get("selected_material_id_count"),
            )
        day_result["enforce_backend_names_before_rebuild"] = timed(
            day_result,
            "enforce_backend_names_before_rebuild",
            lambda cc=customer_center_id, day=day_key: enforce_backend_material_names(cc, day),
        )
        with service.db() as conn:
            day_result["rebuilt_material_daily_rows"] = timed(
                day_result,
                "rebuild_material_daily",
                lambda cc=customer_center_id, day=day_key: rebuild_material_daily_from_relations(conn, cc, day),
            )
        day_result["enforce_backend_names_after_rebuild"] = timed(
            day_result,
            "enforce_backend_names_after_rebuild",
            lambda cc=customer_center_id, day=day_key: enforce_backend_material_names(cc, day),
        )
        day_result["after"] = count_state(customer_center_id, day_key)
        day_results.append(day_result)

    result["days"] = day_results
    if args.skip_index:
        result["index_result"] = {"skipped": True}
    else:
        log("index_rebuild_start", start_date=days[0], end_date=days[-1], customer_center_count=len(customer_center_ids))
        result["index_result"] = timed(
            result,
            "index_rebuild",
            lambda: rebuild_indexes(days[0], days[-1], customer_center_ids),
        )
        log("index_rebuild_done", elapsed_seconds=result["timings"]["index_rebuild"], ok=result["index_result"].get("ok"))
    result["after"] = [count_state(target["customer_center_id"], target["target_date"]) for target in targets]
    result["total_elapsed_seconds"] = round(
        sum(float(value or 0.0) for value in result["timings"].values())
        + sum(sum(float(value or 0.0) for value in item.get("timings", {}).values()) for item in day_results),
        2,
    )
    return result


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    result = run(args)
    result["wall_elapsed_seconds"] = round(time.monotonic() - started, 2)
    output = str(args.output or "").strip()
    if not output:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = str(ROOT_DIR / "tools" / f"material_closed_day_backfill_{result['start_date']}_{result['end_date']}_{stamp}.json")
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log("finished", output=output, wall_elapsed_seconds=result["wall_elapsed_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
