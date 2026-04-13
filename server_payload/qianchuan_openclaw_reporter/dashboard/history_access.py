from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable


class HistoryAccess:
    def __init__(self, current_customer_center_id: Callable[[], str]) -> None:
        self._current_customer_center_id = current_customer_center_id

    @staticmethod
    def _table_exists(conn: Any, table_name: str) -> bool:
        table = str(table_name or "").strip()
        if not table:
            return False
        if getattr(conn, "backend", "") == "postgres":
            row = conn.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
                LIMIT 1
                """,
                (table,),
            ).fetchone()
            return bool(row)
        row = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            LIMIT 1
            """,
            (table,),
        ).fetchone()
        return bool(row)

    def latest_extended_sync_run(self, conn: Any) -> Any:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        return conn.execute(
            """
            SELECT *
            FROM extended_sync_runs
            WHERE customer_center_id = ?
            ORDER BY snapshot_time DESC
            LIMIT 1
            """,
            (customer_center_id,),
        ).fetchone()

    def latest_extended_sync_runs_for_window(
        self,
        conn: Any,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[dict[str, Any]]:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        rows = conn.execute(
            """
            SELECT *
            FROM extended_sync_runs
            WHERE status IN ('ok', 'partial')
              AND customer_center_id = ?
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

    def summary_meta_for_day(self, conn: Any, target_day: datetime) -> dict[str, Any] | None:
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        day_key = target_day.strftime("%Y-%m-%d")
        row = None
        if self._table_exists(conn, "summary_daily"):
            row = conn.execute(
                """
                SELECT snapshot_time, biz_date AS window_day
                FROM summary_daily
                WHERE customer_center_id = ?
                  AND biz_date = ?
                LIMIT 1
                """,
                (customer_center_id, day_key),
            ).fetchone()
        if row:
            snapshot_time = str(row["snapshot_time"] or "").strip()
            if snapshot_time:
                return {
                    "snapshot_time": snapshot_time,
                    "window_start": f"{day_key} 00:00:00",
                    "window_end": f"{day_key} 23:59:59",
                }

        if not self._table_exists(conn, "summary_current"):
            return None
        row = conn.execute(
            """
            SELECT snapshot_time, window_start, window_end
            FROM summary_current
            WHERE customer_center_id = ?
              AND snapshot_time >= ?
              AND snapshot_time <= ?
            LIMIT 1
            """,
            (
                customer_center_id,
                target_day.strftime("%Y-%m-%d 00:00:00"),
                target_day.strftime("%Y-%m-%d 23:59:59"),
            ),
        ).fetchone()
        return dict(row) if row else None

    def missing_extended_days(self, conn: Any, start_dt: datetime, end_dt: datetime) -> list[datetime]:
        start_day = start_dt.date()
        end_day = end_dt.date()
        customer_center_id = str(self._current_customer_center_id() or "").strip()
        rows = conn.execute(
            """
            SELECT DISTINCT substr(snapshot_time, 1, 10) AS day_key
            FROM extended_sync_runs
            WHERE status IN ('ok', 'partial')
              AND customer_center_id = ?
              AND snapshot_time >= ?
              AND snapshot_time <= ?
            """,
            (
                customer_center_id,
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
