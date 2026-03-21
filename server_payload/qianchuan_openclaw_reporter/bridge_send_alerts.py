#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dashboard.db_backend import connect_database, database_backend  # noqa: E402
from report_qianchuan import load_runtime_config  # noqa: E402

DB_PATH = Path(os.environ.get("DASHBOARD_DB_PATH", "/app/data/dashboard.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
CONFIG_PATH = Path(os.environ.get("QIANCHUAN_CONFIG_PATH", "/app/config/config.json"))
OPENCLAW_BIN = os.environ.get("OPENCLAW_BIN", "/usr/local/bin/openclaw")
CHUNK_SIZE = int(os.environ.get("ALERT_CHUNK_SIZE", "6"))
ALERT_LOOKBACK_MINUTES = int(os.environ.get("ALERT_LOOKBACK_MINUTES", "20"))


def load_config() -> dict:
    try:
        return load_runtime_config(CONFIG_PATH)
    except RuntimeError:
        return {}


def db():
    return connect_database(DATABASE_URL, DB_PATH)


def load_notification_settings(conn) -> dict:
    row = None
    try:
        row = conn.execute("SELECT * FROM notification_settings WHERE id = 1").fetchone()
    except Exception:
        row = None
    config = load_config()
    settings = {
        "enabled": False,
        "channel": "feishu",
        "account": "default",
        "target": str(config.get("feishu_target") or "").strip(),
        "alert_enabled": False,
        "alert_batch_size": CHUNK_SIZE,
    }
    if row:
        settings.update(dict(row))
    settings["enabled"] = bool(settings.get("enabled"))
    settings["alert_enabled"] = bool(settings.get("alert_enabled"))
    settings["channel"] = str(settings.get("channel") or "feishu").strip()
    settings["account"] = str(settings.get("account") or "").strip()
    settings["target"] = str(settings.get("target") or "").strip()
    settings["alert_batch_size"] = max(int(settings.get("alert_batch_size") or CHUNK_SIZE), 1)
    return settings


def fetch_pending_events(conn) -> list[dict]:
    cutoff = (datetime.now() - timedelta(minutes=ALERT_LOOKBACK_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    return conn.execute(
        """
        SELECT * FROM alert_events
        WHERE status = 'pending'
          AND created_at >= ?
        ORDER BY created_at ASC, id ASC
        """,
        (cutoff,),
    ).fetchall()


def chunk(items: list[dict], size: int) -> Iterable[list[dict]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def send_message(settings: dict, message: str) -> None:
    command = [OPENCLAW_BIN, "message", "send", "--channel", settings["channel"]]
    if settings.get("account"):
        command.extend(["--account", settings["account"]])
    command.extend(["--target", settings["target"], "-m", message])
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def mark_sent(conn, event_ids: list[int]) -> None:
    sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.executemany(
        "UPDATE alert_events SET status = 'sent', sent_at = ? WHERE id = ?",
        [(sent_at, event_id) for event_id in event_ids],
    )


def build_message(rows: list[dict]) -> str:
    lines = [
        "千川告警汇总",
        f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"条数：{len(rows)}",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        lines.append(f"{index}. {row['message']}")
        lines.append("")
    return "\n".join(lines).strip()


def dispatch_once() -> dict:
    if database_backend(DATABASE_URL) == "sqlite" and not DB_PATH.exists():
        return {"ok": True, "sent": 0, "reason": "db_missing"}

    sent_count = 0
    with db() as conn:
        settings = load_notification_settings(conn)
        if not settings["enabled"] or not settings["target"] or not settings["channel"]:
            return {"ok": True, "sent": 0, "reason": "notification_disabled"}
        if not settings["alert_enabled"]:
            return {"ok": True, "sent": 0, "reason": "alert_disabled"}

        rows = fetch_pending_events(conn)
        for group in chunk(rows, settings["alert_batch_size"]):
            send_message(settings, build_message(group))
            mark_sent(conn, [int(item["id"]) for item in group])
            sent_count += len(group)
    return {"ok": True, "sent": sent_count}


def main() -> int:
    dispatch_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
