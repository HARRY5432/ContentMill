#!/usr/bin/env python3
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def send_telegram(message):
    cfg = load_config()
    token = cfg.get("telegram_bot_token")
    chat_id = cfg.get("telegram_chat_id")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception:
        return False


def notify_master_report(date_str, daily_count, downloaded, built, uploaded, batch_dir, errors=None):
    lines = [
        f"\U0001f4ca <b>Daily Pipeline Report</b>",
        f"\U0001f4c5 {date_str}",
        "",
        f"\u2b07\ufe0f Downloaded: {downloaded} videos",
        f"\u2702\ufe0f Shorts Built: {built} clips",
        f"\u2b06\ufe0f Uploaded: {uploaded}/{daily_count} shorts",
        f"\U0001f4c1 Batch: {batch_dir}",
    ]
    if errors:
        lines.append("")
        lines.append(f"\u274c Errors: {errors}")
    status = "\u2705 Complete" if uploaded == daily_count and not errors else "\u26a0\ufe0f Incomplete"
    lines.insert(1, f"Status: {status}")
    msg = "\n".join(lines)
    return send_telegram(msg)


def notify_error(step, error_msg):
    msg = f"\u274c <b>Pipeline Error</b>\nStep: {step}\nError: {error_msg}"
    return send_telegram(msg)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        send_telegram(" ".join(sys.argv[1:]))
    else:
        send_telegram("Test notification from contentfarming pipeline")

