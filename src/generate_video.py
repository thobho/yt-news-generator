#!/usr/bin/env python3
"""
Generate video with subtitles and background images using Remotion.

Usage:
    python generate_video.py --timeline timeline.json --audio audio.mp3 --images images/ -o video.mp4
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
REMOTION_DIR = PROJECT_ROOT / "remotion"


def copy_assets(
    audio_path: Path,
    timeline_path: Path,
    images_dir: Path | None = None,
) -> None:
    """Copy audio, timeline, and images to Remotion project."""
    public_dir = REMOTION_DIR / "public"
    public_dir.mkdir(exist_ok=True)

    # Copy audio to public folder
    print(f"  Copying audio: {audio_path.name}", file=sys.stderr)
    shutil.copy(audio_path, public_dir / audio_path.name)

    # Copy timeline to project root (for Remotion import)
    print(f"  Copying timeline: {timeline_path.name}", file=sys.stderr)
    target_timeline = PROJECT_ROOT / "timeline.json"
    if timeline_path.resolve() != target_timeline.resolve():
        shutil.copy(timeline_path, target_timeline)

    # Update audio_file reference in timeline
    with open(target_timeline, "r", encoding="utf-8") as f:
        timeline_data = json.load(f)
    timeline_data["audio_file"] = audio_path.name
    with open(target_timeline, "w", encoding="utf-8") as f:
        json.dump(timeline_data, f, ensure_ascii=False, indent=2)

    # Copy images if provided
    if images_dir and images_dir.exists():
        images_public_dir = public_dir / "images"
        images_public_dir.mkdir(exist_ok=True)

        # Copy all image files
        image_files = list(images_dir.glob("*.png")) + list(images_dir.glob("*.jpg"))
        for img_file in image_files:
            print(f"  Copying image: {img_file.name}", file=sys.stderr)
            shutil.copy(img_file, images_public_dir / img_file.name)

        # Copy images.json to output folder for Remotion import
        images_json = images_dir / "images.json"
        if images_json.exists():
            # Copy to output/images/ location that Root.tsx expects
            target_images_dir = PROJECT_ROOT / "output" / "images"
            target_images_dir.mkdir(parents=True, exist_ok=True)
            target_json = target_images_dir / "images.json"
            if images_json.resolve() != target_json.resolve():
                shutil.copy(images_json, target_json)
            print(f"  Images metadata: {target_json}", file=sys.stderr)


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


def get_video_info(video_path: Path) -> dict:
    """Get video file information using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration,size",
            "-show_entries", "stream=width,height",
            "-of", "json",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        import json
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [{}])
        video_stream = next((s for s in streams if s.get("width")), {})
        return {
            "duration": float(fmt.get("duration", 0)),
            "size_mb": int(fmt.get("size", 0)) / (1024 * 1024),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
        }
    return {}


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

    # Show video info
    info = get_video_info(output_path)
    if info:
        print(f"\nVideo rendered: {output_path}", file=sys.stderr)
        print(f"  Resolution: {info.get('width')}x{info.get('height')}", file=sys.stderr)
        print(f"  Duration: {info.get('duration', 0):.1f} seconds", file=sys.stderr)
        print(f"  Size: {info.get('size_mb', 0):.1f} MB", file=sys.stderr)
    else:
        print(f"Video rendered: {output_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Generate video with subtitles and background images using Remotion"
    )
    parser.add_argument(
        "-o", "--output", type=Path, required=True,
        help="Output video file path"
    )
    parser.add_argument(
        "--timeline", type=Path, default=Path("output/timeline.json"),
        help="Path to timeline JSON file"
    )
    parser.add_argument(
        "--audio", type=Path, default=Path("output/final_audio.mp3"),
        help="Path to audio file"
    )
    parser.add_argument(
        "--images", type=Path, default=Path("output/images"),
        help="Path to images directory (containing images.json and .png files)"
    )

    args = parser.parse_args()

    # Validate input files
    if not args.timeline.exists():
        print(f"Error: Timeline file not found: {args.timeline}", file=sys.stderr)
        sys.exit(1)

    if not args.audio.exists():
        print(f"Error: Audio file not found: {args.audio}", file=sys.stderr)
        sys.exit(1)

    # Images are optional
    if args.images and not args.images.exists():
        print(f"Warning: Images directory not found: {args.images}", file=sys.stderr)
        args.images = None

    try:
        # Copy assets
        print("Copying assets to Remotion...", file=sys.stderr)
        copy_assets(args.audio, args.timeline, args.images)

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
