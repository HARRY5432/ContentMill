#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.json"


def _yt_dlp_cmd():
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    return [sys.executable, "-m", "yt_dlp"]


def load_config():
    with open(CONFIG, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def cleanup_partials(raw_dir):
    for f in raw_dir.glob("*.part"):
        f.unlink(missing_ok=True)
    for f in raw_dir.glob("*.ytdl"):
        f.unlink(missing_ok=True)


def download_channel(url, out_dir, videos_per_channel=5):
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = _yt_dlp_cmd() + [
        "--playlist-items", f"1:{videos_per_channel}",
        "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(out_dir / "%(title).80s_%(id)s.%(ext)s"),
        "--no-playlist",
        "--no-overwrites",
        "--ignore-errors",
        "--socket-timeout", "30",
        "--retries", "3",
        "--extractor-retries", "3",
    ]
    cookies = HERE / "cookies.txt"
    if cookies.exists():
        cmd += ["--cookies", str(cookies)]
    cmd.append(url)
    print(f"Downloading up to {videos_per_channel} recent videos from {url}")
    print(f"  -> {out_dir}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"WARNING: yt-dlp exited with code {result.returncode} for {url}")
    else:
        print(f"  Done: {url}")


def main():
    cfg = load_config()
    raw_dir = HERE / cfg["raw_dir"]
    raw_dir.mkdir(exist_ok=True)

    cleanup_partials(raw_dir)

    channels = cfg.get("channels", [])
    if not channels:
        print("No channels configured in config.json")
        sys.exit(1)

    daily = int(cfg.get("daily_shorts", 5))
    needed_videos = max(3, (daily + 2) // 3)

    for ch in channels:
        download_channel(ch, raw_dir, videos_per_channel=needed_videos)

    downloaded = list(raw_dir.glob("*.mp4")) + list(raw_dir.glob("*.mkv"))
    print(f"\nTotal raw files available: {len(downloaded)}")


if __name__ == "__main__":
    main()
