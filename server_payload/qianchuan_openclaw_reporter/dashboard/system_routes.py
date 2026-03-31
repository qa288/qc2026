from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse

from dashboard.api_response import api_response
from dashboard.system_schemas import AuthCodeExchangePayload, OceanEngineRuntimeConfigPayload


def register_system_routes(app: Any, service: Any, require_admin: Any) -> None:
    @app.post("/api/sync")
    async def manual_sync(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        from dashboard.celery_app import celery_app

        task = celery_app.send_task("dashboard.sync")
        return api_response({"ok": True, "queued": True, "task_id": task.id, "task_name": "dashboard.sync"}, status_code=202)

    @app.post("/api/sync/extended")
    async def manual_extended_sync(
        force_refresh: bool = False,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        from dashboard.celery_app import celery_app

        task = celery_app.send_task("dashboard.detail_sync", args=[bool(force_refresh)])
        return api_response(
            {
                "ok": True,
                "queued": True,
                "task_id": task.id,
                "task_name": "dashboard.detail_sync",
                "force_refresh": bool(force_refresh),
            },
            status_code=202,
        )

    @app.post("/api/sync/backfill/performance")
    async def manual_performance_backfill(
        days: int = 30,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        result = service.queue_manual_history_backfill("performance", max(int(days or 30), 1))
        return api_response(result, status_code=202)

    @app.post("/api/sync/backfill/extended")
    async def manual_extended_backfill(
        days: int = 30,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        result = service.queue_manual_history_backfill("detail", max(int(days or 30), 1))
        return api_response(result, status_code=202)

    @app.get("/api/system/integrations/ocean-engine/token-latest")
    async def latest_token(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        return api_response(service.latest_token_payload(masked=False))

    @app.post("/api/system/integrations/ocean-engine/exchange-auth-code")
    async def exchange_auth_code(
        payload: AuthCodeExchangePayload,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            token_payload = await asyncio.to_thread(service.exchange_auth_code, payload.auth_code)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return api_response({"ok": True, "token": token_payload})

    @app.put("/api/system/integrations/ocean-engine/runtime-config")
    async def update_runtime_config(
        payload: OceanEngineRuntimeConfigPayload,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            result = await asyncio.to_thread(service.update_ocean_engine_runtime_config, payload)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return api_response({"ok": True, **result})
