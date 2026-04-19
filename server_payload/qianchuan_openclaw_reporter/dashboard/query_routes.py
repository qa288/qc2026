from __future__ import annotations

import asyncio
from typing import Any

import requests
from fastapi import Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from dashboard.api_response import api_response


def register_query_routes(
    app: Any,
    service: Any,
    require_auth: Any,
    require_admin: Any,
    role_admin: str,
    role_operator: str,
    timezone: str,
) -> None:
    def session_payload(user: dict[str, Any], allowed: set[int] | None) -> dict[str, Any]:
        return {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "display_name": user.get("display_name") or "",
            "upload_materials_enabled": bool(user.get("upload_materials_enabled")),
            "can_upload_materials": service.can_upload_materials(user),
            "scope_type": "all" if allowed is None else "restricted",
            "scope_count": None if allowed is None else len(allowed),
        }

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
        return api_response(payload)

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
        return api_response(payload)

    @app.get("/api/session/me")
    async def current_session(user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        return api_response(session_payload(user, allowed))

    @app.get("/api/catalog/accounts")
    async def available_accounts(
        display_scope: str = "current",
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        items = await asyncio.to_thread(service.latest_account_catalog, allowed, display_scope)
        return api_response({"items": items})

    @app.get("/api/bootstrap")
    async def bootstrap_data(
        display_scope: str = "current",
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        effective_display_scope = display_scope if str(user.get("role") or "") == role_admin else "current"
        latest_task = asyncio.create_task(asyncio.to_thread(service.dashboard_bootstrap_payload, effective_display_scope))
        config_task = asyncio.create_task(asyncio.to_thread(service.read_config))
        latest, current_config = await asyncio.gather(
            latest_task,
            config_task,
        )
        return api_response(
            {
                "session": session_payload(user, allowed),
                "latest": latest,
                "summaryHistory": [],
                "customerCenterId": current_config["customer_center_id"],
                "displayScope": effective_display_scope,
                "timezone": timezone,
            }
        )

    @app.get("/api/overview")
    async def overview_data(
        display_scope: str = "current",
        fresh: bool = False,
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        effective_display_scope = display_scope if str(user.get("role") or "") == role_admin else "current"
        latest_task = asyncio.create_task(
            asyncio.to_thread(service.dashboard_overview_payload, allowed, effective_display_scope, user, bool(fresh))
        )
        latest = await latest_task
        return api_response(
            {
                "latest": latest,
                "summaryHistory": [],
                "displayScope": effective_display_scope,
                "timezone": timezone,
            }
        )

    @app.get("/api/admin/runtime")
    async def admin_runtime_data(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        return api_response(await asyncio.to_thread(service.admin_runtime_payload))

    @app.get("/api/admin/alerts")
    async def admin_alerts_data(_user: dict[str, Any] = Depends(require_admin)) -> JSONResponse:
        return api_response(await asyncio.to_thread(service.admin_alerts_payload))

    @app.get("/api/dashboard")
    async def dashboard_data(
        display_scope: str = "current",
        fresh: bool = False,
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        is_admin = str(user.get("role") or "") == role_admin
        effective_display_scope = display_scope if is_admin else "current"
        latest_task = asyncio.create_task(
            asyncio.to_thread(service.dashboard_overview_payload, allowed, effective_display_scope, user, bool(fresh))
        )
        config_task = asyncio.create_task(asyncio.to_thread(service.read_config))
        admin_runtime_task = asyncio.create_task(asyncio.to_thread(service.admin_runtime_payload)) if is_admin else None
        admin_alerts_task = asyncio.create_task(asyncio.to_thread(service.admin_alerts_payload)) if is_admin else None
        latest, current_config = await asyncio.gather(
            latest_task,
            config_task,
        )
        admin_runtime = await admin_runtime_task if admin_runtime_task else {}
        admin_alerts = await admin_alerts_task if admin_alerts_task else {}
        return api_response(
            {
                "session": session_payload(user, allowed),
                "latest": latest,
                "tokenInfo": admin_runtime.get("tokenInfo"),
                "oceanEngineConfig": admin_runtime.get("oceanEngineConfig"),
                "summaryHistory": [],
                "notificationSettings": admin_alerts.get("notificationSettings", {}),
                "alertRules": admin_alerts.get("alertRules", []),
                "alertEvents": admin_alerts.get("alertEvents", []),
                "customerCenterId": current_config["customer_center_id"],
                "displayScope": effective_display_scope,
                "timezone": timezone,
            }
        )

    @app.get("/api/performance")
    async def performance_data(
        range: str = "day",
        start_date: str = "",
        end_date: str = "",
        section: str = "all",
        page: int = 1,
        page_size: int = 0,
        sort_key: str = "",
        sort_dir: str = "desc",
        search: str = "",
        account_filter: str = "",
        display_scope: str = "current",
        fresh: bool = False,
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        try:
            allowed = service.allowed_advertiser_ids_for_user(user)
            requested_section = str(section or "all").strip().lower()
            if requested_section not in {"all", "account", "plan", "breakdown"}:
                requested_section = "all"
            service_section = requested_section
            if str(user.get("role") or "") == role_operator and requested_section == "account":
                service_section = "plan"
            payload = await asyncio.to_thread(
                service.get_performance_snapshot,
                range,
                start_date,
                end_date,
                bool(fresh),
                allowed,
                service_section,
                display_scope,
            )
            if str(user.get("role") or "") == role_operator:
                payload = service._apply_operator_scope(payload, user)
            payload = service.trim_performance_payload_for_section(payload, requested_section)
            payload = service.paginate_performance_payload(
                payload,
                section=requested_section,
                page=page,
                page_size=page_size,
                sort_key=sort_key,
                sort_dir=sort_dir,
                search=search,
                account_filter=account_filter,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return api_response(payload)

    @app.get("/api/accounts/{advertiser_id}/history")
    async def account_history(advertiser_id: int, user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
        if str(user.get("role") or "") == role_operator:
            raise HTTPException(status_code=403, detail="operator cannot access account history")
        allowed = service.allowed_advertiser_ids_for_user(user)
        return api_response({"items": service.account_history(advertiser_id, allowed_advertiser_ids=allowed)})

    @app.get("/api/plans/{ad_id}/history")
    async def plan_history(ad_id: int, user: dict[str, Any] = Depends(require_auth)) -> JSONResponse:
        if str(user.get("role") or "") == role_operator:
            raise HTTPException(status_code=403, detail="operator cannot access plan history")
        allowed = service.allowed_advertiser_ids_for_user(user)
        return api_response({"items": service.plan_history(ad_id, allowed_advertiser_ids=allowed)})

    @app.get("/api/plans/{ad_id}/assets")
    async def plan_assets(
        ad_id: int,
        snapshot_time: str = "",
        display_scope: str = "current",
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        if str(user.get("role") or "") == role_operator:
            raise HTTPException(status_code=403, detail="operator cannot access plan assets")
        allowed = service.allowed_advertiser_ids_for_user(user)
        return api_response(service.plan_assets(ad_id, snapshot_time, allowed, display_scope))

    @app.get("/api/material-rankings")
    async def material_rankings(
        snapshot_time: str = "",
        range: str = "day",
        start_date: str = "",
        end_date: str = "",
        mode: str = "performance",
        page: int = 1,
        page_size: int = 0,
        sort_key: str = "",
        sort_dir: str = "desc",
        search: str = "",
        display_scope: str = "current",
        fresh: bool = False,
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        effective_display_scope = "current"
        try:
            payload = await asyncio.to_thread(
                service.material_rankings_page_for_user,
                user,
                range,
                start_date,
                end_date,
                snapshot_time,
                allowed,
                effective_display_scope,
                mode,
                page,
                page_size,
                sort_key,
                sort_dir,
                search,
                bool(fresh),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return api_response(payload)


    @app.post("/api/material-relation-detail")
    async def material_relation_detail(
        relation_row: dict[str, Any] = Body(...),
        display_scope: str = "current",
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        try:
            payload = await asyncio.to_thread(
                service.material_relation_detail_lookup,
                material_key=str(relation_row.get("material_key") or "").strip(),
                material_type=str(relation_row.get("material_type") or "").strip(),
                range_key=str(relation_row.get("range") or relation_row.get("range_key") or "day").strip().lower() or "day",
                start_date=str(relation_row.get("start_date") or "").strip(),
                end_date=str(relation_row.get("end_date") or "").strip(),
                snapshot_time=str(relation_row.get("snapshot_time") or "").strip(),
                plan_ids=relation_row.get("plan_ids") or [],
                advertiser_ids=relation_row.get("advertiser_ids") or [],
                allowed_advertiser_ids=allowed,
                display_scope=display_scope,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return api_response(payload)

    @app.get("/api/team-material-rankings")
    async def team_material_rankings(
        snapshot_time: str = "",
        range: str = "day",
        start_date: str = "",
        end_date: str = "",
        page: int = 1,
        page_size: int = 0,
        sort_key: str = "",
        sort_dir: str = "desc",
        search: str = "",
        display_scope: str = "current",
        fresh: bool = False,
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        effective_display_scope = "current"
        try:
            payload = await asyncio.to_thread(
                service.team_material_rankings_page_for_user,
                user,
                range,
                start_date,
                end_date,
                allowed,
                effective_display_scope,
                page,
                page_size,
                sort_key,
                sort_dir,
                search,
                bool(fresh),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return api_response(payload)

    @app.get("/api/material-preview-curve")
    async def material_preview_curve(
        material_key: str,
        snapshot_time: str = "",
        range: str = "day",
        start_date: str = "",
        end_date: str = "",
        display_scope: str = "current",
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
                display_scope,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return api_response(payload)

    @app.post("/api/material-preview-source")
    async def material_preview_source(
        preview_row: dict[str, Any] = Body(...),
        snapshot_time: str = "",
        range: str = "day",
        start_date: str = "",
        end_date: str = "",
        display_scope: str = "current",
        user: dict[str, Any] = Depends(require_auth),
    ) -> JSONResponse:
        allowed = service.allowed_advertiser_ids_for_user(user)
        try:
            payload = await asyncio.to_thread(
                service.material_preview_source_v2,
                preview_row,
                range,
                start_date,
                end_date,
                snapshot_time,
                allowed,
                user,
                display_scope,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return api_response(payload)

    @app.get("/api/material-preview-stream")
    async def material_preview_stream(
        request: Request,
        target: str,
        expires: int,
        sig: str,
        _user: dict[str, Any] = Depends(require_auth),
    ) -> StreamingResponse:
        try:
            target_url = service.resolve_material_preview_proxy_target(target, expires, sig)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        range_header = str(request.headers.get("range") or "").strip()

        def open_remote_stream() -> Any:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/134.0.0.0 Safari/537.36"
                ),
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            if range_header:
                headers["Range"] = range_header
            response = requests.get(
                target_url,
                headers=headers,
                timeout=30,
                stream=True,
                allow_redirects=True,
            )
            response.raise_for_status()
            return response

        try:
            remote_response = await asyncio.to_thread(open_remote_stream)
        except requests.HTTPError as exc:
            response = getattr(exc, "response", None)
            detail = str(exc)
            if response is not None:
                try:
                    error_body = str(response.text or "")[:512].strip()
                    if error_body:
                        detail = f"{detail}: {error_body}"
                except Exception:
                    pass
            raise HTTPException(status_code=502, detail=detail) from exc
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        status_code = int(getattr(remote_response, "status_code", 0) or 200)
        passthrough_headers: dict[str, str] = {
            "Cache-Control": "private, max-age=300",
            "Accept-Ranges": "bytes",
        }
        for header_name in ("Content-Type", "Content-Length", "Content-Range", "Last-Modified", "ETag"):
            value = str(remote_response.headers.get(header_name) or "").strip()
            if value:
                passthrough_headers[header_name] = value

        async def stream_chunks() -> Any:
            try:
                for chunk in remote_response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        break
                    yield chunk
            finally:
                try:
                    remote_response.close()
                except Exception:
                    pass

        return StreamingResponse(
            stream_chunks(),
            status_code=status_code,
            headers=passthrough_headers,
            media_type=str(remote_response.headers.get("Content-Type") or "video/mp4"),
        )

    @app.get("/api/comments")
    async def comments(
        range: str = "day",
        start_date: str = "",
        end_date: str = "",
        advertiser_id: int = 0,
        force: bool = False,
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
                force,
            )
            payload = service._apply_comment_scope(payload, user)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return api_response(payload)

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
        return api_response(response_payload)

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
        return api_response(response_payload)
