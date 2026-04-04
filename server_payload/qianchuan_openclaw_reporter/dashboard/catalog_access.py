from __future__ import annotations

import json
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

    @staticmethod
    def _json_text_list(value: Any) -> list[str]:
        try:
            items = json.loads(str(value or "[]"))
        except Exception:
            return []
        return [str(item or "").strip() for item in items if str(item or "").strip()]

    @staticmethod
    def _json_int_list(value: Any) -> list[int]:
        try:
            items = json.loads(str(value or "[]"))
        except Exception:
            return []
        normalized: list[int] = []
        for item in items if isinstance(items, list) else []:
            try:
                value_int = int(item or 0)
            except Exception:
                value_int = 0
            if value_int > 0:
                normalized.append(value_int)
        return normalized

    def _customer_center_id(self) -> str:
        return str(self._current_customer_center_id() or "").strip()

    def reference_catalog(self) -> dict[str, Any]:
        customer_center_id = self._customer_center_id()
        with self._db() as conn:
            accounts = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT advertiser_id, advertiser_name
                    FROM account_current
                    WHERE customer_center_id = ?
                    ORDER BY advertiser_name ASC, advertiser_id ASC
                    """,
                    (customer_center_id,),
                ).fetchall()
            ]
            plans = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT advertiser_id, advertiser_name, ad_id, ad_name, product_id, product_name
                    FROM plan_current
                    WHERE customer_center_id = ?
                    ORDER BY ad_name ASC, ad_id ASC
                    """,
                    (customer_center_id,),
                ).fetchall()
            ]
            materials = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM material_current
                    WHERE customer_center_id = ?
                    ORDER BY material_name ASC, material_id ASC, material_key ASC
                    """,
                    (customer_center_id,),
                ).fetchall()
            ]
            summary_row = conn.execute(
                """
                SELECT snapshot_time
                FROM summary_current
                WHERE customer_center_id = ?
                LIMIT 1
                """,
                (customer_center_id,),
            ).fetchone()
            material_row = conn.execute(
                """
                SELECT snapshot_time
                FROM material_current
                WHERE customer_center_id = ?
                ORDER BY snapshot_time DESC
                LIMIT 1
                """,
                (customer_center_id,),
            ).fetchone()

        deduped_accounts: dict[int, dict[str, Any]] = {}
        for row in accounts:
            advertiser_id = int(row.get("advertiser_id", 0) or 0)
            if advertiser_id <= 0 or advertiser_id in deduped_accounts:
                continue
            deduped_accounts[advertiser_id] = {
                "advertiser_id": advertiser_id,
                "advertiser_name": str(row.get("advertiser_name") or "").strip(),
            }

        deduped_plans: dict[int, dict[str, Any]] = {}
        product_rows: dict[str, dict[str, Any]] = {}
        for row in plans:
            ad_id = int(row.get("ad_id", 0) or 0)
            if ad_id <= 0 or ad_id in deduped_plans:
                continue
            normalized_row = {
                "advertiser_id": int(row.get("advertiser_id", 0) or 0),
                "advertiser_name": str(row.get("advertiser_name") or "").strip(),
                "ad_id": ad_id,
                "ad_name": str(row.get("ad_name") or "").strip(),
                "product_id": str(row.get("product_id") or "").strip(),
                "product_name": str(row.get("product_name") or "").strip(),
            }
            deduped_plans[ad_id] = normalized_row
            product_key = normalized_row["product_id"] or normalized_row["product_name"] or f"plan:{ad_id}"
            if product_key not in product_rows:
                product_rows[product_key] = {
                    "advertiser_id": normalized_row["advertiser_id"],
                    "advertiser_name": normalized_row["advertiser_name"],
                    "ad_id": normalized_row["ad_id"],
                    "ad_name": normalized_row["ad_name"],
                    "product_key": product_key,
                    "product_id": normalized_row["product_id"],
                    "product_name": normalized_row["product_name"],
                }

        material_items: list[dict[str, Any]] = []
        for row in materials:
            advertiser_ids = self._json_int_list(row.get("advertiser_ids_json"))
            plan_ids = self._json_int_list(row.get("plan_ids_json"))
            material_items.append(
                {
                    "advertiser_id": advertiser_ids[0] if advertiser_ids else 0,
                    "advertiser_name": str(row.get("top_account_name") or "").strip(),
                    "ad_id": plan_ids[0] if plan_ids else 0,
                    "ad_name": str(row.get("top_plan_name") or "").strip(),
                    "material_key": str(row.get("material_key") or "").strip(),
                    "material_id": str(row.get("material_id") or "").strip(),
                    "material_name": str(row.get("material_name") or "").strip(),
                    "video_id": str(row.get("video_id") or "").strip(),
                    "material_type": str(row.get("material_type") or "").strip(),
                }
            )

        return {
            "summary_snapshot_time": str(summary_row["snapshot_time"]) if summary_row else "",
            "detail_snapshot_time": str(material_row["snapshot_time"]) if material_row else "",
            "accounts": sorted(
                deduped_accounts.values(),
                key=lambda item: (str(item.get("advertiser_name") or ""), int(item.get("advertiser_id", 0) or 0)),
            ),
            "plans": sorted(
                deduped_plans.values(),
                key=lambda item: (str(item.get("ad_name") or ""), int(item.get("ad_id", 0) or 0)),
            ),
            "products": sorted(
                product_rows.values(),
                key=lambda item: (
                    str(item.get("product_name") or ""),
                    str(item.get("product_id") or ""),
                    str(item.get("product_key") or ""),
                ),
            ),
            "materials": material_items,
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
            raise ValueError("鍏抽敭璇嶄笉鑳戒负绌恒€?")
        if scope_value not in self._allowed_scopes:
            raise ValueError("scope 蹇呴』鏄?all/account/plan/product/material 涔嬩竴銆?")
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
                if allowed_row(row) and matcher in self._normalize_match_text(row.get("advertiser_name"), row.get("advertiser_id")):
                    sections["accounts"].append(row)
        if scope_value in {"all", "plan"}:
            for row in catalog["plans"]:
                if allowed_row(row) and matcher in self._normalize_match_text(row.get("ad_name"), row.get("ad_id"), row.get("advertiser_name")):
                    sections["plans"].append(row)
        if scope_value in {"all", "product"}:
            for row in catalog["products"]:
                if allowed_row(row) and matcher in self._normalize_match_text(
                    row.get("product_name"),
                    row.get("product_id"),
                    row.get("product_key"),
                    row.get("ad_name"),
                ):
                    sections["products"].append(row)
        if scope_value in {"all", "material"}:
            for row in catalog["materials"]:
                if allowed_row(row) and matcher in self._normalize_match_text(
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
