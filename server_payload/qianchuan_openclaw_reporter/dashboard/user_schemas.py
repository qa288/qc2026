from __future__ import annotations

from pydantic import BaseModel, Field


class AppUserPayload(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(default="", max_length=120)
    role: str = Field(default="operator", pattern="^(admin|supervisor|operator)$")
    display_name: str = Field(default="", max_length=80)
    enabled: bool = True
    upload_materials_enabled: bool = False


class UserScopePayload(BaseModel):
    advertiser_ids: list[int] = Field(default_factory=list)


class UserKeywordPayload(BaseModel):
    keyword: str = Field(min_length=1, max_length=80)
    enabled: bool = True
