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
        snapshot_account_balances: Callable[[Any, str], list[dict[str, Any]]],
        snapshot_shared_wallets: Callable[[Any, str], list[dict[str, Any]]],
        snapshot_wallet_relations: Callable[[Any, str], list[dict[str, Any]]],
    ) -> None:
        self._db = db_factory
        self._rankings_bundle = rankings_bundle
        self._scoped_summary = scoped_summary
        self._decorate_plan_item = decorate_plan_item
        self._apply_employee_attribution = apply_employee_attribution
        self._snapshot_account_balances = snapshot_account_balances
        self._snapshot_shared_wallets = snapshot_shared_wallets
        self._snapshot_wallet_relations = snapshot_wallet_relations

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
        self, payload: dict[str, Any], allowed_advertiser_ids: set[int] | None
    ) -> dict[str, Any]:
        if allowed_advertiser_ids is None:
            return payload
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
        next_payload["summary"], next_payload["products"], next_payload["employees"], next_payload["operators"] = self._rankings_bundle(
            self._scoped_summary(accounts, plans),
            accounts,
            plans,
        )
        return next_payload

    def latest_summary_snapshots_for_window(
        self,
        conn: Any,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT snapshot_time, window_start, window_end
            FROM summary_snapshots
            WHERE snapshot_time >= ?
              AND snapshot_time <= ?
            ORDER BY snapshot_time DESC
            """,
            (
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

    def missing_summary_days(self, conn: Any, start_dt: datetime, end_dt: datetime) -> list[datetime]:
        start_day = start_dt.date()
        end_day = end_dt.date()
        rows = conn.execute(
            """
            SELECT DISTINCT substr(snapshot_time, 1, 10) AS day_key
            FROM summary_snapshots
            WHERE snapshot_time >= ?
              AND snapshot_time <= ?
            """,
            (
                start_dt.strftime("%Y-%m-%d 00:00:00"),
                end_dt.strftime("%Y-%m-%d 23:59:59"),
            ),
        ).fetchall()
        existing_days = {str(row["day_key"] or "") for row in rows if str(row["day_key"] or "").strip()}
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
                group["order_count"] = 0
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
            group["order_count"] = int(group.get("order_count", 0) or 0) + int(float(row.get("order_count", 0.0) or 0.0))
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
            order_count = int(group.get("order_count", 0) or 0)
            group["advertiser_id"] = advertiser_id
            group["stat_cost"] = stat_cost
            group["pay_amount"] = pay_amount
            group["order_count"] = order_count
            group["roi"] = round(pay_amount / stat_cost, 2) if stat_cost > 0 else 0.0
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

    def performance_snapshot_from_db(self, start_dt: datetime, end_dt: datetime) -> dict[str, Any]:
        with self._db() as conn:
            snapshots = self.latest_summary_snapshots_for_window(conn, start_dt, end_dt)
            if not snapshots:
                return self._empty_performance_snapshot(start_dt, end_dt)

            snapshot_times = [str(item.get("snapshot_time") or "") for item in snapshots if str(item.get("snapshot_time") or "").strip()]
            placeholders = ",".join("?" for _ in snapshot_times)
            account_rows = conn.execute(
                f"""
                SELECT *
                FROM account_snapshots
                WHERE snapshot_time IN ({placeholders})
                ORDER BY snapshot_time DESC, stat_cost DESC, advertiser_id ASC
                """,
                snapshot_times,
            ).fetchall()
            plan_rows = conn.execute(
                f"""
                SELECT *
                FROM plan_snapshots
                WHERE snapshot_time IN ({placeholders})
                ORDER BY snapshot_time DESC, order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, ad_id ASC
                """,
                snapshot_times,
            ).fetchall()

            latest_snapshot_time = snapshot_times[-1]
            account_balance_items = self._snapshot_account_balances(conn, latest_snapshot_time)
            shared_wallet_items = self._snapshot_shared_wallets(conn, latest_snapshot_time)
            wallet_relation_items = self._snapshot_wallet_relations(conn, latest_snapshot_time)

        account_items = self.aggregate_account_snapshots([dict(row) for row in account_rows])
        plan_items = [self._decorate_plan_item(item) for item in self.aggregate_plan_snapshots([dict(row) for row in plan_rows])]

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
            "snapshot_count": len(snapshot_times),
        }

    def latest_snapshot(self, allowed_advertiser_ids: set[int] | None = None) -> dict[str, Any] | None:
        with self._db() as conn:
            latest = conn.execute(
                "SELECT snapshot_time FROM summary_snapshots ORDER BY snapshot_time DESC LIMIT 1"
            ).fetchone()
            if not latest:
                return None
            snapshot_time = latest["snapshot_time"]
            summary = conn.execute(
                "SELECT * FROM summary_snapshots WHERE snapshot_time = ?",
                (snapshot_time,),
            ).fetchone()
            accounts = conn.execute(
                """
                SELECT * FROM account_snapshots
                WHERE snapshot_time = ?
                ORDER BY stat_cost DESC, advertiser_id ASC
                """,
                (snapshot_time,),
            ).fetchall()
            plans = conn.execute(
                """
                SELECT * FROM plan_snapshots
                WHERE snapshot_time = ?
                ORDER BY order_count DESC, pay_amount DESC, roi DESC, stat_cost DESC, ad_id ASC
                """,
                (snapshot_time,),
            ).fetchall()
            account_items = [dict(row) for row in accounts]
            plan_items = self._apply_employee_attribution(
                [self._decorate_plan_item(row) for row in plans],
                account_items,
            )
            account_balance_items = self._snapshot_account_balances(conn, snapshot_time)
            shared_wallet_items = self._snapshot_shared_wallets(conn, snapshot_time)
            wallet_relation_items = self._snapshot_wallet_relations(conn, snapshot_time)
            summary_payload, products, employees, operators = self._rankings_bundle(
                dict(summary),
                account_items,
                plan_items,
            )
            summary_payload["wallet_count"] = len(shared_wallet_items)
            summary_payload["account_balance_count"] = len(account_balance_items)
            extended_run = conn.execute(
                "SELECT * FROM extended_sync_runs WHERE snapshot_time = ?",
                (snapshot_time,),
            ).fetchone()
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
                "extendedSync": dict(extended_run) if extended_run else None,
            }
            return self.apply_account_scope(payload, allowed_advertiser_ids)
