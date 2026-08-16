# 3-up Shorts Pipeline

Turns your screen recordings into **9:16 vertical shorts automatically**:

- Each short = **3 clips playing at once**, stacked vertically (top / middle / bottom thirds)
- Every clip is sped up **10,000% (100×)**
- Each short is **10 seconds** long
- A Premiere Pro script then assembles them into a **1080×1920 timeline** and can auto-export

The heavy lifting (speed + layout) happens in **ffmpeg** so it's fast and reliable; the
Premiere script just creates the sequence, imports the finished clips, and places them.

## How it works

```
recordings/          your raw recordings (any order; every 3 files = 1 short)
   │
   │  python build_shorts.py          ← speeds 100x, stacks 3-up, trims to 10s
   ▼
composited/          short_001.mp4, short_002.mp4, ...  (already 1080x1920, 3 rows)
   │
   │  process_shorts.jsx in Premiere  ← creates 9:16 sequence, imports, places, exports
   ▼
Finished 9:16 sequence (one short after another, 10s each)
```

## 1. Install once

1. **Install ffmpeg** (the only dependency — Python comes with most systems, or install it):
   - Windows: `winget install ffmpeg` (or https://ffmpeg.org/download.html)
   - macOS: `brew install ffmpeg`
   - Verify with `ffmpeg -version`.
2. **Put your recordings** in the `recordings/` folder. Supported: `.mp4 .mov .mkv .avi .mxf .ts .webm .m4v`.
   - Files are processed in name order, **every 3 files = one short** (file1+2+3 → short_001, 4+5+6 → short_002, …).
   - The 3 files of a short play **at the same time** — they show the same 10 seconds of
     your session from three recordings (e.g. three screens, or three takes).

## 2. Batch step (terminal)

```bash
python build_shorts.py
```

That creates `composited/short_001.mp4` etc. Run `python build_shorts.py --dry-run`
to preview the ffmpeg commands, or `--force` to redo existing outputs.

> **Duration math:** at 100× speed, a 10-second short consumes **1,000 seconds (~17 min)**
> of recording per input. If a recording is shorter, the short comes out shorter — the
> script warns you about this.

## 3. Assemble in Premiere Pro

1. Copy `premiere/process_shorts.jsx` to Premiere's ScriptUI Panels folder:
   - Windows: `C:\Program Files\Adobe\Adobe Premiere Pro <version>\Support Files\Scripts\ScriptUI Panels\`
   - macOS: `/Applications/Adobe Premiere Pro <version>/Adobe Premiere Pro <version>.app/Contents/Support Files/Scripts/ScriptUI Panels/`
2. Restart Premiere, open (or create) a project.
3. Edit `CONFIG_PATH` at the top of `premiere/process_shorts.jsx` to point at this folder
   (the one with `config.json`). If you leave it empty, Premiere will ask you to pick the
   folder each run.
4. Click **Window > Extensions > process_shorts**. Done: a new `Shorts …` sequence appears
   with all your shorts placed back-to-back.

## Optional: templates & auto-export

Open `config.json`:

| Setting | What it does |
|---|---|
| `sequence_preset` | Path to a saved sequence template (`.sqpreset`). Save one in Premiere: **File > New > Sequence… > Save Preset**, then point here. Leave empty to use a default 1080×1920 sequence. |
| `export_preset` | Path to a saved export preset (`.epr`). Save one via **File > Export > Media > Preset > Save Preset**. When set, the Premiere script exports each timeline automatically. |
| `speed_multiplier` | Default `100` (= 10,000%). |
| `segment_seconds` | Length of each short. Default `10`. |
| `clips_per_short` | Rows in the stack. Default `3`. |
| `keep_audio` | Default `false` — at 100× audio is useless. Set `true` to keep the first clip's audio (also sped up). |

Relative paths in config.json are resolved from this folder.

## Notes & limits

- **Speed is baked in by ffmpeg** — Premiere's script API cannot set clip speed (it can only
  read it), so the speedup happens before clips ever reach Premiere. This also means no
  per-clip `Speed/Duration` work in the timeline.
- The 3-row layout is done with ffmpeg's `xstack` filter; clips are center-cropped to fill
  each slice, so a little of the left/right edge of wide recordings is cut off.
- Premiere's ExtendScript system is supported through **September 2026** (Adobe is moving to
  UXP); this pipeline works fine in current Premiere versions.
