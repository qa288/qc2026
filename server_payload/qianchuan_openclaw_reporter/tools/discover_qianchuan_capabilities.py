#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from report_qianchuan import (  # noqa: E402
    PLAN_MATERIAL_FIELDS,
    PLAN_MATERIAL_TYPES,
    PLAN_PRODUCT_FIELDS,
    UNI_PROMOTION_DATA_TOPICS,
    AccountSummary,
    ApiError,
    OceanEngineClient,
    PlanSummary,
    dump_json,
    load_runtime_config,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default=str(ROOT_DIR))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--max-accounts", type=int, default=50)
    parser.add_argument("--max-config-accounts", type=int, default=3)
    parser.add_argument("--max-plans-per-account", type=int, default=3)
    parser.add_argument("--max-topic-metrics", type=int, default=4)
    parser.add_argument("--sample-rows", type=int, default=5)
    return parser.parse_args()


def now_local(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def build_window(days: int, tz_name: str) -> tuple[datetime, datetime]:
    now = now_local(tz_name)
    start_dt = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=now.tzinfo) - timedelta(days=max(days - 1, 0))
    return start_dt, now


def short_error(exc: Exception) -> str:
    text = str(exc).strip()
    return text[:300] if len(text) > 300 else text


def summary_to_dict(item: AccountSummary) -> dict[str, Any]:
    payload = asdict(item)
    payload["status"] = "ok" if item.ok else "error"
    return payload


def plan_to_dict(item: PlanSummary) -> dict[str, Any]:
    return asdict(item)


def unique_strings(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            values.append(text)
    return values


def simplify_dimension_meta(item: dict[str, Any]) -> dict[str, Any]:
    filter_config = item.get("filter_config") or {}
    return {
        "field": str(item.get("field") or ""),
        "name": str(item.get("name") or ""),
        "is_required": bool(item.get("is_required") or False),
        "filterable": bool(item.get("filterable") or False),
        "filter_only": bool(item.get("filter_only") or False),
        "sortable": bool(item.get("sortable") or False),
        "description": str(item.get("description") or ""),
        "exclusion_dims": item.get("exclusion_dims") or [],
        "exclusion_metrics": item.get("exclusion_metrics") or [],
        "filter_range_count": len(filter_config.get("range_values") or []),
    }


def simplify_metric_meta(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "field": str(item.get("field") or ""),
        "name": str(item.get("name") or ""),
        "sort_able": bool(item.get("sort_able") or False),
        "unit": item.get("unit"),
        "description": str(item.get("description") or ""),
        "exclusion_dims": item.get("exclusion_dims") or [],
    }


def choose_probe_dimensions(topic_meta: dict[str, Any]) -> list[str]:
    required = [
        item["field"]
        for item in topic_meta.get("dimensions", [])
        if item.get("field") and item.get("is_required")
    ]
    if required:
        return required[:4]
    normal = [
        item["field"]
        for item in topic_meta.get("dimensions", [])
        if item.get("field") and not item.get("filter_only")
    ]
    if normal:
        return normal[:2]
    fallback = [item["field"] for item in topic_meta.get("dimensions", []) if item.get("field")]
    return fallback[:1]


def choose_probe_metrics(topic_meta: dict[str, Any], max_metrics: int) -> list[str]:
    preferred = [
        "stat_cost",
        "stat_cost_for_roi2",
        "total_pay_order_gmv_for_roi2",
        "total_pay_order_gmv_include_coupon_for_roi2",
        "total_pay_order_count_for_roi2",
        "total_prepay_and_pay_order_roi2",
        "product_show_count_for_roi2",
        "product_click_count_for_roi2",
    ]
    available = [item["field"] for item in topic_meta.get("metrics", []) if item.get("field")]
    results: list[str] = []
    for field in preferred:
        if field in available and field not in results:
            results.append(field)
    for field in available:
        if field not in results:
            results.append(field)
        if len(results) >= max_metrics:
            break
    return results[:max_metrics]


def topic_probe_summary(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data") or {}
    rows = data.get("rows") or []
    sample_row = rows[0] if rows else {}
    return {
        "row_count": len(rows),
        "page_info": data.get("page_info") or {},
        "sample_dimension_keys": sorted((sample_row.get("dimensions") or {}).keys()),
        "sample_metric_keys": sorted((sample_row.get("metrics") or {}).keys()),
    }


def normalize_allowed_page_size(value: int, allowed: list[int]) -> int:
    for item in sorted(allowed):
        if value <= item:
            return item
    return max(allowed)


def collect_accounts_and_plans(
    client: OceanEngineClient,
    accounts: list[dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
) -> tuple[list[AccountSummary], list[PlanSummary], list[dict[str, Any]]]:
    summaries: list[AccountSummary] = []
    plans: list[PlanSummary] = []
    plan_errors: list[dict[str, Any]] = []
    for item in accounts:
        advertiser_id = int(item["advertiser_id"])
        advertiser_name = str(item["advertiser_name"])
        summaries.append(client.get_account_summary(advertiser_id, advertiser_name, start_dt, end_dt))
        try:
            plans.extend(client.list_plan_summaries(advertiser_id, advertiser_name, start_dt, end_dt))
        except Exception as exc:  # noqa: BLE001
            plan_errors.append(
                {
                    "advertiser_id": advertiser_id,
                    "advertiser_name": advertiser_name,
                    "error": short_error(exc),
                }
            )
    return summaries, plans, plan_errors


def pick_sample_plans(plans: list[PlanSummary], max_plans_per_account: int) -> list[PlanSummary]:
    ranked = sorted(
        [item for item in plans if item.stat_cost > 0],
        key=lambda item: (-item.order_count, -item.pay_amount, -item.roi, -item.stat_cost, item.ad_id),
    )
    picked: list[PlanSummary] = []
    counts: dict[int, int] = defaultdict(int)
    for item in ranked:
        if counts[item.advertiser_id] >= max_plans_per_account:
            continue
        picked.append(item)
        counts[item.advertiser_id] += 1
    return picked


def merge_topic_registry(
    registry: dict[str, dict[str, Any]],
    advertiser_id: int,
    payload: dict[str, Any],
) -> None:
    for item in (payload.get("data") or {}).get("custom_config_datas") or []:
        topic = str(item.get("data_topic") or "").strip()
        if not topic:
            continue
        entry = registry.setdefault(
            topic,
            {
                "data_topic": topic,
                "advertiser_ids": [],
                "dimensions": {},
                "metrics": {},
                "query_limit": item.get("query_limit") or {},
                "probe_advertiser_id": advertiser_id,
            },
        )
        entry["advertiser_ids"] = unique_strings(entry["advertiser_ids"] + [advertiser_id])
        if not entry.get("query_limit"):
            entry["query_limit"] = item.get("query_limit") or {}
        if not entry.get("probe_advertiser_id"):
            entry["probe_advertiser_id"] = advertiser_id
        for dim in item.get("dimensions") or []:
            simplified = simplify_dimension_meta(dim)
            field = simplified["field"]
            if field and field not in entry["dimensions"]:
                entry["dimensions"][field] = simplified
        for metric in item.get("metrics") or []:
            simplified = simplify_metric_meta(metric)
            field = simplified["field"]
            if field and field not in entry["metrics"]:
                entry["metrics"][field] = simplified


def build_granularity_matrix(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    endpoint_summary = snapshot["endpoint_checks"]
    material_probe = endpoint_summary["plan_materials"]
    video_probe = endpoint_summary["original_video_flag"]
    topic_names = {item["data_topic"] for item in snapshot["data_topics"]}
    return [
        {
            "dimension": "account",
            "status": "verified" if endpoint_summary["account_summary"]["success_count"] > 0 else "failed",
            "source": "qianchuan/report/uni_promotion/get",
            "note": "账户消耗、支付、订单、ROI 可直接获取。",
        },
        {
            "dimension": "plan",
            "status": "verified" if endpoint_summary["plan_detail"]["success_count"] > 0 else "failed",
            "source": "qianchuan/uni_promotion/list + qianchuan/uni_promotion/ad/detail",
            "note": "计划基础配置、状态、商品、直播间和表现可直接获取。",
        },
        {
            "dimension": "product",
            "status": "verified" if endpoint_summary["plan_products"]["success_count"] > 0 else "partial",
            "source": "qianchuan/uni_promotion/ad/product/get + SITE_PROMOTION_PRODUCT_PRODUCT",
            "note": "计划下商品与商品维度报表都可通过官方接口扩展。",
        },
        {
            "dimension": "material",
            "status": "verified" if material_probe["success_count"] > 0 else "failed",
            "source": "qianchuan/uni_promotion/ad/material/get",
            "note": "素材列表可按 VIDEO/IMAGE/TITLE/CAROUSEL/LIVE_ROOM 探测。",
        },
        {
            "dimension": "video",
            "status": "verified" if ("SITE_PROMOTION_POST_DATA_VIDEO" in topic_names or "SITE_PROMOTION_PRODUCT_POST_DATA_VIDEO" in topic_names) else "partial",
            "source": "qianchuan/report/uni_promotion/data/get + qianchuan/file/video/original/get",
            "note": "视频维度依赖自定义全域报表主题；首发标记接口只返回素材是否首发。",
        },
        {
            "dimension": "employee",
            "status": "derived",
            "source": "计划里的 anchor_name / 抖音号映射",
            "note": "官方没有直接员工字段，需要映射表或计划归属规则聚合。",
        },
        {
            "dimension": "editor",
            "status": "not_available",
            "source": "无官方公开字段",
            "note": "剪辑人员/制作人不在千川开放平台标准返回里，必须依赖内部素材系统映射。",
        },
    ]


def build_markdown(snapshot: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# 千川官方能力目录")
    lines.append("")
    lines.append(f"- 生成时间：`{snapshot['generated_at']}`")
    lines.append(f"- 工作台账号：`{snapshot['customer_center_id']}`")
    lines.append(f"- 统计窗口：`{snapshot['window_start']}` 到 `{snapshot['window_end']}`")
    lines.append(f"- 探测账户数：`{snapshot['account_overview']['account_count']}`")
    lines.append(f"- 活跃计划样本数：`{len(snapshot['sample_plans'])}`")
    lines.append("")
    lines.append("## 接口验证")
    lines.append("")
    lines.append("| 接口 | 状态 | 说明 |")
    lines.append("|---|---|---|")
    checks = snapshot["endpoint_checks"]
    lines.append(f"| 子账户列表 | {'通过' if checks['list_accounts']['ok'] else '失败'} | 返回 `{checks['list_accounts']['account_count']}` 个子账户 |")
    lines.append(f"| 账户汇总 | {'通过' if checks['account_summary']['success_count'] > 0 else '失败'} | 成功 `{checks['account_summary']['success_count']}` / `{checks['account_summary']['tested_count']}` |")
    lines.append(f"| 计划列表 | {'通过' if checks['plan_list']['success_count'] > 0 else '失败'} | 成功 `{checks['plan_list']['success_count']}` / `{checks['plan_list']['tested_count']}` |")
    lines.append(f"| 计划详情 | {'通过' if checks['plan_detail']['success_count'] > 0 else '失败'} | 成功 `{checks['plan_detail']['success_count']}` / `{checks['plan_detail']['tested_count']}` |")
    lines.append(f"| 计划商品 | {'通过' if checks['plan_products']['success_count'] > 0 else '失败'} | 成功 `{checks['plan_products']['success_count']}` / `{checks['plan_products']['tested_count']}` |")
    lines.append(f"| 计划素材 | {'通过' if checks['plan_materials']['success_count'] > 0 else '失败'} | 成功 `{checks['plan_materials']['success_count']}` / `{checks['plan_materials']['tested_count']}` |")
    lines.append(f"| 视频首发标记 | {'通过' if checks['original_video_flag']['ok'] else '未验证'} | 样本 `{checks['original_video_flag']['sample_material_count']}` 个素材 |")
    lines.append(f"| 自定义主题配置 | {'通过' if checks['uni_promotion_config']['success_count'] > 0 else '失败'} | 返回 `{len(snapshot['data_topics'])}` 个主题 |")
    lines.append(f"| 自定义主题取数 | {'通过' if checks['uni_promotion_data']['success_count'] > 0 else '失败'} | 成功 `{checks['uni_promotion_data']['success_count']}` / `{checks['uni_promotion_data']['tested_count']}` |")
    lines.append("")
    lines.append("## 最小粒度结论")
    lines.append("")
    lines.append("| 维度 | 结论 | 数据源 | 说明 |")
    lines.append("|---|---|---|---|")
    for row in snapshot["granularity_matrix"]:
        status_map = {
            "verified": "已验证",
            "partial": "部分验证",
            "derived": "派生实现",
            "not_available": "官方无直接字段",
            "failed": "验证失败",
        }
        lines.append(f"| {row['dimension']} | {status_map.get(row['status'], row['status'])} | {row['source']} | {row['note']} |")
    lines.append("")
    lines.append("## 自定义全域报表主题")
    lines.append("")
    lines.append("| 主题 | 维度数 | 指标数 | 必填维度 | 样本取数 |")
    lines.append("|---|---:|---:|---|---|")
    for item in snapshot["data_topics"]:
        probe = item.get("probe") or {}
        required_dims = ",".join(item.get("required_dimensions") or []) or "-"
        probe_status = "通过" if probe.get("ok") else f"失败：{probe.get('error', '-')}"
        if probe.get("ok"):
            probe_status = f"通过，样本 `{probe.get('row_count', 0)}` 行"
        lines.append(
            f"| {item['data_topic']} | {item['dimension_count']} | {item['metric_count']} | {required_dims} | {probe_status} |"
        )
    lines.append("")
    lines.append("## 当前官方结论")
    lines.append("")
    lines.append("- 账户、计划、商品、素材、视频相关数据都可以通过官方接口分层获取。")
    lines.append("- 员工维度不是官方原生字段，必须通过计划字段或外部映射表聚合。")
    lines.append("- 剪辑人员、制作人不是当前千川官方开放字段，不能直接从投放接口读取。")
    lines.append("- 后续新增任何维度，先看 `data_topics` 和 `config/get`，再实现对应存储与页面。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    base_dir = Path(args.base_dir).resolve()
    config_path = base_dir / "config.json"
    try:
        config = load_runtime_config(config_path)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output_dir = Path(args.output_dir).resolve() if args.output_dir else (base_dir / "docs" / "discovery")
    output_dir.mkdir(parents=True, exist_ok=True)

    client = OceanEngineClient(config=config, token_cache_path=base_dir / "state" / "token_cache.json")
    start_dt, end_dt = build_window(args.days, config["timezone"])
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")

    accounts = client.list_accounts()[: args.max_accounts]
    summaries, plans, plan_errors = collect_accounts_and_plans(client, accounts, start_dt, end_dt)
    summary_by_advertiser = {item.advertiser_id: item for item in summaries}
    sample_plans = pick_sample_plans(plans, args.max_plans_per_account)
    active_accounts = [
        item for item in summaries if item.ok and item.stat_cost > 0
    ]
    config_accounts = [item.advertiser_id for item in sorted(active_accounts, key=lambda row: (-row.stat_cost, row.advertiser_id))[: args.max_config_accounts]]
    if not config_accounts and summaries:
        config_accounts = [summaries[0].advertiser_id]

    endpoint_checks: dict[str, Any] = {
        "list_accounts": {"ok": True, "account_count": len(accounts)},
        "account_summary": {
            "tested_count": len(summaries),
            "success_count": sum(1 for item in summaries if item.ok),
            "failure_count": sum(1 for item in summaries if not item.ok),
        },
        "plan_list": {
            "tested_count": len(accounts),
            "success_count": len({item.advertiser_id for item in plans}),
            "plan_count": len(plans),
            "active_plan_count": sum(1 for item in plans if item.stat_cost > 0),
            "errors": plan_errors,
        },
        "plan_detail": {"tested_count": 0, "success_count": 0, "samples": [], "errors": []},
        "plan_products": {"tested_count": 0, "success_count": 0, "samples": [], "errors": []},
        "plan_materials": {
            "tested_count": 0,
            "success_count": 0,
            "samples": [],
            "errors": [],
            "material_type_stats": {item: {"tested": 0, "success": 0, "rows": 0} for item in PLAN_MATERIAL_TYPES},
        },
        "original_video_flag": {"ok": False, "sample_material_count": 0, "original_material_count": 0, "errors": []},
        "uni_promotion_config": {"tested_count": 0, "success_count": 0, "errors": []},
        "uni_promotion_data": {"tested_count": 0, "success_count": 0, "errors": []},
    }

    topic_registry: dict[str, dict[str, Any]] = {}
    for advertiser_id in config_accounts:
        endpoint_checks["uni_promotion_config"]["tested_count"] += 1
        try:
            response = client.get_uni_promotion_config(advertiser_id, UNI_PROMOTION_DATA_TOPICS)
        except Exception as exc:  # noqa: BLE001
            endpoint_checks["uni_promotion_config"]["errors"].append(
                {"advertiser_id": advertiser_id, "error": short_error(exc)}
            )
            continue
        endpoint_checks["uni_promotion_config"]["success_count"] += 1
        merge_topic_registry(topic_registry, advertiser_id, response)

    topic_rows: list[dict[str, Any]] = []
    for topic in sorted(topic_registry):
        entry = topic_registry[topic]
        dimensions = list(entry["dimensions"].values())
        metrics = list(entry["metrics"].values())
        required_dimensions = [item["field"] for item in dimensions if item.get("is_required")]
        topic_rows.append(
            {
                "data_topic": topic,
                "advertiser_ids": entry["advertiser_ids"],
                "probe_advertiser_id": entry["probe_advertiser_id"],
                "query_limit": entry["query_limit"] or {},
                "dimension_count": len(dimensions),
                "metric_count": len(metrics),
                "required_dimensions": required_dimensions,
                "dimensions": dimensions,
                "metrics": metrics,
                "probe": {},
            }
        )

    for item in topic_rows:
        endpoint_checks["uni_promotion_data"]["tested_count"] += 1
        dimensions = choose_probe_dimensions(item)
        metrics = choose_probe_metrics(item, args.max_topic_metrics)
        if not dimensions or not metrics:
            item["probe"] = {
                "ok": False,
                "error": "missing probe dimensions or metrics",
            }
            endpoint_checks["uni_promotion_data"]["errors"].append(
                {"data_topic": item["data_topic"], "error": "missing probe dimensions or metrics"}
            )
            continue
        try:
            response = client.get_uni_promotion_data(
                advertiser_id=int(item["probe_advertiser_id"]),
                data_topic=item["data_topic"],
                dimensions=dimensions,
                metrics=metrics,
                start_time=start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                end_time=end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                filters=[],
                order_by=[{"field": metrics[0], "type": 1}],
                page=1,
                page_size=normalize_allowed_page_size(args.sample_rows, [10, 20, 50, 100]),
            )
            item["probe"] = {
                "ok": True,
                "dimensions": dimensions,
                "metrics": metrics,
                **topic_probe_summary(response),
            }
            endpoint_checks["uni_promotion_data"]["success_count"] += 1
        except Exception as exc:  # noqa: BLE001
            item["probe"] = {
                "ok": False,
                "dimensions": dimensions,
                "metrics": metrics,
                "error": short_error(exc),
            }
            endpoint_checks["uni_promotion_data"]["errors"].append(
                {"data_topic": item["data_topic"], "error": short_error(exc)}
            )

    video_material_ids: dict[int, list[str]] = defaultdict(list)
    for plan in sample_plans:
        endpoint_checks["plan_detail"]["tested_count"] += 1
        try:
            detail = client.get_plan_detail(plan.advertiser_id, plan.ad_id)
            data = detail.get("data") or {}
            endpoint_checks["plan_detail"]["success_count"] += 1
            endpoint_checks["plan_detail"]["samples"].append(
                {
                    "advertiser_id": plan.advertiser_id,
                    "ad_id": plan.ad_id,
                    "ad_name": plan.ad_name,
                    "top_level_keys": sorted(data.keys()),
                    "product_infos": len(data.get("product_infos") or []),
                    "room_info": len(data.get("room_info") or []),
                    "has_creative_setting": bool(data.get("creative_setting")),
                    "has_delivery_setting": bool(data.get("delivery_setting")),
                }
            )
        except Exception as exc:  # noqa: BLE001
            endpoint_checks["plan_detail"]["errors"].append(
                {"advertiser_id": plan.advertiser_id, "ad_id": plan.ad_id, "error": short_error(exc)}
            )

        endpoint_checks["plan_products"]["tested_count"] += 1
        try:
            products = client.get_plan_products(
                advertiser_id=plan.advertiser_id,
                ad_id=plan.ad_id,
                start_date=start_date,
                end_date=end_date,
                fields=PLAN_PRODUCT_FIELDS,
                page=1,
                page_size=normalize_allowed_page_size(args.sample_rows, [10, 20, 50, 100]),
            )
            data = products.get("data") or {}
            product_list = data.get("product_list") or []
            sample_product = product_list[0] if product_list else {}
            endpoint_checks["plan_products"]["success_count"] += 1
            endpoint_checks["plan_products"]["samples"].append(
                {
                    "advertiser_id": plan.advertiser_id,
                    "ad_id": plan.ad_id,
                    "ad_name": plan.ad_name,
                    "row_count": len(product_list),
                    "sample_product_keys": sorted((sample_product.get("product_info") or {}).keys()),
                    "sample_stats_keys": sorted((sample_product.get("stats_info") or {}).keys()),
                }
            )
        except Exception as exc:  # noqa: BLE001
            endpoint_checks["plan_products"]["errors"].append(
                {"advertiser_id": plan.advertiser_id, "ad_id": plan.ad_id, "error": short_error(exc)}
            )

        for material_type in PLAN_MATERIAL_TYPES:
            endpoint_checks["plan_materials"]["tested_count"] += 1
            endpoint_checks["plan_materials"]["material_type_stats"][material_type]["tested"] += 1
            filtering = {
                "material_type": material_type,
                "start_date": start_date,
                "end_date": end_date,
                "material_status": "ALL",
            }
            if material_type == "VIDEO":
                filtering["video_type"] = "ALL"
            try:
                materials = client.get_plan_materials(
                    advertiser_id=plan.advertiser_id,
                    ad_id=plan.ad_id,
                    filtering=filtering,
                    fields=PLAN_MATERIAL_FIELDS,
                    page=1,
                    page_size=normalize_allowed_page_size(args.sample_rows, [10, 20, 50, 100]),
                )
                data = materials.get("data") or {}
                rows = data.get("ad_material_infos") or []
                sample_row = rows[0] if rows else {}
                endpoint_checks["plan_materials"]["success_count"] += 1
                endpoint_checks["plan_materials"]["material_type_stats"][material_type]["success"] += 1
                endpoint_checks["plan_materials"]["material_type_stats"][material_type]["rows"] += len(rows)
                endpoint_checks["plan_materials"]["samples"].append(
                    {
                        "advertiser_id": plan.advertiser_id,
                        "ad_id": plan.ad_id,
                        "ad_name": plan.ad_name,
                        "material_type": material_type,
                        "row_count": len(rows),
                        "sample_material_keys": sorted((sample_row.get("material_info") or {}).keys()),
                        "sample_stats_keys": sorted((sample_row.get("stats_info") or {}).keys()),
                    }
                )
                if material_type == "VIDEO":
                    for row in rows:
                        material_info = (row.get("material_info") or {}).get("video_material") or {}
                        material_id = material_info.get("material_id")
                        if material_id:
                            video_material_ids[plan.advertiser_id].append(str(material_id))
            except Exception as exc:  # noqa: BLE001
                endpoint_checks["plan_materials"]["errors"].append(
                    {
                        "advertiser_id": plan.advertiser_id,
                        "ad_id": plan.ad_id,
                        "material_type": material_type,
                        "error": short_error(exc),
                    }
                )

    if video_material_ids:
        advertiser_id = sorted(video_material_ids)[0]
        material_ids = unique_strings(video_material_ids[advertiser_id])[:20]
        endpoint_checks["original_video_flag"]["sample_material_count"] = len(material_ids)
        try:
            response = client.get_original_videos(advertiser_id, material_ids)
            data = response.get("data") or {}
            endpoint_checks["original_video_flag"]["ok"] = True
            endpoint_checks["original_video_flag"]["original_material_count"] = len(data.get("original_material_ids") or [])
            endpoint_checks["original_video_flag"]["sample_original_material_ids"] = (data.get("original_material_ids") or [])[:10]
        except Exception as exc:  # noqa: BLE001
            endpoint_checks["original_video_flag"]["errors"].append(short_error(exc))

    snapshot = {
        "generated_at": now_local(config["timezone"]).strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": config["timezone"],
        "customer_center_id": config["customer_center_id"],
        "window_start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "window_end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "account_overview": {
            "account_count": len(accounts),
            "active_account_count": sum(1 for item in summaries if item.ok and item.stat_cost > 0),
            "plan_count": len(plans),
            "active_plan_count": sum(1 for item in plans if item.stat_cost > 0),
        },
        "endpoint_checks": endpoint_checks,
        "accounts": [summary_to_dict(item) for item in summaries],
        "sample_plans": [plan_to_dict(item) for item in sample_plans],
        "data_topics": topic_rows,
    }
    snapshot["granularity_matrix"] = build_granularity_matrix(snapshot)

    timestamp = now_local(config["timezone"]).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"capability_snapshot_{timestamp}.json"
    latest_json_path = output_dir / "capability_snapshot_latest.json"
    md_path = output_dir / f"capability_snapshot_{timestamp}.md"
    latest_md_path = output_dir / "capability_snapshot_latest.md"

    dump_json(json_path, snapshot)
    dump_json(latest_json_path, snapshot)
    markdown = build_markdown(snapshot)
    md_path.write_text(markdown, encoding="utf-8")
    latest_md_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
