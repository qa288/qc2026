from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class HistoryAccess:
    def latest_extended_sync_run(self, conn: Any) -> Any:
        return conn.execute(
            """
            SELECT *
            FROM extended_sync_runs
            ORDER BY snapshot_time DESC
            LIMIT 1
            """
        ).fetchone()

    def latest_extended_sync_runs_for_window(
        self,
        conn: Any,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT *
            FROM extended_sync_runs
            WHERE status IN ('ok', 'partial')
              AND snapshot_time >= ?
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

    def summary_meta_for_day(self, conn: Any, target_day: datetime) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT snapshot_time, window_start, window_end
            FROM summary_snapshots
            WHERE snapshot_time >= ?
              AND snapshot_time <= ?
            ORDER BY snapshot_time DESC
            LIMIT 1
            """,
            (
                target_day.strftime("%Y-%m-%d 00:00:00"),
                target_day.strftime("%Y-%m-%d 23:59:59"),
            ),
        ).fetchone()
        return dict(row) if row else None

    def missing_extended_days(self, conn: Any, start_dt: datetime, end_dt: datetime) -> list[datetime]:
        start_day = start_dt.date()
        end_day = end_dt.date()
        rows = conn.execute(
            """
            SELECT DISTINCT substr(snapshot_time, 1, 10) AS day_key
            FROM extended_sync_runs
            WHERE status IN ('ok', 'partial')
              AND snapshot_time >= ?
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
