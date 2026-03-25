from __future__ import annotations

from typing import Any, Callable


class UserAccess:
    def __init__(
        self,
        db_factory: Callable[[], Any],
        now_text: Callable[[], str],
        password_hasher: Callable[[str], str],
        password_verifier: Callable[[str, str], bool],
        *,
        role_admin: str,
        role_supervisor: str,
        role_operator: str,
    ) -> None:
        self._db = db_factory
        self._now_text = now_text
        self._password_hasher = password_hasher
        self._password_verifier = password_verifier
        self._role_admin = role_admin
        self._role_supervisor = role_supervisor
        self._role_operator = role_operator

    def get_user_by_id(self, user_id: int, include_disabled: bool = False) -> dict[str, Any] | None:
        with self._db() as conn:
            row = conn.execute(
                """
                SELECT id, username, role, display_name, upload_materials_enabled, enabled, created_at, updated_at
                FROM app_users
                WHERE id = ?
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if not row:
            return None
        if not include_disabled and not bool(row["enabled"]):
            return None
        return dict(row)

    def authenticate_user(self, username: str, password: str) -> dict[str, Any] | None:
        with self._db() as conn:
            row = conn.execute(
                """
                SELECT id, username, password_hash, role, display_name, upload_materials_enabled, enabled
                FROM app_users
                WHERE username = ?
                LIMIT 1
                """,
                (str(username or "").strip(),),
            ).fetchone()
        if not row or not bool(row["enabled"]):
            return None
        if not self._password_verifier(password, str(row["password_hash"] or "")):
            return None
        payload = dict(row)
        payload.pop("password_hash", None)
        return payload

    def allowed_advertiser_ids_for_user(self, user: dict[str, Any] | None) -> set[int] | None:
        if not user:
            return None
        role = str(user.get("role") or "")
        if role in {self._role_admin, self._role_operator}:
            return None
        with self._db() as conn:
            rows = conn.execute(
                "SELECT advertiser_id FROM user_account_scopes WHERE user_id = ?",
                (int(user["id"]),),
            ).fetchall()
        return {int(row["advertiser_id"]) for row in rows}

    def can_upload_materials(self, user: dict[str, Any] | None) -> bool:
        if not user:
            return False
        role = str(user.get("role") or "")
        if role == self._role_admin:
            return True
        if role == self._role_supervisor:
            return bool(user.get("upload_materials_enabled"))
        return False

    def list_users(self) -> list[dict[str, Any]]:
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT
                    u.id,
                    u.username,
                    u.role,
                    u.display_name,
                    u.upload_materials_enabled,
                    u.enabled,
                    u.created_at,
                    u.updated_at,
                    COALESCE(sc.scope_count, 0) AS scope_count,
                    COALESCE(kw.keyword_count, 0) AS keyword_count
                FROM app_users u
                LEFT JOIN (
                    SELECT user_id, COUNT(*) AS scope_count
                    FROM user_account_scopes
                    GROUP BY user_id
                ) sc ON sc.user_id = u.id
                LEFT JOIN (
                    SELECT user_id, COUNT(*) AS keyword_count
                    FROM user_keywords
                    WHERE enabled = 1
                    GROUP BY user_id
                ) kw ON kw.user_id = u.id
                ORDER BY
                    CASE u.role
                        WHEN 'admin' THEN 1
                        WHEN 'supervisor' THEN 2
                        WHEN 'operator' THEN 3
                        ELSE 99
                    END,
                    u.username ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def create_user(self, payload: Any) -> dict[str, Any]:
        password = str(payload.password or "").strip()
        if not password:
            raise ValueError("创建账号时必须填写密码。")
        now = self._now_text()
        password_hash = self._password_hasher(password)
        role = str(payload.role).strip()
        upload_enabled = (
            1 if role == self._role_admin else 1 if role == self._role_supervisor and payload.upload_materials_enabled else 0
        )
        with self._db() as conn:
            exists = conn.execute(
                "SELECT 1 FROM app_users WHERE username = ? LIMIT 1",
                (str(payload.username).strip(),),
            ).fetchone()
            if exists:
                raise ValueError("用户名已存在。")
            conn.execute(
                """
                INSERT INTO app_users (username, password_hash, role, display_name, upload_materials_enabled, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.username).strip(),
                    password_hash,
                    role,
                    str(payload.display_name).strip(),
                    upload_enabled,
                    1 if payload.enabled else 0,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT id
                FROM app_users
                WHERE username = ?
                LIMIT 1
                """,
                (str(payload.username).strip(),),
            ).fetchone()
        return self.get_user_by_id(int(row["id"]), include_disabled=True) if row else {}

    def update_user(self, user_id: int, payload: Any) -> dict[str, Any]:
        current = self.get_user_by_id(user_id, include_disabled=True)
        if not current:
            raise ValueError("用户不存在。")
        role = str(payload.role).strip()
        upload_enabled = (
            1 if role == self._role_admin else 1 if role == self._role_supervisor and payload.upload_materials_enabled else 0
        )
        with self._db() as conn:
            exists = conn.execute(
                """
                SELECT 1
                FROM app_users
                WHERE username = ? AND id <> ?
                LIMIT 1
                """,
                (str(payload.username).strip(), user_id),
            ).fetchone()
            if exists:
                raise ValueError("用户名已存在。")
        params: list[Any] = [
            str(payload.username).strip(),
            role,
            str(payload.display_name).strip(),
            upload_enabled,
            1 if payload.enabled else 0,
            self._now_text(),
        ]
        sql = """
            UPDATE app_users
            SET username = ?, role = ?, display_name = ?, upload_materials_enabled = ?, enabled = ?, updated_at = ?
        """
        password = str(payload.password or "").strip()
        if password:
            sql += ", password_hash = ?"
            params.append(self._password_hasher(password))
        sql += " WHERE id = ?"
        params.append(user_id)
        with self._db() as conn:
            conn.execute(sql, tuple(params))
        return self.get_user_by_id(user_id, include_disabled=True) or {}

    def user_account_scopes(self, user_id: int) -> list[int]:
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT advertiser_id
                FROM user_account_scopes
                WHERE user_id = ?
                ORDER BY advertiser_id ASC
                """,
                (user_id,),
            ).fetchall()
        return [int(row["advertiser_id"]) for row in rows]

    def replace_user_account_scopes(self, user_id: int, advertiser_ids: list[int]) -> list[int]:
        if not self.get_user_by_id(user_id, include_disabled=True):
            raise ValueError("用户不存在。")
        unique_ids = sorted({int(item) for item in advertiser_ids if int(item) > 0})
        now = self._now_text()
        with self._db() as conn:
            conn.execute("DELETE FROM user_account_scopes WHERE user_id = ?", (user_id,))
            if unique_ids:
                conn.executemany(
                    """
                    INSERT INTO user_account_scopes (user_id, advertiser_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    [(user_id, advertiser_id, now) for advertiser_id in unique_ids],
                )
        return unique_ids

    def list_user_keywords(self, user_id: int) -> list[dict[str, Any]]:
        user = self.get_user_by_id(user_id, include_disabled=True)
        if not user:
            raise ValueError("用户不存在。")
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, keyword, enabled, created_at, updated_at
                FROM user_keywords
                WHERE user_id = ?
                ORDER BY enabled DESC, LENGTH(keyword) DESC, keyword ASC, id ASC
                """,
                (user_id,),
            ).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            item["enabled"] = bool(item["enabled"])
        return items

    def create_user_keyword(self, user_id: int, payload: Any) -> dict[str, Any]:
        user = self.get_user_by_id(user_id, include_disabled=True)
        if not user:
            raise ValueError("用户不存在。")
        if str(user.get("role") or "") != self._role_operator:
            raise ValueError("只有运营账号可以配置关键词。")
        keyword = str(payload.keyword or "").strip()
        if not keyword:
            raise ValueError("关键词不能为空。")
        now = self._now_text()
        with self._db() as conn:
            exists = conn.execute(
                """
                SELECT 1
                FROM user_keywords
                WHERE user_id = ? AND keyword = ?
                LIMIT 1
                """,
                (user_id, keyword),
            ).fetchone()
            if exists:
                raise ValueError("该运营账号下已存在相同关键词。")
            conn.execute(
                """
                INSERT INTO user_keywords (user_id, keyword, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, keyword, 1 if payload.enabled else 0, now, now),
            )
            row = conn.execute(
                """
                SELECT id, user_id, keyword, enabled, created_at, updated_at
                FROM user_keywords
                WHERE user_id = ? AND keyword = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, keyword),
            ).fetchone()
        item = dict(row) if row else {}
        if item:
            item["enabled"] = bool(item["enabled"])
        return item

    def delete_user_keyword(self, keyword_id: int) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM user_keywords WHERE id = ?", (keyword_id,))
