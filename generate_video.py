#!/usr/bin/env python3
"""
Generate video with subtitles using Remotion.

Usage:
    python generate_video.py -o output_video.mp4
    python generate_video.py --timeline timeline.json --audio final_audio.mp3 -o output_video.mp4
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


REMOTION_DIR = Path(__file__).parent / "remotion"


def copy_assets(audio_path: Path, timeline_path: Path) -> None:
    """Copy audio and timeline files to Remotion project."""
    # Copy audio to public folder
    public_dir = REMOTION_DIR / "public"
    public_dir.mkdir(exist_ok=True)
    shutil.copy(audio_path, public_dir / audio_path.name)

    # Copy timeline to root (for import)
    shutil.copy(timeline_path, REMOTION_DIR.parent / "timeline.json")


def install_dependencies() -> None:
    """Install npm dependencies if needed."""
    node_modules = REMOTION_DIR / "node_modules"
    if not node_modules.exists():
        print("Installing Remotion dependencies...", file=sys.stderr)
        subprocess.run(
            ["npm", "install"],
            cwd=REMOTION_DIR,
            check=True,
        )


def render_video(output_path: Path) -> None:
    """Render video using Remotion."""
    print("Rendering video...", file=sys.stderr)
    subprocess.run(
        [
            "npx", "remotion", "render",
            "SubtitleVideo",
            str(output_path.absolute()),
        ],
        cwd=REMOTION_DIR,
        check=True,
    )
    print(f"Video rendered: {output_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Generate video with subtitles using Remotion"
    )
    parser.add_argument(
        "-o", "--output", type=Path, required=True, help="Output video file path"
    )
    parser.add_argument(
        "--timeline", type=Path, default=Path("timeline.json"),
        help="Path to timeline JSON file (default: timeline.json)"
    )
    parser.add_argument(
        "--audio", type=Path, default=Path("final_audio.mp3"),
        help="Path to audio file (default: final_audio.mp3)"
    )

    args = parser.parse_args()

    # Validate input files
    if not args.timeline.exists():
        print(f"Error: Timeline file not found: {args.timeline}", file=sys.stderr)
        sys.exit(1)

    if not args.audio.exists():
        print(f"Error: Audio file not found: {args.audio}", file=sys.stderr)
        sys.exit(1)

    try:
        # Copy assets
        copy_assets(args.audio, args.timeline)

        # Install dependencies
        install_dependencies()

        # Render video
        render_video(args.output)

    except subprocess.CalledProcessError as e:
        print(f"Error: Command failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
