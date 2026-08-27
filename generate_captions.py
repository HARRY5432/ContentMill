#!/usr/bin/env python3
import json
import random
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


SYSTEM_PROMPT = """You are a world-class YouTube Shorts metadata and virality writer for premium ASMR / oddly satisfying / funny-cat-style short-form content.

Your job:
- Create a viral YouTube Shorts title, on-screen caption text, and description box copy.
- Optimize for YouTube Shorts search, suggested traffic, and audience retention.
- Keep it natural, premium, and high-performing â€” never spammy.
- Use strong emotional hooks, curiosity, and clear keyword relevance.
- Make the first sentence of the description include the main keyword naturally.
- Include 2-4 highly relevant hashtags only.
- Use concise, punchy language that fits Shorts.
- Write in a way that feels premium, modern, clean, and highly clickable.
- Do not overstuff keywords.
- Avoid generic filler like watch till end unless it feels natural.
- Optimize for high retention, replay value, and shares.

Output EXACTLY this JSON format and nothing else:
{"title": "...", "caption": "...", "description": "...", "hashtags": "#tag1 #tag2 #tag3"}"""


def generate_with_llm(topic, style, api_key, model):
    user_msg = f"Main topic: {topic}\nStyle: {style}\nAudience: US-first, global second\nGoal: maximize clicks, retention, rewatches, and shares"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.9,
        "max_tokens": 512,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://contentfarming.local",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(content)
    except Exception as e:
        print(f"LLM failed ({e}), falling back to templates")
        return None


TEMPLATES = {
    "asmr": {
        "title_hooks": [
            "{keyword} That Will Melt Your Brain",
            "This {keyword} Sound Is Illegal",
            "POV: You Found The Perfect {keyword}",
            "{keyword} So Good It Should Be Banned",
            "Your Brain Will Thank You For This {keyword}",
            "The Most Satisfying {keyword} Ever Caught",
            "{keyword} ASMR That Hits Different",
            "Wait For The {keyword} Drop...",
        ],
        "captions": [
            "pure brain massage", "wait for it...", "your ears will thank you",
            "oddly perfect", "satisfying level: max", "don't blink",
            "feel that?", "instant calm",
        ],
        "desc_templates": [
            "{keyword} content designed to instantly relax your mind and body. This clip delivers deep sensory satisfaction with every frame and sound.\n\nPerfect for unwinding after a long day or falling asleep fast.",
            "Experience {keyword} at its most satisfying. Every detail is crafted to trigger calm and keep you watching on repeat.\n\nSubscribe for daily premium satisfying content.",
            "{keyword} that actually lives up to the hype. Clean visuals, crisp audio, zero filler just pure satisfaction from start to finish.\n\nNew clips drop every single day.",
        ],
        "hashtag_pools": [
            ["#Shorts", "#ASMR", "#Satisfying"],
            ["#Shorts", "#OddlySatisfying", "#Relaxing"],
            ["#Shorts", "#ASMRSounds", "#BrainMassage"],
            ["#Shorts", "#SatisfyingVideo", "#Calm"],
        ],
    },
    "funny_cat": {
        "title_hooks": [
            "This Cat Broke Physics {keyword}",
            "{keyword} Cat Moment Caught On Camera",
            "Cat Does The Impossible ({keyword})",
            "You Wont Believe What This Cat Did | {keyword}",
            "{keyword}: Cat Edition Goes Viral",
            "The Funniest {keyword} Cat Clip Today",
            "Cat vs {keyword} Cat Wins Every Time",
            "POV: Your Cat Discovers {keyword}",
        ],
        "captions": [
            "cats are liquid confirmed", "how is this real??", "send help",
            "cat.exe has stopped working", "absolute chaos",
            "he knew exactly what he was doing", "zero regrets", "legendary moment",
        ],
        "desc_templates": [
            "{keyword} cat moment that proves cats run the internet. This hilarious clip captures pure feline chaos at its absolute best.\n\nShare with someone who needs a laugh today.",
            "Watch this cat handle {keyword} like an absolute pro. Funny, unexpected, and 100% rewatchable.\n\nSubscribe for daily funny cat content.",
            "The ultimate {keyword} cat fail (or win?). Either way, its the funniest thing youll see today.\n\nNew cat clips uploaded every day.",
        ],
        "hashtag_pools": [
            ["#Shorts", "#FunnyCats", "#CatVideos"],
            ["#Shorts", "#Cats", "#Funny"],
            ["#Shorts", "#CatMemes", "#Pets"],
            ["#Shorts", "#FunnyAnimals", "#Cute"],
        ],
    },
    "satisfying": {
        "title_hooks": [
            "{keyword} So Clean It Hurts",
            "Most Satisfying {keyword} Compilation",
            "This {keyword} Will Fix Your Day",
            "{keyword} Perfection Caught On Tape",
            "Oddly Satisfying {keyword} You Cant Stop Watching",
            "The {keyword} Video Everyone Is Sharing",
            "{keyword} Loop That Never Gets Old",
            "Premium {keyword} Satisfaction",
        ],
        "captions": [
            "perfection achieved", "so clean it hurts", "watch it twice",
            "oddly healing", "pure satisfaction", "cant stop watching",
            "visual therapy", "mesmerizing",
        ],
        "desc_templates": [
            "{keyword} content so satisfying youll watch it on loop. Every second delivers visual perfection designed for maximum retention.\n\nHit subscribe for your daily dose of satisfaction.",
            "Premium {keyword} visuals that scratch an itch in your brain. Clean, smooth, and endlessly rewatchable.\n\nNew satisfying content drops daily.",
            "The most satisfying {keyword} clip on YouTube right now. No filler, no fluff just pure visual pleasure from start to finish.\n\nShare if this hit different.",
        ],
        "hashtag_pools": [
            ["#Shorts", "#Satisfying", "#OddlySatisfying"],
            ["#Shorts", "#SatisfyingVideo", "#VisualASMR"],
            ["#Shorts", "#Relaxing", "#Loop"],
            ["#Shorts", "#SatisfyingContent", "#Clean"],
        ],
    },
}


def generate_from_templates(topic, style):
    style_key = style.lower().replace(" ", "_")
    if style_key not in TEMPLATES:
        style_key = "satisfying"
    t = TEMPLATES[style_key]
    title = random.choice(t["title_hooks"]).format(keyword=topic)
    if len(title) > 60:
        title = title[:57] + "..."
    caption = random.choice(t["captions"])
    desc = random.choice(t["desc_templates"]).format(keyword=topic)
    hashtags = " ".join(random.choice(t["hashtag_pools"]))
    return {"title": title, "caption": caption, "description": desc, "hashtags": hashtags}


def generate_package(topic, style):
    cfg = load_config()
    api_key = cfg.get("openrouter_api_key", "")
    model = cfg.get("openrouter_model", "google/gemini-pro-1.5")
    if api_key and api_key != "YOUR_NEW_KEY_HERE":
        result = generate_with_llm(topic, style, api_key, model)
        if result:
            return result
    return generate_from_templates(topic, style)


def write_meta_file(package, output_path):
    tags = package["hashtags"].replace("#", "").split()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"TITLE:\n{package['title']}\n\n")
        f.write(f"DESCRIPTION:\n{package['description']}\n\n{package['hashtags']}\n\n")
        f.write(f"TAGS:\n{','.join(tags)}\n")


def main():
    args = sys.argv[1:]
    if "--generate-all" in args:
        batch_dir = None
        for i, a in enumerate(args):
            if a == "--batch-dir" and i + 1 < len(args):
                batch_dir = Path(args[i + 1])
        if not batch_dir or not batch_dir.exists():
            print("Usage: python generate_captions.py --generate-all --batch-dir <path>")
            sys.exit(1)
        topics = ["ASMR triggers", "satisfying slime", "funny cat fails",
                  "kinetic sand cutting", "soap carving", "hydraulic press",
                  "cat vs cucumber", "paint mixing", "power washing",
                  "cat jumping fails"]
        styles = ["asmr", "satisfying", "funny_cat"]
        videos = sorted(batch_dir.glob("*.mp4"))
        for idx, vid in enumerate(videos):
            topic = topics[idx % len(topics)]
            style = styles[idx % len(styles)]
            pkg = generate_package(topic, style)
            txt_path = batch_dir / f"{vid.stem}.txt"
            write_meta_file(pkg, txt_path)
            print(f"  [{idx+1}/{len(videos)}] {vid.name} -> {txt_path.name}")
        print(f"\nGenerated captions for {len(videos)} videos.")
        return
    if len(args) >= 2:
        topic = args[0]
        style = args[1]
        pkg = generate_package(topic, style)
        print(f"Title: {pkg['title']}")
        print(f"Caption: {pkg['caption']}")
        print(f"Description: {pkg['description']}")
        print(f"Hashtags: {pkg['hashtags']}")
        if "--save" in args and len(args) >= 4:
            out = Path(args[3])
            write_meta_file(pkg, out)
            print(f"\nSaved to {out}")
        return
    print("Usage:")
    print("  python generate_captions.py <topic> <style> [--save <output.txt>]")
    print("  python generate_captions.py --generate-all --batch-dir <path>")
    print("\nStyles: asmr, satisfying, funny_cat")


if __name__ == "__main__":
    main()

