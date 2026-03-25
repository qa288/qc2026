from __future__ import annotations

from pathlib import Path


SCHEMA_PATH = Path(__file__).with_name("schema.sql")
BASE_SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8")
