#!/usr/bin/env python3
"""
Generate YouTube Shorts video from news.
Supports resumable runs with manual review checkpoints.
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from generate_dialogue import generate_dialogue, refine_dialogue
from generate_audio import generate_audio, DEFAULT_VOICE_A, DEFAULT_VOICE_B
from generate_images import generate_image_prompts, generate_all_images
from generate_yt_metadata import generate_yt_metadata
from perplexity_search import run_perplexity_enrichment
from upload_youtube import upload_to_youtube

PROJECT_ROOT = Path(__file__).parent.parent
REMOTION_DIR = PROJECT_ROOT / "remotion"
IMAGE_PROMPT_PATH = PROJECT_ROOT / "data" / "image_prompt.md"
SUMMARIZER_PROMPT_PATH = PROJECT_ROOT / "data" / "fetch_sources_summariser_prompt.md"
DIALOGUE_REFINE_PROMPT_PATH = PROJECT_ROOT / "data" / "dialogue-prompt" / "prompt-5-step-2.md"


# =========================
# HELPERS
# =========================

def create_run_dir(base_dir: Path) -> Path:
    run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = base_dir / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def wait_for_user(message: str):
    print("\n" + "=" * 60, file=sys.stderr)
    print(message, file=sys.stderr)
    print("Press ENTER to continue, or Ctrl+C to abort.", file=sys.stderr)
    print("=" * 60 + "\n", file=sys.stderr)
    try:
        input()
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        sys.exit(1)


def assign_segment_indices(prompts_data: dict, timeline_path: Path) -> dict:
    """Distribute images evenly across timeline chunks."""
    with open(timeline_path, "r", encoding="utf-8") as f:
        timeline = json.load(f)

    chunk_indices = [
        i for i, s in enumerate(timeline["segments"])
        if s.get("chunk")
    ]
    total_chunks = len(chunk_indices)
    images = prompts_data.get("images", [])
    n_images = len(images)

    if n_images == 0 or total_chunks == 0:
        return prompts_data

    per_image = total_chunks / n_images
    for img_idx, image_info in enumerate(images):
        start = int(img_idx * per_image)
        end = int((img_idx + 1) * per_image)
        image_info["segment_indices"] = chunk_indices[start:end]

    return prompts_data


# =========================
# MAIN
# =========================

def main():
    parser = argparse.ArgumentParser(
        description="Generate YouTube Shorts video from news (resumable)"
    )
    parser.add_argument("news", type=Path, help="Path to news-seed.json file")
    parser.add_argument("prompt", type=Path, help="Path to dialogue prompt.md file")

    parser.add_argument("--resume", type=Path, metavar="RUN_DIR",
                        help="Resume from existing run directory (only runs missing steps)")

    parser.add_argument("-m", "--model", default="gpt-4o")
    parser.add_argument("--summarizer-model", default="gpt-4o-mini")
    parser.add_argument("--voice-a", default=DEFAULT_VOICE_A)
    parser.add_argument("--voice-b", default=DEFAULT_VOICE_B)

    args = parser.parse_args()

    # =========================
    # RESOLVE RUN DIRECTORY
    # =========================

    if args.resume:
        run_dir = args.resume
        if not run_dir.exists():
            print(f"Error: run directory not found: {run_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"Resuming run: {run_dir}", file=sys.stderr)
    else:
        run_dir = create_run_dir(PROJECT_ROOT / "output")
        print(f"New run directory: {run_dir}", file=sys.stderr)
        shutil.copy2(args.news, run_dir / args.news.name)
        shutil.copy2(args.prompt, run_dir / args.prompt.name)

    downloaded_news_path = run_dir / "downloaded_news_data.json"
    dialogue_path = run_dir / "dialogue.json"
    audio_path = run_dir / "audio.mp3"
    timeline_path = run_dir / "timeline.json"
    images_dir = run_dir / "images"
    images_json = images_dir / "images.json"
    video_path = run_dir / "video.mp4"
    yt_metadata_path = run_dir / "yt_metadata.md"

    # =========================
    # STEP 1: GET DATA FROM PERPLEXITY
    # =========================

    run_perplexity_enrichment(input_path=args.news, output_path=downloaded_news_path)

    # =========================
    # STEP 2: DIALOGUE
    # =========================

    if dialogue_path.exists():
        print("Step 2: dialogue.json exists, skipping.", file=sys.stderr)
    else:
        print("Step 2a: Generating dialogue...", file=sys.stderr)
        with open(downloaded_news_path, "r", encoding="utf-8") as f:
            news_data = json.load(f)
        dialogue_data = generate_dialogue(news_data, args.prompt, args.model)

        print("Step 2b: Refining dialogue...", file=sys.stderr)
        dialogue_data = refine_dialogue(
            dialogue_data, news_data, DIALOGUE_REFINE_PROMPT_PATH, args.model
        )

        with open(dialogue_path, "w", encoding="utf-8") as f:
            json.dump(dialogue_data, f, ensure_ascii=False, indent=2)

    wait_for_user(
        f"Review dialogue JSON:\n{dialogue_path}\n\n"
        "Make any edits now before continuing."
    )

    # =========================
    # STEP 3: AUDIO + TIMELINE
    # =========================

    if audio_path.exists() and timeline_path.exists():
        print("Step 3: audio.mp3 and timeline.json exist, skipping.", file=sys.stderr)
    else:
        print("Step 3: Generating audio...", file=sys.stderr)

        generate_audio(
            dialogue_path,
            audio_path,
            timeline_path,
            args.voice_a,
            args.voice_b,
        )

    # =========================
    # STEP 4: IMAGES
    # =========================

    if images_json.exists():
        print("Step 4: images.json exists, skipping.", file=sys.stderr)
    else:
        print("Step 4: Generating images...", file=sys.stderr)
        images_dir.mkdir(parents=True, exist_ok=True)

        prompts_data = generate_image_prompts(
            dialogue_path=dialogue_path,
            prompt_path=IMAGE_PROMPT_PATH,
            model=args.model,
        )

        prompts_data = generate_all_images(prompts_data, images_dir)
        prompts_data = assign_segment_indices(prompts_data, timeline_path)

        with open(images_json, "w", encoding="utf-8") as f:
            json.dump(prompts_data, f, ensure_ascii=False, indent=2)

    wait_for_user(
        f"Review generated images and prompts:\n{images_dir}\n\n"
        "Edit or regenerate images if needed before continuing."
    )

    # =========================
    # STEP 5: VIDEO
    # =========================

    if video_path.exists():
        print("Step 5: video.mp4 exists, skipping.", file=sys.stderr)
    else:
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

    # =========================
    # STEP 6: YT METADATA
    # =========================

    if yt_metadata_path.exists():
        print("Step 6: yt_metadata.md exists, skipping.", file=sys.stderr)
    else:
        print("Step 6: Generating YouTube metadata...", file=sys.stderr)
        metadata = generate_yt_metadata(downloaded_news_path, args.model)
        with open(yt_metadata_path, "w", encoding="utf-8") as f:
            f.write(metadata)

    # =========================
    # STEP 7: UPLOAD TO YOUTUBE
    # =========================

    wait_for_user("Review video and metadata before uploading to YouTube.")

    upload_to_youtube(video_path, yt_metadata_path)

    print("\nDone.", file=sys.stderr)


if __name__ == "__main__":
    main()
