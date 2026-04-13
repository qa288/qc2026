from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse

from dashboard.api_response import api_response
from dashboard.settings import settings
from dashboard.system_schemas import AuthCodeExchangePayload, OceanEngineRuntimeConfigPayload


def register_system_routes(app: Any, service: Any, require_admin: Any) -> None:
    @app.post("/api/sync")
    async def manual_sync(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        from dashboard.celery_app import celery_app

        task = celery_app.send_task("dashboard.sync")
        return api_response({"ok": True, "queued": True, "task_id": task.id, "task_name": "dashboard.sync"}, status_code=202)

    @app.post("/api/sync/extended")
    async def manual_detail_sync(
        force_refresh: bool = False,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        return await manual_material_hot_sync(force_refresh=force_refresh, _user=_user)

    @app.post("/api/sync/material-hot")
    async def manual_material_hot_sync(
        force_refresh: bool = False,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        from dashboard.celery_app import celery_app

        if service.runtime_lock_active("detail-sync"):
            service.clear_material_runtime_caches()
            return api_response(
                {
                    "ok": True,
                    "queued": False,
                    "running": True,
                    "task_name": "dashboard.material_hot_sync",
                    "task_name_legacy": "dashboard.detail_sync",
                    "force_refresh": bool(force_refresh),
                },
                status_code=200,
            )
        task = celery_app.send_task("dashboard.material_hot_sync", kwargs={"force_refresh": bool(force_refresh)})
        service.clear_material_runtime_caches()
        return api_response(
            {
                "ok": True,
                "queued": True,
                "task_id": task.id,
                "task_name": "dashboard.material_hot_sync",
                "task_name_legacy": "dashboard.detail_sync",
                "force_refresh": bool(force_refresh),
            },
            status_code=202,
        )

    @app.post("/api/sync/full-refresh")
    async def manual_full_refresh(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        from dashboard.celery_app import celery_app

        current_status = service.full_refresh_status()
        if service.runtime_lock_active("full-refresh"):
            return api_response(
                {
                    "ok": True,
                    "queued": False,
                    "running": True,
                    "task_id": current_status.get("task_id", ""),
                    "task_name": "dashboard.full_refresh",
                    "status": current_status,
                },
                status_code=200,
            )
        task = celery_app.send_task(
            "dashboard.full_refresh",
            args=[int(settings.account_plan_retention_days or 90), 0, True],
            queue="history",
        )
        queued_status = service.mark_full_refresh_queued(task.id, trigger="manual")
        return api_response(
            {
                "ok": True,
                "queued": True,
                "task_id": task.id,
                "task_name": "dashboard.full_refresh",
                "status": queued_status,
            },
            status_code=202,
        )

    @app.post("/api/sync/history-catchup-probe")
    async def manual_history_catchup_probe(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        from dashboard.celery_app import celery_app

        current_status = service.full_refresh_status()
        if service.runtime_lock_active("full-refresh"):
            return api_response(
                {
                    "ok": True,
                    "queued": False,
                    "running": True,
                    "task_id": current_status.get("task_id", ""),
                    "task_name": "dashboard.history_catchup_probe",
                    "status": current_status,
                },
                status_code=200,
            )
        task = celery_app.send_task(
            "dashboard.history_catchup_probe",
            kwargs={"trigger": "manual"},
            queue="history",
        )
        queued_status = service.mark_full_refresh_queued(task.id, trigger="manual")
        queued_status = service.update_full_refresh_status(
            task_id=task.id,
            trigger="manual",
            message="历史补缺任务已进入队列，等待开始执行。",
            updated_at=queued_status.get("updated_at") or queued_status.get("queued_at") or "",
        )
        return api_response(
            {
                "ok": True,
                "queued": True,
                "task_id": task.id,
                "task_name": "dashboard.history_catchup_probe",
                "status": queued_status,
            },
            status_code=202,
        )

    @app.get("/api/sync/full-refresh/status")
    async def manual_full_refresh_status(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        return api_response(service.full_refresh_status())

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
