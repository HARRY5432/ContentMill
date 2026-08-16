# Autoclip — autonomous 9:16 shorts

Turns your screen recordings into **finished, upload-ready vertical shorts — automatically, no Premiere Pro needed.**

- Each short = **3 clips playing at once**, stacked vertically (top / middle / bottom thirds)
- Every clip is sped up **10,000% (100×)**
- Each short is **10 seconds** long, 1080×1920 (9:16)
- Drop clips into a folder, and shorts come out the other end, one by one

## How it works

```
recordings/          ← you drop your recordings here (any time, any amount)
   │
   │  python build_shorts.py --watch     ← runs in the background
   ▼
composited/          short_001.mp4, short_002.mp4, ...  ← finished shorts
```

Every **3 recordings = 1 short** (file1+2+3 → short_001, 4+5+6 → short_002, …).
The 3 clips of a short play **at the same time** — they show the same 10 seconds
from three recordings (e.g. three screens or three takes).

The script remembers what it already processed (`composited/manifest.json`), so it
only ever works on new clips. You can add files mid-run and it picks them up.

## 1. Install once

1. **Install ffmpeg** (the only dependency — Python ships with most systems, or install it):
   - Windows: `winget install ffmpeg` (or https://ffmpeg.org/download.html)
   - macOS: `brew install ffmpeg`
   - Verify with `ffmpeg -version`.
2. Put your recordings in the `recordings/` folder. Supported: `.mp4 .mov .mkv .avi .mxf .ts .webm .m4v`.

## 2. Run it

**Watch mode (recommended)** — leave this running, drop clips in anytime:

```bash
python build_shorts.py --watch
```

Every time 3 new recordings finish appearing, it builds the next short and keeps
waiting. Press `Ctrl+C` to stop.

**One-shot mode** — process whatever's new right now and exit:

```bash
python build_shorts.py
```

Other flags: `--dry-run` (preview commands), `--force` (rebuild everything).

## 3. Grab your shorts

Finished shorts appear in `composited/` — `short_001.mp4`, `short_002.mp4`, …
Each one is a complete 1080×1920 video, ready to upload.

> **Duration math:** at 100× speed, a 10-second short consumes **1,000 seconds (~17 min)**
> of recording per input. If a recording is shorter, the short comes out shorter — the
> script warns you about this.

## Settings

Open `config.json`:

| Setting | What it does |
|---|---|
| `speed_multiplier` | Default `100` (= 10,000%). |
| `segment_seconds` | Length of each short. Default `10`. |
| `clips_per_short` | Rows in the stack. Default `3`. |
| `frame_width` / `frame_height` | Output resolution. Default `1080` × `1920`. |
| `keep_audio` | Default `false` — at 100× audio is useless. Set `true` to keep the first clip's audio (also sped up). |

## Notes & limits

- **Speed and layout are baked in by ffmpeg**, so the output is a plain video file —
  no editing program involved at all.
- The 3-row layout is done with ffmpeg's `xstack` filter; clips are center-cropped to
  fill each slice, so a little of the left/right edge of wide recordings is cut off.
- A file is only used once a recording/copy of it has finished (the script waits until
  its size stops changing), so it's safe to drop clips while they're still being written.
- If you ever want to assemble multiple shorts into one timeline with titles/music,
  there's an optional `premiere/process_shorts.jsx` script in this repo — but you don't
  need it for the basic flow.
