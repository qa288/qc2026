from __future__ import annotations

from pydantic import BaseModel, Field


class AuthCodeExchangePayload(BaseModel):
    auth_code: str = Field(min_length=20, max_length=200)
