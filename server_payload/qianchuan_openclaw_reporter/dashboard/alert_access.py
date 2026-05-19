from __future__ import annotations

from typing import Any, Callable

from dashboard.alert_schemas import normalize_summary_times, validate_alert_rule_payload


class AlertAccess:
    def __init__(
        self,
        db_factory: Callable[[], Any],
        now_text: Callable[[], str],
        default_notification_target: Callable[[], str],
    ) -> None:
        self._db = db_factory
        self._now_text = now_text
        self._default_notification_target = default_notification_target

    def ensure_notification_settings(self, conn: Any) -> None:
        exists = conn.execute("SELECT 1 FROM notification_settings WHERE id = 1").fetchone()
        if exists:
            return
        conn.execute(
            """
            INSERT INTO notification_settings (
                id, enabled, channel, account, target, alert_enabled, alert_batch_size,
                summary_enabled, summary_times, summary_account_limit, summary_plan_limit, updated_at
            ) VALUES (1, 0, 'feishu', 'default', ?, 0, 6, 0, '09:00', 6, 10, ?)
            """,
            (self._default_notification_target(), self._now_text()),
        )

    def get_notification_settings(self) -> dict[str, Any]:
        with self._db() as conn:
            self.ensure_notification_settings(conn)
            row = conn.execute("SELECT * FROM notification_settings WHERE id = 1").fetchone()
        payload = dict(row)
        payload["enabled"] = bool(payload["enabled"])
        payload["alert_enabled"] = bool(payload["alert_enabled"])
        payload["summary_enabled"] = bool(payload["summary_enabled"])
        payload["summary_times"] = normalize_summary_times(payload["summary_times"])
        payload["summary_times_list"] = [item for item in payload["summary_times"].split(",") if item]
        return payload

    def update_notification_settings(self, payload: Any) -> None:
        normalized_times = normalize_summary_times(payload.summary_times)
        if payload.enabled and not payload.target.strip():
            raise ValueError("启用通知前必须填写通知目标 target。")
        if payload.summary_enabled and not normalized_times:
            raise ValueError("启用定时简报前必须至少配置一个推送时间，例如 09:00,12:00。")
        with self._db() as conn:
            self.ensure_notification_settings(conn)
            conn.execute(
                """
                UPDATE notification_settings
                SET enabled = ?, channel = ?, account = ?, target = ?, alert_enabled = ?,
                    alert_batch_size = ?, summary_enabled = ?, summary_times = ?,
                    summary_account_limit = ?, summary_plan_limit = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    1 if payload.enabled else 0,
                    payload.channel.strip(),
                    payload.account.strip(),
                    payload.target.strip(),
                    1 if payload.alert_enabled else 0,
                    payload.alert_batch_size,
                    1 if payload.summary_enabled else 0,
                    normalized_times,
                    payload.summary_account_limit,
                    payload.summary_plan_limit,
                    self._now_text(),
                ),
            )

    def list_alert_rules(self) -> list[dict[str, Any]]:
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM alert_rules ORDER BY entity_type ASC, metric ASC, id DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def create_alert_rule(self, payload: Any) -> None:
        validate_alert_rule_payload(payload)
        now = self._now_text()
        with self._db() as conn:
            conn.execute(
                """
                INSERT INTO alert_rules (
                    entity_type, metric, operator, threshold, min_spend, cooldown_minutes,
                    enabled, target_id, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.entity_type,
                    payload.metric,
                    payload.operator,
                    payload.threshold,
                    payload.min_spend,
                    payload.cooldown_minutes,
                    1 if payload.enabled else 0,
                    payload.target_id.strip(),
                    payload.note.strip(),
                    now,
                    now,
                ),
            )

    def update_alert_rule(self, rule_id: int, payload: Any) -> None:
        validate_alert_rule_payload(payload)
        with self._db() as conn:
            conn.execute(
                """
                UPDATE alert_rules
                SET entity_type = ?, metric = ?, operator = ?, threshold = ?, min_spend = ?,
                    cooldown_minutes = ?, enabled = ?, target_id = ?, note = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.entity_type,
                    payload.metric,
                    payload.operator,
                    payload.threshold,
                    payload.min_spend,
                    payload.cooldown_minutes,
                    1 if payload.enabled else 0,
                    payload.target_id.strip(),
                    payload.note.strip(),
                    self._now_text(),
                    rule_id,
                ),
            )

    def delete_alert_rule(self, rule_id: int) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM alert_events WHERE rule_id = ?", (rule_id,))
            conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))

    def alert_events(self, limit: int = 80) -> list[dict[str, Any]]:
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT * FROM alert_events
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
