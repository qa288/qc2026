from __future__ import annotations

from typing import Any, Callable


class SnapshotAccess:
    def __init__(
        self,
        db_factory: Callable[[], Any],
        latest_summary_meta: Callable[[Any], Any],
        latest_extended_sync_run: Callable[[Any], Any],
        current_customer_center_id: Callable[[], str],
        decorate_plan_item: Callable[[Any], dict[str, Any]],
        marketing_goal_label: Callable[[str], str],
        format_plan_status_text: Callable[[str, str], str],
    ) -> None:
        self._db = db_factory
        self._latest_summary_meta = latest_summary_meta
        self._latest_extended_sync_run = latest_extended_sync_run
        self._current_customer_center_id = current_customer_center_id
        self._decorate_plan_item = decorate_plan_item
        self._marketing_goal_label = marketing_goal_label
        self._format_plan_status_text = format_plan_status_text

    def latest_extended_sync(self) -> dict[str, Any] | None:
        with self._db() as conn:
            row = self._latest_extended_sync_run(conn)
        return dict(row) if row else None

    def plan_assets(
        self,
        ad_id: int,
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        with self._db() as conn:
            target_snapshot = str(snapshot_time or "").strip()
            if not target_snapshot:
                latest = self._latest_summary_meta(conn)
                if not latest:
                    return {"snapshot_time": "", "plan": None, "detail": None, "products": [], "materials": []}
                target_snapshot = str(latest["snapshot_time"])

            plan_row = conn.execute(
                """
                SELECT *
                FROM plan_snapshots
                WHERE snapshot_time = ? AND customer_center_id = ? AND ad_id = ?
                LIMIT 1
                """,
                (target_snapshot, customer_center_id, ad_id),
            ).fetchone()
            detail_row = conn.execute(
                """
                SELECT *
                FROM plan_detail_snapshots
                WHERE snapshot_time = ? AND customer_center_id = ? AND ad_id = ?
                LIMIT 1
                """,
                (target_snapshot, customer_center_id, ad_id),
            ).fetchone()
            products = conn.execute(
                """
                SELECT *
                FROM product_snapshots
                WHERE snapshot_time = ? AND customer_center_id = ? AND ad_id = ?
                ORDER BY order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, product_key ASC
                """,
                (target_snapshot, customer_center_id, ad_id),
            ).fetchall()
            materials = conn.execute(
                """
                SELECT *
                FROM material_snapshots
                WHERE snapshot_time = ? AND customer_center_id = ? AND ad_id = ?
                ORDER BY create_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, material_type ASC, material_key ASC
                """,
                (target_snapshot, customer_center_id, ad_id),
            ).fetchall()
            original_flags = {
                str(row["material_id"]): bool(row["is_original"])
                for row in conn.execute(
                    """
                    SELECT material_id, is_original
                    FROM video_origin_flags
                    WHERE snapshot_time = ? AND customer_center_id = ? AND advertiser_id = (
                        SELECT advertiser_id
                        FROM plan_snapshots
                        WHERE snapshot_time = ? AND customer_center_id = ? AND ad_id = ?
                        LIMIT 1
                    )
                    """,
                    (target_snapshot, customer_center_id, target_snapshot, customer_center_id, ad_id),
                ).fetchall()
            }

        if plan_row and allowed_advertiser_ids is not None:
            allowed = {int(item) for item in allowed_advertiser_ids}
            if int(plan_row["advertiser_id"] or 0) not in allowed:
                return {"snapshot_time": target_snapshot, "plan": None, "detail": None, "products": [], "materials": []}

        plan_payload = self._decorate_plan_item(plan_row) if plan_row else None
        detail_payload = dict(detail_row) if detail_row else None
        if detail_payload:
            detail_payload["marketing_goal_label"] = self._marketing_goal_label(detail_payload["marketing_goal"])
            detail_payload["status_text"] = self._format_plan_status_text(
                detail_payload["status"],
                detail_payload["opt_status"],
            )
        material_items: list[dict[str, Any]] = []
        for row in materials:
            item = dict(row)
            item["is_original"] = bool(original_flags.get(str(item["material_id"]), False))
            material_items.append(item)
        return {
            "snapshot_time": target_snapshot,
            "plan": plan_payload,
            "detail": detail_payload,
            "products": [dict(row) for row in products],
            "materials": material_items,
            "originalVideoCount": sum(1 for item in material_items if item["is_original"]),
        }

    def summary_history(self, limit: int = 144) -> list[dict[str, Any]]:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT snapshot_time, stat_cost, pay_amount, order_count, roi
                FROM summary_snapshots
                WHERE customer_center_id = ?
                ORDER BY snapshot_time DESC
                LIMIT ?
                """,
                (customer_center_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def account_history(
        self,
        advertiser_id: int,
        limit: int = 72,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        if allowed_advertiser_ids is not None and int(advertiser_id) not in {int(item) for item in allowed_advertiser_ids}:
            return []
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT snapshot_time, stat_cost, pay_amount, order_count, roi
                FROM account_snapshots
                WHERE customer_center_id = ? AND advertiser_id = ?
                ORDER BY snapshot_time DESC
                LIMIT ?
                """,
                (customer_center_id, advertiser_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def plan_history(
        self,
        ad_id: int,
        limit: int = 72,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        with self._db() as conn:
            if allowed_advertiser_ids is not None:
                latest = conn.execute(
                    """
                    SELECT advertiser_id
                    FROM plan_snapshots
                    WHERE customer_center_id = ? AND ad_id = ?
                    ORDER BY snapshot_time DESC
                    LIMIT 1
                    """,
                    (customer_center_id, ad_id),
                ).fetchone()
                if not latest or int(latest["advertiser_id"] or 0) not in {int(item) for item in allowed_advertiser_ids}:
                    return []
            rows = conn.execute(
                """
                SELECT snapshot_time, stat_cost, pay_amount, order_count, roi
                FROM plan_snapshots
                WHERE customer_center_id = ? AND ad_id = ?
                ORDER BY snapshot_time DESC
                LIMIT ?
                """,
                (customer_center_id, ad_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]
