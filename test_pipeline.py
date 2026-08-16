#!/usr/bin/env python3
"""
Tests for build_shorts.py — no ffmpeg needed (it's faked in-process).

Run with:  python test_pipeline.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

import build_shorts as bs

REAL_CONFIG_PATH = os.path.abspath(bs.CONFIG_PATH)  # snapshot before tests monkeypatch it
ORIG_STABILITY_CHECK = bs.file_is_stable


def fake_run(cmd, capture_output=False, text=False):
    """Pretend ffmpeg ran: create the output file (last arg), record the cmd."""
    out = cmd[-1]
    with open(out, "w") as f:
        f.write("fake")
    fake_run.CMDS.append(cmd)
    return types.SimpleNamespace(returncode=0, stdout="", stderr="")


fake_run.CMDS = []


def make_files(folder, names):
    for n in names:
        with open(os.path.join(folder, n), "w") as f:
            f.write("x")


def load_real_config():
    with open(REAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def setup():
    """Temp project with a config.json and recordings/ folder."""
    tmp = tempfile.mkdtemp(prefix="autoclip_test_")
    cfg = load_real_config()
    with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    os.makedirs(os.path.join(tmp, "recordings"), exist_ok=True)
    return tmp


def run_pending(tmp, names, ffprobe=None, watch=False, extra_cfg=None):
    """Process the given files in a fresh temp project; returns (manifest, out_dir)."""
    rec = os.path.join(tmp, "recordings")
    out = os.path.join(tmp, "composited")
    os.makedirs(out, exist_ok=True)
    make_files(rec, names)
    bs.HERE = tmp
    bs.CONFIG_PATH = os.path.join(tmp, "config.json")
    bs.subprocess.run = fake_run
    if extra_cfg:
        with open(bs.CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.update(extra_cfg)
        with open(bs.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    manifest = bs.process_pending(bs.load_config(), rec, out, [], None, ffprobe,
                                  dry_run=False, force=False, watch=watch)
    return manifest, out


def test_one_shot_rounds_of_three():
    tmp = setup()
    manifest, out = run_pending(tmp, ["a01.mp4", "a02.mp4", "a03.mp4",
                                      "a04.mp4", "a05.mp4", "a06.mp4"])
    assert len(manifest) == 2, f"expected 2 shorts, got {len(manifest)}"
    assert manifest[0]["short"] == "short_001.mp4"
    assert manifest[0]["inputs"] == ["a01.mp4", "a02.mp4", "a03.mp4"], manifest[0]
    assert manifest[1]["inputs"] == ["a04.mp4", "a05.mp4", "a06.mp4"], manifest[1]
    assert os.path.exists(os.path.join(out, "short_001.mp4"))
    assert os.path.exists(os.path.join(out, "short_002.mp4"))
    print("PASS one-shot: 6 files -> 2 shorts, grouped in threes")
    shutil.rmtree(tmp)


def test_incremental_adds_only_new_files():
    tmp = setup()
    manifest, out = run_pending(tmp, ["b01.mp4", "b02.mp4", "b03.mp4"])
    assert len(manifest) == 1
    manifest, out = run_pending(tmp, ["b04.mp4", "b05.mp4", "b06.mp4"])
    assert len(manifest) == 2, f"expected 2 shorts after re-run, got {len(manifest)}"
    assert manifest[1]["inputs"] == ["b04.mp4", "b05.mp4", "b06.mp4"]
    assert os.path.exists(os.path.join(out, "short_002.mp4"))
    print("PASS incremental: re-run only processes new clips")
    shutil.rmtree(tmp)


def test_watch_builds_group_and_waits_for_rest():
    tmp = setup()
    manifest, out = run_pending(tmp, ["c01.mp4", "c02.mp4", "c03.mp4", "c04.mp4"],
                                watch=True)
    # 4 new files: first 3 become a short, the 4th waits
    assert len(manifest) == 1, f"expected 1 short from 4 files, got {len(manifest)}"
    assert manifest[0]["inputs"] == ["c01.mp4", "c02.mp4", "c03.mp4"]
    manifest, out = run_pending(tmp, ["c05.mp4", "c06.mp4"], watch=True)
    assert len(manifest) == 2, f"expected 2 shorts, got {len(manifest)}"
    assert manifest[1]["inputs"] == ["c04.mp4", "c05.mp4", "c06.mp4"]
    print("PASS watch: builds full groups, waits for partial groups")
    shutil.rmtree(tmp)


def test_segments_use_full_footage():
    tmp = setup()
    fake_run.CMDS = []
    # 2500s (~42 min) clips -> 3 segments: 0-1000, 1000-2000, 2000-2500 (last = 5s)
    orig_probe = bs.probe_duration
    bs.probe_duration = lambda ffprobe, path: 2500.0
    try:
        manifest, out = run_pending(tmp, ["d01.mp4", "d02.mp4", "d03.mp4"],
                                    ffprobe=object())
    finally:
        bs.probe_duration = orig_probe
    assert len(manifest) == 3, f"expected 3 segments, got {len(manifest)}"
    for entry in manifest:
        assert entry["inputs"] == ["d01.mp4", "d02.mp4", "d03.mp4"], entry
    cmds = fake_run.CMDS
    assert "-ss" not in cmds[0], "first segment should start at 0"
    assert "-ss" in cmds[1] and "1000.0" in cmds[1], "second segment should seek to 1000s"
    assert "-ss" in cmds[2] and "2000.0" in cmds[2], "third segment should seek to 2000s"
    assert "-t" in cmds[2] and "5.0" in cmds[2], "last segment should use the 5s tail"
    print("PASS segments: one group -> 3 shorts covering all footage (incl. tail)")
    shutil.rmtree(tmp)


def test_cascade_uses_mismatched_lengths():
    tmp = setup()
    fake_run.CMDS = []
    # d01 = 2500s, d02 = 1500s, d03 = 4000s -> windows:
    #  0-1000 (3-up), 1000-1500 (3-up, 5s), 1500-2500 (2-up),
    #  2500-3500 (full-frame), 3500-4000 (full-frame, 5s)
    durations = {"d01.mp4": 2500.0, "d02.mp4": 1500.0, "d03.mp4": 4000.0}
    orig_probe = bs.probe_duration
    bs.probe_duration = lambda ffprobe, path: durations[os.path.basename(path)]
    try:
        manifest, out = run_pending(tmp, ["d01.mp4", "d02.mp4", "d03.mp4"],
                                    ffprobe=object())
    finally:
        bs.probe_duration = orig_probe
    assert len(manifest) == 5, f"expected 5 shorts, got {len(manifest)}"
    counts = [len(e["inputs"]) for e in manifest]
    assert counts == [3, 3, 2, 1, 1], counts
    assert manifest[2]["inputs"] == ["d01.mp4", "d03.mp4"], manifest[2]
    assert manifest[4]["inputs"] == ["d03.mp4"], manifest[4]
    cmd1 = " ".join(fake_run.CMDS[3])  # first full-frame short
    assert "scale=1080:1920" in cmd1 and "xstack=inputs=1:layout=0_0" in cmd1, cmd1
    print("PASS cascade: mismatched clip lengths fully used (3-up -> 2-up -> full-frame)")
    shutil.rmtree(tmp)


def test_partial_group_becomes_2up():
    tmp = setup()
    fake_run.CMDS = []
    manifest, out = run_pending(tmp, ["e01.mp4", "e02.mp4"])
    assert len(manifest) == 1, f"expected 1 short from 2 files, got {len(manifest)}"
    assert manifest[0]["inputs"] == ["e01.mp4", "e02.mp4"]
    cmd = " ".join(fake_run.CMDS[0])
    assert "scale=1080:960" in cmd, "2-up short should use half-height slices"
    assert "xstack=inputs=2:layout=0_0|0_960" in cmd, cmd
    print("PASS partial: 2 leftover files -> 2-up short, nothing wasted")
    shutil.rmtree(tmp)


def test_stability_check():
    bs.file_is_stable = ORIG_STABILITY_CHECK  # undo the watch-test monkeypatch
    tmp = tempfile.mkdtemp(prefix="autoclip_stab_")
    p = os.path.join(tmp, "stable.mp4")
    with open(p, "w") as f:
        f.write("done")
    assert bs.file_is_stable(p) is True, "finished file should be stable"

    q = os.path.join(tmp, "growing.mp4")
    with open(q, "w") as f:
        f.write("a")
    # simulate a file still being written: it changes size between checks
    orig = bs.time.sleep
    try:
        calls = {"n": 0}
        def fake_sleep(sec):
            calls["n"] += 1
            with open(q, "a") as f:
                f.write("more data")
        bs.time.sleep = fake_sleep
        assert bs.file_is_stable(q) is False, "growing file should be unstable"
    finally:
        bs.time.sleep = orig
    print("PASS stability: growing files are detected and skipped")
    shutil.rmtree(tmp)


if __name__ == "__main__":
    test_one_shot_rounds_of_three()
    test_incremental_adds_only_new_files()
    test_watch_builds_group_and_waits_for_rest()
    test_segments_use_full_footage()
    test_cascade_uses_mismatched_lengths()
    test_partial_group_becomes_2up()
    test_stability_check()
    print("\nAll tests passed.")
