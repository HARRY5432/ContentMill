#!/usr/bin/env python3
"""
build_shorts.py
===============
Autonomous "3-up shorts" pipeline. No Premiere needed.

For every group of N input recordings (N = clips_per_short, default 3) it:
  1. speeds each clip up by speed_multiplier (default 100x = 10000%),
  2. scales + center-crops each clip to fill one vertical slice of the frame
     (frame_height / clips_per_short tall),
  3. stacks the clips top -> middle -> bottom into one 9:16 frame (xstack),
     rows touching so there are no black gaps between them,
  4. trims the result to segment_seconds (default 10s),
  5. writes composited/short_001.mp4, short_002.mp4, ... — each one is a
     finished, upload-ready short.

Nothing is wasted:
  - Every group keeps producing consecutive shorts until its footage runs out
    (segments = "full", the default). When a clip runs out it drops out of the
    stack and shorts continue with the remaining clips (3-up -> 2-up ->
    full-frame), so even clips of very different lengths are fully used.
  - Leftover files that don't form a full group become a smaller stacked short
    (2 files -> 2-up, 1 file -> full-frame) instead of being skipped.

Two ways to run:

  python build_shorts.py             # process everything once
  python build_shorts.py --watch     # keep running; make shorts automatically
                                     # whenever new recordings appear

It remembers what it already processed (composited/manifest.json), so re-runs
only handle new files and you can add clips to the folder at any time.

Requires ffmpeg + ffprobe (both ship together) on your PATH.
  Windows:  winget install ffmpeg   (or https://ffmpeg.org/download.html)
  macOS:    brew install ffmpeg

Other flags:
  --dry-run  print the ffmpeg commands without running them
  --force    re-process everything, overwriting existing shorts
"""

import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".mxf", ".ts", ".webm", ".m4v"}

WATCH_POLL_SECONDS = 10   # how often --watch rescans the input folder
STABILITY_CHECK_SECONDS = 2  # how long a file's size must stop changing before we use it


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


def list_inputs(input_dir, strict=True, skip=None):
    """List usable recordings. `skip` is a set of exact filenames to ignore."""
    skip = skip or set()
    if not os.path.isdir(input_dir):
        if strict:
            die(
                f"input folder '{input_dir}' not found. "
                f"Create it and put your recordings in it (or edit config.json)."
            )
        return []
    files = [
        os.path.join(input_dir, n)
        for n in os.listdir(input_dir)
        if os.path.splitext(n)[1].lower() in VIDEO_EXTENSIONS and n not in skip
    ]
    if not files and strict:
        die(f"no video files found in '{input_dir}' (supported: {sorted(VIDEO_EXTENSIONS)})")
    return sorted(files, key=lambda p: natural_key(os.path.basename(p)))


def manifest_path(output_dir):
    return os.path.join(output_dir, "manifest.json")


def load_manifest(output_dir):
    p = manifest_path(output_dir)
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_manifest(output_dir, manifest):
    with open(manifest_path(output_dir), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def consumed_inputs(manifest):
    return {name for entry in manifest for name in entry.get("inputs", [])}


def probe_info(ffprobe, path):
    """Probe a file once. Returns (duration_seconds, width, height).

    Returns (None, None, None) if the file can't be read at all.
    """
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error",
             "-show_entries", "format=duration:stream=width,height,codec_type",
             "-of", "json", path],
            capture_output=True, text=True, timeout=60,
        )
        data = json.loads(out.stdout)
        dur = float(data["format"]["duration"])
        w = h = None
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                w = s.get("width")
                h = s.get("height")
                break
        return dur, w, h
    except Exception:
        return None, None, None


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


def build_ffmpeg_command(cfg, inputs, out_path, ffmpeg_bin="ffmpeg",
                         segment_start=0.0, segment_dur=None, dims=None):
    """Build the ffmpeg command for one short.

    `inputs` is the group of source clips (2 or 3 for a stacked short).
    `segment_start` seeks each input to that many seconds in, so one group can
    produce several consecutive shorts from different windows of the footage.
    `segment_dur` overrides the output length (used for the final, shorter
    segment so even the leftover tail of the footage is used).
    """
    clips = len(inputs)
    speed = float(cfg.get("speed_multiplier", 100))
    seg = float(cfg.get("segment_seconds", 10))
    if segment_dur is not None:
        seg = segment_dur
    width = int(cfg.get("frame_width", 1080))
    height = int(cfg.get("frame_height", 1920))
    slice_h = height // clips
    fps = cfg.get("fps", 30)
    preset = cfg.get("preset", "medium")
    crf = cfg.get("crf", 18)
    keep_audio = bool(cfg.get("keep_audio", False))

    cmd = [ffmpeg_bin, "-y"]
    for path in inputs:
        if segment_start > 0:
            cmd += ["-ss", str(segment_start)]
        cmd += ["-i", path]

    # how each clip fits its row:
    #   tight (default) - whole clip visible, rows touch (no black between rows)
    #   contain         - whole clip visible, each row padded (bars between rows)
    #   cover           - fills the slice completely, edges cropped
    fit = cfg.get("fit", "tight")

    # tight mode needs each source's dimensions; falls back to contain if unknown
    rows = None
    if fit == "tight" and dims and len(dims) == len(inputs) \
            and all(d and d[0] and d[1] for d in dims):
        rows = tight_layout(dims, width, height)

    def clip_chain(in_label, out_label, w, h):
        if rows is not None:
            return (f"[{in_label}:v]setpts=PTS/{speed},"
                    f"scale={w}:{h},format=yuv420p[{out_label}]")
        if fit == "cover":
            return (f"[{in_label}:v]setpts=PTS/{speed},"
                    f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                    f"crop={w}:{h},format=yuv420p[{out_label}]")
        return (f"[{in_label}:v]setpts=PTS/{speed},"
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:0x000000,format=yuv420p[{out_label}]")

    filters = []
    if clips == 1:
        if rows is not None:
            w, h = rows[0][2], rows[0][3]
            filters.append(f"[0:v]setpts=PTS/{speed},scale={w}:{h},format=yuv420p[vx]")
            filters.append(f"[vx]pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:0x000000[vout]")
        else:
            filters.append(clip_chain(0, "vout", width, height))
    elif rows is not None:
        for i, (x, y, w, h) in enumerate(rows):
            filters.append(clip_chain(i, f"v{i}", w, h))
        layout = "|".join(f"{x}_{y}" for (x, y, _, _) in rows)
        labels = "".join(f"[v{i}]" for i in range(clips))
        filters.append(f"{labels}xstack=inputs={clips}:layout={layout}:fill=0x000000[vx]")
        filters.append(f"[vx]pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:0x000000[vout]")
    else:
        for i in range(clips):
            filters.append(clip_chain(i, f"v{i}", width, slice_h))
        layout = "|".join(f"0_{row * slice_h}" for row in range(clips))
        labels = "".join(f"[v{i}]" for i in range(clips))
        filters.append(f"{labels}xstack=inputs={clips}:layout={layout}[vout]")

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


def build_one_short(cfg, group, idx, output_dir, ffmpeg, dry_run, force,
                    segment_start=0.0, segment_dur=None, dims=None):
    """Build short_XXX.mp4 from one group of clips (one segment). Manifest entry."""
    out_name = f"short_{idx:03d}.mp4"
    out_path = os.path.join(output_dir, out_name)

    if os.path.exists(out_path) and not force and not dry_run:
        print(f"skip  {out_name} (already exists; use --force to redo)")
        return {"short": out_name, "inputs": [os.path.basename(p) for p in group]}

    cmd = build_ffmpeg_command(cfg, group, out_path, ffmpeg or "ffmpeg",
                               segment_start, segment_dur, dims)
    if dry_run:
        print(" ".join(cmd))
        print()
        return {"short": out_name, "inputs": [os.path.basename(p) for p in group]}

    print(f"make  {out_name}  <-  " + ", ".join(os.path.basename(p) for p in group))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-2000:])
        die(f"ffmpeg failed for {out_name}")
    return {"short": out_name, "inputs": [os.path.basename(p) for p in group]}


def probe_all(ffprobe, paths):
    """Probe every path once. Returns (info_by_path, bad_paths).

    A path is 'bad' when ffprobe cannot read it at all (interrupted recording,
    truncated/corrupt file). Those can never be used, so they're skipped.
    """
    info, bad = {}, []
    for p in paths:
        dur, w, h = probe_info(ffprobe, p)
        if dur is None:
            bad.append(p)
        else:
            info[p] = (dur, w, h)
    return info, bad


def tight_layout(dims, frame_w, frame_h):
    """Compute (x, y, w, h) per clip so the rows touch with no black gaps.

    Each clip is scaled to fill its row width (keeping aspect, nothing cut),
    then the block of rows is centered vertically - so the middle row sits at
    the frame's center. Returns None if any clip's size is unknown.
    """
    n = len(dims)
    if n == 0 or any(d is None or d[0] is None or d[1] is None for d in dims):
        return None
    max_h = frame_h // n
    sized = []
    for (sw, sh) in dims:
        scale = min(frame_w / sw, max_h / sh)
        w = max(2, int(round(sw * scale / 2) * 2))
        h = max(2, int(round(sh * scale / 2) * 2))
        sized.append((w, h))
    total_h = sum(h for (_, h) in sized)
    y = (frame_h - total_h) // 2
    rows = []
    for (w, h) in sized:
        x = (frame_w - w) // 2
        rows.append((x, y, w, h))
        y += h
    return rows


def plan_windows(cfg, group, durations, ffprobe):
    """Return a list of (start_seconds, output_duration, clips_used) for a group.

    With segments="full" (default) and known durations, the group's footage is
    consumed window by window: each window becomes one short, and when a clip
    runs out it drops out of the stack so shorts continue with the remaining
    clips. The result uses every second of every clip, even when the clips have
    very different lengths.
    """
    seg = float(cfg.get("segment_seconds", 10))
    speed = float(cfg.get("speed_multiplier", 100))
    needed = seg * speed

    known = ffprobe is not None and all(d is not None for d in durations)
    if cfg.get("segments", "full") != "full" or not known:
        return [(0.0, seg, list(group))]

    alive = [(p, d) for p, d in zip(group, durations)]
    windows = []
    t = 0.0
    while alive:
        remaining = [d - t for (_, d) in alive]
        min_rem = min(remaining)
        if min_rem <= 0.5:
            break
        window = min(needed, min_rem)
        windows.append((t, window / speed, [p for (p, _) in alive]))
        t += window
        alive = [(p, d) for (p, d) in alive if d - t > 0.5]
    if not windows:  # safety: tiny/unknown edge case, still make one short
        windows = [(0.0, seg, list(group))]
    return windows


def process_pending(cfg, input_dir, output_dir, manifest, ffmpeg, ffprobe,
                    dry_run, force, watch, warned=None):
    """Build shorts from every not-yet-used group of clips. Returns new manifest."""
    skip = set(cfg.get("skip_files", []))
    inputs = list_inputs(input_dir, strict=not watch, skip=skip)
    if not inputs:
        return manifest

    clips = int(cfg.get("clips_per_short", 3))
    if force and not watch:
        manifest = []  # full rebuild: discard old entries, restart at short_001
    consumed = set() if (force and not watch) else consumed_inputs(manifest)
    pending = [p for p in inputs if os.path.basename(p) not in consumed]

    if not pending:
        return manifest

    if warned is None:
        warned = set()

    # drop files ffmpeg can't read (interrupted recordings, corrupt files)
    if ffprobe:
        info_map, bad = probe_all(ffprobe, pending)
        for p in bad:
            if p not in warned:
                print(f"SKIP {os.path.basename(p)}: cannot read this file - it looks like an "
                      f"unfinished or corrupt recording. Re-record or delete it. "
                      f"(If it was still being recorded, use --watch so in-progress "
                      f"files are skipped automatically.)")
                warned.add(p)
        pending = [p for p in pending if p not in set(bad)]
        if not pending:
            return manifest
    else:
        info_map = {p: None for p in pending}

    # group pending clips; a leftover partial group is either waited on
    # (watch mode) or used as a smaller stacked short (one-shot mode)
    groups = [pending[i:i + clips] for i in range(0, len(pending), clips)]
    if len(groups[-1]) < clips:
        leftover = groups.pop()
        if watch:
            print(f"NOTE: {len(leftover)} new file(s) don't form a full group of {clips}; "
                  f"leaving them for the next check.")
        elif cfg.get("allow_partial_groups", True):
            print(f"NOTE: using the last {len(leftover)} file(s) as a {len(leftover)}-up short "
                  f"so nothing is left behind.")
            groups.append(leftover)
        else:
            print(f"NOTE: the last {len(leftover)} file(s) don't form a full group of {clips}; skipping them.")

    next_idx = len(manifest) + 1
    seg = float(cfg.get("segment_seconds", 10))
    speed = float(cfg.get("speed_multiplier", 100))
    for group in groups:
        durations = [info_map[p][0] if info_map.get(p) else None for p in group]
        dims_map = {p: (info_map[p][1], info_map[p][2]) for p in group if info_map.get(p)}
        windows = plan_windows(cfg, group, durations, ffprobe)
        prev_count = len(group)
        for (start, dur, clips_now) in windows:
            if len(clips_now) < prev_count:
                print(f"NOTE: a clip ran out after {start:.0f}s of footage - continuing "
                      f"with {len(clips_now)} clip(s) so nothing is wasted.")
                prev_count = len(clips_now)
            if dur < seg:
                print(f"NOTE: this stretch uses the final {dur * speed:.0f}s of footage "
                      f"-> short will be {dur:.1f}s.")
            dims_now = [dims_map.get(p) for p in clips_now]
            entry = build_one_short(cfg, clips_now, next_idx, output_dir, ffmpeg,
                                    dry_run, force, segment_start=start, segment_dur=dur,
                                    dims=dims_now)
            manifest.append(entry)
            next_idx += 1

    if not dry_run:
        save_manifest(output_dir, manifest)
    return manifest


def file_is_stable(path):
    """True once the file's size stops changing (i.e. it isn't being recorded/copied)."""
    try:
        size1 = os.path.getsize(path)
        time.sleep(STABILITY_CHECK_SECONDS)
        size2 = os.path.getsize(path)
        return size1 == size2
    except OSError:
        return False


def watch_loop(cfg, input_dir, output_dir, ffmpeg, ffprobe, dry_run):
    os.makedirs(output_dir, exist_ok=True)
    manifest = load_manifest(output_dir)
    print(f"Watching '{input_dir}' ... every {cfg.get('clips_per_short', 3)} new recordings "
          f"become shorts in '{output_dir}'")
    print("Drop clips in any time. Press Ctrl+C to stop.\n")
    try:
        skip = set(cfg.get("skip_files", []))
        warned = set()
        while True:
            inputs = list_inputs(input_dir, strict=False, skip=skip)
            if inputs:
                pending = [p for p in inputs
                           if os.path.basename(p) not in consumed_inputs(manifest)
                           and file_is_stable(p)]
                if pending:
                    manifest = process_pending(cfg, input_dir, output_dir, manifest,
                                               ffmpeg, ffprobe, dry_run, force=False,
                                               watch=True, warned=warned)
            time.sleep(WATCH_POLL_SECONDS)
    except KeyboardInterrupt:
        print(f"\nStopped. {len(manifest)} short(s) built so far in '{output_dir}'.")


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    force = "--force" in args
    watch = "--watch" in args

    cfg = load_config()
    input_dir = os.path.join(HERE, cfg.get("input_dir", "recordings"))
    output_dir = os.path.join(HERE, cfg.get("output_dir", "composited"))
    os.makedirs(output_dir, exist_ok=True)

    ffmpeg = None
    ffprobe = None
    if not dry_run:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            die("ffmpeg was not found on your PATH. Install it first:\n"
                "  Windows: winget install ffmpeg\n"
                "  macOS:   brew install ffmpeg\n"
                "  or grab it from https://ffmpeg.org/download.html")
        ffmpeg = os.path.abspath(ffmpeg)
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            print("NOTE: ffprobe not found - cannot measure clip lengths, so each group "
                  "will produce one short. ffprobe ships with ffmpeg.")

    manifest = load_manifest(output_dir)

    if watch:
        watch_loop(cfg, input_dir, output_dir, ffmpeg, ffprobe, dry_run)
        return

    manifest = process_pending(cfg, input_dir, output_dir, manifest,
                               ffmpeg, ffprobe, dry_run, force, watch=False)

    if dry_run:
        print(f"DRY RUN - would process pending files in '{input_dir}'")
    else:
        print(f"\nDone: {len(manifest)} short(s) in '{output_dir}'")
        print("Grab the short_*.mp4 files - each one is a finished, upload-ready short.")


if __name__ == "__main__":
    main()
