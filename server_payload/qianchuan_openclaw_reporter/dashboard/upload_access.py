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

    @staticmethod
    def _customer_facing_upload_job_note(status_text: str, note: Any) -> str:
        normalized_status = str(status_text or "").strip().lower()
        raw_note = str(note or "").strip()
        lowered_note = raw_note.lower()
        if normalized_status == "receiving":
            return "视频上传中。"
        if normalized_status == "queued":
            return "等待后台处理。"
        if normalized_status == "running":
            if "绑定" in raw_note or "bind" in lowered_note:
                return "计划绑定中。"
            if "素材库" in raw_note or "上传素材" in raw_note or "upload" in lowered_note:
                return "素材上传中。"
            return "处理中。"
        return raw_note

    @staticmethod
    def _customer_facing_upload_detail_message(stage: str, display_status: str, message: Any) -> str:
        normalized_stage = str(stage or "").strip().lower()
        normalized_status = str(display_status or "").strip().lower()
        raw_message = str(message or "").strip()
        if normalized_status == "running":
            if normalized_stage == "binding":
                return "计划绑定中。"
            if normalized_stage in {"uploading", "upload_queued"}:
                return "素材上传中。"
            return "处理中。"
        if normalized_status == "queued":
            if normalized_stage == "bind_queued":
                return "等待计划绑定。"
            if normalized_stage == "queued":
                return "等待后台处理。"
            return "等待素材上传。"
        return raw_message

    @staticmethod
    def _is_material_upload_limit_error_text(message: Any) -> bool:
        normalized = str(message or "").strip()
        if not normalized:
            return False
        lowered = normalized.lower()
        return (
            "添加素材数量超过上限" in normalized
            or "素材数量超过上限" in normalized
            or "计划素材数量已达上限" in normalized
            or "material count exceeds limit" in lowered
            or "material number exceeds limit" in lowered
        )

    @staticmethod
    def _is_material_upload_video_param_error_text(message: Any) -> bool:
        normalized = str(message or "").strip()
        if not normalized:
            return False
        lowered = normalized.lower()
        return "视频参数错误" in normalized or "video parameter" in lowered or "video param" in lowered

    @staticmethod
    def _is_material_upload_payload_too_large_error_text(message: Any) -> bool:
        normalized = str(message or "").strip()
        if not normalized:
            return False
        lowered = normalized.lower()
        return (
            "http 413" in lowered
            or "request entity too large" in lowered
            or "payload too large" in lowered
            or "capacity limit" in lowered
        )

    @staticmethod
    def _is_material_upload_format_error_text(message: Any) -> bool:
        normalized = str(message or "").strip()
        if not normalized:
            return False
        lowered = normalized.lower()
        if UploadAccess._is_material_upload_payload_too_large_error_text(normalized):
            return False
        return (
            "视频格式校验失败" in normalized
            or "视频元数据预检失败" in normalized
            or "视频尺寸错误" in normalized
            or "视频参数错误" in normalized
            or "video format" in lowered
            or "video size" in lowered
            or "video dimension" in lowered
            or "video parameter" in lowered
            or "invalid video" in lowered
        )

    @staticmethod
    def _is_material_upload_shop_scope_permission_lost_error_text(message: Any) -> bool:
        normalized = str(message or "").strip()
        if not normalized:
            return False
        lowered = normalized.lower()
        return (
            "当前账户已失去该抖音号下对应店铺的商品全域投放权限" in normalized
            or "商品全域投放权限，请重新获取权限后重试" in normalized
            or ("permission" in lowered and "shop" in lowered and "scope" in lowered)
        )

    @classmethod
    def _customer_facing_upload_failure_message(
        cls,
        *,
        target_has_limit_failure: bool,
        message: Any,
    ) -> str:
        raw_message = str(message or "").strip()
        if cls._is_material_upload_shop_scope_permission_lost_error_text(raw_message):
            return "当前账户已失去该抖音号下对应店铺的商品全域投放权限，请重新获取权限后重试。"
        if cls._is_material_upload_payload_too_large_error_text(raw_message):
            return "官方上传网关返回 HTTP 413，本次上传被网关拒绝；可手动重试，若多次失败再压缩视频。"
        if target_has_limit_failure and (
            cls._is_material_upload_limit_error_text(raw_message)
            or cls._is_material_upload_video_param_error_text(raw_message)
        ):
            return "计划素材数量已达上限，请清理后重试。"
        if cls._is_material_upload_limit_error_text(raw_message):
            return "计划素材数量已达上限，请清理后重试。"
        if cls._is_material_upload_video_param_error_text(raw_message):
            return "视频参数错误，系统已自动重试一次，请稍后重试。"
        return raw_message

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
                if int(item.get("advertiser_id", 0) or 0) in account_ids
            ]
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
                    "status": str(item.get("status") or "").strip(),
                    "opt_status": str(item.get("opt_status") or "").strip(),
                    "status_code_text": " / ".join(
                        part
                        for part in (
                            str(item.get("status") or "").strip(),
                            str(item.get("opt_status") or "").strip(),
                        )
                        if part
                    ),
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

    def attach_material_upload_task(
        self,
        job_id: int,
        task_id: str,
        status_text: str = "queued",
        note: str = "",
    ) -> None:
        with self._db() as conn:
            existing = conn.execute(
                """
                SELECT status, note
                FROM material_upload_jobs
                WHERE id = ?
                LIMIT 1
                """,
                (int(job_id),),
            ).fetchone()
            current_status = str((existing or {}).get("status") or "").strip().lower()
            next_status = str(status_text or "").strip().lower() or "queued"
            if current_status in {"receiving", "running"}:
                next_status = current_status
            next_note = str(note or "").strip()
            if not next_note:
                if next_status == "receiving":
                    next_note = "后台正在处理已上传的视频，等待更多视频上传。"
                elif next_status == "running":
                    next_note = str((existing or {}).get("note") or "").strip() or "上传任务正在执行。"
                else:
                    next_note = "上传任务已入队，等待执行。"
            self.update_material_upload_job(
                conn,
                int(job_id),
                task_id=str(task_id or ""),
                status=next_status,
                note=next_note,
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
                item["note"] = self._customer_facing_upload_job_note(status_text, item.get("note"))
                detail_counts = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS detail_count,
                        COALESCE(SUM(CASE WHEN status IN ('success', 'failed') THEN 1 ELSE 0 END), 0) AS completed_detail_count,
                        COALESCE(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END), 0) AS success_detail_count,
                        COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_detail_count
                    FROM material_upload_job_target_assets
                    WHERE job_id = ?
                    """,
                    (job_id,),
                ).fetchone()
                upload_counts = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS upload_operation_count,
                        COALESCE(SUM(CASE WHEN status IN ('success', 'failed', 'skipped') THEN 1 ELSE 0 END), 0) AS completed_upload_operation_count
                    FROM material_upload_job_file_assets
                    WHERE job_id = ?
                    """,
                    (job_id,),
                ).fetchone()
                total_details = int((detail_counts or {}).get("detail_count", 0) or 0)
                completed_details = int((detail_counts or {}).get("completed_detail_count", 0) or 0)
                success_details = int((detail_counts or {}).get("success_detail_count", 0) or 0)
                failed_details = int((detail_counts or {}).get("failed_detail_count", 0) or 0)
                upload_operation_count = int((upload_counts or {}).get("upload_operation_count", 0) or 0)
                upload_completed_count = int((upload_counts or {}).get("completed_upload_operation_count", 0) or 0)
                total_operations = upload_operation_count + total_details
                completed_operations = upload_completed_count + completed_details
                if total_operations > 0:
                    progress_percent = round(max(0, min(100, completed_operations * 100 / total_operations)))
                elif str(item.get("status") or "").strip().lower() in {"success", "ok"}:
                    progress_percent = 100
                else:
                    progress_percent = 0
                item["detail_items"] = []
                item["detail_count"] = total_details
                item["completed_detail_count"] = completed_details
                item["success_detail_count"] = success_details
                item["failed_detail_count"] = failed_details
                item["progress_percent"] = progress_percent
                item["failed_items"] = []
                item["details_lazy"] = True
                items.append(item)
        return items
