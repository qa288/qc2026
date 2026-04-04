from __future__ import annotations

from pydantic import BaseModel, Field


class AuthCodeExchangePayload(BaseModel):
    auth_code: str = Field(min_length=20, max_length=200)


class OceanEngineRuntimeConfigPayload(BaseModel):
    customer_center_id: str = Field(min_length=6, max_length=32, pattern=r"^\d+$")
    auth_code: str = Field(default="", max_length=200)
