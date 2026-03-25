from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse

from dashboard.alert_schemas import AlertRulePayload, NotificationSettingsPayload


def register_alert_routes(app: Any, service: Any, require_admin: Any) -> None:
    @app.get("/api/alert-rules")
    async def alert_rules(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        return JSONResponse({"items": service.list_alert_rules()})

    @app.get("/api/notification-settings")
    async def notification_settings(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        return JSONResponse(service.get_notification_settings())

    @app.put("/api/notification-settings")
    async def update_notification_settings(
        payload: NotificationSettingsPayload,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            service.update_notification_settings(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"ok": True})

    @app.post("/api/alert-rules")
    async def create_alert_rule(
        payload: AlertRulePayload,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            service.create_alert_rule(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"ok": True})

    @app.put("/api/alert-rules/{rule_id}")
    async def update_alert_rule(
        rule_id: int,
        payload: AlertRulePayload,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            service.update_alert_rule(rule_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"ok": True})

    @app.delete("/api/alert-rules/{rule_id}")
    async def delete_alert_rule(rule_id: int, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        service.delete_alert_rule(rule_id)
        return JSONResponse({"ok": True})
