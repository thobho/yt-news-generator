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


def get_dialogue_prompt_keys(prompt_id: Optional[str] = None) -> tuple[str, str, str | None]:
    """Get dialogue prompt keys based on specified or active prompt.

    Args:
        prompt_id: Optional specific prompt ID to use. If None, uses active prompt.

    Returns:
        Tuple of (main_key, step2_key, step3_key). step3_key may be None if not exists.
    """
    # Use specified prompt_id or fall back to active
    selected_id = prompt_id or prompts_service.get_active_prompt_id("dialogue")
    if selected_id:
        main_key = f"prompts/dialogue/{selected_id}.md"
        refine_key = f"prompts/dialogue/{selected_id}-step-2.md"
        polish_key = f"prompts/dialogue/{selected_id}-step-3.md"

        # Check if step-3 exists
        data_storage = get_data_storage()
        if not data_storage.exists(polish_key):
            polish_key = None

        return main_key, refine_key, polish_key

    # Fallback to old path structure for backward compatibility
    current_settings = settings_service.load_settings()
    version = current_settings.prompt_version
    main_key = f"dialogue-prompt/prompt-{version}.md"
    refine_key = f"dialogue-prompt/prompt-{version}-step-2.md"
    return main_key, refine_key, None


def get_dialogue_temperatures(prompt_id: Optional[str] = None) -> tuple[float, float, float]:
    """Get temperature settings for dialogue generation steps.

    Args:
        prompt_id: Optional specific prompt ID to use. If None, uses active prompt.
    """
    if prompt_id:
        prompt = prompts_service.get_prompt("dialogue", prompt_id)
        if prompt:
            return (prompt.temperature, prompt.step2_temperature, prompt.step3_temperature)
    return prompts_service.get_active_dialogue_temperatures()


def get_run_prompt_selections(run_id: str) -> dict:
    """
    Get prompt selections from seed.json for a run.

    Returns dict with keys: dialogue, image, research, yt_metadata (values are prompt IDs or None).
    """
    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    prompts = {}
    if run_storage.exists(keys["seed"]):
        try:
            seed_content = run_storage.read_text(keys["seed"])
            seed_data = json.loads(seed_content)
            prompts = seed_data.get("prompts", {})
        except Exception:
            pass

    return prompts


def save_prompts_snapshot(run_id: str) -> None:
    """
    Save a snapshot of all prompts used for this run.
    Creates prompts_snapshot/ folder with copies of selected prompts (or active if not selected).
    """
    run_storage = get_run_storage(run_id)
    data_storage = get_data_storage()

    # Get prompt selections from seed.json
    selections = get_run_prompt_selections(run_id)

    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "prompts": {}
    }

    # Save dialogue prompts (use selected or fall back to active)
    dialogue_id = selections.get("dialogue") or prompts_service.get_active_prompt_id("dialogue")
    if dialogue_id:
        dialogue_prompt = prompts_service.get_prompt("dialogue", dialogue_id)
        if dialogue_prompt:
            snapshot["prompts"]["dialogue"] = {
                "id": dialogue_id,
                "temperature": dialogue_prompt.temperature,
                "step2_temperature": dialogue_prompt.step2_temperature,
                "step3_temperature": dialogue_prompt.step3_temperature,
            }
            # Save prompt contents
            run_storage.write_text("prompts_snapshot/dialogue_step1.md", dialogue_prompt.content)
            if dialogue_prompt.step2_content:
                run_storage.write_text("prompts_snapshot/dialogue_step2.md", dialogue_prompt.step2_content)
            if dialogue_prompt.step3_content:
                run_storage.write_text("prompts_snapshot/dialogue_step3.md", dialogue_prompt.step3_content)

    # Save image prompt
    image_id = selections.get("image") or prompts_service.get_active_prompt_id("image")
    if image_id:
        image_prompt = prompts_service.get_prompt("image", image_id)
        if image_prompt:
            snapshot["prompts"]["image"] = {
                "id": image_id,
                "temperature": image_prompt.temperature,
            }
            run_storage.write_text("prompts_snapshot/image.md", image_prompt.content)

    # Save research prompt
    research_id = selections.get("research") or prompts_service.get_active_prompt_id("research")
    if research_id:
        research_prompt = prompts_service.get_prompt("research", research_id)
        if research_prompt:
            snapshot["prompts"]["research"] = {
                "id": research_id,
                "temperature": research_prompt.temperature,
            }
            run_storage.write_text("prompts_snapshot/research.md", research_prompt.content)

    # Save yt-metadata prompt
    yt_id = selections.get("yt_metadata") or prompts_service.get_active_prompt_id("yt-metadata")
    if yt_id:
        yt_prompt = prompts_service.get_prompt("yt-metadata", yt_id)
        if yt_prompt:
            snapshot["prompts"]["yt-metadata"] = {
                "id": yt_id,
                "temperature": yt_prompt.temperature,
            }
            run_storage.write_text("prompts_snapshot/yt_metadata.md", yt_prompt.content)

    # Save snapshot config
    run_storage.write_text(
        "prompts_snapshot/config.json",
        json.dumps(snapshot, ensure_ascii=False, indent=2)
    )
    logger.info("Saved prompts snapshot for run: %s", run_id)


def get_image_prompt_key(prompt_id: Optional[str] = None) -> str:
    """Get image prompt key based on specified or active prompt.

    Args:
        prompt_id: Optional specific prompt ID to use. If None, uses active prompt.
    """
    selected_id = prompt_id or prompts_service.get_active_prompt_id("image")
    if selected_id:
        return f"prompts/image/{selected_id}.md"
    # Fallback to old path
    return "image_prompt.md"


def get_research_prompt_key(prompt_id: Optional[str] = None) -> str:
    """Get research/summarizer prompt key based on specified or active prompt.

    Args:
        prompt_id: Optional specific prompt ID to use. If None, uses active prompt.
    """
    selected_id = prompt_id or prompts_service.get_active_prompt_id("research")
    if selected_id:
        return f"prompts/research/{selected_id}.md"
    # Fallback to old path
    return "fetch_sources_summariser_prompt.md"


def get_yt_metadata_prompt_key(prompt_id: Optional[str] = None) -> str:
    """Get YouTube metadata prompt key based on specified or active prompt.

    Args:
        prompt_id: Optional specific prompt ID to use. If None, uses active prompt.
    """
    selected_id = prompt_id or prompts_service.get_active_prompt_id("yt-metadata")
    if selected_id:
        return f"prompts/yt-metadata/{selected_id}.md"
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


def create_seed(
    news_text: str,
    auto_generated: bool = False,
    source_info: Optional[dict] = None,
    prompts: Optional[dict] = None
) -> tuple[str, str]:
    """
    Create a new seed file and run directory.

    Args:
        news_text: The news text content
        auto_generated: Whether this run was auto-generated by scheduler
        source_info: Optional metadata about the news source
        prompts: Optional prompt selections (dialogue, image, research, yt_metadata IDs)

    Returns (run_id, seed_key).
    """
    run_id, run_dir = create_run_dir()
    run_storage = get_run_storage(run_id)

    # Create seed data with optional metadata
    seed_data = {"news_seed": news_text}
    if auto_generated:
        seed_data["auto_generated"] = True
    if source_info:
        seed_data["source_info"] = source_info
    if prompts:
        # Store prompt selections (filter out None values)
        prompt_selections = {k: v for k, v in prompts.items() if v is not None}
        if prompt_selections:
            seed_data["prompts"] = prompt_selections
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
    Steps: perplexity search -> dialogue generation -> refinement -> polish
    """
    logger.info("Starting dialogue generation for run: %s", run_id)
    from perplexity_search import run_perplexity_enrichment
    from generate_dialogue import generate_dialogue as gen_dialogue, refine_dialogue, polish_dialogue

    run_storage = get_run_storage(run_id)
    data_storage = get_data_storage()
    keys = get_run_keys()

    # Find seed file
    if not run_storage.exists(keys["seed"]):
        raise FileNotFoundError(f"No seed file found for run {run_id}")

    # Get prompt selections from seed.json
    selections = get_run_prompt_selections(run_id)
    dialogue_prompt_id = selections.get("dialogue")

    # Save snapshot of all prompts used for this run
    save_prompts_snapshot(run_id)

    # Step 1: Perplexity search
    run_perplexity_enrichment(
        input_path=keys["seed"],
        output_path=keys["news_data"],
        storage=run_storage,
    )

    # Step 2: Generate dialogue
    news_content = run_storage.read_text(keys["news_data"])
    news_data = json.loads(news_content)

    # Get prompt keys and temperatures (use selected or fall back to active)
    dialogue_prompt_key, refine_prompt_key, polish_prompt_key = get_dialogue_prompt_keys(dialogue_prompt_id)
    temp1, temp2, temp3 = get_dialogue_temperatures(dialogue_prompt_id)

    dialogue_data = gen_dialogue(
        news_data,
        dialogue_prompt_key,
        model,
        storage=data_storage,
        temperature=temp1,
    )

    # Step 3: Refine dialogue (logic/structure)
    dialogue_data = refine_dialogue(
        dialogue_data,
        news_data,
        refine_prompt_key,
        model,
        storage=data_storage,
        temperature=temp2,
    )

    # Step 4: Polish dialogue (language/style) - optional
    if polish_prompt_key:
        dialogue_data = polish_dialogue(
            dialogue_data,
            polish_prompt_key,
            model,
            storage=data_storage,
            temperature=temp3,
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
    settings = settings_service.load_settings()
    tts_engine = settings.tts_engine
    logger.info("Starting audio generation for run: %s (engine=%s)", run_id, tts_engine)

    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    if not run_storage.exists(keys["dialogue"]):
        raise FileNotFoundError("Dialogue not found. Generate dialogue first.")

    if tts_engine == "chatterbox":
        from generate_audio_runpod import generate_audio as gen_audio
        gen_audio(
            keys["dialogue"],
            keys["audio"],
            keys["timeline"],
            voice_a="male",
            voice_b="female",
            storage=run_storage,
        )
    else:
        from generate_audio import generate_audio as gen_audio
        gen_audio(
            keys["dialogue"],
            keys["audio"],
            keys["timeline"],
            voice_a,
            voice_b,
            storage=run_storage,
        )

    # Return timeline data
    if run_storage.exists(keys["timeline"]):
        timeline_content = run_storage.read_text(keys["timeline"])
        return json.loads(timeline_content)
    return {}


def generate_audio(run_dir: Path, voice_a: str = "Adam", voice_b: str = "Bella") -> dict:
    """Generate audio from dialogue (legacy interface)."""
    return generate_audio_for_run(run_dir.name, voice_a, voice_b)


def generate_images_for_run(run_id: str, model: str = "gpt-4o") -> dict:
    """Generate images from dialogue."""
    settings = settings_service.load_settings()
    image_engine = settings.image_engine
    logger.info("Starting image generation for run: %s (engine=%s)", run_id, image_engine)

    from generate_images import generate_image_prompts

    if image_engine == "fal":
        from generate_images_fal import generate_all_images
    else:
        from generate_images import generate_all_images

    run_storage = get_run_storage(run_id)
    data_storage = get_data_storage()
    keys = get_run_keys()

    if not run_storage.exists(keys["dialogue"]):
        raise FileNotFoundError("Dialogue not found. Generate dialogue first.")

    if not run_storage.exists(keys["timeline"]):
        raise FileNotFoundError("Timeline not found. Generate audio first.")

    run_storage.makedirs(keys["images_dir"])

    # Get prompt selections from seed.json
    selections = get_run_prompt_selections(run_id)
    image_prompt_id = selections.get("image")

    # Get the image prompt key (use selected or fall back to active)
    image_prompt_key = get_image_prompt_key(image_prompt_id)

    # Generate image prompts
    prompts_data = generate_image_prompts(
        dialogue_path=keys["dialogue"],
        prompt_path=image_prompt_key,
        model=model,
        dialogue_storage=run_storage,
        prompt_storage=data_storage,
    )

    # Generate actual images
    generate_kwargs = {
        "prompts_data": prompts_data,
        "output_dir": keys["images_dir"],
        "storage": run_storage,
    }
    if image_engine == "fal":
        generate_kwargs["model"] = settings.fal_model
    prompts_data = generate_all_images(**generate_kwargs)

    # Save images metadata
    images_json = json.dumps(prompts_data, ensure_ascii=False, indent=2)
    run_storage.write_text(keys["images_json"], images_json)

    return prompts_data


def generate_images(run_dir: Path, model: str = "gpt-4o") -> dict:
    """Generate images from dialogue (legacy interface)."""
    return generate_images_for_run(run_dir.name, model)


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

    # Get prompt selections from seed.json
    selections = get_run_prompt_selections(run_id)
    yt_prompt_id = selections.get("yt_metadata")

    # Get the YT metadata prompt key (use selected or fall back to active)
    yt_prompt_key = get_yt_metadata_prompt_key(yt_prompt_id)

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


def delete_youtube_for_run(run_id: str) -> dict:
    """Delete video from YouTube and remove yt_upload.json."""
    logger.info("Deleting YouTube video for run: %s", run_id)
    from upload_youtube import delete_from_youtube

    run_storage = get_run_storage(run_id)
    keys = get_run_keys()

    if not run_storage.exists(keys["yt_upload"]):
        raise FileNotFoundError("No YouTube upload found for this run.")

    # Read upload info to get video_id
    upload_content = run_storage.read_text(keys["yt_upload"])
    upload_info = json.loads(upload_content)
    video_id = upload_info.get("video_id")

    if not video_id:
        raise ValueError("No video_id found in upload info.")

    # Delete from YouTube
    delete_from_youtube(video_id)

    # Remove yt_upload.json
    run_storage.delete(keys["yt_upload"])

    logger.info("YouTube video deleted for run %s: %s", run_id, video_id)
    return {"deleted_video_id": video_id}


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
    settings = settings_service.load_settings()
    image_engine = settings.image_engine

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

    if image_engine == "fal":
        from generate_images_fal import generate_image
        generate_image(target_image["prompt"], output_key, storage=run_storage, model=settings.fal_model)
    else:
        from generate_images import generate_image
        from openai import OpenAI
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


def list_runs() -> list[dict]:
    """
    List all runs with their IDs and timestamps.
    Returns list of dicts: [{'run_id': '...', 'created_at': '...'}]
    """
    output_storage = get_output_storage()
    runs = []

    if is_s3_enabled():
        # List ALL keys once (single S3 call)
        all_keys = output_storage.list_keys("")
        
        # Group keys by run_id
        run_ids = set()
        for key in all_keys:
            parts = key.split("/", 1)
            if parts and parts[0].startswith("run_"):
                run_ids.add(parts[0])
        
        for run_id in sorted(list(run_ids), reverse=True):
            runs.append({
                "run_id": run_id,
                "created_at": run_id.replace("run_", "").replace("_", " "),
            })
    else:
        # Local filesystem mode
        output_dir = _get_output_dir()
        if not output_dir.exists():
            return []

        entries = [
            entry for entry in output_dir.iterdir()
            if entry.is_dir() and entry.name.startswith("run_")
        ]
        
        # Sort by name descending (timestamp based)
        entries.sort(key=lambda x: x.name, reverse=True)
        
        for entry in entries:
            runs.append({
                "run_id": entry.name,
                "created_at": entry.name.replace("run_", "").replace("_", " "),
            })

    return runs


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
    has_yt_upload = run_storage.exists(keys["yt_upload"])

    # Determine current step and available actions
    if has_video and has_yt_metadata:
        current_step = "ready_to_upload"
        can_upload = not has_yt_upload
    elif has_audio and has_images:
        current_step = "ready_for_video"
        can_upload = False
    elif has_audio:
        current_step = "ready_for_images"
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
        "can_generate_images": has_audio and not has_images,
        "can_generate_video": has_audio and has_images and not has_video,
        "can_upload": can_upload,
        "can_delete_youtube": has_yt_upload,
        # Regeneration options
        "can_drop_audio": has_audio,
        "can_drop_images": has_images,
        "can_drop_video": has_video,
    }


def get_workflow_state(run_dir: Path) -> dict:
    """Determine current workflow state for a run (legacy interface)."""
    return get_workflow_state_for_run(run_dir.name)
