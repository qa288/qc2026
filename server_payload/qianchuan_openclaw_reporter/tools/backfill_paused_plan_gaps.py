#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dashboard.main import TIMEZONE, service  # noqa: E402
from report_qianchuan import AccountSummary, ApiError, PlanSummary, dump_json, load_json  # noqa: E402


PAUSED_STATUS_VALUES = {
    "DISABLE",
    "SYSTEM_DISABLE",
    "DELETE",
    "REMOVED",
    "AUDIT_DENY",
}
PAUSED_OPT_STATUS_VALUES = {
    "DISABLE",
    "ROI2_DISABLE",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan paused-plan trailing gaps from plan_daily and backfill missing days "
            "by pulling official advertiser/day reports and UPSERTing recovered rows."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_filters(target: argparse.ArgumentParser) -> None:
        target.add_argument("--start-date", required=True, help="Inclusive start date in YYYY-MM-DD format.")
        target.add_argument("--end-date", required=True, help="Inclusive end date in YYYY-MM-DD format.")
        target.add_argument(
            "--customer-center-id",
            action="append",
            default=[],
            help="Limit to one or more customer_center_id values.",
        )
        target.add_argument(
            "--advertiser-id",
            action="append",
            type=int,
            default=[],
            help="Limit to one or more advertiser_id values.",
        )
        target.add_argument(
            "--ad-id",
            action="append",
            type=int,
            default=[],
            help="Limit to one or more ad_id values.",
        )

    scan_parser = subparsers.add_parser("scan", help="Scan paused-plan trailing gaps and write a manifest.")
    add_common_filters(scan_parser)
    scan_parser.add_argument(
        "--manifest-out",
        default="paused_plan_gap_manifest.json",
        help="Output path for the generated manifest JSON.",
    )

    apply_parser = subparsers.add_parser("apply", help="Apply backfill from a manifest.")
    apply_parser.add_argument(
        "--manifest-in",
        required=True,
        help="Path to a manifest JSON created by the scan subcommand.",
    )
    apply_parser.add_argument(
        "--result-out",
        default="paused_plan_gap_backfill_result.json",
        help="Output path for the apply result JSON.",
    )
    apply_parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately when a single advertiser/day backfill call fails.",
    )
    return parser.parse_args()


def parse_day(value: str) -> date:
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def day_text(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def iter_days(start_day: date, end_day: date) -> list[str]:
    cursor = start_day
    values: list[str] = []
    while cursor <= end_day:
        values.append(day_text(cursor))
        cursor += timedelta(days=1)
    return values


def is_paused_like(status: Any, opt_status: Any) -> bool:
    status_text = str(status or "").strip().upper()
    opt_text = str(opt_status or "").strip().upper()
    return status_text in PAUSED_STATUS_VALUES or opt_text in PAUSED_OPT_STATUS_VALUES


def load_runtime_timezone() -> str:
    try:
        config = service.read_config()
    except Exception:
        config = {}
    return str(config.get("timezone") or TIMEZONE or "Asia/Shanghai")


def now_text(tz_name: str) -> str:
    return datetime.now(ZoneInfo(tz_name)).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def normalize_filter_lists(values: list[Any]) -> list[Any]:
    normalized: list[Any] = []
    seen: set[Any] = set()
    for value in values:
        item = value
        if isinstance(value, str):
            item = value.strip()
        if item in ("", None):
            continue
        if item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def scan_paused_plan_gaps(
    *,
    start_date: str,
    end_date: str,
    customer_center_ids: list[str],
    advertiser_ids: list[int],
    ad_ids: list[int],
) -> dict[str, Any]:
    service.init_db_once()
    tz_name = load_runtime_timezone()
    start_day = parse_day(start_date)
    end_day = parse_day(end_date)
    if end_day < start_day:
        raise ValueError("end_date must be greater than or equal to start_date")

    normalized_customer_center_ids = normalize_filter_lists(customer_center_ids)
    normalized_advertiser_ids = normalize_filter_lists(advertiser_ids)
    normalized_ad_ids = normalize_filter_lists(ad_ids)

    where_clauses = ["biz_date >= ?", "biz_date <= ?"]
    params: list[Any] = [start_date, end_date]

    if normalized_customer_center_ids:
        placeholders = ", ".join("?" for _ in normalized_customer_center_ids)
        where_clauses.append(f"customer_center_id IN ({placeholders})")
        params.extend(normalized_customer_center_ids)
    if normalized_advertiser_ids:
        placeholders = ", ".join("?" for _ in normalized_advertiser_ids)
        where_clauses.append(f"advertiser_id IN ({placeholders})")
        params.extend(int(item) for item in normalized_advertiser_ids)
    if normalized_ad_ids:
        placeholders = ", ".join("?" for _ in normalized_ad_ids)
        where_clauses.append(f"ad_id IN ({placeholders})")
        params.extend(int(item) for item in normalized_ad_ids)

    rows: list[dict[str, Any]] = []
    with service.db() as conn:
        sql = f"""
            SELECT
                customer_center_id,
                advertiser_id,
                advertiser_name,
                ad_id,
                ad_name,
                biz_date,
                snapshot_time,
                status,
                opt_status,
                stat_cost,
                pay_amount,
                order_count,
                plan_source,
                plan_delivery_type
            FROM plan_daily
            WHERE {' AND '.join(where_clauses)}
            ORDER BY customer_center_id ASC, advertiser_id ASC, ad_id ASC, biz_date ASC, snapshot_time ASC
        """
        rows = [dict(row) for row in conn.execute(sql, params).fetchall()]

    by_plan: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        customer_center_id = str(row.get("customer_center_id") or "").strip()
        advertiser_id = int(row.get("advertiser_id", 0) or 0)
        ad_id = int(row.get("ad_id", 0) or 0)
        if not customer_center_id or advertiser_id <= 0 or ad_id <= 0:
            continue
        by_plan[(customer_center_id, advertiser_id, ad_id)].append(row)

    candidates: list[dict[str, Any]] = []
    skipped_not_paused = 0
    skipped_no_gap = 0
    end_day_text = day_text(end_day)
    for (customer_center_id, advertiser_id, ad_id), plan_rows in sorted(by_plan.items()):
        last_row = max(
            plan_rows,
            key=lambda item: (
                str(item.get("biz_date") or ""),
                str(item.get("snapshot_time") or ""),
            ),
        )
        last_day_text = str(last_row.get("biz_date") or "").strip()
        if not last_day_text or last_day_text >= end_day_text:
            skipped_no_gap += 1
            continue
        if not is_paused_like(last_row.get("status"), last_row.get("opt_status")):
            skipped_not_paused += 1
            continue
        last_day = parse_day(last_day_text)
        missing_start = last_day + timedelta(days=1)
        missing_days = iter_days(missing_start, end_day)
        if not missing_days:
            skipped_no_gap += 1
            continue
        candidates.append(
            {
                "customer_center_id": customer_center_id,
                "advertiser_id": advertiser_id,
                "advertiser_name": str(last_row.get("advertiser_name") or "").strip(),
                "ad_id": ad_id,
                "ad_name": str(last_row.get("ad_name") or "").strip(),
                "last_seen_date": last_day_text,
                "last_snapshot_time": str(last_row.get("snapshot_time") or "").strip(),
                "last_status": str(last_row.get("status") or "").strip(),
                "last_opt_status": str(last_row.get("opt_status") or "").strip(),
                "last_stat_cost": round(float(last_row.get("stat_cost", 0.0) or 0.0), 2),
                "last_pay_amount": round(float(last_row.get("pay_amount", 0.0) or 0.0), 2),
                "last_order_count": int(float(last_row.get("order_count", 0) or 0)),
                "plan_source": str(last_row.get("plan_source") or "").strip(),
                "plan_delivery_type": str(last_row.get("plan_delivery_type") or "").strip(),
                "missing_days": missing_days,
                "missing_day_count": len(missing_days),
            }
        )

    manifest = {
        "kind": "paused_plan_gap_manifest",
        "version": 1,
        "generated_at": now_text(tz_name),
        "timezone": tz_name,
        "start_date": start_date,
        "end_date": end_date,
        "filters": {
            "customer_center_ids": normalized_customer_center_ids,
            "advertiser_ids": [int(item) for item in normalized_advertiser_ids],
            "ad_ids": [int(item) for item in normalized_ad_ids],
        },
        "summary": {
            "scanned_row_count": len(rows),
            "scanned_plan_count": len(by_plan),
            "candidate_plan_count": len(candidates),
            "candidate_missing_day_count": sum(int(item.get("missing_day_count", 0) or 0) for item in candidates),
            "skipped_not_paused": skipped_not_paused,
            "skipped_no_gap": skipped_no_gap,
        },
        "candidates": candidates,
    }
    return manifest


def merge_plan_candidates(primary: list[PlanSummary], secondary: list[PlanSummary]) -> list[PlanSummary]:
    merged: dict[int, PlanSummary] = {int(item.ad_id): item for item in primary if int(item.ad_id or 0) > 0}
    for item in secondary:
        ad_id = int(item.ad_id or 0)
        if ad_id <= 0 or ad_id in merged:
            continue
        merged[ad_id] = item
    return list(merged.values())


def fetch_target_plan_rows(
    *,
    client: Any,
    advertiser_id: int,
    advertiser_name: str,
    start_dt: datetime,
    end_dt: datetime,
    target_ad_ids: set[int],
) -> tuple[list[PlanSummary], list[str]]:
    notes: list[str] = []
    plans: list[PlanSummary] = []
    try:
        plans = client.list_plan_summaries(
            advertiser_id,
            advertiser_name,
            start_dt,
            end_dt,
            allow_standard_fallback=True,
            allow_report_fallback=True,
        )
        notes.append("list_plan_summaries")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"list_plan_summaries_error:{exc}")

    filtered = [item for item in plans if int(item.ad_id or 0) in target_ad_ids]
    missing_ad_ids = target_ad_ids - {int(item.ad_id or 0) for item in filtered}
    if missing_ad_ids:
        try:
            report_plans = client.list_report_plan_summaries(
                advertiser_id,
                advertiser_name,
                start_dt,
                end_dt,
                hydrate_plan_detail=True,
            )
            notes.append("list_report_plan_summaries")
            filtered = [item for item in merge_plan_candidates(filtered, report_plans) if int(item.ad_id or 0) in target_ad_ids]
            missing_ad_ids = target_ad_ids - {int(item.ad_id or 0) for item in filtered}
        except Exception as exc:  # noqa: BLE001
            notes.append(f"list_report_plan_summaries_error:{exc}")

    return filtered, notes


def apply_manifest(manifest: dict[str, Any], *, stop_on_error: bool = False) -> dict[str, Any]:
    service.init_db_once()
    service.bootstrap_token_store()
    service.assert_runtime_client_compatibility()
    tz_name = load_runtime_timezone()

    candidates = [dict(item) for item in manifest.get("candidates") or []]
    work_by_day: dict[tuple[str, int, str], dict[str, Any]] = {}
    for item in candidates:
        customer_center_id = str(item.get("customer_center_id") or "").strip()
        advertiser_id = int(item.get("advertiser_id", 0) or 0)
        advertiser_name = str(item.get("advertiser_name") or "").strip()
        ad_id = int(item.get("ad_id", 0) or 0)
        ad_name = str(item.get("ad_name") or "").strip()
        for day in item.get("missing_days") or []:
            day_text_value = str(day or "").strip()
            if not customer_center_id or advertiser_id <= 0 or ad_id <= 0 or len(day_text_value) != 10:
                continue
            bucket = work_by_day.setdefault(
                (customer_center_id, advertiser_id, day_text_value),
                {
                    "customer_center_id": customer_center_id,
                    "advertiser_id": advertiser_id,
                    "advertiser_name": advertiser_name,
                    "day": day_text_value,
                    "targets": [],
                },
            )
            bucket["targets"].append(
                {
                    "ad_id": ad_id,
                    "ad_name": ad_name,
                    "last_seen_date": str(item.get("last_seen_date") or "").strip(),
                    "last_status": str(item.get("last_status") or "").strip(),
                    "last_opt_status": str(item.get("last_opt_status") or "").strip(),
                }
            )

    client_cache: dict[str, Any] = {}
    groups = sorted(work_by_day.values(), key=lambda item: (item["customer_center_id"], item["advertiser_id"], item["day"]))
    results: list[dict[str, Any]] = []
    applied_group_count = 0
    applied_plan_count = 0

    for group in groups:
        customer_center_id = str(group["customer_center_id"])
        advertiser_id = int(group["advertiser_id"])
        advertiser_name = str(group.get("advertiser_name") or f"advertiser_{advertiser_id}")
        day_key = str(group["day"])
        target_ad_ids = {int(item.get("ad_id", 0) or 0) for item in group.get("targets") or [] if int(item.get("ad_id", 0) or 0) > 0}
        start_dt = datetime.strptime(f"{day_key} 00:00:00", "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(f"{day_key} 23:59:59", "%Y-%m-%d %H:%M:%S")

        if customer_center_id not in client_cache:
            client_cache[customer_center_id] = service._build_scoped_customer_center_client(customer_center_id)
        client = client_cache[customer_center_id]

        result_item: dict[str, Any] = {
            "customer_center_id": customer_center_id,
            "advertiser_id": advertiser_id,
            "advertiser_name": advertiser_name,
            "day": day_key,
            "target_ad_ids": sorted(target_ad_ids),
            "requested_plan_count": len(target_ad_ids),
            "recovered_plan_count": 0,
            "recovered_ad_ids": [],
            "missing_ad_ids": [],
            "plan_fetch_notes": [],
            "ok": False,
            "error": "",
            "applied": False,
        }
        try:
            account_summary = client.get_account_summary(advertiser_id, advertiser_name, start_dt, end_dt)
            plan_rows, fetch_notes = fetch_target_plan_rows(
                client=client,
                advertiser_id=advertiser_id,
                advertiser_name=advertiser_name,
                start_dt=start_dt,
                end_dt=end_dt,
                target_ad_ids=target_ad_ids,
            )
            recovered_ad_ids = sorted({int(item.ad_id or 0) for item in plan_rows if int(item.ad_id or 0) > 0})
            missing_ad_ids = sorted(target_ad_ids - set(recovered_ad_ids))
            result_item["plan_fetch_notes"] = fetch_notes
            result_item["recovered_plan_count"] = len(recovered_ad_ids)
            result_item["recovered_ad_ids"] = recovered_ad_ids
            result_item["missing_ad_ids"] = missing_ad_ids

            if plan_rows:
                with service.db() as conn:
                    service._replace_performance_daily_account_subset(
                        conn,
                        customer_center_id=customer_center_id,
                        target_date=day_key,
                        snapshot_time=f"{day_key} 23:59:59",
                        account_rows=[account_summary],
                        plan_rows=plan_rows,
                    )
                result_item["applied"] = True
                applied_group_count += 1
                applied_plan_count += len(recovered_ad_ids)

            result_item["ok"] = True
        except Exception as exc:  # noqa: BLE001
            result_item["error"] = str(exc)
            if stop_on_error:
                results.append(result_item)
                raise
        results.append(result_item)

    payload = {
        "kind": "paused_plan_gap_backfill_result",
        "version": 1,
        "generated_at": now_text(tz_name),
        "timezone": tz_name,
        "manifest_summary": dict(manifest.get("summary") or {}),
        "group_count": len(groups),
        "applied_group_count": applied_group_count,
        "applied_plan_count": applied_plan_count,
        "error_count": sum(1 for item in results if not bool(item.get("ok"))),
        "unresolved_group_count": sum(1 for item in results if bool(item.get("ok")) and item.get("missing_ad_ids")),
        "results": results,
    }
    return payload


def main() -> int:
    args = parse_args()
    if args.command == "scan":
        manifest = scan_paused_plan_gaps(
            start_date=str(args.start_date).strip(),
            end_date=str(args.end_date).strip(),
            customer_center_ids=[str(item).strip() for item in args.customer_center_id],
            advertiser_ids=[int(item) for item in args.advertiser_id],
            ad_ids=[int(item) for item in args.ad_id],
        )
        output_path = Path(str(args.manifest_out).strip()).resolve()
        dump_json(output_path, manifest)
        print(json.dumps({"manifest_out": str(output_path), "summary": manifest.get("summary")}, ensure_ascii=False))
        return 0

    if args.command == "apply":
        manifest_path = Path(str(args.manifest_in).strip()).resolve()
        manifest = load_json(manifest_path)
        result = apply_manifest(manifest, stop_on_error=bool(args.stop_on_error))
        output_path = Path(str(args.result_out).strip()).resolve()
        dump_json(output_path, result)
        print(
            json.dumps(
                {
                    "result_out": str(output_path),
                    "group_count": result.get("group_count"),
                    "applied_group_count": result.get("applied_group_count"),
                    "applied_plan_count": result.get("applied_plan_count"),
                    "error_count": result.get("error_count"),
                    "unresolved_group_count": result.get("unresolved_group_count"),
                },
                ensure_ascii=False,
            )
        )
        return 0

    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
