from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Any, Protocol

from fastapi import Depends, HTTPException, Request, status


def build_password_hash(password: str, iterations: int = 390000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    text = str(stored_hash or "").strip()
    try:
        algorithm, iterations_text, salt_b64, digest_b64 = text.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


class AuthServiceProtocol(Protocol):
    def get_user_by_id(self, user_id: int, include_disabled: bool = False) -> dict[str, Any] | None: ...

    def can_upload_materials(self, user: dict[str, Any] | None) -> bool: ...


def build_auth_dependencies(
    service: AuthServiceProtocol,
    *,
    role_admin: str,
    role_supervisor: str,
):
    def require_auth(request: Request) -> dict[str, Any]:
        user_id = request.session.get("user_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        user = service.get_user_by_id(int(user_id))
        if not user:
            request.session.clear()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        return user

    def require_admin(user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
        if str(user.get("role") or "") != role_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return user

    def require_material_uploader(user: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
        role = str(user.get("role") or "")
        if role == role_admin:
            return user
        if role == role_supervisor and service.can_upload_materials(user):
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    return require_auth, require_admin, require_material_uploader
