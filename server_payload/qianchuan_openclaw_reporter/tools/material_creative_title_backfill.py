#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dashboard.main import now_text, service  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill publish title / title material ids from creative detail for one material day. "
            "This intentionally does not call the video library API; run material_name_id_backfill first."
        )
    )
    parser.add_argument("--date", required=True, help="Target day, YYYY-MM-DD.")
    parser.add_argument("--customer-center-id", default="", help="Customer center id.")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent creative detail workers.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and compute changes without writing.")
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    return parser.parse_args()


def log(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False, sort_keys=True), flush=True)


def resolve_customer_center_id(requested: str) -> str:
    requested = str(requested or "").strip()
    if requested:
        return requested
    config = service.read_config()
    configured = str(config.get("customer_center_id") or "").strip()
    if configured:
        return configured
    with service.db() as conn:
        row = conn.execute("SELECT customer_center_id FROM summary_daily ORDER BY biz_date DESC LIMIT 1").fetchone()
    return str((row or {}).get("customer_center_id") or "").strip()


def split_titles(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split(" / ") if item.strip()]


def unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def join_titles(values: list[Any], *, limit: int = 3) -> str:
    return " / ".join(unique(values)[:limit])


def json_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return unique(value)
    text = str(value or "").strip()
    if not text:
        return []
    try:
        loaded = json.loads(text)
    except Exception:
        return []
    if isinstance(loaded, list):
        return unique(loaded)
    return []


def first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def selected_plan_pairs(customer_center_id: str, day_key: str) -> list[tuple[int, int]]:
    with service.db() as conn:
        rows = conn.execute(
            """
            SELECT advertiser_id, ad_id
            FROM material_relation_daily
            WHERE customer_center_id = ?
              AND biz_date = ?
              AND advertiser_id > 0
              AND ad_id > 0
            GROUP BY advertiser_id, ad_id
            ORDER BY advertiser_id, ad_id
            """,
            (customer_center_id, day_key),
        ).fetchall()
    return [(int(row["advertiser_id"] or 0), int(row["ad_id"] or 0)) for row in rows]


def fetch_creative_contexts(
    *,
    customer_center_id: str,
    plan_pairs: list[tuple[int, int]],
    workers: int,
) -> dict[str, Any]:
    client = service._build_scoped_customer_center_client(customer_center_id)
    creative_by_plan: dict[tuple[int, int], dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []

    def fetch_one(pair: tuple[int, int]) -> tuple[tuple[int, int], dict[str, Any] | None, dict[str, Any] | None]:
        advertiser_id, ad_id = pair
        try:
            detail_response = client.get_plan_detail(advertiser_id, ad_id)
            detail_data = detail_response.get("data") or {}
            if not isinstance(detail_data, dict) or not detail_data:
                return pair, {}, None
            return pair, service._creative_title_video_context({"raw_json": service._json_text(detail_data)}), None
        except Exception as exc:  # noqa: BLE001
            return pair, None, {
                "advertiser_id": advertiser_id,
                "ad_id": ad_id,
                "error": str(exc),
            }

    with ThreadPoolExecutor(max_workers=max(int(workers or 1), 1)) as pool:
        future_map = {pool.submit(fetch_one, pair): pair for pair in plan_pairs}
        for future in as_completed(future_map):
            pair, context, error = future.result()
            if error:
                errors.append(error)
                continue
            creative_by_plan[pair] = dict(context or {})

    return {
        "creative_by_plan": creative_by_plan,
        "creative_plan_count": len(creative_by_plan),
        "error_count": len(errors),
        "errors": errors[:50],
    }


def load_rows(customer_center_id: str, day_key: str, *, table: str, snapshot: bool = False) -> list[dict[str, Any]]:
    day_predicate = "substr(snapshot_time, 1, 10) = ?" if snapshot else "biz_date = ?"
    with service.db() as conn:
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT advertiser_id, ad_id, material_type, material_key, material_id, material_name,
                       video_id, backend_material_name, publish_title,
                       creative_title_material_ids_json, creative_source, stat_cost
                FROM {table}
                WHERE customer_center_id = ?
                  AND {day_predicate}
                ORDER BY stat_cost DESC, material_key ASC
                """,
                (customer_center_id, day_key),
            ).fetchall()
        ]


def alignment_for_row(row: dict[str, Any], creative_by_plan: dict[tuple[int, int], dict[str, Any]]) -> dict[str, str]:
    advertiser_id = int(row.get("advertiser_id") or 0)
    ad_id = int(row.get("ad_id") or 0)
    material_type = str(row.get("material_type") or "").strip().upper()
    material_name = str(row.get("material_name") or "").strip()
    backend_existing = str(row.get("backend_material_name") or "").strip()
    publish_existing = split_titles(row.get("publish_title"))
    title_ids_existing = json_text_list(row.get("creative_title_material_ids_json"))
    creative_source_existing = str(row.get("creative_source") or "").strip()
    material_id = str(row.get("material_id") or "").strip()
    numeric_material_id = service._numeric_material_id_text(material_id)
    video_id = str(row.get("video_id") or "").strip()
    creative_context = creative_by_plan.get((advertiser_id, ad_id), {})
    plan_titles = json_text_list(creative_context.get("publish_titles"))
    plan_title_ids = json_text_list(creative_context.get("title_material_ids"))
    videos_by_video_id = dict(creative_context.get("videos_by_video_id") or {})
    videos_by_material_id = dict(creative_context.get("videos_by_material_id") or {})
    video_context = {}
    if material_type == "VIDEO":
        video_context = (
            dict(videos_by_video_id.get(video_id) or {})
            or dict(videos_by_material_id.get(material_id) or {})
            or dict(videos_by_material_id.get(numeric_material_id) or {})
        )

    publish_titles = publish_existing
    title_ids = title_ids_existing
    backend_name = backend_existing
    display_name = material_name
    creative_source = creative_source_existing

    if material_type == "VIDEO":
        video_titles = json_text_list(video_context.get("publish_titles"))
        video_title_ids = json_text_list(video_context.get("title_material_ids"))
        publish_titles = unique(video_titles or plan_titles or publish_existing)
        title_ids = unique(video_title_ids or plan_title_ids or title_ids_existing)
        backend_name = first_text(
            video_context.get("backend_material_name"),
            backend_existing,
            "" if service._looks_like_publish_caption(material_name) else material_name,
        )
        display_name = backend_name or ("" if service._looks_like_publish_caption(material_name) else material_name)
        if video_context or plan_titles or plan_title_ids:
            creative_source = "creative_detail"
    elif material_type == "TITLE":
        publish_titles = unique([material_name, *plan_titles, *publish_existing])
        title_ids = unique(plan_title_ids or title_ids_existing)
        if plan_titles or plan_title_ids:
            creative_source = "creative_detail"
    elif material_type == "UNATTRIBUTED_DELETED":
        display_name = material_name
    elif creative_context:
        publish_titles = unique(plan_titles or publish_existing)
        title_ids = unique(plan_title_ids or title_ids_existing)
        if plan_titles or plan_title_ids:
            creative_source = "creative_detail"

    return {
        "backend_material_name": backend_name,
        "publish_title": join_titles(publish_titles),
        "creative_title_material_ids_json": json.dumps(unique(title_ids), ensure_ascii=False),
        "creative_source": creative_source,
        "material_name": display_name,
    }


def build_updates(
    rows: list[dict[str, Any]],
    creative_by_plan: dict[tuple[int, int], dict[str, Any]],
) -> tuple[list[tuple[Any, ...]], dict[str, dict[str, Any]], dict[str, int]]:
    updates: list[tuple[Any, ...]] = []
    material_meta: dict[str, dict[str, Any]] = {}
    counts = {
        "row_count": len(rows),
        "backend_name_row_count": 0,
        "publish_title_row_count": 0,
        "creative_source_row_count": 0,
        "changed_row_count": 0,
    }
    for row in rows:
        alignment = alignment_for_row(row, creative_by_plan)
        if alignment["backend_material_name"]:
            counts["backend_name_row_count"] += 1
        if alignment["publish_title"]:
            counts["publish_title_row_count"] += 1
        if alignment["creative_source"] == "creative_detail":
            counts["creative_source_row_count"] += 1
        changed = any(
            str(row.get(key) or "").strip() != str(alignment.get(key) or "").strip()
            for key in (
                "backend_material_name",
                "publish_title",
                "creative_title_material_ids_json",
                "creative_source",
                "material_name",
            )
        )
        if changed:
            counts["changed_row_count"] += 1
        updates.append(
            (
                alignment["backend_material_name"],
                alignment["publish_title"],
                alignment["creative_title_material_ids_json"],
                alignment["creative_source"],
                alignment["material_name"],
                int(row.get("advertiser_id") or 0),
                int(row.get("ad_id") or 0),
                str(row.get("material_type") or "").strip(),
                str(row.get("material_key") or "").strip(),
            )
        )
        material_key = str(row.get("material_key") or "").strip()
        if not material_key:
            continue
        bucket = material_meta.setdefault(
            material_key,
            {
                "material_key": material_key,
                "material_id": str(row.get("material_id") or "").strip(),
                "material_type": str(row.get("material_type") or "").strip().upper(),
                "video_id": str(row.get("video_id") or "").strip(),
                "backend_costs": {},
                "publish_titles": [],
                "title_ids": [],
                "fallback_material_name": str(row.get("material_name") or "").strip(),
            },
        )
        if not bucket.get("material_id"):
            bucket["material_id"] = str(row.get("material_id") or "").strip()
        if not bucket.get("video_id"):
            bucket["video_id"] = str(row.get("video_id") or "").strip()
        if alignment["backend_material_name"]:
            backend_costs = bucket["backend_costs"]
            backend_costs[alignment["backend_material_name"]] = round(
                float(backend_costs.get(alignment["backend_material_name"], 0.0) or 0.0)
                + float(row.get("stat_cost") or 0.0),
                4,
            )
        for title in split_titles(alignment["publish_title"]):
            if title and title not in bucket["publish_titles"]:
                bucket["publish_titles"].append(title)
        for title_id in json_text_list(alignment["creative_title_material_ids_json"]):
            if title_id and title_id not in bucket["title_ids"]:
                bucket["title_ids"].append(title_id)
    return updates, material_meta, counts


def rollup_updates_from_meta(material_meta: dict[str, dict[str, Any]]) -> list[tuple[Any, ...]]:
    rollups: list[tuple[Any, ...]] = []
    for material_key, bucket in material_meta.items():
        backend_costs = dict(bucket.get("backend_costs") or {})
        backend_name = ""
        if backend_costs:
            backend_name = sorted(backend_costs.items(), key=lambda item: (-float(item[1] or 0.0), item[0]))[0][0]
        material_type = str(bucket.get("material_type") or "").strip().upper()
        fallback = str(bucket.get("fallback_material_name") or "").strip()
        display_name = backend_name or ("" if service._looks_like_publish_caption(fallback) else fallback)
        publish_title = join_titles(list(bucket.get("publish_titles") or []))
        title_ids_json = json.dumps(unique(list(bucket.get("title_ids") or [])), ensure_ascii=False)
        creative_source = "creative_detail" if publish_title or title_ids_json != "[]" else ""
        rollups.append(
            (
                backend_name,
                publish_title,
                title_ids_json,
                creative_source,
                display_name,
                str(bucket.get("material_id") or "").strip(),
                material_type,
                str(bucket.get("video_id") or "").strip(),
                material_key,
            )
        )
    return rollups


def apply_updates(
    *,
    customer_center_id: str,
    day_key: str,
    relation_updates: list[tuple[Any, ...]],
    snapshot_updates: list[tuple[Any, ...]],
    rollup_updates: list[tuple[Any, ...]],
) -> dict[str, int]:
    updated_at = now_text()
    with service.db() as conn:
        if relation_updates:
            conn.executemany(
                """
                UPDATE material_relation_daily
                SET backend_material_name = ?,
                    publish_title = ?,
                    creative_title_material_ids_json = ?,
                    creative_source = ?,
                    material_name = ?
                WHERE customer_center_id = ?
                  AND biz_date = ?
                  AND advertiser_id = ?
                  AND ad_id = ?
                  AND material_type = ?
                  AND material_key = ?
                """,
                [
                    (
                        backend_name,
                        publish_title,
                        title_ids_json,
                        creative_source,
                        material_name,
                        customer_center_id,
                        day_key,
                        advertiser_id,
                        ad_id,
                        material_type,
                        material_key,
                    )
                    for (
                        backend_name,
                        publish_title,
                        title_ids_json,
                        creative_source,
                        material_name,
                        advertiser_id,
                        ad_id,
                        material_type,
                        material_key,
                    ) in relation_updates
                ],
            )
        if snapshot_updates:
            conn.executemany(
                """
                UPDATE material_snapshots
                SET backend_material_name = ?,
                    publish_title = ?,
                    creative_title_material_ids_json = ?,
                    creative_source = ?,
                    material_name = ?
                WHERE customer_center_id = ?
                  AND substr(snapshot_time, 1, 10) = ?
                  AND advertiser_id = ?
                  AND ad_id = ?
                  AND material_type = ?
                  AND material_key = ?
                """,
                [
                    (
                        backend_name,
                        publish_title,
                        title_ids_json,
                        creative_source,
                        material_name,
                        customer_center_id,
                        day_key,
                        advertiser_id,
                        ad_id,
                        material_type,
                        material_key,
                    )
                    for (
                        backend_name,
                        publish_title,
                        title_ids_json,
                        creative_source,
                        material_name,
                        advertiser_id,
                        ad_id,
                        material_type,
                        material_key,
                    ) in snapshot_updates
                ],
            )
        if rollup_updates:
            conn.executemany(
                """
                UPDATE material_daily
                SET backend_material_name = ?,
                    publish_title = ?,
                    creative_title_material_ids_json = ?,
                    creative_source = ?,
                    material_name = ?
                WHERE customer_center_id = ?
                  AND biz_date = ?
                  AND material_key = ?
                """,
                [
                    (
                        backend_name,
                        publish_title,
                        title_ids_json,
                        creative_source,
                        material_name,
                        customer_center_id,
                        day_key,
                        material_key,
                    )
                    for (
                        backend_name,
                        publish_title,
                        title_ids_json,
                        creative_source,
                        material_name,
                        _material_id,
                        _material_type,
                        _video_id,
                        material_key,
                    ) in rollup_updates
                ],
            )
            conn.executemany(
                """
                UPDATE material_rollups
                SET backend_material_name = ?,
                    publish_title = ?,
                    creative_title_material_ids_json = ?,
                    creative_source = ?,
                    material_name = ?
                WHERE customer_center_id = ?
                  AND substr(snapshot_time, 1, 10) = ?
                  AND material_key = ?
                """,
                [
                    (
                        backend_name,
                        publish_title,
                        title_ids_json,
                        creative_source,
                        material_name,
                        customer_center_id,
                        day_key,
                        material_key,
                    )
                    for (
                        backend_name,
                        publish_title,
                        title_ids_json,
                        creative_source,
                        material_name,
                        _material_id,
                        _material_type,
                        _video_id,
                        material_key,
                    ) in rollup_updates
                ],
            )
            conn.executemany(
                """
                INSERT INTO material_profile (
                    customer_center_id, material_key, material_id, material_name, material_type,
                    video_id, updated_at, backend_material_name, publish_title,
                    creative_title_material_ids_json, creative_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (customer_center_id, material_key) DO UPDATE SET
                    material_id = COALESCE(NULLIF(excluded.material_id, ''), material_profile.material_id),
                    material_name = COALESCE(NULLIF(excluded.material_name, ''), material_profile.material_name),
                    material_type = COALESCE(NULLIF(excluded.material_type, ''), material_profile.material_type),
                    video_id = COALESCE(NULLIF(excluded.video_id, ''), material_profile.video_id),
                    updated_at = excluded.updated_at,
                    backend_material_name = CASE
                        WHEN COALESCE(excluded.backend_material_name, '') <> '' THEN excluded.backend_material_name
                        ELSE material_profile.backend_material_name
                    END,
                    publish_title = CASE
                        WHEN COALESCE(excluded.publish_title, '') <> '' THEN excluded.publish_title
                        ELSE material_profile.publish_title
                    END,
                    creative_title_material_ids_json = CASE
                        WHEN COALESCE(excluded.creative_title_material_ids_json, '') <> ''
                         AND excluded.creative_title_material_ids_json <> '[]'
                        THEN excluded.creative_title_material_ids_json
                        ELSE material_profile.creative_title_material_ids_json
                    END,
                    creative_source = CASE
                        WHEN COALESCE(excluded.creative_source, '') <> '' THEN excluded.creative_source
                        ELSE material_profile.creative_source
                    END
                """,
                [
                    (
                        customer_center_id,
                        material_key,
                        material_id,
                        material_name,
                        material_type,
                        video_id,
                        updated_at,
                        backend_name,
                        publish_title,
                        title_ids_json,
                        creative_source,
                    )
                    for (
                        backend_name,
                        publish_title,
                        title_ids_json,
                        creative_source,
                        material_name,
                        material_id,
                        material_type,
                        video_id,
                        material_key,
                    ) in rollup_updates
                ],
            )
            service._invalidate_material_ranking_indexes_for_day(conn, day_key, customer_center_id)
    service.clear_material_runtime_caches(scope="all")
    return {
        "relation_rows": len(relation_updates),
        "snapshot_rows": len(snapshot_updates),
        "material_keys": len(rollup_updates),
    }


def count_state(customer_center_id: str, day_key: str) -> dict[str, Any]:
    with service.db() as conn:
        relation = dict(
            conn.execute(
                """
                SELECT COUNT(*) AS relation_rows,
                       COUNT(*) FILTER (WHERE COALESCE(publish_title, '') <> '') AS publish_title_filled,
                       COUNT(*) FILTER (WHERE creative_source = 'creative_detail') AS creative_detail_rows,
                       COUNT(*) FILTER (
                           WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO'
                             AND COALESCE(backend_material_name, '') <> ''
                       ) AS video_backend_filled,
                       ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS stat_cost
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
                       COUNT(*) FILTER (WHERE COALESCE(publish_title, '') <> '') AS publish_title_filled,
                       COUNT(*) FILTER (WHERE creative_source = 'creative_detail') AS creative_detail_rows,
                       COUNT(*) FILTER (
                           WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO'
                             AND COALESCE(backend_material_name, '') <> ''
                       ) AS video_backend_filled,
                       ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS stat_cost
                FROM material_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                """,
                (customer_center_id, day_key),
            ).fetchone()
            or {}
        )
    return {
        "relation": {key: (float(value) if key == "stat_cost" else int(value or 0)) for key, value in relation.items()},
        "daily": {key: (float(value) if key == "stat_cost" else int(value or 0)) for key, value in daily.items()},
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    service.init_db_once()
    service.bootstrap_token_store()
    service.assert_runtime_client_compatibility()
    customer_center_id = resolve_customer_center_id(args.customer_center_id)
    day_key = str(args.date).strip()[:10]
    if not customer_center_id:
        raise RuntimeError("customer_center_id is required")

    result: dict[str, Any] = {
        "customer_center_id": customer_center_id,
        "day": day_key,
        "dry_run": bool(args.dry_run),
        "updated": False,
        "timings": {},
    }
    result["before"] = count_state(customer_center_id, day_key)
    plan_pairs = selected_plan_pairs(customer_center_id, day_key)
    result["selected_plan_count"] = len(plan_pairs)
    log("selected_plans", day=day_key, plan_count=len(plan_pairs))

    fetch_started = time.monotonic()
    fetch_result = fetch_creative_contexts(
        customer_center_id=customer_center_id,
        plan_pairs=plan_pairs,
        workers=max(int(args.workers or 1), 1),
    )
    result["timings"]["fetch_creative"] = round(time.monotonic() - fetch_started, 2)
    result["creative"] = {
        key: fetch_result.get(key)
        for key in ("creative_plan_count", "error_count", "errors")
    }
    creative_by_plan = fetch_result["creative_by_plan"]
    log("fetch_done", day=day_key, elapsed_seconds=result["timings"]["fetch_creative"], **result["creative"])

    build_started = time.monotonic()
    relation_rows = load_rows(customer_center_id, day_key, table="material_relation_daily")
    snapshot_rows = load_rows(customer_center_id, day_key, table="material_snapshots", snapshot=True)
    relation_updates, material_meta, relation_counts = build_updates(relation_rows, creative_by_plan)
    snapshot_updates, _snapshot_meta, snapshot_counts = build_updates(snapshot_rows, creative_by_plan)
    rollup_updates = rollup_updates_from_meta(material_meta)
    result["timings"]["build_updates"] = round(time.monotonic() - build_started, 2)
    result["computed"] = {
        "relation": relation_counts,
        "snapshot": snapshot_counts,
        "material_key_count": len(rollup_updates),
    }
    log("computed_updates", day=day_key, **result["computed"])

    if not args.dry_run:
        write_started = time.monotonic()
        result["write"] = apply_updates(
            customer_center_id=customer_center_id,
            day_key=day_key,
            relation_updates=relation_updates,
            snapshot_updates=snapshot_updates,
            rollup_updates=rollup_updates,
        )
        result["timings"]["write"] = round(time.monotonic() - write_started, 2)
        result["updated"] = True
        log("write_done", day=day_key, elapsed_seconds=result["timings"]["write"], **result["write"])
    else:
        result["write"] = {"skipped": True}

    result["after"] = count_state(customer_center_id, day_key)
    result["wall_elapsed_seconds"] = round(time.monotonic() - started, 2)
    return result


def main() -> int:
    args = parse_args()
    result = run(args)
    output = str(args.output or "").strip()
    if not output:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = str(ROOT_DIR / "tools" / f"material_creative_title_backfill_{result['day']}_{stamp}.json")
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log("finished", output=output, wall_elapsed_seconds=result["wall_elapsed_seconds"])
    return 1 if int((result.get("creative") or {}).get("error_count") or 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
