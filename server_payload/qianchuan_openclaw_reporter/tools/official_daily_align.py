#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for candidate in (ROOT_DIR, TOOLS_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from dashboard.main import TIMEZONE, material_ranking_index, now_text, service  # noqa: E402
from report_qianchuan import AccountSummary, PlanSummary, dump_json, fetch_account_bundle  # noqa: E402


UNATTRIBUTED_PLAN_SOURCE = "OFFICIAL_ACCOUNT_RESIDUAL"
UNATTRIBUTED_PLAN_DELIVERY_TYPE = "UNATTRIBUTED"
UNATTRIBUTED_PLAN_NAME = "未归因关闭/暂停计划消耗"
UNATTRIBUTED_MATERIAL_TYPE = "UNATTRIBUTED_DELETED"
UNATTRIBUTED_MATERIAL_KEY_PREFIX = "__unattributed_deleted_material__"
UNATTRIBUTED_MATERIAL_NAME = UNATTRIBUTED_PLAN_NAME
UNATTRIBUTED_PRODUCT_INFO_TEXT = "official plan cost exceeds attributable material cost; source intentionally left blank"
MIN_RESIDUAL_STAT_COST = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "One-time official daily alignment. For each day/customer center, fetch the official "
            "account-plan-material set, replace local daily performance rows with that official set, "
            "refresh material history, add unattributed residual rows where the official account cost "
            "cannot be traced to returned plans/materials, and rebuild material indexes."
        )
    )
    parser.add_argument("--start-date", required=True, help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument(
        "--customer-center-id",
        action="append",
        default=[],
        help="Limit alignment to one or more customer_center_id values.",
    )
    parser.add_argument(
        "--skip-material",
        action="store_true",
        help="Only align account/plan/summary daily tables; skip material refresh and index rebuild.",
    )
    parser.add_argument(
        "--skip-title-video-alignment",
        action="store_true",
        help="Skip creative title/video alignment after material repair.",
    )
    parser.add_argument(
        "--prune-material-to-plan-daily",
        action="store_true",
        help=(
            "Delete material rows whose ad_id is not present in plan_daily. This is off by default "
            "because paused/deleted plans can disappear from plan_daily while official account cost remains."
        ),
    )
    parser.add_argument(
        "--material-collection-mode",
        default="full_snapshot",
        choices=("full_snapshot", "report_batch"),
        help="Primary material collection mode. full_snapshot falls back to report_batch on errors.",
    )
    parser.add_argument(
        "--allow-performance-errors",
        action="store_true",
        help="Write performance rows even when official collection reports account/plan errors.",
    )
    parser.add_argument(
        "--allow-material-errors",
        action="store_true",
        help="Continue after material refresh errors.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch official performance data and compare counts without writing local daily tables.",
    )
    parser.add_argument(
        "--result-out",
        default="official_daily_align_result.json",
        help="Output path for JSON result details.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop at the first failed day/customer center.",
    )
    return parser.parse_args()


def parse_day(value: str) -> date:
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def day_text(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def iter_days(start_day: date, end_day: date) -> list[str]:
    days: list[str] = []
    cursor = start_day
    while cursor <= end_day:
        days.append(day_text(cursor))
        cursor += timedelta(days=1)
    return days


def normalize_text_list(values: list[Any]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def load_runtime_timezone() -> str:
    try:
        config = service.read_config()
    except Exception:
        config = {}
    return str(config.get("timezone") or TIMEZONE or "Asia/Shanghai")


def resolve_customer_center_ids(requested_ids: list[str]) -> list[str]:
    requested = normalize_text_list(requested_ids)
    if requested:
        return requested
    bound_ids = normalize_text_list(service.bound_customer_center_ids())
    if bound_ids:
        return bound_ids
    current_customer_center_id = str(service._current_customer_center_id() or "").strip()
    return [current_customer_center_id] if current_customer_center_id else []


def scoped_timezone(customer_center_id: str) -> str:
    try:
        config = service._scoped_config_for_customer_center(customer_center_id)
    except Exception:
        config = {}
    return str(config.get("timezone") or load_runtime_timezone() or TIMEZONE)


def build_day_window(day_key: str, tz_name: str) -> tuple[datetime, datetime]:
    target_day = parse_day(day_key)
    tz = ZoneInfo(str(tz_name or TIMEZONE or "Asia/Shanghai"))
    start_dt = datetime(target_day.year, target_day.month, target_day.day, 0, 0, 0, tzinfo=tz)
    end_dt = datetime(target_day.year, target_day.month, target_day.day, 23, 59, 59, tzinfo=tz)
    return start_dt, end_dt


def row_count_and_cost(conn: Any, table: str, customer_center_id: str, day_key: str) -> dict[str, Any]:
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS row_count,
               COALESCE(SUM(stat_cost), 0) AS stat_cost,
               COALESCE(SUM(pay_amount), 0) AS pay_amount,
               COALESCE(SUM(order_count), 0) AS order_count
        FROM {table}
        WHERE customer_center_id = ?
          AND biz_date = ?
        """,
        (customer_center_id, day_key),
    ).fetchone()
    values = dict(row or {})
    return {
        "row_count": int(values.get("row_count", 0) or 0),
        "stat_cost": round(float(values.get("stat_cost", 0.0) or 0.0), 2),
        "pay_amount": round(float(values.get("pay_amount", 0.0) or 0.0), 2),
        "order_count": int(float(values.get("order_count", 0) or 0)),
    }


def performance_counts(conn: Any, customer_center_id: str, day_key: str) -> dict[str, Any]:
    summary_row = conn.execute(
        """
        SELECT account_count, plan_count, stat_cost, pay_amount, order_count, snapshot_time
        FROM summary_daily
        WHERE customer_center_id = ?
          AND biz_date = ?
        """,
        (customer_center_id, day_key),
    ).fetchone()
    summary = dict(summary_row or {})
    return {
        "summary_daily": {
            "account_count": int(summary.get("account_count", 0) or 0),
            "plan_count": int(summary.get("plan_count", 0) or 0),
            "stat_cost": round(float(summary.get("stat_cost", 0.0) or 0.0), 2),
            "pay_amount": round(float(summary.get("pay_amount", 0.0) or 0.0), 2),
            "order_count": int(float(summary.get("order_count", 0) or 0)),
            "snapshot_time": str(summary.get("snapshot_time") or ""),
        },
        "account_daily": row_count_and_cost(conn, "account_daily", customer_center_id, day_key),
        "plan_daily": row_count_and_cost(conn, "plan_daily", customer_center_id, day_key),
    }


def material_counts(conn: Any, customer_center_id: str, day_key: str) -> dict[str, Any]:
    daily = row_count_and_cost(conn, "material_daily", customer_center_id, day_key)
    relation = row_count_and_cost(conn, "material_relation_daily", customer_center_id, day_key)
    non_title_row = conn.execute(
        """
        SELECT COUNT(*) AS row_count,
               COALESCE(SUM(stat_cost), 0) AS stat_cost,
               COALESCE(SUM(pay_amount), 0) AS pay_amount,
               COALESCE(SUM(order_count), 0) AS order_count
        FROM material_relation_daily
        WHERE customer_center_id = ?
          AND biz_date = ?
          AND COALESCE(material_type, '') <> 'TITLE'
        """,
        (customer_center_id, day_key),
    ).fetchone()
    non_title = dict(non_title_row or {})
    snapshot_row = conn.execute(
        """
        SELECT COUNT(*) AS row_count,
               COALESCE(SUM(stat_cost), 0) AS stat_cost
        FROM material_snapshots
        WHERE customer_center_id = ?
          AND substr(snapshot_time, 1, 10) = ?
        """,
        (customer_center_id, day_key),
    ).fetchone()
    snapshots = dict(snapshot_row or {})
    return {
        "material_daily": daily,
        "material_relation_daily": relation,
        "material_relation_daily_non_title": {
            "row_count": int(non_title.get("row_count", 0) or 0),
            "stat_cost": round(float(non_title.get("stat_cost", 0.0) or 0.0), 2),
            "pay_amount": round(float(non_title.get("pay_amount", 0.0) or 0.0), 2),
            "order_count": int(float(non_title.get("order_count", 0) or 0)),
        },
        "material_snapshots": {
            "row_count": int(snapshots.get("row_count", 0) or 0),
            "stat_cost": round(float(snapshots.get("stat_cost", 0.0) or 0.0), 2),
        },
    }


def payload_error_count(payload: dict[str, Any]) -> int:
    errors = payload.get("errors") or {}
    if not isinstance(errors, dict):
        return 0
    return sum(len(errors.get(key) or []) for key in ("accounts", "plans", "balances"))


def money(value: Any) -> float:
    return round(float(value or 0.0), 2)


def int_metric(value: Any) -> int:
    return int(float(value or 0) or 0)


def synthetic_residual_ad_id(advertiser_id: int) -> int:
    return -abs(int(advertiser_id or 0))


def account_payload_has_performance(row: dict[str, Any]) -> bool:
    return abs(money(row.get("stat_cost"))) > 0.005 or abs(money(row.get("pay_amount"))) > 0.005 or int_metric(row.get("order_count")) != 0


def plan_rollups_by_advertiser(plan_rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    rollups: dict[int, dict[str, Any]] = {}
    for row in plan_rows:
        advertiser_id = int(row.get("advertiser_id", 0) or 0)
        if advertiser_id <= 0:
            continue
        bucket = rollups.setdefault(
            advertiser_id,
            {
                "stat_cost": 0.0,
                "pay_amount": 0.0,
                "total_pay_amount": 0.0,
                "settled_pay_amount": 0.0,
                "order_count": 0,
                "settled_order_count": 0,
                "refund_amount_1h": 0.0,
                "plan_count": 0,
            },
        )
        bucket["stat_cost"] = money(bucket["stat_cost"] + money(row.get("stat_cost")))
        bucket["pay_amount"] = money(bucket["pay_amount"] + money(row.get("pay_amount")))
        bucket["total_pay_amount"] = money(bucket["total_pay_amount"] + money(row.get("total_pay_amount")))
        bucket["settled_pay_amount"] = money(bucket["settled_pay_amount"] + money(row.get("settled_pay_amount")))
        bucket["order_count"] += int_metric(row.get("order_count"))
        bucket["settled_order_count"] += int_metric(row.get("settled_order_count"))
        bucket["refund_amount_1h"] = money(bucket["refund_amount_1h"] + money(row.get("refund_amount_1h")))
        bucket["plan_count"] += 1
    return rollups


def residual_plan_from_account(
    account: AccountSummary,
    *,
    residual_cost: float,
    residual_pay_amount: float,
    residual_total_pay_amount: float,
    residual_settled_pay_amount: float,
    residual_order_count: int,
    residual_settled_order_count: int,
    residual_refund_amount_1h: float,
) -> PlanSummary:
    stat_cost = max(money(residual_cost), 0.0)
    pay_amount = max(money(residual_pay_amount), 0.0)
    total_pay_amount = max(money(residual_total_pay_amount), pay_amount)
    settled_pay_amount = max(money(residual_settled_pay_amount), 0.0)
    order_count = max(int_metric(residual_order_count), 0)
    settled_order_count = max(int_metric(residual_settled_order_count), 0)
    refund_amount_1h = max(money(residual_refund_amount_1h), 0.0)
    return PlanSummary(
        advertiser_id=int(account.advertiser_id or 0),
        advertiser_name=str(account.advertiser_name or ""),
        ad_id=synthetic_residual_ad_id(int(account.advertiser_id or 0)),
        ad_name=UNATTRIBUTED_PLAN_NAME,
        product_id="",
        product_name="",
        anchor_name="",
        marketing_goal="",
        status="UNATTRIBUTED",
        opt_status="UNATTRIBUTED",
        roi_goal=0.0,
        stat_cost=stat_cost,
        roi=round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
        order_count=order_count,
        pay_amount=pay_amount,
        total_pay_amount=total_pay_amount,
        settled_pay_amount=settled_pay_amount,
        settled_roi=round(settled_pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0,
        settled_order_count=settled_order_count,
        pay_order_cost=round(stat_cost / order_count, 2) if order_count > 0 else 0.0,
        settled_amount_rate=round(settled_pay_amount / total_pay_amount * 100.0, 2) if total_pay_amount > 0 else 0.0,
        refund_rate_1h=round(refund_amount_1h / total_pay_amount * 100.0, 2) if total_pay_amount > 0 else 0.0,
        refund_amount_1h=refund_amount_1h,
        plan_source=UNATTRIBUTED_PLAN_SOURCE,
        plan_delivery_type=UNATTRIBUTED_PLAN_DELIVERY_TYPE,
    )


def fetch_official_account_summaries(
    customer_center_id: str,
    start_dt: datetime,
    end_dt: datetime,
) -> tuple[list[AccountSummary], list[dict[str, Any]], int]:
    scoped_config = service._scoped_config_for_customer_center(customer_center_id)
    client = service._build_scoped_customer_center_client(customer_center_id)
    accounts = client.list_accounts()
    if not accounts:
        return [], [{"stage": "account_list", "error": "official account list is empty"}], 0
    max_workers = max(1, int(scoped_config.get("max_workers", 6) or 6))
    summaries: list[AccountSummary] = []
    errors: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(accounts))) as pool:
        future_map = {
            pool.submit(fetch_account_bundle, client, item, start_dt, end_dt): item
            for item in accounts
        }
        for future in as_completed(future_map):
            item = future_map[future]
            advertiser_id = int(item.get("advertiser_id", 0) or 0)
            advertiser_name = str(item.get("advertiser_name") or f"advertiser_{advertiser_id}")
            try:
                summary = future.result()
            except Exception as exc:  # noqa: BLE001
                summary = AccountSummary(
                    advertiser_id=advertiser_id,
                    advertiser_name=advertiser_name,
                    stat_cost=0.0,
                    roi=0.0,
                    order_count=0,
                    pay_amount=0.0,
                    ok=False,
                    error=str(exc),
                )
            summaries.append(summary)
            if not bool(summary.ok):
                errors.append(
                    {
                        "stage": "account_summary",
                        "advertiser_id": int(summary.advertiser_id or advertiser_id),
                        "advertiser_name": str(summary.advertiser_name or advertiser_name),
                        "error": str(summary.error or "official account summary failed"),
                    }
                )
    summaries.sort(key=lambda item: (-float(item.stat_cost or 0.0), int(item.advertiser_id or 0)))
    return summaries, errors, len(accounts)


def apply_official_account_authority(
    payload: dict[str, Any],
    *,
    customer_center_id: str,
    start_dt: datetime,
    end_dt: datetime,
) -> dict[str, Any]:
    official_accounts, account_errors, listed_account_count = fetch_official_account_summaries(
        customer_center_id,
        start_dt,
        end_dt,
    )
    if not official_accounts:
        return {
            "applied": False,
            "account_count": 0,
            "account_error_count": len(account_errors),
            "errors": account_errors,
            "residual_plan_count": 0,
            "residual_stat_cost": 0.0,
            "negative_plan_delta_count": 0,
            "negative_plan_delta_stat_cost": 0.0,
        }

    original_plans = [dict(item) for item in (payload.get("plans") or [])]
    rollups = plan_rollups_by_advertiser(original_plans)
    residual_plans: list[PlanSummary] = []
    negative_deltas: list[dict[str, Any]] = []
    for account in official_accounts:
        if not bool(account.ok):
            continue
        advertiser_id = int(account.advertiser_id or 0)
        rollup = rollups.get(advertiser_id, {})
        residual_cost = money(account.stat_cost - money(rollup.get("stat_cost")))
        if residual_cost >= MIN_RESIDUAL_STAT_COST:
            residual_plans.append(
                residual_plan_from_account(
                    account,
                    residual_cost=residual_cost,
                    residual_pay_amount=money(account.pay_amount - money(rollup.get("pay_amount"))),
                    residual_total_pay_amount=money(account.total_pay_amount - money(rollup.get("total_pay_amount"))),
                    residual_settled_pay_amount=money(account.settled_pay_amount - money(rollup.get("settled_pay_amount"))),
                    residual_order_count=int_metric(account.order_count) - int_metric(rollup.get("order_count")),
                    residual_settled_order_count=int_metric(account.settled_order_count) - int_metric(rollup.get("settled_order_count")),
                    residual_refund_amount_1h=money(account.refund_amount_1h - money(rollup.get("refund_amount_1h"))),
                )
            )
        elif residual_cost <= -MIN_RESIDUAL_STAT_COST:
            negative_deltas.append(
                {
                    "advertiser_id": advertiser_id,
                    "advertiser_name": str(account.advertiser_name or ""),
                    "official_account_stat_cost": money(account.stat_cost),
                    "plan_stat_cost": money(rollup.get("stat_cost")),
                    "delta": residual_cost,
                }
            )

    account_rows = [asdict(item) for item in official_accounts]
    plan_rows = [*original_plans, *[asdict(item) for item in residual_plans]]
    ok_accounts = [dict(item) for item in account_rows if bool(item.get("ok", True))]
    total_cost = money(sum(money(item.get("stat_cost")) for item in ok_accounts))
    total_pay = money(sum(money(item.get("pay_amount")) for item in ok_accounts))
    total_orders = sum(int_metric(item.get("order_count")) for item in ok_accounts)
    active_accounts = sum(1 for item in ok_accounts if account_payload_has_performance(item))
    active_plans = sum(1 for item in plan_rows if abs(money(item.get("stat_cost"))) > 0.005)
    payload["accounts"] = account_rows
    payload["plans"] = sorted(
        plan_rows,
        key=lambda item: (
            -int_metric(item.get("order_count")),
            -money(item.get("pay_amount")),
            -money(item.get("stat_cost")),
            int(item.get("ad_id", 0) or 0),
        ),
    )
    payload["summary"] = {
        **dict(payload.get("summary") or {}),
        "account_count": listed_account_count or len(account_rows),
        "active_account_count": active_accounts,
        "plan_count": len(plan_rows),
        "active_plan_count": active_plans,
        "stat_cost": total_cost,
        "pay_amount": total_pay,
        "order_count": total_orders,
        "roi": round(total_pay / total_cost, 2) if total_cost > 0 else 0.0,
        "account_failures": len(account_errors),
        "plan_failures": int((payload.get("summary") or {}).get("plan_failures", 0) or 0),
    }
    if account_errors:
        errors = payload.setdefault("errors", {})
        if isinstance(errors, dict):
            existing = list(errors.get("accounts") or [])
            errors["accounts"] = [*existing, *account_errors]
    return {
        "applied": True,
        "account_count": len(account_rows),
        "account_error_count": len(account_errors),
        "errors": account_errors[:20],
        "residual_plan_count": len(residual_plans),
        "residual_stat_cost": money(sum(float(item.stat_cost or 0.0) for item in residual_plans)),
        "residual_ad_ids": [int(item.ad_id or 0) for item in residual_plans],
        "negative_plan_delta_count": len(negative_deltas),
        "negative_plan_delta_stat_cost": money(sum(abs(money(item.get("delta"))) for item in negative_deltas)),
        "negative_plan_deltas": negative_deltas[:20],
    }


def replace_performance_day(
    *,
    customer_center_id: str,
    day_key: str,
    dry_run: bool,
    allow_errors: bool,
) -> dict[str, Any]:
    start_dt, end_dt = build_day_window(day_key, scoped_timezone(customer_center_id))
    payload = service._collect_window_snapshot_for_customer_center(
        customer_center_id,
        start_dt,
        end_dt,
        include_balances=False,
    )
    payload["snapshot_time"] = service._closed_day_snapshot_time(end_dt)
    payload["window_start"] = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    payload["window_end"] = end_dt.strftime("%Y-%m-%d %H:%M:%S")
    official_account_authority = apply_official_account_authority(
        payload,
        customer_center_id=customer_center_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )
    official_error_count = payload_error_count(payload)
    if official_error_count and not allow_errors:
        raise RuntimeError(f"official performance collection returned {official_error_count} errors")

    summary = dict(payload.get("summary") or {})
    official_counts = {
        "account_count": len(payload.get("accounts") or []),
        "plan_count": len(payload.get("plans") or []),
        "stat_cost": round(float(summary.get("stat_cost", 0.0) or 0.0), 2),
        "pay_amount": round(float(summary.get("pay_amount", 0.0) or 0.0), 2),
        "order_count": int(float(summary.get("order_count", 0) or 0)),
        "error_count": official_error_count,
    }

    with service.db() as conn:
        before = performance_counts(conn, customer_center_id, day_key)
        if dry_run:
            after = before
        else:
            enriched_plan_rows = service._apply_plan_delivery_type_metadata_rows(
                conn,
                [
                    {
                        "customer_center_id": customer_center_id,
                        **dict(item),
                    }
                    for item in (payload.get("plans") or [])
                ],
            )
            payload["plans"] = [
                {
                    key: value
                    for key, value in dict(row).items()
                    if key != "customer_center_id"
                }
                for row in enriched_plan_rows
            ]
            conn.execute(
                "DELETE FROM account_daily WHERE customer_center_id = ? AND biz_date = ?",
                (customer_center_id, day_key),
            )
            conn.execute(
                "DELETE FROM plan_daily WHERE customer_center_id = ? AND biz_date = ?",
                (customer_center_id, day_key),
            )
            conn.execute(
                "DELETE FROM summary_daily WHERE customer_center_id = ? AND biz_date = ?",
                (customer_center_id, day_key),
            )
            service.performance_access.upsert_daily_read_models(
                conn,
                [service._summary_current_row_from_payload(customer_center_id, payload)],
                service._scoped_payload_accounts(customer_center_id, payload),
                service._scoped_payload_plans(customer_center_id, payload),
            )
            after = performance_counts(conn, customer_center_id, day_key)

    return {
        "customer_center_id": customer_center_id,
        "day": day_key,
        "official": official_counts,
        "before": before,
        "after": after,
        "updated": not dry_run,
        "matches_official": round(float(after["summary_daily"]["stat_cost"]), 2) == official_counts["stat_cost"],
        "official_account_authority": official_account_authority,
    }


def placeholders(values: list[int]) -> str:
    return ",".join("?" for _ in values)


def official_plan_ids(conn: Any, customer_center_id: str, day_key: str) -> list[int]:
    rows = conn.execute(
        """
        SELECT ad_id
        FROM plan_daily
        WHERE customer_center_id = ?
          AND biz_date = ?
          AND ad_id > 0
        ORDER BY ad_id
        """,
        (customer_center_id, day_key),
    ).fetchall()
    return sorted({int(dict(row).get("ad_id", 0) or 0) for row in rows if int(dict(row).get("ad_id", 0) or 0) > 0})


def prune_table_to_official_plans(
    conn: Any,
    *,
    table: str,
    customer_center_id: str,
    day_key: str,
    allowed_ad_ids: list[int],
    snapshot_table: bool = False,
) -> int:
    if allowed_ad_ids:
        params: list[Any] = [customer_center_id, day_key, *allowed_ad_ids]
        day_predicate = "substr(snapshot_time, 1, 10) = ?" if snapshot_table else "biz_date = ?"
        sql = (
            f"DELETE FROM {table} "
            f"WHERE customer_center_id = ? AND {day_predicate} "
            f"AND ad_id NOT IN ({placeholders(allowed_ad_ids)})"
        )
    else:
        params = [customer_center_id, day_key]
        day_predicate = "substr(snapshot_time, 1, 10) = ?" if snapshot_table else "biz_date = ?"
        sql = f"DELETE FROM {table} WHERE customer_center_id = ? AND {day_predicate}"
    cursor = conn.execute(sql, params)
    return int(getattr(cursor, "rowcount", 0) or 0)


def add_unattributed_material_residuals(conn: Any, customer_center_id: str, day_key: str) -> dict[str, Any]:
    residual_key_like = f"{UNATTRIBUTED_MATERIAL_KEY_PREFIX}:%"
    delete_cursor = conn.execute(
        """
        DELETE FROM material_relation_daily
        WHERE customer_center_id = ?
          AND biz_date = ?
          AND material_key LIKE ?
        """,
        (customer_center_id, day_key, residual_key_like),
    )
    rows = [
        dict(row)
        for row in conn.execute(
            """
            WITH relation_rollup AS (
                SELECT
                    ad_id,
                    ROUND(COALESCE(SUM(stat_cost), 0)::numeric, 2) AS stat_cost,
                    ROUND(COALESCE(SUM(pay_amount), 0)::numeric, 2) AS pay_amount,
                    ROUND(COALESCE(SUM(total_pay_amount), 0)::numeric, 2) AS total_pay_amount,
                    ROUND(COALESCE(SUM(settled_pay_amount), 0)::numeric, 2) AS settled_pay_amount,
                    COALESCE(SUM(order_count), 0) AS order_count,
                    COALESCE(SUM(settled_order_count), 0) AS settled_order_count
                FROM material_relation_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                  AND COALESCE(material_type, '') <> 'TITLE'
                  AND material_key NOT LIKE ?
                GROUP BY ad_id
            )
            SELECT
                p.customer_center_id,
                p.biz_date,
                p.snapshot_time,
                p.advertiser_id,
                p.advertiser_name,
                p.ad_id,
                p.ad_name,
                COALESCE(p.anchor_name, '') AS anchor_name,
                ROUND(p.stat_cost::numeric - COALESCE(r.stat_cost, 0), 2) AS stat_cost_delta,
                ROUND(p.pay_amount::numeric - COALESCE(r.pay_amount, 0), 2) AS pay_amount_delta,
                ROUND(p.total_pay_amount::numeric - COALESCE(r.total_pay_amount, 0), 2) AS total_pay_amount_delta,
                ROUND(p.settled_pay_amount::numeric - COALESCE(r.settled_pay_amount, 0), 2) AS settled_pay_amount_delta,
                CAST(p.order_count - COALESCE(r.order_count, 0) AS INTEGER) AS order_count_delta,
                CAST(p.settled_order_count - COALESCE(r.settled_order_count, 0) AS INTEGER) AS settled_order_count_delta
            FROM plan_daily p
            LEFT JOIN relation_rollup r ON r.ad_id = p.ad_id
            WHERE p.customer_center_id = ?
              AND p.biz_date = ?
              AND ROUND(p.stat_cost::numeric - COALESCE(r.stat_cost, 0), 2) >= ?
            ORDER BY stat_cost_delta DESC, p.ad_id ASC
            """,
            (customer_center_id, day_key, residual_key_like, customer_center_id, day_key, MIN_RESIDUAL_STAT_COST),
        ).fetchall()
    ]
    if rows:
        conn.executemany(
            """
            INSERT INTO material_relation_daily (
                customer_center_id, biz_date, snapshot_time, window_start, window_end, advertiser_id, advertiser_name,
                ad_id, ad_name, material_type, material_key, material_id, material_name, create_time,
                video_id, cover_url, aweme_item_id, video_url, stat_cost, pay_amount, total_pay_amount,
                settled_pay_amount, order_count, settled_order_count, overall_show_count, overall_click_count,
                top_anchor_name, product_info_text, is_original
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    customer_center_id,
                    day_key,
                    str(row.get("snapshot_time") or ""),
                    f"{day_key} 00:00:00",
                    f"{day_key} 23:59:59",
                    int(row.get("advertiser_id", 0) or 0),
                    str(row.get("advertiser_name") or ""),
                    int(row.get("ad_id", 0) or 0),
                    str(row.get("ad_name") or ""),
                    UNATTRIBUTED_MATERIAL_TYPE,
                    f"{UNATTRIBUTED_MATERIAL_KEY_PREFIX}:{int(row.get('ad_id', 0) or 0)}",
                    "",
                    UNATTRIBUTED_MATERIAL_NAME,
                    "",
                    "",
                    "",
                    "",
                    "",
                    float(row.get("stat_cost_delta", 0.0) or 0.0),
                    max(float(row.get("pay_amount_delta", 0.0) or 0.0), 0.0),
                    max(float(row.get("total_pay_amount_delta", 0.0) or 0.0), 0.0),
                    max(float(row.get("settled_pay_amount_delta", 0.0) or 0.0), 0.0),
                    max(int(row.get("order_count_delta", 0) or 0), 0),
                    max(int(row.get("settled_order_count_delta", 0) or 0), 0),
                    0,
                    0,
                    str(row.get("anchor_name") or ""),
                    UNATTRIBUTED_PRODUCT_INFO_TEXT,
                    0,
                )
                for row in rows
            ],
        )
    total_cost = round(sum(float(row.get("stat_cost_delta", 0.0) or 0.0) for row in rows), 2)
    total_pay = round(sum(max(float(row.get("pay_amount_delta", 0.0) or 0.0), 0.0) for row in rows), 2)
    return {
        "deleted_previous_rows": int(getattr(delete_cursor, "rowcount", 0) or 0),
        "inserted_rows": len(rows),
        "stat_cost": total_cost,
        "pay_amount": total_pay,
        "ad_ids": [int(row.get("ad_id", 0) or 0) for row in rows],
    }


def rebuild_material_daily_from_relations(conn: Any, customer_center_id: str, day_key: str) -> int:
    relation_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM material_relation_daily
            WHERE customer_center_id = ?
              AND biz_date = ?
            ORDER BY stat_cost DESC, material_key ASC
            """,
            (customer_center_id, day_key),
        ).fetchall()
    ]
    non_title_metric_plan_keys = {
        (
            int(row.get("advertiser_id", 0) or 0),
            int(row.get("ad_id", 0) or 0),
        )
        for row in relation_rows
        if str(row.get("material_type") or "").strip().upper() != "TITLE"
        and service._material_source_row_has_positive_metrics(row)
    }
    source_rows: list[dict[str, Any]] = []
    for row in relation_rows:
        ad_id = int(row.get("ad_id", 0) or 0)
        advertiser_id = int(row.get("advertiser_id", 0) or 0)
        record = dict(row)
        if (
            str(record.get("material_type") or "").strip().upper() == "TITLE"
            and (advertiser_id, ad_id) in non_title_metric_plan_keys
        ):
            service._zero_material_source_row_metrics(record)
        record["plan_ids_json"] = json.dumps([ad_id] if ad_id > 0 else [], ensure_ascii=False)
        record["advertiser_ids_json"] = json.dumps([advertiser_id] if advertiser_id > 0 else [], ensure_ascii=False)
        record["plan_count"] = 1 if ad_id > 0 else 0
        record["advertiser_count"] = 1 if advertiser_id > 0 else 0
        record["top_plan_name"] = str(row.get("ad_name") or "")
        record["top_account_name"] = str(row.get("advertiser_name") or "")
        record["product_names_json"] = "[]"
        record["refund_amount_1h"] = 0.0
        record["refund_rate_1h"] = None
        source_rows.append(record)
    rollup_records = service._aggregate_material_rollups(source_rows)
    rollup_rows = [service._material_rollup_tuple_from_record(row) for row in rollup_records]
    service._replace_material_daily_rows(conn, customer_center_id, day_key, rollup_rows)
    service._invalidate_material_ranking_indexes_for_day(conn, day_key, customer_center_id)
    return len(rollup_rows)


def align_material_day(
    *,
    customer_center_id: str,
    day_key: str,
    material_collection_mode: str,
    allow_errors: bool,
    dry_run: bool,
    skip_title_video_alignment: bool,
    prune_material_to_plan_daily: bool,
) -> dict[str, Any]:
    target = {"customer_center_id": customer_center_id, "target_date": day_key}
    with service.db() as conn:
        before = material_counts(conn, customer_center_id, day_key)
    if dry_run:
        return {
            "customer_center_id": customer_center_id,
            "day": day_key,
            "updated": False,
            "before": before,
            "after": before,
            "history_result": {"skipped": True, "reason": "dry_run"},
            "fallback_history_result": None,
            "pruned_relation_rows": 0,
            "pruned_snapshot_rows": 0,
            "pruned_to_plan_daily": False,
            "title_video_alignment": {"skipped": True, "reason": "dry_run"},
            "rebuilt_material_daily_rows": before["material_daily"]["row_count"],
        }

    primary_mode = str(material_collection_mode or "full_snapshot").strip().lower()
    history_result = service.refresh_extended_history_targets(
        [target],
        material_collection_mode=primary_mode,
        force_replace=True,
    )
    fallback_history_result: dict[str, Any] | None = None
    effective_result = history_result
    primary_errors = int(history_result.get("error_count", 0) or 0)
    primary_refreshed = int(history_result.get("refreshed_days", 0) or 0)
    if primary_mode == "full_snapshot" and (primary_errors > 0 or primary_refreshed < 1):
        fallback_history_result = service.refresh_extended_history_targets(
            [target],
            material_collection_mode="report_batch",
            force_replace=True,
        )
        fallback_errors = int(fallback_history_result.get("error_count", 0) or 0)
        fallback_refreshed = int(fallback_history_result.get("refreshed_days", 0) or 0)
        if fallback_errors < primary_errors or fallback_refreshed > primary_refreshed:
            effective_result = fallback_history_result

    effective_errors = int(effective_result.get("error_count", 0) or 0)
    if effective_errors and not allow_errors:
        raise RuntimeError(f"official material collection returned {effective_errors} errors")

    with service.db() as conn:
        if prune_material_to_plan_daily:
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
        else:
            pruned_relation_rows = 0
            pruned_snapshot_rows = 0
        residual_result = add_unattributed_material_residuals(conn, customer_center_id, day_key)
        rebuilt_count = rebuild_material_daily_from_relations(conn, customer_center_id, day_key)
    if skip_title_video_alignment:
        title_video_alignment = {"skipped": True, "reason": "skip_title_video_alignment"}
    else:
        title_video_alignment = service.repair_material_title_video_alignment_day(
            customer_center_id,
            day_key,
            fetch_creative=True,
            dry_run=False,
        )
    with service.db() as conn:
        after = material_counts(conn, customer_center_id, day_key)

    return {
        "customer_center_id": customer_center_id,
        "day": day_key,
        "updated": True,
        "before": before,
        "after": after,
        "history_result": effective_result,
        "primary_history_result": history_result,
        "fallback_history_result": fallback_history_result,
        "pruned_relation_rows": pruned_relation_rows,
        "pruned_snapshot_rows": pruned_snapshot_rows,
        "pruned_to_plan_daily": bool(prune_material_to_plan_daily),
        "unattributed_residual": residual_result,
        "title_video_alignment": title_video_alignment,
        "rebuilt_material_daily_rows": rebuilt_count,
    }


def rebuild_material_prefix_indexes(start_date: str, end_date: str, customer_center_ids: list[str]) -> dict[str, Any]:
    closed_days = iter_days(parse_day(start_date), parse_day(end_date))
    if not closed_days:
        return {"ok": True, "skipped": True, "reason": "empty_range", "results": []}
    prefix_end_day = service._material_history_index_refresh_end_day(closed_days)
    results: list[dict[str, Any]] = []
    for customer_center_id in customer_center_ids:
        try:
            results.append(
                material_ranking_index.rebuild_day_prefix_range(
                    service,
                    start_day=closed_days[0],
                    end_day=prefix_end_day,
                    all_customer_centers=False,
                    force_scope_key=customer_center_id,
                    force_customer_center_id=customer_center_id,
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "ok": False,
                    "scope_key": customer_center_id,
                    "start_day": closed_days[0],
                    "end_day": prefix_end_day,
                    "error": str(exc),
                }
            )
    try:
        results.append(
            material_ranking_index.rebuild_day_prefix_range(
                service,
                start_day=closed_days[0],
                end_day=prefix_end_day,
                all_customer_centers=True,
                force_scope_key=material_ranking_index.SCOPE_ALL,
            )
        )
    except Exception as exc:  # noqa: BLE001
        results.append(
            {
                "ok": False,
                "scope_key": material_ranking_index.SCOPE_ALL,
                "start_day": closed_days[0],
                "end_day": prefix_end_day,
                "error": str(exc),
            }
        )
    service.clear_material_runtime_caches(scope="all")
    return {
        "ok": all(bool(item.get("ok")) for item in results),
        "start_day": closed_days[0],
        "end_day": prefix_end_day,
        "result_count": len(results),
        "results": results,
    }


def main() -> int:
    args = parse_args()
    start_day = parse_day(str(args.start_date).strip())
    end_day = parse_day(str(args.end_date).strip())
    if end_day < start_day:
        raise ValueError("end_date must be greater than or equal to start_date")

    service.init_db_once()
    service.bootstrap_token_store()
    service.assert_runtime_client_compatibility()

    customer_center_ids = resolve_customer_center_ids([str(item).strip() for item in args.customer_center_id])
    if not customer_center_ids:
        raise RuntimeError("No customer_center_id is available for official alignment")

    day_values = iter_days(start_day, end_day)
    performance_results: list[dict[str, Any]] = []
    material_results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for customer_center_id in customer_center_ids:
        for day_key in day_values:
            try:
                perf_result = replace_performance_day(
                    customer_center_id=customer_center_id,
                    day_key=day_key,
                    dry_run=bool(args.dry_run),
                    allow_errors=bool(args.allow_performance_errors),
                )
                performance_results.append(perf_result)
                if not bool(args.skip_material):
                    material_results.append(
                        align_material_day(
                            customer_center_id=customer_center_id,
                            day_key=day_key,
                            material_collection_mode=str(args.material_collection_mode),
                            allow_errors=bool(args.allow_material_errors),
                            dry_run=bool(args.dry_run),
                            skip_title_video_alignment=bool(args.skip_title_video_alignment),
                            prune_material_to_plan_daily=bool(args.prune_material_to_plan_daily),
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                error_item = {
                    "customer_center_id": customer_center_id,
                    "day": day_key,
                    "error": str(exc),
                }
                errors.append(error_item)
                if bool(args.stop_on_error):
                    raise

    prefix_result: dict[str, Any] | None = None
    if not bool(args.skip_material) and not bool(args.dry_run):
        prefix_result = rebuild_material_prefix_indexes(
            str(args.start_date).strip(),
            str(args.end_date).strip(),
            customer_center_ids,
        )

    result = {
        "kind": "official_daily_align_result",
        "version": 1,
        "generated_at": now_text(load_runtime_timezone()),
        "start_date": str(args.start_date).strip(),
        "end_date": str(args.end_date).strip(),
        "customer_center_ids": customer_center_ids,
        "dry_run": bool(args.dry_run),
        "skip_material": bool(args.skip_material),
        "skip_title_video_alignment": bool(args.skip_title_video_alignment),
        "prune_material_to_plan_daily": bool(args.prune_material_to_plan_daily),
        "performance": {
            "result_count": len(performance_results),
            "updated_count": sum(1 for item in performance_results if bool(item.get("updated"))),
            "match_count": sum(1 for item in performance_results if bool(item.get("matches_official"))),
            "results": performance_results,
        },
        "material": {
            "result_count": len(material_results),
            "updated_count": sum(1 for item in material_results if bool(item.get("updated"))),
            "results": material_results,
            "prefix_rebuild": prefix_result,
        },
        "error_count": len(errors),
        "errors": errors,
    }
    dump_json(Path(args.result_out), result)
    print(
        json.dumps(
            {
                "result_out": args.result_out,
                "performance_results": len(performance_results),
                "performance_matches": result["performance"]["match_count"],
                "material_results": len(material_results),
                "error_count": len(errors),
            },
            ensure_ascii=False,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
