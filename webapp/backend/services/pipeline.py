"""
Pipeline service - orchestrates video generation steps.
Each step is isolated and can be called independently.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"

# Storage paths (will be set after storage_config import)
def _get_output_dir() -> Path:
    return get_storage_dir() / "output"

def _get_data_dir() -> Path:
    return get_storage_dir() / "data"

def _get_seeds_dir() -> Path:
    return get_storage_dir() / "data" / "news-seeds"

# Add src to path for imports
sys.path.insert(0, str(SRC_DIR))

from logging_config import get_logger
from storage_config import (
    get_data_storage,
    get_output_storage,
    get_run_storage,
    get_storage_dir,
    is_s3_enabled,
    ensure_storage_dirs,
)

logger = get_logger(__name__)

# Import settings and prompts services
from . import settings as settings_service
from . import prompts as prompts_service


def get_dialogue_prompt_keys() -> tuple[str, str]:
    """Get dialogue prompt keys based on current active prompt."""
    active_id = prompts_service.get_active_prompt_id("dialogue")
    if active_id:
        main_key = f"prompts/dialogue/{active_id}.md"
        refine_key = f"prompts/dialogue/{active_id}-step-2.md"
        return main_key, refine_key

    # Fallback to old path structure for backward compatibility
    current_settings = settings_service.load_settings()
    version = current_settings.prompt_version
    main_key = f"dialogue-prompt/prompt-{version}.md"
    refine_key = f"dialogue-prompt/prompt-{version}-step-2.md"
    return main_key, refine_key


def get_image_prompt_key() -> str:
    """Get image prompt key based on current active prompt."""
    active_id = prompts_service.get_active_prompt_id("image")
    if active_id:
        return f"prompts/image/{active_id}.md"
    # Fallback to old path
    return "image_prompt.md"


def get_research_prompt_key() -> str:
    """Get research/summarizer prompt key based on current active prompt."""
    active_id = prompts_service.get_active_prompt_id("research")
    if active_id:
        return f"prompts/research/{active_id}.md"
    # Fallback to old path
    return "fetch_sources_summariser_prompt.md"


def get_yt_metadata_prompt_key() -> str:
    """Get YouTube metadata prompt key based on current active prompt."""
    active_id = prompts_service.get_active_prompt_id("yt-metadata")
    if active_id:
        return f"prompts/yt-metadata/{active_id}.md"
    # Fallback to old path
    return "yt_metadata_prompt.md"


def create_run_dir() -> tuple[str, Path]:
    """Create a new run directory with timestamp ID.

    Returns:
        Tuple of (run_id, run_dir_path). run_dir is None for S3.
    """
    run_id = f"run_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

    if is_s3_enabled():
        # For S3, just return the run_id - no local directory needed
        logger.info("Created run: %s (S3 mode)", run_id)
        return run_id, None
    else:
        ensure_storage_dirs()
        run_dir = _get_output_dir() / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Created run directory: %s", run_dir)
        return run_id, run_dir


def create_seed(news_text: str) -> tuple[str, str]:
    """
    Create a new seed file and run directory.
    Returns (run_id, seed_key).
    """
    run_id, run_dir = create_run_dir()
    run_storage = get_run_storage(run_id)

    # Create seed data
    seed_data = {"news_seed": news_text}
    seed_json = json.dumps(seed_data, ensure_ascii=False, indent=2)

    # Save seed to run storage
    run_storage.write_text("seed.json", seed_json)

    # Also save to seeds directory (data storage)
    if not is_s3_enabled():
        seeds_dir = _get_seeds_dir()
        seeds_dir.mkdir(parents=True, exist_ok=True)
        seeds_seed_path = seeds_dir / f"{run_id}.json"
        with open(seeds_seed_path, "w", encoding="utf-8") as f:
            f.write(seed_json)
    else:
        data_storage = get_data_storage()
        data_storage.write_text(f"news-seeds/{run_id}.json", seed_json)

    return run_id, "seed.json"


def get_run_keys() -> dict:
    """Get all standard file keys for a run."""
    return {
        "seed": "seed.json",
        "news_data": "downloaded_news_data.json",
        "dialogue": "dialogue.json",
        "audio": "audio.mp3",
        "timeline": "timeline.json",
        "images_dir": "images",
        "images_json": "images/images.json",
        "video": "video.mp4",
        "yt_metadata": "yt_metadata.md",
        "yt_upload": "yt_upload.json",
    }


def get_run_paths(run_dir: Path) -> dict:
    """Get all standard paths for a run (local mode only)."""
    return {
        "seed": run_dir / "seed.json",
        "news_data": run_dir / "downloaded_news_data.json",
        "dialogue": run_dir / "dialogue.json",
        "audio": run_dir / "audio.mp3",
        "timeline": run_dir / "timeline.json",
        "images_dir": run_dir / "images",
        "images_json": run_dir / "images" / "images.json",
        "video": run_dir / "video.mp4",
        "yt_metadata": run_dir / "yt_metadata.md",
        "yt_upload": run_dir / "yt_upload.json",
    }


def generate_dialogue_for_run(run_id: str, model: str = "gpt-4o") -> dict:
    """
    Generate dialogue from seed.
    Steps: perplexity search -> dialogue generation -> refinement
    """
    logger.info("Starting dialogue generation for run: %s", run_id)
    from perplexity_search import run_perplexity_enrichment
    from generate_dialogue import generate_dialogue as gen_dialogue, refine_dialogue

    run_storage = get_run_storage(run_id)
    data_storage = get_data_storage()
    keys = get_run_keys()

    # Find seed file
    if not run_storage.exists(keys["seed"]):
        raise FileNotFoundError(f"No seed file found for run {run_id}")

    # Step 1: Perplexity search
    run_perplexity_enrichment(
        input_path=keys["seed"],
        output_path=keys["news_data"],
        storage=run_storage,
    )

    # Step 2: Generate dialogue
    news_content = run_storage.read_text(keys["news_data"])
    news_data = json.loads(news_content)

    # Get prompt keys from settings
    dialogue_prompt_key, refine_prompt_key = get_dialogue_prompt_keys()

    dialogue_data = gen_dialogue(
        news_data,
        dialogue_prompt_key,
        model,
        storage=data_storage,
    )

    # Step 3: Refine dialogue
    dialogue_data = refine_dialogue(
        dialogue_data,
        news_data,
        refine_prompt_key,
        model,
        storage=data_storage,
    )

    # Save dialogue
    dialogue_json = json.dumps(dialogue_data, ensure_ascii=False, indent=2)
    run_storage.write_text(keys["dialogue"], dialogue_json)

    logger.info("Dialogue generation complete for run: %s", run_id)
    return dialogue_data


# Legacy wrapper for backward compatibility
def generate_dialogue(run_dir: Path, model: str = "gpt-4o") -> dict:
    """Generate dialogue from seed (legacy local-only interface)."""
    run_id = run_dir.name
    return generate_dialogue_for_run(run_id, model)


def update_dialogue_for_run(run_id: str, dialogue_data: dict) -> dict:
    """Update dialogue JSON for a run."""
    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    dialogue_json = json.dumps(dialogue_data, ensure_ascii=False, indent=2)
    run_storage.write_text(keys["dialogue"], dialogue_json)

    return dialogue_data


def update_dialogue(run_dir: Path, dialogue_data: dict) -> dict:
    """Update dialogue JSON for a run (legacy interface)."""
    return update_dialogue_for_run(run_dir.name, dialogue_data)


def generate_audio_for_run(run_id: str, voice_a: str = "Adam", voice_b: str = "Bella") -> dict:
    """Generate audio from dialogue."""
    logger.info("Starting audio generation for run: %s", run_id)
    from generate_audio import generate_audio as gen_audio

    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    if not run_storage.exists(keys["dialogue"]):
        raise FileNotFoundError("Dialogue not found. Generate dialogue first.")

    gen_audio(
        keys["dialogue"],
        keys["audio"],
        keys["timeline"],
        voice_a,
        voice_b,
        storage=run_storage,
    )

    # Return timeline data
    timeline_content = run_storage.read_text(keys["timeline"])
    return json.loads(timeline_content)


def generate_audio(run_dir: Path, voice_a: str = "Adam", voice_b: str = "Bella") -> dict:
    """Generate audio from dialogue (legacy interface)."""
    return generate_audio_for_run(run_dir.name, voice_a, voice_b)


def generate_images_for_run(run_id: str, model: str = "gpt-4o") -> dict:
    """Generate images from dialogue."""
    logger.info("Starting image generation for run: %s", run_id)
    from generate_images import generate_image_prompts, generate_all_images

    run_storage = get_run_storage(run_id)
    data_storage = get_data_storage()
    keys = get_run_keys()

    if not run_storage.exists(keys["dialogue"]):
        raise FileNotFoundError("Dialogue not found. Generate dialogue first.")

    if not run_storage.exists(keys["timeline"]):
        raise FileNotFoundError("Timeline not found. Generate audio first.")

    run_storage.makedirs(keys["images_dir"])

    # Get the active image prompt key
    image_prompt_key = get_image_prompt_key()

    # Generate image prompts
    prompts_data = generate_image_prompts(
        dialogue_path=keys["dialogue"],
        prompt_path=image_prompt_key,
        model=model,
        dialogue_storage=run_storage,
        prompt_storage=data_storage,
    )

    # Generate actual images
    prompts_data = generate_all_images(
        prompts_data,
        keys["images_dir"],
        storage=run_storage,
    )

    # Assign segment indices
    prompts_data = assign_segment_indices_for_run(prompts_data, run_id)

    # Save images metadata
    images_json = json.dumps(prompts_data, ensure_ascii=False, indent=2)
    run_storage.write_text(keys["images_json"], images_json)

    return prompts_data


def generate_images(run_dir: Path, model: str = "gpt-4o") -> dict:
    """Generate images from dialogue (legacy interface)."""
    return generate_images_for_run(run_dir.name, model)


def assign_segment_indices_for_run(prompts_data: dict, run_id: str) -> dict:
    """Distribute images evenly across timeline chunks."""
    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    timeline_content = run_storage.read_text(keys["timeline"])
    timeline = json.loads(timeline_content)

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


def assign_segment_indices(prompts_data: dict, timeline_path: Path) -> dict:
    """Distribute images evenly across timeline chunks (legacy interface)."""
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


def generate_video_for_run(run_id: str) -> str:
    """Render video using Remotion."""
    logger.info("Starting video generation for run: %s", run_id)
    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    if not run_storage.exists(keys["audio"]):
        raise FileNotFoundError("Audio not found. Generate audio first.")

    if not run_storage.exists(keys["timeline"]):
        raise FileNotFoundError("Timeline not found. Generate audio first.")

    # Get current episode number for DYSKUSJA counter
    episode_number = settings_service.get_episode_number()

    # Build command
    cmd = [
        sys.executable,
        str(SRC_DIR / "generate_video.py"),
        "--audio", keys["audio"],
        "--timeline", keys["timeline"],
        "--images", keys["images_dir"],
        "--episode", str(episode_number),
        "-o", keys["video"],
        "--run-id", run_id,
    ]

    if not is_s3_enabled():
        # For local mode, use full paths
        run_dir = _get_output_dir() / run_id
        cmd = [
            sys.executable,
            str(SRC_DIR / "generate_video.py"),
            "--audio", str(run_dir / keys["audio"]),
            "--timeline", str(run_dir / keys["timeline"]),
            "--images", str(run_dir / keys["images_dir"]),
            "--episode", str(episode_number),
            "-o", str(run_dir / keys["video"]),
        ]

    subprocess.run(cmd, check=True)

    return keys["video"]


def generate_video(run_dir: Path) -> Path:
    """Render video using Remotion (legacy interface)."""
    run_id = run_dir.name
    generate_video_for_run(run_id)
    return run_dir / "video.mp4"


def generate_yt_metadata_for_run(run_id: str, model: str = "gpt-4o") -> str:
    """Generate YouTube metadata."""
    from generate_yt_metadata import generate_yt_metadata as gen_metadata

    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    if not run_storage.exists(keys["news_data"]):
        raise FileNotFoundError("News data not found. Generate dialogue first.")

    # Get the active YT metadata prompt key
    yt_prompt_key = get_yt_metadata_prompt_key()

    metadata = gen_metadata(
        keys["news_data"],
        model,
        storage=run_storage,
        prompt_key=yt_prompt_key
    )
    run_storage.write_text(keys["yt_metadata"], metadata)

    return metadata


def generate_yt_metadata(run_dir: Path, model: str = "gpt-4o") -> str:
    """Generate YouTube metadata (legacy interface)."""
    return generate_yt_metadata_for_run(run_dir.name, model)


def upload_to_youtube_for_run(run_id: str, schedule_option: str = "auto") -> dict:
    """Upload video to YouTube.

    Args:
        run_id: The run ID
        schedule_option: One of "8:00", "18:00", "1hour", or "auto"
    """
    logger.info("Starting YouTube upload for run: %s (schedule: %s)", run_id, schedule_option)
    from upload_youtube import upload_to_youtube as yt_upload, parse_yt_metadata

    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    if not run_storage.exists(keys["video"]):
        raise FileNotFoundError("Video not found. Generate video first.")

    if not run_storage.exists(keys["yt_metadata"]):
        raise FileNotFoundError("YouTube metadata not found.")

    # Parse metadata for return info
    metadata = parse_yt_metadata(keys["yt_metadata"], storage=run_storage)

    # Get current episode number (before upload, for logging)
    current_episode = settings_service.get_episode_number()

    # Do the upload
    video_id, publish_at = yt_upload(
        keys["video"], keys["yt_metadata"],
        storage=run_storage,
        schedule_option=schedule_option
    )

    # Increment episode counter after successful upload
    new_episode = settings_service.increment_episode_counter()

    # Save upload info
    upload_info = {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "title": metadata["title"],
        "publish_at": publish_at,
        "status": "uploaded",
        "episode_number": current_episode,
    }

    upload_json = json.dumps(upload_info, ensure_ascii=False, indent=2)
    run_storage.write_text(keys["yt_upload"], upload_json)

    logger.info("YouTube upload complete: %s (episode %d)", upload_info["url"], current_episode)
    return upload_info


def upload_to_youtube(run_dir: Path) -> dict:
    """Upload video to YouTube (legacy interface)."""
    return upload_to_youtube_for_run(run_dir.name)


def update_images_metadata_for_run(run_id: str, images_data: dict) -> dict:
    """Update images.json for a run."""
    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    run_storage.makedirs(keys["images_dir"])
    images_json = json.dumps(images_data, ensure_ascii=False, indent=2)
    run_storage.write_text(keys["images_json"], images_json)

    return images_data


def update_images_metadata(run_dir: Path, images_data: dict) -> dict:
    """Update images.json for a run (legacy interface)."""
    return update_images_metadata_for_run(run_dir.name, images_data)


def regenerate_single_image_for_run(run_id: str, image_id: str) -> dict:
    """Regenerate a single image by its ID."""
    from generate_images import generate_image
    from openai import OpenAI

    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    if not run_storage.exists(keys["images_json"]):
        raise FileNotFoundError("images.json not found")

    # Load images metadata
    images_content = run_storage.read_text(keys["images_json"])
    images_data = json.loads(images_content)

    # Find the image by ID
    target_image = None
    for img in images_data.get("images", []):
        if img.get("id") == image_id:
            target_image = img
            break

    if not target_image:
        raise ValueError(f"Image with ID '{image_id}' not found")

    # Generate the image
    output_key = f"{keys['images_dir']}/{image_id}.png"
    client = OpenAI()

    generate_image(client, target_image["prompt"], output_key, storage=run_storage)

    # Update metadata
    target_image["file"] = f"{image_id}.png"
    if "error" in target_image:
        del target_image["error"]

    # Save updated metadata
    images_json = json.dumps(images_data, ensure_ascii=False, indent=2)
    run_storage.write_text(keys["images_json"], images_json)

    return {"image_id": image_id, "file": output_key}


def regenerate_single_image(run_dir: Path, image_id: str) -> dict:
    """Regenerate a single image by its ID (legacy interface)."""
    return regenerate_single_image_for_run(run_dir.name, image_id)


def drop_audio_for_run(run_id: str) -> dict:
    """
    Delete audio and timeline files for a run, allowing regeneration.
    Also drops video since it depends on audio.
    """
    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    deleted = []

    # Delete audio file
    if run_storage.exists(keys["audio"]):
        run_storage.delete(keys["audio"])
        deleted.append("audio.mp3")

    # Delete timeline
    if run_storage.exists(keys["timeline"]):
        run_storage.delete(keys["timeline"])
        deleted.append("timeline.json")

    # Also delete video since it depends on audio
    if run_storage.exists(keys["video"]):
        run_storage.delete(keys["video"])
        deleted.append("video.mp4")

    logger.info("Dropped audio for run %s: %s", run_id, deleted)
    return {"deleted": deleted}


def drop_video_for_run(run_id: str) -> dict:
    """
    Delete video file for a run, allowing regeneration.
    """
    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    deleted = []

    # Delete video file
    if run_storage.exists(keys["video"]):
        run_storage.delete(keys["video"])
        deleted.append("video.mp4")

    logger.info("Dropped video for run %s: %s", run_id, deleted)
    return {"deleted": deleted}


def drop_images_for_run(run_id: str) -> dict:
    """
    Delete all images for a run, allowing regeneration.
    Also drops video since it depends on images.
    """
    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    deleted = []

    # Delete images.json
    if run_storage.exists(keys["images_json"]):
        # First read to get image files
        try:
            content = run_storage.read_text(keys["images_json"])
            images_data = json.loads(content)
            for img in images_data.get("images", []):
                if img.get("file"):
                    img_key = f"images/{img['file']}"
                    if run_storage.exists(img_key):
                        run_storage.delete(img_key)
                        deleted.append(img["file"])
        except Exception:
            pass

        run_storage.delete(keys["images_json"])
        deleted.append("images.json")

    # Also delete video since it depends on images
    if run_storage.exists(keys["video"]):
        run_storage.delete(keys["video"])
        deleted.append("video.mp4")

    logger.info("Dropped images for run %s: %s", run_id, deleted)
    return {"deleted": deleted}


def delete_run_for_run(run_id: str) -> dict:
    """
    Delete an entire run and all its files.
    """
    run_storage = get_run_storage(run_id)

    # List all files in the run
    all_keys = run_storage.list_keys("")
    deleted = []

    for key in all_keys:
        try:
            run_storage.delete(key)
            deleted.append(key)
        except Exception as e:
            logger.warning("Failed to delete %s: %s", key, e)

    # For local storage, also remove the directory
    if not is_s3_enabled():
        run_dir = _get_output_dir() / run_id
        if run_dir.exists():
            import shutil
            shutil.rmtree(run_dir, ignore_errors=True)

    logger.info("Deleted run %s: %d files", run_id, len(deleted))
    return {"run_id": run_id, "deleted_count": len(deleted)}


def get_workflow_state_for_run(run_id: str) -> dict:
    """
    Determine current workflow state for a run.
    Returns dict with available actions.
    """
    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    has_seed = run_storage.exists(keys["seed"]) or run_storage.exists(keys["news_data"])
    has_dialogue = run_storage.exists(keys["dialogue"])
    has_audio = run_storage.exists(keys["audio"]) and run_storage.exists(keys["timeline"])
    has_images = run_storage.exists(keys["images_json"])
    has_video = run_storage.exists(keys["video"])
    has_yt_metadata = run_storage.exists(keys["yt_metadata"])

    # Determine current step and available actions
    if has_video and has_yt_metadata:
        current_step = "ready_to_upload"
        can_upload = True
    elif has_audio and has_images:
        current_step = "ready_for_video"
        can_upload = False
    elif has_audio:
        current_step = "generating_images"
        can_upload = False
    elif has_dialogue:
        current_step = "ready_for_audio"
        can_upload = False
    elif has_seed:
        current_step = "ready_for_dialogue"
        can_upload = False
    else:
        current_step = "new"
        can_upload = False

    return {
        "current_step": current_step,
        "has_seed": has_seed,
        "has_dialogue": has_dialogue,
        "has_audio": has_audio,
        "has_images": has_images,
        "has_video": has_video,
        "has_yt_metadata": has_yt_metadata,
        "can_generate_dialogue": has_seed and not has_dialogue,
        "can_edit_dialogue": has_dialogue,  # Always allow editing dialogue
        "can_generate_audio": has_dialogue and not has_audio,
        "can_generate_video": has_audio and has_images and not has_video,
        "can_upload": has_video and has_yt_metadata,
        # Regeneration options
        "can_drop_audio": has_audio,
        "can_drop_images": has_images,
        "can_drop_video": has_video,
    }


def get_workflow_state(run_dir: Path) -> dict:
    """Determine current workflow state for a run (legacy interface)."""
    return get_workflow_state_for_run(run_dir.name)
