#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for candidate in (ROOT_DIR, TOOLS_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from backfill_paused_plan_gaps import apply_manifest, scan_paused_plan_gaps  # noqa: E402
from dashboard.main import TIMEZONE, material_ranking_index, now_text, service  # noqa: E402
from report_qianchuan import dump_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repair a historical date window by re-fetching account/plan daily data, "
            "re-applying paused-plan gap recovery, rebuilding material history, and "
            "refreshing material ranking prefix aggregates."
        )
    )
    parser.add_argument("--start-date", required=True, help="Inclusive start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", required=True, help="Inclusive end date in YYYY-MM-DD format.")
    parser.add_argument(
        "--customer-center-id",
        action="append",
        default=[],
        help="Limit the repair to one or more customer_center_id values.",
    )
    parser.add_argument(
        "--skip-performance",
        action="store_true",
        help="Skip account/plan daily backfill from official reports.",
    )
    parser.add_argument(
        "--skip-paused-plan-gap-repair",
        action="store_true",
        help="Skip the paused-plan trailing-gap scan/apply stage.",
    )
    parser.add_argument(
        "--skip-material",
        action="store_true",
        help="Skip material history repair and prefix rebuild.",
    )
    parser.add_argument(
        "--material-collection-mode",
        default="full_snapshot",
        choices=("full_snapshot", "report_batch"),
        help="Material history collection mode to use during repair.",
    )
    parser.add_argument(
        "--result-out",
        default="history_repair_result.json",
        help="Output path for the repair result JSON.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately when a single day/customer-center repair step fails.",
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


def normalize_text_list(values: list[Any]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
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
        scoped_config = service._scoped_config_for_customer_center(customer_center_id)
    except Exception:
        scoped_config = {}
    return str(scoped_config.get("timezone") or load_runtime_timezone() or TIMEZONE)


def build_day_window(day_key: str, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(str(tz_name or TIMEZONE))
    target_day = parse_day(day_key)
    start_dt = datetime(target_day.year, target_day.month, target_day.day, 0, 0, 0, tzinfo=tz)
    end_dt = datetime(target_day.year, target_day.month, target_day.day, 23, 59, 59, tzinfo=tz)
    return start_dt, end_dt


def repair_performance_window(
    *,
    start_date: str,
    end_date: str,
    customer_center_ids: list[str],
    stop_on_error: bool = False,
) -> dict[str, Any]:
    tz_cache: dict[str, str] = {}
    day_values = iter_days(parse_day(start_date), parse_day(end_date))
    results: list[dict[str, Any]] = []
    repaired_targets: list[dict[str, str]] = []
    for customer_center_id in customer_center_ids:
        tz_name = tz_cache.setdefault(customer_center_id, scoped_timezone(customer_center_id))
        for day_key in day_values:
            result_item: dict[str, Any] = {
                "customer_center_id": customer_center_id,
                "day": day_key,
                "ok": False,
                "account_row_count": 0,
                "plan_row_count": 0,
                "summary_stat_cost": 0.0,
                "summary_pay_amount": 0.0,
                "error": "",
            }
            try:
                start_dt, end_dt = build_day_window(day_key, tz_name)
                payload = service._collect_window_snapshot_for_customer_center(
                    customer_center_id,
                    start_dt,
                    end_dt,
                    include_balances=False,
                )
                payload["snapshot_time"] = service._closed_day_snapshot_time(end_dt)
                payload["window_start"] = start_dt.strftime("%Y-%m-%d %H:%M:%S")
                payload["window_end"] = end_dt.strftime("%Y-%m-%d %H:%M:%S")
                with service.db() as conn:
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
                    service.performance_access.upsert_daily_read_models(
                        conn,
                        [service._summary_current_row_from_payload(customer_center_id, payload)],
                        service._scoped_payload_accounts(customer_center_id, payload),
                        service._scoped_payload_plans(customer_center_id, payload),
                    )
                summary = dict(payload.get("summary") or {})
                result_item["account_row_count"] = len(payload.get("accounts") or [])
                result_item["plan_row_count"] = len(payload.get("plans") or [])
                result_item["summary_stat_cost"] = round(float(summary.get("stat_cost", 0.0) or 0.0), 2)
                result_item["summary_pay_amount"] = round(float(summary.get("pay_amount", 0.0) or 0.0), 2)
                result_item["ok"] = True
                repaired_targets.append(
                    {
                        "customer_center_id": customer_center_id,
                        "target_date": day_key,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                result_item["error"] = str(exc)
                if stop_on_error:
                    results.append(result_item)
                    raise
            results.append(result_item)
    return {
        "start_date": start_date,
        "end_date": end_date,
        "customer_center_count": len(customer_center_ids),
        "target_day_count": len(day_values),
        "result_count": len(results),
        "success_count": sum(1 for item in results if bool(item.get("ok"))),
        "error_count": sum(1 for item in results if not bool(item.get("ok"))),
        "repaired_targets": repaired_targets,
        "results": results,
    }


def repair_material_window(
    *,
    start_date: str,
    end_date: str,
    customer_center_ids: list[str],
    material_collection_mode: str,
) -> dict[str, Any]:
    targets = [
        {
            "customer_center_id": customer_center_id,
            "target_date": day_key,
        }
        for customer_center_id in customer_center_ids
        for day_key in iter_days(parse_day(start_date), parse_day(end_date))
    ]
    normalized_collection_mode = str(material_collection_mode or "full_snapshot").strip().lower()
    primary_history_result = service.refresh_extended_history_targets(
        targets,
        material_collection_mode=normalized_collection_mode,
    )
    history_result = primary_history_result
    fallback_history_result: dict[str, Any] | None = None
    expected_refresh_days = len(targets)
    primary_error_count = int(primary_history_result.get("error_count", 0) or 0)
    primary_refreshed_days = int(primary_history_result.get("refreshed_days", 0) or 0)
    if (
        normalized_collection_mode == "full_snapshot"
        and targets
        and (primary_error_count > 0 or primary_refreshed_days < expected_refresh_days)
    ):
        fallback_history_result = service.refresh_extended_history_targets(
            targets,
            material_collection_mode="report_batch",
        )
        fallback_errors = int(fallback_history_result.get("error_count", 0) or 0)
        fallback_refreshed_days = int(fallback_history_result.get("refreshed_days", 0) or 0)
        if fallback_refreshed_days > primary_refreshed_days or fallback_errors < primary_error_count:
            history_result = fallback_history_result
    runtime_timezone = load_runtime_timezone()
    yesterday_key = (datetime.now(ZoneInfo(runtime_timezone)).date() - timedelta(days=1)).strftime("%Y-%m-%d")
    closed_days = sorted(
        {
            str(item.get("target_date") or "").strip()
            for item in targets
            if str(item.get("target_date") or "").strip() and str(item.get("target_date") or "").strip() <= yesterday_key
        }
    )
    if not closed_days:
        return {
            "history_result": history_result,
            "primary_history_result": primary_history_result,
            "fallback_history_result": fallback_history_result,
            "material_collection_mode": normalized_collection_mode,
            "prefix_rebuild": {
                "ok": True,
                "skipped": True,
                "reason": "no_closed_history_days",
            },
        }
    prefix_end_day = service._material_history_index_refresh_end_day(closed_days)
    prefix_results: list[dict[str, Any]] = []
    for customer_center_id in customer_center_ids:
        try:
            prefix_results.append(
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
            prefix_results.append(
                {
                    "ok": False,
                    "scope_key": customer_center_id,
                    "start_day": closed_days[0],
                    "end_day": prefix_end_day,
                    "error": str(exc),
                }
            )
    try:
        prefix_results.append(
            material_ranking_index.rebuild_day_prefix_range(
                service,
                start_day=closed_days[0],
                end_day=prefix_end_day,
                all_customer_centers=True,
                force_scope_key=material_ranking_index.SCOPE_ALL,
            )
        )
    except Exception as exc:  # noqa: BLE001
        prefix_results.append(
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
        "history_result": history_result,
        "primary_history_result": primary_history_result,
        "fallback_history_result": fallback_history_result,
        "material_collection_mode": normalized_collection_mode,
        "prefix_rebuild": {
            "ok": all(bool(item.get("ok")) for item in prefix_results),
            "start_day": closed_days[0],
            "end_day": prefix_end_day,
            "result_count": len(prefix_results),
            "results": prefix_results,
        },
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
        raise RuntimeError("No customer_center_id is available for repair")

    result: dict[str, Any] = {
        "kind": "history_window_repair_result",
        "version": 1,
        "generated_at": now_text(load_runtime_timezone()),
        "start_date": str(args.start_date).strip(),
        "end_date": str(args.end_date).strip(),
        "customer_center_ids": customer_center_ids,
        "skip_performance": bool(args.skip_performance),
        "skip_paused_plan_gap_repair": bool(args.skip_paused_plan_gap_repair),
        "skip_material": bool(args.skip_material),
    }

    if not bool(args.skip_performance):
        result["performance"] = repair_performance_window(
            start_date=str(args.start_date).strip(),
            end_date=str(args.end_date).strip(),
            customer_center_ids=customer_center_ids,
            stop_on_error=bool(args.stop_on_error),
        )

    if not bool(args.skip_paused_plan_gap_repair):
        paused_plan_manifest = scan_paused_plan_gaps(
            start_date=str(args.start_date).strip(),
            end_date=str(args.end_date).strip(),
            customer_center_ids=customer_center_ids,
            advertiser_ids=[],
            ad_ids=[],
        )
        result["paused_plan_gap_repair"] = {
            "manifest_summary": dict(paused_plan_manifest.get("summary") or {}),
            "apply_result": apply_manifest(
                paused_plan_manifest,
                stop_on_error=bool(args.stop_on_error),
            ),
        }

    if not bool(args.skip_material):
        result["material"] = repair_material_window(
            start_date=str(args.start_date).strip(),
            end_date=str(args.end_date).strip(),
            customer_center_ids=customer_center_ids,
            material_collection_mode=str(args.material_collection_mode).strip().lower(),
        )

    output_path = Path(str(args.result_out).strip()).resolve()
    dump_json(output_path, result)
    print(
        json.dumps(
            {
                "result_out": str(output_path),
                "customer_center_count": len(customer_center_ids),
                "performance_error_count": int(((result.get("performance") or {}).get("error_count") or 0)),
                "paused_plan_group_count": int(
                    ((((result.get("paused_plan_gap_repair") or {}).get("apply_result") or {}).get("group_count") or 0))
                ),
                "paused_plan_error_count": int(
                    ((((result.get("paused_plan_gap_repair") or {}).get("apply_result") or {}).get("error_count") or 0))
                ),
                "material_error_count": int(
                    (((((result.get("material") or {}).get("history_result") or {}).get("error_count") or 0)))
                ),
                "material_primary_error_count": int(
                    (((((result.get("material") or {}).get("primary_history_result") or {}).get("error_count") or 0)))
                ),
                "material_fallback_error_count": (
                    int(((((result.get("material") or {}).get("fallback_history_result") or {}).get("error_count") or 0)))
                    if ((result.get("material") or {}).get("fallback_history_result") is not None)
                    else None
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
