from __future__ import annotations

from pydantic import BaseModel, Field


class EmployeePayload(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=200)
    enabled: bool = True


class EmployeeKeywordPayload(BaseModel):
    keyword: str = Field(min_length=1, max_length=80)
    scope: str = Field(default="all", pattern="^(all|account|plan|product|material)$")
    priority: int = Field(default=100, ge=1, le=9999)
    enabled: bool = True


class EmployeeBindingPayload(BaseModel):
    object_type: str = Field(pattern="^(account|plan|product|material)$")
    object_key: str = Field(min_length=1, max_length=200)
    object_label: str = Field(default="", max_length=255)
    note: str = Field(default="", max_length=200)
