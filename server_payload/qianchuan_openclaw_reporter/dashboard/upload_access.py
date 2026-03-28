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
    ) -> None:
        self._db = db_factory
        self._now_text = now_text
        self._role_admin = role_admin
        self._allowed_advertiser_ids_for_user = allowed_advertiser_ids_for_user
        self._latest_snapshot = latest_snapshot
        self._current_customer_center_id = current_customer_center_id
        self._normalize_match_text = normalize_match_text
        self._sanitize_material_title = sanitize_material_title

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

    def visible_upload_targets(self, user: dict[str, Any], scope: str, query: str) -> dict[str, Any]:
        allowed = self._allowed_advertiser_ids_for_user(user)
        payload = self._latest_snapshot(allowed)
        if not payload:
            return {"scope": scope, "query": query, "accounts": [], "plans": [], "plan_count": 0, "account_count": 0}
        accounts = [dict(item) for item in payload.get("accounts", [])]
        plans = [
            dict(item)
            for item in payload.get("plans", [])
            if str(item.get("plan_source") or PLAN_SOURCE_UNI_PROMOTION).strip().upper() == PLAN_SOURCE_UNI_PROMOTION
        ]
        query_text = str(query or "").strip().casefold()
        account_map = {int(item.get("advertiser_id", 0) or 0): dict(item) for item in accounts}
        if scope == "account":
            matched_accounts = []
            for item in accounts:
                haystack = self._normalize_match_text(
                    str(item.get("advertiser_name") or ""),
                    str(item.get("advertiser_id") or ""),
                )
                if not query_text or query_text in haystack:
                    matched_accounts.append(dict(item))
            account_ids = {int(item.get("advertiser_id", 0) or 0) for item in matched_accounts}
            target_plans = [dict(item) for item in plans if int(item.get("advertiser_id", 0) or 0) in account_ids]
        else:
            target_plans = []
            for item in plans:
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
        for item in target_plans:
            normalized_plans.append(
                {
                    "advertiser_id": int(item.get("advertiser_id", 0) or 0),
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
                    "status_text": str(item.get("status_text") or ""),
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
                "plan_count": sum(
                    1
                    for plan in normalized_plans
                    if int(plan["advertiser_id"]) == int(item.get("advertiser_id", 0) or 0)
                ),
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
        return {
            "scope": scope,
            "query": str(query or "").strip(),
            "snapshot_time": str(payload.get("snapshot_time") or ""),
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
            raw_json_select = "p.raw_json"
            if not self._column_exists_locked(conn, "plan_snapshots", "raw_json"):
                raw_json_select = "'{}' AS raw_json"
            rows = conn.execute(
                f"""
                SELECT p.ad_id, p.advertiser_id, p.advertiser_name, p.ad_name, p.product_id, p.product_name, p.anchor_name,
                       p.marketing_goal, p.plan_source, p.status, p.opt_status, p.snapshot_time, {raw_json_select}
                FROM plan_snapshots p
                JOIN (
                    SELECT ad_id, MAX(snapshot_time) AS latest_snapshot_time
                    FROM plan_snapshots
                    WHERE ad_id IN ({placeholders})
                      AND customer_center_id = ?
                      AND COALESCE(plan_source, 'UNI_PROMOTION') = 'UNI_PROMOTION'
                    GROUP BY ad_id
                ) latest
                  ON latest.ad_id = p.ad_id
                 AND latest.latest_snapshot_time = p.snapshot_time
                WHERE COALESCE(p.plan_source, 'UNI_PROMOTION') = 'UNI_PROMOTION'
                  AND p.customer_center_id = ?
                """,
                [*normalized_ids, customer_center_id, customer_center_id],
            ).fetchall()
            context_map = {int(row["ad_id"]): dict(row) for row in rows}
            if context_map and self._column_exists_locked(conn, "plan_detail_snapshots", "raw_json"):
                detail_rows = conn.execute(
                    f"""
                    SELECT d.ad_id, d.raw_json
                    FROM plan_detail_snapshots d
                    JOIN (
                        SELECT ad_id, MAX(snapshot_time) AS latest_snapshot_time
                        FROM plan_detail_snapshots
                        WHERE ad_id IN ({placeholders})
                          AND customer_center_id = ?
                        GROUP BY ad_id
                    ) latest
                      ON latest.ad_id = d.ad_id
                     AND latest.latest_snapshot_time = d.snapshot_time
                    WHERE d.customer_center_id = ?
                    """,
                    [*normalized_ids, customer_center_id, customer_center_id],
                ).fetchall()
                for row in detail_rows:
                    ad_id = int(row["ad_id"])
                    if ad_id not in context_map:
                        continue
                    detail_raw_json = str(row["raw_json"] or "").strip()
                    if detail_raw_json:
                        context_map[ad_id]["raw_json"] = detail_raw_json
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
                upload_failures = conn.execute(
                    """
                    SELECT
                        fa.status,
                        fa.message,
                        f.original_name,
                        fa.advertiser_id,
                        fa.advertiser_name
                    FROM material_upload_job_file_assets fa
                    JOIN material_upload_job_files f ON f.id = fa.file_id
                    WHERE fa.job_id = ? AND fa.status = 'failed'
                    ORDER BY fa.id ASC
                    LIMIT 5
                    """,
                    (job_id,),
                ).fetchall()
                bind_failures = conn.execute(
                    """
                    SELECT
                        ta.status,
                        ta.message,
                        f.original_name,
                        t.advertiser_id,
                        t.advertiser_name,
                        t.ad_id,
                        t.ad_name
                    FROM material_upload_job_target_assets ta
                    JOIN material_upload_job_targets t ON t.id = ta.target_id
                    JOIN material_upload_job_files f ON f.id = ta.file_id
                    LEFT JOIN material_upload_job_file_assets fa
                        ON fa.job_id = ta.job_id
                       AND fa.file_id = ta.file_id
                       AND fa.advertiser_id = t.advertiser_id
                    WHERE ta.job_id = ?
                      AND ta.status = 'failed'
                      AND COALESCE(fa.status, '') != 'failed'
                    ORDER BY ta.id ASC
                    LIMIT 5
                    """,
                    (job_id,),
                ).fetchall()
                item = dict(row)
                item["created_by_label"] = str(item.get("display_name") or item.get("username") or "")
                failed_items = [
                    {
                        "failure_stage": "upload",
                        "original_name": str(failed_row["original_name"] or ""),
                        "message": str(failed_row["message"] or ""),
                        "status": str(failed_row["status"] or ""),
                        "advertiser_id": int(failed_row["advertiser_id"] or 0),
                        "advertiser_name": str(failed_row["advertiser_name"] or ""),
                        "ad_id": 0,
                        "ad_name": "",
                    }
                    for failed_row in upload_failures
                ]
                failed_items.extend(
                    {
                        "failure_stage": "bind",
                        "original_name": str(failed_row["original_name"] or ""),
                        "message": str(failed_row["message"] or ""),
                        "status": str(failed_row["status"] or ""),
                        "advertiser_id": int(failed_row["advertiser_id"] or 0),
                        "advertiser_name": str(failed_row["advertiser_name"] or ""),
                        "ad_id": int(failed_row["ad_id"] or 0),
                        "ad_name": str(failed_row["ad_name"] or ""),
                    }
                    for failed_row in bind_failures
                )
                if not failed_items:
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
                            "failure_stage": "upload",
                            "original_name": str(failed_row["original_name"] or ""),
                            "message": str(failed_row["message"] or ""),
                            "status": str(failed_row["status"] or ""),
                            "advertiser_id": 0,
                            "advertiser_name": "",
                            "ad_id": 0,
                            "ad_name": "",
                        }
                        for failed_row in legacy_failures
                    ]
                item["failed_items"] = failed_items
                items.append(item)
        return items
