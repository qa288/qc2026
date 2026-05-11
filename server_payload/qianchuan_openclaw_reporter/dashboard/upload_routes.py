from __future__ import annotations

import json
from typing import Any

from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from dashboard.api_response import api_response

def register_upload_routes(app: Any, service: Any, require_material_uploader: Any) -> None:
    def queue_upload_job(payload: dict[str, Any], note: str, stage: str = "library") -> dict[str, Any]:
        from dashboard.celery_app import celery_app

        normalized_stage = "bind" if str(stage or "").strip().lower() == "bind" else "library"
        if service.material_uploads_paused():
            pause_note = "上传任务已暂停，等待恢复后继续执行。"
            service.attach_material_upload_task(
                int(payload["id"]),
                str(payload.get("task_id") or ""),
                status_text=str(payload.get("status") or "queued"),
                note=pause_note,
            )
            payload["queued"] = False
            payload["paused"] = True
            payload["pause"] = service.material_upload_pause_status()
            payload["note"] = pause_note
            payload["queued_stage"] = normalized_stage
            return payload
        task_name = "dashboard.material_upload_bind" if normalized_stage == "bind" else "dashboard.material_upload_library"
        queue_name = "upload-bind" if normalized_stage == "bind" else "upload-library"
        status_text = str(payload.get("status") or ("running" if normalized_stage == "bind" else "queued"))
        task = celery_app.send_task(task_name, args=[int(payload["id"])], queue=queue_name)
        service.attach_material_upload_task(
            int(payload["id"]),
            str(task.id or ""),
            status_text=status_text,
            note=str(note or payload.get("note") or ""),
        )
        payload["task_id"] = str(task.id or "")
        payload["queued"] = True
        payload["note"] = str(note or payload.get("note") or "Upload job has been queued and is waiting for the worker.")
        payload["queued_stage"] = normalized_stage
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

    @app.get("/api/upload/pause")
    async def upload_pause_status(user: dict[str, Any] = Depends(require_material_uploader)) -> JSONResponse:
        _ = user
        return api_response(service.material_upload_pause_status())

    @app.post("/api/upload/pause")
    async def pause_uploads(user: dict[str, Any] = Depends(require_material_uploader)) -> JSONResponse:
        _ = user
        return api_response(service.pause_material_uploads("manual"))

    @app.post("/api/upload/resume")
    async def resume_uploads(user: dict[str, Any] = Depends(require_material_uploader)) -> JSONResponse:
        _ = user
        service.resume_material_uploads()
        return api_response(service.material_upload_pause_status())

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

    @app.post("/api/upload/jobs/prepare")
    async def prepare_upload_job(
        scope: str = Form("plan"),
        query_text: str = Form(""),
        target_plan_ids: str = Form("[]"),
        file_count: int = Form(0),
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        try:
            plan_ids = [int(item) for item in json.loads(str(target_plan_ids or "[]"))]
        except Exception as exc:
            raise HTTPException(status_code=400, detail="target_plan_ids format is invalid") from exc
        payload = service.prepare_material_upload_job(user, scope, query_text, plan_ids, int(file_count or 0))
        return api_response(payload, status_code=202)

    @app.post("/api/upload/jobs/{job_id}/files")
    async def upload_job_file(
        job_id: int,
        file: UploadFile = File(...),
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        payload = await service.receive_material_upload_job_file(user, int(job_id), file)
        if payload.get("should_queue"):
            return api_response(
                queue_upload_job(payload, "视频已上传到服务器，后台已开始处理已上传的视频。"),
                status_code=202,
            )
        return api_response(payload, status_code=202)

    @app.get("/api/upload/jobs/{job_id}/files/chunks")
    async def upload_job_file_chunk_status(
        job_id: int,
        file_index: int,
        file_name: str,
        file_size: int,
        total_chunks: int,
        chunk_size: int,
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        payload = service.material_upload_job_file_chunk_status(
            user,
            int(job_id),
            file_index=int(file_index),
            file_name=str(file_name or ""),
            file_size=int(file_size or 0),
            total_chunks=int(total_chunks or 0),
            chunk_size=int(chunk_size or 0),
        )
        return api_response(payload, status_code=200)

    @app.post("/api/upload/jobs/{job_id}/files/chunks")
    async def upload_job_file_chunk(
        job_id: int,
        file_index: int = Form(...),
        chunk_index: int = Form(...),
        total_chunks: int = Form(...),
        file_name: str = Form(...),
        file_size: int = Form(...),
        file_last_modified: str = Form(""),
        mime_type: str = Form(""),
        chunk_size: int = Form(0),
        chunk: UploadFile = File(...),
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        payload = await service.receive_material_upload_job_file_chunk(
            user,
            int(job_id),
            chunk,
            file_index=int(file_index),
            chunk_index=int(chunk_index),
            total_chunks=int(total_chunks),
            file_name=str(file_name or ""),
            file_size=int(file_size),
            file_last_modified=str(file_last_modified or ""),
            mime_type=str(mime_type or ""),
            chunk_size=int(chunk_size or 0),
        )
        if payload.get("should_queue"):
            return api_response(
                queue_upload_job(payload, "视频已全部上传到服务器，后台开始处理素材。"),
                status_code=202,
            )
        return api_response(payload, status_code=202)

    @app.post("/api/upload/jobs/{job_id}/files/complete")
    async def complete_upload_job_files(
        job_id: int,
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        payload = service.finalize_material_upload_job_files(user, int(job_id))
        if payload.get("should_queue"):
            return api_response(
                queue_upload_job(payload, "视频已全部上传到服务器，后台开始处理素材。"),
                status_code=202,
            )
        return api_response(payload, status_code=202)

    @app.post("/api/upload/jobs/{job_id}/retry")
    async def retry_upload_job(
        job_id: int,
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        payload = service.retry_material_upload_job(user, int(job_id))
        queue_stage = "library" if int(payload.get("upload_retry_count", 0) or 0) > 0 else "bind"
        return api_response(
            queue_upload_job(payload, "Retry job has been queued and is waiting for the worker.", stage=queue_stage),
            status_code=202,
        )

    @app.get("/api/upload/jobs/{job_id}/targets")
    async def upload_job_targets(
        job_id: int,
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        return api_response(service.list_material_upload_job_targets(user, int(job_id)))

    @app.get("/api/upload/jobs/{job_id}/targets/{target_id}/files")
    async def upload_job_target_files(
        job_id: int,
        target_id: int,
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        return api_response(service.list_material_upload_job_target_files(user, int(job_id), int(target_id)))

    @app.post("/api/upload/jobs/{job_id}/targets/{target_id}/retry")
    async def retry_upload_target(
        job_id: int,
        target_id: int,
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        payload = service.retry_material_upload_target(user, int(job_id), int(target_id))
        queue_stage = "library" if int(payload.get("upload_retry_count", 0) or 0) > 0 else "bind"
        return api_response(
            queue_upload_job(payload, "Retry job has been queued and is waiting for the worker.", stage=queue_stage),
            status_code=202,
        )

    @app.post("/api/upload/jobs/{job_id}/targets/{target_id}/files/{file_id}/retry")
    async def retry_upload_target_file(
        job_id: int,
        target_id: int,
        file_id: int,
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        payload = service.retry_material_upload_target_file(user, int(job_id), int(target_id), int(file_id))
        queue_stage = "library" if int(payload.get("upload_retry_count", 0) or 0) > 0 else "bind"
        return api_response(
            queue_upload_job(payload, "Retry job has been queued and is waiting for the worker.", stage=queue_stage),
            status_code=202,
        )

    @app.post("/api/upload/jobs/{job_id}/target-assets/{target_asset_id}/retry")
    async def retry_upload_target_asset(
        job_id: int,
        target_asset_id: int,
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        payload = service.retry_material_upload_target_asset(user, int(job_id), int(target_asset_id))
        queue_stage = "library" if int(payload.get("upload_retry_count", 0) or 0) > 0 else "bind"
        return api_response(
            queue_upload_job(payload, "Retry job has been queued and is waiting for the worker.", stage=queue_stage),
            status_code=202,
        )

    @app.delete("/api/upload/jobs/{job_id}")
    async def delete_upload_job(
        job_id: int,
        user: dict[str, Any] = Depends(require_material_uploader),
    ) -> JSONResponse:
        payload = service.delete_material_upload_job(user, int(job_id))
        return api_response({"ok": True, **payload})
