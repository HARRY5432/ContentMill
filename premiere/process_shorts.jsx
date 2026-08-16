// process_shorts.jsx
// ==================
// Second half of the "3-up shorts" pipeline.
//
// What it does, in one click:
//   1. Creates a new 9:16 sequence (from your saved .sqpreset template if
//      you set sequence_preset in config.json, otherwise a 1080x1920 default).
//   2. Imports every composited short from the output_dir (short_001.mp4, ...).
//   3. Places them back-to-back on video track 1, in order.
//   4. Optionally exports the finished sequence with your .epr export preset
//      (set export_preset in config.json).
//
// The clips come out of build_shorts.py already sped up (100x) and already
// stacked into the 9:16 3-row layout, so no per-clip work is needed here.
//
// HOW TO INSTALL / RUN
// --------------------
// Option A (recommended): copy this file into Premiere's ScriptUI Panels folder
//   Windows: C:\Program Files\Adobe\Adobe Premiere Pro <version>\Support Files\Scripts\ScriptUI Panels\
//   macOS:   /Applications/Adobe Premiere Pro <version>/Adobe Premiere Pro <version>.app/Contents/Support Files/Scripts/ScriptUI Panels/
//   Restart Premiere, open your project, then:  Window > Extensions > process_shorts
//
// Option B: run it from the ExtendScript Toolkit / VS Code ExtendScript Debugger
//   (older Premiere versions ship the toolkit; newer ones need the VS Code extension).
//
// Before first run: set CONFIG_PATH below to your shorts-pipeline folder
// (the one containing config.json and build_shorts.py). Leave it empty and
// you'll be asked to pick the folder each time.

#target premierepro

var CONFIG_PATH = ""; // e.g. "C:/Users/you/shorts-pipeline/config.json"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function readConfig() {
    var f = new File(CONFIG_PATH);
    if (!f.exists) {
        var folder = Folder.selectDialog("Select your shorts-pipeline folder (the one with config.json)");
        if (!folder) return null;
        f = new File(folder.fsName + "/config.json");
        if (!f.exists) {
            alert("No config.json found in " + folder.fsName);
            return null;
        }
    }
    f.open("r");
    var text = f.read();
    f.close();
    try {
        return JSON.parse(text);
    } catch (e) {
        // Very old ExtendScript engines have no JSON.parse; config is local,
        // so eval'ing it is acceptable here.
        try {
            return eval("(" + text + ")");
        } catch (e2) {
            alert("Could not parse config.json: " + e2);
            return null;
        }
    }
}

function configFolder() {
    return new Folder(CONFIG_PATH).parent;
}

function resolvePath(cfg, key) {
    var raw = cfg[key];
    if (!raw) return "";
    var p = new File(raw);
    if (!p.exists && !/^[A-Za-z]:[\\\/]/.test(raw) && raw.indexOf("/") !== 0) {
        // treat as relative to the pipeline folder
        p = new File(configFolder().fsName + "/" + raw);
    }
    return p.exists ? p.fsName : "";
}

function listCompositedShorts(outputDir) {
    var folder = new Folder(outputDir);
    if (!folder.exists) return [];
    var files = folder.getFiles("*.mp4");
    var out = [];
    for (var i = 0; i < files.length; i++) {
        var name = files[i].name;
        if (name.indexOf("short_") === 0) out.push(files[i]);
    }
    out.sort(function (a, b) { return a.name < b.name ? -1 : 1; });
    return out;
}

function findProjectItem(root, name) {
    if (!root || !root.children) return null;
    var kids = root.children;
    for (var i = 0; i < kids.length; i++) {
        var kid = kids[i];
        if (kid.name === name) return kid;
        var found = findProjectItem(kid, name);
        if (found) return found;
    }
    return null;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
    if (!app.project) {
        alert("Open a Premiere project first (or create a new one).");
        return;
    }

    var cfg = readConfig();
    if (!cfg) return;

    var outputDir = resolvePath(cfg, "output_dir");
    if (!outputDir) outputDir = configFolder().fsName + "/" + (cfg.output_dir || "composited");
    var shorts = listCompositedShorts(outputDir);
    if (shorts.length === 0) {
        alert("No short_*.mp4 files found in\n" + outputDir +
              "\n\nRun build_shorts.py first (see README.md), then try again.");
        return;
    }

    // 1. Create the 9:16 sequence ------------------------------------------
    var stamp = new Date();
    var seqName = "Shorts " +
        stamp.getFullYear() + "-" + pad(stamp.getMonth() + 1) + "-" + pad(stamp.getDate()) +
        " " + pad(stamp.getHours()) + "." + pad(stamp.getMinutes());

    var seq = null;
    var preset = resolvePath(cfg, "sequence_preset");
    if (preset) {
        seq = app.project.newSequence(seqName, preset);
        if (!seq) alert("Could not create sequence from preset:\n" + preset + "\n\nFalling back to a default 1080x1920 sequence.");
    }
    if (!seq) {
        seq = app.project.createNewSequence(seqName, "");
        if (seq) {
            var s = seq.getSettings();
            s.videoFrameWidth = cfg.frame_width || 1080;
            s.videoFrameHeight = cfg.frame_height || 1920;
            seq.setSettings(s);
        }
    }
    if (!seq) {
        alert("Failed to create a sequence. Is a project open?");
        return;
    }
    app.project.openSequence(seq.sequenceID);

    // 2. Import the composited shorts --------------------------------------
    var paths = [];
    for (var i = 0; i < shorts.length; i++) paths.push(shorts[i].fsName);
    app.project.importFiles(paths, true, app.project.rootItem, false);

    // 3. Place them back-to-back on video track 1 --------------------------
    var seg = Number(cfg.segment_seconds) || 10;
    var placed = 0;
    var t = 0;
    for (var j = 0; j < shorts.length; j++) {
        var item = findProjectItem(app.project.rootItem, shorts[j].name);
        if (!item) {
            alert("Could not find imported item: " + shorts[j].name);
            continue;
        }
        try {
            var ok = seq.overwriteClip(item, t, 0, -1);
            if (ok !== false) placed++;
            else alert("overwriteClip returned false for " + shorts[j].name);
        } catch (e) {
            alert("Failed to place " + shorts[j].name + ": " + e);
        }
        t += seg;
    }

    if (placed === 0) {
        alert("No clips were placed on the timeline. Check the messages above.");
        return;
    }

    // 4. Set in/out to the full timeline and optionally export -------------
    seq.setInPoint(0);
    seq.setOutPoint(placed * seg);

    var exported = "";
    var epreset = resolvePath(cfg, "export_preset");
    if (epreset) {
        try {
            var ext = seq.getExportFileExtension(epreset) || ".mp4";
            var outPath = outputDir + "/" + seqName + ext;
            seq.exportAsMediaDirect(outPath, epreset, 1);
            exported = "\n\nExported: " + outPath;
        } catch (e) {
            alert("Export failed: " + e + "\n\nYou can still export manually (File > Export > Media).");
        }
    }

    alert("Done!\n\nSequence: " + seqName +
          "\nClips placed: " + placed +
          "\nTimeline length: " + (placed * seg) + "s" +
          exported +
          "\n\nIf export_preset is empty, export manually with your usual settings.");
}

function pad(n) {
    return n < 10 ? "0" + n : "" + n;
}

main();
