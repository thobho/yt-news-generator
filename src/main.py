#!/usr/bin/env python3
"""
Generate YouTube Shorts video from news.
Supports resumable runs.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from generate_dialogue import generate_dialogue
from generate_audio import generate_audio, DEFAULT_VOICE_A, DEFAULT_VOICE_B
from generate_images import generate_image_prompts, generate_all_images
from fetch_sources import (
    load_prompt as load_summarizer_prompt,
    process_sources,
    build_enriched_news,
)


PROJECT_ROOT = Path(__file__).parent.parent
REMOTION_DIR = PROJECT_ROOT / "remotion"
IMAGE_PROMPT_PATH = PROJECT_ROOT / "data" / "image_prompt.md"
SUMMARIZER_PROMPT_PATH = PROJECT_ROOT / "data" / "fetch_sources_summariser_prompt.md"


# =========================
# RUN DIRECTORY MANAGEMENT
# =========================

def create_run_dir(base_dir: Path) -> Path:
    run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = base_dir / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def main():
    parser = argparse.ArgumentParser(
        description="Generate YouTube Shorts video from news (resumable)"
    )
    parser.add_argument("news", type=Path, help="Path to news.json file")
    parser.add_argument("prompt", type=Path, help="Path to dialogue prompt.md file")

    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("-v", "--video", type=Path)
    parser.add_argument("-t", "--timeline", type=Path)
    parser.add_argument("--keep-dialogue", type=Path)

    parser.add_argument("--resume-run", type=Path)
    parser.add_argument("--reuse-images", action="store_true")

    parser.add_argument("-m", "--model", default="gpt-4o")
    parser.add_argument("--summarizer-model", default="gpt-4o-mini")
    parser.add_argument("--voice-a", default=DEFAULT_VOICE_A)
    parser.add_argument("--voice-b", default=DEFAULT_VOICE_B)
    parser.add_argument("--skip-enrichment", action="store_true",
                        help="Skip source fetching/summarization")

    args = parser.parse_args()

    # =========================
    # RESOLVE RUN DIRECTORY
    # =========================

    if args.resume_run:
        run_dir = args.resume_run
        if not run_dir.exists():
            print(f"Error: run directory not found: {run_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"Resuming run: {run_dir}", file=sys.stderr)
    else:
        run_dir = create_run_dir(PROJECT_ROOT / "output")
        print(f"New run directory: {run_dir}", file=sys.stderr)

    audio_path = run_dir / args.output
    video_path = run_dir / args.video if args.video else None
    timeline_path = run_dir / args.timeline if args.timeline else None
    dialogue_path = run_dir / (args.keep_dialogue or "dialogue.json")
    enriched_path = run_dir / "enriched_news.json"

    images_dir = run_dir / "images"
    images_json = images_dir / "images.json"
    images_data = []

    # =========================
    # STEP 1: ENRICH SOURCES
    # =========================

    if args.resume_run:
        if enriched_path.exists():
            print("Using existing enriched_news.json", file=sys.stderr)
        else:
            print("No enriched_news.json found, will use original news file", file=sys.stderr)
    elif args.skip_enrichment:
        print("Skipping source enrichment (--skip-enrichment)", file=sys.stderr)
        # Copy original news to enriched path for consistency
        with open(args.news, "r", encoding="utf-8") as f:
            news_data = json.load(f)
        with open(enriched_path, "w", encoding="utf-8") as f:
            json.dump(news_data, f, ensure_ascii=False, indent=2)
    else:
        print("Step 1: Enriching sources (fetching & summarizing)...", file=sys.stderr)

        with open(args.news, "r", encoding="utf-8") as f:
            news_data = json.load(f)

        summarizer_prompt = load_summarizer_prompt(SUMMARIZER_PROMPT_PATH)
        results = process_sources(news_data, summarizer_prompt, args.summarizer_model)
        enriched_data = build_enriched_news(news_data, results)

        with open(enriched_path, "w", encoding="utf-8") as f:
            json.dump(enriched_data, f, ensure_ascii=False, indent=2)

        stats = enriched_data["fetch_stats"]
        print(f"         {stats['successful']}/{stats['total']} sources enriched", file=sys.stderr)

    # =========================
    # STEP 2: DIALOGUE
    # =========================

    if args.resume_run:
        if not dialogue_path.exists():
            print("Error: dialogue.json missing in resumed run", file=sys.stderr)
            sys.exit(1)
        print("Skipping dialogue generation.", file=sys.stderr)
    else:
        print("Step 2: Generating dialogue...", file=sys.stderr)
        # Use enriched news if available
        news_input = enriched_path if enriched_path.exists() else args.news
        dialogue_data = generate_dialogue(news_input, args.prompt, args.model)
        with open(dialogue_path, "w", encoding="utf-8") as f:
            json.dump(dialogue_data, f, ensure_ascii=False, indent=2)

    # =========================
    # STEP 3: AUDIO
    # =========================

    if args.resume_run:
        if not audio_path.exists():
            print("Error: audio.mp3 missing in resumed run", file=sys.stderr)
            sys.exit(1)
        # Set timeline_path from existing file when resuming
        if not timeline_path:
            timeline_path = run_dir / "timeline.json"
        print("Skipping audio generation.", file=sys.stderr)
    else:
        print("Step 3: Generating audio...", file=sys.stderr)

        temp_timeline = False
        if args.video and not timeline_path:
            fd, tmp = tempfile.mkstemp(suffix=".json")
            os.close(fd)
            timeline_path = Path(tmp)
            temp_timeline = True

        generate_audio(
            dialogue_path,
            audio_path,
            timeline_path,
            args.voice_a,
            args.voice_b,
        )

        if temp_timeline:
            shutil.move(timeline_path, run_dir / "timeline.json")
            timeline_path = run_dir / "timeline.json"

    # =========================
    # STEP 4: IMAGES
    # =========================

    if args.resume_run and args.reuse_images:
        if not images_json.exists():
            print("Error: images.json missing for reuse", file=sys.stderr)
            sys.exit(1)
        images_data = json.load(open(images_json)).get("images", [])
        print("Reusing existing images.", file=sys.stderr)
    else:
        print("Step 4: Generating images...", file=sys.stderr)
        images_dir.mkdir(parents=True, exist_ok=True)

        prompts_data = generate_image_prompts(
            dialogue_path=dialogue_path,
            prompt_path=IMAGE_PROMPT_PATH,
            model=args.model,
        )

        prompts_data = generate_all_images(prompts_data, images_dir)

        with open(images_json, "w", encoding="utf-8") as f:
            json.dump(prompts_data, f, ensure_ascii=False, indent=2)

    print("\nDone.", file=sys.stderr)

    # =========================
    # STEP 5: VIDEO
    # =========================

    if video_path:
        print("Step 5: Rendering video...", file=sys.stderr)

        subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "src" / "generate_video.py"),
                "--audio", str(audio_path),
                "--timeline", str(timeline_path),
                "--images", str(images_dir),
                "-o", str(video_path),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
