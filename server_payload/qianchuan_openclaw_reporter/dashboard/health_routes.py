from __future__ import annotations

from typing import Any, Callable

from fastapi.responses import JSONResponse


def register_health_routes(app: Any, readiness_payload: Callable[[], dict[str, Any]]) -> None:
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        payload = readiness_payload()
        return JSONResponse(payload, status_code=200 if payload["ok"] else 503)
