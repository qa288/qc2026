from __future__ import annotations

import re

from pydantic import BaseModel, Field

from dashboard.settings import settings


ALERT_ENTITY_TYPES = {"account", "plan", "account_balance", "shared_wallet", "burst_plan"}
ALERT_METRICS = {"stat_cost", "roi", "order_count", "pay_amount", "account_balance", "wallet_balance", "burst_order_count"}
ALERT_ENTITY_METRICS = {
    "account": {"stat_cost", "roi", "order_count", "pay_amount"},
    "plan": {"stat_cost", "roi", "order_count", "pay_amount"},
    "account_balance": {"account_balance"},
    "shared_wallet": {"wallet_balance"},
    "burst_plan": {"burst_order_count"},
}
ALERT_COOLDOWN_DEFAULT = settings.alert_cooldown_default


def normalize_summary_times(value: str) -> str:
    tokens = re.split(r"[,，\s]+", str(value or "").strip())
    valid = sorted({token for token in tokens if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", token)})
    return ",".join(valid)


class AlertRulePayload(BaseModel):
    entity_type: str = Field(pattern="^(account|plan|account_balance|shared_wallet|burst_plan)$")
    metric: str = Field(pattern="^(stat_cost|roi|order_count|pay_amount|account_balance|wallet_balance|burst_order_count)$")
    operator: str = Field(pattern="^(gt|lt|gte|lte)$")
    threshold: float
    min_spend: float = 0.0
    cooldown_minutes: int = ALERT_COOLDOWN_DEFAULT
    enabled: bool = True
    target_id: str = ""
    note: str = ""


class NotificationSettingsPayload(BaseModel):
    enabled: bool = False
    channel: str = Field(default="feishu", min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    account: str = Field(default="default", max_length=80)
    target: str = Field(default="", max_length=200)
    alert_enabled: bool = False
    alert_batch_size: int = Field(default=6, ge=1, le=20)
    summary_enabled: bool = False
    summary_times: str = Field(default="", max_length=200)
    summary_account_limit: int = Field(default=6, ge=1, le=20)
    summary_plan_limit: int = Field(default=10, ge=1, le=30)


def validate_alert_rule_payload(payload: AlertRulePayload) -> None:
    entity_type = str(payload.entity_type or "").strip()
    metric = str(payload.metric or "").strip()
    allowed_metrics = ALERT_ENTITY_METRICS.get(entity_type, set())
    if metric not in allowed_metrics:
        raise ValueError("当前对象不支持所选指标。")
    if entity_type in {"account_balance", "shared_wallet", "burst_plan"} and float(payload.min_spend or 0) != 0:
        raise ValueError("当前规则类型不支持最低消耗限制。")
