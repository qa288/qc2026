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
UNATTRIBUTED_MATERIAL_TYPE = "UNATTRIBUTED_DELETED"
UNATTRIBUTED_MATERIAL_DISPLAY_NAME = "未归因关闭/暂停计划消耗"
ZERO_BUCKET_FIELDS = (
    "stat_cost",
    "pay_amount",
    "total_pay_amount",
    "settled_pay_amount",
    "order_count",
    "settled_order_count",
    "overall_show_count",
    "overall_click_count",
    "refund_amount_1h",
)


def scope_key(service: Any, *, all_customer_centers: bool = False) -> str:
    if all_customer_centers:
        try:
            customer_center_ids = [
                str(item or "").strip()
                for item in service.bound_customer_center_ids()
                if str(item or "").strip()
            ]
            customer_center_ids = list(dict.fromkeys(customer_center_ids))
            if len(customer_center_ids) == 1:
                return customer_center_ids[0]
        except Exception:
            pass
        return SCOPE_ALL
    return str(service._current_customer_center_id() or "").strip()


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
    if normalized_range == "custom" and str(start_day or "").strip() and str(end_day or "").strip():
        return "custom"
    return ""


def zero_bucket_sql(alias: str = "") -> str:
    prefix = str(alias or "").strip()
    if prefix and not prefix.endswith("."):
        prefix = f"{prefix}."
    comparisons = " AND ".join(f"COALESCE({prefix}{field}, 0) = 0" for field in ZERO_BUCKET_FIELDS)
    return f"CASE WHEN {comparisons} THEN 1 ELSE 0 END"


def material_display_name_value(material_type: Any, material_name: Any, fallback: str = "unnamed material") -> str:
    name = str(material_name or "").strip()
    if name:
        return name
    if str(material_type or "").strip().upper() == UNATTRIBUTED_MATERIAL_TYPE:
        return UNATTRIBUTED_MATERIAL_DISPLAY_NAME
    return str(fallback or "")


def material_type_value(material_key: Any, profile: dict[str, Any]) -> str:
    material_type = str((profile or {}).get("material_type") or "").strip().upper()
    if material_type:
        return material_type
    if str(material_key or "").strip().startswith("__unattributed_deleted_material__:"):
        return UNATTRIBUTED_MATERIAL_TYPE
    return "OTHER"


def _date_key(value: str, field_name: str = "date") -> str:
    try:
        return datetime.strptime(str(value or "").strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _material_profile_search_expr() -> str:
    return """
        LOWER(
            COALESCE(material_key, '') || ' ' ||
            COALESCE(material_id, '') || ' ' ||
            COALESCE(backend_material_name, '') || ' ' ||
            COALESCE(material_name, '') || ' ' ||
            COALESCE(publish_title, '') || ' ' ||
            COALESCE(video_id, '') || ' ' ||
            COALESCE(product_info_text, '') || ' ' ||
            COALESCE(top_anchor_name, '') || ' ' ||
            COALESCE(top_plan_name, '') || ' ' ||
            COALESCE(top_account_name, '') || ' ' ||
            COALESCE(aweme_item_id, '') || ' ' ||
            COALESCE(material_type, '') || ' ' ||
            COALESCE(product_names_json, '')
        )
    """


def _material_profile_search_parts(
    service: Any,
    *,
    all_customer_centers: bool,
    search_text: str,
    join_target_expr: str,
) -> tuple[str, str, list[Any], str]:
    normalized_search_text = str(search_text or "").strip().lower()
    if not normalized_search_text:
        return normalized_search_text, "", [], ""
    escaped_search = normalized_search_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    search_scope_sql = "COALESCE(customer_center_id, '') <> ''" if all_customer_centers else "customer_center_id = ?"
    search_params: list[Any] = [] if all_customer_centers else [service._current_customer_center_id()]
    search_params.append(f"%{escaped_search}%")
    search_cte_sql = f"""
    matching_materials AS (
        SELECT DISTINCT material_key
        FROM material_profile
        WHERE {search_scope_sql}
          AND {_material_profile_search_expr()} LIKE ? ESCAPE '\\'
    ),
    """
    search_join_sql = f"INNER JOIN matching_materials mm ON mm.material_key = {join_target_expr}"
    return normalized_search_text, search_cte_sql, search_params, search_join_sql


def _empty_material_index_payload(
    service: Any,
    *,
    latest_snapshot_time: str,
    normalized: str,
    range_label: str,
    start_day: str,
    end_day: str,
    normalized_page_size: int,
    normalized_sort_key: str,
    normalized_sort_dir: str,
    search_text: str,
    ranking_index_range_key: str,
    freshness_source: str,
    freshness_notice: str,
    all_customer_centers: bool,
    day_prefix_used: bool,
    day_rollup_used: bool,
    live_overlay_used: bool,
) -> dict[str, Any]:
    payload = {
        "snapshot_time": str(latest_snapshot_time or "").strip(),
        "snapshot_count": 0,
        "items": [],
        "meta": service._material_meta_from_rows([], str(latest_snapshot_time or "").strip(), material_count=0),
        "range_key": normalized,
        "range_label": range_label,
        "material_mode": "performance",
        "query_start_date": start_day,
        "query_end_date": end_day,
        "pagination": {
            "page": 1,
            "page_size": normalized_page_size,
            "total_count": 0,
            "total_pages": 1,
            "start_index": 0,
            "end_index": 0,
            "sort_key": normalized_sort_key,
            "sort_dir": normalized_sort_dir,
            "search": str(search_text or "").strip(),
        },
        "materials_aggregate": {
            "material_mode": "performance",
            "material_count": 0,
            "stat_cost": 0.0,
            "pay_amount": 0.0,
            "total_pay_amount": 0.0,
            "settled_pay_amount": 0.0,
            "order_count": 0,
            "settled_order_count": 0,
            "overall_show_count": 0,
            "overall_click_count": 0,
            "overall_ctr": 0.0,
            "roi": 0.0,
            "settled_roi": 0.0,
            "pay_order_cost": 0.0,
            "settled_amount_rate": 0.0,
            "refund_amount_1h": 0.0,
            "refund_rate_1h": 0.0,
            "plan_count": 0,
            "advertiser_count": 0,
            "summary_text": "total 0 materials",
        },
        "metrics_semantics": {
            "money_scope": "material_reuse_aggregation",
            "reconcilable_to_account_summary": False,
            "notice": freshness_notice,
        },
        "materialTodayStatus": service._material_today_hot_status(
            all_customer_centers=all_customer_centers,
        ),
        "ranking_index_used": True,
        "ranking_index_range_key": ranking_index_range_key,
        "ranking_index_day_prefix_used": bool(day_prefix_used),
        "ranking_index_day_rollup_used": bool(day_rollup_used),
        "ranking_index_live_overlay_used": bool(live_overlay_used),
    }
    return service._attach_freshness(
        payload,
        data_time=payload.get("snapshot_time"),
        synced_at=payload.get("snapshot_time"),
        source=freshness_source,
        partial=False,
    )


def _date_range(start_day: str, end_day: str) -> list[str]:
    start = datetime.strptime(_date_key(start_day, "start_day"), "%Y-%m-%d").date()
    end = datetime.strptime(_date_key(end_day, "end_day"), "%Y-%m-%d").date()
    if start > end:
        start, end = end, start
    return [
        (start + timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range((end - start).days + 1)
    ]


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
            WHEN 'stat_cost' THEN prepared.stat_cost
            WHEN 'total_pay_amount' THEN prepared.total_pay_amount
            WHEN 'settled_pay_amount' THEN prepared.settled_pay_amount
            WHEN 'pay_amount' THEN prepared.pay_amount
            WHEN 'order_count' THEN prepared.order_count::double precision
            ELSE prepared.stat_cost
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
        prepared AS (
            SELECT
                aggregated.*,
                {zero_bucket_sql("aggregated")} AS zero_bucket
            FROM aggregated
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
            FROM prepared
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
                    prepared.material_key,
                    prepared.zero_bucket,
                    {metric_expr} AS metric_value,
                    prepared.stat_cost,
                    prepared.pay_amount,
                    prepared.total_pay_amount,
                    prepared.settled_pay_amount,
                    prepared.order_count,
                    prepared.settled_order_count,
                    prepared.overall_show_count,
                    prepared.overall_click_count,
                    prepared.refund_amount_1h,
                    prepared.plan_count,
                    prepared.advertiser_count,
                    prepared.snapshot_time,
                    ROW_NUMBER() OVER (
                        PARTITION BY sort_config.sort_key, sort_config.sort_dir
                        ORDER BY
                            prepared.zero_bucket ASC,
                            CASE WHEN sort_config.sort_dir = 'desc' THEN {metric_expr} END DESC,
                            CASE WHEN sort_config.sort_dir = 'asc' THEN {metric_expr} END ASC,
                            prepared.create_time DESC,
                            prepared.material_key ASC
                    ) AS rank_no
                FROM prepared
                CROSS JOIN sort_config
            )
            INSERT INTO material_ranking_index (
                scope_key, range_key, start_date, end_date, sort_key, sort_dir,
                material_key, rank_no, page_no, zero_bucket, metric_value,
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
                ranked.zero_bucket,
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
    rolling_results: list[dict[str, Any]] = []
    prefix_result: dict[str, Any] = {
        "ok": True,
        "skipped": True,
        "reason": "no_closed_days",
    }
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
    closed_day_keys = sorted(day for day in available_day_keys if str(day or "").strip() and day < today_key)
    if closed_day_keys:
        prefix_result = rebuild_day_prefix_range(
            service,
            start_day=closed_day_keys[0],
            end_day=closed_day_keys[-1],
            all_customer_centers=all_customer_centers,
        )
        closed_window_specs = [
            (
                "week",
                (today - timedelta(days=7)).strftime("%Y-%m-%d"),
                (today - timedelta(days=1)).strftime("%Y-%m-%d"),
            ),
            (
                "month",
                (today - timedelta(days=30)).strftime("%Y-%m-%d"),
                (today - timedelta(days=1)).strftime("%Y-%m-%d"),
            ),
        ]
        oldest_closed_day = closed_day_keys[0]
        latest_closed_day = closed_day_keys[-1]
        for range_key_value, start_day, end_day in closed_window_specs:
            if start_day < oldest_closed_day or end_day > latest_closed_day:
                rolling_results.append(
                    {
                        "ok": True,
                        "skipped": True,
                        "range_key": range_key_value,
                        "start_date": start_day,
                        "end_date": end_day,
                        "reason": "insufficient_closed_history_days",
                    }
                )
                continue
            rolling_results.append(
                refresh_window(
                    service,
                    start_day=start_day,
                    end_day=end_day,
                    range_key=range_key_value,
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
        "closed_day_count": len(closed_day_keys),
        "all_customer_centers": bool(all_customer_centers),
        "result_count": len(results),
        "material_count": sum(int(item.get("material_count", 0) or 0) for item in results),
        "prefix_result": prefix_result,
        "rolling_result_count": len(rolling_results),
        "rolling_results": rolling_results,
        "results": results[-5:],
    }


def _day_prefix_source_min_day(
    conn: Any,
    *,
    customer_center_id: str,
    all_customer_centers: bool,
) -> str:
    if all_customer_centers:
        row = conn.execute(
            """
            SELECT MIN(biz_date) AS min_day
            FROM material_daily
            WHERE COALESCE(customer_center_id, '') <> ''
            """
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT MIN(biz_date) AS min_day
            FROM material_daily
            WHERE customer_center_id = ?
            """,
            [customer_center_id],
        ).fetchone()
    return str((row or {}).get("min_day") or "").strip()


def _day_prefix_previous_exists(conn: Any, *, scope_key_value: str, previous_day: str) -> bool:
    row = conn.execute(
        """
        SELECT EXISTS(
            SELECT 1
            FROM material_ranking_day_prefix
            WHERE scope_key = ?
              AND day_key = ?
            LIMIT 1
        ) AS exists_flag
        """,
        [scope_key_value, previous_day],
    ).fetchone()
    return bool((row or {}).get("exists_flag"))


def rebuild_day_prefix_day(
    service: Any,
    conn: Any,
    *,
    scope_key_value: str,
    day_key: str,
    previous_day: str,
    customer_center_id: str = "",
    all_customer_centers: bool = False,
) -> int:
    day_key = _date_key(day_key, "day_key")
    previous_day = _date_key(previous_day, "previous_day")
    normalized_customer_center_id = str(customer_center_id or "").strip()
    if not all_customer_centers and not normalized_customer_center_id:
        return 0
    if all_customer_centers:
        where_sql = "COALESCE(md.customer_center_id, '') <> ''"
        where_params: list[Any] = []
    else:
        where_sql = "md.customer_center_id = ?"
        where_params = [normalized_customer_center_id]
    stable_sql = service._material_history_stable_day_sql(
        day_expr="md.biz_date",
        customer_center_expr="md.customer_center_id",
    )
    updated_at = _now_text()
    conn.execute(
        "DELETE FROM material_ranking_day_prefix WHERE scope_key = ? AND day_key = ?",
        [scope_key_value, day_key],
    )
    cursor = conn.execute(
        f"""
        WITH prev AS (
            SELECT *
            FROM material_ranking_day_prefix
            WHERE scope_key = ?
              AND day_key = ?
        ),
        daily AS (
            SELECT
                md.material_key,
                MAX(md.snapshot_time) AS snapshot_time,
                CAST(ROUND(COALESCE(SUM(md.stat_cost), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS stat_cost,
                CAST(ROUND(COALESCE(SUM(md.pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS pay_amount,
                CAST(ROUND(COALESCE(SUM(md.total_pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS total_pay_amount,
                CAST(ROUND(COALESCE(SUM(md.settled_pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS settled_pay_amount,
                CAST(COALESCE(SUM(md.order_count), 0) AS INTEGER) AS order_count,
                CAST(COALESCE(SUM(md.settled_order_count), 0) AS INTEGER) AS settled_order_count,
                CAST(COALESCE(SUM(md.overall_show_count), 0) AS INTEGER) AS overall_show_count,
                CAST(COALESCE(SUM(md.overall_click_count), 0) AS INTEGER) AS overall_click_count,
                CAST(ROUND(COALESCE(SUM(md.refund_amount_1h), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS refund_amount_1h,
                CAST(COALESCE(SUM(md.plan_count), 0) AS INTEGER) AS plan_count,
                CAST(COALESCE(SUM(md.advertiser_count), 0) AS INTEGER) AS advertiser_count
            FROM material_daily md
            WHERE md.biz_date = ?
              AND {where_sql}
              AND {stable_sql}
            GROUP BY md.material_key
        ),
        merged AS (
            SELECT
                ?::text AS scope_key,
                ?::text AS day_key,
                COALESCE(d.material_key, p.material_key) AS material_key,
                COALESCE(NULLIF(d.snapshot_time, ''), NULLIF(p.snapshot_time, ''), '') AS snapshot_time,
                CAST(COALESCE(p.active_day_count, 0) + CASE WHEN d.material_key IS NULL THEN 0 ELSE 1 END AS INTEGER) AS active_day_count,
                CAST(ROUND((COALESCE(p.stat_cost, 0) + COALESCE(d.stat_cost, 0))::numeric, 2) AS DOUBLE PRECISION) AS stat_cost,
                CAST(ROUND((COALESCE(p.pay_amount, 0) + COALESCE(d.pay_amount, 0))::numeric, 2) AS DOUBLE PRECISION) AS pay_amount,
                CAST(ROUND((COALESCE(p.total_pay_amount, 0) + COALESCE(d.total_pay_amount, 0))::numeric, 2) AS DOUBLE PRECISION) AS total_pay_amount,
                CAST(ROUND((COALESCE(p.settled_pay_amount, 0) + COALESCE(d.settled_pay_amount, 0))::numeric, 2) AS DOUBLE PRECISION) AS settled_pay_amount,
                CAST(COALESCE(p.order_count, 0) + COALESCE(d.order_count, 0) AS INTEGER) AS order_count,
                CAST(COALESCE(p.settled_order_count, 0) + COALESCE(d.settled_order_count, 0) AS INTEGER) AS settled_order_count,
                CAST(COALESCE(p.overall_show_count, 0) + COALESCE(d.overall_show_count, 0) AS INTEGER) AS overall_show_count,
                CAST(COALESCE(p.overall_click_count, 0) + COALESCE(d.overall_click_count, 0) AS INTEGER) AS overall_click_count,
                CAST(ROUND((COALESCE(p.refund_amount_1h, 0) + COALESCE(d.refund_amount_1h, 0))::numeric, 2) AS DOUBLE PRECISION) AS refund_amount_1h,
                CAST(COALESCE(p.plan_count, 0) + COALESCE(d.plan_count, 0) AS INTEGER) AS plan_count,
                CAST(COALESCE(p.advertiser_count, 0) + COALESCE(d.advertiser_count, 0) AS INTEGER) AS advertiser_count,
                ?::text AS updated_at
            FROM prev p
            FULL OUTER JOIN daily d
              ON d.material_key = p.material_key
        )
        INSERT INTO material_ranking_day_prefix (
            scope_key, day_key, material_key, snapshot_time, active_day_count,
            stat_cost, pay_amount, total_pay_amount, settled_pay_amount,
            order_count, settled_order_count, overall_show_count, overall_click_count,
            refund_amount_1h, plan_count, advertiser_count, updated_at
        )
        SELECT
            scope_key, day_key, material_key, snapshot_time, active_day_count,
            stat_cost, pay_amount, total_pay_amount, settled_pay_amount,
            order_count, settled_order_count, overall_show_count, overall_click_count,
            refund_amount_1h, plan_count, advertiser_count, updated_at
        FROM merged
        WHERE material_key IS NOT NULL
        """,
        [scope_key_value, previous_day, day_key, *where_params, scope_key_value, day_key, updated_at],
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def rebuild_day_prefix_range(
    service: Any,
    *,
    start_day: str,
    end_day: str,
    all_customer_centers: bool = False,
    force_scope_key: str = "",
    force_customer_center_id: str = "",
) -> dict[str, Any]:
    start_day = _date_key(start_day, "start_day")
    end_day = _date_key(end_day, "end_day")
    if start_day > end_day:
        start_day, end_day = end_day, start_day
    customer_center_id = "" if all_customer_centers else str(
        force_customer_center_id or service._current_customer_center_id() or ""
    ).strip()
    scope_key_value = str(force_scope_key or "").strip()
    if not scope_key_value:
        if all_customer_centers:
            scope_key_value = scope_key(service, all_customer_centers=True)
        else:
            scope_key_value = customer_center_id or scope_key(service, all_customer_centers=False)
    if not scope_key_value:
        return {
            "ok": False,
            "reason": "missing_scope_key",
            "start_day": start_day,
            "end_day": end_day,
            "all_customer_centers": bool(all_customer_centers),
        }
    with service.db() as conn:
        prefix_table = conn.execute("SELECT to_regclass('public.material_ranking_day_prefix') AS name").fetchone()
        if not (prefix_table or {}).get("name"):
            return {
                "ok": False,
                "reason": "missing_material_ranking_day_prefix",
                "scope_key": scope_key_value,
                "start_day": start_day,
                "end_day": end_day,
                "all_customer_centers": bool(all_customer_centers),
            }
        source_min_day = _day_prefix_source_min_day(
            conn,
            customer_center_id=customer_center_id,
            all_customer_centers=all_customer_centers,
        )
        requested_start_day = start_day
        previous_day = (datetime.strptime(start_day, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d")
        if (
            source_min_day
            and source_min_day < start_day
            and not _day_prefix_previous_exists(conn, scope_key_value=scope_key_value, previous_day=previous_day)
        ):
            start_day = source_min_day
            previous_day = (datetime.strptime(start_day, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d")
        inserted_total = 0
        processed_days = 0
        for day_key in _date_range(start_day, end_day):
            inserted_total += rebuild_day_prefix_day(
                service,
                conn,
                scope_key_value=scope_key_value,
                day_key=day_key,
                previous_day=previous_day,
                customer_center_id=customer_center_id,
                all_customer_centers=all_customer_centers,
            )
            processed_days += 1
            previous_day = day_key
    return {
        "ok": True,
        "scope_key": scope_key_value,
        "requested_start_day": requested_start_day,
        "start_day": start_day,
        "end_day": end_day,
        "processed_days": processed_days,
        "inserted_rows": inserted_total,
        "all_customer_centers": bool(all_customer_centers),
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
    material_key_placeholders = ",".join("?" for _ in page_material_keys)
    today_key = datetime.now(ZoneInfo(str(tz_name or "Asia/Shanghai"))).strftime("%Y-%m-%d")
    daily_end_day = min(
        end_day,
        (datetime.strptime(today_key, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    page_source_queries: list[str] = []
    page_source_params: list[Any] = []
    if start_day <= daily_end_day:
        daily_where = [
            "md.biz_date >= ?",
            "md.biz_date <= ?",
            f"md.material_key IN ({material_key_placeholders})",
        ]
        page_source_params.extend([start_day, daily_end_day, *page_material_keys])
        if all_customer_centers:
            daily_where.append("COALESCE(md.customer_center_id, '') <> ''")
        else:
            daily_where.append("md.customer_center_id = ?")
            page_source_params.append(service._current_customer_center_id())
        page_source_queries.append(
            f"""
            SELECT
                md.customer_center_id,
                md.snapshot_time,
                md.biz_date AS source_day,
                md.window_start,
                md.window_end,
                md.material_key,
                md.material_id,
                md.material_name,
                md.create_time,
                md.material_type,
                md.video_id,
                md.cover_url,
                md.aweme_item_id,
                md.video_url,
                md.stat_cost,
                md.pay_amount,
                md.total_pay_amount,
                md.settled_pay_amount,
                md.order_count,
                md.settled_order_count,
                md.plan_count,
                md.advertiser_count,
                md.plan_ids_json,
                md.advertiser_ids_json,
                md.is_original,
                md.top_plan_name,
                md.top_account_name,
                md.top_anchor_name,
                md.product_info_text,
                md.product_names_json,
                md.overall_show_count,
                md.overall_click_count,
                md.overall_ctr,
                md.roi,
                md.settled_roi,
                md.pay_order_cost,
                md.settled_amount_rate,
                md.refund_amount_1h,
                md.refund_rate_1h
            FROM material_daily md
            WHERE {' AND '.join(daily_where)}
            """
        )
    if end_day >= today_key:
        current_where = [f"mc.material_key IN ({material_key_placeholders})"]
        page_source_params.extend(page_material_keys)
        if all_customer_centers:
            current_where.append("COALESCE(mc.customer_center_id, '') <> ''")
        else:
            current_where.append("mc.customer_center_id = ?")
            page_source_params.append(service._current_customer_center_id())
        page_source_queries.append(
            f"""
            SELECT
                mc.customer_center_id,
                mc.snapshot_time,
                substr(mc.snapshot_time, 1, 10) AS source_day,
                mc.window_start,
                mc.window_end,
                mc.material_key,
                mc.material_id,
                mc.material_name,
                mc.create_time,
                mc.material_type,
                mc.video_id,
                mc.cover_url,
                mc.aweme_item_id,
                mc.video_url,
                mc.stat_cost,
                mc.pay_amount,
                mc.total_pay_amount,
                mc.settled_pay_amount,
                mc.order_count,
                mc.settled_order_count,
                mc.plan_count,
                mc.advertiser_count,
                mc.plan_ids_json,
                mc.advertiser_ids_json,
                mc.is_original,
                mc.top_plan_name,
                mc.top_account_name,
                mc.top_anchor_name,
                mc.product_info_text,
                mc.product_names_json,
                mc.overall_show_count,
                mc.overall_click_count,
                mc.overall_ctr,
                mc.roi,
                mc.settled_roi,
                mc.pay_order_cost,
                mc.settled_amount_rate,
                mc.refund_amount_1h,
                mc.refund_rate_1h
            FROM material_current mc
            WHERE {' AND '.join(current_where)}
            """
        )
    page_source_rows = (
        [dict(row) for row in conn.execute(" UNION ALL ".join(page_source_queries), page_source_params).fetchall()]
        if page_source_queries
        else []
    )
    latest_snapshot_time = str(summary.get("snapshot_time") or "").strip()
    payload = service._build_material_payload_from_rows(
        conn,
        page_source_rows,
        latest_snapshot_time=latest_snapshot_time,
        all_customer_centers=all_customer_centers,
        meta_rows=page_source_rows,
        enrich_snapshot_context=False,
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
    payload["ranking_index_used"] = True
    payload["ranking_index_range_key"] = index_range_key_value
    return service._attach_freshness(
        payload,
        data_time=payload.get("snapshot_time"),
        synced_at=payload.get("snapshot_time"),
        source="material_ranking_index",
        partial=False,
    )


def payload_from_day_rollup_index(
    service: Any,
    conn: Any,
    *,
    source_queries: list[str],
    source_params: list[Any],
    scope_key_value: str,
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
    search_text: str = "",
) -> dict[str, Any] | None:
    start_day = _date_key(start_day, "start_day")
    end_day = _date_key(end_day, "end_day")
    if start_day > end_day:
        start_day, end_day = end_day, start_day
    normalized_sort_key = normalize_sort_key(sort_key)
    normalized_sort_dir = normalize_sort_dir(sort_dir)
    metric_column = {
        "stat_cost": "stat_cost",
        "total_pay_amount": "total_pay_amount",
        "settled_pay_amount": "settled_pay_amount",
        "pay_amount": "pay_amount",
        "order_count": "order_count",
    }.get(normalized_sort_key, "stat_cost")
    metric_order = "DESC" if normalized_sort_dir == "desc" else "ASC"
    normalized_page = max(int(page or 1), 1)
    normalized_page_size = max(int(page_size or DEFAULT_PAGE_SIZE), 1)
    normalized_search_text = str(search_text or "").strip().lower()
    escaped_search = normalized_search_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    search_like = f"%{escaped_search}%" if escaped_search else ""
    profile_search_expr = """
        LOWER(
            COALESCE(material_key, '') || ' ' ||
            COALESCE(material_id, '') || ' ' ||
            COALESCE(material_name, '') || ' ' ||
            COALESCE(video_id, '') || ' ' ||
            COALESCE(product_info_text, '') || ' ' ||
            COALESCE(top_anchor_name, '') || ' ' ||
            COALESCE(top_plan_name, '') || ' ' ||
            COALESCE(top_account_name, '') || ' ' ||
            COALESCE(aweme_item_id, '') || ' ' ||
            COALESCE(material_type, '') || ' ' ||
            COALESCE(product_names_json, '')
        )
    """
    search_cte_sql = ""
    search_join_sql = ""
    search_params: list[Any] = []
    if search_like:
        search_scope_sql = "COALESCE(customer_center_id, '') <> ''" if all_customer_centers else "customer_center_id = ?"
        search_params = [] if all_customer_centers else [service._current_customer_center_id()]
        search_params.append(search_like)
        search_cte_sql = f"""
        matching_materials AS (
            SELECT DISTINCT material_key
            FROM material_profile
            WHERE {search_scope_sql}
              AND {profile_search_expr} LIKE ? ESCAPE '\\'
        ),
        """
        search_join_sql = "INNER JOIN matching_materials mm ON mm.material_key = aggregated.material_key"
    prefix_start_day = (datetime.strptime(start_day, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d")
    prefix_day_count = (datetime.strptime(end_day, "%Y-%m-%d").date() - datetime.strptime(start_day, "%Y-%m-%d").date()).days + 1
    use_prefix_index = False
    prefix_table = conn.execute("SELECT to_regclass('public.material_ranking_day_prefix') AS name").fetchone()
    if (prefix_table or {}).get("name"):
        prefix_state = conn.execute(
            """
            SELECT
                EXISTS(
                    SELECT 1
                    FROM material_ranking_day_prefix
                    WHERE scope_key = ? AND day_key = ?
                    LIMIT 1
                ) AS has_end_day,
                (SELECT MIN(day_key) FROM material_ranking_day_prefix WHERE scope_key = ?) AS min_day,
                EXISTS(
                    SELECT 1
                    FROM material_ranking_day_prefix
                    WHERE scope_key = ? AND day_key = ?
                    LIMIT 1
                ) AS has_start_day
            """,
            [scope_key_value, end_day, scope_key_value, scope_key_value, prefix_start_day],
        ).fetchone()
        min_prefix_day = str((prefix_state or {}).get("min_day") or "").strip()
        use_prefix_index = bool(
            bool((prefix_state or {}).get("has_end_day"))
            and (
                bool((prefix_state or {}).get("has_start_day"))
                or (min_prefix_day and prefix_start_day < min_prefix_day)
            )
        )
    prefix_page_sql = f"""
    WITH end_rows AS (
        SELECT *
        FROM material_ranking_day_prefix
        WHERE scope_key = ?
          AND day_key = ?
    ),
    start_rows AS (
        SELECT *
        FROM material_ranking_day_prefix
        WHERE scope_key = ?
          AND day_key = ?
    ),
    {search_cte_sql}
    aggregated AS (
        SELECT
            e.material_key,
            e.snapshot_time,
            CAST(e.active_day_count - COALESCE(s.active_day_count, 0) AS INTEGER) AS active_day_count,
            CASE
                WHEN COALESCE(e.stat_cost - COALESCE(s.stat_cost, 0), 0) = 0
                 AND COALESCE(e.pay_amount - COALESCE(s.pay_amount, 0), 0) = 0
                 AND COALESCE(e.total_pay_amount - COALESCE(s.total_pay_amount, 0), 0) = 0
                 AND COALESCE(e.settled_pay_amount - COALESCE(s.settled_pay_amount, 0), 0) = 0
                 AND COALESCE(e.order_count - COALESCE(s.order_count, 0), 0) = 0
                 AND COALESCE(e.settled_order_count - COALESCE(s.settled_order_count, 0), 0) = 0
                 AND COALESCE(e.overall_show_count - COALESCE(s.overall_show_count, 0), 0) = 0
                 AND COALESCE(e.overall_click_count - COALESCE(s.overall_click_count, 0), 0) = 0
                 AND COALESCE(e.refund_amount_1h - COALESCE(s.refund_amount_1h, 0), 0) = 0
                THEN 1 ELSE 0
            END AS zero_bucket,
            CAST(ROUND((e.stat_cost - COALESCE(s.stat_cost, 0))::numeric, 2) AS DOUBLE PRECISION) AS stat_cost,
            CAST(ROUND((e.pay_amount - COALESCE(s.pay_amount, 0))::numeric, 2) AS DOUBLE PRECISION) AS pay_amount,
            CAST(ROUND((e.total_pay_amount - COALESCE(s.total_pay_amount, 0))::numeric, 2) AS DOUBLE PRECISION) AS total_pay_amount,
            CAST(ROUND((e.settled_pay_amount - COALESCE(s.settled_pay_amount, 0))::numeric, 2) AS DOUBLE PRECISION) AS settled_pay_amount,
            CAST(e.order_count - COALESCE(s.order_count, 0) AS INTEGER) AS order_count,
            CAST(e.settled_order_count - COALESCE(s.settled_order_count, 0) AS INTEGER) AS settled_order_count,
            CAST(e.overall_show_count - COALESCE(s.overall_show_count, 0) AS INTEGER) AS overall_show_count,
            CAST(e.overall_click_count - COALESCE(s.overall_click_count, 0) AS INTEGER) AS overall_click_count,
            CAST(ROUND((e.refund_amount_1h - COALESCE(s.refund_amount_1h, 0))::numeric, 2) AS DOUBLE PRECISION) AS refund_amount_1h,
            CAST(e.plan_count - COALESCE(s.plan_count, 0) AS INTEGER) AS plan_count,
            CAST(e.advertiser_count - COALESCE(s.advertiser_count, 0) AS INTEGER) AS advertiser_count
        FROM end_rows e
        LEFT JOIN start_rows s
          ON s.scope_key = e.scope_key
         AND s.material_key = e.material_key
    ),
    filtered AS (
        SELECT aggregated.*
        FROM aggregated
        {search_join_sql}
        WHERE active_day_count > 0
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
            CAST(COALESCE(SUM(plan_count), 0) AS INTEGER) AS aggregate_plan_count,
            CAST(COALESCE(SUM(advertiser_count), 0) AS INTEGER) AS aggregate_advertiser_count
        FROM filtered
    ),
    ranked AS (
        SELECT
            filtered.*,
            ROW_NUMBER() OVER (
                ORDER BY zero_bucket ASC, {metric_column} {metric_order}, material_key ASC
            ) AS rank_no
        FROM filtered
    ),
    paged AS (
        SELECT *
        FROM ranked
        WHERE rank_no > ?
          AND rank_no <= ?
    )
    SELECT
        COALESCE((SELECT MAX(snapshot_time) FROM filtered), '') AS latest_snapshot_time,
        ? AS snapshot_count,
        ? AS indexed_day_count,
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
        paged.material_key,
        paged.rank_no,
        paged.snapshot_time AS page_snapshot_time,
        paged.active_day_count AS page_active_day_count,
        paged.stat_cost AS page_stat_cost,
        paged.pay_amount AS page_pay_amount,
        paged.total_pay_amount AS page_total_pay_amount,
        paged.settled_pay_amount AS page_settled_pay_amount,
        paged.order_count AS page_order_count,
        paged.settled_order_count AS page_settled_order_count,
        paged.overall_show_count AS page_overall_show_count,
        paged.overall_click_count AS page_overall_click_count,
        paged.refund_amount_1h AS page_refund_amount_1h,
        paged.plan_count AS page_plan_count,
        paged.advertiser_count AS page_advertiser_count
    FROM summary
    LEFT JOIN paged ON TRUE
    ORDER BY paged.rank_no NULLS LAST
    """

    page_sql = f"""
    WITH daily_rows AS (
        SELECT
            start_date,
            material_key,
            snapshot_time,
            zero_bucket,
            stat_cost,
            pay_amount,
            total_pay_amount,
            settled_pay_amount,
            order_count,
            settled_order_count,
            overall_show_count,
            overall_click_count,
            refund_amount_1h,
            plan_count,
            advertiser_count
        FROM material_ranking_index
        WHERE scope_key = ?
          AND range_key = 'day'
          AND start_date = end_date
          AND start_date >= ?
          AND start_date <= ?
          AND sort_key = ?
          AND sort_dir = ?
    ),
    aggregated AS (
        SELECT
            material_key,
            MAX(snapshot_time) AS snapshot_time,
            CASE WHEN SUM(COALESCE(zero_bucket, 1)) = COUNT(*) THEN 1 ELSE 0 END AS zero_bucket,
            CAST(ROUND(COALESCE(SUM(stat_cost), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS stat_cost,
            CAST(ROUND(COALESCE(SUM(pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS pay_amount,
            CAST(ROUND(COALESCE(SUM(total_pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS total_pay_amount,
            CAST(ROUND(COALESCE(SUM(settled_pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS settled_pay_amount,
            CAST(COALESCE(SUM(order_count), 0) AS INTEGER) AS order_count,
            CAST(COALESCE(SUM(settled_order_count), 0) AS INTEGER) AS settled_order_count,
            CAST(COALESCE(SUM(overall_show_count), 0) AS INTEGER) AS overall_show_count,
            CAST(COALESCE(SUM(overall_click_count), 0) AS INTEGER) AS overall_click_count,
            CAST(ROUND(COALESCE(SUM(refund_amount_1h), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS refund_amount_1h,
            CAST(COALESCE(SUM(plan_count), 0) AS INTEGER) AS plan_count,
            CAST(COALESCE(SUM(advertiser_count), 0) AS INTEGER) AS advertiser_count
        FROM daily_rows
        GROUP BY material_key
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
            CAST(COALESCE(SUM(plan_count), 0) AS INTEGER) AS aggregate_plan_count,
            CAST(COALESCE(SUM(advertiser_count), 0) AS INTEGER) AS aggregate_advertiser_count
        FROM aggregated
    ),
    source_meta AS (
        SELECT
            COALESCE(MAX(snapshot_time), '') AS latest_snapshot_time,
            COUNT(DISTINCT snapshot_time) AS snapshot_count,
            COUNT(DISTINCT start_date) AS indexed_day_count
        FROM daily_rows
    ),
    ranked AS (
        SELECT
            material_key,
            ROW_NUMBER() OVER (
                ORDER BY zero_bucket ASC, {metric_column} {metric_order}, material_key ASC
            ) AS rank_no
        FROM aggregated
    ),
    paged AS (
        SELECT material_key, rank_no
        FROM ranked
        WHERE rank_no > ?
          AND rank_no <= ?
    )
    SELECT
        source_meta.latest_snapshot_time,
        source_meta.snapshot_count,
        source_meta.indexed_day_count,
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
        paged.material_key,
        paged.rank_no
    FROM summary
    CROSS JOIN source_meta
    LEFT JOIN paged ON TRUE
    ORDER BY paged.rank_no NULLS LAST
    """

    def run_page(page_value: int) -> list[dict[str, Any]]:
        start_index = max(page_value - 1, 0) * normalized_page_size
        if use_prefix_index:
            return [
                dict(row)
                for row in conn.execute(
                    prefix_page_sql,
                    [
                        scope_key_value,
                        end_day,
                        scope_key_value,
                        prefix_start_day,
                        *search_params,
                        start_index,
                        start_index + normalized_page_size,
                        prefix_day_count,
                        prefix_day_count,
                    ],
                ).fetchall()
            ]
        return [
            dict(row)
            for row in conn.execute(
                page_sql,
                [
                    scope_key_value,
                    start_day,
                    end_day,
                    normalized_sort_key,
                    normalized_sort_dir,
                    start_index,
                    start_index + normalized_page_size,
                ],
            ).fetchall()
        ]

    def empty_search_index_payload(summary_values: dict[str, Any], indexed_days: int) -> dict[str, Any]:
        source_name = "material_ranking_day_prefix" if use_prefix_index else "material_ranking_day_rollup"
        latest_snapshot_time = str(summary_values.get("latest_snapshot_time") or "").strip()
        payload = {
            "snapshot_time": latest_snapshot_time,
            "snapshot_count": int(summary_values.get("snapshot_count", 0) or 0),
            "items": [],
            "meta": service._material_meta_from_rows(
                [],
                latest_snapshot_time,
                material_count=0,
            ),
            "range_key": normalized,
            "range_label": range_label,
            "material_mode": "performance",
            "query_start_date": start_day,
            "query_end_date": end_day,
            "pagination": {
                "page": 1,
                "page_size": normalized_page_size,
                "total_count": 0,
                "total_pages": 1,
                "start_index": 0,
                "end_index": 0,
                "sort_key": normalized_sort_key,
                "sort_dir": normalized_sort_dir,
                "search": str(search_text or "").strip(),
            },
            "materials_aggregate": {
                "material_mode": "performance",
                "material_count": 0,
                "stat_cost": 0.0,
                "pay_amount": 0.0,
                "total_pay_amount": 0.0,
                "settled_pay_amount": 0.0,
                "order_count": 0,
                "settled_order_count": 0,
                "overall_show_count": 0,
                "overall_click_count": 0,
                "overall_ctr": 0.0,
                "roi": 0.0,
                "settled_roi": 0.0,
                "pay_order_cost": 0.0,
                "settled_amount_rate": 0.0,
                "refund_amount_1h": 0.0,
                "refund_rate_1h": 0.0,
                "plan_count": 0,
                "advertiser_count": 0,
                "summary_text": "total 0 materials",
            },
            "metrics_semantics": {
                "money_scope": "material_reuse_aggregation",
                "reconcilable_to_account_summary": False,
                "notice": "material performance uses daily prefix index for custom date range search",
            },
            "materialTodayStatus": service._material_today_hot_status(
                all_customer_centers=all_customer_centers,
            ),
            "ranking_index_used": True,
            "ranking_index_range_key": "day_prefix" if use_prefix_index else "day_rollup",
            "ranking_index_day_prefix_used": bool(use_prefix_index),
            "ranking_index_day_rollup_used": True,
            "ranking_index_day_rollup_days": int(indexed_days or 0),
        }
        return service._attach_freshness(
            payload,
            data_time=payload.get("snapshot_time"),
            synced_at=payload.get("snapshot_time"),
            source=source_name,
            partial=False,
        )

    query_rows = run_page(normalized_page)
    summary = dict(query_rows[0] or {}) if query_rows else {}
    total_count = int(summary.get("total_count", 0) or 0)
    indexed_day_count = int(summary.get("indexed_day_count", 0) or 0)
    if (total_count <= 0 or indexed_day_count <= 0) and use_prefix_index:
        use_prefix_index = False
        query_rows = run_page(normalized_page)
        summary = dict(query_rows[0] or {}) if query_rows else {}
        total_count = int(summary.get("total_count", 0) or 0)
        indexed_day_count = int(summary.get("indexed_day_count", 0) or 0)
    if total_count <= 0 or indexed_day_count <= 0:
        if normalized_search_text and use_prefix_index and indexed_day_count > 0:
            return empty_search_index_payload(summary, indexed_day_count)
        return None
    total_pages = max(1, (total_count + normalized_page_size - 1) // normalized_page_size)
    current_page = min(max(1, normalized_page), total_pages)
    if current_page != normalized_page:
        query_rows = run_page(current_page)
        summary = dict(query_rows[0] or {}) if query_rows else summary
    page_material_keys = [
        str(row.get("material_key") or "").strip()
        for row in query_rows
        if str(row.get("material_key") or "").strip()
    ]
    if not page_material_keys:
        return None

    if use_prefix_index:
        profile_placeholders = ",".join("?" for _ in page_material_keys)
        profile_where = [f"material_key IN ({profile_placeholders})"]
        profile_params: list[Any] = list(page_material_keys)
        if not all_customer_centers:
            profile_where.append("customer_center_id = ?")
            profile_params.append(service._current_customer_center_id())
        profile_rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM material_profile
                WHERE {' AND '.join(profile_where)}
                """,
                profile_params,
            ).fetchall()
        ]
        profile_by_key = {
            str(row.get("material_key") or "").strip(): row
            for row in profile_rows
            if str(row.get("material_key") or "").strip()
        }
        metric_by_key = {
            str(row.get("material_key") or "").strip(): dict(row)
            for row in query_rows
            if str(row.get("material_key") or "").strip()
        }
        latest_snapshot_time = str(summary.get("latest_snapshot_time") or "").strip()
        page_source_rows: list[dict[str, Any]] = []
        for material_key in page_material_keys:
            metric = metric_by_key.get(material_key) or {}
            profile = profile_by_key.get(material_key) or {}
            stat_cost = round(float(metric.get("page_stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(metric.get("page_pay_amount", 0.0) or 0.0), 2)
            total_pay_amount = round(float(metric.get("page_total_pay_amount", 0.0) or 0.0), 2)
            settled_pay_amount = round(float(metric.get("page_settled_pay_amount", 0.0) or 0.0), 2)
            order_count = int(metric.get("page_order_count", 0) or 0)
            settled_order_count = int(metric.get("page_settled_order_count", 0) or 0)
            overall_show_count = int(metric.get("page_overall_show_count", 0) or 0)
            overall_click_count = int(metric.get("page_overall_click_count", 0) or 0)
            refund_amount_1h = round(float(metric.get("page_refund_amount_1h", 0.0) or 0.0), 2)
            material_type = material_type_value(material_key, profile)
            page_source_rows.append(
                {
                    "customer_center_id": str(profile.get("customer_center_id") or service._current_customer_center_id()),
                    "snapshot_time": str(metric.get("page_snapshot_time") or latest_snapshot_time),
                    "source_day": end_day,
                    "window_start": f"{start_day} 00:00:00",
                    "window_end": f"{end_day} 23:59:59",
                    "material_key": material_key,
                    "material_id": str(profile.get("material_id") or ""),
                    "material_name": material_display_name_value(material_type, profile.get("material_name")),
                    "create_time": str(profile.get("create_time") or ""),
                    "material_type": material_type,
                    "video_id": str(profile.get("video_id") or ""),
                    "cover_url": str(profile.get("cover_url") or ""),
                    "aweme_item_id": str(profile.get("aweme_item_id") or ""),
                    "video_url": str(profile.get("video_url") or ""),
                    "stat_cost": stat_cost,
                    "pay_amount": pay_amount,
                    "total_pay_amount": total_pay_amount,
                    "settled_pay_amount": settled_pay_amount,
                    "order_count": order_count,
                    "settled_order_count": settled_order_count,
                    "plan_count": int(metric.get("page_plan_count", 0) or profile.get("plan_count", 0) or 0),
                    "advertiser_count": int(metric.get("page_advertiser_count", 0) or profile.get("advertiser_count", 0) or 0),
                    "plan_ids_json": str(profile.get("plan_ids_json") or "[]"),
                    "advertiser_ids_json": str(profile.get("advertiser_ids_json") or "[]"),
                    "is_original": int(profile.get("is_original", 0) or 0),
                    "top_plan_name": str(profile.get("top_plan_name") or ""),
                    "top_account_name": str(profile.get("top_account_name") or ""),
                    "top_anchor_name": str(profile.get("top_anchor_name") or ""),
                    "product_info_text": str(profile.get("product_info_text") or ""),
                    "product_names_json": str(profile.get("product_names_json") or "[]"),
                    "overall_show_count": overall_show_count,
                    "overall_click_count": overall_click_count,
                    "overall_ctr": round(overall_click_count / overall_show_count * 100.0, 2) if overall_show_count > 0 else 0.0,
                    "roi": round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                    "settled_roi": round(settled_pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                    "pay_order_cost": round(stat_cost / order_count, 2) if order_count > 0 else 0.0,
                    "settled_amount_rate": round(settled_pay_amount / total_pay_amount * 100.0, 2) if total_pay_amount > 0 else 0.0,
                    "refund_amount_1h": refund_amount_1h,
                    "refund_rate_1h": round(refund_amount_1h / total_pay_amount * 100.0, 2) if total_pay_amount > 0 else None,
                }
            )
        payload = service._build_material_payload_from_rows(
            conn,
            page_source_rows,
            latest_snapshot_time=latest_snapshot_time,
            all_customer_centers=all_customer_centers,
            meta_rows=page_source_rows,
            enrich_snapshot_context=False,
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
        start_index = (current_page - 1) * normalized_page_size
        payload["snapshot_time"] = latest_snapshot_time
        payload["snapshot_count"] = int(summary.get("snapshot_count", 0) or 0)
        payload["meta"] = service._material_meta_from_rows(
            list(page_items or []),
            latest_snapshot_time,
            material_count=total_count,
        )
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
            "sort_key": normalized_sort_key,
            "sort_dir": normalized_sort_dir,
            "search": str(search_text or "").strip(),
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
            "summary_text": f"total {total_count} materials",
        }
        payload["metrics_semantics"] = {
            "money_scope": "material_reuse_aggregation",
            "reconcilable_to_account_summary": False,
            "notice": "material performance uses daily prefix index for custom date ranges",
        }
        payload["materialTodayStatus"] = service._material_today_hot_status(
            all_customer_centers=all_customer_centers,
        )
        payload["ranking_index_used"] = True
        payload["ranking_index_range_key"] = "day_prefix"
        payload["ranking_index_day_prefix_used"] = True
        payload["ranking_index_day_rollup_used"] = True
        payload["ranking_index_day_rollup_days"] = indexed_day_count
        return service._attach_freshness(
            payload,
            data_time=payload.get("snapshot_time"),
            synced_at=payload.get("snapshot_time"),
            source="material_ranking_day_prefix",
            partial=False,
        )

    material_key_placeholders = ",".join("?" for _ in page_material_keys)
    today_key = datetime.now(ZoneInfo(str(tz_name or "Asia/Shanghai"))).strftime("%Y-%m-%d")
    daily_end_day = min(
        end_day,
        (datetime.strptime(today_key, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    page_source_queries: list[str] = []
    page_source_params: list[Any] = []
    if start_day <= daily_end_day:
        daily_where = [
            "md.biz_date >= ?",
            "md.biz_date <= ?",
            f"md.material_key IN ({material_key_placeholders})",
        ]
        page_source_params.extend([start_day, daily_end_day, *page_material_keys])
        if all_customer_centers:
            daily_where.append("COALESCE(md.customer_center_id, '') <> ''")
        else:
            daily_where.append("md.customer_center_id = ?")
            page_source_params.append(service._current_customer_center_id())
        page_source_queries.append(
            f"""
            SELECT
                md.customer_center_id,
                md.snapshot_time,
                md.biz_date AS source_day,
                md.window_start,
                md.window_end,
                md.material_key,
                md.material_id,
                md.material_name,
                md.create_time,
                md.material_type,
                md.video_id,
                md.cover_url,
                md.aweme_item_id,
                md.video_url,
                md.stat_cost,
                md.pay_amount,
                md.total_pay_amount,
                md.settled_pay_amount,
                md.order_count,
                md.settled_order_count,
                md.plan_count,
                md.advertiser_count,
                md.plan_ids_json,
                md.advertiser_ids_json,
                md.is_original,
                md.top_plan_name,
                md.top_account_name,
                md.top_anchor_name,
                md.product_info_text,
                md.product_names_json,
                md.overall_show_count,
                md.overall_click_count,
                md.overall_ctr,
                md.roi,
                md.settled_roi,
                md.pay_order_cost,
                md.settled_amount_rate,
                md.refund_amount_1h,
                md.refund_rate_1h
            FROM material_daily md
            WHERE {' AND '.join(daily_where)}
            """
        )
    if end_day >= today_key:
        current_where = [f"mc.material_key IN ({material_key_placeholders})"]
        page_source_params.extend(page_material_keys)
        if all_customer_centers:
            current_where.append("COALESCE(mc.customer_center_id, '') <> ''")
        else:
            current_where.append("mc.customer_center_id = ?")
            page_source_params.append(service._current_customer_center_id())
        page_source_queries.append(
            f"""
            SELECT
                mc.customer_center_id,
                mc.snapshot_time,
                substr(mc.snapshot_time, 1, 10) AS source_day,
                mc.window_start,
                mc.window_end,
                mc.material_key,
                mc.material_id,
                mc.material_name,
                mc.create_time,
                mc.material_type,
                mc.video_id,
                mc.cover_url,
                mc.aweme_item_id,
                mc.video_url,
                mc.stat_cost,
                mc.pay_amount,
                mc.total_pay_amount,
                mc.settled_pay_amount,
                mc.order_count,
                mc.settled_order_count,
                mc.plan_count,
                mc.advertiser_count,
                mc.plan_ids_json,
                mc.advertiser_ids_json,
                mc.is_original,
                mc.top_plan_name,
                mc.top_account_name,
                mc.top_anchor_name,
                mc.product_info_text,
                mc.product_names_json,
                mc.overall_show_count,
                mc.overall_click_count,
                mc.overall_ctr,
                mc.roi,
                mc.settled_roi,
                mc.pay_order_cost,
                mc.settled_amount_rate,
                mc.refund_amount_1h,
                mc.refund_rate_1h
            FROM material_current mc
            WHERE {' AND '.join(current_where)}
            """
        )
    page_source_rows = (
        [dict(row) for row in conn.execute(" UNION ALL ".join(page_source_queries), page_source_params).fetchall()]
        if page_source_queries
        else []
    )
    latest_snapshot_time = str(summary.get("latest_snapshot_time") or "").strip()
    payload = service._build_material_payload_from_rows(
        conn,
        page_source_rows,
        latest_snapshot_time=latest_snapshot_time,
        all_customer_centers=all_customer_centers,
        meta_rows=page_source_rows,
        enrich_snapshot_context=False,
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
    start_index = (current_page - 1) * normalized_page_size

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
        "sort_key": normalized_sort_key,
        "sort_dir": normalized_sort_dir,
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
        "summary_text": f"total {total_count} materials",
    }
    payload["metrics_semantics"] = {
        "money_scope": "material_reuse_aggregation",
        "reconcilable_to_account_summary": False,
        "notice": "material performance uses dynamic daily ranking index rollup for custom date ranges",
    }
    payload["materialTodayStatus"] = service._material_today_hot_status(
        all_customer_centers=all_customer_centers,
    )
    payload["ranking_index_used"] = True
    payload["ranking_index_range_key"] = "day_prefix" if use_prefix_index else "day_rollup"
    payload["ranking_index_day_prefix_used"] = bool(use_prefix_index)
    payload["ranking_index_day_rollup_used"] = True
    payload["ranking_index_day_rollup_days"] = indexed_day_count
    return service._attach_freshness(
        payload,
        data_time=payload.get("snapshot_time"),
        synced_at=payload.get("snapshot_time"),
        source="material_ranking_day_prefix" if use_prefix_index else "material_ranking_day_rollup",
        partial=False,
    )


def payload_from_current_index(
    service: Any,
    conn: Any,
    *,
    start_day: str,
    end_day: str,
    normalized: str,
    range_label: str,
    page: int,
    page_size: int,
    sort_key: str,
    sort_dir: str,
    tz_name: str,
    all_customer_centers: bool,
    search_text: str = "",
) -> dict[str, Any] | None:
    start_day = _date_key(start_day, "start_day")
    end_day = _date_key(end_day, "end_day")
    today_key = datetime.now(ZoneInfo(str(tz_name or "Asia/Shanghai"))).strftime("%Y-%m-%d")
    if not (start_day == today_key and end_day == today_key):
        return None

    normalized_sort_key = normalize_sort_key(sort_key)
    normalized_sort_dir = normalize_sort_dir(sort_dir)
    metric_column = {
        "stat_cost": "stat_cost",
        "total_pay_amount": "total_pay_amount",
        "settled_pay_amount": "settled_pay_amount",
        "pay_amount": "pay_amount",
        "order_count": "order_count",
    }.get(normalized_sort_key, "stat_cost")
    metric_order = "DESC" if normalized_sort_dir == "desc" else "ASC"
    normalized_page = max(int(page or 1), 1)
    normalized_page_size = max(int(page_size or DEFAULT_PAGE_SIZE), 1)
    current_scope_sql = "COALESCE(mc.customer_center_id, '') <> ''" if all_customer_centers else "mc.customer_center_id = ?"
    current_scope_params: list[Any] = [] if all_customer_centers else [service._current_customer_center_id()]
    normalized_search_text, search_cte_sql, search_params, current_search_join_sql = _material_profile_search_parts(
        service,
        all_customer_centers=all_customer_centers,
        search_text=search_text,
        join_target_expr="mc.material_key",
    )

    page_sql = f"""
    WITH {search_cte_sql}current_source AS (
        SELECT
            mc.material_key,
            MAX(mc.snapshot_time) AS snapshot_time,
            CAST(COALESCE(SUM(mc.plan_count), 0) AS INTEGER) AS plan_count,
            CAST(COALESCE(SUM(mc.advertiser_count), 0) AS INTEGER) AS advertiser_count,
            CAST(ROUND(COALESCE(SUM(mc.stat_cost), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS stat_cost,
            CAST(ROUND(COALESCE(SUM(mc.pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS pay_amount,
            CAST(ROUND(COALESCE(SUM(mc.total_pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS total_pay_amount,
            CAST(ROUND(COALESCE(SUM(mc.settled_pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS settled_pay_amount,
            CAST(COALESCE(SUM(mc.order_count), 0) AS INTEGER) AS order_count,
            CAST(COALESCE(SUM(mc.settled_order_count), 0) AS INTEGER) AS settled_order_count,
            CAST(COALESCE(SUM(mc.overall_show_count), 0) AS INTEGER) AS overall_show_count,
            CAST(COALESCE(SUM(mc.overall_click_count), 0) AS INTEGER) AS overall_click_count,
            CAST(ROUND(COALESCE(SUM(mc.refund_amount_1h), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS refund_amount_1h
        FROM material_current mc
        {current_search_join_sql}
        WHERE {current_scope_sql}
        GROUP BY mc.material_key
    ),
    prepared AS (
        SELECT
            current_source.*,
            {zero_bucket_sql("current_source")} AS zero_bucket
        FROM current_source
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
            CAST(COALESCE(SUM(plan_count), 0) AS INTEGER) AS aggregate_plan_count,
            CAST(COALESCE(SUM(advertiser_count), 0) AS INTEGER) AS aggregate_advertiser_count
        FROM prepared
    ),
    ranked AS (
        SELECT
            prepared.*,
            ROW_NUMBER() OVER (
                ORDER BY zero_bucket ASC, {metric_column} {metric_order}, material_key ASC
            ) AS rank_no
        FROM prepared
    ),
    paged AS (
        SELECT *
        FROM ranked
        WHERE rank_no > ?
          AND rank_no <= ?
    )
    SELECT
        COALESCE((SELECT MAX(snapshot_time) FROM prepared), '') AS latest_snapshot_time,
        1 AS snapshot_count,
        1 AS indexed_day_count,
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
        paged.material_key,
        paged.rank_no,
        paged.snapshot_time AS page_snapshot_time,
        1 AS page_active_day_count,
        paged.stat_cost AS page_stat_cost,
        paged.pay_amount AS page_pay_amount,
        paged.total_pay_amount AS page_total_pay_amount,
        paged.settled_pay_amount AS page_settled_pay_amount,
        paged.order_count AS page_order_count,
        paged.settled_order_count AS page_settled_order_count,
        paged.overall_show_count AS page_overall_show_count,
        paged.overall_click_count AS page_overall_click_count,
        paged.refund_amount_1h AS page_refund_amount_1h,
        paged.plan_count AS page_plan_count,
        paged.advertiser_count AS page_advertiser_count
    FROM summary
    LEFT JOIN paged ON TRUE
    ORDER BY paged.rank_no NULLS LAST
    """

    start_index = max(normalized_page - 1, 0) * normalized_page_size
    query_rows = [
        dict(row)
        for row in conn.execute(
            page_sql,
            [
                *search_params,
                *current_scope_params,
                start_index,
                start_index + normalized_page_size,
            ],
        ).fetchall()
    ]
    summary = dict(query_rows[0] or {}) if query_rows else {}
    total_count = int(summary.get("total_count", 0) or 0)
    if total_count <= 0:
        if normalized_search_text:
            latest_snapshot_time = str(summary.get("latest_snapshot_time") or "").strip()
            return _empty_material_index_payload(
                service,
                latest_snapshot_time=latest_snapshot_time,
                normalized=normalized,
                range_label=range_label,
                start_day=today_key,
                end_day=today_key,
                normalized_page_size=normalized_page_size,
                normalized_sort_key=normalized_sort_key,
                normalized_sort_dir=normalized_sort_dir,
                search_text=search_text,
                ranking_index_range_key="current_live",
                freshness_source="material_current_index",
                freshness_notice="material performance uses material_current live index for today",
                all_customer_centers=all_customer_centers,
                day_prefix_used=False,
                day_rollup_used=False,
                live_overlay_used=True,
            )
        return None
    total_pages = max(1, (total_count + normalized_page_size - 1) // normalized_page_size)
    current_page = min(max(1, normalized_page), total_pages)
    if current_page != normalized_page:
        return payload_from_current_index(
            service,
            conn,
            start_day=start_day,
            end_day=end_day,
            normalized=normalized,
            range_label=range_label,
            page=current_page,
            page_size=normalized_page_size,
            sort_key=normalized_sort_key,
            sort_dir=normalized_sort_dir,
            tz_name=tz_name,
            all_customer_centers=all_customer_centers,
            search_text=search_text,
        )

    page_material_keys = [
        str(row.get("material_key") or "").strip()
        for row in query_rows
        if str(row.get("material_key") or "").strip()
    ]
    if not page_material_keys:
        return None

    profile_placeholders = ",".join("?" for _ in page_material_keys)
    profile_where = [f"material_key IN ({profile_placeholders})"]
    profile_params: list[Any] = list(page_material_keys)
    if not all_customer_centers:
        profile_where.append("customer_center_id = ?")
        profile_params.append(service._current_customer_center_id())
    profile_rows = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT DISTINCT ON (material_key) *
            FROM material_profile
            WHERE {' AND '.join(profile_where)}
            ORDER BY material_key, updated_at DESC
            """,
            profile_params,
        ).fetchall()
    ]
    profile_by_key = {
        str(row.get("material_key") or "").strip(): row
        for row in profile_rows
        if str(row.get("material_key") or "").strip()
    }
    metric_by_key = {
        str(row.get("material_key") or "").strip(): dict(row)
        for row in query_rows
        if str(row.get("material_key") or "").strip()
    }
    latest_snapshot_time = str(summary.get("latest_snapshot_time") or "").strip()
    page_source_rows: list[dict[str, Any]] = []
    for material_key in page_material_keys:
        metric = metric_by_key.get(material_key) or {}
        profile = profile_by_key.get(material_key) or {}
        stat_cost = round(float(metric.get("page_stat_cost", 0.0) or 0.0), 2)
        pay_amount = round(float(metric.get("page_pay_amount", 0.0) or 0.0), 2)
        total_pay_amount = round(float(metric.get("page_total_pay_amount", 0.0) or 0.0), 2)
        settled_pay_amount = round(float(metric.get("page_settled_pay_amount", 0.0) or 0.0), 2)
        order_count = int(metric.get("page_order_count", 0) or 0)
        settled_order_count = int(metric.get("page_settled_order_count", 0) or 0)
        overall_show_count = int(metric.get("page_overall_show_count", 0) or 0)
        overall_click_count = int(metric.get("page_overall_click_count", 0) or 0)
        refund_amount_1h = round(float(metric.get("page_refund_amount_1h", 0.0) or 0.0), 2)
        material_type = material_type_value(material_key, profile)
        page_source_rows.append(
            {
                "customer_center_id": str(profile.get("customer_center_id") or service._current_customer_center_id() or ""),
                "snapshot_time": str(metric.get("page_snapshot_time") or latest_snapshot_time),
                "source_day": today_key,
                "window_start": f"{today_key} 00:00:00",
                "window_end": f"{today_key} 23:59:59",
                "material_key": material_key,
                "material_id": str(profile.get("material_id") or ""),
                "material_name": material_display_name_value(material_type, profile.get("material_name")),
                "create_time": str(profile.get("create_time") or ""),
                "material_type": material_type,
                "video_id": str(profile.get("video_id") or ""),
                "cover_url": str(profile.get("cover_url") or ""),
                "aweme_item_id": str(profile.get("aweme_item_id") or ""),
                "video_url": str(profile.get("video_url") or ""),
                "stat_cost": stat_cost,
                "pay_amount": pay_amount,
                "total_pay_amount": total_pay_amount,
                "settled_pay_amount": settled_pay_amount,
                "order_count": order_count,
                "settled_order_count": settled_order_count,
                "plan_count": int(metric.get("page_plan_count", 0) or profile.get("plan_count", 0) or 0),
                "advertiser_count": int(metric.get("page_advertiser_count", 0) or profile.get("advertiser_count", 0) or 0),
                "plan_ids_json": str(profile.get("plan_ids_json") or "[]"),
                "advertiser_ids_json": str(profile.get("advertiser_ids_json") or "[]"),
                "is_original": int(profile.get("is_original", 0) or 0),
                "top_plan_name": str(profile.get("top_plan_name") or ""),
                "top_account_name": str(profile.get("top_account_name") or ""),
                "top_anchor_name": str(profile.get("top_anchor_name") or ""),
                "product_info_text": str(profile.get("product_info_text") or ""),
                "product_names_json": str(profile.get("product_names_json") or "[]"),
                "overall_show_count": overall_show_count,
                "overall_click_count": overall_click_count,
                "overall_ctr": round(overall_click_count / overall_show_count * 100.0, 2) if overall_show_count > 0 else 0.0,
                "roi": round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                "settled_roi": round(settled_pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                "pay_order_cost": round(stat_cost / order_count, 2) if order_count > 0 else 0.0,
                "settled_amount_rate": round(settled_pay_amount / total_pay_amount * 100.0, 2) if total_pay_amount > 0 else 0.0,
                "refund_amount_1h": refund_amount_1h,
                "refund_rate_1h": round(refund_amount_1h / total_pay_amount * 100.0, 2) if total_pay_amount > 0 else None,
            }
        )

    payload = service._build_material_payload_from_rows(
        conn,
        page_source_rows,
        latest_snapshot_time=latest_snapshot_time,
        all_customer_centers=all_customer_centers,
        meta_rows=page_source_rows,
        enrich_snapshot_context=False,
        query_context_ready=True,
    )
    key_order = {key: index for index, key in enumerate(page_material_keys)}
    items = service._sanitize_material_preview_fields_for_payload(
        service._apply_latest_material_previews(conn, payload.get("items") or [])
    )
    items = [dict(item or {}) for item in items]
    items.sort(key=lambda item: key_order.get(str(item.get("material_key") or "").strip(), len(key_order)))
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
    payload["snapshot_time"] = latest_snapshot_time
    payload["snapshot_count"] = 1
    payload["meta"] = service._material_meta_from_rows(list(payload.get("items") or []), latest_snapshot_time, material_count=total_count)
    payload["range_key"] = normalized
    payload["range_label"] = range_label
    payload["material_mode"] = "performance"
    payload["query_start_date"] = today_key
    payload["query_end_date"] = today_key
    payload["pagination"] = {
        "page": current_page,
        "page_size": normalized_page_size,
        "total_count": total_count,
        "total_pages": total_pages,
        "start_index": start_index + 1 if total_count > 0 else 0,
        "end_index": start_index + len(items),
        "sort_key": normalized_sort_key,
        "sort_dir": normalized_sort_dir,
        "search": str(search_text or "").strip(),
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
        "summary_text": f"total {total_count} materials",
    }
    payload["metrics_semantics"] = {
        "money_scope": "material_reuse_aggregation",
        "reconcilable_to_account_summary": False,
        "notice": "material performance uses material_current live index for today",
    }
    payload["materialTodayStatus"] = service._material_today_hot_status(
        all_customer_centers=all_customer_centers,
    )
    payload["ranking_index_used"] = True
    payload["ranking_index_range_key"] = "current_live"
    payload["ranking_index_live_overlay_used"] = True
    payload["ranking_index_day_prefix_used"] = False
    payload["ranking_index_day_rollup_used"] = False
    return service._attach_freshness(
        payload,
        data_time=payload.get("snapshot_time"),
        synced_at=payload.get("snapshot_time"),
        source="material_current_index",
        partial=False,
    )


def payload_from_live_overlay_index(
    service: Any,
    conn: Any,
    *,
    scope_key_value: str,
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
    search_text: str = "",
) -> dict[str, Any] | None:
    start_day = _date_key(start_day, "start_day")
    end_day = _date_key(end_day, "end_day")
    if start_day > end_day:
        start_day, end_day = end_day, start_day
    today_key = datetime.now(ZoneInfo(str(tz_name or "Asia/Shanghai"))).strftime("%Y-%m-%d")
    if not (start_day < today_key <= end_day):
        return None
    history_end_day = min(
        end_day,
        (datetime.strptime(today_key, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    if start_day > history_end_day:
        return None

    normalized_sort_key = normalize_sort_key(sort_key)
    normalized_sort_dir = normalize_sort_dir(sort_dir)
    metric_column = {
        "stat_cost": "stat_cost",
        "total_pay_amount": "total_pay_amount",
        "settled_pay_amount": "settled_pay_amount",
        "pay_amount": "pay_amount",
        "order_count": "order_count",
    }.get(normalized_sort_key, "stat_cost")
    metric_order = "DESC" if normalized_sort_dir == "desc" else "ASC"
    normalized_page = max(int(page or 1), 1)
    normalized_page_size = max(int(page_size or DEFAULT_PAGE_SIZE), 1)
    history_day_count = (
        datetime.strptime(history_end_day, "%Y-%m-%d").date() - datetime.strptime(start_day, "%Y-%m-%d").date()
    ).days + 1
    current_scope_sql = "COALESCE(mc.customer_center_id, '') <> ''" if all_customer_centers else "mc.customer_center_id = ?"
    current_scope_params: list[Any] = [] if all_customer_centers else [service._current_customer_center_id()]
    normalized_search_text, search_cte_sql, search_params, search_join_sql = _material_profile_search_parts(
        service,
        all_customer_centers=all_customer_centers,
        search_text=search_text,
        join_target_expr="prepared.material_key",
    )

    use_prefix_index = False
    prefix_start_day = (datetime.strptime(start_day, "%Y-%m-%d").date() - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        use_prefix_index, prefix_start_day, _ = service._material_prefix_window_ready(
            conn,
            scope_key_value=scope_key_value,
            start_day=start_day,
            end_day=history_end_day,
        )
    except Exception:
        use_prefix_index = False

    prefix_overlay_sql = f"""
    WITH end_rows AS (
        SELECT *
        FROM material_ranking_day_prefix
        WHERE scope_key = ?
          AND day_key = ?
    ),
    start_rows AS (
        SELECT *
        FROM material_ranking_day_prefix
        WHERE scope_key = ?
          AND day_key = ?
    ),
    {search_cte_sql}
    history_metrics AS (
        SELECT
            e.material_key,
            e.snapshot_time,
            CAST(e.active_day_count - COALESCE(s.active_day_count, 0) AS INTEGER) AS active_day_count,
            CAST(ROUND((e.stat_cost - COALESCE(s.stat_cost, 0))::numeric, 2) AS DOUBLE PRECISION) AS stat_cost,
            CAST(ROUND((e.pay_amount - COALESCE(s.pay_amount, 0))::numeric, 2) AS DOUBLE PRECISION) AS pay_amount,
            CAST(ROUND((e.total_pay_amount - COALESCE(s.total_pay_amount, 0))::numeric, 2) AS DOUBLE PRECISION) AS total_pay_amount,
            CAST(ROUND((e.settled_pay_amount - COALESCE(s.settled_pay_amount, 0))::numeric, 2) AS DOUBLE PRECISION) AS settled_pay_amount,
            CAST(e.order_count - COALESCE(s.order_count, 0) AS INTEGER) AS order_count,
            CAST(e.settled_order_count - COALESCE(s.settled_order_count, 0) AS INTEGER) AS settled_order_count,
            CAST(e.overall_show_count - COALESCE(s.overall_show_count, 0) AS INTEGER) AS overall_show_count,
            CAST(e.overall_click_count - COALESCE(s.overall_click_count, 0) AS INTEGER) AS overall_click_count,
            CAST(ROUND((e.refund_amount_1h - COALESCE(s.refund_amount_1h, 0))::numeric, 2) AS DOUBLE PRECISION) AS refund_amount_1h,
            CAST(e.plan_count - COALESCE(s.plan_count, 0) AS INTEGER) AS plan_count,
            CAST(e.advertiser_count - COALESCE(s.advertiser_count, 0) AS INTEGER) AS advertiser_count
        FROM end_rows e
        LEFT JOIN start_rows s
          ON s.scope_key = e.scope_key
         AND s.material_key = e.material_key
        WHERE CAST(e.active_day_count - COALESCE(s.active_day_count, 0) AS INTEGER) > 0
    ),
    current_metrics AS (
        SELECT
            mc.material_key,
            mc.snapshot_time,
            1 AS active_day_count,
            CAST(ROUND(COALESCE(mc.stat_cost, 0.0)::numeric, 2) AS DOUBLE PRECISION) AS stat_cost,
            CAST(ROUND(COALESCE(mc.pay_amount, 0.0)::numeric, 2) AS DOUBLE PRECISION) AS pay_amount,
            CAST(ROUND(COALESCE(mc.total_pay_amount, 0.0)::numeric, 2) AS DOUBLE PRECISION) AS total_pay_amount,
            CAST(ROUND(COALESCE(mc.settled_pay_amount, 0.0)::numeric, 2) AS DOUBLE PRECISION) AS settled_pay_amount,
            CAST(COALESCE(mc.order_count, 0) AS INTEGER) AS order_count,
            CAST(COALESCE(mc.settled_order_count, 0) AS INTEGER) AS settled_order_count,
            CAST(COALESCE(mc.overall_show_count, 0) AS INTEGER) AS overall_show_count,
            CAST(COALESCE(mc.overall_click_count, 0) AS INTEGER) AS overall_click_count,
            CAST(ROUND(COALESCE(mc.refund_amount_1h, 0.0)::numeric, 2) AS DOUBLE PRECISION) AS refund_amount_1h,
            CAST(COALESCE(mc.plan_count, 0) AS INTEGER) AS plan_count,
            CAST(COALESCE(mc.advertiser_count, 0) AS INTEGER) AS advertiser_count
        FROM material_current mc
        WHERE {current_scope_sql}
    ),
    merged AS (
        SELECT
            COALESCE(h.material_key, c.material_key) AS material_key,
            CASE
                WHEN COALESCE(c.snapshot_time, '') > COALESCE(h.snapshot_time, '') THEN COALESCE(c.snapshot_time, '')
                ELSE COALESCE(h.snapshot_time, '')
            END AS snapshot_time,
            CAST(COALESCE(h.active_day_count, 0) + COALESCE(c.active_day_count, 0) AS INTEGER) AS active_day_count,
            CAST(ROUND((COALESCE(h.stat_cost, 0.0) + COALESCE(c.stat_cost, 0.0))::numeric, 2) AS DOUBLE PRECISION) AS stat_cost,
            CAST(ROUND((COALESCE(h.pay_amount, 0.0) + COALESCE(c.pay_amount, 0.0))::numeric, 2) AS DOUBLE PRECISION) AS pay_amount,
            CAST(ROUND((COALESCE(h.total_pay_amount, 0.0) + COALESCE(c.total_pay_amount, 0.0))::numeric, 2) AS DOUBLE PRECISION) AS total_pay_amount,
            CAST(ROUND((COALESCE(h.settled_pay_amount, 0.0) + COALESCE(c.settled_pay_amount, 0.0))::numeric, 2) AS DOUBLE PRECISION) AS settled_pay_amount,
            CAST(COALESCE(h.order_count, 0) + COALESCE(c.order_count, 0) AS INTEGER) AS order_count,
            CAST(COALESCE(h.settled_order_count, 0) + COALESCE(c.settled_order_count, 0) AS INTEGER) AS settled_order_count,
            CAST(COALESCE(h.overall_show_count, 0) + COALESCE(c.overall_show_count, 0) AS INTEGER) AS overall_show_count,
            CAST(COALESCE(h.overall_click_count, 0) + COALESCE(c.overall_click_count, 0) AS INTEGER) AS overall_click_count,
            CAST(ROUND((COALESCE(h.refund_amount_1h, 0.0) + COALESCE(c.refund_amount_1h, 0.0))::numeric, 2) AS DOUBLE PRECISION) AS refund_amount_1h,
            CAST(COALESCE(h.plan_count, 0) + COALESCE(c.plan_count, 0) AS INTEGER) AS plan_count,
            CAST(COALESCE(h.advertiser_count, 0) + COALESCE(c.advertiser_count, 0) AS INTEGER) AS advertiser_count
        FROM history_metrics h
        FULL OUTER JOIN current_metrics c
          ON c.material_key = h.material_key
    ),
    prepared AS (
        SELECT
            merged.*,
            {zero_bucket_sql("merged")} AS zero_bucket
        FROM merged
        WHERE COALESCE(merged.active_day_count, 0) > 0
    ),
    filtered AS (
        SELECT prepared.*
        FROM prepared
        {search_join_sql}
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
            CAST(COALESCE(SUM(plan_count), 0) AS INTEGER) AS aggregate_plan_count,
            CAST(COALESCE(SUM(advertiser_count), 0) AS INTEGER) AS aggregate_advertiser_count
        FROM filtered
    ),
    source_meta AS (
        SELECT
            COALESCE(MAX(snapshot_time), '') AS latest_snapshot_time,
            ? + CASE WHEN EXISTS(SELECT 1 FROM current_metrics) THEN 1 ELSE 0 END AS snapshot_count,
            ? + CASE WHEN EXISTS(SELECT 1 FROM current_metrics) THEN 1 ELSE 0 END AS indexed_day_count
        FROM filtered
    ),
    ranked AS (
        SELECT
            filtered.*,
            ROW_NUMBER() OVER (
                ORDER BY zero_bucket ASC, {metric_column} {metric_order}, material_key ASC
            ) AS rank_no
        FROM filtered
    ),
    paged AS (
        SELECT *
        FROM ranked
        WHERE rank_no > ?
          AND rank_no <= ?
    )
    SELECT
        source_meta.latest_snapshot_time,
        source_meta.snapshot_count,
        source_meta.indexed_day_count,
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
        paged.material_key,
        paged.rank_no,
        paged.snapshot_time AS page_snapshot_time,
        paged.active_day_count AS page_active_day_count,
        paged.stat_cost AS page_stat_cost,
        paged.pay_amount AS page_pay_amount,
        paged.total_pay_amount AS page_total_pay_amount,
        paged.settled_pay_amount AS page_settled_pay_amount,
        paged.order_count AS page_order_count,
        paged.settled_order_count AS page_settled_order_count,
        paged.overall_show_count AS page_overall_show_count,
        paged.overall_click_count AS page_overall_click_count,
        paged.refund_amount_1h AS page_refund_amount_1h,
        paged.plan_count AS page_plan_count,
        paged.advertiser_count AS page_advertiser_count
    FROM summary
    CROSS JOIN source_meta
    LEFT JOIN paged ON TRUE
    ORDER BY paged.rank_no NULLS LAST
    """

    rollup_overlay_sql = f"""
    WITH daily_rows AS (
        SELECT
            start_date,
            material_key,
            snapshot_time,
            zero_bucket,
            stat_cost,
            pay_amount,
            total_pay_amount,
            settled_pay_amount,
            order_count,
            settled_order_count,
            overall_show_count,
            overall_click_count,
            refund_amount_1h,
            plan_count,
            advertiser_count
        FROM material_ranking_index
        WHERE scope_key = ?
          AND range_key = 'day'
          AND start_date = end_date
          AND start_date >= ?
          AND start_date <= ?
          AND sort_key = ?
          AND sort_dir = ?
    ),
    {search_cte_sql}
    history_metrics AS (
        SELECT
            material_key,
            MAX(snapshot_time) AS snapshot_time,
            CAST(COUNT(*) AS INTEGER) AS active_day_count,
            CAST(ROUND(COALESCE(SUM(stat_cost), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS stat_cost,
            CAST(ROUND(COALESCE(SUM(pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS pay_amount,
            CAST(ROUND(COALESCE(SUM(total_pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS total_pay_amount,
            CAST(ROUND(COALESCE(SUM(settled_pay_amount), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS settled_pay_amount,
            CAST(COALESCE(SUM(order_count), 0) AS INTEGER) AS order_count,
            CAST(COALESCE(SUM(settled_order_count), 0) AS INTEGER) AS settled_order_count,
            CAST(COALESCE(SUM(overall_show_count), 0) AS INTEGER) AS overall_show_count,
            CAST(COALESCE(SUM(overall_click_count), 0) AS INTEGER) AS overall_click_count,
            CAST(ROUND(COALESCE(SUM(refund_amount_1h), 0.0)::numeric, 2) AS DOUBLE PRECISION) AS refund_amount_1h,
            CAST(COALESCE(SUM(plan_count), 0) AS INTEGER) AS plan_count,
            CAST(COALESCE(SUM(advertiser_count), 0) AS INTEGER) AS advertiser_count
        FROM daily_rows
        GROUP BY material_key
    ),
    current_metrics AS (
        SELECT
            mc.material_key,
            mc.snapshot_time,
            1 AS active_day_count,
            CAST(ROUND(COALESCE(mc.stat_cost, 0.0)::numeric, 2) AS DOUBLE PRECISION) AS stat_cost,
            CAST(ROUND(COALESCE(mc.pay_amount, 0.0)::numeric, 2) AS DOUBLE PRECISION) AS pay_amount,
            CAST(ROUND(COALESCE(mc.total_pay_amount, 0.0)::numeric, 2) AS DOUBLE PRECISION) AS total_pay_amount,
            CAST(ROUND(COALESCE(mc.settled_pay_amount, 0.0)::numeric, 2) AS DOUBLE PRECISION) AS settled_pay_amount,
            CAST(COALESCE(mc.order_count, 0) AS INTEGER) AS order_count,
            CAST(COALESCE(mc.settled_order_count, 0) AS INTEGER) AS settled_order_count,
            CAST(COALESCE(mc.overall_show_count, 0) AS INTEGER) AS overall_show_count,
            CAST(COALESCE(mc.overall_click_count, 0) AS INTEGER) AS overall_click_count,
            CAST(ROUND(COALESCE(mc.refund_amount_1h, 0.0)::numeric, 2) AS DOUBLE PRECISION) AS refund_amount_1h,
            CAST(COALESCE(mc.plan_count, 0) AS INTEGER) AS plan_count,
            CAST(COALESCE(mc.advertiser_count, 0) AS INTEGER) AS advertiser_count
        FROM material_current mc
        WHERE {current_scope_sql}
    ),
    merged AS (
        SELECT
            COALESCE(h.material_key, c.material_key) AS material_key,
            CASE
                WHEN COALESCE(c.snapshot_time, '') > COALESCE(h.snapshot_time, '') THEN COALESCE(c.snapshot_time, '')
                ELSE COALESCE(h.snapshot_time, '')
            END AS snapshot_time,
            CAST(COALESCE(h.active_day_count, 0) + COALESCE(c.active_day_count, 0) AS INTEGER) AS active_day_count,
            CAST(ROUND((COALESCE(h.stat_cost, 0.0) + COALESCE(c.stat_cost, 0.0))::numeric, 2) AS DOUBLE PRECISION) AS stat_cost,
            CAST(ROUND((COALESCE(h.pay_amount, 0.0) + COALESCE(c.pay_amount, 0.0))::numeric, 2) AS DOUBLE PRECISION) AS pay_amount,
            CAST(ROUND((COALESCE(h.total_pay_amount, 0.0) + COALESCE(c.total_pay_amount, 0.0))::numeric, 2) AS DOUBLE PRECISION) AS total_pay_amount,
            CAST(ROUND((COALESCE(h.settled_pay_amount, 0.0) + COALESCE(c.settled_pay_amount, 0.0))::numeric, 2) AS DOUBLE PRECISION) AS settled_pay_amount,
            CAST(COALESCE(h.order_count, 0) + COALESCE(c.order_count, 0) AS INTEGER) AS order_count,
            CAST(COALESCE(h.settled_order_count, 0) + COALESCE(c.settled_order_count, 0) AS INTEGER) AS settled_order_count,
            CAST(COALESCE(h.overall_show_count, 0) + COALESCE(c.overall_show_count, 0) AS INTEGER) AS overall_show_count,
            CAST(COALESCE(h.overall_click_count, 0) + COALESCE(c.overall_click_count, 0) AS INTEGER) AS overall_click_count,
            CAST(ROUND((COALESCE(h.refund_amount_1h, 0.0) + COALESCE(c.refund_amount_1h, 0.0))::numeric, 2) AS DOUBLE PRECISION) AS refund_amount_1h,
            CAST(COALESCE(h.plan_count, 0) + COALESCE(c.plan_count, 0) AS INTEGER) AS plan_count,
            CAST(COALESCE(h.advertiser_count, 0) + COALESCE(c.advertiser_count, 0) AS INTEGER) AS advertiser_count
        FROM history_metrics h
        FULL OUTER JOIN current_metrics c
          ON c.material_key = h.material_key
    ),
    prepared AS (
        SELECT
            merged.*,
            {zero_bucket_sql("merged")} AS zero_bucket
        FROM merged
        WHERE COALESCE(merged.active_day_count, 0) > 0
    ),
    filtered AS (
        SELECT prepared.*
        FROM prepared
        {search_join_sql}
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
            CAST(COALESCE(SUM(plan_count), 0) AS INTEGER) AS aggregate_plan_count,
            CAST(COALESCE(SUM(advertiser_count), 0) AS INTEGER) AS aggregate_advertiser_count
        FROM filtered
    ),
    source_meta AS (
        SELECT
            COALESCE(MAX(snapshot_time), '') AS latest_snapshot_time,
            (SELECT COUNT(DISTINCT start_date) FROM daily_rows) + CASE WHEN EXISTS(SELECT 1 FROM current_metrics) THEN 1 ELSE 0 END AS snapshot_count,
            (SELECT COUNT(DISTINCT start_date) FROM daily_rows) + CASE WHEN EXISTS(SELECT 1 FROM current_metrics) THEN 1 ELSE 0 END AS indexed_day_count
        FROM filtered
    ),
    ranked AS (
        SELECT
            filtered.*,
            ROW_NUMBER() OVER (
                ORDER BY zero_bucket ASC, {metric_column} {metric_order}, material_key ASC
            ) AS rank_no
        FROM filtered
    ),
    paged AS (
        SELECT *
        FROM ranked
        WHERE rank_no > ?
          AND rank_no <= ?
    )
    SELECT
        source_meta.latest_snapshot_time,
        source_meta.snapshot_count,
        source_meta.indexed_day_count,
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
        paged.material_key,
        paged.rank_no,
        paged.snapshot_time AS page_snapshot_time,
        paged.active_day_count AS page_active_day_count,
        paged.stat_cost AS page_stat_cost,
        paged.pay_amount AS page_pay_amount,
        paged.total_pay_amount AS page_total_pay_amount,
        paged.settled_pay_amount AS page_settled_pay_amount,
        paged.order_count AS page_order_count,
        paged.settled_order_count AS page_settled_order_count,
        paged.overall_show_count AS page_overall_show_count,
        paged.overall_click_count AS page_overall_click_count,
        paged.refund_amount_1h AS page_refund_amount_1h,
        paged.plan_count AS page_plan_count,
        paged.advertiser_count AS page_advertiser_count
    FROM summary
    CROSS JOIN source_meta
    LEFT JOIN paged ON TRUE
    ORDER BY paged.rank_no NULLS LAST
    """

    def run_overlay_page(page_value: int) -> list[dict[str, Any]]:
        start_index = max(page_value - 1, 0) * normalized_page_size
        if use_prefix_index:
            return [
                dict(row)
                for row in conn.execute(
                    prefix_overlay_sql,
                    [
                        scope_key_value,
                        history_end_day,
                        scope_key_value,
                        prefix_start_day,
                        *search_params,
                        *current_scope_params,
                        history_day_count,
                        history_day_count,
                        start_index,
                        start_index + normalized_page_size,
                    ],
                ).fetchall()
            ]
        return [
            dict(row)
            for row in conn.execute(
                rollup_overlay_sql,
                [
                    scope_key_value,
                    start_day,
                    history_end_day,
                    normalized_sort_key,
                    normalized_sort_dir,
                    *search_params,
                    *current_scope_params,
                    start_index,
                    start_index + normalized_page_size,
                ],
            ).fetchall()
        ]

    query_rows = run_overlay_page(normalized_page)
    summary = dict(query_rows[0] or {}) if query_rows else {}
    total_count = int(summary.get("total_count", 0) or 0)
    indexed_day_count = int(summary.get("indexed_day_count", 0) or 0)
    expected_indexed_day_count = history_day_count + 1
    if indexed_day_count < expected_indexed_day_count:
        return None
    if total_count <= 0:
        if normalized_search_text:
            latest_snapshot_time = str(summary.get("latest_snapshot_time") or "").strip()
            return _empty_material_index_payload(
                service,
                latest_snapshot_time=latest_snapshot_time,
                normalized=normalized,
                range_label=range_label,
                start_day=start_day,
                end_day=end_day,
                normalized_page_size=normalized_page_size,
                normalized_sort_key=normalized_sort_key,
                normalized_sort_dir=normalized_sort_dir,
                search_text=search_text,
                ranking_index_range_key="day_prefix_live" if use_prefix_index else "day_rollup_live",
                freshness_source="material_ranking_day_prefix_live" if use_prefix_index else "material_ranking_day_rollup_live",
                freshness_notice="material performance uses historical prefix plus live current overlay",
                all_customer_centers=all_customer_centers,
                day_prefix_used=bool(use_prefix_index),
                day_rollup_used=True,
                live_overlay_used=True,
            )
        return None

    total_pages = max(1, (total_count + normalized_page_size - 1) // normalized_page_size)
    current_page = min(max(1, normalized_page), total_pages)
    if current_page != normalized_page:
        query_rows = run_overlay_page(current_page)
        summary = dict(query_rows[0] or {}) if query_rows else summary

    page_material_keys = [
        str(row.get("material_key") or "").strip()
        for row in query_rows
        if str(row.get("material_key") or "").strip()
    ]
    if not page_material_keys:
        return None

    profile_placeholders = ",".join("?" for _ in page_material_keys)
    profile_where = [f"material_key IN ({profile_placeholders})"]
    profile_params: list[Any] = list(page_material_keys)
    if not all_customer_centers:
        profile_where.append("customer_center_id = ?")
        profile_params.append(service._current_customer_center_id())
    profile_rows = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT DISTINCT ON (material_key) *
            FROM material_profile
            WHERE {' AND '.join(profile_where)}
            ORDER BY material_key, updated_at DESC
            """,
            profile_params,
        ).fetchall()
    ]
    profile_by_key = {
        str(row.get("material_key") or "").strip(): row
        for row in profile_rows
        if str(row.get("material_key") or "").strip()
    }
    metric_by_key = {
        str(row.get("material_key") or "").strip(): dict(row)
        for row in query_rows
        if str(row.get("material_key") or "").strip()
    }
    latest_snapshot_time = str(summary.get("latest_snapshot_time") or "").strip()
    page_source_rows: list[dict[str, Any]] = []
    for material_key in page_material_keys:
        metric = metric_by_key.get(material_key) or {}
        profile = profile_by_key.get(material_key) or {}
        stat_cost = round(float(metric.get("page_stat_cost", 0.0) or 0.0), 2)
        pay_amount = round(float(metric.get("page_pay_amount", 0.0) or 0.0), 2)
        total_pay_amount = round(float(metric.get("page_total_pay_amount", 0.0) or 0.0), 2)
        settled_pay_amount = round(float(metric.get("page_settled_pay_amount", 0.0) or 0.0), 2)
        order_count = int(metric.get("page_order_count", 0) or 0)
        settled_order_count = int(metric.get("page_settled_order_count", 0) or 0)
        overall_show_count = int(metric.get("page_overall_show_count", 0) or 0)
        overall_click_count = int(metric.get("page_overall_click_count", 0) or 0)
        refund_amount_1h = round(float(metric.get("page_refund_amount_1h", 0.0) or 0.0), 2)
        material_type = material_type_value(material_key, profile)
        page_source_rows.append(
            {
                "customer_center_id": str(profile.get("customer_center_id") or service._current_customer_center_id() or ""),
                "snapshot_time": str(metric.get("page_snapshot_time") or latest_snapshot_time),
                "source_day": end_day,
                "window_start": f"{start_day} 00:00:00",
                "window_end": f"{end_day} 23:59:59",
                "material_key": material_key,
                "material_id": str(profile.get("material_id") or ""),
                "material_name": material_display_name_value(material_type, profile.get("material_name")),
                "create_time": str(profile.get("create_time") or ""),
                "material_type": material_type,
                "video_id": str(profile.get("video_id") or ""),
                "cover_url": str(profile.get("cover_url") or ""),
                "aweme_item_id": str(profile.get("aweme_item_id") or ""),
                "video_url": str(profile.get("video_url") or ""),
                "stat_cost": stat_cost,
                "pay_amount": pay_amount,
                "total_pay_amount": total_pay_amount,
                "settled_pay_amount": settled_pay_amount,
                "order_count": order_count,
                "settled_order_count": settled_order_count,
                "plan_count": int(metric.get("page_plan_count", 0) or profile.get("plan_count", 0) or 0),
                "advertiser_count": int(metric.get("page_advertiser_count", 0) or profile.get("advertiser_count", 0) or 0),
                "plan_ids_json": str(profile.get("plan_ids_json") or "[]"),
                "advertiser_ids_json": str(profile.get("advertiser_ids_json") or "[]"),
                "is_original": int(profile.get("is_original", 0) or 0),
                "top_plan_name": str(profile.get("top_plan_name") or ""),
                "top_account_name": str(profile.get("top_account_name") or ""),
                "top_anchor_name": str(profile.get("top_anchor_name") or ""),
                "product_info_text": str(profile.get("product_info_text") or ""),
                "product_names_json": str(profile.get("product_names_json") or "[]"),
                "overall_show_count": overall_show_count,
                "overall_click_count": overall_click_count,
                "overall_ctr": round(overall_click_count / overall_show_count * 100.0, 2) if overall_show_count > 0 else 0.0,
                "roi": round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                "settled_roi": round(settled_pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
                "pay_order_cost": round(stat_cost / order_count, 2) if order_count > 0 else 0.0,
                "settled_amount_rate": round(settled_pay_amount / total_pay_amount * 100.0, 2) if total_pay_amount > 0 else 0.0,
                "refund_amount_1h": refund_amount_1h,
                "refund_rate_1h": round(refund_amount_1h / total_pay_amount * 100.0, 2) if total_pay_amount > 0 else None,
            }
        )

    payload = service._build_material_payload_from_rows(
        conn,
        page_source_rows,
        latest_snapshot_time=latest_snapshot_time,
        all_customer_centers=all_customer_centers,
        meta_rows=page_source_rows,
        enrich_snapshot_context=False,
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
    start_index = (current_page - 1) * normalized_page_size
    payload["snapshot_time"] = latest_snapshot_time
    payload["snapshot_count"] = int(summary.get("snapshot_count", 0) or 0)
    payload["meta"] = service._material_meta_from_rows(
        list(payload.get("items") or []),
        latest_snapshot_time,
        material_count=total_count,
    )
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
        "end_index": start_index + len(items),
        "sort_key": normalized_sort_key,
        "sort_dir": normalized_sort_dir,
        "search": str(search_text or "").strip(),
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
        "summary_text": f"total {total_count} materials",
    }
    payload["metrics_semantics"] = {
        "money_scope": "material_reuse_aggregation",
        "reconcilable_to_account_summary": False,
        "notice": "material performance uses historical prefix plus live current overlay",
    }
    payload["materialTodayStatus"] = service._material_today_hot_status(
        all_customer_centers=all_customer_centers,
    )
    payload["ranking_index_used"] = True
    payload["ranking_index_range_key"] = "day_prefix_live" if use_prefix_index else "day_rollup_live"
    payload["ranking_index_day_prefix_used"] = bool(use_prefix_index)
    payload["ranking_index_day_rollup_used"] = True
    payload["ranking_index_day_rollup_days"] = indexed_day_count
    payload["ranking_index_live_overlay_used"] = True
    return service._attach_freshness(
        payload,
        data_time=payload.get("snapshot_time"),
        synced_at=payload.get("snapshot_time"),
        source="material_ranking_day_prefix_live" if use_prefix_index else "material_ranking_day_rollup_live",
        partial=False,
    )
