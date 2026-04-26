from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

PLAN_SOURCE_UNI_PROMOTION = "UNI_PROMOTION"


class UploadAccess:
    def __init__(
        self,
        db_factory: Callable[[], Any],
        now_text: Callable[[], str],
        role_admin: str,
        allowed_advertiser_ids_for_user: Callable[[dict[str, Any] | None], set[int] | None],
        latest_snapshot: Callable[[set[int] | None], dict[str, Any] | None],
        current_customer_center_id: Callable[[], str],
        normalize_match_text: Callable[..., str],
        sanitize_material_title: Callable[[str], str],
        format_plan_status_text: Callable[[str, str], str] | None = None,
    ) -> None:
        self._db = db_factory
        self._now_text = now_text
        self._role_admin = role_admin
        self._allowed_advertiser_ids_for_user = allowed_advertiser_ids_for_user
        self._latest_snapshot = latest_snapshot
        self._current_customer_center_id = current_customer_center_id
        self._normalize_match_text = normalize_match_text
        self._sanitize_material_title = sanitize_material_title
        self._format_plan_status_text = format_plan_status_text
        self._column_exists_cache: dict[tuple[str, str, str], bool] = {}

    @staticmethod
    def _column_exists_locked(conn: Any, table_name: str, column_name: str) -> bool:
        table = str(table_name or "").strip()
        column = str(column_name or "").strip()
        if not table or not column:
            return False
        if getattr(conn, "backend", "") == "postgres":
            row = conn.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
                LIMIT 1
                """,
                (table, column),
            ).fetchone()
            return bool(row)
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(str(row["name"]) == column for row in rows)

    @staticmethod
    def _empty_visible_upload_targets(scope: str, query: str) -> dict[str, Any]:
        return {
            "scope": scope,
            "query": str(query or "").strip(),
            "snapshot_time": "",
            "accounts": [],
            "plans": [],
            "plan_count": 0,
            "account_count": 0,
        }

    @staticmethod
    def _normalize_allowed_advertiser_ids(
        allowed_advertiser_ids: set[int] | list[int] | tuple[int, ...] | None,
    ) -> list[int] | None:
        if allowed_advertiser_ids is None:
            return None
        return sorted({int(item) for item in allowed_advertiser_ids if int(item or 0) > 0})

    def _column_exists_cached_locked(self, conn: Any, table_name: str, column_name: str) -> bool:
        key = (str(getattr(conn, "backend", "") or ""), str(table_name or "").strip(), str(column_name or "").strip())
        if key not in self._column_exists_cache:
            self._column_exists_cache[key] = self._column_exists_locked(conn, table_name, column_name)
        return self._column_exists_cache[key]

    def _upload_target_account_rows_locked(self, conn: Any, allowed_advertiser_ids: list[int] | None) -> list[dict[str, Any]]:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        where_clauses = ["customer_center_id = ?"]
        params: list[Any] = [customer_center_id]
        if allowed_advertiser_ids is not None:
            placeholders = ",".join("?" for _ in allowed_advertiser_ids)
            where_clauses.append(f"advertiser_id IN ({placeholders})")
            params.extend(allowed_advertiser_ids)
        rows = conn.execute(
            f"""
            SELECT
                snapshot_time,
                advertiser_id,
                advertiser_name,
                stat_cost,
                pay_amount,
                order_count,
                roi
            FROM account_current
            WHERE {" AND ".join(where_clauses)}
            ORDER BY stat_cost DESC, advertiser_id ASC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _upload_target_plan_rows_locked(self, conn: Any, allowed_advertiser_ids: list[int] | None) -> list[dict[str, Any]]:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        has_plan_source = self._column_exists_cached_locked(conn, "plan_current", "plan_source")
        has_status = self._column_exists_cached_locked(conn, "plan_current", "status")
        has_opt_status = self._column_exists_cached_locked(conn, "plan_current", "opt_status")
        where_clauses = ["customer_center_id = ?"]
        params: list[Any] = [customer_center_id]
        if has_plan_source:
            where_clauses.append("COALESCE(plan_source, 'UNI_PROMOTION') = 'UNI_PROMOTION'")
        if allowed_advertiser_ids is not None:
            placeholders = ",".join("?" for _ in allowed_advertiser_ids)
            where_clauses.append(f"advertiser_id IN ({placeholders})")
            params.extend(allowed_advertiser_ids)
        rows = conn.execute(
            f"""
            SELECT
                snapshot_time,
                advertiser_id,
                advertiser_name,
                ad_id,
                ad_name,
                product_id,
                product_name,
                anchor_name,
                marketing_goal,
                {"plan_source," if has_plan_source else "'UNI_PROMOTION' AS plan_source,"}
                {"status," if has_status else "'' AS status,"}
                {"opt_status," if has_opt_status else "'' AS opt_status,"}
                stat_cost,
                pay_amount,
                order_count,
                roi
            FROM plan_current
            WHERE {" AND ".join(where_clauses)}
            ORDER BY stat_cost DESC, advertiser_id ASC, ad_id ASC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _upload_plan_status_text(self, item: dict[str, Any]) -> str:
        status = str(item.get("status") or "").strip()
        opt_status = str(item.get("opt_status") or "").strip()
        if callable(self._format_plan_status_text):
            try:
                return str(self._format_plan_status_text(status, opt_status) or "")
            except Exception:
                pass
        return " / ".join(part for part in (status, opt_status) if part)

    def _upload_target_plan_paused(self, item: dict[str, Any]) -> bool:
        status = str(item.get("status") or "").strip().upper()
        opt_status = str(item.get("opt_status") or "").strip().upper()
        status_text = str(self._upload_plan_status_text(item) or "").strip()
        if status_text == "???":
            return True
        return status == "DISABLE" and opt_status in {"", "DISABLE"}

    def visible_upload_targets(self, user: dict[str, Any], scope: str, query: str) -> dict[str, Any]:
        normalized_scope = "account" if str(scope or "").strip().lower() == "account" else "plan"
        query_text = str(query or "").strip().casefold()
        allowed = self._normalize_allowed_advertiser_ids(self._allowed_advertiser_ids_for_user(user))
        if allowed is not None and not allowed:
            return self._empty_visible_upload_targets(normalized_scope, query)
        with self._db() as conn:
            accounts = self._upload_target_account_rows_locked(conn, allowed)
            plans = self._upload_target_plan_rows_locked(conn, allowed)
        if not accounts and not plans:
            return self._empty_visible_upload_targets(normalized_scope, query)
        account_map = {int(item.get("advertiser_id", 0) or 0): dict(item) for item in accounts}
        if normalized_scope == "account":
            matched_accounts = []
            for item in accounts:
                haystack = self._normalize_match_text(
                    str(item.get("advertiser_name") or ""),
                    str(item.get("advertiser_id") or ""),
                )
                if not query_text or query_text in haystack:
                    matched_accounts.append(dict(item))
            account_ids = {int(item.get("advertiser_id", 0) or 0) for item in matched_accounts}
            target_plans = [
                dict(item)
                for item in plans
                if int(item.get("advertiser_id", 0) or 0) in account_ids and not self._upload_target_plan_paused(item)
            ]
        else:
            target_plans = []
            for item in plans:
                if self._upload_target_plan_paused(item):
                    continue
                haystack = self._normalize_match_text(
                    str(item.get("ad_name") or ""),
                    str(item.get("product_name") or ""),
                    str(item.get("anchor_name") or ""),
                    str(item.get("advertiser_name") or ""),
                    str(item.get("ad_id") or ""),
                )
                if not query_text or query_text in haystack:
                    target_plans.append(dict(item))
            account_ids = {int(item.get("advertiser_id", 0) or 0) for item in target_plans}
            matched_accounts = [account_map[item] for item in account_ids if item in account_map]
        normalized_plans = []
        plan_counts_by_advertiser: dict[int, int] = {}
        for item in target_plans:
            advertiser_id = int(item.get("advertiser_id", 0) or 0)
            plan_counts_by_advertiser[advertiser_id] = plan_counts_by_advertiser.get(advertiser_id, 0) + 1
            normalized_plans.append(
                {
                    "advertiser_id": advertiser_id,
                    "advertiser_name": str(item.get("advertiser_name") or ""),
                    "ad_id": int(item.get("ad_id", 0) or 0),
                    "ad_name": str(item.get("ad_name") or ""),
                    "product_id": str(item.get("product_id") or ""),
                    "product_name": str(item.get("product_name") or ""),
                    "anchor_name": str(item.get("anchor_name") or ""),
                    "marketing_goal": str(item.get("marketing_goal") or ""),
                    "stat_cost": round(float(item.get("stat_cost", 0.0) or 0.0), 2),
                    "pay_amount": round(float(item.get("pay_amount", 0.0) or 0.0), 2),
                    "order_count": int(float(item.get("order_count", 0.0) or 0.0)),
                    "roi": round(float(item.get("roi", 0.0) or 0.0), 2),
                    "status_text": self._upload_plan_status_text(item),
                }
            )
        normalized_plans.sort(
            key=lambda item: (
                str(item["advertiser_name"]),
                -float(item["stat_cost"]),
                str(item["ad_name"]),
                int(item["ad_id"]),
            )
        )
        normalized_accounts = [
            {
                "advertiser_id": int(item.get("advertiser_id", 0) or 0),
                "advertiser_name": str(item.get("advertiser_name") or ""),
                "plan_count": int(plan_counts_by_advertiser.get(int(item.get("advertiser_id", 0) or 0), 0)),
                "stat_cost": round(float(item.get("stat_cost", 0.0) or 0.0), 2),
                "pay_amount": round(float(item.get("pay_amount", 0.0) or 0.0), 2),
                "order_count": int(float(item.get("order_count", 0.0) or 0.0)),
                "roi": round(float(item.get("roi", 0.0) or 0.0), 2),
            }
            for item in matched_accounts
        ]
        normalized_accounts.sort(
            key=lambda item: (-float(item["stat_cost"]), str(item["advertiser_name"]), int(item["advertiser_id"]))
        )
        snapshot_time = max(
            (str(item.get("snapshot_time") or "") for item in [*accounts, *plans]),
            default="",
        )
        return {
            "scope": normalized_scope,
            "query": str(query or "").strip(),
            "snapshot_time": snapshot_time,
            "accounts": normalized_accounts,
            "plans": normalized_plans,
            "plan_count": len(normalized_plans),
            "account_count": len(normalized_accounts),
        }

    def update_material_upload_job(self, conn: Any, job_id: int, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields.keys())
        params = list(fields.values()) + [job_id]
        conn.execute(
            f"UPDATE material_upload_jobs SET {assignments} WHERE id = ?",
            params,
        )

    def recompute_material_upload_job_locked(self, conn: Any, job_id: int) -> dict[str, int]:
        file_rows = conn.execute(
            """
            SELECT status
            FROM material_upload_job_files
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchall()
        target_rows = conn.execute(
            """
            SELECT status
            FROM material_upload_job_targets
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchall()
        processed_files = sum(1 for row in file_rows if str(row["status"] or "") in {"success", "failed", "partial"})
        success_files = sum(1 for row in file_rows if str(row["status"] or "") == "success")
        failed_files = sum(1 for row in file_rows if str(row["status"] or "") in {"failed", "partial"})
        uploaded_files = success_files
        processed_targets = sum(1 for row in target_rows if str(row["status"] or "") in {"success", "failed", "partial"})
        success_targets = sum(1 for row in target_rows if str(row["status"] or "") == "success")
        failed_targets = sum(1 for row in target_rows if str(row["status"] or "") in {"failed", "partial"})
        self.update_material_upload_job(
            conn,
            job_id,
            uploaded_files=uploaded_files,
            processed_files=processed_files,
            success_files=success_files,
            failed_files=failed_files,
            processed_targets=processed_targets,
            success_targets=success_targets,
            failed_targets=failed_targets,
            updated_at=self._now_text(),
        )
        return {
            "processed_files": processed_files,
            "success_files": success_files,
            "failed_files": failed_files,
            "processed_targets": processed_targets,
            "success_targets": success_targets,
            "failed_targets": failed_targets,
        }

    def material_title_from_filename(self, filename: str) -> str:
        base = Path(str(filename or "")).stem.strip() or "视频素材"
        return self._sanitize_material_title(base)

    def latest_plan_context_map(self, ad_ids: list[int]) -> dict[int, dict[str, Any]]:
        normalized_ids = sorted({int(item) for item in ad_ids if int(item or 0) > 0})
        if not normalized_ids:
            return {}
        placeholders = ",".join("?" for _ in normalized_ids)
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        with self._db() as conn:
            current_rows = conn.execute(
                f"""
                SELECT
                    ad_id,
                    advertiser_id,
                    advertiser_name,
                    ad_name,
                    product_id,
                    product_name,
                    anchor_name,
                    marketing_goal,
                    plan_source,
                    status,
                    opt_status,
                    snapshot_time,
                    '{{}}' AS raw_json
                FROM plan_current
                WHERE ad_id IN ({placeholders})
                  AND customer_center_id = ?
                  AND COALESCE(plan_source, 'UNI_PROMOTION') = 'UNI_PROMOTION'
                ORDER BY ad_id ASC
                """,
                [*normalized_ids, customer_center_id],
            ).fetchall()
            context_map = {int(row["ad_id"]): dict(row) for row in current_rows}
            missing_ids = [ad_id for ad_id in normalized_ids if ad_id not in context_map]
            if missing_ids:
                daily_placeholders = ",".join("?" for _ in missing_ids)
                daily_rows = conn.execute(
                    f"""
                    SELECT
                        ad_id,
                        advertiser_id,
                        advertiser_name,
                        ad_name,
                        product_id,
                        product_name,
                        anchor_name,
                        marketing_goal,
                        plan_source,
                        status,
                        opt_status,
                        snapshot_time,
                        '{{}}' AS raw_json
                    FROM plan_daily
                    WHERE ad_id IN ({daily_placeholders})
                      AND customer_center_id = ?
                      AND COALESCE(plan_source, 'UNI_PROMOTION') = 'UNI_PROMOTION'
                    ORDER BY ad_id ASC, biz_date DESC, snapshot_time DESC
                    """,
                    [*missing_ids, customer_center_id],
                ).fetchall()
                for row in daily_rows:
                    ad_id = int(row["ad_id"] or 0)
                    if ad_id <= 0 or ad_id in context_map:
                        continue
                    context_map[ad_id] = dict(row)
        for item in context_map.values():
            item["raw_json"] = str(item.get("raw_json") or "{}")
        return context_map

    def find_advertiser_material_asset_locked(self, conn: Any, advertiser_id: int, file_sha256: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT advertiser_id, file_sha256, material_id, video_id, video_url, material_name, created_at, updated_at
            FROM advertiser_material_assets
            WHERE advertiser_id = ? AND file_sha256 = ?
            LIMIT 1
            """,
            (advertiser_id, file_sha256),
        ).fetchone()
        return dict(row) if row else None

    def upsert_advertiser_material_asset_locked(
        self,
        conn: Any,
        advertiser_id: int,
        file_sha256: str,
        material_id: str,
        video_id: str,
        video_url: str,
        material_name: str,
    ) -> None:
        now = self._now_text()
        conn.execute(
            """
            INSERT INTO advertiser_material_assets (
                advertiser_id, file_sha256, material_id, video_id, video_url, material_name, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (advertiser_id, file_sha256) DO UPDATE SET
                material_id = excluded.material_id,
                video_id = excluded.video_id,
                video_url = excluded.video_url,
                material_name = excluded.material_name,
                updated_at = excluded.updated_at
            """,
            (advertiser_id, file_sha256, material_id, video_id, video_url, material_name, now, now),
        )

    def upsert_material_upload_file_asset_locked(
        self,
        conn: Any,
        job_id: int,
        file_id: int,
        advertiser_id: int,
        advertiser_name: str,
        status: str,
        material_id: str = "",
        video_id: str = "",
        video_url: str = "",
        message: str = "",
    ) -> None:
        now = self._now_text()
        existing = conn.execute(
            """
            SELECT id
            FROM material_upload_job_file_assets
            WHERE job_id = ? AND file_id = ? AND advertiser_id = ?
            LIMIT 1
            """,
            (job_id, file_id, advertiser_id),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE material_upload_job_file_assets
                SET advertiser_name = ?, status = ?, material_id = ?, video_id = ?, video_url = ?, message = ?, updated_at = ?
                WHERE id = ?
                """,
                (advertiser_name, status, material_id, video_id, video_url, message, now, existing["id"]),
            )
            return
        conn.execute(
            """
            INSERT INTO material_upload_job_file_assets (
                job_id, file_id, advertiser_id, advertiser_name, status, material_id, video_id, video_url, message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, file_id, advertiser_id, advertiser_name, status, material_id, video_id, video_url, message, now, now),
        )

    def upsert_material_upload_target_asset_locked(
        self,
        conn: Any,
        job_id: int,
        target_id: int,
        file_id: int,
        status: str,
        message: str = "",
    ) -> None:
        now = self._now_text()
        existing = conn.execute(
            """
            SELECT id
            FROM material_upload_job_target_assets
            WHERE job_id = ? AND target_id = ? AND file_id = ?
            LIMIT 1
            """,
            (job_id, target_id, file_id),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE material_upload_job_target_assets
                SET status = ?, message = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, message, now, existing["id"]),
            )
            return
        conn.execute(
            """
            INSERT INTO material_upload_job_target_assets (
                job_id, target_id, file_id, status, message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, target_id, file_id, status, message, now, now),
        )

    def attach_material_upload_task(self, job_id: int, task_id: str) -> None:
        with self._db() as conn:
            self.update_material_upload_job(
                conn,
                int(job_id),
                task_id=str(task_id or ""),
                status="queued",
                note="上传任务已入队，等待执行。",
                updated_at=self._now_text(),
            )

    def mark_material_upload_job_failed(self, job_id: int, message: str) -> None:
        with self._db() as conn:
            self.update_material_upload_job(
                conn,
                int(job_id),
                status="failed",
                note=str(message or "上传任务执行失败。"),
                completed_at=self._now_text(),
                updated_at=self._now_text(),
            )

    def list_material_upload_jobs(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        role = str(user.get("role") or "")
        with self._db() as conn:
            if role == self._role_admin:
                rows = conn.execute(
                    """
                    SELECT j.*, u.username, u.display_name
                    FROM material_upload_jobs j
                    LEFT JOIN app_users u ON u.id = j.created_by_user_id
                    ORDER BY j.id DESC
                    LIMIT 30
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT j.*, u.username, u.display_name
                    FROM material_upload_jobs j
                    LEFT JOIN app_users u ON u.id = j.created_by_user_id
                    WHERE j.created_by_user_id = ?
                    ORDER BY j.id DESC
                    LIMIT 30
                    """,
                    (int(user.get("id", 0) or 0),),
                ).fetchall()
            items = []
            for row in rows:
                job_id = int(row["id"])
                item = dict(row)
                item["created_by_label"] = str(item.get("display_name") or item.get("username") or "")
                status_text = str(item.get("status") or "").strip().lower()
                has_failures = (
                    int(item.get("failed_files", 0) or 0) > 0
                    or int(item.get("failed_targets", 0) or 0) > 0
                    or status_text in {"failed", "partial"}
                )
                detail_rows = conn.execute(
                    """
                    SELECT
                        ta.id AS target_asset_id,
                        ta.target_id,
                        ta.file_id,
                        ta.status AS target_asset_status,
                        ta.message AS target_message,
                        f.original_name,
                        f.status AS file_status,
                        f.message AS file_message,
                        t.advertiser_id,
                        t.advertiser_name,
                        t.ad_id,
                        t.ad_name,
                        fa.status AS file_asset_status,
                        fa.message AS file_asset_message,
                        fa.material_id,
                        fa.video_id
                    FROM material_upload_job_target_assets ta
                    JOIN material_upload_job_targets t ON t.id = ta.target_id
                    JOIN material_upload_job_files f ON f.id = ta.file_id
                    LEFT JOIN material_upload_job_file_assets fa
                        ON fa.job_id = ta.job_id
                       AND fa.file_id = ta.file_id
                       AND fa.advertiser_id = t.advertiser_id
                    WHERE ta.job_id = ?
                    ORDER BY ta.id ASC
                    LIMIT 500
                    """,
                    (job_id,),
                ).fetchall()
                detail_items: list[dict[str, Any]] = []
                completed_details = 0
                success_details = 0
                failed_items: list[dict[str, Any]] = []
                upload_operation_keys: set[tuple[int, int]] = set()
                upload_completed_keys: set[tuple[int, int]] = set()
                for detail_row in detail_rows:
                    target_asset_status = str(detail_row["target_asset_status"] or "").strip().lower()
                    file_asset_status = str(detail_row["file_asset_status"] or "").strip().lower()
                    file_status = str(detail_row["file_status"] or "").strip().lower()
                    target_asset_id = int(detail_row["target_asset_id"] or 0)
                    target_id = int(detail_row["target_id"] or 0)
                    file_id = int(detail_row["file_id"] or 0)
                    advertiser_id = int(detail_row["advertiser_id"] or 0)
                    upload_key = (file_id, advertiser_id)
                    upload_operation_keys.add(upload_key)
                    if file_asset_status in {"success", "failed"}:
                        upload_completed_keys.add(upload_key)
                    file_asset_failed = file_asset_status == "failed"
                    if target_asset_status == "success":
                        stage = "done"
                        display_status = "success"
                        message = str(detail_row["target_message"] or "")
                        completed_details += 1
                        success_details += 1
                    elif target_asset_status == "failed":
                        stage = "upload_failed" if file_asset_failed else "bind_failed"
                        display_status = "failed"
                        message = str((detail_row["file_asset_message"] if file_asset_failed else detail_row["target_message"]) or "")
                        completed_details += 1
                    elif target_asset_status == "running":
                        stage = "binding"
                        display_status = "running"
                        message = str(detail_row["target_message"] or "正在绑定计划。")
                    elif file_asset_status == "running":
                        stage = "uploading"
                        display_status = "running"
                        message = str(detail_row["file_asset_message"] or "正在上传素材。")
                    elif file_asset_status == "success":
                        stage = "bind_queued"
                        display_status = "queued"
                        message = "素材上传完成，等待绑定计划。"
                    elif file_asset_status == "failed" or file_status == "failed":
                        stage = "upload_failed"
                        display_status = "failed"
                        message = str(detail_row["file_asset_message"] or detail_row["file_message"] or "上传素材失败。")
                        completed_details += 1
                    elif status_text == "queued":
                        stage = "queued"
                        display_status = "queued"
                        message = "等待后台执行。"
                    else:
                        stage = "upload_queued"
                        display_status = "queued"
                        message = "等待上传素材。"
                    detail_item = {
                        "target_asset_id": target_asset_id,
                        "target_id": target_id,
                        "file_id": file_id,
                        "failure_stage": "upload" if file_asset_failed or stage == "upload_failed" else "bind",
                        "stage": stage,
                        "status": display_status,
                        "original_name": str(detail_row["original_name"] or ""),
                        "message": message,
                        "advertiser_id": advertiser_id,
                        "advertiser_name": str(detail_row["advertiser_name"] or ""),
                        "ad_id": int(detail_row["ad_id"] or 0),
                        "ad_name": str(detail_row["ad_name"] or ""),
                        "material_id": str(detail_row["material_id"] or ""),
                        "video_id": str(detail_row["video_id"] or ""),
                        "retryable": target_asset_status == "failed",
                    }
                    detail_items.append(detail_item)
                    if display_status == "failed":
                        failed_items.append(detail_item)
                total_details = len(detail_items)
                total_operations = len(upload_operation_keys) + total_details
                completed_operations = len(upload_completed_keys) + completed_details
                if total_operations > 0:
                    progress_percent = round(max(0, min(100, completed_operations * 100 / total_operations)))
                elif str(item.get("status") or "").strip().lower() in {"success", "ok"}:
                    progress_percent = 100
                else:
                    progress_percent = 0
                item["detail_items"] = detail_items
                item["detail_count"] = total_details
                item["completed_detail_count"] = completed_details
                item["success_detail_count"] = success_details
                item["failed_detail_count"] = len(failed_items)
                item["progress_percent"] = progress_percent
                if has_failures and not failed_items:
                    legacy_failures = conn.execute(
                        """
                        SELECT original_name, message, status
                        FROM material_upload_job_files
                        WHERE job_id = ? AND status IN ('failed', 'partial')
                        ORDER BY id ASC
                        LIMIT 5
                        """,
                        (job_id,),
                    ).fetchall()
                    failed_items = [
                        {
                            "target_asset_id": 0,
                            "target_id": 0,
                            "file_id": 0,
                            "failure_stage": "upload",
                            "stage": "upload_failed",
                            "original_name": str(failed_row["original_name"] or ""),
                            "message": str(failed_row["message"] or ""),
                            "status": str(failed_row["status"] or ""),
                            "advertiser_id": 0,
                            "advertiser_name": "",
                            "ad_id": 0,
                            "ad_name": "",
                            "retryable": False,
                        }
                        for failed_row in legacy_failures
                    ]
                    item["failed_detail_count"] = len(failed_items)
                item["failed_items"] = failed_items
                items.append(item)
        return items
