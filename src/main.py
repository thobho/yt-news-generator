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
from storage_config import (
    get_data_storage,
    get_output_storage,
    get_run_storage,
    get_project_root,
    get_storage_dir,
    is_s3_enabled,
    ensure_storage_dirs,
)

PROJECT_ROOT = get_project_root()
REMOTION_DIR = PROJECT_ROOT / "remotion"

# Storage keys for data files
IMAGE_PROMPT_KEY = "image_prompt.md"
SUMMARIZER_PROMPT_KEY = "fetch_sources_summariser_prompt.md"
DIALOGUE_REFINE_PROMPT_KEY = "dialogue-prompt/prompt-5-step-2.md"


# =========================
# HELPERS
# =========================

def create_run_dir(base_dir: Path = None) -> tuple[str, Path]:
    """Create a new run directory.

    Returns:
        Tuple of (run_id, run_dir_path)
    """
    run_id = f"run_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

    if is_s3_enabled():
        # For S3, we don't create a local directory
        # The run_id is used as a key prefix
        return run_id, None
    else:
        if base_dir is None:
            base_dir = get_storage_dir() / "output"
        run_dir = base_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_id, run_dir


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


def assign_segment_indices(prompts_data: dict, timeline_path: str, storage=None) -> dict:
    """Distribute images evenly across timeline chunks."""
    if storage is not None:
        content = storage.read_text(timeline_path)
        timeline = json.loads(content)
    else:
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
    parser.add_argument("news", type=str, help="Path to news-seed.json file")
    parser.add_argument("prompt", type=str, help="Path to dialogue prompt.md file")

    parser.add_argument("--resume", type=str, metavar="RUN_ID",
                        help="Resume from existing run (run ID or directory path)")

    parser.add_argument("-m", "--model", default="gpt-4o")
    parser.add_argument("--summarizer-model", default="gpt-4o-mini")
    parser.add_argument("--voice-a", default=DEFAULT_VOICE_A)
    parser.add_argument("--voice-b", default=DEFAULT_VOICE_B)

    args = parser.parse_args()

    # =========================
    # SETUP STORAGE
    # =========================

    ensure_storage_dirs()
    data_storage = get_data_storage()
    using_s3 = is_s3_enabled()
    storage_dir = get_storage_dir()

    # =========================
    # RESOLVE RUN DIRECTORY
    # =========================

    if args.resume:
        run_id = args.resume
        if run_id.startswith("run_"):
            pass  # Already a run_id
        elif "/" in run_id or "\\" in run_id:
            # It's a path, extract run_id
            run_id = Path(run_id).name

        if using_s3:
            run_storage = get_run_storage(run_id)
            run_dir = None
        else:
            run_dir = storage_dir / "output" / run_id
            if not run_dir.exists():
                print(f"Error: run directory not found: {run_dir}", file=sys.stderr)
                sys.exit(1)
            run_storage = get_run_storage(run_id)

        print(f"Resuming run: {run_id}", file=sys.stderr)
    else:
        run_id, run_dir = create_run_dir()
        run_storage = get_run_storage(run_id)
        print(f"New run: {run_id}", file=sys.stderr)

        # Copy seed files to run storage
        if using_s3:
            # Read local files and upload to S3
            with open(args.news, "r", encoding="utf-8") as f:
                run_storage.write_text("seed.json", f.read())
            with open(args.prompt, "r", encoding="utf-8") as f:
                run_storage.write_text(Path(args.prompt).name, f.read())
        else:
            shutil.copy2(args.news, run_dir / Path(args.news).name)
            shutil.copy2(args.prompt, run_dir / Path(args.prompt).name)

    # Define file keys/paths
    downloaded_news_key = "downloaded_news_data.json"
    dialogue_key = "dialogue.json"
    audio_key = "audio.mp3"
    timeline_key = "timeline.json"
    images_dir_key = "images"
    images_json_key = "images/images.json"
    video_key = "video.mp4"
    yt_metadata_key = "yt_metadata.md"

    # =========================
    # STEP 1: GET DATA FROM PERPLEXITY
    # =========================

    run_perplexity_enrichment(
        input_path="seed.json" if using_s3 else args.news,
        output_path=downloaded_news_key,
        storage=run_storage if using_s3 else None,
    )

    # =========================
    # STEP 2: DIALOGUE
    # =========================

    if run_storage.exists(dialogue_key):
        print("Step 2: dialogue.json exists, skipping.", file=sys.stderr)
    else:
        print("Step 2a: Generating dialogue...", file=sys.stderr)
        news_content = run_storage.read_text(downloaded_news_key)
        news_data = json.loads(news_content)

        # Load prompt - either from storage or local path
        if using_s3:
            prompt_content = run_storage.read_text(Path(args.prompt).name)
        else:
            with open(args.prompt, "r", encoding="utf-8") as f:
                prompt_content = f.read()

        dialogue_data = generate_dialogue(
            news_data,
            args.prompt if not using_s3 else Path(args.prompt).name,
            args.model,
            storage=run_storage if using_s3 else None,
        )

        print("Step 2b: Refining dialogue...", file=sys.stderr)
        dialogue_data = refine_dialogue(
            dialogue_data,
            news_data,
            DIALOGUE_REFINE_PROMPT_KEY,
            args.model,
            storage=data_storage,
        )

        dialogue_json = json.dumps(dialogue_data, ensure_ascii=False, indent=2)
        run_storage.write_text(dialogue_key, dialogue_json)

    if using_s3:
        print(f"Review dialogue JSON in S3: s3://{run_storage.bucket}/{run_storage._full_key(dialogue_key)}", file=sys.stderr)
    else:
        dialogue_path = run_dir / dialogue_key
        wait_for_user(
            f"Review dialogue JSON:\n{dialogue_path}\n\n"
            "Make any edits now before continuing."
        )

    # =========================
    # STEP 3: AUDIO + TIMELINE
    # =========================

    if run_storage.exists(audio_key) and run_storage.exists(timeline_key):
        print("Step 3: audio.mp3 and timeline.json exist, skipping.", file=sys.stderr)
    else:
        print("Step 3: Generating audio...", file=sys.stderr)

        generate_audio(
            dialogue_key,
            audio_key,
            timeline_key,
            args.voice_a,
            args.voice_b,
            storage=run_storage,
        )

    # =========================
    # STEP 4: IMAGES
    # =========================

    if run_storage.exists(images_json_key):
        print("Step 4: images.json exists, skipping.", file=sys.stderr)
    else:
        print("Step 4: Generating images...", file=sys.stderr)
        run_storage.makedirs(images_dir_key)

        prompts_data = generate_image_prompts(
            dialogue_path=dialogue_key,
            prompt_path=IMAGE_PROMPT_KEY,
            model=args.model,
            dialogue_storage=run_storage,
            prompt_storage=data_storage,
        )

        prompts_data = generate_all_images(prompts_data, images_dir_key, storage=run_storage)
        prompts_data = assign_segment_indices(prompts_data, timeline_key, storage=run_storage)

        images_json = json.dumps(prompts_data, ensure_ascii=False, indent=2)
        run_storage.write_text(images_json_key, images_json)

    if using_s3:
        print(f"Review images in S3: s3://{run_storage.bucket}/{run_storage._full_key(images_dir_key)}/", file=sys.stderr)
    else:
        images_dir = run_dir / images_dir_key
        wait_for_user(
            f"Review generated images and prompts:\n{images_dir}\n\n"
            "Edit or regenerate images if needed before continuing."
        )

    # =========================
    # STEP 5: VIDEO
    # =========================

    if run_storage.exists(video_key):
        print("Step 5: video.mp4 exists, skipping.", file=sys.stderr)
    else:
        print("Step 5: Rendering video...", file=sys.stderr)

        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "src" / "generate_video.py"),
            "--audio", audio_key,
            "--timeline", timeline_key,
            "--images", images_dir_key,
            "-o", video_key,
        ]

        if using_s3:
            cmd.extend(["--run-id", run_id])
        else:
            # For local mode, use full paths
            cmd = [
                sys.executable,
                str(PROJECT_ROOT / "src" / "generate_video.py"),
                "--audio", str(run_dir / audio_key),
                "--timeline", str(run_dir / timeline_key),
                "--images", str(run_dir / images_dir_key),
                "-o", str(run_dir / video_key),
            ]

        subprocess.run(cmd, check=True)

    # =========================
    # STEP 6: YT METADATA
    # =========================

    if run_storage.exists(yt_metadata_key):
        print("Step 6: yt_metadata.md exists, skipping.", file=sys.stderr)
    else:
        print("Step 6: Generating YouTube metadata...", file=sys.stderr)
        metadata = generate_yt_metadata(downloaded_news_key, args.model, storage=run_storage)
        run_storage.write_text(yt_metadata_key, metadata)

    # =========================
    # STEP 7: UPLOAD TO YOUTUBE
    # =========================

    if not using_s3:
        wait_for_user("Review video and metadata before uploading to YouTube.")

    upload_to_youtube(video_key, yt_metadata_key, storage=run_storage)

    print("\nDone.", file=sys.stderr)


if __name__ == "__main__":
    main()
