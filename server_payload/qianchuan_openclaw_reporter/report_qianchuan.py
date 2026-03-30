#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
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
STANDARD_ACCOUNT_REPORT_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/report/advertiser/get/"
STANDARD_PLAN_LIST_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/ad/get/"
STANDARD_PLAN_REPORT_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/report/ad/get/"
UNI_PROMOTION_CONFIG_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/report/uni_promotion/config/get/"
UNI_PROMOTION_DATA_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/report/uni_promotion/data/get/"
PLAN_DETAIL_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/uni_promotion/ad/detail/"
PLAN_PRODUCT_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/uni_promotion/ad/product/get/"
PLAN_MATERIAL_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/uni_promotion/ad/material/get/"
PLAN_MATERIAL_ADD_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/uni_promotion/ad/material/add/"
QIANCHUAN_VIDEO_GET_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/video/get/"
QIANCHUAN_IMAGE_GET_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/image/get/"
QIANCHUAN_CAROUSEL_GET_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/carousel/get/"
VIDEO_USER_LOSE_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/report/video_user_lose/get/"
VIDEO_ORIGINAL_URL = "https://api.oceanengine.com/open_api/v1.0/qianchuan/file/video/original/get/"
VIDEO_AD_UPLOAD_URL = "https://api.oceanengine.com/open_api/2/file/video/ad/"
VIDEO_AD_GET_URL = "https://api.oceanengine.com/open_api/2/file/video/ad/get/"
IMAGE_AD_UPLOAD_URL = "https://api.oceanengine.com/open_api/2/file/image/ad/"
COMMENT_LIST_URL = "https://api.oceanengine.com/open_api/v3.0/tools/comment/get/"
COMMENT_REPLY_URL = "https://api.oceanengine.com/open_api/v3.0/tools/comment/reply/"
COMMENT_HIDE_URL = "https://api.oceanengine.com/open_api/v3.0/tools/comment/hide/"

REPORT_FIELDS = [
    "stat_cost",
    "total_prepay_and_pay_order_roi2",
    "total_pay_order_count_for_roi2",
    "total_pay_order_gmv_for_roi2",
]

STANDARD_ACCOUNT_REPORT_FIELDS = [
    "stat_cost",
    "pay_order_amount",
    "pay_order_count",
    "prepay_and_pay_order_roi",
]

PLAN_REPORT_FIELDS = [
    "stat_cost",
    "total_prepay_and_pay_order_roi2",
    "total_pay_order_count_for_roi2",
    "total_pay_order_gmv_for_roi2",
    "total_pay_order_gmv_include_coupon_for_roi2",
    "total_order_settle_amount_for_roi2_1h",
    "total_prepay_and_pay_settle_roi2_1h",
    "total_order_settle_count_for_roi2_1h",
    "total_cost_per_pay_order_for_roi2",
    "total_order_settle_amount_rate_for_roi2_1h",
    "total_refund_order_gmv_for_roi2_1h_rate",
    "total_refund_order_gmv_for_roi2_1h_all",
]

STANDARD_PLAN_REPORT_FIELDS = [
    "stat_cost",
    "pay_order_amount",
    "pay_order_count",
    "prepay_and_pay_order_roi",
    "pay_order_cost_per_order",
    "pay_order_coupon_amount",
]
STANDARD_REPORT_TIME_GRANULARITY = "TIME_GRANULARITY_DAILY"

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

VIDEO_USER_LOSE_FIELDS = [
    "click_cnt",
    "user_lose_cnt",
]

PLAN_MATERIAL_FIELDS_BY_TYPE = {
    # TITLE accepts the core performance metrics but rejects product exposure/click fields.
    "TITLE": [
        "stat_cost_for_roi2",
        "total_pay_order_count_for_roi2",
        "total_pay_order_gmv_for_roi2",
        "total_prepay_and_pay_order_roi2",
    ],
}

PLAN_MATERIAL_TYPES = ["VIDEO", "IMAGE", "TITLE", "CAROUSEL", "LIVE_ROOM"]
PLAN_SOURCE_UNI_PROMOTION = "UNI_PROMOTION"
PLAN_SOURCE_STANDARD = "STANDARD"
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
    total_pay_amount: float
    settled_pay_amount: float
    settled_roi: float
    settled_order_count: int
    pay_order_cost: float
    settled_amount_rate: float
    refund_rate_1h: float
    refund_amount_1h: float
    plan_source: str = PLAN_SOURCE_UNI_PROMOTION


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


def normalize_standard_marketing_goal(config: dict[str, Any]) -> str:
    value = str(config.get("marketing_goal") or "ALL").strip()
    if value in {"ALL", "VIDEO_PROM_GOODS", "LIVE_PROM_GOODS"}:
        return value
    return "ALL"


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


def post_api_json(url: str, access_token: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Access-Token": access_token,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ApiError(f"HTTP {exc.code}: {body}") from exc


def _multipart_form_body(
    fields: dict[str, Any],
    files: list[tuple[str, str, str, bytes]],
) -> tuple[bytes, str]:
    boundary = f"----CodexOcean{int(time.time() * 1000)}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    for field_name, filename, content_type, content in files:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return bytes(body), boundary


def post_api_multipart(
    url: str,
    access_token: str,
    fields: dict[str, Any],
    files: list[tuple[str, str, str, bytes]],
    timeout: int = 120,
) -> dict[str, Any]:
    body, boundary = _multipart_form_body(fields, files)
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Access-Token": access_token,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
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


def post_api_json_with_retries(
    url: str,
    access_token: str,
    payload: dict[str, Any],
    timeout: int = 30,
    attempts: int = 4,
    base_delay: float = 1.0,
) -> dict[str, Any]:
    last_error: Exception | None = None
    last_response: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = post_api_json(url, access_token, payload, timeout=timeout)
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


def post_api_multipart_with_retries(
    url: str,
    access_token: str,
    fields: dict[str, Any],
    files: list[tuple[str, str, str, bytes]],
    timeout: int = 120,
    attempts: int = 3,
    base_delay: float = 1.0,
) -> dict[str, Any]:
    last_error: Exception | None = None
    last_response: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = post_api_multipart(url, access_token, fields, files, timeout=timeout)
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


def sanitize_material_title(value: str, max_length: int = 60) -> str:
    text = str(value or "").strip()
    if not text:
        return "视频素材"
    text = text.replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_length:
        return text
    return text[:max_length]


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

    def _normalize_integer_id_list(self, values: list[str | int], field_name: str) -> list[int]:
        normalized: list[int] = []
        for item in values:
            if item is None:
                continue
            text = str(item).strip()
            if not text:
                continue
            try:
                normalized.append(int(text))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name} must contain integers") from exc
        if not normalized:
            raise ValueError(f"{field_name} is required")
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

    def get_qianchuan_videos(
        self,
        advertiser_id: int,
        filtering: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        params: dict[str, Any] = {
            "advertiser_id": int(advertiser_id),
            "page": int(page),
            "page_size": int(page_size),
        }
        if filtering:
            params["filtering"] = dict(filtering)
        response = get_json_with_retries(QIANCHUAN_VIDEO_GET_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get qianchuan videos failed: {response}")
        return response

    def list_qianchuan_videos(
        self,
        advertiser_id: int,
        filtering: dict[str, Any] | None = None,
        page_size: int = 100,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        page = 1
        rows: list[dict[str, Any]] = []
        while True:
            response = self.get_qianchuan_videos(
                advertiser_id=advertiser_id,
                filtering=filtering,
                page=page,
                page_size=page_size,
            )
            data = response.get("data") or {}
            rows.extend(data.get("list") or [])
            page_info = data.get("page_info") or {}
            total_page = int(page_info.get("total_page", 1) or 1)
            if page >= total_page or page >= max_pages:
                break
            page += 1
        return rows

    def get_qianchuan_images(
        self,
        advertiser_id: int,
        filtering: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        params: dict[str, Any] = {
            "advertiser_id": int(advertiser_id),
            "page": int(page),
            "page_size": int(page_size),
        }
        if filtering:
            params["filtering"] = dict(filtering)
        response = get_json_with_retries(QIANCHUAN_IMAGE_GET_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get qianchuan images failed: {response}")
        return response

    def list_qianchuan_images(
        self,
        advertiser_id: int,
        filtering: dict[str, Any] | None = None,
        page_size: int = 100,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        page = 1
        rows: list[dict[str, Any]] = []
        while True:
            response = self.get_qianchuan_images(
                advertiser_id=advertiser_id,
                filtering=filtering,
                page=page,
                page_size=page_size,
            )
            data = response.get("data") or {}
            rows.extend(data.get("list") or [])
            page_info = data.get("page_info") or {}
            total_page = int(page_info.get("total_page", 1) or 1)
            if page >= total_page or page >= max_pages:
                break
            page += 1
        return rows

    def get_qianchuan_carousels(
        self,
        advertiser_id: int,
        filtering: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 100,
        order_field: str | None = None,
        order_type: str | None = None,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        params: dict[str, Any] = {
            "advertiser_id": int(advertiser_id),
            "page": int(page),
            "page_size": int(page_size),
        }
        if filtering:
            params["filtering"] = dict(filtering)
        if order_field:
            params["order_field"] = str(order_field)
        if order_type:
            params["order_type"] = str(order_type)
        response = get_json_with_retries(QIANCHUAN_CAROUSEL_GET_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get qianchuan carousels failed: {response}")
        return response

    def list_qianchuan_carousels(
        self,
        advertiser_id: int,
        filtering: dict[str, Any] | None = None,
        page_size: int = 100,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        page = 1
        rows: list[dict[str, Any]] = []
        while True:
            response = self.get_qianchuan_carousels(
                advertiser_id=advertiser_id,
                filtering=filtering,
                page=page,
                page_size=page_size,
            )
            data = response.get("data") or {}
            rows.extend(data.get("carousels") or [])
            page_info = data.get("page_info") or {}
            total_page = int(page_info.get("total_page", 1) or 1)
            if page >= total_page or page >= max_pages:
                break
            page += 1
        return rows

    def get_video_user_lose(
        self,
        advertiser_id: int,
        material_id: int | str,
        start_date: str,
        end_date: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        material_text = str(material_id or "").strip()
        if not material_text:
            raise ValueError("material_id is required")
        material_value: int | str = int(material_text) if material_text.isdigit() else material_text
        params: dict[str, Any] = {
            "advertiser_id": int(advertiser_id),
            "start_date": str(start_date).strip(),
            "end_date": str(end_date).strip(),
            "fields": list(fields or VIDEO_USER_LOSE_FIELDS),
            "filtering": {
                "material_id": material_value,
            },
        }
        response = get_json_with_retries(VIDEO_USER_LOSE_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get video user lose failed: {response}")
        return response

    def get_comments(
        self,
        advertiser_id: int,
        start_time: str,
        end_time: str,
        filtering: dict[str, Any] | None = None,
        order_field: str | None = None,
        order_type: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        params: dict[str, Any] = {
            "advertiser_id": int(advertiser_id),
            "start_time": str(start_time).strip(),
            "end_time": str(end_time).strip(),
            "page": int(page),
            "page_size": int(page_size),
        }
        if filtering:
            params["filtering"] = filtering
        if order_field:
            params["order_field"] = str(order_field).strip()
        if order_type:
            params["order_type"] = str(order_type).strip()
        response = get_json_with_retries(COMMENT_LIST_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get comments failed: {response}")
        return response

    def list_comments(
        self,
        advertiser_id: int,
        start_time: str,
        end_time: str,
        filtering: dict[str, Any] | None = None,
        order_field: str | None = None,
        order_type: str | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        page = 1
        rows: list[dict[str, Any]] = []
        while True:
            response = self.get_comments(
                advertiser_id=advertiser_id,
                start_time=start_time,
                end_time=end_time,
                filtering=filtering,
                order_field=order_field,
                order_type=order_type,
                page=page,
                page_size=page_size,
            )
            data = response.get("data") or {}
            rows.extend(data.get("comment_list") or [])
            page_info = data.get("page_info") or {}
            total_page = int(page_info.get("total_page", 1) or 1)
            if page >= total_page:
                break
            page += 1
        return rows

    def reply_comments(
        self,
        advertiser_id: int,
        comment_ids: list[str | int],
        reply_text: str,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        normalized_comment_ids = self._normalize_integer_id_list(comment_ids, "comment_ids")
        payload = {
            "advertiser_id": int(advertiser_id),
            "comment_ids": normalized_comment_ids,
            "reply_text": str(reply_text).strip(),
        }
        response = post_api_json_with_retries(COMMENT_REPLY_URL, access_token, payload)
        if response.get("code") != 0:
            raise ApiError(f"reply comments failed: {response}")
        return response

    def hide_comments(
        self,
        advertiser_id: int,
        comment_ids: list[str | int],
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        normalized_comment_ids = self._normalize_integer_id_list(comment_ids, "comment_ids")
        payload = {
            "advertiser_id": int(advertiser_id),
            "comment_ids": normalized_comment_ids,
        }
        response = post_api_json_with_retries(COMMENT_HIDE_URL, access_token, payload)
        if response.get("code") != 0:
            raise ApiError(f"hide comments failed: {response}")
        return response

    def upload_local_video(
        self,
        advertiser_id: int,
        material_name: str,
        file_path: Path,
        video_signature: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        raw = file_path.read_bytes()
        signature = str(video_signature or hashlib.md5(raw).hexdigest())
        detected_type = mime_type or mimetypes.guess_type(file_path.name)[0] or "video/mp4"
        fields = {
            "advertiser_id": int(advertiser_id),
            "filename": sanitize_material_title(material_name, max_length=255),
            "upload_type": "UPLOAD_BY_FILE",
            "video_signature": signature,
        }
        files = [
            (
                "video_file",
                file_path.name,
                detected_type,
                raw,
            )
        ]
        response = post_api_multipart_with_retries(
            VIDEO_AD_UPLOAD_URL,
            access_token,
            fields,
            files,
            timeout=180,
        )
        if response.get("code") != 0:
            raise ApiError(f"upload local video failed: {response}")
        data = response.get("data")
        normalized_data = dict(data) if isinstance(data, dict) else {}
        material_id = normalized_data.get("material_id")
        if material_id is None:
            material_id = normalized_data.get("materialId")
        if material_id not in (None, ""):
            normalized_data["material_id"] = str(material_id)
        video_id = normalized_data.get("video_id")
        if video_id is None:
            video_id = normalized_data.get("videoId")
        if video_id not in (None, ""):
            normalized_data["video_id"] = str(video_id)
        video_url = normalized_data.get("video_url")
        if video_url is None:
            video_url = normalized_data.get("videoUrl")
        if video_url not in (None, ""):
            normalized_data["video_url"] = str(video_url)
        if normalized_data:
            response = dict(response)
            response["data"] = normalized_data
        return response

    def get_uploaded_videos(self, advertiser_id: int, video_ids: list[str]) -> dict[str, Any]:
        access_token = self.get_access_token()
        normalized_ids = [str(item).strip() for item in video_ids if str(item).strip()]
        if not normalized_ids:
            raise ValueError("video_ids is required")
        params = {
            "advertiser_id": int(advertiser_id),
            "video_ids": CsvParam(normalized_ids),
        }
        response = get_json_with_retries(VIDEO_AD_GET_URL, access_token, params)
        if response.get("code") != 0:
            raise ApiError(f"get uploaded videos failed: {response}")
        return response

    def get_uploaded_video(
        self,
        advertiser_id: int,
        video_id: str,
        attempts: int = 4,
        base_delay: float = 1.0,
    ) -> dict[str, Any]:
        normalized_video_id = str(video_id or "").strip()
        if not normalized_video_id:
            raise ValueError("video_id is required")
        for attempt in range(1, attempts + 1):
            response = self.get_uploaded_videos(advertiser_id, [normalized_video_id])
            data = response.get("data") or {}
            rows = data.get("list") or []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                normalized_row = dict(row)
                resolved_video_id = normalized_row.get("id")
                if resolved_video_id not in (None, ""):
                    normalized_row["video_id"] = str(resolved_video_id)
                poster_url = normalized_row.get("poster_url")
                if poster_url is None:
                    poster_url = normalized_row.get("posterUrl")
                if poster_url not in (None, ""):
                    normalized_row["poster_url"] = str(poster_url)
                if str(normalized_row.get("video_id") or "").strip() == normalized_video_id:
                    return normalized_row
            if attempt < attempts:
                time.sleep(base_delay * (2 ** (attempt - 1)))
        raise ApiError(f"get uploaded video failed: not found for video_id={normalized_video_id}")

    def upload_image_by_url(
        self,
        advertiser_id: int,
        material_name: str,
        image_url: str,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        image_url_text = str(image_url or "").strip()
        if not image_url_text:
            raise ValueError("image_url is required")
        fields = {
            "advertiser_id": int(advertiser_id),
            "filename": sanitize_material_title(material_name, max_length=55),
            "upload_type": "UPLOAD_BY_URL",
            "image_url": image_url_text,
        }
        response = post_api_multipart_with_retries(
            IMAGE_AD_UPLOAD_URL,
            access_token,
            fields,
            [],
            timeout=60,
        )
        if response.get("code") != 0:
            raise ApiError(f"upload image by url failed: {response}")
        data = response.get("data")
        normalized_data = dict(data) if isinstance(data, dict) else {}
        image_id = normalized_data.get("id")
        if image_id is None:
            image_id = normalized_data.get("image_id")
        if image_id not in (None, ""):
            normalized_data["image_id"] = str(image_id)
            normalized_data["id"] = str(image_id)
        material_id = normalized_data.get("material_id")
        if material_id is None:
            material_id = normalized_data.get("materialId")
        if material_id not in (None, ""):
            normalized_data["material_id"] = str(material_id)
        image_asset_url = normalized_data.get("url")
        if image_asset_url is None:
            image_asset_url = normalized_data.get("image_url")
        if image_asset_url not in (None, ""):
            normalized_data["url"] = str(image_asset_url)
        if normalized_data:
            response = dict(response)
            response["data"] = normalized_data
        return response

    def upload_image_file(
        self,
        advertiser_id: int,
        material_name: str,
        file_path: Path,
        image_signature: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        raw = file_path.read_bytes()
        signature = str(image_signature or hashlib.md5(raw).hexdigest())
        detected_type = mime_type or mimetypes.guess_type(file_path.name)[0] or "image/jpeg"
        fields = {
            "advertiser_id": int(advertiser_id),
            "filename": sanitize_material_title(material_name, max_length=255),
            "upload_type": "UPLOAD_BY_FILE",
            "image_signature": signature,
        }
        files = [
            (
                "image_file",
                file_path.name,
                detected_type,
                raw,
            )
        ]
        response = post_api_multipart_with_retries(
            IMAGE_AD_UPLOAD_URL,
            access_token,
            fields,
            files,
            timeout=120,
        )
        if response.get("code") != 0:
            raise ApiError(f"upload image file failed: {response}")
        data = response.get("data")
        normalized_data = dict(data) if isinstance(data, dict) else {}
        image_id = normalized_data.get("id")
        if image_id is None:
            image_id = normalized_data.get("image_id")
        if image_id not in (None, ""):
            normalized_data["image_id"] = str(image_id)
            normalized_data["id"] = str(image_id)
        material_id = normalized_data.get("material_id")
        if material_id is None:
            material_id = normalized_data.get("materialId")
        if material_id not in (None, ""):
            normalized_data["material_id"] = str(material_id)
        image_asset_url = normalized_data.get("url")
        if image_asset_url is None:
            image_asset_url = normalized_data.get("image_url")
        if image_asset_url not in (None, ""):
            normalized_data["url"] = str(image_asset_url)
        if normalized_data:
            response = dict(response)
            response["data"] = normalized_data
        return response

    def add_plan_material(
        self,
        advertiser_id: int,
        ad_id: int,
        material_title: str,
        video_id: str,
        marketing_goal: str = "",
        product_id: str = "",
        image_material: list[dict[str, Any]] | None = None,
        video_image_mode: str = "",
        video_cover_id: str = "",
    ) -> dict[str, Any]:
        access_token = self.get_access_token()
        title = sanitize_material_title(material_title)
        video_material_item: dict[str, Any] = {"video_id": str(video_id)}
        video_image_mode_text = str(video_image_mode or "").strip()
        if video_image_mode_text:
            video_material_item["image_mode"] = video_image_mode_text
        video_cover_id_text = str(video_cover_id or "").strip()
        if video_cover_id_text:
            video_material_item["video_cover_id"] = video_cover_id_text
        video_material = [video_material_item]
        title_material = [{"title": title}]
        normalized_image_material = [
            dict(item)
            for item in (image_material or [])
            if isinstance(item, dict)
        ]
        payload: dict[str, Any] = {
            "advertiser_id": int(advertiser_id),
            "ad_id": int(ad_id),
        }
        product_text = str(product_id or "").strip()
        if str(marketing_goal or "").strip() == "VIDEO_PROM_GOODS" and product_text.isdigit():
            creative_payload: dict[str, Any] = {
                "product_id": int(product_text),
                "title_material": title_material,
                "video_material": video_material,
            }
            if normalized_image_material:
                creative_payload["image_material"] = normalized_image_material
            payload["multi_product_creative_list"] = [creative_payload]
        else:
            payload["programmatic_creative_media_list"] = {
                "title_material": title_material,
                "video_material": video_material,
            }
        response = post_api_json_with_retries(
            PLAN_MATERIAL_ADD_URL,
            access_token,
            payload,
            timeout=60,
        )
        if response.get("code") != 0:
            raise ApiError(f"add plan material failed: {response}")
        return response

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

    @staticmethod
    def _empty_account_summary(
        advertiser_id: int,
        advertiser_name: str,
        *,
        ok: bool,
        error: str | None = None,
    ) -> AccountSummary:
        return AccountSummary(
            advertiser_id=advertiser_id,
            advertiser_name=advertiser_name,
            stat_cost=0.0,
            roi=0.0,
            order_count=0,
            pay_amount=0.0,
            ok=ok,
            error=error,
        )

    def _get_uni_account_summary(
        self,
        advertiser_id: int,
        advertiser_name: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> AccountSummary:
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
            return self._empty_account_summary(
                advertiser_id,
                advertiser_name,
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

    def _get_standard_account_summary(
        self,
        advertiser_id: int,
        advertiser_name: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> AccountSummary:
        access_token = self.get_access_token()
        filtering: dict[str, Any] = {
            "marketing_goal": normalize_standard_marketing_goal(self.config),
        }
        order_platform = str(self.config.get("order_platform") or "").strip()
        if order_platform:
            filtering["order_platform"] = order_platform
        params = {
            "advertiser_id": advertiser_id,
            "start_date": start_dt.strftime("%Y-%m-%d"),
            "end_date": end_dt.strftime("%Y-%m-%d"),
            "fields": STANDARD_ACCOUNT_REPORT_FIELDS,
            "filtering": filtering,
            "time_granularity": STANDARD_REPORT_TIME_GRANULARITY,
            "page": 1,
            "page_size": 10,
        }
        response = get_json_with_retries(STANDARD_ACCOUNT_REPORT_URL, access_token, params)
        if response.get("code") != 0:
            return self._empty_account_summary(
                advertiser_id,
                advertiser_name,
                ok=False,
                error=response.get("message", "unknown error"),
            )
        rows = (response.get("data") or {}).get("list") or []
        stat_cost = round(sum(float(row.get("stat_cost", 0.0) or 0.0) for row in rows), 2)
        pay_amount = round(sum(float(row.get("pay_order_amount", 0.0) or 0.0) for row in rows), 2)
        order_count = int(sum(float(row.get("pay_order_count", 0.0) or 0.0) for row in rows))
        return AccountSummary(
            advertiser_id=advertiser_id,
            advertiser_name=advertiser_name,
            stat_cost=stat_cost,
            roi=derive_ratio(pay_amount, stat_cost, 0.0),
            order_count=order_count,
            pay_amount=pay_amount,
        )

    def get_account_summary(self, advertiser_id: int, advertiser_name: str, start_dt: datetime, end_dt: datetime) -> AccountSummary:
        try:
            source_summaries = [
                self._get_uni_account_summary(advertiser_id, advertiser_name, start_dt, end_dt),
                self._get_standard_account_summary(advertiser_id, advertiser_name, start_dt, end_dt),
            ]
            successful = [item for item in source_summaries if item.ok]
            if successful:
                stat_cost = round(sum(item.stat_cost for item in successful), 2)
                pay_amount = round(sum(item.pay_amount for item in successful), 2)
                order_count = sum(int(item.order_count or 0) for item in successful)
                return AccountSummary(
                    advertiser_id=advertiser_id,
                    advertiser_name=advertiser_name,
                    stat_cost=stat_cost,
                    roi=derive_ratio(pay_amount, stat_cost, 0.0),
                    order_count=order_count,
                    pay_amount=pay_amount,
                )
            errors = [str(item.error or "").strip() for item in source_summaries if str(item.error or "").strip()]
            return self._empty_account_summary(
                advertiser_id,
                advertiser_name,
                ok=False,
                error="; ".join(errors) or "unknown error",
            )
        except Exception as exc:  # noqa: BLE001
            return self._empty_account_summary(advertiser_id, advertiser_name, ok=False, error=str(exc))

    def _list_uni_plan_summaries(
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
                    raise ApiError(f"list uni promotion plans failed: {response}")
                data = response.get("data") or {}
                for item in data.get("ad_list", []):
                    ad_info = item.get("ad_info") or {}
                    stats_info = item.get("stats_info") or {}
                    product_items = item.get("product_info") or []
                    room_items = item.get("room_info") or []
                    first_product = product_items[0] if product_items else {}
                    first_room = room_items[0] if room_items else {}
                    stat_cost = normalize_plan_money(stats_info.get("stat_cost"))
                    order_count = int(float(stats_info.get("total_pay_order_count_for_roi2", 0.0) or 0.0))
                    pay_amount = normalize_plan_money(stats_info.get("total_pay_order_gmv_for_roi2"))
                    total_pay_amount = normalize_plan_money(stats_info.get("total_pay_order_gmv_include_coupon_for_roi2"))
                    settled_pay_amount = normalize_plan_money(stats_info.get("total_order_settle_amount_for_roi2_1h"))
                    settled_order_count = int(float(stats_info.get("total_order_settle_count_for_roi2_1h", 0.0) or 0.0))
                    refund_amount_1h = normalize_plan_money(stats_info.get("total_refund_order_gmv_for_roi2_1h_all"))
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
                            stat_cost=stat_cost,
                            roi=round(float(stats_info.get("total_prepay_and_pay_order_roi2", 0.0) or 0.0), 2),
                            order_count=order_count,
                            pay_amount=pay_amount,
                            total_pay_amount=total_pay_amount,
                            settled_pay_amount=settled_pay_amount,
                            settled_roi=derive_ratio(
                                settled_pay_amount,
                                stat_cost,
                                stats_info.get("total_prepay_and_pay_settle_roi2_1h"),
                            ),
                            settled_order_count=settled_order_count,
                            pay_order_cost=derive_ratio(
                                stat_cost,
                                order_count,
                                normalize_plan_money(stats_info.get("total_cost_per_pay_order_for_roi2")),
                            ),
                            settled_amount_rate=derive_percent(
                                settled_pay_amount,
                                total_pay_amount,
                                stats_info.get("total_order_settle_amount_rate_for_roi2_1h"),
                            ),
                            refund_rate_1h=derive_percent(
                                refund_amount_1h,
                                total_pay_amount,
                                stats_info.get("total_refund_order_gmv_for_roi2_1h_rate"),
                            ),
                            refund_amount_1h=refund_amount_1h,
                            plan_source=PLAN_SOURCE_UNI_PROMOTION,
                        )
                    )
                page_info = data.get("page_info") or {}
                total_page = int(page_info.get("total_page", 1) or 1)
                if page >= total_page:
                    break
                page += 1
        return plans

    def _list_standard_plan_metadata(self, advertiser_id: int) -> dict[int, dict[str, Any]]:
        access_token = self.get_access_token()
        page_size = normalize_plan_page_size(self.config)
        plans: dict[int, dict[str, Any]] = {}
        for marketing_goal in get_plan_marketing_goals(self.config):
            page = 1
            while True:
                params = {
                    "advertiser_id": advertiser_id,
                    "filtering": {"marketing_goal": marketing_goal},
                    "request_aweme_info": 1,
                    "page": page,
                    "page_size": page_size,
                }
                response = get_json_with_retries(STANDARD_PLAN_LIST_URL, access_token, params)
                if response.get("code") != 0:
                    raise ApiError(f"list standard plans failed: {response}")
                data = response.get("data") or {}
                rows = data.get("list") or []
                for row in rows:
                    ad_id = int(row.get("ad_id", 0) or 0)
                    if ad_id:
                        plans[ad_id] = dict(row)
                page_info = data.get("page_info") or {}
                total_page = int(page_info.get("total_page", 1) or 1)
                if page >= total_page:
                    break
                page += 1
        return plans

    def _list_standard_plan_stats(
        self,
        advertiser_id: int,
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict[int, dict[str, Any]]:
        access_token = self.get_access_token()
        page_size = normalize_plan_page_size(self.config)
        filtering: dict[str, Any] = {
            "marketing_goal": normalize_standard_marketing_goal(self.config),
        }
        order_platform = str(self.config.get("order_platform") or "").strip()
        if order_platform:
            filtering["order_platform"] = order_platform
        rows_by_ad_id: dict[int, dict[str, Any]] = {}
        page = 1
        while True:
            params = {
                "advertiser_id": advertiser_id,
                "start_date": start_dt.strftime("%Y-%m-%d"),
                "end_date": end_dt.strftime("%Y-%m-%d"),
                "fields": STANDARD_PLAN_REPORT_FIELDS,
                "filtering": filtering,
                "time_granularity": STANDARD_REPORT_TIME_GRANULARITY,
                "page": page,
                "page_size": page_size,
            }
            response = get_json_with_retries(STANDARD_PLAN_REPORT_URL, access_token, params)
            if response.get("code") != 0:
                raise ApiError(f"list standard plan reports failed: {response}")
            data = response.get("data") or {}
            rows = data.get("list") or []
            for row in rows:
                ad_id = int(row.get("ad_id", 0) or 0)
                if ad_id:
                    rows_by_ad_id[ad_id] = dict(row)
            page_info = data.get("page_info") or {}
            total_page = int(page_info.get("total_page", 1) or 1)
            if page >= total_page:
                break
            page += 1
        return rows_by_ad_id

    def _list_standard_plan_summaries(
        self,
        advertiser_id: int,
        advertiser_name: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[PlanSummary]:
        metadata_rows = self._list_standard_plan_metadata(advertiser_id)
        stats_rows = self._list_standard_plan_stats(advertiser_id, start_dt, end_dt)
        plans: list[PlanSummary] = []
        for ad_id in sorted(set(metadata_rows.keys()) | set(stats_rows.keys())):
            metadata = metadata_rows.get(ad_id) or {}
            stats = stats_rows.get(ad_id) or {}
            product_items = metadata.get("product_info") or []
            aweme_items = metadata.get("aweme_info") or []
            first_product = product_items[0] if product_items else {}
            first_aweme = aweme_items[0] if aweme_items else {}
            delivery_setting = metadata.get("delivery_setting") or {}
            pay_amount = normalize_metric(stats.get("pay_order_amount"))
            coupon_amount = normalize_metric(stats.get("pay_order_coupon_amount"))
            stat_cost = normalize_metric(stats.get("stat_cost"))
            order_count = int(float(stats.get("pay_order_count", 0.0) or 0.0))
            plans.append(
                PlanSummary(
                    advertiser_id=advertiser_id,
                    advertiser_name=advertiser_name,
                    ad_id=ad_id,
                    ad_name=str(metadata.get("name") or f"ad_{ad_id}"),
                    product_id=str(first_product.get("id") or first_product.get("product_id") or ""),
                    product_name=str(first_product.get("name") or first_product.get("product_name") or ""),
                    anchor_name=str(
                        first_aweme.get("aweme_name")
                        or first_aweme.get("aweme_show_id")
                        or first_aweme.get("name")
                        or ""
                    ),
                    marketing_goal=str(metadata.get("marketing_goal") or stats.get("marketing_goal") or ""),
                    status=str(metadata.get("status") or ""),
                    opt_status=str(metadata.get("opt_status") or ""),
                    roi_goal=round(
                        float(delivery_setting.get("roi_goal") or delivery_setting.get("target_roi") or 0.0),
                        2,
                    ),
                    stat_cost=stat_cost,
                    roi=derive_ratio(pay_amount, stat_cost, stats.get("prepay_and_pay_order_roi")),
                    order_count=order_count,
                    pay_amount=pay_amount,
                    total_pay_amount=round(pay_amount + coupon_amount, 2),
                    settled_pay_amount=0.0,
                    settled_roi=0.0,
                    settled_order_count=0,
                    pay_order_cost=derive_ratio(stat_cost, order_count, stats.get("pay_order_cost_per_order")),
                    settled_amount_rate=0.0,
                    refund_rate_1h=0.0,
                    refund_amount_1h=0.0,
                    plan_source=PLAN_SOURCE_STANDARD,
                )
            )
        return plans

    def list_plan_summaries(
        self,
        advertiser_id: int,
        advertiser_name: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[PlanSummary]:
        plans: list[PlanSummary] = []
        errors: list[str] = []
        try:
            plans.extend(self._list_uni_plan_summaries(advertiser_id, advertiser_name, start_dt, end_dt))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"uni_promotion: {exc}")
        try:
            plans.extend(self._list_standard_plan_summaries(advertiser_id, advertiser_name, start_dt, end_dt))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"standard: {exc}")
        if not plans and errors:
            raise ApiError("; ".join(errors))
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


def normalize_metric(value: Any) -> float:
    return round(float(value or 0.0), 2)


def derive_ratio(numerator: float, denominator: float, fallback: Any = 0.0) -> float:
    if float(denominator or 0.0) > 0:
        return round(float(numerator or 0.0) / float(denominator or 0.0), 2)
    return normalize_metric(fallback)


def derive_percent(numerator: float, denominator: float, fallback: Any = 0.0) -> float:
    if float(denominator or 0.0) > 0:
        return round(float(numerator or 0.0) / float(denominator or 0.0) * 100.0, 2)
    return normalize_metric(fallback)


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


def plan_material_fields_for_type(material_type: str) -> list[str]:
    normalized = str(material_type or "").strip().upper()
    fields = PLAN_MATERIAL_FIELDS_BY_TYPE.get(normalized, PLAN_MATERIAL_FIELDS)
    return list(fields)


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
