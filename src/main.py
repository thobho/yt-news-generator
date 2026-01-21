#!/usr/bin/env python3
"""
Generate YouTube Shorts video from news.

This script combines three steps:
1. Generate dialogue from news using ChatGPT
2. Generate audio from dialogue using ElevenLabs
3. Generate video with subtitles using Remotion

Usage (from project root):
    python src/main.py data/news.json data/prompt.md -o output/audio.mp3
    python src/main.py data/news.json data/prompt.md -o output/audio.mp3 -v output/video.mp4
    python src/main.py data/news.json data/prompt.md -o output/audio.mp3 --voice-a "Adam" --voice-b "Domi"
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from generate_dialogue import generate_dialogue
from generate_audio import generate_audio, DEFAULT_VOICE_A, DEFAULT_VOICE_B


PROJECT_ROOT = Path(__file__).parent.parent
REMOTION_DIR = PROJECT_ROOT / "remotion"


def main():
    parser = argparse.ArgumentParser(
        description="Generate YouTube dialogue audio from news"
    )
    parser.add_argument("news", type=Path, help="Path to news.json file")
    parser.add_argument("prompt", type=Path, help="Path to prompt.md file")
    parser.add_argument(
        "-o", "--output", type=Path, required=True, help="Output MP3 file path"
    )
    parser.add_argument(
        "-m", "--model", default="gpt-4o", help="OpenAI model to use (default: gpt-4o)"
    )
    parser.add_argument(
        "--voice-a",
        default=DEFAULT_VOICE_A,
        help=f"Voice name for Speaker A (default: {DEFAULT_VOICE_A})",
    )
    parser.add_argument(
        "--voice-b",
        default=DEFAULT_VOICE_B,
        help=f"Voice name for Speaker B (default: {DEFAULT_VOICE_B})",
    )
    parser.add_argument(
        "--keep-dialogue",
        type=Path,
        help="Save intermediate dialogue JSON to this path",
    )
    parser.add_argument(
        "-t", "--timeline",
        type=Path,
        help="Output timeline JSON file path (for subtitles)",
    )
    parser.add_argument(
        "-v", "--video",
        type=Path,
        help="Output video file path (requires Remotion)",
    )

    args = parser.parse_args()

    # Validate input files
    if not args.news.exists():
        print(f"Error: News file not found: {args.news}", file=sys.stderr)
        sys.exit(1)

    if not args.prompt.exists():
        print(f"Error: Prompt file not found: {args.prompt}", file=sys.stderr)
        sys.exit(1)

    try:
        # Step 1: Generate dialogue
        print("Step 1: Generating dialogue from news...", file=sys.stderr)
        dialogue_data = generate_dialogue(args.news, args.prompt, args.model)
        print("Dialogue generated successfully.", file=sys.stderr)

        # Save dialogue to temp file or specified path
        if args.keep_dialogue:
            dialogue_path = args.keep_dialogue
            with open(dialogue_path, "w", encoding="utf-8") as f:
                json.dump(dialogue_data, f, ensure_ascii=False, indent=2)
            print(f"Dialogue saved to: {dialogue_path}", file=sys.stderr)
        else:
            # Use temp file
            temp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            )
            json.dump(dialogue_data, temp_file, ensure_ascii=False, indent=2)
            temp_file.close()
            dialogue_path = Path(temp_file.name)

        # Step 2: Generate audio
        print("\nStep 2: Generating audio from dialogue...", file=sys.stderr)

        # If video is requested, we need a timeline (use temp file if not specified)
        timeline_path = args.timeline
        temp_timeline = False
        if args.video and not timeline_path:
            fd, tmp = tempfile.mkstemp(suffix=".json")
            os.close(fd)
            timeline_path = Path(tmp)
            temp_timeline = True

        generate_audio(
            dialogue_path, args.output, timeline_path, args.voice_a, args.voice_b
        )

        # Clean up temp file if not keeping dialogue
        if not args.keep_dialogue:
            dialogue_path.unlink()

        print(f"Audio saved to: {args.output}", file=sys.stderr)

        # Step 3: Generate video (if requested)
        if args.video:
            print("\nStep 3: Generating video with subtitles...", file=sys.stderr)

            # Copy audio to Remotion public folder
            public_dir = REMOTION_DIR / "public"
            public_dir.mkdir(exist_ok=True)
            shutil.copy(args.output, public_dir / args.output.name)

            # Copy timeline to project root for Remotion import (if not already there)
            target_timeline = PROJECT_ROOT / "timeline.json"
            if timeline_path.resolve() != target_timeline.resolve():
                shutil.copy(timeline_path, target_timeline)

            # Update timeline audio_file reference
            with open(target_timeline, "r", encoding="utf-8") as f:
                timeline_data = json.load(f)
            timeline_data["audio_file"] = args.output.name
            with open(target_timeline, "w", encoding="utf-8") as f:
                json.dump(timeline_data, f, ensure_ascii=False, indent=2)

            # Render video
            subprocess.run(
                ["npx", "remotion", "render", "SubtitleVideo", str(args.video.absolute())],
                cwd=REMOTION_DIR,
                check=True,
            )
            print(f"Video saved to: {args.video}", file=sys.stderr)

            # Clean up temp timeline
            if temp_timeline:
                timeline_path.unlink()

        print("\nDone!", file=sys.stderr)

    except subprocess.CalledProcessError as e:
        print(f"Error: Video rendering failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
