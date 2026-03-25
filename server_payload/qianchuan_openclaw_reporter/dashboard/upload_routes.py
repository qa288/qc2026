from __future__ import annotations

import json
from typing import Any

from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse


def register_upload_routes(app: Any, service: Any, require_material_uploader: Any) -> None:
    @app.get("/api/upload/targets")
    async def upload_targets(
        scope: str = "plan",
        q: str = "",
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        return JSONResponse(service._visible_upload_targets(user, scope, q))

    @app.get("/api/upload/jobs")
    async def upload_jobs(user: dict[str, Any] = Depends(require_material_uploader)) -> JSONResponse:
        return JSONResponse({"items": service.list_material_upload_jobs(user)})

    @app.post("/api/upload/jobs")
    async def create_upload_job(
        scope: str = Form("plan"),
        query_text: str = Form(""),
        target_plan_ids: str = Form("[]"),
        files: list[UploadFile] = File(...),
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        try:
            plan_ids = [int(item) for item in json.loads(str(target_plan_ids or "[]"))]
        except Exception as exc:
            raise HTTPException(status_code=400, detail="target_plan_ids 格式错误") from exc
        payload = await service.create_material_upload_job(user, scope, query_text, plan_ids, files)
        from dashboard.celery_app import celery_app

        task = celery_app.send_task("dashboard.material_upload", args=[int(payload["id"])])
        service.attach_material_upload_task(int(payload["id"]), str(task.id or ""))
        payload["task_id"] = str(task.id or "")
        payload["queued"] = True
        payload["note"] = "上传任务已入队，后台正在执行。"
        return JSONResponse(payload, status_code=202)
