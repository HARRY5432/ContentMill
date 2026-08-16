#!/usr/bin/env python3
"""
build_shorts.py
===============
Batch step of the "3-up shorts" pipeline.

For every group of N input recordings (N = clips_per_short, default 3) it:
  1. speeds each clip up by speed_multiplier (default 100x = 10000%),
  2. scales + center-crops each clip to fill one vertical slice of the frame
     (frame_height / clips_per_short tall),
  3. stacks the slices top -> middle -> bottom into one 9:16 frame (xstack),
  4. trims the result to segment_seconds (default 10s),
  5. writes composited/short_001.mp4, short_002.mp4, ...

Then run the Premiere Pro script (premiere/process_shorts.jsx) to turn the
composited clips into a finished timeline.

Requires ffmpeg (and optionally ffprobe) on your PATH.
  Windows:  winget install ffmpeg   (or https://ffmpeg.org/download.html)
  macOS:    brew install ffmpeg

Usage:
  python build_shorts.py            # process everything
  python build_shorts.py --dry-run  # print ffmpeg commands without running them
  python build_shorts.py --force    # overwrite existing output files
"""

import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".mxf", ".ts", ".webm", ".m4v"}


def die(message):
    print(f"\nERROR: {message}")
    sys.exit(1)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        die(f"config.json not found next to this script ({CONFIG_PATH})")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def natural_key(name):
    """Sort names so file2 comes before file10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def list_inputs(input_dir):
    if not os.path.isdir(input_dir):
        die(
            f"input folder '{input_dir}' not found. "
            f"Create it and put your recordings in it (or edit config.json)."
        )
    files = [
        os.path.join(input_dir, n)
        for n in os.listdir(input_dir)
        if os.path.splitext(n)[1].lower() in VIDEO_EXTENSIONS
    ]
    if not files:
        die(f"no video files found in '{input_dir}' (supported: {sorted(VIDEO_EXTENSIONS)})")
    return sorted(files, key=lambda p: natural_key(os.path.basename(p)))


def probe_duration(ffprobe, path):
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip())
    except Exception:
        return None


def atempo_chain(multiplier):
    """Build an ffmpeg atempo chain for an arbitrary speed multiplier (>1)."""
    parts = []
    remaining = multiplier
    while remaining > 2.0:
        parts.append("atempo=2")
        remaining /= 2.0
    if remaining > 1.0:
        parts.append(f"atempo={remaining:.6f}")
    return ",".join(parts)


def build_ffmpeg_command(cfg, inputs, out_path, dry_run):
    clips = int(cfg.get("clips_per_short", 3))
    if clips < 1:
        die("clips_per_short must be at least 1")
    if len(inputs) != clips:
        die(f"expected {clips} inputs per short, got {len(inputs)}")

    speed = float(cfg.get("speed_multiplier", 100))
    seg = float(cfg.get("segment_seconds", 10))
    width = int(cfg.get("frame_width", 1080))
    height = int(cfg.get("frame_height", 1920))
    slice_h = height // clips
    fps = cfg.get("fps", 30)
    preset = cfg.get("preset", "medium")
    crf = cfg.get("crf", 18)
    keep_audio = bool(cfg.get("keep_audio", False))

    cmd = ["ffmpeg", "-y"]
    for path in inputs:
        cmd += ["-i", path]

    filters = []
    for i in range(clips):
        filters.append(
            f"[{i}:v]setpts=PTS/{speed},"
            f"scale={width}:{slice_h}:force_original_aspect_ratio=increase,"
            f"crop={width}:{slice_h},"
            f"format=yuv420p[v{i}]"
        )
    layout = "|".join(f"0_{row * slice_h}" for row in range(clips))
    filters.append(f"[{']['.join(f'v{i}' for i in range(clips))}]"
                   f"xstack=inputs={clips}:layout={layout}[vout]")

    if keep_audio:
        chain = atempo_chain(speed)
        if chain:
            filters.append(f"[0:a]{chain}[aout]")

    cmd += ["-filter_complex", ";".join(filters)]
    cmd += ["-map", "[vout]"]
    if keep_audio:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]
    cmd += ["-t", str(seg), "-r", str(fps),
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p", out_path]
    return cmd


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    force = "--force" in args

    cfg = load_config()
    speed = float(cfg.get("speed_multiplier", 100))
    seg = float(cfg.get("segment_seconds", 10))
    clips = int(cfg.get("clips_per_short", 3))

    input_dir = os.path.join(HERE, cfg.get("input_dir", "recordings"))
    output_dir = os.path.join(HERE, cfg.get("output_dir", "composited"))

    inputs = list_inputs(input_dir)
    if len(inputs) < clips:
        die(f"need at least {clips} recordings to make one short; found {len(inputs)} in '{input_dir}'")

    ffmpeg = None
    ffprobe = None
    if not dry_run:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            die("ffmpeg was not found on your PATH. Install it first:\n"
                "  Windows: winget install ffmpeg\n"
                "  macOS:   brew install ffmpeg\n"
                "  or grab it from https://ffmpeg.org/download.html")
        ffprobe = shutil.which("ffprobe")

    os.makedirs(output_dir, exist_ok=True)

    groups = [inputs[i:i + clips] for i in range(0, len(inputs), clips)]
    if len(groups[-1]) < clips:
        print(f"NOTE: the last {len(groups[-1])} file(s) don't form a full group of {clips}; skipping them.")
        groups = groups[:-1]

    manifest = []
    for idx, group in enumerate(groups, start=1):
        out_name = f"short_{idx:03d}.mp4"
        out_path = os.path.join(output_dir, out_name)
        if os.path.exists(out_path) and not force:
            print(f"skip  {out_name} (already exists; use --force to redo)")
            continue

        needed = seg * speed
        for p in group:
            dur = probe_duration(ffprobe, p) if ffprobe else None
            if dur is not None and dur < needed:
                print(f"  WARNING: {os.path.basename(p)} is {dur:.0f}s long, "
                      f"but {out_name} needs {needed:.0f}s of source at {speed:.0g}x "
                      f"to fill {seg:.0f}s. Output will be shorter.")

        cmd = build_ffmpeg_command(cfg, group, out_path, dry_run)
        if dry_run:
            print(" ".join(cmd))
            print()
        else:
            print(f"make  {out_name}  <-  " + ", ".join(os.path.basename(p) for p in group))
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(result.stderr[-2000:])
                die(f"ffmpeg failed for {out_name}")
        manifest.append({"short": out_name, "inputs": [os.path.basename(p) for p in group]})

    if dry_run:
        print(f"DRY RUN - {len(groups)} short(s) would be built into '{output_dir}'")
    else:
        with open(os.path.join(output_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        print(f"\nDone: {len(manifest)} short(s) written to '{output_dir}'")
        print("Next step: run the Premiere Pro script (see README.md) to assemble "
              "these into a 9:16 sequence and export.")


if __name__ == "__main__":
    main()
