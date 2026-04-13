from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse


def _asset_version() -> str:
    base_dir = Path(__file__).resolve().parent
    candidates = [
        base_dir / "static" / "app.js",
        base_dir / "static" / "style.css",
        base_dir / "templates" / "index.html",
    ]
    version = 0
    for path in candidates:
        try:
            version = max(version, int(path.stat().st_mtime))
        except OSError:
            continue
    return str(version or 1)


def register_page_routes(app: Any, service: Any, app_name: str) -> None:
    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        if request.session.get("user_id"):
            return RedirectResponse("/", status_code=302)
        return service.templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"request": request, "app_name": app_name, "asset_version": _asset_version()},
        )

    @app.post("/login")
    async def login(request: Request, username: str = Form(...), password: str = Form(...)) -> RedirectResponse:
        user = service.authenticate_user(username, password)
        if user:
            request.session["authenticated"] = True
            request.session["user_id"] = int(user["id"])
            request.session["username"] = str(user["username"])
            request.session["role"] = str(user["role"])
            return RedirectResponse("/", status_code=302)
        return RedirectResponse("/login?error=1", status_code=302)

    @app.post("/logout")
    async def logout(request: Request) -> RedirectResponse:
        request.session.clear()
        return RedirectResponse("/login", status_code=302)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        if not request.session.get("user_id"):
            return RedirectResponse("/login", status_code=302)
        user = service.get_user_by_id(int(request.session["user_id"]))
        if not user:
            request.session.clear()
            return RedirectResponse("/login", status_code=302)
        return service.templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "request": request,
                "app_name": app_name,
                "customer_center_id": service.read_config()["customer_center_id"],
                "asset_version": _asset_version(),
            },
        )

    @app.get("/workbench", response_class=HTMLResponse)
    async def legacy_workbench(request: Request) -> RedirectResponse:
        if not request.session.get("user_id"):
            return RedirectResponse("/login", status_code=302)
        return RedirectResponse("/", status_code=302)
