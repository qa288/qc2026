from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse

from dashboard.user_schemas import AppUserPayload, UserKeywordPayload, UserScopePayload


def register_user_routes(app: Any, service: Any, require_admin: Any) -> None:
    @app.get("/api/users")
    async def users(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        return JSONResponse({"items": service.list_users()})

    @app.post("/api/users")
    async def create_user(payload: AppUserPayload, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        try:
            item = service.create_user(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(item)

    @app.put("/api/users/{user_id}")
    async def update_user(
        user_id: int,
        payload: AppUserPayload,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            item = service.update_user(user_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(item)

    @app.get("/api/users/{user_id}/account-scopes")
    async def user_account_scopes(user_id: int, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        return JSONResponse({"advertiser_ids": service.user_account_scopes(user_id)})

    @app.put("/api/users/{user_id}/account-scopes")
    async def replace_user_account_scopes(
        user_id: int,
        payload: UserScopePayload,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            advertiser_ids = service.replace_user_account_scopes(user_id, payload.advertiser_ids)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"advertiser_ids": advertiser_ids})

    @app.get("/api/users/{user_id}/keywords")
    async def user_keywords(user_id: int, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        try:
            items = service.list_user_keywords(user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"items": items})

    @app.post("/api/users/{user_id}/keywords")
    async def create_user_keyword(
        user_id: int,
        payload: UserKeywordPayload,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            item = service.create_user_keyword(user_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(item)

    @app.get("/api/users/{user_id}/matched-materials")
    async def user_matched_materials(
        user_id: int,
        range: str = "month",
        start_date: str = "",
        end_date: str = "",
        q: str = "",
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            payload = service.matched_materials_for_user(user_id, range, start_date, end_date, q)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(payload)

    @app.delete("/api/user-keywords/{keyword_id}")
    async def delete_user_keyword(keyword_id: int, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        service.delete_user_keyword(keyword_id)
        return JSONResponse({"ok": True})
