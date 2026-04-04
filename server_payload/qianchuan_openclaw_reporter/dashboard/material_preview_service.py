from __future__ import annotations

import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from report_qianchuan import PLAN_MATERIAL_TYPES

from dashboard.settings import settings


DISPLAY_SCOPE_CURRENT = "current"
ROLE_OPERATOR = "operator"
TIMEZONE = settings.timezone
MATERIAL_PREVIEW_SOURCE_CACHE_SECONDS = settings.material_preview_source_cache_seconds
MATERIAL_PREVIEW_CURVE_CACHE_SECONDS = settings.material_preview_curve_cache_seconds
MATERIAL_PREVIEW_REFRESH_CACHE_SECONDS = settings.material_preview_refresh_cache_seconds
PREVIEW_VIDEO_RESOLVE_CACHE_SECONDS = settings.preview_video_resolve_cache_seconds
MATERIAL_PREVIEW_REFRESH_LEADING_ITEM_LIMIT = 24


def _scope_cache_key_fragment(allowed_advertiser_ids: set[int] | None = None) -> str:
    if allowed_advertiser_ids is None:
        return "all"
    items = sorted(int(item) for item in allowed_advertiser_ids if int(item or 0))
    if not items:
        return "none"
    return ",".join(str(item) for item in items)


def build_material_preview_identity_key(row: dict[str, Any] | None) -> str:
    item = dict(row or {})
    return "|".join(
        [
            str(item.get("material_key") or "").strip(),
            str(item.get("material_id") or "").strip(),
            str(item.get("video_id") or "").strip(),
            str(item.get("aweme_item_id") or "").strip(),
            str(item.get("material_type") or "").strip().upper(),
        ]
    )


def build_material_preview_source_cache_key(
    row: dict[str, Any] | None,
    range_key: str,
    start_date: str,
    end_date: str,
    snapshot_time: str,
    allowed_advertiser_ids: set[int] | None,
    customer_center_id: str,
) -> str:
    identity_key = build_material_preview_identity_key(row)
    return "|".join(
        [
            "source",
            identity_key,
            str(range_key or "").strip().lower(),
            str(start_date or "").strip(),
            str(end_date or "").strip(),
            str(snapshot_time or "").strip(),
            str(customer_center_id or "").strip(),
            _scope_cache_key_fragment(allowed_advertiser_ids),
        ]
    )


def build_material_preview_curve_cache_key(
    material_key: str,
    range_key: str,
    start_date: str,
    end_date: str,
    snapshot_time: str,
    allowed_advertiser_ids: set[int] | None,
    customer_center_id: str,
) -> str:
    return "|".join(
        [
            "curve",
            str(material_key or "").strip(),
            str(range_key or "").strip().lower(),
            str(start_date or "").strip(),
            str(end_date or "").strip(),
            str(snapshot_time or "").strip(),
            str(customer_center_id or "").strip(),
            _scope_cache_key_fragment(allowed_advertiser_ids),
        ]
    )


class MaterialPreviewService:
    def __init__(self, host: Any) -> None:
        self.host = host

    def __getattr__(self, name: str) -> Any:
        return getattr(self.host, name)

    @staticmethod
    def _now_text() -> str:
        return datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")

    def _material_preview_cache_customer_center_id(self, display_scope: str) -> str:
        if self._display_scope_uses_all_customer_centers(display_scope):
            return "__all_customer_centers__"
        return self._current_customer_center_id()

    def _persistent_preview_cache_payload(self, namespace: str, cache_key: str) -> dict[str, Any] | list[dict[str, Any]] | None:
        normalized_namespace = str(namespace or "").strip()
        normalized_cache_key = str(cache_key or "").strip()
        if not normalized_namespace or not normalized_cache_key:
            return None
        with self.db() as conn:
            if getattr(conn, "backend", "") == "postgres":
                row = conn.execute(
                    """
                    SELECT payload_json
                    FROM material_preview_cache_entries
                    WHERE cache_namespace = ?
                      AND cache_key = ?
                      AND expires_at > CURRENT_TIMESTAMP
                    LIMIT 1
                    """,
                    (normalized_namespace, normalized_cache_key),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT payload_json
                    FROM material_preview_cache_entries
                    WHERE cache_namespace = ?
                      AND cache_key = ?
                      AND expires_at > ?
                    LIMIT 1
                    """,
                    (normalized_namespace, normalized_cache_key, self._now_text()),
                ).fetchone()
        if not row:
            return None
        raw_payload = row["payload_json"]
        if isinstance(raw_payload, dict):
            return copy.deepcopy(raw_payload)
        if isinstance(raw_payload, list):
            return [dict(item) for item in raw_payload if isinstance(item, dict)]
        text = str(raw_payload or "").strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except Exception:
            return None
        if isinstance(parsed, dict):
            return copy.deepcopy(parsed)
        if isinstance(parsed, list):
            return [dict(item) for item in parsed if isinstance(item, dict)]
        return None

    def _store_persistent_preview_cache_payload(
        self,
        namespace: str,
        cache_key: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        ttl_seconds: int,
        customer_center_id: str = "",
        material_key: str = "",
    ) -> None:
        normalized_namespace = str(namespace or "").strip()
        normalized_cache_key = str(cache_key or "").strip()
        if not normalized_namespace or not normalized_cache_key:
            return
        now_text = self._now_text()
        expires_text = (
            datetime.now(ZoneInfo(TIMEZONE)) + timedelta(seconds=max(int(ttl_seconds or 0), 1))
        ).strftime("%Y-%m-%d %H:%M:%S")
        payload_json = self._json_text(payload)
        with self.db() as conn:
            conn.execute(
                """
                INSERT INTO material_preview_cache_entries (
                    cache_namespace,
                    cache_key,
                    customer_center_id,
                    material_key,
                    payload_json,
                    created_at,
                    updated_at,
                    expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (cache_namespace, cache_key) DO UPDATE SET
                    customer_center_id = excluded.customer_center_id,
                    material_key = excluded.material_key,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at
                """,
                (
                    normalized_namespace,
                    normalized_cache_key,
                    str(customer_center_id or "").strip(),
                    str(material_key or "").strip(),
                    payload_json,
                    self._db_optional_timestamp_value(now_text),
                    self._db_optional_timestamp_value(now_text),
                    self._db_optional_timestamp_value(expires_text),
                ),
            )

    def _material_preview_source_cached_payload(self, cache_key: str, cache_version: str) -> dict[str, Any] | None:
        versioned_cache_key = self._versioned_cache_key(cache_version, cache_key)
        cached_payload = self._local_dict_cache_get(
            self._material_preview_source_cache,
            versioned_cache_key,
            MATERIAL_PREVIEW_SOURCE_CACHE_SECONDS,
        )
        if cached_payload is None:
            cached_payload = self._shared_dict_cache_get("material-preview-source", cache_key, cache_version)
            if cached_payload is None:
                cached_payload = self._persistent_preview_cache_payload("material-preview-source", versioned_cache_key)
                if isinstance(cached_payload, dict):
                    self._shared_dict_cache_set(
                        "material-preview-source",
                        cache_key,
                        cache_version,
                        cached_payload,
                        MATERIAL_PREVIEW_SOURCE_CACHE_SECONDS,
                    )
            if cached_payload is not None:
                self._local_dict_cache_set(
                    self._material_preview_source_cache,
                    versioned_cache_key,
                    cached_payload,
                )
        if not isinstance(cached_payload, dict):
            return None
        for field in ("public_video_url", "video_url", "cover_url"):
            url = self._normalize_media_url(cached_payload.get(field))
            if url and self._preview_url_needs_refresh(url, leeway_seconds=60):
                return None
        return cached_payload

    def _store_material_preview_source_cache(
        self,
        cache_key: str,
        cache_version: str,
        payload: dict[str, Any],
    ) -> None:
        versioned_cache_key = self._versioned_cache_key(cache_version, cache_key)
        self._local_dict_cache_set(self._material_preview_source_cache, versioned_cache_key, payload)
        self._shared_dict_cache_set(
            "material-preview-source",
            cache_key,
            cache_version,
            payload,
            MATERIAL_PREVIEW_SOURCE_CACHE_SECONDS,
        )
        self._store_persistent_preview_cache_payload(
            "material-preview-source",
            versioned_cache_key,
            payload,
            ttl_seconds=MATERIAL_PREVIEW_SOURCE_CACHE_SECONDS,
            customer_center_id=str(payload.get("customer_center_id") or "").strip(),
            material_key=str(payload.get("material_key") or "").strip(),
        )

    def _material_preview_curve_cached_payload(self, cache_key: str, cache_version: str) -> dict[str, Any] | None:
        versioned_cache_key = self._versioned_cache_key(cache_version, cache_key)
        cached_payload = self._local_dict_cache_get(
            self._material_preview_curve_cache,
            versioned_cache_key,
            MATERIAL_PREVIEW_CURVE_CACHE_SECONDS,
        )
        if cached_payload is None:
            cached_payload = self._shared_dict_cache_get("material-preview-curve", cache_key, cache_version)
            if cached_payload is None:
                cached_payload = self._persistent_preview_cache_payload("material-preview-curve", versioned_cache_key)
                if isinstance(cached_payload, dict):
                    self._shared_dict_cache_set(
                        "material-preview-curve",
                        cache_key,
                        cache_version,
                        cached_payload,
                        MATERIAL_PREVIEW_CURVE_CACHE_SECONDS,
                    )
            if cached_payload is not None:
                self._local_dict_cache_set(
                    self._material_preview_curve_cache,
                    versioned_cache_key,
                    cached_payload,
                )
        return cached_payload if isinstance(cached_payload, dict) else None

    def _store_material_preview_curve_cache(
        self,
        cache_key: str,
        cache_version: str,
        payload: dict[str, Any],
    ) -> None:
        versioned_cache_key = self._versioned_cache_key(cache_version, cache_key)
        self._local_dict_cache_set(self._material_preview_curve_cache, versioned_cache_key, payload)
        self._shared_dict_cache_set(
            "material-preview-curve",
            cache_key,
            cache_version,
            payload,
            MATERIAL_PREVIEW_CURVE_CACHE_SECONDS,
        )
        self._store_persistent_preview_cache_payload(
            "material-preview-curve",
            versioned_cache_key,
            payload,
            ttl_seconds=MATERIAL_PREVIEW_CURVE_CACHE_SECONDS,
            customer_center_id=str(payload.get("customer_center_id") or "").strip(),
            material_key=str(payload.get("material_key") or "").strip(),
        )

    def _shared_preview_video_resolved_url(self, target_url: str) -> str:
        normalized_target = self._normalize_media_url(target_url)
        if not normalized_target:
            return ""
        cache_version = self._shared_cache_version("material-preview-url")
        versioned_cache_key = self._versioned_cache_key(cache_version, normalized_target)
        cached_payload = self._local_dict_cache_get(
            self._preview_video_resolve_cache,
            versioned_cache_key,
            PREVIEW_VIDEO_RESOLVE_CACHE_SECONDS,
        )
        if cached_payload is None:
            cached_payload = self._shared_dict_cache_get("material-preview-url", normalized_target, cache_version)
            if cached_payload is None:
                cached_payload = self._persistent_preview_cache_payload("material-preview-url", versioned_cache_key)
                if isinstance(cached_payload, dict):
                    self._shared_dict_cache_set(
                        "material-preview-url",
                        normalized_target,
                        cache_version,
                        cached_payload,
                        PREVIEW_VIDEO_RESOLVE_CACHE_SECONDS,
                    )
            if cached_payload is not None:
                self._local_dict_cache_set(self._preview_video_resolve_cache, versioned_cache_key, cached_payload)
        if not isinstance(cached_payload, dict):
            return ""
        resolved_url = self._normalize_media_url(cached_payload.get("resolved_url"))
        if not resolved_url or self._preview_url_needs_refresh(resolved_url, leeway_seconds=60):
            return ""
        return resolved_url

    def _store_shared_preview_video_resolved_url(self, target_url: str, resolved_url: str) -> None:
        normalized_target = self._normalize_media_url(target_url)
        normalized_resolved_url = self._normalize_media_url(resolved_url)
        if not normalized_target or not normalized_resolved_url:
            return
        cache_version = self._shared_cache_version("material-preview-url")
        payload = {"resolved_url": normalized_resolved_url}
        versioned_cache_key = self._versioned_cache_key(cache_version, normalized_target)
        self._local_dict_cache_set(self._preview_video_resolve_cache, versioned_cache_key, payload)
        self._shared_dict_cache_set(
            "material-preview-url",
            normalized_target,
            cache_version,
            payload,
            PREVIEW_VIDEO_RESOLVE_CACHE_SECONDS,
        )
        self._store_persistent_preview_cache_payload(
            "material-preview-url",
            versioned_cache_key,
            payload,
            ttl_seconds=PREVIEW_VIDEO_RESOLVE_CACHE_SECONDS,
        )

    def _material_preview_refresh_cached_rows(self, cache_key: str) -> list[dict[str, Any]] | None:
        now_ts = time.time()
        cached = self._material_preview_refresh_cache.get(cache_key)
        if cached and now_ts - float(cached.get("_cached_at", 0.0)) < MATERIAL_PREVIEW_REFRESH_CACHE_SECONDS:
            return [dict(row) for row in cached.get("rows", [])]
        cache_version = self._shared_cache_version("material-preview-refresh")
        shared_rows = self._shared_list_cache_get("material-preview-refresh", cache_key, cache_version)
        if shared_rows is None:
            versioned_cache_key = self._versioned_cache_key(cache_version, cache_key)
            persistent_rows = self._persistent_preview_cache_payload("material-preview-refresh", versioned_cache_key)
            if isinstance(persistent_rows, list):
                shared_rows = [dict(row) for row in persistent_rows if isinstance(row, dict)]
                self._shared_list_cache_set(
                    "material-preview-refresh",
                    cache_key,
                    cache_version,
                    shared_rows,
                    MATERIAL_PREVIEW_REFRESH_CACHE_SECONDS,
                )
        if shared_rows is not None:
            self._material_preview_refresh_cache[cache_key] = {
                "_cached_at": now_ts,
                "rows": [dict(row) for row in shared_rows],
            }
            return [dict(row) for row in shared_rows]
        return None

    def _store_material_preview_refresh_rows(self, cache_key: str, rows: list[dict[str, Any]]) -> None:
        normalized_rows = [dict(row) for row in rows if isinstance(row, dict)]
        self._material_preview_refresh_cache[cache_key] = {
            "_cached_at": time.time(),
            "rows": normalized_rows,
        }
        cache_version = self._shared_cache_version("material-preview-refresh")
        self._shared_list_cache_set(
            "material-preview-refresh",
            cache_key,
            cache_version,
            normalized_rows,
            MATERIAL_PREVIEW_REFRESH_CACHE_SECONDS,
        )
        versioned_cache_key = self._versioned_cache_key(cache_version, cache_key)
        customer_center_id = ""
        if normalized_rows:
            customer_center_id = str(normalized_rows[0].get("customer_center_id") or "").strip()
        self._store_persistent_preview_cache_payload(
            "material-preview-refresh",
            versioned_cache_key,
            normalized_rows,
            ttl_seconds=MATERIAL_PREVIEW_REFRESH_CACHE_SECONDS,
            customer_center_id=customer_center_id,
        )

    @staticmethod
    def _empty_material_preview_fields() -> dict[str, str]:
        return {
            "video_id": "",
            "cover_url": "",
            "aweme_item_id": "",
            "video_url": "",
        }

    @staticmethod
    def _merge_material_preview_fields(target: dict[str, str], row: dict[str, Any]) -> None:
        for field in ("video_id", "cover_url", "aweme_item_id", "video_url"):
            if target.get(field):
                continue
            text = str(row.get(field) or "").strip()
            if text:
                target[field] = text

    @staticmethod
    def _material_preview_available(preview: dict[str, str]) -> bool:
        return any(
            str(preview.get(field) or "").strip()
            for field in ("cover_url", "aweme_item_id", "video_url")
        )

    def _latest_material_preview_map(
        self,
        conn: Any,
        items: list[dict[str, Any]],
        *,
        default_customer_center_id: str = "",
    ) -> dict[str, dict[str, str]]:
        requested_keys = {
            str(item.get("material_key") or "").strip()
            for item in items
            if str(item.get("material_key") or "").strip()
        }
        if not requested_keys:
            return {}
        requested_customer_centers_by_key: dict[str, set[str]] = {}
        normalized_default_customer_center_id = str(default_customer_center_id or "").strip()
        for item in items:
            material_key = str(item.get("material_key") or "").strip()
            if not material_key:
                continue
            customer_center_id = str(item.get("customer_center_id") or normalized_default_customer_center_id).strip()
            if customer_center_id:
                requested_customer_centers_by_key.setdefault(material_key, set()).add(customer_center_id)
        preview_map: dict[str, dict[str, str]] = {}
        latest_by_table_and_key: dict[tuple[str, str], dict[str, Any]] = {}
        latest_by_table_key_and_customer_center: dict[tuple[str, str, str], dict[str, Any]] = {}
        for table_name in ("material_rollups", "material_snapshots"):
            for material_key_chunk in self._chunked_material_keys(sorted(requested_keys)):
                placeholders = ",".join("?" for _ in material_key_chunk)
                clauses = [f"material_key IN ({placeholders})"]
                params: list[Any] = [*material_key_chunk]
                if normalized_default_customer_center_id:
                    clauses.append("customer_center_id = ?")
                    params.append(normalized_default_customer_center_id)
                rows = conn.execute(
                    f"""
                    SELECT customer_center_id, material_key, video_id, cover_url, aweme_item_id, video_url, snapshot_time, create_time
                    FROM {table_name}
                    WHERE {" AND ".join(clauses)}
                    ORDER BY material_key ASC, snapshot_time DESC, create_time DESC
                    """,
                    params,
                ).fetchall()
                for raw_row in rows:
                    row = dict(raw_row)
                    material_key = str(row.get("material_key") or "").strip()
                    if not material_key:
                        continue
                    latest_by_table_and_key.setdefault((table_name, material_key), row)
                    customer_center_id = str(row.get("customer_center_id") or "").strip()
                    if customer_center_id:
                        latest_by_table_key_and_customer_center.setdefault((table_name, material_key, customer_center_id), row)
        for material_key in requested_keys:
            preview = preview_map.setdefault(material_key, self._empty_material_preview_fields())
            requested_customer_centers = requested_customer_centers_by_key.get(material_key) or set()
            for table_name in ("material_rollups", "material_snapshots"):
                for customer_center_id in sorted(requested_customer_centers):
                    scoped_row = latest_by_table_key_and_customer_center.get((table_name, material_key, customer_center_id))
                    if scoped_row:
                        self._merge_material_preview_fields(preview, scoped_row)
                latest_row = latest_by_table_and_key.get((table_name, material_key))
                if latest_row:
                    self._merge_material_preview_fields(preview, latest_row)
        return {
            key: value
            for key, value in preview_map.items()
            if self._material_preview_available(value) or str(value.get("video_id") or "").strip()
        }

    def _apply_latest_material_previews(
        self,
        conn: Any,
        items: list[dict[str, Any]],
        *,
        default_customer_center_id: str = "",
    ) -> list[dict[str, Any]]:
        if not items:
            return items
        preview_map = self._latest_material_preview_map(
            conn,
            items,
            default_customer_center_id=default_customer_center_id,
        )
        if not preview_map:
            return items
        for item in items:
            preview = preview_map.get(str(item.get("material_key") or "").strip())
            if not preview:
                continue
            for field in ("video_id", "cover_url", "aweme_item_id", "video_url"):
                text = str(preview.get(field) or "").strip()
                if text:
                    item[field] = text
        return items

    def _sanitize_material_preview_fields_for_payload(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not items:
            return items
        sanitized_items: list[dict[str, Any]] = []
        for raw_item in items:
            item = dict(raw_item)
            cover_url = self._normalize_media_url(item.get("cover_url"))
            video_url = self._normalize_media_url(item.get("video_url"))
            item["cover_url"] = self._coerce_public_preview_cover_url(cover_url)
            item["video_url"] = (
                video_url
                if self._is_public_preview_video_url(video_url) and not self._needs_preview_video_redirect_resolution(video_url)
                else ""
            )
            item["preview_available"] = bool(
                item["cover_url"]
                or item["video_url"]
                or str(item.get("aweme_item_id") or "").strip()
                or str(item.get("video_id") or "").strip()
                or str(item.get("material_id") or "").strip()
                or str(item.get("material_key") or "").strip()
            )
            sanitized_items.append(item)
        return sanitized_items

    def _material_preview_candidate_indexes(
        self,
        rows: list[dict[str, Any]],
        material_type: str,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        indexes = {
            "material_id": {},
            "material_key": {},
            "video_id": {},
            "aweme_item_id": {},
        }
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_material_info = self._json_object(row.get("material_info"))
            resolved_material_type = str(
                row.get("material_type")
                or raw_material_info.get("material_type")
                or material_type
                or "VIDEO"
            ).strip().upper()
            identity = self._extract_material_identity(resolved_material_type, row)
            preview = self._extract_material_preview(resolved_material_type, row)
            if not self._material_preview_available(preview):
                continue
            candidate = {
                "material_type": resolved_material_type,
                "identity": identity,
                "preview": preview,
            }
            material_id = self._numeric_material_id_text(identity.get("material_id"))
            if material_id and material_id not in indexes["material_id"]:
                indexes["material_id"][material_id] = candidate
            material_key = str(identity.get("material_key") or "").strip()
            if material_key and material_key not in indexes["material_key"]:
                indexes["material_key"][material_key] = candidate
            video_id = str(identity.get("video_id") or "").strip()
            if video_id and video_id not in indexes["video_id"]:
                indexes["video_id"][video_id] = candidate
            aweme_item_id = str(preview.get("aweme_item_id") or "").strip()
            if aweme_item_id and aweme_item_id not in indexes["aweme_item_id"]:
                indexes["aweme_item_id"][aweme_item_id] = candidate
        return indexes

    def _match_refreshed_material_preview(
        self,
        item: dict[str, Any],
        source: dict[str, Any],
        indexes: dict[str, dict[str, dict[str, Any]]],
    ) -> dict[str, Any] | None:
        material_id = self._numeric_material_id_text(source.get("material_id"), item.get("material_id"))
        if material_id:
            candidate = indexes["material_id"].get(material_id)
            if candidate:
                return candidate
        video_id = self._first_text(source.get("video_id"), item.get("video_id"))
        if video_id:
            candidate = indexes["video_id"].get(video_id)
            if candidate:
                return candidate
        aweme_item_id = self._first_text(source.get("aweme_item_id"), item.get("aweme_item_id"))
        if aweme_item_id:
            candidate = indexes["aweme_item_id"].get(aweme_item_id)
            if candidate:
                return candidate
        material_key = self._first_text(source.get("material_key"), item.get("material_key"))
        if material_key:
            return indexes["material_key"].get(material_key)
        return None

    def _refresh_stale_material_previews(
        self,
        items: list[dict[str, Any]],
        start_date: str,
        end_date: str,
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
        *,
        search_all_customer_centers: bool = False,
    ) -> list[dict[str, Any]]:
        if not items:
            return items
        refresh_targets: dict[tuple[str, int, int, str], list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        current_customer_center_id = self._current_customer_center_id()
        for item in items:
            material_type = str(item.get("material_type") or "VIDEO").strip().upper()
            cover_needs_refresh = self._preview_url_needs_refresh(str(item.get("cover_url") or ""))
            video_needs_refresh = self._preview_url_needs_refresh(str(item.get("video_url") or ""))
            should_refresh = video_needs_refresh or cover_needs_refresh if material_type == "VIDEO" else cover_needs_refresh
            if not should_refresh:
                continue
            source = self._resolve_material_curve_source(
                item,
                start_date,
                end_date,
                snapshot_time,
                allowed_advertiser_ids,
                search_all_customer_centers=search_all_customer_centers,
            )
            if not source:
                continue
            customer_center_id = str(source.get("customer_center_id") or current_customer_center_id).strip()
            advertiser_id = int(source.get("advertiser_id", 0) or 0)
            ad_id = int(source.get("ad_id", 0) or 0)
            material_type = str(source.get("material_type") or item.get("material_type") or "VIDEO").strip().upper()
            if not customer_center_id or advertiser_id <= 0 or ad_id <= 0 or material_type not in PLAN_MATERIAL_TYPES:
                continue
            refresh_targets.setdefault(
                (customer_center_id, advertiser_id, ad_id, material_type),
                [],
            ).append((item, source))
        if not refresh_targets:
            return items

        refreshed_rows: dict[tuple[str, int, int, str], list[dict[str, Any]]] = {}
        with ThreadPoolExecutor(max_workers=min(len(refresh_targets), 4)) as executor:
            future_map = {
                executor.submit(
                    self._plan_material_rows_for_preview_refresh,
                    customer_center_id,
                    advertiser_id,
                    ad_id,
                    material_type,
                ): (customer_center_id, advertiser_id, ad_id, material_type)
                for customer_center_id, advertiser_id, ad_id, material_type in refresh_targets
            }
            for future in as_completed(future_map):
                group_key = future_map[future]
                try:
                    refreshed_rows[group_key] = future.result()
                except Exception:
                    refreshed_rows[group_key] = []

        for group_key, targets in refresh_targets.items():
            customer_center_id, advertiser_id, ad_id, material_type = group_key
            candidate_rows = refreshed_rows.get(group_key) or []
            if not candidate_rows:
                continue
            indexes = self._material_preview_candidate_indexes(candidate_rows, material_type)
            for item, source in targets:
                candidate = self._match_refreshed_material_preview(item, source, indexes)
                if not candidate:
                    continue
                preview = candidate.get("preview") or {}
                identity = candidate.get("identity") or {}
                cover_url = str(preview.get("cover_url") or "").strip()
                if cover_url:
                    item["cover_url"] = cover_url
                aweme_item_id = str(preview.get("aweme_item_id") or "").strip()
                if aweme_item_id:
                    item["aweme_item_id"] = aweme_item_id
                video_url = str(preview.get("video_url") or "").strip()
                if video_url:
                    item["video_url"] = video_url
                video_id = str(identity.get("video_id") or "").strip()
                if video_id:
                    item["video_id"] = video_id
                item["_preview_refreshed"] = True
                item["_preview_refresh_customer_center_id"] = customer_center_id
                item["_preview_refresh_advertiser_id"] = advertiser_id
                item["_preview_refresh_ad_id"] = ad_id
        return items

    def _refresh_leading_material_previews(
        self,
        items: list[dict[str, Any]],
        start_date: str,
        end_date: str,
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
        *,
        search_all_customer_centers: bool = False,
    ) -> list[dict[str, Any]]:
        if not items:
            return items
        leading_items = items[:MATERIAL_PREVIEW_REFRESH_LEADING_ITEM_LIMIT]
        self._refresh_stale_material_previews(
            leading_items,
            start_date,
            end_date,
            snapshot_time,
            allowed_advertiser_ids,
            search_all_customer_centers=search_all_customer_centers,
        )
        return items

    def material_preview_source_v2(
        self,
        row: dict[str, Any] | None,
        range_key: str = "day",
        start_date: str = "",
        end_date: str = "",
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
        user: dict[str, Any] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> dict[str, Any]:
        seed_row = dict(row or {})
        material_key_text = str(seed_row.get("material_key") or "").strip()
        search_all_customer_centers = (
            self._display_scope_uses_all_customer_centers(display_scope)
            or str((user or {}).get("role") or "") == ROLE_OPERATOR
        )
        if material_key_text:
            try:
                resolved_row, search_all_customer_centers = self._material_preview_row_for_request(
                    material_key_text,
                    range_key,
                    start_date,
                    end_date,
                    snapshot_time,
                    allowed_advertiser_ids,
                    user,
                    display_scope,
                )
            except ValueError:
                if not seed_row:
                    raise
                resolved_row = seed_row
        elif seed_row:
            resolved_row = seed_row
        else:
            raise ValueError("material_key is required")

        merged_row = dict(resolved_row)
        for key, value in seed_row.items():
            if key not in merged_row or merged_row.get(key) in (None, ""):
                merged_row[key] = value

        current_video_url = self._normalize_media_url(merged_row.get("video_url"))
        resolved_current_video_url = self._resolve_preview_video_url(current_video_url)
        cover_url = self._normalize_media_url(merged_row.get("cover_url"))
        aweme_item_id = str(merged_row.get("aweme_item_id") or "").strip()
        video_id = str(merged_row.get("video_id") or "").strip()
        material_id = str(merged_row.get("material_id") or "").strip()
        public_video_url = resolved_current_video_url or current_video_url
        result = {
            "material_key": str(merged_row.get("material_key") or "").strip(),
            "material_id": material_id,
            "video_id": video_id,
            "cover_url": cover_url if self._is_public_preview_cover_url(cover_url) else "",
            "aweme_item_id": aweme_item_id,
            "video_url": public_video_url if self._is_public_preview_video_url(public_video_url) else "",
            "public_video_url": public_video_url if self._is_public_preview_video_url(public_video_url) else "",
            "is_public_video_url": self._is_public_preview_video_url(public_video_url),
            "source": "current_material_payload",
            "reason": "",
            "customer_center_id": str(merged_row.get("customer_center_id") or "").strip(),
        }

        start_text = str(start_date or "").strip()
        end_text = str(end_date or "").strip()
        if not snapshot_time and (not start_text or not end_text):
            if str(range_key or "").strip().lower() == "custom":
                start_text = start_text or str(merged_row.get("create_time") or "")[:10]
                end_text = end_text or str(merged_row.get("create_time") or "")[:10]
            else:
                requested_start_dt, requested_end_dt, _label = self._material_preview_requested_window(
                    range_key,
                    start_date,
                    end_date,
                    snapshot_time,
                )
                start_text = requested_start_dt.strftime("%Y-%m-%d")
                end_text = requested_end_dt.strftime("%Y-%m-%d")

        cache_key = build_material_preview_source_cache_key(
            merged_row,
            range_key,
            start_text,
            end_text,
            snapshot_time,
            allowed_advertiser_ids,
            self._material_preview_cache_customer_center_id(display_scope),
        )
        cache_version = self._shared_cache_version("material-preview-source") if cache_key else "1"

        def finish(payload: dict[str, Any]) -> dict[str, Any]:
            if cache_key and isinstance(payload, dict):
                self._store_material_preview_source_cache(cache_key, cache_version, payload)
            return payload

        if cache_key:
            cached_payload = self._material_preview_source_cached_payload(cache_key, cache_version)
            if cached_payload is not None:
                return cached_payload

        if result["is_public_video_url"]:
            return finish(result)

        resolved_sources = self._material_curve_source_candidates(
            merged_row,
            start_text,
            end_text,
            snapshot_time,
            allowed_advertiser_ids,
            search_all_customer_centers=search_all_customer_centers,
        )
        if not resolved_sources:
            result["reason"] = "当前素材未定位到可解析的预览来源。"
            if current_video_url and self._needs_preview_video_redirect_resolution(current_video_url):
                result["reason"] = "当前素材返回的是千川中转预览地址，无法直接在浏览器中播放。"
                result["source"] = "redirect_preview_video_url"
            elif current_video_url and self._is_internal_preview_video_url(current_video_url):
                result["reason"] = "当前素材只返回站内预览地址，无法在外部页面直接播放。"
                result["source"] = "internal_video_url"
            elif cover_url and not self._is_public_preview_cover_url(cover_url):
                result["reason"] = "当前素材仅返回受限封面图地址，浏览器无法直接加载。"
                result["source"] = "restricted_cover_url"
            elif not current_video_url and cover_url:
                result["reason"] = "当前素材仅返回封面图，未返回可直接播放的视频地址。"
                result["source"] = "cover_only"
            return finish(result)

        attempted_sources = 0
        any_source_material_id = False
        for resolved_source in resolved_sources:
            customer_center_id = str(resolved_source.get("customer_center_id") or "").strip()
            advertiser_id = int(resolved_source.get("advertiser_id", 0) or 0)
            source_video_id = str(resolved_source.get("video_id") or video_id).strip()
            source_material_id = str(resolved_source.get("material_id") or material_id).strip()
            if source_material_id:
                any_source_material_id = True
            if not customer_center_id or advertiser_id <= 0:
                continue
            attempted_sources += 1
            client = self._build_scoped_customer_center_client(customer_center_id)
            if source_video_id:
                try:
                    uploaded_video = client.get_uploaded_video(advertiser_id, source_video_id)
                    candidate_video_url = self._preferred_video_url_from_values(
                        uploaded_video.get("url"),
                        uploaded_video.get("video_url"),
                        uploaded_video.get("videoUrl"),
                        uploaded_video.get("play_url"),
                        uploaded_video.get("playUrl"),
                        uploaded_video.get("download_url"),
                        uploaded_video.get("downloadUrl"),
                        uploaded_video.get("download_url_https"),
                        uploaded_video.get("downloadUrlHttps"),
                        uploaded_video.get("material_url"),
                        uploaded_video.get("materialUrl"),
                        current_video_url,
                    )
                    resolved_public_video_url = self._resolve_preview_video_url(candidate_video_url)
                    if self._is_public_preview_video_url(resolved_public_video_url):
                        result["video_url"] = resolved_public_video_url
                        result["public_video_url"] = resolved_public_video_url
                        result["is_public_video_url"] = True
                        result["source"] = "file_video_ad_get"
                        result["reason"] = ""
                        result["customer_center_id"] = customer_center_id
                        poster_url = self._coerce_public_preview_cover_url(
                            uploaded_video.get("poster_url") or uploaded_video.get("posterUrl")
                        )
                        if poster_url:
                            result["cover_url"] = poster_url
                        return finish(result)
                    proxy_video_url = self.build_material_preview_proxy_url(candidate_video_url)
                    if proxy_video_url:
                        result["video_url"] = proxy_video_url
                        result["public_video_url"] = proxy_video_url
                        result["is_public_video_url"] = True
                        result["source"] = "file_video_ad_get_proxy"
                        result["reason"] = ""
                        result["customer_center_id"] = customer_center_id
                        poster_url = self._coerce_public_preview_cover_url(
                            uploaded_video.get("poster_url") or uploaded_video.get("posterUrl")
                        )
                        if poster_url:
                            result["cover_url"] = poster_url
                        return finish(result)
                except Exception as exc:  # noqa: BLE001
                    message = str(exc)
                    lowered = message.lower()
                    if "permission" in lowered and not result["reason"]:
                        result["reason"] = "当前账号未授权公开视频接口，无法优先返回公网直链。"
                        result["source"] = "file_video_ad_get_permission_denied"
                    elif ("refresh_token" in lowered or "40103" in message or "已过期" in message) and not result["reason"]:
                        result["reason"] = "素材所属客服中心授权已过期，当前无法解析可外部访问的预览地址。"
                        result["source"] = "file_video_ad_get_token_expired"
                try:
                    video_rows = client.list_qianchuan_videos(
                        advertiser_id=advertiser_id,
                        filtering={"video_ids": [source_video_id]},
                        page_size=20,
                        max_pages=1,
                    )
                    for item in video_rows:
                        resolved_library_video_id = str(item.get("id") or item.get("video_id") or item.get("videoId") or "").strip()
                        if resolved_library_video_id and resolved_library_video_id != source_video_id:
                            continue
                        candidate_video_url = self._preferred_video_url_from_values(
                            item.get("url"),
                            item.get("video_url"),
                            item.get("videoUrl"),
                            item.get("play_url"),
                            item.get("playUrl"),
                            current_video_url,
                        )
                        resolved_library_video_url = self._resolve_preview_video_url(candidate_video_url)
                        if self._is_public_preview_video_url(resolved_library_video_url):
                            result["video_url"] = resolved_library_video_url
                            result["public_video_url"] = resolved_library_video_url
                            result["is_public_video_url"] = True
                            result["source"] = "qianchuan_video_get"
                            result["reason"] = ""
                            result["customer_center_id"] = customer_center_id
                            poster_url = self._coerce_public_preview_cover_url(
                                item.get("poster_url") or item.get("posterUrl") or cover_url
                            )
                            if poster_url:
                                result["cover_url"] = poster_url
                            return finish(result)
                        proxy_video_url = self.build_material_preview_proxy_url(candidate_video_url)
                        if proxy_video_url:
                            result["video_url"] = proxy_video_url
                            result["public_video_url"] = proxy_video_url
                            result["is_public_video_url"] = True
                            result["source"] = "qianchuan_video_get_proxy"
                            result["reason"] = ""
                            result["customer_center_id"] = customer_center_id
                            poster_url = self._coerce_public_preview_cover_url(
                                item.get("poster_url") or item.get("posterUrl") or cover_url
                            )
                            if poster_url:
                                result["cover_url"] = poster_url
                            return finish(result)
                        poster_url = self._coerce_public_preview_cover_url(
                            item.get("poster_url") or item.get("posterUrl") or cover_url
                        )
                        if poster_url and not result["cover_url"]:
                            result["cover_url"] = poster_url
                except Exception:
                    pass

        if attempted_sources <= 0:
            result["reason"] = "当前素材缺少可解析的预览来源配置。"
            return finish(result)

        if current_video_url and self._needs_preview_video_redirect_resolution(current_video_url):
            result["reason"] = result["reason"] or "当前素材返回的是千川中转预览地址，无法直接在浏览器中播放。"
            result["source"] = "redirect_preview_video_url"
        elif current_video_url and self._is_internal_preview_video_url(current_video_url):
            result["reason"] = result["reason"] or "当前素材只返回站内预览地址，无法在外部页面直接播放。"
            result["source"] = "internal_video_url"
        elif cover_url and not self._is_public_preview_cover_url(cover_url):
            result["reason"] = result["reason"] or "当前素材仅返回受限封面图地址，浏览器无法直接加载。"
            result["source"] = "restricted_cover_url"
        elif not current_video_url and cover_url:
            result["reason"] = result["reason"] or "当前素材仅返回封面图，未返回可直接播放的视频地址。"
            result["source"] = "cover_only"
        elif any_source_material_id:
            result["reason"] = result["reason"] or "已尝试解析公网直链，但当前接口未返回可外部访问的视频文件地址。"
        return finish(result)

    def material_preview_curve(
        self,
        material_key: str,
        range_key: str = "day",
        start_date: str = "",
        end_date: str = "",
        snapshot_time: str = "",
        allowed_advertiser_ids: set[int] | None = None,
        user: dict[str, Any] | None = None,
        display_scope: str = DISPLAY_SCOPE_CURRENT,
    ) -> dict[str, Any]:
        material_key_text = str(material_key or "").strip()
        row, search_all_customer_centers = self._material_preview_row_for_request(
            material_key_text,
            range_key,
            start_date,
            end_date,
            snapshot_time,
            allowed_advertiser_ids,
            user,
            display_scope,
        )

        material_type = str(row.get("material_type") or "").strip().upper()
        advertiser_ids = [int(item) for item in row.get("advertiser_ids", []) if int(item or 0)]
        advertiser_id = advertiser_ids[0] if advertiser_ids else 0

        requested_start_dt, requested_end_dt, requested_range_label = self._material_preview_requested_window(
            range_key,
            start_date,
            end_date,
            snapshot_time,
        )
        config = self.read_config()
        tz = ZoneInfo(str(config.get("timezone") or TIMEZONE))
        latest_available_day = (datetime.now(tz) - timedelta(days=1)).date()
        latest_available_start = datetime(
            latest_available_day.year,
            latest_available_day.month,
            latest_available_day.day,
            0,
            0,
            0,
            tzinfo=tz,
        )
        latest_available_end = datetime(
            latest_available_day.year,
            latest_available_day.month,
            latest_available_day.day,
            23,
            59,
            59,
            tzinfo=tz,
        )

        response_payload: dict[str, Any] = {
            "material_key": material_key_text,
            "material_id": str(row.get("material_id") or ""),
            "material_name": str(row.get("material_name") or ""),
            "material_type": material_type,
            "advertiser_id": advertiser_id,
            "curve_material_id": "",
            "curve_advertiser_id": 0,
            "curve_ad_id": 0,
            "material_id_source": "",
            "advertiser_count": len(advertiser_ids),
            "top_account_name": str(row.get("top_account_name") or ""),
            "customer_center_id": str(row.get("customer_center_id") or "").strip(),
            "supported": material_type == "VIDEO",
            "t_plus_one_only": True,
            "range_key": str(range_key or "day"),
            "range_label": str(requested_range_label or ""),
            "requested_start_date": requested_start_dt.strftime("%Y-%m-%d"),
            "requested_end_date": requested_end_dt.strftime("%Y-%m-%d"),
            "query_start_date": "",
            "query_end_date": "",
            "is_clamped_to_yesterday": False,
            "notice": "",
            "message": "",
            "series": [],
            "totals": {
                "click_cnt": 0,
                "user_lose_cnt": 0,
            },
            "peak": {
                "second": 0,
                "click_cnt": 0,
                "user_lose_cnt": 0,
            },
            "duration_seconds": 0,
            "point_count": 0,
        }

        if material_type != "VIDEO":
            response_payload["message"] = "仅视频素材支持互动峰形图。"
            return response_payload

        query_start_dt = requested_start_dt
        query_end_dt = min(requested_end_dt, latest_available_end)
        clamped = query_end_dt < requested_end_dt
        target_snapshot = str(snapshot_time or "").strip()
        normalized_range = str(range_key or "day").strip().lower()
        if query_start_dt > query_end_dt:
            if not target_snapshot and normalized_range == "day":
                query_start_dt = latest_available_start
                query_end_dt = latest_available_end
                clamped = True
            else:
                response_payload["query_start_date"] = requested_start_dt.strftime("%Y-%m-%d")
                response_payload["query_end_date"] = requested_end_dt.strftime("%Y-%m-%d")
                response_payload["is_clamped_to_yesterday"] = clamped
                response_payload["message"] = "当前筛选范围内没有可查询的 T+1 数据。"
                if clamped:
                    response_payload["notice"] = f"该接口仅支持 T+1 数据，最近可查询日期为 {latest_available_day.isoformat()}。"
                return response_payload

        response_payload["query_start_date"] = query_start_dt.strftime("%Y-%m-%d")
        response_payload["query_end_date"] = query_end_dt.strftime("%Y-%m-%d")
        response_payload["is_clamped_to_yesterday"] = clamped

        cache_key = build_material_preview_curve_cache_key(
            material_key_text,
            range_key,
            response_payload["query_start_date"],
            response_payload["query_end_date"],
            snapshot_time,
            allowed_advertiser_ids,
            self._material_preview_cache_customer_center_id(display_scope),
        )
        cache_version = self._shared_cache_version("material-preview-curve") if cache_key else "1"

        def finish(payload: dict[str, Any]) -> dict[str, Any]:
            if cache_key and isinstance(payload, dict):
                self._store_material_preview_curve_cache(cache_key, cache_version, payload)
            return payload

        if cache_key:
            cached_payload = self._material_preview_curve_cached_payload(cache_key, cache_version)
            if cached_payload is not None:
                return cached_payload

        resolved_source = self._resolve_material_curve_source(
            row,
            response_payload["query_start_date"],
            response_payload["query_end_date"],
            snapshot_time,
            allowed_advertiser_ids,
            search_all_customer_centers=search_all_customer_centers,
        )
        if resolved_source:
            response_payload["curve_material_id"] = str(resolved_source.get("material_id") or "")
            response_payload["curve_advertiser_id"] = int(resolved_source.get("advertiser_id", 0) or 0)
            response_payload["curve_ad_id"] = int(resolved_source.get("ad_id", 0) or 0)
            response_payload["material_id_source"] = str(resolved_source.get("source") or "")
            response_payload["customer_center_id"] = str(resolved_source.get("customer_center_id") or response_payload["customer_center_id"]).strip()
        if not response_payload["curve_material_id"]:
            response_payload["message"] = "未找到可用于峰形图查询的素材唯一 ID。"
            return finish(response_payload)
        if not response_payload["curve_advertiser_id"]:
            response_payload["message"] = "未找到可用于峰形图查询的投放账户 ID。"
            return finish(response_payload)

        notices: list[str] = []
        if clamped:
            notices.append(f"该接口仅支持 T+1 数据，当前展示截至 {latest_available_day.isoformat()} 的数据。")
        if len(advertiser_ids) > 1:
            account_name = str(row.get("top_account_name") or "").strip()
            if account_name:
                notices.append(f"该素材被多个账户复用，当前仅展示账户 {account_name} 的曲线。")
            else:
                notices.append("该素材被多个账户复用，当前仅展示其中一个账户的曲线。")

        client = self.build_client(config)
        response = client.get_video_user_lose(
            advertiser_id=int(response_payload["curve_advertiser_id"]),
            material_id=response_payload["curve_material_id"],
            start_date=response_payload["query_start_date"],
            end_date=response_payload["query_end_date"],
        )
        points = self._normalize_video_user_lose_rows(response)
        response_payload["series"] = [
            {
                "second": int(point["second"]),
                "click_cnt": int(round(point["click_cnt"])),
                "user_lose_cnt": int(round(point["user_lose_cnt"])),
            }
            for point in points
        ]
        response_payload["duration_seconds"] = int(max((point["second"] for point in points), default=0))
        response_payload["point_count"] = len(points)
        response_payload["totals"] = {
            "click_cnt": int(round(sum(point["click_cnt"] for point in points))),
            "user_lose_cnt": int(round(sum(point["user_lose_cnt"] for point in points))),
        }
        peak_point = max(
            response_payload["series"],
            key=lambda item: (int(item["user_lose_cnt"]), int(item["click_cnt"]), -int(item["second"])),
            default={"second": 0, "click_cnt": 0, "user_lose_cnt": 0},
        )
        response_payload["peak"] = {
            "second": int(peak_point["second"]),
            "click_cnt": int(peak_point["click_cnt"]),
            "user_lose_cnt": int(peak_point["user_lose_cnt"]),
        }
        if not response_payload["series"]:
            response_payload["message"] = "接口未返回该素材的秒级互动分布数据。"
        if notices:
            response_payload["notice"] = " ".join(notices)
        return finish(response_payload)
