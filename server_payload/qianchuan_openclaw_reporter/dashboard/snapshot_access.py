from __future__ import annotations

import json
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

    @staticmethod
    def _json_int_list(value: Any) -> list[int]:
        try:
            items = json.loads(str(value or "[]"))
        except Exception:
            return []
        result: list[int] = []
        for item in items if isinstance(items, list) else []:
            try:
                normalized = int(item or 0)
            except Exception:
                normalized = 0
            if normalized > 0:
                result.append(normalized)
        return result

    @staticmethod
    def _json_text_list(value: Any) -> list[str]:
        try:
            items = json.loads(str(value or "[]"))
        except Exception:
            return []
        result: list[str] = []
        for item in items if isinstance(items, list) else []:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result

    def _customer_center_id(self) -> str:
        return str(self._current_customer_center_id() or "").strip()

    def _latest_material_rows(self, conn: Any, customer_center_id: str) -> list[dict[str, Any]]:
        current_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM material_current
                WHERE customer_center_id = ?
                ORDER BY snapshot_time DESC, stat_cost DESC, material_key ASC
                """,
                (customer_center_id,),
            ).fetchall()
        ]
        if current_rows:
            return current_rows
        latest_daily = conn.execute(
            """
            SELECT biz_date
            FROM material_daily
            WHERE customer_center_id = ?
            ORDER BY biz_date DESC, snapshot_time DESC
            LIMIT 1
            """,
            (customer_center_id,),
        ).fetchone()
        if not latest_daily:
            return []
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM material_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                ORDER BY stat_cost DESC, material_key ASC
                """,
                (customer_center_id, str(latest_daily["biz_date"] or "")),
            ).fetchall()
        ]

    def latest_extended_sync(self) -> dict[str, Any] | None:
        customer_center_id = self._customer_center_id()
        with self._db() as conn:
            rows = self._latest_material_rows(conn, customer_center_id)
        if not rows:
            return None
        snapshot_time = max(str(row.get("snapshot_time") or "") for row in rows)
        plan_ids: set[int] = set()
        products: set[str] = set()
        original_video_count = 0
        for row in rows:
            plan_ids.update(self._json_int_list(row.get("plan_ids_json")))
            product_names = self._json_text_list(row.get("product_names_json"))
            if product_names:
                products.update(product_names)
            else:
                fallback_product = str(row.get("product_info_text") or "").strip()
                if fallback_product:
                    products.add(fallback_product)
            if bool(row.get("is_original")):
                original_video_count += 1
        material_row_count = len(rows)
        return {
            "snapshot_time": snapshot_time,
            "status": "ok",
            "plan_count": len(plan_ids),
            "detail_count": material_row_count,
            "product_row_count": len(products),
            "material_row_count": material_row_count,
            "original_video_row_count": original_video_count,
            "error_count": 0,
        }

    def _plan_row(self, conn: Any, customer_center_id: str, ad_id: int, snapshot_time: str) -> tuple[dict[str, Any] | None, bool]:
        target_snapshot = str(snapshot_time or "").strip()
        if target_snapshot:
            current_row = conn.execute(
                """
                SELECT *
                FROM plan_current
                WHERE customer_center_id = ? AND ad_id = ? AND snapshot_time = ?
                LIMIT 1
                """,
                (customer_center_id, ad_id, target_snapshot),
            ).fetchone()
            if current_row:
                return dict(current_row), False
            daily_row = conn.execute(
                """
                SELECT *
                FROM plan_daily
                WHERE customer_center_id = ? AND ad_id = ? AND biz_date = ?
                ORDER BY snapshot_time DESC
                LIMIT 1
                """,
                (customer_center_id, ad_id, target_snapshot[:10]),
            ).fetchone()
            return (dict(daily_row), True) if daily_row else (None, True)

        current_row = conn.execute(
            """
            SELECT *
            FROM plan_current
            WHERE customer_center_id = ? AND ad_id = ?
            LIMIT 1
            """,
            (customer_center_id, ad_id),
        ).fetchone()
        if current_row:
            return dict(current_row), False
        daily_row = conn.execute(
            """
            SELECT *
            FROM plan_daily
            WHERE customer_center_id = ? AND ad_id = ?
            ORDER BY biz_date DESC, snapshot_time DESC
            LIMIT 1
            """,
            (customer_center_id, ad_id),
        ).fetchone()
        return (dict(daily_row), True) if daily_row else (None, True)

    def _material_rows_for_plan(
        self,
        conn: Any,
        customer_center_id: str,
        ad_id: int,
        plan_name: str,
        *,
        use_daily: bool,
        snapshot_time: str,
    ) -> list[dict[str, Any]]:
        target_snapshot = str(snapshot_time or "").strip()
        if use_daily:
            if target_snapshot:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM material_daily
                    WHERE customer_center_id = ?
                      AND biz_date = ?
                    ORDER BY create_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, material_key ASC
                    """,
                    (customer_center_id, target_snapshot[:10]),
                ).fetchall()
            else:
                latest_daily = conn.execute(
                    """
                    SELECT biz_date
                    FROM material_daily
                    WHERE customer_center_id = ?
                    ORDER BY biz_date DESC, snapshot_time DESC
                    LIMIT 1
                    """,
                    (customer_center_id,),
                ).fetchone()
                if not latest_daily:
                    return []
                rows = conn.execute(
                    """
                    SELECT *
                    FROM material_daily
                    WHERE customer_center_id = ?
                      AND biz_date = ?
                    ORDER BY create_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, material_key ASC
                    """,
                    (customer_center_id, str(latest_daily["biz_date"] or "")),
                ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM material_current
                WHERE customer_center_id = ?
                ORDER BY create_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, material_key ASC
                """,
                (customer_center_id,),
            ).fetchall()

        plan_name_text = str(plan_name or "").strip()
        items: list[dict[str, Any]] = []
        for raw_row in rows:
            row = dict(raw_row)
            plan_ids = self._json_int_list(row.get("plan_ids_json"))
            if ad_id in plan_ids:
                items.append(row)
                continue
            if plan_name_text and str(row.get("top_plan_name") or "").strip() == plan_name_text:
                items.append(row)
        return items

    def plan_assets(
        self,
        ad_id: int,
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        customer_center_id = self._customer_center_id()
        with self._db() as conn:
            plan_row, use_daily = self._plan_row(conn, customer_center_id, int(ad_id or 0), snapshot_time)
            if not plan_row:
                return {"snapshot_time": str(snapshot_time or "").strip(), "plan": None, "detail": None, "products": [], "materials": []}
            if allowed_advertiser_ids is not None:
                allowed = {int(item) for item in allowed_advertiser_ids}
                if int(plan_row.get("advertiser_id", 0) or 0) not in allowed:
                    return {"snapshot_time": str(plan_row.get("snapshot_time") or ""), "plan": None, "detail": None, "products": [], "materials": []}

            material_rows = self._material_rows_for_plan(
                conn,
                customer_center_id,
                int(ad_id or 0),
                str(plan_row.get("ad_name") or ""),
                use_daily=use_daily,
                snapshot_time=str(plan_row.get("snapshot_time") or snapshot_time or ""),
            )

        plan_payload = self._decorate_plan_item(plan_row)
        detail_payload = dict(plan_row)
        detail_payload["marketing_goal_label"] = self._marketing_goal_label(str(detail_payload.get("marketing_goal") or ""))
        detail_payload["status_text"] = self._format_plan_status_text(
            str(detail_payload.get("status") or ""),
            str(detail_payload.get("opt_status") or ""),
        )

        materials = [dict(row) for row in material_rows]
        product_groups: dict[str, dict[str, Any]] = {}
        default_product_id = str(plan_row.get("product_id") or "").strip()
        default_product_name = str(plan_row.get("product_name") or "").strip()
        for row in materials:
            product_names = self._json_text_list(row.get("product_names_json"))
            if not product_names:
                fallback_name = str(row.get("product_info_text") or "").strip() or default_product_name
                product_names = [fallback_name] if fallback_name else []
            for product_name in product_names:
                product_key = product_name or default_product_id or "unlinked"
                bucket = product_groups.setdefault(
                    product_key,
                    {
                        "advertiser_id": int(plan_row.get("advertiser_id", 0) or 0),
                        "advertiser_name": str(plan_row.get("advertiser_name") or ""),
                        "ad_id": int(plan_row.get("ad_id", 0) or 0),
                        "ad_name": str(plan_row.get("ad_name") or ""),
                        "product_key": product_key,
                        "product_id": default_product_id,
                        "product_name": product_name,
                        "stat_cost": 0.0,
                        "pay_amount": 0.0,
                        "order_count": 0,
                        "roi": 0.0,
                    },
                )
                bucket["stat_cost"] = round(float(bucket.get("stat_cost", 0.0) or 0.0) + float(row.get("stat_cost", 0.0) or 0.0), 2)
                bucket["pay_amount"] = round(float(bucket.get("pay_amount", 0.0) or 0.0) + float(row.get("pay_amount", 0.0) or 0.0), 2)
                bucket["order_count"] = int(bucket.get("order_count", 0) or 0) + int(float(row.get("order_count", 0.0) or 0.0))

        if not product_groups and (default_product_id or default_product_name):
            product_key = default_product_id or default_product_name
            product_groups[product_key] = {
                "advertiser_id": int(plan_row.get("advertiser_id", 0) or 0),
                "advertiser_name": str(plan_row.get("advertiser_name") or ""),
                "ad_id": int(plan_row.get("ad_id", 0) or 0),
                "ad_name": str(plan_row.get("ad_name") or ""),
                "product_key": product_key,
                "product_id": default_product_id,
                "product_name": default_product_name,
                "stat_cost": 0.0,
                "pay_amount": 0.0,
                "order_count": 0,
                "roi": 0.0,
            }

        products: list[dict[str, Any]] = []
        for item in product_groups.values():
            stat_cost = round(float(item.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(item.get("pay_amount", 0.0) or 0.0), 2)
            item["roi"] = round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0
            products.append(item)
        products.sort(
            key=lambda item: (
                -int(item.get("order_count", 0) or 0),
                -float(item.get("pay_amount", 0.0) or 0.0),
                -float(item.get("stat_cost", 0.0) or 0.0),
                str(item.get("product_name") or ""),
            )
        )

        return {
            "snapshot_time": str(plan_row.get("snapshot_time") or snapshot_time or ""),
            "plan": plan_payload,
            "detail": detail_payload,
            "products": products,
            "materials": materials,
            "originalVideoCount": sum(1 for item in materials if bool(item.get("is_original"))),
        }

    def summary_history(self, limit: int = 144) -> list[dict[str, Any]]:
        customer_center_id = self._customer_center_id()
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT snapshot_time, stat_cost, pay_amount, order_count, roi
                FROM summary_daily
                WHERE customer_center_id = ?
                ORDER BY biz_date DESC, snapshot_time DESC
                LIMIT ?
                """,
                (customer_center_id, limit),
            ).fetchall()
            current_row = conn.execute(
                """
                SELECT snapshot_time, stat_cost, pay_amount, order_count, roi
                FROM summary_current
                WHERE customer_center_id = ?
                LIMIT 1
                """,
                (customer_center_id,),
            ).fetchone()
        items = [dict(row) for row in reversed(rows)]
        if current_row:
            items.append(dict(current_row))
        return items[-max(int(limit or 0), 0) :] if limit > 0 else items

    def account_history(
        self,
        advertiser_id: int,
        limit: int = 72,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        normalized_advertiser_id = int(advertiser_id or 0)
        if allowed_advertiser_ids is not None and normalized_advertiser_id not in {int(item) for item in allowed_advertiser_ids}:
            return []
        customer_center_id = self._customer_center_id()
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT snapshot_time, stat_cost, pay_amount, order_count, roi
                FROM account_daily
                WHERE customer_center_id = ? AND advertiser_id = ?
                ORDER BY biz_date DESC, snapshot_time DESC
                LIMIT ?
                """,
                (customer_center_id, normalized_advertiser_id, limit),
            ).fetchall()
            current_row = conn.execute(
                """
                SELECT snapshot_time, stat_cost, pay_amount, order_count, roi
                FROM account_current
                WHERE customer_center_id = ? AND advertiser_id = ?
                LIMIT 1
                """,
                (customer_center_id, normalized_advertiser_id),
            ).fetchone()
        items = [dict(row) for row in reversed(rows)]
        if current_row:
            items.append(dict(current_row))
        return items[-max(int(limit or 0), 0) :] if limit > 0 else items

    def plan_history(
        self,
        ad_id: int,
        limit: int = 72,
        allowed_advertiser_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        customer_center_id = self._customer_center_id()
        normalized_ad_id = int(ad_id or 0)
        with self._db() as conn:
            if allowed_advertiser_ids is not None:
                current_row = conn.execute(
                    """
                    SELECT advertiser_id
                    FROM plan_current
                    WHERE customer_center_id = ? AND ad_id = ?
                    LIMIT 1
                    """,
                    (customer_center_id, normalized_ad_id),
                ).fetchone()
                if not current_row:
                    current_row = conn.execute(
                        """
                        SELECT advertiser_id
                        FROM plan_daily
                        WHERE customer_center_id = ? AND ad_id = ?
                        ORDER BY biz_date DESC, snapshot_time DESC
                        LIMIT 1
                        """,
                        (customer_center_id, normalized_ad_id),
                    ).fetchone()
                if not current_row or int(current_row["advertiser_id"] or 0) not in {int(item) for item in allowed_advertiser_ids}:
                    return []

            rows = conn.execute(
                """
                SELECT snapshot_time, stat_cost, pay_amount, order_count, roi
                FROM plan_daily
                WHERE customer_center_id = ? AND ad_id = ?
                ORDER BY biz_date DESC, snapshot_time DESC
                LIMIT ?
                """,
                (customer_center_id, normalized_ad_id, limit),
            ).fetchall()
            current_plan = conn.execute(
                """
                SELECT snapshot_time, stat_cost, pay_amount, order_count, roi
                FROM plan_current
                WHERE customer_center_id = ? AND ad_id = ?
                LIMIT 1
                """,
                (customer_center_id, normalized_ad_id),
            ).fetchone()
        items = [dict(row) for row in reversed(rows)]
        if current_plan:
            items.append(dict(current_plan))
        return items[-max(int(limit or 0), 0) :] if limit > 0 else items
