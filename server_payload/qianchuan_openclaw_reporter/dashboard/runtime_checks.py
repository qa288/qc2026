from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

try:
    import redis
except Exception:  # noqa: BLE001
    redis = None

from dashboard.db_backend import connect_database, database_backend
from dashboard.migrations import available_schema_version, current_schema_version
from dashboard.settings import settings


def _mask_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme:
        return text
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or ""
    return f"{parsed.scheme}://{host}{port}{path}"


def _redis_check(url: str) -> dict[str, Any]:
    target = _mask_url(url)
    if not str(url or "").strip():
        return {"ok": False, "status": "missing", "target": target, "error": "url_missing"}
    if redis is None:
        return {"ok": False, "status": "unavailable", "target": target, "error": "redis_package_missing"}
    client = None
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        return {"ok": True, "status": "ok", "target": target}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "error", "target": target, "error": str(exc)}
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()


def readiness_payload() -> dict[str, Any]:
    checks: dict[str, Any] = {}

    try:
        with connect_database(settings.database_url, settings.database_path) as conn:
            conn.execute("SELECT 1")
            checks["database"] = {
                "ok": True,
                "status": "ok",
                "backend": database_backend(settings.database_url),
                "schema_version": current_schema_version(conn),
                "expected_schema_version": available_schema_version(),
            }
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {
            "ok": False,
            "status": "error",
            "backend": database_backend(settings.database_url),
            "error": str(exc),
            "expected_schema_version": available_schema_version(),
        }

    checks["redis"] = _redis_check(settings.redis_url)
    checks["celery_broker"] = _redis_check(settings.celery_broker_url)
    checks["celery_result_backend"] = _redis_check(settings.celery_result_backend)

    ok = all(bool(item.get("ok")) for item in checks.values())
    return {
        "status": "ok" if ok else "degraded",
        "ok": ok,
        "checks": checks,
    }
