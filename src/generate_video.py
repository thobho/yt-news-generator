#!/usr/bin/env python3
"""
Generate video with subtitles and background images using Remotion.
Uses per-run public directories (no global asset leakage).
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
REMOTION_DIR = PROJECT_ROOT / "remotion"


def prepare_public_dir(
    audio_path: Path,
    timeline_path: Path,
    images_dir: Path | None,
    public_dir: Path,
) -> dict:
    """
    Prepare a run-scoped Remotion public directory.
    Returns props to pass to Remotion.
    """
    if public_dir.exists():
        shutil.rmtree(public_dir)
    public_dir.mkdir(parents=True, exist_ok=True)

    # --- Audio ---
    shutil.copy(audio_path, public_dir / audio_path.name)

    # --- Timeline ---
    with open(timeline_path, "r", encoding="utf-8") as f:
        timeline_data = json.load(f)

    # IMPORTANT: audio_file must be just the filename
    timeline_data["audio_file"] = audio_path.name

    # --- Images ---
    images = []
    if images_dir and images_dir.exists():
        images_public = public_dir / "images"
        images_public.mkdir(parents=True, exist_ok=True)

        for img in images_dir.glob("*.png"):
            shutil.copy(img, images_public / img.name)

        images_json = images_dir / "images.json"
        if images_json.exists():
            with open(images_json, "r", encoding="utf-8") as f:
                images = json.load(f).get("images", [])

    return {
        "timeline": timeline_data,
        "images": images,
    }


def install_dependencies() -> None:
    node_modules = REMOTION_DIR / "node_modules"
    if not node_modules.exists():
        print("Installing Remotion dependencies...", file=sys.stderr)
        subprocess.run(["npm", "install"], cwd=REMOTION_DIR, check=True)


def render_video(
    output_path: Path,
    public_dir: Path,
    props: dict,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Rendering video...", file=sys.stderr)

    subprocess.run(
        [
            "npx",
            "remotion",
            "render",
            "SubtitleVideo",
            str(output_path.absolute()),
            "--public-dir",
            str(public_dir.absolute()),
            "--props",
            json.dumps(props),
        ],
        cwd=REMOTION_DIR,
        check=True,
    )

    print(f"Video rendered: {output_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Generate video with subtitles and background images using Remotion"
    )
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--images", type=Path)

    args = parser.parse_args()

    if not args.timeline.exists():
        print(f"Error: timeline not found: {args.timeline}", file=sys.stderr)
        sys.exit(1)

    if not args.audio.exists():
        print(f"Error: audio not found: {args.audio}", file=sys.stderr)
        sys.exit(1)

    if args.images and not args.images.exists():
        print(f"Warning: images directory not found: {args.images}", file=sys.stderr)
        args.images = None

    # Per-run public directory
    public_dir = args.output.parent / "_remotion_public"

    try:
        install_dependencies()

        props = prepare_public_dir(
            audio_path=args.audio,
            timeline_path=args.timeline,
            images_dir=args.images,
            public_dir=public_dir,
        )

        render_video(
            output_path=args.output,
            public_dir=public_dir,
            props=props,
        )

    except subprocess.CalledProcessError as e:
        print(f"Error: Remotion failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
