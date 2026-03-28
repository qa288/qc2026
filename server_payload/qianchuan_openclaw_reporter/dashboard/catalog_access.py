from __future__ import annotations

from typing import Any, Callable


class CatalogAccess:
    def __init__(
        self,
        db_factory: Callable[[], Any],
        latest_summary_meta: Callable[[Any], Any],
        latest_extended_sync_run: Callable[[Any], Any],
        current_customer_center_id: Callable[[], str],
        normalize_match_text: Callable[..., str],
        allowed_scopes: set[str],
    ) -> None:
        self._db = db_factory
        self._latest_summary_meta = latest_summary_meta
        self._latest_extended_sync_run = latest_extended_sync_run
        self._current_customer_center_id = current_customer_center_id
        self._normalize_match_text = normalize_match_text
        self._allowed_scopes = set(allowed_scopes)

    def reference_catalog(self) -> dict[str, Any]:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        with self._db() as conn:
            latest_summary = self._latest_summary_meta(conn)
            latest_extended = self._latest_extended_sync_run(conn)
            accounts: list[dict[str, Any]] = []
            plans: list[dict[str, Any]] = []
            products: list[dict[str, Any]] = []
            materials: list[dict[str, Any]] = []
            if latest_summary:
                snapshot_time = str(latest_summary["snapshot_time"])
                accounts = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT advertiser_id, advertiser_name
                        FROM account_snapshots
                        WHERE snapshot_time = ?
                          AND customer_center_id = ?
                        ORDER BY advertiser_name ASC, advertiser_id ASC
                        """,
                        (snapshot_time, customer_center_id),
                    ).fetchall()
                ]
                plans = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT advertiser_id, advertiser_name, ad_id, ad_name, product_id, product_name
                        FROM plan_snapshots
                        WHERE snapshot_time = ?
                          AND customer_center_id = ?
                        ORDER BY ad_name ASC, ad_id ASC
                        """,
                        (snapshot_time, customer_center_id),
                    ).fetchall()
                ]
            if latest_extended:
                extended_snapshot = str(latest_extended["snapshot_time"])
                products = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT advertiser_id, advertiser_name, ad_id, ad_name, product_key, product_id, product_name
                        FROM product_snapshots
                        WHERE snapshot_time = ?
                          AND customer_center_id = ?
                        ORDER BY product_name ASC, product_id ASC, product_key ASC
                        """,
                        (extended_snapshot, customer_center_id),
                    ).fetchall()
                ]
                materials = [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT advertiser_id, advertiser_name, ad_id, ad_name, material_key, material_id, material_name, video_id, material_type
                        FROM material_snapshots
                        WHERE snapshot_time = ?
                          AND customer_center_id = ?
                        ORDER BY material_name ASC, material_id ASC, material_key ASC
                        """,
                        (extended_snapshot, customer_center_id),
                    ).fetchall()
                ]
        return {
            "summary_snapshot_time": str(latest_summary["snapshot_time"]) if latest_summary else "",
            "detail_snapshot_time": str(latest_extended["snapshot_time"]) if latest_extended else "",
            "accounts": accounts,
            "plans": plans,
            "products": products,
            "materials": materials,
        }

    def preview_keyword_matches(
        self,
        keyword: str,
        scope: str = "all",
        allowed_advertiser_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        needle = str(keyword or "").strip()
        scope_value = str(scope or "all").strip().lower()
        if not needle:
            raise ValueError("关键词不能为空。")
        if scope_value not in self._allowed_scopes:
            raise ValueError("scope 必须是 all/account/plan/product/material 之一。")
        catalog = self.reference_catalog()
        allowed = None if allowed_advertiser_ids is None else {int(item) for item in allowed_advertiser_ids}
        matcher = needle.casefold()

        def allowed_row(row: dict[str, Any]) -> bool:
            if allowed is None:
                return True
            advertiser_id = int(row.get("advertiser_id", 0) or 0)
            return advertiser_id in allowed

        sections: dict[str, list[dict[str, Any]]] = {"accounts": [], "plans": [], "products": [], "materials": []}
        if scope_value in {"all", "account"}:
            for row in catalog["accounts"]:
                if not allowed_row(row):
                    continue
                if matcher in self._normalize_match_text(row.get("advertiser_name"), row.get("advertiser_id")):
                    sections["accounts"].append(row)
        if scope_value in {"all", "plan"}:
            for row in catalog["plans"]:
                if not allowed_row(row):
                    continue
                if matcher in self._normalize_match_text(row.get("ad_name"), row.get("ad_id"), row.get("advertiser_name")):
                    sections["plans"].append(row)
        if scope_value in {"all", "product"}:
            for row in catalog["products"]:
                if not allowed_row(row):
                    continue
                if matcher in self._normalize_match_text(
                    row.get("product_name"),
                    row.get("product_id"),
                    row.get("product_key"),
                    row.get("ad_name"),
                ):
                    sections["products"].append(row)
        if scope_value in {"all", "material"}:
            for row in catalog["materials"]:
                if not allowed_row(row):
                    continue
                if matcher in self._normalize_match_text(
                    row.get("material_name"),
                    row.get("material_id"),
                    row.get("material_key"),
                    row.get("video_id"),
                    row.get("ad_name"),
                ):
                    sections["materials"].append(row)
        return {
            "keyword": needle,
            "scope": scope_value,
            "summary_snapshot_time": catalog["summary_snapshot_time"],
            "detail_snapshot_time": catalog["detail_snapshot_time"],
            "counts": {key: len(value) for key, value in sections.items()},
            "items": sections,
        }
