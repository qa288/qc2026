#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import subprocess
import sys
import urllib.error
import urllib.request
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
CONFIG_PATH = Path(os.environ.get("QIANCHUAN_CONFIG_PATH") or os.environ.get("CONFIG_PATH") or "/app/config/config.json")
OPENCLAW_BIN = os.environ.get("OPENCLAW_BIN", "/usr/local/bin/openclaw")
CHUNK_SIZE = int(os.environ.get("ALERT_CHUNK_SIZE", "6"))
ALERT_LOOKBACK_MINUTES = int(os.environ.get("ALERT_LOOKBACK_MINUTES", "20"))
FEISHU_TOKEN_URL = os.environ.get(
    "FEISHU_TOKEN_URL",
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
)
FEISHU_MESSAGE_URL = os.environ.get(
    "FEISHU_MESSAGE_URL",
    "https://open.feishu.cn/open-apis/im/v1/messages",
)


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
        "feishu_app_id": str(os.environ.get("FEISHU_APP_ID") or config.get("feishu_app_id") or "").strip(),
        "feishu_app_secret": str(
            os.environ.get("FEISHU_APP_SECRET") or config.get("feishu_app_secret") or ""
        ).strip(),
        "feishu_receive_id_type": str(
            os.environ.get("FEISHU_RECEIVE_ID_TYPE") or config.get("feishu_receive_id_type") or ""
        ).strip(),
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


def post_json(url: str, payload: dict, headers: dict[str, str] | None = None, timeout: int = 15) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code}: {text}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid json response: {text[:500]}") from exc


def feishu_receive_id_type(target: str, configured_type: str = "") -> str:
    configured_type = str(configured_type or "").strip()
    if configured_type:
        return configured_type
    if target.startswith("oc_"):
        return "chat_id"
    if target.startswith("ou_"):
        return "open_id"
    if target.startswith("on_"):
        return "union_id"
    return "chat_id"


def feishu_tenant_access_token(settings: dict) -> str:
    app_id = str(settings.get("feishu_app_id") or "").strip()
    app_secret = str(settings.get("feishu_app_secret") or "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("feishu app id/secret is not configured")
    result = post_json(FEISHU_TOKEN_URL, {"app_id": app_id, "app_secret": app_secret})
    if int(result.get("code", -1)) != 0:
        raise RuntimeError(f"feishu token failed: {result}")
    token = str(result.get("tenant_access_token") or "").strip()
    if not token:
        raise RuntimeError(f"feishu token response missing tenant_access_token: {result}")
    return token


def send_feishu_message(settings: dict, message: str) -> None:
    target = str(settings.get("target") or "").strip()
    if not target:
        raise RuntimeError("feishu target is empty")
    token = feishu_tenant_access_token(settings)
    receive_id_type = feishu_receive_id_type(target, str(settings.get("feishu_receive_id_type") or ""))
    payload = {
        "receive_id": target,
        "msg_type": "text",
        "content": json.dumps({"text": message}, ensure_ascii=False),
    }
    result = post_json(
        f"{FEISHU_MESSAGE_URL}?receive_id_type={receive_id_type}",
        payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    if int(result.get("code", -1)) != 0:
        raise RuntimeError(f"feishu message failed: {result}")


def send_message(settings: dict, message: str) -> None:
    if str(settings.get("channel") or "").strip().lower() == "feishu":
        send_feishu_message(settings, message)
        return
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
