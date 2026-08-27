# Contentfarming — sequential 45s shorts

Cuts raw footage into upload-ready shorts. No intermediate files, no stacking.

## The flow

```
raw/                <- drop raw footage here (any time)
   |  python build_shorts.py --watch
   v
shorts/             s001.mp4 = 0-45s
                    s002.mp4 = 45-90s
                    s003.mp4 = 90-135s ...
```

Every raw file is sliced into `short_seconds` (default **45s**) blocks, cut in
playback order and named `s001`, `s002`, ... The final block keeps whatever
time is left, even if shorter than 45s.

Each short is normalized to `frame_width` x `frame_height` (default
1080 x 1920 vertical, `fit: cover` crops the sides of landscape footage),
real-time speed, audio kept.

## Run it

```bash
python build_shorts.py             # process what's new, then exit
python build_shorts.py --watch     # keep running; pick up new files automatically
python build_shorts.py --dry-run   # preview only, writes nothing
python build_shorts.py --force     # rebuild everything from scratch
```

Requires ffmpeg + ffprobe on PATH (`winget install ffmpeg`).

## Settings (`config.json`)

| Setting | What it does |
|---|---|
| `raw_dir` / `output_dir` | Folders for footage and finished shorts (relative to this script). |
| `short_seconds` | Length of each short. Default `45`. |
| `frame_width` / `frame_height` | Output size. Default `1080` x `1920`. |
| `fit` | `cover`: fill frame, crop edges. `contain`: whole frame visible with bars. |
| `fps` | Output frame rate. Default `30`. |
| `preset` / `crf` | x264 speed/quality. Defaults `veryfast` / `20`. |
| `keep_audio` | Keep the source audio. Default `true`. |
| `max_workers` | Parallel encodes. Default `2`. |
| `skip_files` | Exact filenames to never process. |

## State

`shorts/manifest.json` remembers which raw files were already cut (and where
each short came from). Re-runs only touch new footage. Use `--force` to start
over.
