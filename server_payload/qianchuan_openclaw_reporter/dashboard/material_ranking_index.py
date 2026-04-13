from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


SORT_KEYS = (
    "stat_cost",
    "total_pay_amount",
    "settled_pay_amount",
    "pay_amount",
    "order_count",
)
DEFAULT_PAGE_SIZE = 20
RETENTION_DAYS = max(int(str(os.environ.get("MATERIAL_RANKING_INDEX_RETENTION_DAYS") or "60").strip() or "60"), 1)
SCOPE_ALL = "__all_customer_centers__"


def scope_key(service: Any, *, all_customer_centers: bool = False) -> str:
    return SCOPE_ALL if all_customer_centers else str(service._current_customer_center_id() or "").strip()


def normalize_sort_key(value: str = "") -> str:
    text = str(value or "").strip()
    return text if text in SORT_KEYS else "stat_cost"


def normalize_sort_dir(value: str = "desc") -> str:
    text = str(value or "desc").strip().lower()
    return text if text in {"asc", "desc"} else "desc"


def index_range_key(normalized: str, start_day: str, end_day: str) -> str:
    normalized_range = str(normalized or "").strip().lower()
    if str(start_day or "").strip() == str(end_day or "").strip():
        return "day"
    if normalized_range in {"week", "month"}:
        return normalized_range
    return ""


def _date_key(value: str, field_name: str = "date") -> str:
    try:
        return datetime.strptime(str(value or "").strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _metric_source_queries(
    service: Any,
    *,
    start_day: str,
    end_day: str,
    today_key: str,
    all_customer_centers: bool,
) -> tuple[list[str], list[Any]]:
    queries: list[str] = []
    params: list[Any] = []
    daily_end_day = min(
        end_day,
        (datetime.strptime(today_key, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    if start_day <= daily_end_day:
        daily_where = ["md.biz_date >= ?", "md.biz_date <= ?"]
        params.extend([start_day, daily_end_day])
        daily_where.append(
            service._material_history_stable_day_sql(
                day_expr="md.biz_date",
                customer_center_expr="md.customer_center_id",
            )
        )
        if all_customer_centers:
            daily_where.append("COALESCE(md.customer_center_id, '') <> ''")
        else:
            daily_where.append("md.customer_center_id = ?")
            params.append(service._current_customer_center_id())
        queries.append(
            f"""
            SELECT
                md.customer_center_id,
                md.snapshot_time,
                md.biz_date AS source_day,
                md.material_key,
                md.create_time,
                md.stat_cost,
                md.pay_amount,
                md.total_pay_amount,
                md.settled_pay_amount,
                md.order_count,
                md.settled_order_count,
                md.overall_show_count,
                md.overall_click_count,
                md.refund_amount_1h,
                md.plan_ids_json,
                md.advertiser_ids_json
            FROM material_daily md
            WHERE {' AND '.join(daily_where)}
            """
        )
    if end_day >= today_key:
        current_where: list[str] = []
        if all_customer_centers:
            current_where.append("COALESCE(mc.customer_center_id, '') <> ''")
        else:
            current_where.append("mc.customer_center_id = ?")
            params.append(service._current_customer_center_id())
        queries.append(
            f"""
            SELECT
                mc.customer_center_id,
                mc.snapshot_time,
                substr(mc.snapshot_time, 1, 10) AS source_day,
                mc.material_key,
                mc.create_time,
                mc.stat_cost,
                mc.pay_amount,
                mc.total_pay_amount,
                mc.settled_pay_amount,
                mc.order_count,
                mc.settled_order_count,
                mc.overall_show_count,
                mc.overall_click_count,
                mc.refund_amount_1h,
                mc.plan_ids_json,
                mc.advertiser_ids_json
            FROM material_current mc
            WHERE {' AND '.join(current_where) if current_where else '1 = 1'}
            """
        )
    return queries, params


def _source_has_rows(conn: Any, source_sql: str, params: list[Any]) -> bool:
    row = conn.execute(
        f"""
        WITH source AS (
            {source_sql}
        )
        SELECT EXISTS(SELECT 1 FROM source LIMIT 1) AS has_rows
        """,
        params,
    ).fetchone()
    return bool((row or {}).get("has_rows"))


def _available_recent_day_keys(
    service: Any,
    conn: Any,
    *,
    today_key: str,
    day_count: int,
    all_customer_centers: bool,
) -> list[str]:
    start_day = (datetime.strptime(today_key, "%Y-%m-%d").date() - timedelta(days=max(day_count - 1, 0))).strftime(
        "%Y-%m-%d"
    )
    params: list[Any] = [start_day, today_key]
    daily_where = [
        "COALESCE(md.biz_date::text, '') >= ?",
        "COALESCE(md.biz_date::text, '') <= ?",
        service._material_history_stable_day_sql(
            day_expr="md.biz_date",
            customer_center_expr="md.customer_center_id",
        ),
    ]
    if all_customer_centers:
        daily_where.append("COALESCE(md.customer_center_id, '') <> ''")
    else:
        daily_where.append("md.customer_center_id = ?")
        params.append(service._current_customer_center_id())
    current_params: list[Any] = [start_day, today_key]
    current_where = [
        "COALESCE(substr(mc.snapshot_time, 1, 10), '') >= ?",
        "COALESCE(substr(mc.snapshot_time, 1, 10), '') <= ?",
    ]
    if all_customer_centers:
        current_where.append("COALESCE(mc.customer_center_id, '') <> ''")
    else:
        current_where.append("mc.customer_center_id = ?")
        current_params.append(service._current_customer_center_id())
    rows = conn.execute(
        f"""
        WITH available_days AS (
            SELECT DISTINCT md.biz_date::text AS day_key
            FROM material_daily md
            WHERE {' AND '.join(daily_where)}
            UNION
            SELECT DISTINCT substr(mc.snapshot_time, 1, 10) AS day_key
            FROM material_current mc
            WHERE {' AND '.join(current_where)}
        )
        SELECT day_key
        FROM available_days
        WHERE COALESCE(day_key, '') <> ''
        ORDER BY day_key DESC
        """,
        [*params, *current_params],
    ).fetchall()
    return [str((row or {}).get("day_key") or "").strip() for row in rows if str((row or {}).get("day_key") or "").strip()]


def _purge_missing_recent_days(
    conn: Any,
    *,
    scope_key_value: str,
    start_day: str,
    end_day: str,
    available_day_keys: list[str],
) -> None:
    filters = [
        "scope_key = ?",
        "range_key = 'day'",
        "start_date = end_date",
        "start_date >= ?",
        "end_date <= ?",
    ]
    params: list[Any] = [scope_key_value, start_day, end_day]
    if available_day_keys:
        filters.append(f"start_date NOT IN ({','.join('?' for _ in available_day_keys)})")
        params.extend(available_day_keys)
    index_where = " AND ".join(filters)
    conn.execute(f"DELETE FROM material_ranking_index WHERE {index_where}", params)
    conn.execute(f"DELETE FROM material_ranking_summary WHERE {index_where}", params)


def refresh_window(
    service: Any,
    *,
    start_day: str,
    end_day: str,
    range_key: str = "day",
    all_customer_centers: bool = False,
    sort_keys: list[str] | tuple[str, ...] | None = None,
    sort_dirs: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    start_day = _date_key(start_day, "start_day")
    end_day = _date_key(end_day, "end_day")
    if start_day > end_day:
        start_day, end_day = end_day, start_day
    normalized_range = str(range_key or "day").strip().lower() or "day"
    normalized_sort_keys = list(dict.fromkeys(normalize_sort_key(item) for item in list(sort_keys or SORT_KEYS)))
    normalized_sort_dirs = list(dict.fromkeys(normalize_sort_dir(item) for item in list(sort_dirs or ("desc",))))
    target_scope = scope_key(service, all_customer_centers=all_customer_centers)
    sort_values_sql = ", ".join(
        f"('{sort_key}', '{sort_dir}')"
        for sort_key in normalized_sort_keys
        for sort_dir in normalized_sort_dirs
    )
    metric_expr = """
        CASE sort_config.sort_key
            WHEN 'stat_cost' THEN aggregated.stat_cost
            WHEN 'total_pay_amount' THEN aggregated.total_pay_amount
            WHEN 'settled_pay_amount' THEN aggregated.settled_pay_amount
            WHEN 'pay_amount' THEN aggregated.pay_amount
            WHEN 'order_count' THEN aggregated.order_count::double precision
            ELSE aggregated.stat_cost
        END
    """
    with service.db() as conn:
        today_key = datetime.now(ZoneInfo(service.read_config().get("timezone") or "Asia/Shanghai")).strftime("%Y-%m-%d")
        source_queries, source_params = _metric_source_queries(
            service,
            start_day=start_day,
            end_day=end_day,
            today_key=today_key,
            all_customer_centers=all_customer_centers,
        )
        delete_params = [target_scope, normalized_range, start_day, end_day]
        conn.execute(
            """
            DELETE FROM material_ranking_index
            WHERE scope_key = ?
              AND range_key = ?
              AND start_date = ?
              AND end_date = ?
            """,
            delete_params,
        )
        conn.execute(
            """
            DELETE FROM material_ranking_summary
            WHERE scope_key = ?
              AND range_key = ?
              AND start_date = ?
              AND end_date = ?
            """,
            delete_params,
        )
        if not source_queries:
            return {
                "ok": True,
                "skipped": True,
                "reason": "no source rows",
                "scope_key": target_scope,
                "range_key": normalized_range,
                "start_date": start_day,
                "end_date": end_day,
            }
        updated_at = _now_text()
        source_sql = " UNION ALL ".join(source_queries)
        if not _source_has_rows(conn, source_sql, source_params):
            return {
                "ok": True,
                "skipped": True,
                "reason": "source query returned no rows",
                "scope_key": target_scope,
                "range_key": normalized_range,
                "start_date": start_day,
                "end_date": end_day,
            }
        aggregate_cte = f"""
        WITH source AS (
            {source_sql}
        ),
        material_plan_ids AS (
            SELECT DISTINCT source.material_key, CAST(plan_item.value AS BIGINT) AS plan_id
            FROM source
            CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(NULLIF(source.plan_ids_json, ''), '[]')::jsonb) AS plan_item(value)
        ),
        material_advertiser_ids AS (
            SELECT DISTINCT source.material_key, CAST(adv_item.value AS BIGINT) AS advertiser_id
            FROM source
            CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(NULLIF(source.advertiser_ids_json, ''), '[]')::jsonb) AS adv_item(value)
        ),
        aggregated AS (
            SELECT
                source.material_key,
                COALESCE(MIN(NULLIF(source.create_time, '')), '') AS create_time,
                MAX(source.snapshot_time) AS snapshot_time,
                CAST(ROUND(COALESCE(SUM(source.stat_cost), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS stat_cost,
                CAST(ROUND(COALESCE(SUM(source.pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS pay_amount,
                CAST(ROUND(COALESCE(SUM(source.total_pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS total_pay_amount,
                CAST(ROUND(COALESCE(SUM(source.settled_pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS settled_pay_amount,
                CAST(COALESCE(SUM(source.order_count), 0) AS INTEGER) AS order_count,
                CAST(COALESCE(SUM(source.settled_order_count), 0) AS INTEGER) AS settled_order_count,
                CAST(COALESCE(SUM(source.overall_show_count), 0) AS INTEGER) AS overall_show_count,
                CAST(COALESCE(SUM(source.overall_click_count), 0) AS INTEGER) AS overall_click_count,
                CAST(ROUND(COALESCE(SUM(source.refund_amount_1h), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS refund_amount_1h,
                CAST(COALESCE((SELECT COUNT(DISTINCT mpi.plan_id) FROM material_plan_ids mpi WHERE mpi.material_key = source.material_key), 0) AS INTEGER) AS plan_count,
                CAST(COALESCE((SELECT COUNT(DISTINCT mai.advertiser_id) FROM material_advertiser_ids mai WHERE mai.material_key = source.material_key), 0) AS INTEGER) AS advertiser_count
            FROM source
            GROUP BY source.material_key
        ),
        source_meta AS (
            SELECT
                COALESCE(MAX(snapshot_time), '') AS latest_snapshot_time,
                COUNT(DISTINCT snapshot_time) AS snapshot_count,
                COUNT(DISTINCT customer_center_id) AS customer_center_count
            FROM source
        ),
        summary AS (
            SELECT
                COUNT(*) AS total_count,
                CAST(ROUND(COALESCE(SUM(stat_cost), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS aggregate_stat_cost,
                CAST(ROUND(COALESCE(SUM(pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS aggregate_pay_amount,
                CAST(ROUND(COALESCE(SUM(total_pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS aggregate_total_pay_amount,
                CAST(ROUND(COALESCE(SUM(settled_pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS aggregate_settled_pay_amount,
                CAST(COALESCE(SUM(order_count), 0) AS INTEGER) AS aggregate_order_count,
                CAST(COALESCE(SUM(settled_order_count), 0) AS INTEGER) AS aggregate_settled_order_count,
                CAST(COALESCE(SUM(overall_show_count), 0) AS INTEGER) AS aggregate_overall_show_count,
                CAST(COALESCE(SUM(overall_click_count), 0) AS INTEGER) AS aggregate_overall_click_count,
                CAST(ROUND(COALESCE(SUM(refund_amount_1h), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS aggregate_refund_amount_1h,
                COALESCE((SELECT COUNT(DISTINCT plan_id) FROM material_plan_ids), 0) AS aggregate_plan_count,
                COALESCE((SELECT COUNT(DISTINCT advertiser_id) FROM material_advertiser_ids), 0) AS aggregate_advertiser_count
            FROM aggregated
        )
        """
        conn.execute(
            f"""
            {aggregate_cte}
            INSERT INTO material_ranking_summary (
                scope_key, range_key, start_date, end_date, total_count,
                aggregate_stat_cost, aggregate_pay_amount, aggregate_total_pay_amount,
                aggregate_settled_pay_amount, aggregate_order_count, aggregate_settled_order_count,
                aggregate_overall_show_count, aggregate_overall_click_count, aggregate_refund_amount_1h,
                aggregate_plan_count, aggregate_advertiser_count,
                snapshot_time, snapshot_count, customer_center_count, updated_at
            )
            SELECT
                ?, ?, ?, ?,
                summary.total_count,
                summary.aggregate_stat_cost,
                summary.aggregate_pay_amount,
                summary.aggregate_total_pay_amount,
                summary.aggregate_settled_pay_amount,
                summary.aggregate_order_count,
                summary.aggregate_settled_order_count,
                summary.aggregate_overall_show_count,
                summary.aggregate_overall_click_count,
                summary.aggregate_refund_amount_1h,
                summary.aggregate_plan_count,
                summary.aggregate_advertiser_count,
                source_meta.latest_snapshot_time,
                source_meta.snapshot_count,
                source_meta.customer_center_count,
                ?
            FROM summary
            CROSS JOIN source_meta
            """,
            [*source_params, target_scope, normalized_range, start_day, end_day, updated_at],
        )
        insert_cursor = conn.execute(
            f"""
            {aggregate_cte},
            sort_config(sort_key, sort_dir) AS (
                VALUES {sort_values_sql}
            ),
            ranked AS (
                SELECT
                    sort_config.sort_key,
                    sort_config.sort_dir,
                    aggregated.material_key,
                    {metric_expr} AS metric_value,
                    aggregated.stat_cost,
                    aggregated.pay_amount,
                    aggregated.total_pay_amount,
                    aggregated.settled_pay_amount,
                    aggregated.order_count,
                    aggregated.settled_order_count,
                    aggregated.overall_show_count,
                    aggregated.overall_click_count,
                    aggregated.refund_amount_1h,
                    aggregated.plan_count,
                    aggregated.advertiser_count,
                    aggregated.snapshot_time,
                    ROW_NUMBER() OVER (
                        PARTITION BY sort_config.sort_key, sort_config.sort_dir
                        ORDER BY
                            CASE WHEN {metric_expr} > 0 THEN 0 ELSE 1 END ASC,
                            CASE WHEN sort_config.sort_dir = 'desc' THEN {metric_expr} END DESC,
                            CASE WHEN sort_config.sort_dir = 'asc' THEN {metric_expr} END ASC,
                            aggregated.create_time DESC,
                            aggregated.material_key ASC
                    ) AS rank_no
                FROM aggregated
                CROSS JOIN sort_config
            )
            INSERT INTO material_ranking_index (
                scope_key, range_key, start_date, end_date, sort_key, sort_dir,
                material_key, rank_no, page_no, metric_value,
                stat_cost, pay_amount, total_pay_amount, settled_pay_amount,
                order_count, settled_order_count, overall_show_count, overall_click_count,
                refund_amount_1h, plan_count, advertiser_count, snapshot_time, updated_at
            )
            SELECT
                ?, ?, ?, ?,
                ranked.sort_key,
                ranked.sort_dir,
                ranked.material_key,
                ranked.rank_no,
                CAST(((ranked.rank_no - 1) / ?) + 1 AS INTEGER),
                ranked.metric_value,
                ranked.stat_cost,
                ranked.pay_amount,
                ranked.total_pay_amount,
                ranked.settled_pay_amount,
                ranked.order_count,
                ranked.settled_order_count,
                ranked.overall_show_count,
                ranked.overall_click_count,
                ranked.refund_amount_1h,
                ranked.plan_count,
                ranked.advertiser_count,
                ranked.snapshot_time,
                ?
            FROM ranked
            """,
            [
                *source_params,
                target_scope,
                normalized_range,
                start_day,
                end_day,
                DEFAULT_PAGE_SIZE,
                updated_at,
            ],
        )
        cutoff = (datetime.strptime(end_day, "%Y-%m-%d").date() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
        conn.execute("DELETE FROM material_ranking_index WHERE end_date < ?", [cutoff])
        conn.execute("DELETE FROM material_ranking_summary WHERE end_date < ?", [cutoff])
        summary_row = conn.execute(
            """
            SELECT total_count
            FROM material_ranking_summary
            WHERE scope_key = ?
              AND range_key = ?
              AND start_date = ?
              AND end_date = ?
            """,
            [target_scope, normalized_range, start_day, end_day],
        ).fetchone()
    return {
        "ok": True,
        "scope_key": target_scope,
        "range_key": normalized_range,
        "start_date": start_day,
        "end_date": end_day,
        "sort_keys": normalized_sort_keys,
        "sort_dirs": normalized_sort_dirs,
        "material_count": int((summary_row or {}).get("total_count", 0) or 0),
        "inserted_rows": int(getattr(insert_cursor, "rowcount", 0) or 0),
    }


def rebuild_recent(service: Any, *, days: int = RETENTION_DAYS, all_customer_centers: bool = False) -> dict[str, Any]:
    tz_name = str(service.read_config().get("timezone") or "Asia/Shanghai")
    today = datetime.now(ZoneInfo(tz_name)).date()
    day_count = max(min(int(days or RETENTION_DAYS), RETENTION_DAYS), 1)
    results: list[dict[str, Any]] = []
    today_key = today.strftime("%Y-%m-%d")
    window_start_day = (today - timedelta(days=max(day_count - 1, 0))).strftime("%Y-%m-%d")
    target_scope = scope_key(service, all_customer_centers=all_customer_centers)
    with service.db() as conn:
        available_day_keys = _available_recent_day_keys(
            service,
            conn,
            today_key=today_key,
            day_count=day_count,
            all_customer_centers=all_customer_centers,
        )
        _purge_missing_recent_days(
            conn,
            scope_key_value=target_scope,
            start_day=window_start_day,
            end_day=today_key,
            available_day_keys=available_day_keys,
        )
    for day_key in available_day_keys:
        results.append(
            refresh_window(
                service,
                start_day=day_key,
                end_day=day_key,
                range_key="day",
                all_customer_centers=all_customer_centers,
            )
        )
    for range_name, length in (("week", 7), ("month", 30)):
        results.append(
            refresh_window(
                service,
                start_day=(today - timedelta(days=length - 1)).strftime("%Y-%m-%d"),
                end_day=today.strftime("%Y-%m-%d"),
                range_key=range_name,
                all_customer_centers=all_customer_centers,
            )
        )
    try:
        service.clear_material_runtime_caches(scope="all")
    except Exception:
        pass
    return {
        "ok": True,
        "days": day_count,
        "available_day_count": len(available_day_keys),
        "all_customer_centers": bool(all_customer_centers),
        "result_count": len(results),
        "material_count": sum(int(item.get("material_count", 0) or 0) for item in results),
        "results": results[-5:],
    }


def payload_from_index(
    service: Any,
    conn: Any,
    *,
    source_queries: list[str],
    source_params: list[Any],
    scope_key_value: str,
    index_range_key_value: str,
    start_day: str,
    end_day: str,
    normalized: str,
    range_label: str,
    start_dt: datetime,
    end_dt: datetime,
    tz_name: str,
    page: int,
    page_size: int,
    sort_key: str,
    sort_dir: str,
    all_customer_centers: bool,
) -> dict[str, Any] | None:
    summary_row = conn.execute(
        """
        SELECT *
        FROM material_ranking_summary
        WHERE scope_key = ?
          AND range_key = ?
          AND start_date = ?
          AND end_date = ?
        """,
        [scope_key_value, index_range_key_value, start_day, end_day],
    ).fetchone()
    if not summary_row:
        return None
    summary = dict(summary_row)
    total_count = int(summary.get("total_count", 0) or 0)
    if total_count <= 0:
        return None
    normalized_page = max(int(page or 1), 1)
    normalized_page_size = max(int(page_size or DEFAULT_PAGE_SIZE), 1)
    total_pages = max(1, (total_count + normalized_page_size - 1) // normalized_page_size)
    current_page = min(normalized_page, total_pages)
    start_index = (current_page - 1) * normalized_page_size
    page_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT material_key, rank_no
            FROM material_ranking_index
            WHERE scope_key = ?
              AND range_key = ?
              AND start_date = ?
              AND end_date = ?
              AND sort_key = ?
              AND sort_dir = ?
            ORDER BY rank_no ASC
            LIMIT ? OFFSET ?
            """,
            [
                scope_key_value,
                index_range_key_value,
                start_day,
                end_day,
                sort_key,
                sort_dir,
                normalized_page_size,
                start_index,
            ],
        ).fetchall()
    ]
    page_material_keys = [
        str(row.get("material_key") or "").strip()
        for row in page_rows
        if str(row.get("material_key") or "").strip()
    ]
    if not page_material_keys:
        return None
    page_source_sql = f"""
    WITH source AS (
        {' UNION ALL '.join(source_queries)}
    )
    SELECT *
    FROM source
    WHERE material_key IN ({','.join('?' for _ in page_material_keys)})
    """
    page_source_rows = [
        dict(row)
        for row in conn.execute(page_source_sql, [*source_params, *page_material_keys]).fetchall()
    ]
    latest_snapshot_time = str(summary.get("snapshot_time") or "").strip()
    payload = service._build_material_payload_from_rows(
        conn,
        page_source_rows,
        latest_snapshot_time=latest_snapshot_time,
        all_customer_centers=all_customer_centers,
        meta_rows=page_source_rows,
        enrich_snapshot_context=True,
        query_context_ready=True,
    )
    key_order = {key: index for index, key in enumerate(page_material_keys)}
    items = service._sanitize_material_preview_fields_for_payload(
        service._apply_latest_material_previews(
            conn,
            payload.get("items") or [],
        )
    )
    items = [dict(item or {}) for item in items]
    items.sort(
        key=lambda item: key_order.get(
            str(item.get("material_key") or "").strip(),
            len(key_order),
        )
    )
    payload["items"] = items
    total_stat_cost = round(float(summary.get("aggregate_stat_cost", 0.0) or 0.0), 2)
    total_pay_amount = round(float(summary.get("aggregate_pay_amount", 0.0) or 0.0), 2)
    total_total_pay_amount = round(float(summary.get("aggregate_total_pay_amount", 0.0) or 0.0), 2)
    total_settled_pay_amount = round(float(summary.get("aggregate_settled_pay_amount", 0.0) or 0.0), 2)
    total_order_count = int(summary.get("aggregate_order_count", 0) or 0)
    total_settled_order_count = int(summary.get("aggregate_settled_order_count", 0) or 0)
    total_show_count = int(summary.get("aggregate_overall_show_count", 0) or 0)
    total_click_count = int(summary.get("aggregate_overall_click_count", 0) or 0)
    total_refund_amount_1h = round(float(summary.get("aggregate_refund_amount_1h", 0.0) or 0.0), 2)
    page_items = list(payload.get("items") or [])
    payload["snapshot_time"] = latest_snapshot_time
    payload["snapshot_count"] = int(summary.get("snapshot_count", 0) or 0)
    payload["meta"] = service._material_meta_from_rows(
        list(page_items or []),
        latest_snapshot_time,
        material_count=total_count,
    )
    if all_customer_centers:
        payload["customer_center_count"] = int(summary.get("customer_center_count", 0) or 0)
    payload["range_key"] = normalized
    payload["range_label"] = range_label
    payload["material_mode"] = "performance"
    payload["query_start_date"] = start_day
    payload["query_end_date"] = end_day
    payload["pagination"] = {
        "page": current_page,
        "page_size": normalized_page_size,
        "total_count": total_count,
        "total_pages": total_pages,
        "start_index": start_index + 1 if total_count > 0 else 0,
        "end_index": start_index + len(page_items),
        "sort_key": sort_key,
        "sort_dir": sort_dir,
        "search": "",
    }
    payload["materials_aggregate"] = {
        "material_mode": "performance",
        "material_count": total_count,
        "stat_cost": total_stat_cost,
        "pay_amount": total_pay_amount,
        "total_pay_amount": total_total_pay_amount,
        "settled_pay_amount": total_settled_pay_amount,
        "order_count": total_order_count,
        "settled_order_count": total_settled_order_count,
        "overall_show_count": total_show_count,
        "overall_click_count": total_click_count,
        "overall_ctr": round(total_click_count / total_show_count * 100.0, 2) if total_show_count > 0 else 0.0,
        "roi": round(total_pay_amount / total_stat_cost, 2) if total_stat_cost > 0 else 0.0,
        "settled_roi": round(total_settled_pay_amount / total_stat_cost, 2) if total_stat_cost > 0 else 0.0,
        "pay_order_cost": round(total_stat_cost / total_order_count, 2) if total_order_count > 0 else 0.0,
        "settled_amount_rate": round(total_settled_pay_amount / total_total_pay_amount * 100.0, 2) if total_total_pay_amount > 0 else 0.0,
        "refund_amount_1h": total_refund_amount_1h,
        "refund_rate_1h": round(total_refund_amount_1h / total_total_pay_amount * 100.0, 2) if total_total_pay_amount > 0 else 0.0,
        "plan_count": int(summary.get("aggregate_plan_count", 0) or 0),
        "advertiser_count": int(summary.get("aggregate_advertiser_count", 0) or 0),
        "summary_text": f"共{total_count}条素材",
    }
    payload["metrics_semantics"] = {
        "money_scope": "material_reuse_aggregation",
        "reconcilable_to_account_summary": False,
        "notice": "material performance uses precomputed ranking index when available",
    }
    payload["materialTodayStatus"] = service._material_today_hot_status(
        all_customer_centers=all_customer_centers,
    )
    payload.update(
        service._history_backfill_status_for_window(
            start_dt,
            end_dt,
            tz_name=tz_name,
            kind="material",
            all_customer_centers=all_customer_centers,
        )
    )
    payload.update(
        service._history_correction_status_for_window(
            start_dt,
            end_dt,
            tz_name=tz_name,
            kind="material",
            all_customer_centers=all_customer_centers,
        )
    )
    payload["ranking_index_used"] = True
    payload["ranking_index_range_key"] = index_range_key_value
    return service._attach_freshness(
        payload,
        data_time=payload.get("snapshot_time"),
        synced_at=payload.get("snapshot_time"),
        source="material_ranking_index",
        partial=False,
    )
