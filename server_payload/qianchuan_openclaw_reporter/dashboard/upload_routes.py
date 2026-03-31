from __future__ import annotations

import json
from typing import Any

from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from dashboard.api_response import api_response

def register_upload_routes(app: Any, service: Any, require_material_uploader: Any) -> None:
    def queue_upload_job(payload: dict[str, Any], note: str) -> dict[str, Any]:
        from dashboard.celery_app import celery_app

        task = celery_app.send_task("dashboard.material_upload", args=[int(payload["id"])])
        service.attach_material_upload_task(int(payload["id"]), str(task.id or ""))
        payload["task_id"] = str(task.id or "")
        payload["queued"] = True
        payload["note"] = str(note or "Upload job has been queued and is waiting for the worker.")
        return payload

    @app.get("/api/upload/targets")
    async def upload_targets(
        scope: str = "plan",
        q: str = "",
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        return api_response(service._visible_upload_targets(user, scope, q))

    @app.get("/api/upload/jobs")
    async def upload_jobs(user: dict[str, Any] = Depends(require_material_uploader)) -> JSONResponse:
        return api_response({"items": service.list_material_upload_jobs(user)})

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
            raise HTTPException(status_code=400, detail="target_plan_ids format is invalid") from exc
        payload = await service.create_material_upload_job(user, scope, query_text, plan_ids, files)
        return api_response(
            queue_upload_job(payload, "Upload job has been queued and is waiting for the worker."),
            status_code=202,
        )

    @app.post("/api/upload/jobs/{job_id}/retry")
    async def retry_upload_job(
        job_id: int,
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        payload = service.retry_material_upload_job(user, int(job_id))
        return api_response(
            queue_upload_job(payload, "Retry job has been queued and is waiting for the worker."),
            status_code=202,
        )

    @app.delete("/api/upload/jobs/{job_id}")
    async def delete_upload_job(
        job_id: int,
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        payload = service.delete_material_upload_job(user, int(job_id))
        return api_response({"ok": True, **payload})
