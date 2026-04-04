from __future__ import annotations

import time
from typing import Any, Callable


class TokenAccess:
    def __init__(
        self,
        db_factory: Callable[[], Any],
        config_loader: Callable[[], dict[str, Any]],
        client_builder: Callable[[dict[str, Any]], Any],
    ) -> None:
        self._db = db_factory
        self._config_loader = config_loader
        self._client_builder = client_builder

    def persist_token_record(self, payload: dict[str, Any]) -> None:
        app_id = str(payload.get("app_id") or "").strip()
        customer_center_id = str(payload.get("customer_center_id") or "").strip()
        if not app_id or not customer_center_id:
            return
        with self._db() as conn:
            conn.execute(
                """
                INSERT INTO oauth_tokens (
                    app_id, customer_center_id, access_token, refresh_token,
                    expires_at, refresh_token_expires_in, updated_at, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (app_id, customer_center_id) DO UPDATE SET
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    expires_at = excluded.expires_at,
                    refresh_token_expires_in = excluded.refresh_token_expires_in,
                    updated_at = excluded.updated_at,
                    source = excluded.source
                """,
                (
                    app_id,
                    customer_center_id,
                    str(payload.get("access_token") or ""),
                    str(payload.get("refresh_token") or ""),
                    int(payload.get("expires_at") or 0),
                    int(payload.get("refresh_token_expires_in") or 0),
                    int(payload.get("updated_at") or int(time.time())),
                    str(payload.get("source") or "runtime"),
                ),
            )

    def token_payload_for(
        self,
        app_id: str,
        customer_center_id: str,
        masked: bool = False,
    ) -> dict[str, Any] | None:
        normalized_app_id = str(app_id or "").strip()
        normalized_customer_center_id = str(customer_center_id or "").strip()
        if not normalized_app_id or not normalized_customer_center_id:
            return None
        with self._db() as conn:
            row = conn.execute(
                """
                SELECT app_id, customer_center_id, access_token, refresh_token,
                       expires_at, refresh_token_expires_in, updated_at, source
                FROM oauth_tokens
                WHERE app_id = ? AND customer_center_id = ?
                LIMIT 1
                """,
                (normalized_app_id, normalized_customer_center_id),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        if not masked:
            return payload
        masked_payload = dict(payload)
        masked_payload["access_token"] = self._mask_token(masked_payload.get("access_token", ""))
        masked_payload["refresh_token"] = self._mask_token(masked_payload.get("refresh_token", ""))
        return masked_payload

    def _db_token_payload(self) -> dict[str, Any] | None:
        config = self._config_loader()
        return self.token_payload_for(str(config["app_id"]), str(config["customer_center_id"]))

    def bootstrap_token_store(self) -> None:
        existing = self._db_token_payload()
        if existing:
            return
        client = self._client_builder(self._config_loader())
        payload = client.latest_token_payload()
        if payload.get("access_token") or payload.get("refresh_token"):
            payload["source"] = "file_cache"
            self.persist_token_record(payload)

    @staticmethod
    def _mask_token(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if len(text) <= 10:
            return text
        return f"{text[:4]}...{text[-6:]}"

    def latest_token_payload(self, masked: bool = False) -> dict[str, Any]:
        payload = self._db_token_payload()
        if not payload:
            client = self._client_builder(self._config_loader())
            payload = client.latest_token_payload()
            if payload.get("access_token") or payload.get("refresh_token"):
                payload["source"] = "file_cache"
                self.persist_token_record(payload)
        if not masked:
            return payload
        masked_payload = dict(payload)
        masked_payload["access_token"] = self._mask_token(masked_payload.get("access_token", ""))
        masked_payload["refresh_token"] = self._mask_token(masked_payload.get("refresh_token", ""))
        return masked_payload

    def exchange_auth_code(self, auth_code: str) -> dict[str, Any]:
        client = self._client_builder(self._config_loader())
        return client.exchange_auth_code(auth_code)
