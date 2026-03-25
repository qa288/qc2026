from __future__ import annotations

from typing import Any, Callable


class EmployeeAccess:
    def __init__(self, db_factory: Callable[[], Any], now_text: Callable[[], str]) -> None:
        self._db = db_factory
        self._now_text = now_text

    def list_employees(self) -> list[dict[str, Any]]:
        with self._db() as conn:
            employee_rows = conn.execute(
                """
                SELECT id, display_name, note, enabled, created_at, updated_at
                FROM employees
                ORDER BY enabled DESC, display_name ASC
                """
            ).fetchall()
            keyword_rows = conn.execute(
                """
                SELECT employee_id, COUNT(*) AS keyword_count
                FROM employee_keywords
                GROUP BY employee_id
                """
            ).fetchall()
            binding_rows = conn.execute(
                """
                SELECT employee_id, COUNT(*) AS binding_count
                FROM employee_manual_bindings
                GROUP BY employee_id
                """
            ).fetchall()
        keyword_count = {int(row["employee_id"]): int(row["keyword_count"]) for row in keyword_rows}
        binding_count = {int(row["employee_id"]): int(row["binding_count"]) for row in binding_rows}
        items: list[dict[str, Any]] = []
        for row in employee_rows:
            item = dict(row)
            item["keyword_count"] = keyword_count.get(int(row["id"]), 0)
            item["binding_count"] = binding_count.get(int(row["id"]), 0)
            item["enabled"] = bool(item["enabled"])
            items.append(item)
        return items

    def employee_detail(self, employee_id: int) -> dict[str, Any] | None:
        with self._db() as conn:
            row = conn.execute(
                """
                SELECT id, display_name, note, enabled, created_at, updated_at
                FROM employees
                WHERE id = ?
                LIMIT 1
                """,
                (employee_id,),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        return item

    def create_employee(self, payload: Any) -> dict[str, Any]:
        now = self._now_text()
        with self._db() as conn:
            exists = conn.execute(
                "SELECT 1 FROM employees WHERE display_name = ? LIMIT 1",
                (str(payload.display_name).strip(),),
            ).fetchone()
            if exists:
                raise ValueError("归属人名称已存在。")
            conn.execute(
                """
                INSERT INTO employees (display_name, note, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(payload.display_name).strip(),
                    str(payload.note).strip(),
                    1 if payload.enabled else 0,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT id
                FROM employees
                WHERE display_name = ?
                LIMIT 1
                """,
                (str(payload.display_name).strip(),),
            ).fetchone()
        return self.employee_detail(int(row["id"])) if row else {}

    def update_employee(self, employee_id: int, payload: Any) -> dict[str, Any]:
        if not self.employee_detail(employee_id):
            raise ValueError("归属人不存在。")
        with self._db() as conn:
            exists = conn.execute(
                """
                SELECT 1
                FROM employees
                WHERE display_name = ? AND id <> ?
                LIMIT 1
                """,
                (str(payload.display_name).strip(), employee_id),
            ).fetchone()
            if exists:
                raise ValueError("归属人名称已存在。")
            conn.execute(
                """
                UPDATE employees
                SET display_name = ?, note = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(payload.display_name).strip(),
                    str(payload.note).strip(),
                    1 if payload.enabled else 0,
                    self._now_text(),
                    employee_id,
                ),
            )
        return self.employee_detail(employee_id) or {}

    def list_employee_keywords(self, employee_id: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT k.id, k.employee_id, e.display_name AS employee_name, k.keyword, k.scope, k.priority,
                   k.enabled, k.created_at, k.updated_at
            FROM employee_keywords AS k
            INNER JOIN employees AS e ON e.id = k.employee_id
        """
        params: tuple[Any, ...] = ()
        if employee_id is not None:
            query += " WHERE k.employee_id = ?"
            params = (employee_id,)
        query += " ORDER BY e.display_name ASC, k.priority ASC, LENGTH(k.keyword) DESC, k.id ASC"
        with self._db() as conn:
            rows = conn.execute(query, params).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            item["enabled"] = bool(item["enabled"])
        return items

    def create_employee_keyword(self, employee_id: int, payload: Any) -> dict[str, Any]:
        if not self.employee_detail(employee_id):
            raise ValueError("归属人不存在。")
        now = self._now_text()
        with self._db() as conn:
            exists = conn.execute(
                """
                SELECT 1
                FROM employee_keywords
                WHERE employee_id = ? AND keyword = ? AND scope = ?
                LIMIT 1
                """,
                (employee_id, str(payload.keyword).strip(), str(payload.scope).strip()),
            ).fetchone()
            if exists:
                raise ValueError("同一归属人下已存在相同关键词。")
            conn.execute(
                """
                INSERT INTO employee_keywords (employee_id, keyword, scope, priority, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    employee_id,
                    str(payload.keyword).strip(),
                    str(payload.scope).strip(),
                    int(payload.priority),
                    1 if payload.enabled else 0,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT id
                FROM employee_keywords
                WHERE employee_id = ? AND keyword = ? AND scope = ? AND created_at = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (employee_id, str(payload.keyword).strip(), str(payload.scope).strip(), now),
            ).fetchone()
        keyword_id = int(row["id"]) if row else 0
        return next((item for item in self.list_employee_keywords(employee_id) if int(item["id"]) == keyword_id), {})

    def update_employee_keyword(self, keyword_id: int, payload: Any) -> dict[str, Any]:
        now = self._now_text()
        with self._db() as conn:
            row = conn.execute(
                "SELECT employee_id FROM employee_keywords WHERE id = ? LIMIT 1",
                (keyword_id,),
            ).fetchone()
            if not row:
                raise ValueError("关键词不存在。")
            employee_id = int(row["employee_id"])
            conn.execute(
                """
                UPDATE employee_keywords
                SET keyword = ?, scope = ?, priority = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(payload.keyword).strip(),
                    str(payload.scope).strip(),
                    int(payload.priority),
                    1 if payload.enabled else 0,
                    now,
                    keyword_id,
                ),
            )
        return next((item for item in self.list_employee_keywords(employee_id) if int(item["id"]) == keyword_id), {})

    def delete_employee_keyword(self, keyword_id: int) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM employee_keywords WHERE id = ?", (keyword_id,))

    def list_employee_bindings(self, employee_id: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT b.id, b.employee_id, e.display_name AS employee_name, b.object_type, b.object_key,
                   b.object_label, b.note, b.created_at, b.updated_at
            FROM employee_manual_bindings AS b
            INNER JOIN employees AS e ON e.id = b.employee_id
        """
        params: tuple[Any, ...] = ()
        if employee_id is not None:
            query += " WHERE b.employee_id = ?"
            params = (employee_id,)
        query += " ORDER BY e.display_name ASC, b.object_type ASC, b.object_label ASC, b.id ASC"
        with self._db() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def create_employee_binding(self, employee_id: int, payload: Any) -> dict[str, Any]:
        if not self.employee_detail(employee_id):
            raise ValueError("归属人不存在。")
        now = self._now_text()
        with self._db() as conn:
            exists = conn.execute(
                """
                SELECT 1
                FROM employee_manual_bindings
                WHERE object_type = ? AND object_key = ?
                LIMIT 1
                """,
                (str(payload.object_type).strip(), str(payload.object_key).strip()),
            ).fetchone()
            if exists:
                raise ValueError("该对象已经绑定到其他归属人。")
            conn.execute(
                """
                INSERT INTO employee_manual_bindings (employee_id, object_type, object_key, object_label, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    employee_id,
                    str(payload.object_type).strip(),
                    str(payload.object_key).strip(),
                    str(payload.object_label).strip(),
                    str(payload.note).strip(),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT id
                FROM employee_manual_bindings
                WHERE employee_id = ? AND object_type = ? AND object_key = ?
                LIMIT 1
                """,
                (employee_id, str(payload.object_type).strip(), str(payload.object_key).strip()),
            ).fetchone()
        binding_id = int(row["id"]) if row else 0
        return next((item for item in self.list_employee_bindings(employee_id) if int(item["id"]) == binding_id), {})

    def delete_employee_binding(self, binding_id: int) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM employee_manual_bindings WHERE id = ?", (binding_id,))
