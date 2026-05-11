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

from dashboard.main import material_ranking_index, now_text, service  # noqa: E402
from tools.official_daily_align import rebuild_material_daily_from_relations  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill material backend names by material/video ids.")
    parser.add_argument("--date", required=True, help="Target day, YYYY-MM-DD.")
    parser.add_argument("--customer-center-id", default="", help="Customer center id.")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent advertiser lookup workers.")
    parser.add_argument("--batch-size", type=int, default=100, help="Video API id batch size.")
    parser.add_argument("--timeout", type=int, default=20, help="Video API request timeout.")
    parser.add_argument("--attempts", type=int, default=2, help="Video API request attempts.")
    parser.add_argument("--skip-profile-cache", action="store_true", help="Skip local material_profile cache fill.")
    parser.add_argument("--skip-index", action="store_true", help="Skip material ranking prefix index rebuild.")
    parser.add_argument("--dry-run", action="store_true", help="Only inspect selected ids.")
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


def timed(result: dict[str, Any], key: str, func: Any) -> Any:
    started = time.monotonic()
    try:
        return func()
    finally:
        result.setdefault("timings", {})[key] = round(time.monotonic() - started, 2)


def profile_cache_fill(customer_center_id: str, day_key: str) -> dict[str, int]:
    with service.db() as conn:
        relation_cursor = conn.execute(
            """
            UPDATE material_relation_daily m
            SET backend_material_name = COALESCE(NULLIF(p.backend_material_name, ''), m.backend_material_name, ''),
                publish_title = COALESCE(NULLIF(p.publish_title, ''), m.publish_title, ''),
                material_name = CASE
                    WHEN COALESCE(NULLIF(p.backend_material_name, ''), '') <> '' THEN p.backend_material_name
                    ELSE m.material_name
                END
            FROM material_profile p
            WHERE m.customer_center_id = p.customer_center_id
              AND m.material_key = p.material_key
              AND m.customer_center_id = ?
              AND m.biz_date = ?
              AND (COALESCE(p.backend_material_name, '') <> '' OR COALESCE(p.publish_title, '') <> '')
            """,
            (customer_center_id, day_key),
        )
        snapshot_cursor = conn.execute(
            """
            UPDATE material_snapshots m
            SET backend_material_name = COALESCE(NULLIF(p.backend_material_name, ''), m.backend_material_name, ''),
                publish_title = COALESCE(NULLIF(p.publish_title, ''), m.publish_title, ''),
                material_name = CASE
                    WHEN COALESCE(NULLIF(p.backend_material_name, ''), '') <> '' THEN p.backend_material_name
                    ELSE m.material_name
                END
            FROM material_profile p
            WHERE m.customer_center_id = p.customer_center_id
              AND m.material_key = p.material_key
              AND m.customer_center_id = ?
              AND substr(m.snapshot_time, 1, 10) = ?
              AND (COALESCE(p.backend_material_name, '') <> '' OR COALESCE(p.publish_title, '') <> '')
            """,
            (customer_center_id, day_key),
        )
        daily_cursor = conn.execute(
            """
            UPDATE material_daily m
            SET backend_material_name = COALESCE(NULLIF(p.backend_material_name, ''), m.backend_material_name, ''),
                publish_title = COALESCE(NULLIF(p.publish_title, ''), m.publish_title, ''),
                material_name = CASE
                    WHEN COALESCE(NULLIF(p.backend_material_name, ''), '') <> '' THEN p.backend_material_name
                    ELSE m.material_name
                END
            FROM material_profile p
            WHERE m.customer_center_id = p.customer_center_id
              AND m.material_key = p.material_key
              AND m.customer_center_id = ?
              AND m.biz_date = ?
              AND (COALESCE(p.backend_material_name, '') <> '' OR COALESCE(p.publish_title, '') <> '')
            """,
            (customer_center_id, day_key),
        )
    return {
        "relation_rows": int(getattr(relation_cursor, "rowcount", 0) or 0),
        "snapshot_rows": int(getattr(snapshot_cursor, "rowcount", 0) or 0),
        "daily_rows": int(getattr(daily_cursor, "rowcount", 0) or 0),
    }


def selected_video_ids(customer_center_id: str, day_key: str) -> dict[int, dict[str, set[str]]]:
    grouped: dict[int, dict[str, set[str]]] = {}
    with service.db() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT advertiser_id, material_key, material_id, video_id, material_name, backend_material_name
                FROM material_relation_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                  AND UPPER(COALESCE(material_type, '')) = 'VIDEO'
                  AND (
                        COALESCE(backend_material_name, '') = ''
                     OR LENGTH(COALESCE(material_name, '')) >= 60
                  )
                GROUP BY advertiser_id, material_key, material_id, video_id, material_name, backend_material_name
                ORDER BY advertiser_id, material_key
                """,
                (customer_center_id, day_key),
            ).fetchall()
        ]
    for row in rows:
        advertiser_id = int(row.get("advertiser_id") or 0)
        if advertiser_id <= 0:
            continue
        material_id = service._numeric_material_id_text(row.get("material_id"))
        video_id = str(row.get("video_id") or "").strip()
        material_key = str(row.get("material_key") or "").strip()
        bucket = grouped.setdefault(advertiser_id, {"material_ids": set(), "video_ids": set(), "keys": set()})
        if material_id:
            bucket["material_ids"].add(material_id)
        if video_id:
            bucket["video_ids"].add(video_id)
        if material_key:
            bucket["keys"].add(material_key)
    return grouped


def chunks(values: list[str], size: int) -> list[list[str]]:
    normalized_size = max(int(size or 100), 1)
    return [values[index : index + normalized_size] for index in range(0, len(values), normalized_size)]


def fetch_names_for_advertiser(
    *,
    client: Any,
    advertiser_id: int,
    material_ids: set[str],
    video_ids: set[str],
    batch_size: int,
    timeout: int,
    attempts: int,
) -> dict[str, Any]:
    material_name_map: dict[str, dict[str, str]] = {}
    video_name_map: dict[str, dict[str, str]] = {}
    errors: list[dict[str, Any]] = []
    api_calls = 0
    returned_rows = 0

    def remember(item: dict[str, Any]) -> None:
        nonlocal returned_rows
        returned_rows += 1
        backend_name = service._backend_material_name_from_video_item(item)
        if not backend_name:
            return
        material_id = service._numeric_material_id_text(item.get("material_id"))
        video_id = str(item.get("id") or item.get("video_id") or item.get("videoId") or "").strip()
        payload = {"backend_material_name": backend_name, "video_id": video_id, "material_id": material_id}
        if material_id:
            material_name_map[material_id] = payload
        if video_id:
            video_name_map[video_id] = payload

    for batch in chunks(sorted(video_ids), batch_size):
        if not batch:
            continue
        api_calls += 1
        try:
            rows = client.list_qianchuan_videos(
                advertiser_id=advertiser_id,
                filtering={"video_ids": batch},
                page_size=max(20, min(100, len(batch))),
                max_pages=1,
                timeout=timeout,
                attempts=attempts,
            )
            for item in rows:
                remember(dict(item or {}))
        except Exception as exc:  # noqa: BLE001
            errors.append({"advertiser_id": advertiser_id, "lookup": "video_ids", "ids": batch[:10], "error": str(exc)})

    unresolved_material_ids = [item for item in sorted(material_ids) if item not in material_name_map]
    for batch in chunks(unresolved_material_ids, batch_size):
        if not batch:
            continue
        api_calls += 1
        try:
            rows = client.list_qianchuan_videos(
                advertiser_id=advertiser_id,
                filtering={"material_ids": [int(item) for item in batch]},
                page_size=max(20, min(100, len(batch))),
                max_pages=1,
                timeout=timeout,
                attempts=attempts,
            )
            for item in rows:
                remember(dict(item or {}))
        except Exception as exc:  # noqa: BLE001
            errors.append({"advertiser_id": advertiser_id, "lookup": "material_ids", "ids": batch[:10], "error": str(exc)})

    return {
        "advertiser_id": advertiser_id,
        "material_name_map": material_name_map,
        "video_name_map": video_name_map,
        "api_calls": api_calls,
        "returned_rows": returned_rows,
        "error_count": len(errors),
        "errors": errors,
    }


def update_names(
    *,
    customer_center_id: str,
    day_key: str,
    material_name_map: dict[tuple[int, str], dict[str, str]],
    video_name_map: dict[tuple[int, str], dict[str, str]],
) -> dict[str, Any]:
    updates_by_key: dict[tuple[int, str], dict[str, str]] = {}
    with service.db() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT advertiser_id, material_key, material_id, video_id
                FROM material_relation_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                  AND UPPER(COALESCE(material_type, '')) = 'VIDEO'
                GROUP BY advertiser_id, material_key, material_id, video_id
                """,
                (customer_center_id, day_key),
            ).fetchall()
        ]
        for row in rows:
            advertiser_id = int(row.get("advertiser_id") or 0)
            material_key = str(row.get("material_key") or "").strip()
            material_id = service._numeric_material_id_text(row.get("material_id"))
            video_id = str(row.get("video_id") or "").strip()
            payload = None
            if material_id:
                payload = material_name_map.get((advertiser_id, material_id))
            if payload is None and video_id:
                payload = video_name_map.get((advertiser_id, video_id))
            if not material_key or not payload or not payload.get("backend_material_name"):
                continue
            updates_by_key[(advertiser_id, material_key)] = {
                "material_key": material_key,
                "material_id": material_id or payload.get("material_id", ""),
                "video_id": video_id or payload.get("video_id", ""),
                "backend_material_name": payload["backend_material_name"],
            }

        updated_at = now_text()
        update_tuples = [
            (
                item["backend_material_name"],
                item["backend_material_name"],
                item.get("video_id", ""),
                customer_center_id,
                day_key,
                advertiser_id,
                item["material_key"],
            )
            for (advertiser_id, _material_key), item in updates_by_key.items()
        ]
        if update_tuples:
            conn.executemany(
                """
                UPDATE material_relation_daily
                SET backend_material_name = ?,
                    material_name = ?,
                    video_id = COALESCE(NULLIF(?, ''), video_id)
                WHERE customer_center_id = ?
                  AND biz_date = ?
                  AND advertiser_id = ?
                  AND material_key = ?
                """,
                update_tuples,
            )
            conn.executemany(
                """
                UPDATE material_snapshots
                SET backend_material_name = ?,
                    material_name = ?,
                    video_id = COALESCE(NULLIF(?, ''), video_id)
                WHERE customer_center_id = ?
                  AND substr(snapshot_time, 1, 10) = ?
                  AND advertiser_id = ?
                  AND material_key = ?
                """,
                update_tuples,
            )
            conn.executemany(
                """
                INSERT INTO material_profile (
                    customer_center_id, material_key, material_id, material_name, material_type,
                    video_id, updated_at, backend_material_name
                ) VALUES (?, ?, ?, ?, 'VIDEO', ?, ?, ?)
                ON CONFLICT (customer_center_id, material_key) DO UPDATE SET
                    material_id = COALESCE(NULLIF(excluded.material_id, ''), material_profile.material_id),
                    material_name = excluded.material_name,
                    material_type = 'VIDEO',
                    video_id = COALESCE(NULLIF(excluded.video_id, ''), material_profile.video_id),
                    updated_at = excluded.updated_at,
                    backend_material_name = excluded.backend_material_name
                """,
                [
                    (
                        customer_center_id,
                        item["material_key"],
                        item.get("material_id", ""),
                        item["backend_material_name"],
                        item.get("video_id", ""),
                        updated_at,
                        item["backend_material_name"],
                    )
                    for item in updates_by_key.values()
                ],
            )
        rebuilt_daily_rows = rebuild_material_daily_from_relations(conn, customer_center_id, day_key)
    post_rebuild_cache_fill = profile_cache_fill(customer_center_id, day_key)
    return {
        "updated_material_keys": len(updates_by_key),
        "rebuilt_material_daily_rows": rebuilt_daily_rows,
        "post_rebuild_cache_fill": post_rebuild_cache_fill,
    }


def count_state(customer_center_id: str, day_key: str) -> dict[str, Any]:
    with service.db() as conn:
        relation = dict(
            conn.execute(
                """
                SELECT COUNT(*) AS relation_rows,
                       COUNT(DISTINCT material_key) AS relation_keys,
                       COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO') AS video_rows,
                       COUNT(*) FILTER (
                           WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO'
                             AND COALESCE(backend_material_name, '') <> ''
                       ) AS video_backend_filled,
                       COUNT(*) FILTER (WHERE COALESCE(publish_title, '') <> '') AS publish_title_filled,
                       COUNT(*) FILTER (
                           WHERE LENGTH(COALESCE(material_name, '')) >= 60
                             AND COALESCE(backend_material_name, '') = ''
                       ) AS long_name_backend_blank,
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
                       COUNT(*) FILTER (WHERE UPPER(COALESCE(material_type, '')) = 'VIDEO') AS video_rows,
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


def rebuild_index(customer_center_id: str, day_key: str) -> dict[str, Any]:
    prefix_end_day = service._material_history_index_refresh_end_day([day_key])
    results = []
    results.append(
        material_ranking_index.rebuild_day_prefix_range(
            service,
            start_day=day_key,
            end_day=prefix_end_day,
            all_customer_centers=False,
            force_scope_key=customer_center_id,
            force_customer_center_id=customer_center_id,
        )
    )
    results.append(
        material_ranking_index.rebuild_day_prefix_range(
            service,
            start_day=day_key,
            end_day=prefix_end_day,
            all_customer_centers=True,
            force_scope_key=material_ranking_index.SCOPE_ALL,
        )
    )
    service.clear_material_runtime_caches(scope="all")
    return {
        "ok": all(bool(item.get("ok")) for item in results),
        "start_day": day_key,
        "end_day": prefix_end_day,
        "results": results,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
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
        "updated": False,
        "timings": {},
    }
    result["before"] = count_state(customer_center_id, day_key)
    if not args.skip_profile_cache and not args.dry_run:
        result["profile_cache_fill"] = timed(
            result,
            "profile_cache_fill",
            lambda: profile_cache_fill(customer_center_id, day_key),
        )
    else:
        result["profile_cache_fill"] = {"skipped": True}

    grouped = selected_video_ids(customer_center_id, day_key)
    result["selected_advertiser_count"] = len(grouped)
    result["selected_material_id_count"] = sum(len(item["material_ids"]) for item in grouped.values())
    result["selected_video_id_count"] = sum(len(item["video_ids"]) for item in grouped.values())
    result["selected_samples"] = [
        {
            "advertiser_id": advertiser_id,
            "material_ids": len(payload["material_ids"]),
            "video_ids": len(payload["video_ids"]),
        }
        for advertiser_id, payload in list(sorted(grouped.items()))[:20]
    ]
    log(
        "selected_ids",
        day=day_key,
        advertiser_count=result["selected_advertiser_count"],
        material_id_count=result["selected_material_id_count"],
        video_id_count=result["selected_video_id_count"],
    )
    if args.dry_run or not grouped:
        result["after"] = count_state(customer_center_id, day_key)
        return result

    client = service._build_scoped_customer_center_client(customer_center_id)

    def fetch_all() -> dict[str, Any]:
        material_name_map: dict[tuple[int, str], dict[str, str]] = {}
        video_name_map: dict[tuple[int, str], dict[str, str]] = {}
        errors: list[dict[str, Any]] = []
        api_calls = 0
        returned_rows = 0
        with ThreadPoolExecutor(max_workers=max(int(args.workers or 1), 1)) as pool:
            future_map = {
                pool.submit(
                    fetch_names_for_advertiser,
                    client=client,
                    advertiser_id=advertiser_id,
                    material_ids=payload["material_ids"],
                    video_ids=payload["video_ids"],
                    batch_size=max(int(args.batch_size or 100), 1),
                    timeout=max(int(args.timeout or 20), 1),
                    attempts=max(int(args.attempts or 2), 1),
                ): advertiser_id
                for advertiser_id, payload in grouped.items()
            }
            for future in as_completed(future_map):
                payload = future.result()
                advertiser_id = int(payload["advertiser_id"])
                api_calls += int(payload.get("api_calls") or 0)
                returned_rows += int(payload.get("returned_rows") or 0)
                errors.extend(payload.get("errors") or [])
                for material_id, item in (payload.get("material_name_map") or {}).items():
                    material_name_map[(advertiser_id, str(material_id))] = dict(item)
                for video_id, item in (payload.get("video_name_map") or {}).items():
                    video_name_map[(advertiser_id, str(video_id))] = dict(item)
        return {
            "material_name_map": material_name_map,
            "video_name_map": video_name_map,
            "api_calls": api_calls,
            "returned_rows": returned_rows,
            "error_count": len(errors),
            "errors": errors[:50],
        }

    fetch_result = timed(result, "fetch_video_library", fetch_all)
    result["fetch_video_library"] = {
        "api_calls": fetch_result["api_calls"],
        "returned_rows": fetch_result["returned_rows"],
        "material_name_count": len(fetch_result["material_name_map"]),
        "video_name_count": len(fetch_result["video_name_map"]),
        "error_count": fetch_result["error_count"],
        "errors": fetch_result["errors"],
    }
    log("fetch_done", day=day_key, **result["fetch_video_library"])

    result["update_names"] = timed(
        result,
        "update_names",
        lambda: update_names(
            customer_center_id=customer_center_id,
            day_key=day_key,
            material_name_map=fetch_result["material_name_map"],
            video_name_map=fetch_result["video_name_map"],
        ),
    )
    log("update_done", day=day_key, **result["update_names"])

    if args.skip_index:
        result["index_result"] = {"skipped": True}
    else:
        result["index_result"] = timed(result, "index_rebuild", lambda: rebuild_index(customer_center_id, day_key))
        log("index_done", day=day_key, ok=result["index_result"].get("ok"))

    result["after"] = count_state(customer_center_id, day_key)
    result["updated"] = True
    result["total_elapsed_seconds"] = round(sum(float(value or 0.0) for value in result["timings"].values()), 2)
    return result


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    result = run(args)
    result["wall_elapsed_seconds"] = round(time.monotonic() - started, 2)
    output = str(args.output or "").strip()
    if not output:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = str(ROOT_DIR / "tools" / f"material_name_id_backfill_{result['day']}_{stamp}.json")
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log("finished", output=output, wall_elapsed_seconds=result["wall_elapsed_seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
