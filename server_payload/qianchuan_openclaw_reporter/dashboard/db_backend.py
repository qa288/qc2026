from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None


def is_postgres_url(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith("postgresql://") or text.startswith("postgres://")


def _split_sql_script(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    escape = False
    for char in script:
        current.append(char)
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == ";" and not in_single and not in_double:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def _translate_sql(statement: str, backend: str) -> str:
    text = str(statement or "").strip()
    if not text:
        return ""
    if backend == "sqlite":
        return text

    upper = text.upper()
    if upper.startswith("PRAGMA "):
        return ""

    text = text.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    text = text.replace("INSERT OR IGNORE INTO", "INSERT INTO")
    if upper.startswith("INSERT OR IGNORE INTO"):
        text += " ON CONFLICT DO NOTHING"
    text = text.replace("?", "%s")
    return text


class DbConnection:
    def __init__(self, backend: str, raw_conn: Any) -> None:
        self.backend = backend
        self.raw_conn = raw_conn

    def __enter__(self) -> "DbConnection":
        return self

    def __exit__(self, exc_type, exc, _tb) -> bool:
        if exc is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False

    def execute(self, statement: str, params: Iterable[Any] | None = None) -> Any:
        sql = _translate_sql(statement, self.backend)
        if not sql:
            return _NullCursor()
        if params is None:
            return self.raw_conn.execute(sql)
        return self.raw_conn.execute(sql, tuple(params))

    def executemany(self, statement: str, param_sets: Iterable[Iterable[Any]]) -> Any:
        sql = _translate_sql(statement, self.backend)
        if not sql:
            return _NullCursor()
        prepared = [tuple(item) for item in param_sets]
        if self.backend == "postgres":
            with self.raw_conn.cursor() as cursor:
                cursor.executemany(sql, prepared)
                return cursor
        return self.raw_conn.executemany(sql, prepared)

    def executescript(self, script: str) -> None:
        for statement in _split_sql_script(script):
            sql = _translate_sql(statement, self.backend)
            if not sql:
                continue
            self.raw_conn.execute(sql)

    def commit(self) -> None:
        self.raw_conn.commit()

    def rollback(self) -> None:
        self.raw_conn.rollback()

    def close(self) -> None:
        self.raw_conn.close()


class _NullCursor:
    rowcount = 0

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[Any]:
        return []


def connect_database(database_url: str | None, database_path: Path) -> DbConnection:
    if is_postgres_url(database_url):
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgreSQL support")
        conn = psycopg.connect(str(database_url), row_factory=dict_row)
        return DbConnection("postgres", conn)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(database_path))
    conn.row_factory = sqlite3.Row
    return DbConnection("sqlite", conn)


def database_backend(database_url: str | None) -> str:
    return "postgres" if is_postgres_url(database_url) else "sqlite"
