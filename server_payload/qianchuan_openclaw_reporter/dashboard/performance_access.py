from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable


class PerformanceAccess:
    def __init__(
        self,
        db_factory: Callable[[], Any],
        rankings_bundle: Callable[
            [dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]],
            tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]],
        ],
        scoped_summary: Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]],
        decorate_plan_item: Callable[[Any], dict[str, Any]],
        apply_employee_attribution: Callable[[list[dict[str, Any]], list[dict[str, Any]]], list[dict[str, Any]]],
        current_customer_center_id: Callable[[], str],
        snapshot_account_balances: Callable[[Any, str], list[dict[str, Any]]],
        snapshot_shared_wallets: Callable[[Any, str], list[dict[str, Any]]],
        snapshot_wallet_relations: Callable[[Any, str], list[dict[str, Any]]],
        apply_plan_delivery_type_metadata: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._db = db_factory
        self._rankings_bundle = rankings_bundle
        self._scoped_summary = scoped_summary
        self._decorate_plan_item = decorate_plan_item
        self._apply_employee_attribution = apply_employee_attribution
        self._current_customer_center_id = current_customer_center_id
        self._snapshot_account_balances = snapshot_account_balances
        self._snapshot_shared_wallets = snapshot_shared_wallets
        self._snapshot_wallet_relations = snapshot_wallet_relations
        self._apply_plan_delivery_type_metadata = apply_plan_delivery_type_metadata

    @staticmethod
    def _plan_ratio(numerator: Any, denominator: Any) -> float:
        denominator_value = float(denominator or 0.0)
        if denominator_value <= 0:
            return 0.0
        return round(float(numerator or 0.0) / denominator_value, 2)

    @staticmethod
    def _plan_percent(numerator: Any, denominator: Any) -> float:
        denominator_value = float(denominator or 0.0)
        if denominator_value <= 0:
            return 0.0
        return round(float(numerator or 0.0) / denominator_value * 100.0, 2)

    def apply_account_scope(
        self,
        payload: dict[str, Any],
        allowed_advertiser_ids: set[int] | None,
        *,
        section: str = "all",
    ) -> dict[str, Any]:
        if allowed_advertiser_ids is None:
            return payload
        normalized_section = str(section or "all").strip().lower()
        allowed = {int(item) for item in allowed_advertiser_ids}
        accounts = [dict(item) for item in payload.get("accounts", []) if int(item.get("advertiser_id", 0) or 0) in allowed]
        plans = [dict(item) for item in payload.get("plans", []) if int(item.get("advertiser_id", 0) or 0) in allowed]
        account_balances = [
            dict(item) for item in payload.get("accountBalances", []) if int(item.get("advertiser_id", 0) or 0) in allowed
        ]
        wallet_relations = [
            dict(item) for item in payload.get("walletRelations", []) if int(item.get("advertiser_id", 0) or 0) in allowed
        ]
        allowed_wallet_ids = {
            str(item.get("main_wallet_id") or "") for item in wallet_relations if str(item.get("main_wallet_id") or "")
        }
        shared_wallets = [
            dict(item) for item in payload.get("sharedWallets", []) if str(item.get("main_wallet_id") or "") in allowed_wallet_ids
        ]
        next_payload = dict(payload)
        next_payload["accounts"] = accounts
        next_payload["plans"] = plans
        next_payload["accountBalances"] = account_balances
        next_payload["walletRelations"] = wallet_relations
        next_payload["sharedWallets"] = shared_wallets
        if normalized_section in {"all", "breakdown"}:
            next_payload["summary"], next_payload["products"], next_payload["employees"], next_payload["operators"] = self._rankings_bundle(
                self._scoped_summary(accounts, plans),
                accounts,
                plans,
            )
        else:
            next_payload["summary"] = self._scoped_summary(accounts, plans)
            next_payload["products"] = []
            next_payload["employees"] = []
            next_payload["operators"] = []
        return next_payload

    @staticmethod
    def window_day_keys(start_dt: datetime, end_dt: datetime) -> list[str]:
        start_day = start_dt.date()
        end_day = end_dt.date()
        day_keys: list[str] = []
        cursor = start_day
        while cursor <= end_day:
            day_keys.append(cursor.strftime("%Y-%m-%d"))
            cursor += timedelta(days=1)
        return day_keys

    @staticmethod
    def summary_row_biz_date(row: dict[str, Any]) -> str:
        biz_date = str(row.get("biz_date") or "").strip()
        if len(biz_date) >= 10:
            return biz_date[:10]

        window_start = str(row.get("window_start") or "").strip()
        window_end = str(row.get("window_end") or "").strip()
        if len(window_start) >= 10 and len(window_end) >= 10 and window_start[:10] == window_end[:10]:
            return window_end[:10]

        snapshot_time = str(row.get("snapshot_time") or "").strip()
        if len(snapshot_time) >= 10:
            return snapshot_time[:10]
        return ""

    @classmethod
    def summary_window_signature(cls, rows: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
        return {
            (
                str(row.get("customer_center_id") or "").strip(),
                cls.summary_row_biz_date(row),
                str(row.get("snapshot_time") or "").strip(),
            )
            for row in rows
            if cls.summary_row_biz_date(row) and str(row.get("snapshot_time") or "").strip()
        }

    @staticmethod
    def is_missing_daily_read_model_error(exc: Exception) -> bool:
        message = str(exc or "").strip().lower()
        if not message:
            return False
        if not any(table in message for table in ("summary_daily", "account_daily", "plan_daily")):
            return False
        return (
            "undefinedtable" in message
            or "does not exist" in message
            or "no such table" in message
            or "relation" in message
        )

    def latest_summary_snapshots_for_window(
        self,
        conn: Any,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[dict[str, Any]]:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        rows = conn.execute(
            """
            SELECT *
            FROM summary_snapshots
            WHERE customer_center_id = ?
              AND snapshot_time >= ?
              AND snapshot_time <= ?
            ORDER BY snapshot_time DESC
            """,
            (
                customer_center_id,
                start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        ).fetchall()
        selected: list[dict[str, Any]] = []
        seen_dates: set[str] = set()
        for row in rows:
            item = dict(row)
            day_key = str(item.get("snapshot_time") or "")[:10]
            if not day_key or day_key in seen_dates:
                continue
            selected.append(item)
            seen_dates.add(day_key)
        selected.sort(key=lambda item: str(item.get("snapshot_time") or ""))
        return selected

    def latest_summary_daily_for_window(
        self,
        conn: Any,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[dict[str, Any]]:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM summary_daily
                WHERE customer_center_id = ?
                  AND biz_date >= ?
                  AND biz_date <= ?
                ORDER BY biz_date ASC
                """,
                (
                    customer_center_id,
                    start_dt.strftime("%Y-%m-%d"),
                    end_dt.strftime("%Y-%m-%d"),
                ),
            ).fetchall()
        except Exception as exc:  # noqa: BLE001
            if self.is_missing_daily_read_model_error(exc):
                return []
            raise
        return [dict(row) for row in rows]

    def missing_summary_days(self, conn: Any, start_dt: datetime, end_dt: datetime) -> list[datetime]:
        start_day = start_dt.date()
        end_day = end_dt.date()
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        existing_days: set[str] = set()
        daily_rows = conn.execute(
            """
            SELECT DISTINCT biz_date AS day_key
            FROM summary_daily
            WHERE customer_center_id = ?
              AND biz_date >= ?
              AND biz_date <= ?
            """,
            (
                customer_center_id,
                start_dt.strftime("%Y-%m-%d"),
                end_dt.strftime("%Y-%m-%d"),
            ),
        ).fetchall()
        existing_days.update(
            str(row["day_key"] or "").strip()
            for row in daily_rows
            if str(row["day_key"] or "").strip()
        )
        current_rows = conn.execute(
            """
            SELECT DISTINCT substr(snapshot_time, 1, 10) AS day_key
            FROM summary_current
            WHERE customer_center_id = ?
              AND snapshot_time >= ?
              AND snapshot_time <= ?
            """,
            (
                customer_center_id,
                start_dt.strftime("%Y-%m-%d 00:00:00"),
                end_dt.strftime("%Y-%m-%d 23:59:59"),
            ),
        ).fetchall()
        existing_days.update(
            str(row["day_key"] or "").strip()
            for row in current_rows
            if str(row["day_key"] or "").strip()
        )
        missing: list[datetime] = []
        cursor = start_day
        while cursor <= end_day:
            if cursor.strftime("%Y-%m-%d") not in existing_days:
                missing.append(datetime(cursor.year, cursor.month, cursor.day))
            cursor += timedelta(days=1)
        return missing

    def aggregate_account_snapshots(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[int, dict[str, Any]] = {}
        for row in rows:
            advertiser_id = int(row.get("advertiser_id", 0) or 0)
            if not advertiser_id:
                continue
            group = groups.get(advertiser_id)
            if group is None:
                group = dict(row)
                group["stat_cost"] = 0.0
                group["pay_amount"] = 0.0
                group["total_pay_amount"] = 0.0
                group["settled_pay_amount"] = 0.0
                group["order_count"] = 0
                group["settled_order_count"] = 0
                group["refund_amount_1h"] = 0.0
                group["plan_count"] = 0
                group["_all_ok"] = True
                group["_any_fallback"] = False
                group["_first_error"] = ""
                groups[advertiser_id] = group
            group["stat_cost"] = round(
                float(group.get("stat_cost", 0.0) or 0.0) + float(row.get("stat_cost", 0.0) or 0.0),
                2,
            )
            group["pay_amount"] = round(
                float(group.get("pay_amount", 0.0) or 0.0) + float(row.get("pay_amount", 0.0) or 0.0),
                2,
            )
            group["total_pay_amount"] = round(
                float(group.get("total_pay_amount", 0.0) or 0.0) + float(row.get("total_pay_amount", 0.0) or 0.0),
                2,
            )
            group["settled_pay_amount"] = round(
                float(group.get("settled_pay_amount", 0.0) or 0.0) + float(row.get("settled_pay_amount", 0.0) or 0.0),
                2,
            )
            group["order_count"] = int(group.get("order_count", 0) or 0) + int(float(row.get("order_count", 0.0) or 0.0))
            group["settled_order_count"] = int(group.get("settled_order_count", 0) or 0) + int(
                float(row.get("settled_order_count", 0.0) or 0.0)
            )
            group["refund_amount_1h"] = round(
                float(group.get("refund_amount_1h", 0.0) or 0.0) + float(row.get("refund_amount_1h", 0.0) or 0.0),
                2,
            )
            group["plan_count"] = int(group.get("plan_count", 0) or 0) + int(float(row.get("plan_count", 0.0) or 0.0))
            row_ok = bool(row.get("ok", True))
            group["_all_ok"] = bool(group["_all_ok"]) and row_ok
            row_error = str(row.get("error") or "").strip()
            if row_error.startswith("fallback:"):
                group["_any_fallback"] = True
            elif row_error and not group["_first_error"]:
                group["_first_error"] = row_error

        items: list[dict[str, Any]] = []
        for advertiser_id, group in groups.items():
            stat_cost = round(float(group.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(group.get("pay_amount", 0.0) or 0.0), 2)
            total_pay_amount = round(float(group.get("total_pay_amount", 0.0) or 0.0), 2)
            settled_pay_amount = round(float(group.get("settled_pay_amount", 0.0) or 0.0), 2)
            order_count = int(group.get("order_count", 0) or 0)
            settled_order_count = int(group.get("settled_order_count", 0) or 0)
            refund_amount_1h = round(float(group.get("refund_amount_1h", 0.0) or 0.0), 2)
            plan_count = int(group.get("plan_count", 0) or 0)
            group["advertiser_id"] = advertiser_id
            group["stat_cost"] = stat_cost
            group["pay_amount"] = pay_amount
            group["total_pay_amount"] = total_pay_amount
            group["settled_pay_amount"] = settled_pay_amount
            group["order_count"] = order_count
            group["settled_order_count"] = settled_order_count
            group["refund_amount_1h"] = refund_amount_1h
            group["plan_count"] = plan_count
            group["roi"] = round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0
            group["settled_roi"] = self._plan_ratio(settled_pay_amount, stat_cost)
            group["pay_order_cost"] = self._plan_ratio(stat_cost, order_count)
            group["settled_amount_rate"] = self._plan_percent(settled_pay_amount, total_pay_amount)
            group["refund_rate_1h"] = self._plan_percent(refund_amount_1h, total_pay_amount)
            group["ok"] = bool(group.pop("_all_ok", True))
            any_fallback = bool(group.pop("_any_fallback", False))
            first_error = str(group.pop("_first_error", "") or "").strip()
            group["error"] = "fallback: plan rollup" if any_fallback else first_error
            items.append(group)
        items.sort(key=lambda item: (-float(item.get("stat_cost", 0.0) or 0.0), int(item.get("advertiser_id", 0) or 0)))
        return items

    def aggregate_plan_snapshots(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[int, dict[str, Any]] = {}
        for row in rows:
            ad_id = int(row.get("ad_id", 0) or 0)
            if not ad_id:
                continue
            group = groups.get(ad_id)
            if group is None:
                group = dict(row)
                group["stat_cost"] = 0.0
                group["pay_amount"] = 0.0
                group["order_count"] = 0
                group["total_pay_amount"] = 0.0
                group["settled_pay_amount"] = 0.0
                group["settled_order_count"] = 0
                group["refund_amount_1h"] = 0.0
                groups[ad_id] = group
            if str(row.get("plan_delivery_type") or "").strip().upper() == "CUBIC":
                group["plan_delivery_type"] = "CUBIC"
            group["stat_cost"] = round(
                float(group.get("stat_cost", 0.0) or 0.0) + float(row.get("stat_cost", 0.0) or 0.0),
                2,
            )
            group["pay_amount"] = round(
                float(group.get("pay_amount", 0.0) or 0.0) + float(row.get("pay_amount", 0.0) or 0.0),
                2,
            )
            group["order_count"] = int(group.get("order_count", 0) or 0) + int(float(row.get("order_count", 0.0) or 0.0))
            group["total_pay_amount"] = round(
                float(group.get("total_pay_amount", 0.0) or 0.0) + float(row.get("total_pay_amount", 0.0) or 0.0),
                2,
            )
            group["settled_pay_amount"] = round(
                float(group.get("settled_pay_amount", 0.0) or 0.0) + float(row.get("settled_pay_amount", 0.0) or 0.0),
                2,
            )
            group["settled_order_count"] = int(group.get("settled_order_count", 0) or 0) + int(
                float(row.get("settled_order_count", 0.0) or 0.0)
            )
            group["refund_amount_1h"] = round(
                float(group.get("refund_amount_1h", 0.0) or 0.0) + float(row.get("refund_amount_1h", 0.0) or 0.0),
                2,
            )

        items: list[dict[str, Any]] = []
        for ad_id, group in groups.items():
            stat_cost = round(float(group.get("stat_cost", 0.0) or 0.0), 2)
            pay_amount = round(float(group.get("pay_amount", 0.0) or 0.0), 2)
            order_count = int(group.get("order_count", 0) or 0)
            total_pay_amount = round(float(group.get("total_pay_amount", 0.0) or 0.0), 2)
            settled_pay_amount = round(float(group.get("settled_pay_amount", 0.0) or 0.0), 2)
            settled_order_count = int(group.get("settled_order_count", 0) or 0)
            refund_amount_1h = round(float(group.get("refund_amount_1h", 0.0) or 0.0), 2)
            group["ad_id"] = ad_id
            group["stat_cost"] = stat_cost
            group["pay_amount"] = pay_amount
            group["order_count"] = order_count
            group["total_pay_amount"] = total_pay_amount
            group["settled_pay_amount"] = settled_pay_amount
            group["settled_order_count"] = settled_order_count
            group["refund_amount_1h"] = refund_amount_1h
            group["roi"] = self._plan_ratio(pay_amount, stat_cost)
            group["settled_roi"] = self._plan_ratio(settled_pay_amount, stat_cost)
            group["pay_order_cost"] = self._plan_ratio(stat_cost, order_count)
            group["settled_amount_rate"] = self._plan_percent(settled_pay_amount, total_pay_amount)
            group["refund_rate_1h"] = self._plan_percent(refund_amount_1h, total_pay_amount)
            items.append(group)
        items.sort(
            key=lambda item: (
                -int(float(item.get("order_count", 0.0) or 0.0)),
                -float(item.get("pay_amount", 0.0) or 0.0),
                -float(item.get("roi", 0.0) or 0.0),
                -float(item.get("stat_cost", 0.0) or 0.0),
                int(item.get("ad_id", 0) or 0),
            )
        )
        return items

    @staticmethod
    def _empty_performance_snapshot(start_dt: datetime, end_dt: datetime) -> dict[str, Any]:
        return {
            "snapshot_time": "",
            "window_start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "window_end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "account_count": 0,
                "active_account_count": 0,
                "plan_count": 0,
                "active_plan_count": 0,
                "stat_cost": 0.0,
                "pay_amount": 0.0,
                "order_count": 0,
                "roi": 0.0,
                "account_failures": 0,
                "plan_failures": 0,
                "wallet_count": 0,
                "balance_failures": 0,
            },
            "accounts": [],
            "plans": [],
            "accountBalances": [],
            "sharedWallets": [],
            "walletRelations": [],
            "errors": {"accounts": [], "plans": [], "balances": []},
            "snapshot_count": 0,
        }

    def upsert_daily_read_models(
        self,
        conn: Any,
        summary_rows: list[dict[str, Any]],
        account_rows: list[dict[str, Any]],
        plan_rows: list[dict[str, Any]],
    ) -> None:
        try:
            normalized_summary_rows: list[dict[str, Any]] = []
            snapshot_day_map: dict[tuple[str, str], str] = {}
            for raw_row in summary_rows:
                row = dict(raw_row)
                customer_center_id = str(row.get("customer_center_id") or "").strip()
                snapshot_time = str(row.get("snapshot_time") or "").strip()
                biz_date = self.summary_row_biz_date(row)
                if not customer_center_id or not snapshot_time or not biz_date:
                    continue
                row["biz_date"] = biz_date
                normalized_summary_rows.append(row)
                snapshot_day_map[(customer_center_id, snapshot_time)] = biz_date
            if not normalized_summary_rows:
                return

            account_rows_by_day: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            for raw_row in account_rows:
                row = dict(raw_row)
                customer_center_id = str(row.get("customer_center_id") or "").strip()
                snapshot_time = str(row.get("snapshot_time") or "").strip()
                biz_date = snapshot_day_map.get((customer_center_id, snapshot_time), "")
                if not biz_date:
                    continue
                account_rows_by_day.setdefault((customer_center_id, biz_date, snapshot_time), []).append(row)

            plan_rows_by_day: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            for raw_row in plan_rows:
                row = dict(raw_row)
                customer_center_id = str(row.get("customer_center_id") or "").strip()
                snapshot_time = str(row.get("snapshot_time") or "").strip()
                biz_date = snapshot_day_map.get((customer_center_id, snapshot_time), "")
                if not biz_date:
                    continue
                plan_rows_by_day.setdefault((customer_center_id, biz_date, snapshot_time), []).append(row)

            for row in normalized_summary_rows:
                customer_center_id = str(row.get("customer_center_id") or "").strip()
                biz_date = str(row.get("biz_date") or "").strip()
                snapshot_time = str(row.get("snapshot_time") or "").strip()
                if not customer_center_id or not biz_date or not snapshot_time:
                    continue

                conn.execute(
                    """
                    INSERT INTO summary_daily (
                        customer_center_id, biz_date, snapshot_time, account_count, active_account_count,
                        plan_count, active_plan_count, stat_cost, pay_amount, order_count, roi,
                        account_failures, plan_failures
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (customer_center_id, biz_date) DO UPDATE SET
                        snapshot_time = excluded.snapshot_time,
                        account_count = excluded.account_count,
                        active_account_count = excluded.active_account_count,
                        plan_count = excluded.plan_count,
                        active_plan_count = excluded.active_plan_count,
                        stat_cost = excluded.stat_cost,
                        pay_amount = excluded.pay_amount,
                        order_count = excluded.order_count,
                        roi = excluded.roi,
                        account_failures = excluded.account_failures,
                        plan_failures = excluded.plan_failures
                    """,
                    (
                        customer_center_id,
                        biz_date,
                        snapshot_time,
                        int(row.get("account_count", 0) or 0),
                        int(row.get("active_account_count", 0) or 0),
                        int(row.get("plan_count", 0) or 0),
                        int(row.get("active_plan_count", 0) or 0),
                        float(row.get("stat_cost", 0.0) or 0.0),
                        float(row.get("pay_amount", 0.0) or 0.0),
                        int(row.get("order_count", 0) or 0),
                        float(row.get("roi", 0.0) or 0.0),
                        int(row.get("account_failures", 0) or 0),
                        int(row.get("plan_failures", 0) or 0),
                    ),
                )

                conn.execute(
                    "DELETE FROM account_daily WHERE customer_center_id = ? AND biz_date = ?",
                    (customer_center_id, biz_date),
                )
                day_account_rows = account_rows_by_day.get((customer_center_id, biz_date, snapshot_time), [])
                if day_account_rows:
                    conn.executemany(
                        """
                        INSERT INTO account_daily (
                            customer_center_id, biz_date, snapshot_time, advertiser_id, advertiser_name,
                            stat_cost, roi, order_count, pay_amount, total_pay_amount, settled_pay_amount,
                            settled_roi, settled_order_count, pay_order_cost, settled_amount_rate,
                            refund_rate_1h, refund_amount_1h, plan_count, ok, error
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                customer_center_id,
                                biz_date,
                                snapshot_time,
                                int(item.get("advertiser_id", 0) or 0),
                                str(item.get("advertiser_name") or ""),
                                float(item.get("stat_cost", 0.0) or 0.0),
                                float(item.get("roi", 0.0) or 0.0),
                                int(float(item.get("order_count", 0.0) or 0.0)),
                                float(item.get("pay_amount", 0.0) or 0.0),
                                float(item.get("total_pay_amount", 0.0) or 0.0),
                                float(item.get("settled_pay_amount", 0.0) or 0.0),
                                float(item.get("settled_roi", 0.0) or 0.0),
                                int(float(item.get("settled_order_count", 0.0) or 0.0)),
                                float(item.get("pay_order_cost", 0.0) or 0.0),
                                float(item.get("settled_amount_rate", 0.0) or 0.0),
                                float(item.get("refund_rate_1h", 0.0) or 0.0),
                                float(item.get("refund_amount_1h", 0.0) or 0.0),
                                int(float(item.get("plan_count", 0.0) or 0.0)),
                                1 if bool(item.get("ok", True)) else 0,
                                str(item.get("error") or ""),
                            )
                            for item in day_account_rows
                        ],
                    )

                conn.execute(
                    "DELETE FROM plan_daily WHERE customer_center_id = ? AND biz_date = ?",
                    (customer_center_id, biz_date),
                )
                day_plan_rows = plan_rows_by_day.get((customer_center_id, biz_date, snapshot_time), [])
                if day_plan_rows:
                    conn.executemany(
                        """
                        INSERT INTO plan_daily (
                            customer_center_id, biz_date, snapshot_time, advertiser_id, advertiser_name,
                            ad_id, ad_name, product_id, product_name, anchor_name, marketing_goal,
                            plan_source, plan_delivery_type, status, opt_status, roi_goal, stat_cost,
                            roi, order_count, pay_amount, total_pay_amount, settled_pay_amount,
                            settled_roi, settled_order_count, pay_order_cost, settled_amount_rate,
                            refund_rate_1h, refund_amount_1h
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                customer_center_id,
                                biz_date,
                                snapshot_time,
                                int(item.get("advertiser_id", 0) or 0),
                                str(item.get("advertiser_name") or ""),
                                int(item.get("ad_id", 0) or 0),
                                str(item.get("ad_name") or ""),
                                str(item.get("product_id") or ""),
                                str(item.get("product_name") or ""),
                                str(item.get("anchor_name") or ""),
                                str(item.get("marketing_goal") or ""),
                                str(item.get("plan_source") or "UNI_PROMOTION"),
                                str(item.get("plan_delivery_type") or "GLOBAL"),
                                str(item.get("status") or ""),
                                str(item.get("opt_status") or ""),
                                float(item.get("roi_goal", 0.0) or 0.0),
                                float(item.get("stat_cost", 0.0) or 0.0),
                                float(item.get("roi", 0.0) or 0.0),
                                int(float(item.get("order_count", 0.0) or 0.0)),
                                float(item.get("pay_amount", 0.0) or 0.0),
                                float(item.get("total_pay_amount", 0.0) or 0.0),
                                float(item.get("settled_pay_amount", 0.0) or 0.0),
                                float(item.get("settled_roi", 0.0) or 0.0),
                                int(float(item.get("settled_order_count", 0.0) or 0.0)),
                                float(item.get("pay_order_cost", 0.0) or 0.0),
                                float(item.get("settled_amount_rate", 0.0) or 0.0),
                                float(item.get("refund_rate_1h", 0.0) or 0.0),
                                float(item.get("refund_amount_1h", 0.0) or 0.0),
                            )
                            for item in day_plan_rows
                        ],
                    )
        except Exception as exc:  # noqa: BLE001
            if self.is_missing_daily_read_model_error(exc):
                return
            raise

    def upsert_current_read_models(
        self,
        conn: Any,
        summary_row: dict[str, Any],
        account_rows: list[dict[str, Any]],
        plan_rows: list[dict[str, Any]],
    ) -> None:
        row = dict(summary_row or {})
        customer_center_id = str(row.get("customer_center_id") or "").strip()
        snapshot_time = str(row.get("snapshot_time") or "").strip()
        if not customer_center_id or not snapshot_time:
            return
        conn.execute(
            """
            INSERT INTO summary_current (
                customer_center_id, snapshot_time, window_start, window_end, account_count, active_account_count,
                plan_count, active_plan_count, stat_cost, pay_amount, order_count, roi, account_failures, plan_failures
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (customer_center_id) DO UPDATE SET
                snapshot_time = excluded.snapshot_time,
                window_start = excluded.window_start,
                window_end = excluded.window_end,
                account_count = excluded.account_count,
                active_account_count = excluded.active_account_count,
                plan_count = excluded.plan_count,
                active_plan_count = excluded.active_plan_count,
                stat_cost = excluded.stat_cost,
                pay_amount = excluded.pay_amount,
                order_count = excluded.order_count,
                roi = excluded.roi,
                account_failures = excluded.account_failures,
                plan_failures = excluded.plan_failures
            """,
            (
                customer_center_id,
                snapshot_time,
                str(row.get("window_start") or ""),
                str(row.get("window_end") or ""),
                int(row.get("account_count", 0) or 0),
                int(row.get("active_account_count", 0) or 0),
                int(row.get("plan_count", 0) or 0),
                int(row.get("active_plan_count", 0) or 0),
                float(row.get("stat_cost", 0.0) or 0.0),
                float(row.get("pay_amount", 0.0) or 0.0),
                int(row.get("order_count", 0) or 0),
                float(row.get("roi", 0.0) or 0.0),
                int(row.get("account_failures", 0) or 0),
                int(row.get("plan_failures", 0) or 0),
            ),
        )
        conn.execute("DELETE FROM account_current WHERE customer_center_id = ?", (customer_center_id,))
        if account_rows:
            conn.executemany(
                """
                INSERT INTO account_current (
                    customer_center_id, snapshot_time, advertiser_id, advertiser_name, stat_cost, roi, order_count,
                    pay_amount, total_pay_amount, settled_pay_amount, settled_roi, settled_order_count, pay_order_cost,
                    settled_amount_rate, refund_rate_1h, refund_amount_1h, plan_count, ok, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        customer_center_id,
                        snapshot_time,
                        int(item.get("advertiser_id", 0) or 0),
                        str(item.get("advertiser_name") or ""),
                        float(item.get("stat_cost", 0.0) or 0.0),
                        float(item.get("roi", 0.0) or 0.0),
                        int(float(item.get("order_count", 0.0) or 0.0)),
                        float(item.get("pay_amount", 0.0) or 0.0),
                        float(item.get("total_pay_amount", 0.0) or 0.0),
                        float(item.get("settled_pay_amount", 0.0) or 0.0),
                        float(item.get("settled_roi", 0.0) or 0.0),
                        int(float(item.get("settled_order_count", 0.0) or 0.0)),
                        float(item.get("pay_order_cost", 0.0) or 0.0),
                        float(item.get("settled_amount_rate", 0.0) or 0.0),
                        float(item.get("refund_rate_1h", 0.0) or 0.0),
                        float(item.get("refund_amount_1h", 0.0) or 0.0),
                        int(float(item.get("plan_count", 0.0) or 0.0)),
                        1 if bool(item.get("ok", True)) else 0,
                        str(item.get("error") or ""),
                    )
                    for item in account_rows
                ],
            )
        conn.execute("DELETE FROM plan_current WHERE customer_center_id = ?", (customer_center_id,))
        if plan_rows:
            conn.executemany(
                """
                INSERT INTO plan_current (
                    customer_center_id, snapshot_time, advertiser_id, advertiser_name, ad_id, ad_name,
                    product_id, product_name, anchor_name, marketing_goal, plan_source, plan_delivery_type,
                    status, opt_status, roi_goal, stat_cost, roi, order_count, pay_amount, total_pay_amount,
                    settled_pay_amount, settled_roi, settled_order_count, pay_order_cost, settled_amount_rate,
                    refund_rate_1h, refund_amount_1h
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        customer_center_id,
                        snapshot_time,
                        int(item.get("advertiser_id", 0) or 0),
                        str(item.get("advertiser_name") or ""),
                        int(item.get("ad_id", 0) or 0),
                        str(item.get("ad_name") or ""),
                        str(item.get("product_id") or ""),
                        str(item.get("product_name") or ""),
                        str(item.get("anchor_name") or ""),
                        str(item.get("marketing_goal") or ""),
                        str(item.get("plan_source") or "UNI_PROMOTION"),
                        str(item.get("plan_delivery_type") or "GLOBAL"),
                        str(item.get("status") or ""),
                        str(item.get("opt_status") or ""),
                        float(item.get("roi_goal", 0.0) or 0.0),
                        float(item.get("stat_cost", 0.0) or 0.0),
                        float(item.get("roi", 0.0) or 0.0),
                        int(float(item.get("order_count", 0.0) or 0.0)),
                        float(item.get("pay_amount", 0.0) or 0.0),
                        float(item.get("total_pay_amount", 0.0) or 0.0),
                        float(item.get("settled_pay_amount", 0.0) or 0.0),
                        float(item.get("settled_roi", 0.0) or 0.0),
                        int(float(item.get("settled_order_count", 0.0) or 0.0)),
                        float(item.get("pay_order_cost", 0.0) or 0.0),
                        float(item.get("settled_amount_rate", 0.0) or 0.0),
                        float(item.get("refund_rate_1h", 0.0) or 0.0),
                        float(item.get("refund_amount_1h", 0.0) or 0.0),
                    )
                    for item in plan_rows
                ],
            )

    def _current_rows_for_customer_center(self, conn: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        summary = conn.execute(
            "SELECT * FROM summary_current WHERE customer_center_id = ? LIMIT 1",
            (customer_center_id,),
        ).fetchone()
        if not summary:
            return None, [], []
        account_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM account_current
                WHERE customer_center_id = ?
                ORDER BY stat_cost DESC, advertiser_id ASC
                """,
                (customer_center_id,),
            ).fetchall()
        ]
        plan_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM plan_current
                WHERE customer_center_id = ?
                ORDER BY order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, ad_id ASC
                """,
                (customer_center_id,),
            ).fetchall()
        ]
        if callable(self._apply_plan_delivery_type_metadata):
            plan_rows = self._apply_plan_delivery_type_metadata(conn, plan_rows)
        return dict(summary), account_rows, plan_rows

    @staticmethod
    def _summary_row_matches_day(row: dict[str, Any] | None, day_key: str) -> bool:
        if not row:
            return False
        summary_day = str(row.get("snapshot_time") or "").strip()[:10]
        if summary_day == day_key:
            return True
        window_start = str(row.get("window_start") or "").strip()[:10]
        window_end = str(row.get("window_end") or "").strip()[:10]
        return bool(window_start and window_start == day_key and window_end == day_key)

    def _build_payload_from_summary_rows(
        self,
        conn: Any,
        start_dt: datetime,
        end_dt: datetime,
        *,
        summary_rows: list[dict[str, Any]],
        account_rows: list[dict[str, Any]],
        plan_rows: list[dict[str, Any]],
        latest_snapshot_time: str,
    ) -> dict[str, Any]:
        account_balance_items = self._snapshot_account_balances(conn, latest_snapshot_time) if latest_snapshot_time else []
        shared_wallet_items = self._snapshot_shared_wallets(conn, latest_snapshot_time) if latest_snapshot_time else []
        wallet_relation_items = self._snapshot_wallet_relations(conn, latest_snapshot_time) if latest_snapshot_time else []
        return self._build_performance_snapshot_payload(
            start_dt,
            end_dt,
            latest_snapshot_time=latest_snapshot_time,
            snapshot_count=len(summary_rows),
            account_rows=account_rows,
            plan_rows=plan_rows,
            account_balance_items=account_balance_items,
            shared_wallet_items=shared_wallet_items,
            wallet_relation_items=wallet_relation_items,
        )

    def _performance_snapshot_from_current_rows(
        self,
        conn: Any,
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict[str, Any]:
        summary_row, account_rows, plan_rows = self._current_rows_for_customer_center(conn)
        if not summary_row:
            return self._empty_performance_snapshot(start_dt, end_dt)
        latest_snapshot_time = str(summary_row.get("snapshot_time") or "").strip()
        return self._build_payload_from_summary_rows(
            conn,
            start_dt,
            end_dt,
            summary_rows=[summary_row],
            account_rows=account_rows,
            plan_rows=plan_rows,
            latest_snapshot_time=latest_snapshot_time,
        )

    def _performance_snapshot_from_daily_and_current_rows(
        self,
        conn: Any,
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict[str, Any]:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        summary_rows = self.latest_summary_daily_for_window(conn, start_dt, end_dt)
        account_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM account_daily
                WHERE customer_center_id = ?
                  AND biz_date >= ?
                  AND biz_date <= ?
                ORDER BY biz_date DESC, stat_cost DESC, advertiser_id ASC
                """,
                (
                    customer_center_id,
                    start_dt.strftime("%Y-%m-%d"),
                    end_dt.strftime("%Y-%m-%d"),
                ),
            ).fetchall()
        ]
        plan_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM plan_daily
                WHERE customer_center_id = ?
                  AND biz_date >= ?
                  AND biz_date <= ?
                ORDER BY biz_date DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, ad_id ASC
                """,
                (
                    customer_center_id,
                    start_dt.strftime("%Y-%m-%d"),
                    end_dt.strftime("%Y-%m-%d"),
                ),
            ).fetchall()
        ]
        current_summary, current_accounts, current_plans = self._current_rows_for_customer_center(conn)
        if current_summary:
            summary_rows.append(current_summary)
            account_rows.extend(current_accounts)
            plan_rows.extend(current_plans)
        if callable(self._apply_plan_delivery_type_metadata):
            plan_rows = self._apply_plan_delivery_type_metadata(conn, plan_rows)
        latest_snapshot_time = max((str(item.get("snapshot_time") or "") for item in summary_rows), default="")
        if not summary_rows:
            return self._empty_performance_snapshot(start_dt, end_dt)
        return self._build_payload_from_summary_rows(
            conn,
            start_dt,
            end_dt,
            summary_rows=summary_rows,
            account_rows=account_rows,
            plan_rows=plan_rows,
            latest_snapshot_time=latest_snapshot_time,
        )

    def _legacy_performance_snapshot_from_snapshots(
        self,
        conn: Any,
        start_dt: datetime,
        end_dt: datetime,
        *,
        prefer_daily: bool = False,
    ) -> dict[str, Any]:
        snapshots = self.latest_summary_snapshots_for_window(conn, start_dt, end_dt)
        if not snapshots:
            return self._empty_performance_snapshot(start_dt, end_dt)

        if prefer_daily:
            daily_summaries = self.latest_summary_daily_for_window(conn, start_dt, end_dt)
            if self.summary_window_signature(daily_summaries) == self.summary_window_signature(snapshots):
                try:
                    return self._performance_snapshot_from_daily_rows(conn, start_dt, end_dt, daily_summaries)
                except Exception as exc:  # noqa: BLE001
                    if not self.is_missing_daily_read_model_error(exc):
                        raise

        snapshot_times = [str(item.get("snapshot_time") or "") for item in snapshots if str(item.get("snapshot_time") or "").strip()]
        placeholders = ",".join("?" for _ in snapshot_times)
        account_rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM account_snapshots
                WHERE customer_center_id = ?
                  AND snapshot_time IN ({placeholders})
                ORDER BY snapshot_time DESC, stat_cost DESC, advertiser_id ASC
                """,
                [str(self._current_customer_center_id() or "").strip(), *snapshot_times],
            ).fetchall()
        ]
        plan_rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM plan_snapshots
                WHERE customer_center_id = ?
                  AND snapshot_time IN ({placeholders})
                ORDER BY snapshot_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, ad_id ASC
                """,
                [str(self._current_customer_center_id() or "").strip(), *snapshot_times],
            ).fetchall()
        ]
        if callable(self._apply_plan_delivery_type_metadata):
            plan_rows = self._apply_plan_delivery_type_metadata(conn, plan_rows)
        latest_snapshot_time = snapshot_times[-1]
        return self._build_payload_from_summary_rows(
            conn,
            start_dt,
            end_dt,
            summary_rows=snapshots,
            account_rows=account_rows,
            plan_rows=plan_rows,
            latest_snapshot_time=latest_snapshot_time,
        )

    def _build_performance_snapshot_payload(
        self,
        start_dt: datetime,
        end_dt: datetime,
        *,
        latest_snapshot_time: str,
        snapshot_count: int,
        account_rows: list[dict[str, Any]],
        plan_rows: list[dict[str, Any]],
        account_balance_items: list[dict[str, Any]],
        shared_wallet_items: list[dict[str, Any]],
        wallet_relation_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        account_items = self.aggregate_account_snapshots(account_rows)
        plan_items = [self._decorate_plan_item(item) for item in self.aggregate_plan_snapshots(plan_rows)]

        total_cost = round(
            sum(float(item.get("stat_cost", 0.0) or 0.0) for item in account_items if bool(item.get("ok", True))),
            2,
        )
        total_pay = round(
            sum(float(item.get("pay_amount", 0.0) or 0.0) for item in account_items if bool(item.get("ok", True))),
            2,
        )
        total_orders = int(
            sum(int(float(item.get("order_count", 0.0) or 0.0)) for item in account_items if bool(item.get("ok", True)))
        )
        active_accounts = sum(
            1 for item in account_items if bool(item.get("ok", True)) and float(item.get("stat_cost", 0.0) or 0.0) > 0
        )
        active_plans = sum(1 for item in plan_items if float(item.get("stat_cost", 0.0) or 0.0) > 0)

        return {
            "snapshot_time": latest_snapshot_time,
            "window_start": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "window_end": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "account_count": len(account_items),
                "active_account_count": active_accounts,
                "plan_count": len(plan_items),
                "active_plan_count": active_plans,
                "stat_cost": total_cost,
                "pay_amount": total_pay,
                "order_count": total_orders,
                "roi": round(total_pay / total_cost, 2) if total_cost > 0 else 0.0,
                "account_failures": sum(1 for item in account_items if not bool(item.get("ok", True))),
                "plan_failures": 0,
                "wallet_count": len(shared_wallet_items),
                "balance_failures": 0,
            },
            "accounts": account_items,
            "plans": plan_items,
            "accountBalances": account_balance_items,
            "sharedWallets": shared_wallet_items,
            "walletRelations": wallet_relation_items,
            "errors": {
                "accounts": [dict(item) for item in account_items if not bool(item.get("ok", True))],
                "plans": [],
                "balances": [],
            },
            "snapshot_count": snapshot_count,
        }

    def _performance_snapshot_from_daily_rows(
        self,
        conn: Any,
        start_dt: datetime,
        end_dt: datetime,
        summary_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        selected_day_snapshots = {
            (
                self.summary_row_biz_date(row),
                str(row.get("snapshot_time") or "").strip(),
            )
            for row in summary_rows
            if self.summary_row_biz_date(row) and str(row.get("snapshot_time") or "").strip()
        }
        account_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM account_daily
                WHERE customer_center_id = ?
                  AND biz_date >= ?
                  AND biz_date <= ?
                ORDER BY biz_date DESC, stat_cost DESC, advertiser_id ASC
                """,
                (
                    customer_center_id,
                    start_dt.strftime("%Y-%m-%d"),
                    end_dt.strftime("%Y-%m-%d"),
                ),
            ).fetchall()
        ]
        account_rows = [
            row
            for row in account_rows
            if (
                str(row.get("biz_date") or "").strip(),
                str(row.get("snapshot_time") or "").strip(),
            )
            in selected_day_snapshots
        ]
        plan_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM plan_daily
                WHERE customer_center_id = ?
                  AND biz_date >= ?
                  AND biz_date <= ?
                ORDER BY biz_date DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, ad_id ASC
                """,
                (
                    customer_center_id,
                    start_dt.strftime("%Y-%m-%d"),
                    end_dt.strftime("%Y-%m-%d"),
                ),
            ).fetchall()
        ]
        plan_rows = [
            row
            for row in plan_rows
            if (
                str(row.get("biz_date") or "").strip(),
                str(row.get("snapshot_time") or "").strip(),
            )
            in selected_day_snapshots
        ]
        if callable(self._apply_plan_delivery_type_metadata):
            plan_rows = self._apply_plan_delivery_type_metadata(conn, plan_rows)

        latest_snapshot_time = max(str(item.get("snapshot_time") or "") for item in summary_rows)
        account_balance_items = self._snapshot_account_balances(conn, latest_snapshot_time)
        shared_wallet_items = self._snapshot_shared_wallets(conn, latest_snapshot_time)
        wallet_relation_items = self._snapshot_wallet_relations(conn, latest_snapshot_time)
        return self._build_performance_snapshot_payload(
            start_dt,
            end_dt,
            latest_snapshot_time=latest_snapshot_time,
            snapshot_count=len(summary_rows),
            account_rows=account_rows,
            plan_rows=plan_rows,
            account_balance_items=account_balance_items,
            shared_wallet_items=shared_wallet_items,
            wallet_relation_items=wallet_relation_items,
        )

    def performance_snapshot_from_db(
        self,
        start_dt: datetime,
        end_dt: datetime,
        *,
        prefer_daily: bool = False,
    ) -> dict[str, Any]:
        with self._db() as conn:
            today_key = datetime.now(start_dt.tzinfo or end_dt.tzinfo).strftime("%Y-%m-%d")
            start_key = start_dt.strftime("%Y-%m-%d")
            end_key = end_dt.strftime("%Y-%m-%d")
            try:
                if start_key == today_key and end_key == today_key:
                    payload = self._performance_snapshot_from_current_rows(conn, start_dt, end_dt)
                    if payload.get("snapshot_time"):
                        return payload
                if end_key < today_key:
                    daily_summaries = self.latest_summary_daily_for_window(conn, start_dt, end_dt)
                    if daily_summaries:
                        return self._performance_snapshot_from_daily_rows(conn, start_dt, end_dt, daily_summaries)
                    if start_key == end_key:
                        current_summary, current_accounts, current_plans = self._current_rows_for_customer_center(conn)
                        if current_summary and self._summary_row_matches_day(current_summary, start_key):
                            return self._build_payload_from_summary_rows(
                                conn,
                                start_dt,
                                end_dt,
                                summary_rows=[current_summary],
                                account_rows=current_accounts,
                                plan_rows=current_plans,
                                latest_snapshot_time=str(current_summary.get("snapshot_time") or "").strip(),
                            )
                if start_key < today_key <= end_key:
                    payload = self._performance_snapshot_from_daily_and_current_rows(conn, start_dt, end_dt)
                    if payload.get("snapshot_time"):
                        return payload
            except Exception as exc:  # noqa: BLE001
                if not self.is_missing_daily_read_model_error(exc):
                    raise
            return self._empty_performance_snapshot(start_dt, end_dt)

    def latest_snapshot(self, allowed_advertiser_ids: set[int] | None = None) -> dict[str, Any] | None:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        with self._db() as conn:
            current_summary = conn.execute(
                """
                SELECT *
                FROM summary_current
                WHERE customer_center_id = ?
                LIMIT 1
                """,
                (customer_center_id,),
            ).fetchone()
            if current_summary:
                snapshot_time = str(current_summary["snapshot_time"] or "")
                accounts = conn.execute(
                    """
                    SELECT * FROM account_current
                    WHERE customer_center_id = ?
                    ORDER BY stat_cost DESC, advertiser_id ASC
                    """,
                    (customer_center_id,),
                ).fetchall()
                plans = conn.execute(
                    """
                    SELECT * FROM plan_current
                    WHERE customer_center_id = ?
                    ORDER BY order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, ad_id ASC
                    """,
                    (customer_center_id,),
                ).fetchall()
                account_items = [dict(row) for row in accounts]
                plan_rows = [dict(row) for row in plans]
                if callable(self._apply_plan_delivery_type_metadata):
                    plan_rows = self._apply_plan_delivery_type_metadata(conn, plan_rows)
                plan_items = self._apply_employee_attribution(
                    [self._decorate_plan_item(row) for row in plan_rows],
                    account_items,
                )
                account_balance_items = self._snapshot_account_balances(conn, snapshot_time)
                shared_wallet_items = self._snapshot_shared_wallets(conn, snapshot_time)
                wallet_relation_items = self._snapshot_wallet_relations(conn, snapshot_time)
                summary_payload, products, employees, operators = self._rankings_bundle(
                    dict(current_summary),
                    account_items,
                    plan_items,
                )
                summary_payload["wallet_count"] = len(shared_wallet_items)
                summary_payload["account_balance_count"] = len(account_balance_items)
                payload = {
                    "snapshot_time": snapshot_time,
                    "summary": summary_payload,
                    "accounts": account_items,
                    "plans": plan_items,
                    "accountBalances": account_balance_items,
                    "sharedWallets": shared_wallet_items,
                    "walletRelations": wallet_relation_items,
                    "products": products,
                    "employees": employees,
                    "operators": operators,
                    "extendedSync": None,
                }
                return self.apply_account_scope(payload, allowed_advertiser_ids)
        return None
