#!/usr/bin/env python3
"""
yt_upload.py - upload a batch of shorts to YouTube via the official API.

Pure Python (google-api-python-client). No external binaries.

- Reads each video's .txt sidecar (TITLE / DESCRIPTION / TAGS) written by
  rename_publish.py
- First run: opens your browser once for Google login, then stores the
  token in token.json for all future headless runs
- Skips videos already listed in <batch>/uploaded.json, so re-runs resume

Usage:
  python yt_upload.py shorts\\batch_01
  python yt_upload.py shorts\\batch_01 --privacy public
  python yt_upload.py shorts\\batch_01 --dry-run
"""

import argparse
import http.server
import json
import os
import re
import socketserver
import sys
import threading
import webbrowser

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS_PATH = os.path.join(HERE, "client_secrets.json")
TOKEN_PATH = os.path.join(HERE, "token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube"]
REDIRECT_URI = "http://localhost:8080/oauth2callback"
UPLOAD_PORT = 8080

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_meta(txt_path):
    with open(txt_path, "r", encoding="utf-8-sig") as f:
        content = f.read()
    title_m = re.search(r"^TITLE:\s*\n(.+)$", content, re.MULTILINE)
    desc_m = re.search(r"^DESCRIPTION:\s*\n(.*?)(?=^\n?TAGS?:|\Z)", content,
                       re.MULTILINE | re.DOTALL)
    tags_m = re.search(r"^TAGS:\s*\n(.+)$", content, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else None
    description = desc_m.group(1).strip() if desc_m else None
    tags = [t.strip() for t in tags_m.group(1).split(",") if t.strip()] if tags_m else None
    return title, description, tags


class _OAuthHandler(http.server.BaseHTTPRequestHandler):
    code = None

    def do_GET(self):
        if self.path.startswith("/oauth2callback"):
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
            _OAuthHandler.code = params.get("code")
            error = params.get("error")
            msg = ("Upload auth complete - you can close this tab."
                   if _OAuthHandler.code else f"Auth failed: {error}")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=SCOPES,
        )
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds)
        return creds

    flow = Flow.from_client_secrets_file(SECRETS_PATH, scopes=SCOPES,
                                         redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(access_type="offline",
                                         prompt="consent",
                                         include_granted_scopes="false")
    print("\nA browser window should have opened for Google login.")
    print("If not, open this URL manually:\n")
    print(auth_url[:100] + "...")
    print("\nLog in -> Advanced -> 'Go to demo (unsafe)' -> Allow\n")

    with socketserver.TCPServer(("localhost", UPLOAD_PORT), _OAuthHandler) as httpd:
        threading.Thread(target=lambda: webbrowser.open(auth_url), daemon=True).start()
        while _OAuthHandler.code is None:
            httpd.handle_request()

    flow.fetch_token(code=_OAuthHandler.code)
    creds = flow.credentials
    save_credentials(creds)
    print("Login OK - token saved for future runs.\n")
    return creds


def save_credentials(creds):
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
        }, f, indent=2)


def upload_one(youtube, video_path, meta, privacy):
    body = {
        "snippet": {},
        "status": {"privacyStatus": privacy,
                   "selfDeclaredMadeForKids": False},
    }
    snippet = body["snippet"]
    if meta["title"]:
        snippet["title"] = meta["title"]
    else:
        snippet["title"] = os.path.splitext(os.path.basename(video_path))[0]
    if meta["description"]:
        snippet["description"] = meta["description"]
    if meta["tags"]:
        snippet["tags"] = meta["tags"]
    if meta["category_id"]:
        snippet["categoryId"] = meta["category_id"]

    media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024,
                            resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body,
                                      media_body=media)
    response = None
    last_pct = -1
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            if pct != last_pct:
                last_pct = pct
                print(f"\r       uploading... {pct:>3}%", end="", flush=True)
    print("\r" + " " * 40 + "\r", end="", flush=True)
    return response


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch_dir")
    ap.add_argument("--privacy", default="private",
                    choices=["private", "unlisted", "public"])
    ap.add_argument("--category", default=None,
                    help="YouTube categoryId e.g. 24=Entertainment, 22=People & Blogs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    batch_dir = os.path.abspath(args.batch_dir)
    if not os.path.isdir(batch_dir):
        print(f"batch folder not found: {batch_dir}")
        sys.exit(1)

    videos = sorted(n for n in os.listdir(batch_dir) if n.lower().endswith(".mp4"))
    state_path = os.path.join(batch_dir, "uploaded.json")
    uploaded = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                uploaded = json.load(f)
        except Exception:
            uploaded = {}
    todo = [n for n in videos if n not in uploaded]
    if not todo:
        print(f"all {len(videos)} video(s) already uploaded.")
        return

    youtube = None
    if not args.dry_run:
        if not os.path.exists(SECRETS_PATH):
            print("ERROR: client_secrets.json missing next to this script.")
            sys.exit(1)
        creds = get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

    print(f"{len(todo)} of {len(videos)} video(s) to upload "
          f"(privacy={args.privacy}, dry_run={args.dry_run})\n")

    ok_count = fail_count = 0
    for idx, name in enumerate(todo, 1):
        stem = name[:-4]
        txt_path = os.path.join(batch_dir, stem + ".txt")
        title, description, tags = (None, None, None)
        if os.path.exists(txt_path):
            title, description, tags = parse_meta(txt_path)
        meta = {"title": title, "description": description,
                "tags": tags, "category_id": args.category}

        print(f"[{idx}/{len(todo)}] {name}")
        print(f"       title: {title or '(none - using filename)'}")
        if args.dry_run:
            print("       (dry) would upload\n")
            continue

        try:
            resp = upload_one(youtube, os.path.join(batch_dir, name),
                              meta, args.privacy)
            vid = resp.get("id")
            uploaded[name] = {"videoId": vid, "title": title,
                              "privacy": args.privacy}
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(uploaded, f, indent=2, ensure_ascii=False)
            ok_count += 1
            print(f"       OK -> https://youtu.be/{vid}\n")
        except HttpError as e:
            fail_count += 1
            detail = ""
            if e.resp is not None and e.content:
                try:
                    detail = json.loads(e.content)["error"]["errors"][0].get("reason", "")
                except Exception:
                    detail = str(e)[:200]
            print(f"       FAILED ({detail or e.status})\n")
            if detail == "quotaExceeded":
                print("Daily YouTube API quota reached (~6 uploads/day on new projects).")
                print("Run again tomorrow - it will continue where it stopped.\n")
                break
        except Exception as e:
            fail_count += 1
            print(f"       FAILED: {e}\n")

    print(f"done: {ok_count} uploaded, {fail_count} failed, "
          f"{len(todo) - ok_count - fail_count} left.")


if __name__ == "__main__":
    main()
