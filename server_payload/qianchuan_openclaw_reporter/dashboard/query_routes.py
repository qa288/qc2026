from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Body, Depends, HTTPException
from fastapi.responses import JSONResponse


def register_query_routes(
    app: Any,
    service: Any,
    require_auth: Any,
    require_admin: Any,
    role_admin: str,
    role_operator: str,
    timezone: str,
) -> None:
    @app.get("/api/operator-rankings")
    async def operator_rankings(
        range: str = "day",
        start_date: str = "",
        end_date: str = "",
        sort_key: str = "stat_cost",
        sort_dir: str = "desc",
        _user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        try:
            payload = await asyncio.to_thread(
                service.public_employee_rankings,
                range,
                start_date,
                end_date,
                sort_key,
                sort_dir,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(payload)

    @app.get("/api/unassigned-candidates")
    async def unassigned_candidates(
        range: str = "day",
        start_date: str = "",
        end_date: str = "",
        scope: str = "all",
        user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        try:
            payload = await asyncio.to_thread(
                service.unassigned_candidates,
                range,
                start_date,
                end_date,
                scope,
                allowed,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(payload)

    @app.get("/api/session/me")
    async def current_session(user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        return JSONResponse(
            {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "display_name": user.get("display_name") or "",
                "upload_materials_enabled": bool(user.get("upload_materials_enabled")),
                "can_upload_materials": service.can_upload_materials(user),
                "scope_type": "all" if allowed is None else "restricted",
                "scope_count": None if allowed is None else len(allowed),
            }
        )

    @app.get("/api/catalog/accounts")
    async def available_accounts(user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        return JSONResponse({"items": service.latest_account_catalog(allowed)})

    @app.get("/api/dashboard")
    async def dashboard_data(user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        latest = service.latest_snapshot(allowed)
        if latest and str(user.get("role") or "") == role_operator:
            latest = service._apply_operator_scope(latest, user)
        is_admin = str(user.get("role") or "") == role_admin
        return JSONResponse(
            {
                "session": {
                    "id": user["id"],
                    "username": user["username"],
                    "role": user["role"],
                    "display_name": user.get("display_name") or "",
                    "upload_materials_enabled": bool(user.get("upload_materials_enabled")),
                    "can_upload_materials": service.can_upload_materials(user),
                    "scope_type": "all" if allowed is None else "restricted",
                    "scope_count": None if allowed is None else len(allowed),
                },
                "latest": latest,
                "extendedSync": service.latest_extended_sync(),
                "tokenInfo": service.latest_token_payload(masked=True) if is_admin else None,
                "summaryHistory": service.summary_history(),
                "notificationSettings": service.get_notification_settings() if is_admin else {},
                "alertRules": service.list_alert_rules() if is_admin else [],
                "alertEvents": service.alert_events() if is_admin else [],
                "timezone": timezone,
            }
        )

    @app.get("/api/performance")
    async def performance_data(
        range: str = "day",
        start_date: str = "",
        end_date: str = "",
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        try:
            allowed = service.allowed_advertiser_ids_for_user(user)
            payload = await asyncio.to_thread(
                service.get_performance_snapshot,
                range,
                start_date,
                end_date,
                False,
                allowed,
            )
            if str(user.get("role") or "") == role_operator:
                payload = service._apply_operator_scope(payload, user)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(payload)

    @app.get("/api/accounts/{advertiser_id}/history")
    async def account_history(advertiser_id: int, user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
        if str(user.get("role") or "") == role_operator:
            raise HTTPException(status_code=403, detail="operator cannot access account history")
        allowed = service.allowed_advertiser_ids_for_user(user)
        return JSONResponse({"items": service.account_history(advertiser_id, allowed_advertiser_ids=allowed)})

    @app.get("/api/plans/{ad_id}/history")
    async def plan_history(ad_id: int, user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
        if str(user.get("role") or "") == role_operator:
            raise HTTPException(status_code=403, detail="operator cannot access plan history")
        allowed = service.allowed_advertiser_ids_for_user(user)
        return JSONResponse({"items": service.plan_history(ad_id, allowed_advertiser_ids=allowed)})

    @app.get("/api/plans/{ad_id}/assets")
    async def plan_assets(ad_id: int, snapshot_time: str = "", user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
        if str(user.get("role") or "") == role_operator:
            raise HTTPException(status_code=403, detail="operator cannot access plan assets")
        allowed = service.allowed_advertiser_ids_for_user(user)
        return JSONResponse(service.plan_assets(ad_id, snapshot_time, allowed))

    @app.get("/api/material-rankings")
    async def material_rankings(
        snapshot_time: str = "",
        range: str = "day",
        start_date: str = "",
        end_date: str = "",
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        try:
            payload = service.material_rankings(range, start_date, end_date, snapshot_time, allowed)
            payload = service._apply_material_scope(payload, user)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(payload)

    @app.get("/api/material-preview-curve")
    async def material_preview_curve(
        material_key: str,
        snapshot_time: str = "",
        range: str = "day",
        start_date: str = "",
        end_date: str = "",
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        try:
            payload = await asyncio.to_thread(
                service.material_preview_curve,
                material_key,
                range,
                start_date,
                end_date,
                snapshot_time,
                allowed,
                user,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return JSONResponse(payload)

    @app.get("/api/comments")
    async def comments(
        range: str = "day",
        start_date: str = "",
        end_date: str = "",
        advertiser_id: int = 0,
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        try:
            payload = await asyncio.to_thread(
                service.comment_items,
                range,
                start_date,
                end_date,
                advertiser_id,
                allowed,
            )
            payload = service._apply_comment_scope(payload, user)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return JSONResponse(payload)

    @app.post("/api/comments/reply")
    async def reply_comment(
        payload: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        try:
            response_payload = await asyncio.to_thread(
                service.reply_comment,
                int(payload.get("advertiser_id") or 0),
                str(payload.get("comment_id") or ""),
                str(payload.get("reply_text") or ""),
                allowed,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return JSONResponse(response_payload)

    @app.post("/api/comments/hide")
    async def hide_comment(
        payload: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        try:
            response_payload = await asyncio.to_thread(
                service.hide_comment,
                int(payload.get("advertiser_id") or 0),
                str(payload.get("comment_id") or ""),
                allowed,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return JSONResponse(response_payload)
