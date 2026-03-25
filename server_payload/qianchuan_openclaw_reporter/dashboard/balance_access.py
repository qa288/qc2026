from __future__ import annotations

import json
from typing import Any, Callable


class BalanceAccess:
    def __init__(
        self,
        json_text: Callable[[Any], str],
        normalize_account_fund_money: Callable[[Any], float],
    ) -> None:
        self._json_text = json_text
        self._normalize_account_fund_money = normalize_account_fund_money

    @staticmethod
    def wallet_display_name(wallet_id: str, member_count: int) -> str:
        text = str(wallet_id or "").strip()
        if not text:
            return "未命名钱包"
        suffix = text[-6:] if len(text) > 6 else text
        return f"{'共享钱包' if member_count > 1 else '钱包'} {suffix}"

    def collect_balance_snapshot(self, client: Any, accounts: list[dict[str, Any]]) -> dict[str, Any]:
        account_ids = [int(item.get("advertiser_id", 0) or 0) for item in accounts if int(item.get("advertiser_id", 0) or 0)]
        account_map = {int(item["advertiser_id"]): item for item in accounts if int(item.get("advertiser_id", 0) or 0)}
        if not account_ids:
            return {
                "account_balances": [],
                "shared_wallets": [],
                "wallet_relations": [],
                "errors": [],
            }

        try:
            rows = client.list_account_funds(account_ids, account_type="QIANCHUAN")
        except Exception as exc:  # noqa: BLE001
            return {
                "account_balances": [],
                "shared_wallets": [],
                "wallet_relations": [],
                "errors": [
                    {
                        "stage": "account_fund_get",
                        "error": str(exc),
                    }
                ],
            }
        fund_map = {int(item.get("account_id", 0) or 0): item for item in rows if int(item.get("account_id", 0) or 0)}

        account_balance_rows: list[dict[str, Any]] = []
        shared_wallet_groups: dict[str, dict[str, Any]] = {}
        errors: list[dict[str, Any]] = []

        for advertiser_id in account_ids:
            meta = account_map.get(advertiser_id) or {}
            raw = fund_map.get(advertiser_id)
            if not raw:
                errors.append(
                    {
                        "stage": "account_fund_get",
                        "advertiser_id": advertiser_id,
                        "error": "missing account fund row",
                    }
                )
                continue

            advertiser_name = str(meta.get("advertiser_name") or raw.get("account_id") or advertiser_id)
            wallet_id = str(raw.get("wallet_id") or "").strip()
            balance = self._normalize_account_fund_money(raw.get("balance"))
            valid_balance = self._normalize_account_fund_money(raw.get("valid_balance"))
            wallet_valid_balance = self._normalize_account_fund_money(raw.get("wallet_total_balance_valid"))
            account_balance_rows.append(
                {
                    "advertiser_id": advertiser_id,
                    "advertiser_name": advertiser_name,
                    "account_balance": balance,
                    "available_balance": valid_balance,
                    "wallet_id": wallet_id,
                    "wallet_balance": wallet_valid_balance,
                    "stat_cost": 0.0,
                    "pay_amount": 0.0,
                    "order_count": 0,
                    "roi": 0.0,
                    "raw_json": self._json_text(raw),
                }
            )

            if not wallet_id:
                continue
            group = shared_wallet_groups.setdefault(
                wallet_id,
                {
                    "main_wallet_id": wallet_id,
                    "account_ids": set(),
                    "account_names": [],
                    "valid_balances": [],
                    "rows": [],
                },
            )
            group["account_ids"].add(advertiser_id)
            group["account_names"].append(advertiser_name)
            group["valid_balances"].append(wallet_valid_balance)
            group["rows"].append(raw)

        shared_wallet_rows: list[dict[str, Any]] = []
        wallet_relation_rows: list[dict[str, Any]] = []
        for wallet_id, group in shared_wallet_groups.items():
            member_count = len(group["account_ids"])
            if member_count < 2:
                continue
            wallet_name = self.wallet_display_name(wallet_id, member_count)
            valid_balance = max((float(item or 0.0) for item in group["valid_balances"]), default=0.0)
            shared_wallet_rows.append(
                {
                    "main_wallet_id": wallet_id,
                    "wallet_name": wallet_name,
                    "wallet_balance": round(valid_balance, 2),
                    "total_balance": round(valid_balance, 2),
                    "valid_balance": round(valid_balance, 2),
                    "member_count": member_count,
                    "stat_cost": 0.0,
                    "pay_amount": 0.0,
                    "order_count": 0,
                    "roi": 0.0,
                    "raw_json": self._json_text(
                        {
                            "source": "account_fund_get_v3.0",
                            "account_ids": sorted(group["account_ids"]),
                            "account_names": group["account_names"],
                            "rows": group["rows"],
                        }
                    ),
                }
            )
            for advertiser_id in sorted(group["account_ids"]):
                advertiser_name = str(account_map.get(advertiser_id, {}).get("advertiser_name") or advertiser_id)
                wallet_relation_rows.append(
                    {
                        "main_wallet_id": wallet_id,
                        "advertiser_id": advertiser_id,
                        "advertiser_name": advertiser_name,
                        "child_wallet_id": wallet_id,
                        "wallet_name": wallet_name,
                        "raw_json": self._json_text(
                            {
                                "source": "account_fund_get_v3.0",
                                "wallet_id": wallet_id,
                                "advertiser_id": advertiser_id,
                            }
                        ),
                    }
                )

        account_balance_rows.sort(key=lambda item: (-float(item["available_balance"]), int(item["advertiser_id"])))
        shared_wallet_rows.sort(key=lambda item: (-float(item["valid_balance"]), str(item["main_wallet_id"])))
        wallet_relation_rows.sort(key=lambda item: (str(item["main_wallet_id"]), int(item["advertiser_id"])))
        return {
            "account_balances": account_balance_rows,
            "shared_wallets": shared_wallet_rows,
            "wallet_relations": wallet_relation_rows,
            "errors": errors,
        }

    def snapshot_account_balances(self, conn: Any, snapshot_time: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT *
            FROM account_balances
            WHERE snapshot_time = ?
            ORDER BY available_balance DESC, advertiser_id ASC
            """,
            (snapshot_time,),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                raw = json.loads(str(item.get("raw_json") or "{}"))
            except Exception:
                raw = {}
            item["wallet_id"] = str(raw.get("wallet_id") or "")
            item["wallet_balance"] = self._normalize_account_fund_money(raw.get("wallet_total_balance_valid"))
            items.append(item)
        return items

    def snapshot_shared_wallets(self, conn: Any, snapshot_time: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT w.*,
                   COALESCE(rel.member_count, 0) AS member_count
            FROM shared_wallets AS w
            LEFT JOIN (
                SELECT snapshot_time, main_wallet_id, COUNT(*) AS member_count
                FROM shared_wallet_account_relations
                GROUP BY snapshot_time, main_wallet_id
            ) AS rel
              ON rel.snapshot_time = w.snapshot_time
             AND rel.main_wallet_id = w.main_wallet_id
            WHERE w.snapshot_time = ?
            ORDER BY w.valid_balance DESC, w.main_wallet_id ASC
            """,
            (snapshot_time,),
        ).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            item["wallet_balance"] = item.get("valid_balance", 0)
        return items

    def snapshot_wallet_relations(self, conn: Any, snapshot_time: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT *
            FROM shared_wallet_account_relations
            WHERE snapshot_time = ?
            ORDER BY main_wallet_id ASC, advertiser_id ASC
            """,
            (snapshot_time,),
        ).fetchall()
        return [dict(row) for row in rows]
