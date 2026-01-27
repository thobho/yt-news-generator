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
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT / "data"
SEEDS_DIR = DATA_DIR / "news-seeds"
IMAGE_PROMPT_PATH = DATA_DIR / "image_prompt.md"

# Import settings service for dynamic prompt paths
from . import settings as settings_service


def get_dialogue_prompt_paths() -> tuple[Path, Path]:
    """Get dialogue prompt paths based on current settings."""
    current_settings = settings_service.load_settings()
    return settings_service.get_prompt_paths(current_settings.prompt_version)

# Add src to path for imports
sys.path.insert(0, str(SRC_DIR))


def create_run_dir() -> Path:
    """Create a new run directory with timestamp ID."""
    run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = OUTPUT_DIR / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def create_seed(news_text: str) -> tuple[Path, Path]:
    """
    Create a new seed file and run directory.
    Returns (seed_path, run_dir).
    """
    # Create run directory
    run_dir = create_run_dir()

    # Create seed data
    seed_data = {"news_seed": news_text}

    # Save seed to run directory
    seed_path = run_dir / "seed.json"
    with open(seed_path, "w", encoding="utf-8") as f:
        json.dump(seed_data, f, ensure_ascii=False, indent=2)

    # Also save to seeds directory with run ID
    run_id = run_dir.name
    seeds_seed_path = SEEDS_DIR / f"{run_id}.json"
    SEEDS_DIR.mkdir(parents=True, exist_ok=True)
    with open(seeds_seed_path, "w", encoding="utf-8") as f:
        json.dump(seed_data, f, ensure_ascii=False, indent=2)

    return seed_path, run_dir


def get_run_paths(run_dir: Path) -> dict:
    """Get all standard paths for a run."""
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


def generate_dialogue(run_dir: Path, model: str = "gpt-4o") -> dict:
    """
    Generate dialogue from seed.
    Steps: perplexity search -> dialogue generation -> refinement
    """
    from perplexity_search import run_perplexity_enrichment
    from generate_dialogue import generate_dialogue as gen_dialogue, refine_dialogue

    paths = get_run_paths(run_dir)

    # Find seed file
    seed_path = paths["seed"]
    if not seed_path.exists():
        # Try to find any seed file in the run dir
        seed_files = list(run_dir.glob("seed*.json"))
        if seed_files:
            seed_path = seed_files[0]
        else:
            raise FileNotFoundError(f"No seed file found in {run_dir}")

    # Step 1: Perplexity search
    run_perplexity_enrichment(
        input_path=seed_path,
        output_path=paths["news_data"]
    )

    # Step 2: Generate dialogue
    with open(paths["news_data"], "r", encoding="utf-8") as f:
        news_data = json.load(f)

    # Get prompt paths from settings
    dialogue_prompt_path, refine_prompt_path = get_dialogue_prompt_paths()

    dialogue_data = gen_dialogue(news_data, dialogue_prompt_path, model)

    # Step 3: Refine dialogue
    dialogue_data = refine_dialogue(
        dialogue_data, news_data, refine_prompt_path, model
    )

    # Save dialogue
    with open(paths["dialogue"], "w", encoding="utf-8") as f:
        json.dump(dialogue_data, f, ensure_ascii=False, indent=2)

    return dialogue_data


def update_dialogue(run_dir: Path, dialogue_data: dict) -> dict:
    """Update dialogue JSON for a run."""
    paths = get_run_paths(run_dir)

    with open(paths["dialogue"], "w", encoding="utf-8") as f:
        json.dump(dialogue_data, f, ensure_ascii=False, indent=2)

    return dialogue_data


def generate_audio(run_dir: Path, voice_a: str = "Adam", voice_b: str = "Bella") -> dict:
    """Generate audio from dialogue."""
    from generate_audio import generate_audio as gen_audio

    paths = get_run_paths(run_dir)

    if not paths["dialogue"].exists():
        raise FileNotFoundError("Dialogue not found. Generate dialogue first.")

    gen_audio(
        paths["dialogue"],
        paths["audio"],
        paths["timeline"],
        voice_a,
        voice_b,
    )

    # Return timeline data
    with open(paths["timeline"], "r", encoding="utf-8") as f:
        return json.load(f)


def generate_images(run_dir: Path, model: str = "gpt-4o") -> dict:
    """Generate images from dialogue."""
    from generate_images import generate_image_prompts, generate_all_images

    paths = get_run_paths(run_dir)

    if not paths["dialogue"].exists():
        raise FileNotFoundError("Dialogue not found. Generate dialogue first.")

    if not paths["timeline"].exists():
        raise FileNotFoundError("Timeline not found. Generate audio first.")

    paths["images_dir"].mkdir(parents=True, exist_ok=True)

    # Generate image prompts
    prompts_data = generate_image_prompts(
        dialogue_path=paths["dialogue"],
        prompt_path=IMAGE_PROMPT_PATH,
        model=model,
    )

    # Generate actual images
    prompts_data = generate_all_images(prompts_data, paths["images_dir"])

    # Assign segment indices
    prompts_data = assign_segment_indices(prompts_data, paths["timeline"])

    # Save images metadata
    with open(paths["images_json"], "w", encoding="utf-8") as f:
        json.dump(prompts_data, f, ensure_ascii=False, indent=2)

    return prompts_data


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


def generate_video(run_dir: Path) -> Path:
    """Render video using Remotion."""
    paths = get_run_paths(run_dir)

    if not paths["audio"].exists():
        raise FileNotFoundError("Audio not found. Generate audio first.")

    if not paths["timeline"].exists():
        raise FileNotFoundError("Timeline not found. Generate audio first.")

    # Get current episode number for DYSKUSJA counter
    episode_number = settings_service.get_episode_number()

    # Call generate_video.py as subprocess
    subprocess.run(
        [
            sys.executable,
            str(SRC_DIR / "generate_video.py"),
            "--audio", str(paths["audio"]),
            "--timeline", str(paths["timeline"]),
            "--images", str(paths["images_dir"]),
            "--episode", str(episode_number),
            "-o", str(paths["video"]),
        ],
        check=True,
    )

    return paths["video"]


def generate_yt_metadata(run_dir: Path, model: str = "gpt-4o") -> str:
    """Generate YouTube metadata."""
    from generate_yt_metadata import generate_yt_metadata as gen_metadata

    paths = get_run_paths(run_dir)

    if not paths["news_data"].exists():
        raise FileNotFoundError("News data not found. Generate dialogue first.")

    metadata = gen_metadata(paths["news_data"], model)

    with open(paths["yt_metadata"], "w", encoding="utf-8") as f:
        f.write(metadata)

    return metadata


def upload_to_youtube(run_dir: Path) -> dict:
    """Upload video to YouTube."""
    from upload_youtube import upload_to_youtube as yt_upload, parse_yt_metadata, get_scheduled_publish_time

    paths = get_run_paths(run_dir)

    if not paths["video"].exists():
        raise FileNotFoundError("Video not found. Generate video first.")

    if not paths["yt_metadata"].exists():
        raise FileNotFoundError("YouTube metadata not found.")

    # Parse metadata for return info
    metadata = parse_yt_metadata(paths["yt_metadata"])
    publish_at = get_scheduled_publish_time()

    # Get current episode number (before upload, for logging)
    current_episode = settings_service.get_episode_number()

    # Do the upload
    video_id = yt_upload(paths["video"], paths["yt_metadata"])

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

    with open(paths["yt_upload"], "w", encoding="utf-8") as f:
        json.dump(upload_info, f, ensure_ascii=False, indent=2)

    return upload_info


def update_images_metadata(run_dir: Path, images_data: dict) -> dict:
    """Update images.json for a run."""
    paths = get_run_paths(run_dir)

    paths["images_dir"].mkdir(parents=True, exist_ok=True)

    with open(paths["images_json"], "w", encoding="utf-8") as f:
        json.dump(images_data, f, ensure_ascii=False, indent=2)

    return images_data


def regenerate_single_image(run_dir: Path, image_id: str) -> dict:
    """Regenerate a single image by its ID."""
    from generate_images import generate_image

    from openai import OpenAI

    paths = get_run_paths(run_dir)

    if not paths["images_json"].exists():
        raise FileNotFoundError("images.json not found")

    # Load images metadata
    with open(paths["images_json"], "r", encoding="utf-8") as f:
        images_data = json.load(f)

    # Find the image by ID
    target_image = None
    for img in images_data.get("images", []):
        if img.get("id") == image_id:
            target_image = img
            break

    if not target_image:
        raise ValueError(f"Image with ID '{image_id}' not found")

    # Generate the image
    output_path = paths["images_dir"] / f"{image_id}.png"
    client = OpenAI()

    generate_image(client, target_image["prompt"], output_path)

    # Update metadata
    target_image["file"] = f"{image_id}.png"
    if "error" in target_image:
        del target_image["error"]

    # Save updated metadata
    with open(paths["images_json"], "w", encoding="utf-8") as f:
        json.dump(images_data, f, ensure_ascii=False, indent=2)

    return {"image_id": image_id, "file": str(output_path)}


def get_workflow_state(run_dir: Path) -> dict:
    """
    Determine current workflow state for a run.
    Returns dict with available actions.
    """
    paths = get_run_paths(run_dir)

    has_seed = paths["seed"].exists() or paths["news_data"].exists()
    has_dialogue = paths["dialogue"].exists()
    has_audio = paths["audio"].exists() and paths["timeline"].exists()
    has_images = paths["images_json"].exists()
    has_video = paths["video"].exists()
    has_yt_metadata = paths["yt_metadata"].exists()

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
        "can_edit_dialogue": has_dialogue and not has_audio,
        "can_generate_audio": has_dialogue and not has_audio,
        "can_generate_video": has_audio and has_images and not has_video,
        "can_upload": has_video and has_yt_metadata,
    }
