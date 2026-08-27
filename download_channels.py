import json
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).with_name("config.json")
YT_DLP = r"C:\Users\admin\AppData\Local\Python\pythoncore-3.14-64\Scripts\yt-dlp.exe"

def load_config():
    with open(CONFIG, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def download_channel(url, out_dir):
    cmd = [
        YT_DLP,
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(out_dir / "%(title)s_%(id)s.%(ext)s"),
        "--no-playlist",
        url,
    ]
    print(f"Downloading from {url} -> {out_dir}")
    subprocess.run(cmd, check=True)

def main():
    cfg = load_config()
    raw_dir = Path(__file__).parent / cfg["raw_dir"]
    raw_dir.mkdir(exist_ok=True)

    channels = cfg.get("channels", [])
    if not channels:
        print("No channels configured in config.json")
        sys.exit(1)

    for ch in channels:
        download_channel(ch, raw_dir)

if __name__ == "__main__":
    main()

