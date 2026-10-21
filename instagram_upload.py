#!/usr/bin/env python3
"""Upload the generated Shorts batch to one Instagram account.

The account folders contain browser-exported Instagram cookies. This adapter
uses only the sessionid cookie to authenticate Instagrapi, then verifies the
actual username before any upload is attempted.

Examples:
  python instagram_upload.py --account account_2 --dry-run
  python instagram_upload.py --account account_2 --verify
  python instagram_upload.py --account account_2 --limit 1 --trial
  python instagram_upload.py --account account_2
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACCOUNTS_DIR = HERE / "accounts"
SHORTS_DIR = HERE / "shorts"


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def account_dir(account):
    if not re.fullmatch(r"account_[0-9]+", account):
        raise ValueError("account must look like account_2")
    path = ACCOUNTS_DIR / account
    if not path.is_dir():
        raise FileNotFoundError(f"account folder not found: {path}")
    return path


def find_cookie_file(path):
    candidates = sorted(p for p in path.glob("*.txt") if p.is_file())
    if not candidates:
        raise FileNotFoundError(f"no Instagram cookie export found in {path}")
    return candidates[0]


def load_sessionid(cookie_path):
    try:
        data = json.loads(cookie_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"invalid cookie JSON in {cookie_path.name}: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("cookie export must be a JSON array")
    for cookie in data:
        if isinstance(cookie, dict) and cookie.get("name") == "sessionid":
            value = str(cookie.get("value", ""))
            if len(value) > 30:
                return value
    raise ValueError(f"sessionid cookie missing from {cookie_path.name}")


def newest_batch(explicit):
    if explicit:
        path = Path(explicit)
        if not path.is_dir():
            raise FileNotFoundError(f"batch folder not found: {path}")
        return path
    batches = sorted(p for p in SHORTS_DIR.glob("batch_*") if p.is_dir())
    if not batches:
        raise FileNotFoundError("no shorts batch found under shorts/")
    return batches[-1]


def parse_metadata(path):
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    title_match = re.search(r"^TITLE:\s*\n(.+)$", text, re.MULTILINE)
    desc_match = re.search(
        r"^DESCRIPTION:\s*\n(.*?)(?=^\n?TAGS?:|\Z)",
        text, re.MULTILINE | re.DOTALL,
    )
    tags_match = re.search(r"^TAGS:\s*\n(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""
    description = desc_match.group(1).strip() if desc_match else ""
    tags = []
    if tags_match:
        tags = [f"#{x.strip().lstrip('#')}" for x in tags_match.group(1).split(",") if x.strip()]
    return title, description, tags


def instagram_caption(video_path):
    meta_path = video_path.with_suffix(".txt")
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata missing for {video_path.name}")
    title, description, tags = parse_metadata(meta_path)
    parts = [part for part in (title, description, " ".join(tags)) if part]
    caption = "\n\n".join(parts).strip()
    if not caption:
        raise ValueError(f"metadata is empty for {video_path.name}")
    return caption[:2200]


def batch_items(batch):
    videos = sorted(batch.glob("*.mp4"))
    if not videos:
        raise ValueError(f"batch {batch.name} contains no MP4 files")
    items = []
    for video in videos:
        caption = instagram_caption(video)
        items.append({
            "name": video.name,
            "path": video,
            "caption": caption,
            "caption_sha256": hashlib.sha256(caption.encode()).hexdigest(),
        })
    return items


def state_path(account_path, batch):
    return account_path / f"instagram_uploads_{batch.name}.json"


def load_state(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def login_account(sessionid):
    try:
        from instagrapi import Client
    except ImportError as exc:
        raise RuntimeError("instagrapi is not installed; install requirements.txt") from exc
    client = Client()
    client.delay_range = [1, 3]
    client.login_by_sessionid(sessionid)
    return client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", required=True, help="account folder, for example account_2")
    parser.add_argument("--batch", default=None, help="shorts batch directory")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true", help="validate locally; no network or upload")
    parser.add_argument("--verify", action="store_true", help="login and print the account username only")
    parser.add_argument("--trial", action="store_true", help="send one trial reel instead of the full batch")
    args = parser.parse_args()

    try:
        acct = account_dir(args.account)
        batch = newest_batch(args.batch)
        items = batch_items(batch)[:max(1, args.limit)]
        cookie_file = find_cookie_file(acct)
        print(f"Account: {args.account}")
        print(f"Cookie export: {cookie_file.name}")
        print(f"Batch: {batch}")
        print(f"Prepared: {len(items)} Instagram caption(s)")
        for idx, item in enumerate(items, 1):
            print(f"  [{idx}/{len(items)}] {item['name']} ({len(item['caption'])} caption chars)")
        if args.dry_run:
            print("\nDry run: no Instagram network request and no upload.")
            return 0
        client = login_account(load_sessionid(cookie_file))
        username = getattr(client, "username", None) or "unknown"
        print(f"Authenticated Instagram account: @{username}")
        if args.verify:
            print("Verification only: no upload.")
            return 0
        if args.trial:
            items = items[:1]
            print("Trial mode: one reel maximum.")

        state_file = state_path(acct, batch)
        state = load_state(state_file)
        uploaded = state.setdefault("uploaded", {})
        for item in items:
            if item["name"] in uploaded:
                print(f"Skipping already recorded upload: {item['name']}")
                continue
            print(f"Uploading {item['name']}...")
            media = client.clip_upload(
                Path(item["path"]), item["caption"], trial=args.trial
            )
            uploaded[item["name"]] = {
                "status": "trial" if args.trial else "posted",
                "media_pk": str(getattr(media, "pk", "")),
                "caption_sha256": item["caption_sha256"],
                "posted_at": datetime.now(timezone.utc).isoformat(),
            }
            save_state(state_file, state)
            print(f"  Posted {item['name']}")
        print(f"Done. State: {state_file}")
        return 0
    except Exception as exc:
        return fail(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
