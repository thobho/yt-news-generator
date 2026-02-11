#!/usr/bin/env python3
"""
Generate video with subtitles and background images using Remotion.
Uses per-run public directories (no global asset leakage).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Union

from logging_config import get_logger
from storage import StorageBackend
from storage_config import get_data_storage, get_project_root, is_s3_enabled

logger = get_logger(__name__)

PROJECT_ROOT = get_project_root()
REMOTION_DIR = PROJECT_ROOT / "remotion"
CHANNEL_LOGO_KEY = "media/balanced_news_logo.png"

DEFAULT_EPISODE_NUMBER = 6  # Starting episode number for DYSKUSJA counter

# Node.js heap size in MB - needed for Remotion on low-memory instances
NODE_HEAP_SIZE_MB = 2048

# Parallelization settings
IMAGE_DOWNLOAD_WORKERS = 5  # Max parallel image downloads from S3


def _get_node_env() -> dict:
    """Get environment variables with increased Node.js heap size."""
    env = os.environ.copy()
    env["NODE_OPTIONS"] = f"--max-old-space-size={NODE_HEAP_SIZE_MB}"
    return env


def prepare_public_dir(
    audio_path: Union[Path, str],
    timeline_path: Union[Path, str],
    images_dir: Union[Path, str, None],
    public_dir: Path,
    episode_number: int,
    storage: StorageBackend = None,
) -> dict:
    """
    Prepare a run-scoped Remotion public directory.
    Downloads files from storage (local or S3) to local public_dir for Remotion.
    Returns props to pass to Remotion.

    Args:
        audio_path: Path/key to audio file
        timeline_path: Path/key to timeline JSON
        images_dir: Path/key to images directory (or None)
        public_dir: Local directory for Remotion assets
        episode_number: Episode number for DYSKUSJA counter
        storage: Optional storage backend. If None, uses local filesystem.
    """
    if public_dir.exists():
        shutil.rmtree(public_dir)
    public_dir.mkdir(parents=True, exist_ok=True)

    audio_name = Path(audio_path).name

    # --- Audio ---
    if storage is not None:
        with storage.get_local_path(str(audio_path)) as local_audio:
            shutil.copy(local_audio, public_dir / audio_name)
    else:
        shutil.copy(audio_path, public_dir / audio_name)

    # --- Channel logo ---
    data_storage = get_data_storage()
    if data_storage.exists(CHANNEL_LOGO_KEY):
        with data_storage.get_local_path(CHANNEL_LOGO_KEY) as local_logo:
            shutil.copy(local_logo, public_dir / "channel-logo.png")

    # --- Timeline ---
    if storage is not None:
        timeline_content = storage.read_text(str(timeline_path))
        timeline_data = json.loads(timeline_content)
    else:
        with open(timeline_path, "r", encoding="utf-8") as f:
            timeline_data = json.load(f)

    # IMPORTANT: audio_file must be just the filename
    timeline_data["audio_file"] = audio_name

    # --- Images ---
    images = []
    if images_dir:
        images_public = public_dir / "images"
        images_public.mkdir(parents=True, exist_ok=True)

        if storage is not None:
            # List and download images from storage in parallel
            images_prefix = str(images_dir)
            image_keys = [k for k in storage.list_keys(images_prefix) if k.endswith(".png")]

            def download_image(key: str) -> None:
                """Download a single image from storage."""
                img_name = Path(key).name
                with storage.get_local_path(key) as local_img:
                    shutil.copy(local_img, images_public / img_name)

            if image_keys:
                logger.debug("Downloading %d images in parallel", len(image_keys))
                with ThreadPoolExecutor(max_workers=IMAGE_DOWNLOAD_WORKERS) as executor:
                    futures = [executor.submit(download_image, key) for key in image_keys]
                    for future in as_completed(futures):
                        future.result()  # Raise any exceptions

            # Load images.json
            images_json_key = f"{images_prefix}/images.json"
            if storage.exists(images_json_key):
                content = storage.read_text(images_json_key)
                images = json.loads(content).get("images", [])
        else:
            images_dir = Path(images_dir)
            if images_dir.exists():
                for img in images_dir.glob("*.png"):
                    shutil.copy(img, images_public / img.name)

                images_json = images_dir / "images.json"
                if images_json.exists():
                    with open(images_json, "r", encoding="utf-8") as f:
                        images = json.load(f).get("images", [])

    return {
        "timeline": timeline_data,
        "images": images,
        "episodeNumber": episode_number,
    }


def install_dependencies() -> None:
    node_modules = REMOTION_DIR / "node_modules"
    if not node_modules.exists():
        logger.info("Installing Remotion dependencies...")
        subprocess.run(["npm", "install"], cwd=REMOTION_DIR, check=True, env=_get_node_env())


def render_video(
    output_path: Union[Path, str],
    public_dir: Path,
    props: dict,
    storage: StorageBackend = None,
) -> None:
    """Render video using Remotion.

    Args:
        output_path: Path/key for output video
        public_dir: Local public directory with assets
        props: Props to pass to Remotion
        storage: Optional storage backend. If provided, uploads result to storage.
    """
    # Always render to a local temp file first
    if storage is not None:
        # Use temp directory for Remotion output
        temp_output = public_dir / "output_video.mp4"
    else:
        temp_output = Path(output_path)
        temp_output.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Rendering video with Remotion...")
    logger.debug("Output: %s, public_dir: %s", temp_output, public_dir)

    subprocess.run(
        [
            "npx",
            "remotion",
            "render",
            "SubtitleVideo",
            str(temp_output.absolute()),
            "--public-dir",
            str(public_dir.absolute()),
            "--props",
            json.dumps(props),
        ],
        cwd=REMOTION_DIR,
        check=True,
        env=_get_node_env(),
    )

    # Upload to storage if needed
    if storage is not None:
        storage.copy_from_local(temp_output, str(output_path))
        logger.info("Video uploaded to storage: %s", output_path)
    else:
        logger.info("Video rendered successfully: %s", output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Generate video with subtitles and background images using Remotion"
    )
    parser.add_argument("-o", "--output", type=str, required=True)
    parser.add_argument("--timeline", type=str, required=True)
    parser.add_argument("--audio", type=str, required=True)
    parser.add_argument("--images", type=str)
    parser.add_argument(
        "--episode", type=int, default=DEFAULT_EPISODE_NUMBER,
        help=f"Episode number for DYSKUSJA counter (default: {DEFAULT_EPISODE_NUMBER})"
    )
    parser.add_argument(
        "--run-id", type=str,
        help="Run ID for storage operations (required for S3 backend)"
    )

    args = parser.parse_args()

    # Determine storage backend
    storage = None
    if is_s3_enabled() and args.run_id:
        from storage_config import get_run_storage
        storage = get_run_storage(args.run_id)

    # Validate inputs
    if storage is not None:
        if not storage.exists(args.timeline):
            logger.error("Timeline not found: %s", args.timeline)
            sys.exit(1)
        if not storage.exists(args.audio):
            logger.error("Audio not found: %s", args.audio)
            sys.exit(1)
    else:
        timeline_path = Path(args.timeline)
        audio_path = Path(args.audio)
        if not timeline_path.exists():
            logger.error("Timeline not found: %s", timeline_path)
            sys.exit(1)
        if not audio_path.exists():
            logger.error("Audio not found: %s", audio_path)
            sys.exit(1)

    # Per-run public directory (always local for Remotion)
    if storage is not None:
        # Use temp directory for S3 mode
        public_dir = Path(tempfile.mkdtemp(prefix="remotion_"))
    else:
        public_dir = Path(args.output).parent / "_remotion_public"

    try:
        install_dependencies()

        props = prepare_public_dir(
            audio_path=args.audio,
            timeline_path=args.timeline,
            images_dir=args.images,
            public_dir=public_dir,
            episode_number=args.episode,
            storage=storage,
        )

        render_video(
            output_path=args.output,
            public_dir=public_dir,
            props=props,
            storage=storage,
        )

    except subprocess.CalledProcessError as e:
        logger.error("Remotion failed with exit code %d", e.returncode)
        sys.exit(1)
    except Exception as e:
        logger.error("Video generation failed: %s", e, exc_info=True)
        sys.exit(1)
    finally:
        # Clean up temp public dir for S3 mode
        if storage is not None and public_dir.exists():
            shutil.rmtree(public_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
