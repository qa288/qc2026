#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    import redis
    from redis.exceptions import LockError as RedisLockError
except Exception:  # noqa: BLE001
    redis = None
    RedisLockError = Exception


ACCESS_TOKEN_URL = "https://ad.oceanengine.com/open_api/oauth2/access_token/"
REFRESH_URL = "https://ad.oceanengine.com/open_api/oauth2/refresh_token/"
CUSTOMER_CENTER_URL = "https://ad.oceanengine.com/open_api/2/customer_center/advertiser/list/"
ACCOUNT_FUND_URL = "https://api.oceanengine.com/open_api/v3.0/account/fund/get/"
ACCOUNT_REPORT_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/report/uni_promotion/get/"
PLAN_LIST_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/uni_promotion/list/"
UNI_PROMOTION_CONFIG_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/report/uni_promotion/config/get/"
UNI_PROMOTION_DATA_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/report/uni_promotion/data/get/"
PLAN_DETAIL_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/uni_promotion/ad/detail/"
PLAN_PRODUCT_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/uni_promotion/ad/product/get/"
PLAN_MATERIAL_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/uni_promotion/ad/material/get/"
VIDEO_ORIGINAL_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/file/video/original/get/"

REPORT_FIELDS = [
    "stat_cost",
    "total_prepay_and_pay_order_roi2",
    "total_pay_order_count_for_roi2",
    "total_pay_order_gmv_for_roi2",
]

PLAN_REPORT_FIELDS = [
    "stat_cost",
    "total_prepay_and_pay_order_roi2",
    "total_pay_order_count_for_roi2",
    "total_pay_order_gmv_for_roi2",
]

UNI_PROMOTION_DATA_TOPICS = [
    "ROI2_IMAGE_AGG_MATERIAL_ANALYSIS",
    "SITE_PROMOTION_POST_DATA_LIVE",
    "SITE_PROMOTION_POST_DATA_OTHER",
    "SITE_PROMOTION_POST_DATA_TITLE",
    "SITE_PROMOTION_POST_DATA_VIDEO",
    "SITE_PROMOTION_PRODUCT_AD",
    "SITE_PROMOTION_PRODUCT_POST_ASSIST_TASK",
    "SITE_PROMOTION_PRODUCT_POST_DATA_IMAGE",
    "SITE_PROMOTION_PRODUCT_POST_DATA_OTHER",
    "SITE_PROMOTION_PRODUCT_POST_DATA_TITLE",
    "SITE_PROMOTION_PRODUCT_POST_DATA_VIDEO",
    "SITE_PROMOTION_PRODUCT_PRODUCT",
]

PLAN_PRODUCT_FIELDS = [
    "product_show_count_for_roi2",
    "product_click_count_for_roi2",
    "stat_cost_for_roi2",
    "total_pay_order_count_for_roi2",
    "total_pay_order_gmv_for_roi2",
    "total_prepay_and_pay_order_roi2",
]

PLAN_MATERIAL_FIELDS = [
    "product_show_count_for_roi2",
    "product_click_count_for_roi2",
    "stat_cost_for_roi2",
    "total_pay_order_count_for_roi2",
    "total_pay_order_gmv_for_roi2",
    "total_prepay_and_pay_order_roi2",
]

PLAN_MATERIAL_TYPES = ["VIDEO", "IMAGE", "TITLE", "CAROUSEL", "LIVE_ROOM"]
TOKEN_LOCK_KEY = os.environ.get("OCEANENGINE_TOKEN_LOCK_KEY", "qianchuan:oauth:refresh")
TOKEN_LOCK_TIMEOUT_SECONDS = int(os.environ.get("OCEANENGINE_TOKEN_LOCK_TIMEOUT_SECONDS", "120") or 120)
TOKEN_LOCK_BLOCKING_TIMEOUT_SECONDS = int(
    os.environ.get("OCEANENGINE_TOKEN_LOCK_BLOCKING_TIMEOUT_SECONDS", "150") or 150
)

PLAN_MONEY_SCALE = 100000.0
ACCOUNT_FUND_MONEY_SCALE = 100.0
RETRYABLE_API_CODES = {40100, 50000}

DELIVERY_STATUS_LABELS = {
    "DELIVERY_OK": "投放中",
    "DISABLE": "已暂停",
    "SYSTEM_DISABLE": "系统暂停",
    "DELETE": "已删除",
    "REMOVED": "已删除",
    "AUDIT_PENDING": "审核中",
    "AUDIT_DENY": "审核拒绝",
}

OPT_STATUS_LABELS = {
    "ENABLE": "已启用",
    "DISABLE": "已停用",
    "ROI2_DISABLE": "ROI保护暂停",
}

MARKETING_GOAL_LABELS = {
    "VIDEO_PROM_GOODS": "商品全域推广",
    "LIVE_PROM_GOODS": "直播间全域推广",
    "ALL": "全部营销目标",
}

PLAN_STATUS_PAIR_LABELS = {
    ("DELIVERY_OK", "ENABLE"): "投放中",
    ("DISABLE", "DISABLE"): "已暂停",
    ("SYSTEM_DISABLE", "ROI2_DISABLE"): "系统暂停",
}


@dataclass
class AccountSummary:
    advertiser_id: int
    advertiser_name: str
    stat_cost: float
    roi: float
    order_count: int
    pay_amount: float
    ok: bool = True
    error: str | None = None


@dataclass
class PlanSummary:
    advertiser_id: int
    advertiser_name: str
    ad_id: int
    ad_name: str
    product_id: str
    product_name: str
    anchor_name: str
    marketing_goal: str
    status: str
    opt_status: str
    roi_goal: float
    stat_cost: float
    roi: float
    order_count: int
    pay_amount: float


class ApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class CsvParam:
    values: list[Any]


def plan_delivery_status_label(status: str) -> str:
    text = str(status or "").strip()
    if not text:
        return "未知状态"
    return DELIVERY_STATUS_LABELS.get(text, text)


def plan_opt_status_label(opt_status: str) -> str:
    text = str(opt_status or "").strip()
    if not text:
        return "未知操作"
    return OPT_STATUS_LABELS.get(text, text)


def format_plan_status_text(status: str, opt_status: str) -> str:
    status_text = str(status or "").strip()
    opt_text = str(opt_status or "").strip()
    pair = PLAN_STATUS_PAIR_LABELS.get((status_text, opt_text))
    if pair:
        return pair
    delivery = plan_delivery_status_label(status_text)
    operation = plan_opt_status_label(opt_text)
    if not opt_text:
        return delivery
    if delivery == operation:
        return delivery
    return f"{delivery} / {operation}"


def plan_marketing_goal_label(marketing_goal: str) -> str:
    text = str(marketing_goal or "").strip()
    if not text:
        return "未设置"
    return MARKETING_GOAL_LABELS.get(text, text)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _env_text(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _env_int(name: str) -> int | None:
    value = _env_text(name)
    if value is None:
        return None
    return int(value)


def _env_list(name: str) -> list[str] | None:
    value = _env_text(name)
    if value is None:
        return None
    if value.startswith("["):
        payload = json.loads(value)
        return [str(item).strip() for item in payload if str(item).strip()]
    return [item.strip() for item in value.split(",") if item.strip()]


def build_runtime_config(base_config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = {
        "timezone": "Asia/Shanghai",
        "account_source": "QIANCHUAN",
        "marketing_goal": "ALL",
        "order_platform": "QIANCHUAN",
        "max_workers": 6,
        "plan_max_workers": 2,
        "detail_sync_workers": 2,
        "detail_sync_plan_limit": 0,
        "detail_material_types": list(PLAN_MATERIAL_TYPES),
        "max_plan_rows": 30,
        "plan_page_size": 100,
        "plan_marketing_goals": ["VIDEO_PROM_GOODS", "LIVE_PROM_GOODS"],
    }
    if base_config:
        config.update(base_config)

    text_fields = {
        "app_id": "APP_ID",
        "app_secret": "APP_SECRET",
        "refresh_token": "REFRESH_TOKEN",
        "customer_center_id": "CUSTOMER_CENTER_ID",
        "feishu_target": "FEISHU_TARGET",
        "timezone": "TIMEZONE",
        "account_source": "ACCOUNT_SOURCE",
        "marketing_goal": "MARKETING_GOAL",
        "order_platform": "ORDER_PLATFORM",
    }
    int_fields = {
        "max_workers": "MAX_WORKERS",
        "plan_max_workers": "PLAN_MAX_WORKERS",
        "detail_sync_workers": "DETAIL_SYNC_WORKERS",
        "detail_sync_plan_limit": "DETAIL_SYNC_PLAN_LIMIT",
        "max_plan_rows": "MAX_PLAN_ROWS",
        "plan_page_size": "PLAN_PAGE_SIZE",
    }
    list_fields = {
        "detail_material_types": "DETAIL_MATERIAL_TYPES",
        "plan_marketing_goals": "PLAN_MARKETING_GOALS",
    }

    for key, env_name in text_fields.items():
        value = _env_text(env_name)
        if value is not None:
            config[key] = value
    for key, env_name in int_fields.items():
        value = _env_int(env_name)
        if value is not None:
            config[key] = value
    for key, env_name in list_fields.items():
        value = _env_list(env_name)
        if value is not None:
            config[key] = value

    missing = [key for key in ("app_id", "app_secret", "refresh_token", "customer_center_id") if not str(config.get(key) or "").strip()]
    if missing:
        missing_text = ", ".join(missing)
        raise RuntimeError(f"missing required config: {missing_text}")
    return config


def load_runtime_config(config_path: Path | None) -> dict[str, Any]:
    base_config: dict[str, Any] = {}
    if config_path and config_path.exists():
        base_config = load_json(config_path)
    return build_runtime_config(base_config)


def post_json(url: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ApiError(f"HTTP {exc.code}: {body}") from exc


def get_json(url: str, access_token: str, params: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    encoded: dict[str, str] = {}
    for key, value in params.items():
        if isinstance(value, CsvParam):
            encoded[key] = ",".join(str(item) for item in value.values)
        elif isinstance(value, (list, dict)):
            encoded[key] = json.dumps(value, ensure_ascii=False)
        else:
            encoded[key] = str(value)
    query = urllib.parse.urlencode(encoded)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"Access-Token": access_token},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ApiError(f"HTTP {exc.code}: {body}") from exc


def get_json_with_retries(
    url: str,
    access_token: str,
    params: dict[str, Any],
    timeout: int = 30,
    attempts: int = 4,
    base_delay: float = 1.0,
) -> dict[str, Any]:
    last_error: Exception | None = None
    last_response: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = get_json(url, access_token, params, timeout=timeout)
        except ApiError as exc:
            last_error = exc
            if attempt >= attempts:
                raise
        else:
            code = int(response.get("code", 0) or 0)
            if code not in RETRYABLE_API_CODES or attempt >= attempts:
                return response
            last_response = response
        time.sleep(base_delay * (2 ** (attempt - 1)))
    if last_response is not None:
        return last_response
    if last_error is not None:
        raise ApiError(str(last_error)) from last_error
    raise ApiError("request failed without response")


class OceanEngineClient:
    def __init__(
        self,
        config: dict[str, Any],
        token_cache_path: Path,
        latest_token_path: Path | None = None,
        token_persist_callback: Any | None = None,
    ) -> None:
        self.config = config
        self.token_cache_path = token_cache_path
        self.latest_token_path = latest_token_path or token_cache_path
        self.token_persist_callback = token_persist_callback
        self._token_cache: dict[str, Any] | None = None
        self._redis_client: Any | None = None

    def _load_token_cache(self) -> dict[str, Any]:
        if self._token_cache is not None:
            return self._token_cache
        if self.latest_token_path.exists():
            self._token_cache = load_json(self.latest_token_path)
        elif self.token_cache_path.exists():
            self._token_cache = load_json(self.token_cache_path)
        else:
            self._token_cache = {}
        return self._token_cache

    def _reload_token_cache(self) -> dict[str, Any]:
        self._token_cache = None
        return self._load_token_cache()

    def _redis(self) -> Any | None:
        redis_url = str(os.environ.get("REDIS_URL") or "").strip()
        if not redis_url or redis is None:
            return None
        if self._redis_client is None:
            self._redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        return self._redis_client

    @contextmanager
    def _token_refresh_lock(self) -> Any:
        client = self._redis()
        if client is None:
            yield
            return
        lock_key = f"{TOKEN_LOCK_KEY}:{self.config.get('app_id')}:{self.config.get('customer_center_id')}"
        lock = client.lock(
            lock_key,
            timeout=TOKEN_LOCK_TIMEOUT_SECONDS,
            blocking_timeout=TOKEN_LOCK_BLOCKING_TIMEOUT_SECONDS,
        )
        acquired = lock.acquire(blocking=True)
        if not acquired:
            raise ApiError(f"acquire token refresh lock failed: {lock_key}")
        try:
            yield
        finally:
            try:
                lock.release()
            except RedisLockError:
                pass

    def _normalize_token_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized["app_id"] = str(self.config.get("app_id") or "")
        normalized["customer_center_id"] = str(self.config.get("customer_center_id") or "")
        return normalized

    def _save_token_cache(self, payload: dict[str, Any]) -> None:
        normalized = self._normalize_token_record(payload)
        dump_json(self.token_cache_path, normalized)
        os.chmod(self.token_cache_path, 0o600)
        if self.latest_token_path != self.token_cache_path:
            dump_json(self.latest_token_path, normalized)
            os.chmod(self.latest_token_path, 0o600)
        self._token_cache = normalized
        if callable(self.token_persist_callback):
            self.token_persist_callback(normalized)

    def latest_token_payload(self) -> dict[str, Any]:
        if self.latest_token_path.exists():
            return self._normalize_token_record(load_json(self.latest_token_path))
        if self.token_cache_path.exists():
            return self._normalize_token_record(load_json(self.token_cache_path))
        return self._normalize_token_record({})

    def exchange_auth_code(self, auth_code: str) -> dict[str, Any]:
        now = int(time.time())
        payload = {
            "app_id": self.config["app_id"],
            "secret": self.config["app_secret"],
            "grant_type": "auth_code",
            "auth_code": str(auth_code).strip(),
        }
        response = post_json(ACCESS_TOKEN_URL, payload)
        if response.get("code") != 0:
            raise ApiError(f"exchange auth_code failed: {response}")
        data = response["data"]
        refreshed = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": now + int(data["expires_in"]),
            "refresh_token_expires_in": data.get("refresh_token_expires_in"),
            "updated_at": now,
        }
        self._save_token_cache(refreshed)
        return self.latest_token_payload()

    def get_access_token(self) -> str:
        cache = self._load_token_cache()
        now = int(time.time())
        if cache.get("access_token") and cache.get("expires_at", 0) > now + 300:
            return str(cache["access_token"])
        with self._token_refresh_lock():
            cache = self._reload_token_cache()
            now = int(time.time())
            if cache.get("access_token") and cache.get("expires_at", 0) > now + 300:
                return str(cache["access_token"])
            refresh_token = str(cache.get("refresh_token") or self.config["refresh_token"])
            payload = {
                "app_id": self.config["app_id"],
                "secret": self.config["app_secret"],
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
            response = post_json(REFRESH_URL, payload)
            if response.get("code") != 0:
                raise ApiError(f"refresh token failed: {response}")
            data = response["data"]
            refreshed = {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_at": now + int(data["expires_in"]),
                "refresh_token_expires_in": data.get("refresh_token_expires_in"),
                "updated_at": now,
            }
            self._save_token_cache(refreshed)
            return str(refreshed["access_token"])

    def list_accounts(self) -> list[dict[str, Any]]:
        access_token = self.get_access_token()
        page = 1
        page_size = 100
        results: list[dict[str, Any]] = []
        while True:
            params = {
                "cc_account_id": self.config["customer_center_id"],
                "account_source": self.config["account_source"],
                "page": page,
                "page_size": page_size,
            }
            response = get_json_with_retries(CUSTOMER_CENTER_URL, access_token, params)
            if response.get("code") != 0:
                raise ApiError(f"list accounts failed: {response}")
            data = response["data"]
            results.extend(data.get("list", []))
            page_info = data.get("page_info", {})
            total_page = int(page_info.get("total_page", 1) or 1)
            if page >= total_page:
                return results
            page += 1

    def get_account_funds(
        self,
        account_ids: list[int],
        account_type: str = "QIANCHUAN",
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        params = {
            "account_ids": [int(item) for item in account_ids],
            "account_type": account_type,
        }
        response = get_json_with_retries(ACCOUNT_FUND_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get account funds failed: {response}")
        return response

    def list_account_funds(
        self,
        account_ids: list[int],
        account_type: str = "QIANCHUAN",
        batch_size: int = 20,
    ) -> list[dict[str, Any]]:
        normalized = [int(item) for item in account_ids if int(item)]
        if not normalized:
            return []
        rows: list[dict[str, Any]] = []
        for start_index in range(0, len(normalized), batch_size):
            batch = normalized[start_index : start_index + batch_size]
            response = self.get_account_funds(batch, account_type=account_type)
            data = response.get("data") or {}
            rows.extend(data.get("list") or [])
        return rows

    def get_uni_promotion_config(
        self,
        advertiser_id: int,
        data_topics: list[str] | None = None,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        params = {
            "advertiser_id": advertiser_id,
            "data_topics": list(data_topics or UNI_PROMOTION_DATA_TOPICS),
        }
        response = get_json_with_retries(UNI_PROMOTION_CONFIG_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get uni promotion config failed: {response}")
        return response

    def get_uni_promotion_data(
        self,
        advertiser_id: int,
        data_topic: str,
        dimensions: list[str],
        metrics: list[str],
        start_time: str,
        end_time: str,
        filters: list[dict[str, Any]] | None = None,
        order_by: list[dict[str, Any]] | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        params: dict[str, Any] = {
            "advertiser_id": advertiser_id,
            "data_topic": data_topic,
            "dimensions": dimensions,
            "metrics": metrics,
            "start_time": start_time,
            "end_time": end_time,
            "page": page,
            "page_size": page_size,
        }
        if filters is not None:
            params["filters"] = filters
        if order_by:
            params["order_by"] = order_by
        response = get_json_with_retries(UNI_PROMOTION_DATA_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get uni promotion data failed: {response}")
        return response

    def get_plan_detail(self, advertiser_id: int, ad_id: int) -> dict[str, Any]:
        access_token = self.get_access_token()
        params = {
            "advertiser_id": advertiser_id,
            "ad_id": ad_id,
        }
        response = get_json_with_retries(PLAN_DETAIL_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get plan detail failed: {response}")
        return response

    def get_plan_products(
        self,
        advertiser_id: int,
        ad_id: int,
        start_date: str,
        end_date: str,
        fields: list[str] | None = None,
        filtering: dict[str, Any] | None = None,
        order_type: str | None = None,
        order_field: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        params: dict[str, Any] = {
            "advertiser_id": advertiser_id,
            "ad_id": ad_id,
            "start_date": start_date,
            "end_date": end_date,
            "fields": list(fields or PLAN_PRODUCT_FIELDS),
            "page": page,
            "page_size": page_size,
        }
        if filtering:
            params["filtering"] = filtering
        if order_type:
            params["order_type"] = order_type
        if order_field:
            params["order_field"] = order_field
        response = get_json_with_retries(PLAN_PRODUCT_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get plan products failed: {response}")
        return response

    def list_plan_products(
        self,
        advertiser_id: int,
        ad_id: int,
        start_date: str,
        end_date: str,
        fields: list[str] | None = None,
        filtering: dict[str, Any] | None = None,
        order_type: str | None = None,
        order_field: str | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        page = 1
        rows: list[dict[str, Any]] = []
        while True:
            response = self.get_plan_products(
                advertiser_id=advertiser_id,
                ad_id=ad_id,
                start_date=start_date,
                end_date=end_date,
                fields=fields,
                filtering=filtering,
                order_type=order_type,
                order_field=order_field,
                page=page,
                page_size=page_size,
            )
            data = response.get("data") or {}
            rows.extend(data.get("product_list") or [])
            page_info = data.get("page_info") or {}
            total_page = int(page_info.get("total_page", 1) or 1)
            if page >= total_page:
                break
            page += 1
        return rows

    def get_plan_materials(
        self,
        advertiser_id: int,
        ad_id: int,
        filtering: dict[str, Any],
        fields: list[str] | None = None,
        order_type: str | None = None,
        order_field: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        params: dict[str, Any] = {
            "advertiser_id": advertiser_id,
            "ad_id": ad_id,
            "filtering": filtering,
            "page": page,
            "page_size": page_size,
        }
        if fields:
            params["fields"] = list(fields)
        if order_type:
            params["order_type"] = order_type
        if order_field:
            params["order_field"] = order_field
        response = get_json_with_retries(PLAN_MATERIAL_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get plan materials failed: {response}")
        return response

    def list_plan_materials(
        self,
        advertiser_id: int,
        ad_id: int,
        filtering: dict[str, Any],
        fields: list[str] | None = None,
        order_type: str | None = None,
        order_field: str | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        page = 1
        rows: list[dict[str, Any]] = []
        while True:
            response = self.get_plan_materials(
                advertiser_id=advertiser_id,
                ad_id=ad_id,
                filtering=filtering,
                fields=fields,
                order_type=order_type,
                order_field=order_field,
                page=page,
                page_size=page_size,
            )
            data = response.get("data") or {}
            rows.extend(data.get("ad_material_infos") or [])
            page_info = data.get("page_info") or {}
            total_page = int(page_info.get("total_page", 1) or 1)
            if page >= total_page:
                break
            page += 1
        return rows

    def get_original_videos(self, advertiser_id: int, material_ids: list[str]) -> dict[str, Any]:
        access_token = self.get_access_token()
        params = {
            "advertiser_id": advertiser_id,
            "material_ids": [str(item) for item in material_ids],
        }
        response = get_json_with_retries(VIDEO_ORIGINAL_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get original videos failed: {response}")
        return response

    def get_account_summary(self, advertiser_id: int, advertiser_name: str, start_dt: datetime, end_dt: datetime) -> AccountSummary:
        try:
            access_token = self.get_access_token()
            params = {
                "advertiser_id": advertiser_id,
                "start_date": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "marketing_goal": self.config["marketing_goal"],
                "order_platform": self.config["order_platform"],
                "fields": REPORT_FIELDS,
            }
            response = get_json_with_retries(ACCOUNT_REPORT_URL, access_token, params)
            if response.get("code") != 0:
                return AccountSummary(
                    advertiser_id=advertiser_id,
                    advertiser_name=advertiser_name,
                    stat_cost=0.0,
                    roi=0.0,
                    order_count=0,
                    pay_amount=0.0,
                    ok=False,
                    error=response.get("message", "unknown error"),
                )
            data = response.get("data") or {}
            return AccountSummary(
                advertiser_id=advertiser_id,
                advertiser_name=advertiser_name,
                stat_cost=round(float(data.get("stat_cost", 0.0) or 0.0), 2),
                roi=round(float(data.get("total_prepay_and_pay_order_roi2", 0.0) or 0.0), 2),
                order_count=int(float(data.get("total_pay_order_count_for_roi2", 0.0) or 0.0)),
                pay_amount=round(float(data.get("total_pay_order_gmv_for_roi2", 0.0) or 0.0), 2),
            )
        except Exception as exc:  # noqa: BLE001
            return AccountSummary(
                advertiser_id=advertiser_id,
                advertiser_name=advertiser_name,
                stat_cost=0.0,
                roi=0.0,
                order_count=0,
                pay_amount=0.0,
                ok=False,
                error=str(exc),
            )

    def list_plan_summaries(
        self,
        advertiser_id: int,
        advertiser_name: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[PlanSummary]:
        access_token = self.get_access_token()
        page_size = normalize_plan_page_size(self.config)
        plans: list[PlanSummary] = []
        for marketing_goal in get_plan_marketing_goals(self.config):
            page = 1
            while True:
                params = {
                    "advertiser_id": advertiser_id,
                    "start_time": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "end_time": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "marketing_goal": marketing_goal,
                    "page": page,
                    "page_size": page_size,
                    "fields": PLAN_REPORT_FIELDS,
                }
                response = get_json_with_retries(PLAN_LIST_URL, access_token, params)
                if response.get("code") != 0:
                    raise ApiError(f"list plans failed: {response}")
                data = response.get("data") or {}
                for item in data.get("ad_list", []):
                    ad_info = item.get("ad_info") or {}
                    stats_info = item.get("stats_info") or {}
                    product_items = item.get("product_info") or []
                    room_items = item.get("room_info") or []
                    first_product = product_items[0] if product_items else {}
                    first_room = room_items[0] if room_items else {}
                    plans.append(
                        PlanSummary(
                            advertiser_id=advertiser_id,
                            advertiser_name=advertiser_name,
                            ad_id=int(ad_info.get("id", 0) or 0),
                            ad_name=str(ad_info.get("name") or f"ad_{ad_info.get('id', 0)}"),
                            product_id=str(first_product.get("product_id") or ""),
                            product_name=str(first_product.get("product_name") or ""),
                            anchor_name=str(first_room.get("anchor_name") or ""),
                            marketing_goal=str(ad_info.get("marketing_goal") or marketing_goal),
                            status=str(ad_info.get("status") or ""),
                            opt_status=str(ad_info.get("opt_status") or ""),
                            roi_goal=round(float(ad_info.get("roi2_goal", 0.0) or 0.0), 2),
                            stat_cost=normalize_plan_money(stats_info.get("stat_cost")),
                            roi=round(float(stats_info.get("total_prepay_and_pay_order_roi2", 0.0) or 0.0), 2),
                            order_count=int(float(stats_info.get("total_pay_order_count_for_roi2", 0.0) or 0.0)),
                            pay_amount=normalize_plan_money(stats_info.get("total_pay_order_gmv_for_roi2")),
                        )
                    )
                page_info = data.get("page_info") or {}
                total_page = int(page_info.get("total_page", 1) or 1)
                if page >= total_page:
                    break
                page += 1
        return plans


def build_window(mode: str, tz_name: str) -> tuple[datetime, datetime, str, str]:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    if mode == "daily":
        target_date = (now - timedelta(days=1)).date()
        start_dt = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=tz)
        end_dt = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, tzinfo=tz)
        title = "巨量千川昨日报简"
        window_label = target_date.isoformat()
        return start_dt, end_dt, title, window_label
    start_dt = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=tz)
    end_dt = now
    title = "巨量千川10分钟播报"
    window_label = f"{start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%H:%M')}"
    return start_dt, end_dt, title, window_label


def format_money(value: float) -> str:
    return f"{value:,.2f}"


def normalize_plan_money(value: Any) -> float:
    return round(float(value or 0.0) / PLAN_MONEY_SCALE, 2)


def normalize_account_fund_money(value: Any) -> float:
    return round(float(value or 0.0) / ACCOUNT_FUND_MONEY_SCALE, 2)


def get_plan_marketing_goals(config: dict[str, Any]) -> list[str]:
    values = config.get("plan_marketing_goals") or ["VIDEO_PROM_GOODS", "LIVE_PROM_GOODS"]
    goals: list[str] = []
    for value in values:
        text = str(value)
        if text in {"VIDEO_PROM_GOODS", "LIVE_PROM_GOODS"} and text not in goals:
            goals.append(text)
    return goals or ["VIDEO_PROM_GOODS", "LIVE_PROM_GOODS"]


def normalize_plan_page_size(config: dict[str, Any]) -> int:
    value = int(config.get("plan_page_size", 100) or 100)
    if value in {10, 20, 50, 100, 200}:
        return value
    return 100


def fetch_account_bundle(
    client: "OceanEngineClient", item: dict[str, Any], start_dt: datetime, end_dt: datetime
) -> AccountSummary:
    advertiser_id = int(item["advertiser_id"])
    advertiser_name = str(item["advertiser_name"])
    return client.get_account_summary(advertiser_id, advertiser_name, start_dt, end_dt)


def fetch_plan_bundle(
    client: "OceanEngineClient",
    item: dict[str, Any],
    start_dt: datetime,
    end_dt: datetime,
) -> tuple[list[PlanSummary], str | None]:
    advertiser_id = int(item["advertiser_id"])
    advertiser_name = str(item["advertiser_name"])
    try:
        return client.list_plan_summaries(advertiser_id, advertiser_name, start_dt, end_dt), None
    except Exception as exc:  # noqa: BLE001
        return [], f"{advertiser_name}: {exc}"


def apply_account_rollup_fallback(
    summaries: list[AccountSummary],
    plans: list[PlanSummary],
    plan_failure_ids: set[int] | None = None,
) -> tuple[list[AccountSummary], list[AccountSummary]]:
    failure_ids = set(plan_failure_ids or set())
    plan_rollups: dict[int, dict[str, Any]] = {}
    for item in plans:
        bucket = plan_rollups.setdefault(
            int(item.advertiser_id),
            {
                "advertiser_name": item.advertiser_name,
                "stat_cost": 0.0,
                "pay_amount": 0.0,
                "order_count": 0,
            },
        )
        bucket["stat_cost"] = round(bucket["stat_cost"] + float(item.stat_cost or 0.0), 2)
        bucket["pay_amount"] = round(bucket["pay_amount"] + float(item.pay_amount or 0.0), 2)
        bucket["order_count"] += int(item.order_count or 0)

    normalized: list[AccountSummary] = []
    hard_failures: list[AccountSummary] = []
    for summary in summaries:
        if summary.ok:
            normalized.append(summary)
            continue
        if summary.advertiser_id in failure_ids:
            normalized.append(summary)
            hard_failures.append(summary)
            continue
        fallback = plan_rollups.get(summary.advertiser_id, {})
        fallback_cost = round(float(fallback.get("stat_cost", 0.0) or 0.0), 2)
        fallback_pay = round(float(fallback.get("pay_amount", 0.0) or 0.0), 2)
        fallback_orders = int(fallback.get("order_count", 0) or 0)
        fallback_roi = round(fallback_pay / fallback_cost, 2) if fallback_cost > 0 else 0.0
        normalized.append(
            AccountSummary(
                advertiser_id=summary.advertiser_id,
                advertiser_name=summary.advertiser_name,
                stat_cost=fallback_cost,
                roi=fallback_roi,
                order_count=fallback_orders,
                pay_amount=fallback_pay,
                ok=True,
                error="fallback: plan rollup",
            )
        )
    return normalized, hard_failures


def build_report(mode: str, config: dict[str, Any], client: OceanEngineClient) -> tuple[str, dict[str, Any]]:
    start_dt, end_dt, title, window_label = build_window(mode, config["timezone"])
    accounts = client.list_accounts()
    max_workers = int(config.get("max_workers", 6) or 6)
    plan_max_workers = int(config.get("plan_max_workers", 2) or 2)
    summaries: list[AccountSummary] = []
    plans: list[PlanSummary] = []
    failures: list[AccountSummary] = []
    plan_failures: list[str] = []
    plan_failure_ids: set[int] = set()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(fetch_account_bundle, client, item, start_dt, end_dt): item
            for item in accounts
        }
        for future in as_completed(future_map):
            summary = future.result()
            if summary.ok:
                summaries.append(summary)
            else:
                failures.append(summary)
                summaries.append(summary)
    with ThreadPoolExecutor(max_workers=plan_max_workers) as pool:
        future_map = {
            pool.submit(fetch_plan_bundle, client, item, start_dt, end_dt): item
            for item in accounts
        }
        for future in as_completed(future_map):
            item = future_map[future]
            account_plans, plan_error = future.result()
            plans.extend(account_plans)
            if plan_error:
                plan_failures.append(plan_error)
                plan_failure_ids.add(int(item["advertiser_id"]))
    summaries, failures = apply_account_rollup_fallback(summaries, plans, plan_failure_ids)
    summaries.sort(key=lambda item: (-item.stat_cost, item.advertiser_id))
    total_cost = round(sum(item.stat_cost for item in summaries if item.ok), 2)
    total_pay = round(sum(item.pay_amount for item in summaries if item.ok), 2)
    total_orders = sum(item.order_count for item in summaries if item.ok)
    active_accounts = sum(1 for item in summaries if item.ok and item.stat_cost > 0)
    total_roi = round(total_pay / total_cost, 2) if total_cost > 0 else 0.0
    active_plans = [item for item in plans if item.stat_cost > 0]
    active_plans.sort(
        key=lambda item: (-item.order_count, -item.pay_amount, -item.roi, -item.stat_cost, item.ad_id)
    )
    max_plan_rows = int(config.get("max_plan_rows", 30) or 30)
    plan_rows = active_plans[:max_plan_rows]
    now_text = datetime.now(ZoneInfo(config["timezone"])).strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        title,
        f"时间：{now_text}",
        f"统计范围：{window_label}",
        (
            f"整体：账户 {len(summaries)} 个，活跃 {active_accounts} 个，"
            f"计划 {len(plans)} 条，活跃计划 {len(active_plans)} 条，"
            f"消耗 {format_money(total_cost)}，支付 {format_money(total_pay)}，订单 {total_orders}，ROI {total_roi:.2f}"
        ),
        "",
        "账户明细：",
    ]
    for index, item in enumerate(summaries, start=1):
        if item.ok:
            lines.append(
                f"{index}. {item.advertiser_name} | 消耗 {format_money(item.stat_cost)} | ROI {item.roi:.2f} | 订单 {item.order_count} | 支付 {format_money(item.pay_amount)}"
            )
        else:
            lines.append(f"{index}. {item.advertiser_name} | 查询失败 | {item.error}")
    lines.extend(
        [
            "",
            "计划排名：按订单数优先排序；同订单数下按支付金额、ROI、消耗排序；仅展示有消耗计划。",
        ]
    )
    if plan_rows:
        for index, item in enumerate(plan_rows, start=1):
            lines.append(
                (
                    f"{index}. {item.ad_name} | 账户 {item.advertiser_name} | ROI {item.roi:.2f} | "
                    f"消耗 {format_money(item.stat_cost)} | 订单 {item.order_count} | "
                    f"支付 {format_money(item.pay_amount)} | 营销目标 {plan_marketing_goal_label(item.marketing_goal)} | "
                    f"状态 {format_plan_status_text(item.status, item.opt_status)}"
                )
            )
    else:
        lines.append("暂无有消耗计划。")
    if len(active_plans) > len(plan_rows):
        lines.append(f"... 其余 {len(active_plans) - len(plan_rows)} 条计划已省略，可后续按需扩展。")
    if failures:
        lines.extend(
            [
                "",
                f"异常：{len(failures)} 个账户查询失败，请检查 OceanEngine 接口或 token 状态。",
            ]
        )
    if plan_failures:
        lines.extend(
            [
                "",
                f"计划异常：{len(plan_failures)} 个账户计划查询失败，请检查接口权限或参数。",
            ]
        )
    report_text = "\n".join(lines)
    snapshot = {
        "mode": mode,
        "generated_at": now_text,
        "window_start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "window_end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "overall": {
            "account_count": len(summaries),
            "active_account_count": active_accounts,
            "plan_count": len(plans),
            "active_plan_count": len(active_plans),
            "stat_cost": total_cost,
            "pay_amount": total_pay,
            "order_count": total_orders,
            "roi": total_roi,
        },
        "accounts": [item.__dict__ for item in summaries],
        "plans": [item.__dict__ for item in plan_rows],
        "plan_errors": plan_failures,
    }
    return report_text, snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["intraday", "daily"])
    parser.add_argument("--base-dir", default=str(Path(__file__).resolve().parent))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = Path(args.base_dir).resolve()
    config_path = base_dir / "config.json"
    try:
        config = load_runtime_config(config_path)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    state_dir = base_dir / "state"
    data_dir = base_dir / "data"
    logs_dir = base_dir / "logs"
    state_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    token_cache_path = state_dir / "token_cache.json"
    client = OceanEngineClient(config=config, token_cache_path=token_cache_path)
    report_text, snapshot = build_report(args.mode, config, client)
    dump_json(data_dir / f"{args.mode}_latest.json", snapshot)
    append_jsonl(data_dir / "history.jsonl", snapshot)
    print(report_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
