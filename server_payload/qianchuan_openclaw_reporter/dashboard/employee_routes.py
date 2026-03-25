from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse

from dashboard.employee_schemas import EmployeeBindingPayload, EmployeeKeywordPayload, EmployeePayload


def register_employee_routes(app: Any, service: Any, require_admin: Any) -> None:
    @app.get("/api/employees")
    async def employees(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        return JSONResponse({"items": service.list_employees()})

    @app.post("/api/employees")
    async def create_employee(payload: EmployeePayload, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        try:
            item = service.create_employee(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(item)

    @app.put("/api/employees/{employee_id}")
    async def update_employee(
        employee_id: int,
        payload: EmployeePayload,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            item = service.update_employee(employee_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(item)

    @app.get("/api/employees/{employee_id}/keywords")
    async def employee_keywords(employee_id: int, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        return JSONResponse({"items": service.list_employee_keywords(employee_id)})

    @app.post("/api/employees/{employee_id}/keywords")
    async def create_employee_keyword(
        employee_id: int,
        payload: EmployeeKeywordPayload,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            item = service.create_employee_keyword(employee_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(item)

    @app.put("/api/employee-keywords/{keyword_id}")
    async def update_employee_keyword(
        keyword_id: int,
        payload: EmployeeKeywordPayload,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            item = service.update_employee_keyword(keyword_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(item)

    @app.delete("/api/employee-keywords/{keyword_id}")
    async def delete_employee_keyword(keyword_id: int, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        service.delete_employee_keyword(keyword_id)
        return JSONResponse({"ok": True})

    @app.get("/api/employees/{employee_id}/bindings")
    async def employee_bindings(employee_id: int, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        return JSONResponse({"items": service.list_employee_bindings(employee_id)})

    @app.post("/api/employees/{employee_id}/bindings")
    async def create_employee_binding(
        employee_id: int,
        payload: EmployeeBindingPayload,
        _user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        try:
            item = service.create_employee_binding(employee_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(item)

    @app.delete("/api/employee-bindings/{binding_id}")
    async def delete_employee_binding(binding_id: int, _user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        service.delete_employee_binding(binding_id)
        return JSONResponse({"ok": True})

    @app.get("/api/employee-match-preview")
    async def employee_match_preview(
        keyword: str,
        scope: str = "all",
        user: dict[str, Any] = Depends(require_admin),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        try:
            payload = service.preview_keyword_matches(keyword, scope, allowed)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(payload)
