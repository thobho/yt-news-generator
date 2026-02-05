"""
Settings service - manages global webapp settings.
Settings are persisted to a JSON file (local) or S3 (cloud).
"""

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

# Add src to path for storage imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from storage_config import get_config_storage, is_s3_enabled

# Settings file location
SETTINGS_FILE = PROJECT_ROOT / "webapp" / "settings.json"
SETTINGS_KEY = "settings.json"

# Available prompt versions
PROMPT_VERSIONS = ["5", "6", "7"]
PromptVersion = Literal["5", "6", "7"]

# Available TTS engines
TTSEngine = Literal["elevenlabs", "chatterbox"]
TTS_ENGINES = [
    {
        "id": "elevenlabs",
        "label": "ElevenLabs",
        "description": "Cloud TTS via ElevenLabs API (eleven_multilingual_v2)",
    },
    {
        "id": "chatterbox",
        "label": "Chatterbox",
        "description": "Chatterbox TTS on RunPod Serverless (voice cloning)",
    },
]

# Available image engines
ImageEngine = Literal["dalle", "fal"]
IMAGE_ENGINES = [
    {
        "id": "dalle",
        "label": "DALL-E 3",
        "description": "OpenAI DALL-E 3 image generation",
    },
    {
        "id": "fal",
        "label": "FLUX (fal.ai)",
        "description": "fal.ai FLUX Schnell fast image generation",
    },
]

# Starting episode number for DYSKUSJA counter
DEFAULT_EPISODE_NUMBER = 6


class Settings(BaseModel):
    """Global webapp settings."""
    prompt_version: PromptVersion = "7"
    episode_counter: int = DEFAULT_EPISODE_NUMBER
    tts_engine: TTSEngine = "elevenlabs"
    image_engine: ImageEngine = "dalle"


def get_default_settings() -> Settings:
    """Return default settings."""
    return Settings()


def load_settings() -> Settings:
    """Load settings from storage (local file or S3)."""
    try:
        storage = get_config_storage()
        if storage.exists(SETTINGS_KEY):
            content = storage.read_text(SETTINGS_KEY)
            data = json.loads(content)
            return Settings(**data)
    except Exception:
        pass

    return get_default_settings()


def save_settings(settings: Settings) -> None:
    """Save settings to storage (local file or S3)."""
    storage = get_config_storage()
    content = json.dumps(settings.model_dump(), indent=2)
    storage.write_text(SETTINGS_KEY, content)


def get_episode_number() -> int:
    """Get the current episode number for DYSKUSJA counter."""
    settings = load_settings()
    return settings.episode_counter


def increment_episode_counter() -> int:
    """
    Increment the episode counter and return the new value.
    Called after successful YouTube upload.
    """
    settings = load_settings()
    settings.episode_counter += 1
    save_settings(settings)
    return settings.episode_counter


def get_prompt_keys(version: PromptVersion) -> tuple[str, str]:
    """
    Get dialogue prompt keys for given version (for storage backend).
    Returns (main_prompt_key, refine_prompt_key).
    """
    main_key = f"dialogue-prompt/prompt-{version}.md"
    refine_key = f"dialogue-prompt/prompt-{version}-step-2.md"
    return main_key, refine_key


def get_prompt_paths(version: PromptVersion) -> tuple[Path, Path]:
    """
    Get dialogue prompt paths for given version (legacy local interface).
    Returns (main_prompt_path, refine_prompt_path).
    """
    data_dir = PROJECT_ROOT / "data" / "dialogue-prompt"
    main_prompt = data_dir / f"prompt-{version}.md"
    refine_prompt = data_dir / f"prompt-{version}-step-2.md"
    return main_prompt, refine_prompt


def get_available_tts_engines() -> list[dict]:
    """Get list of available TTS engines."""
    return TTS_ENGINES


def get_available_image_engines() -> list[dict]:
    """Get list of available image engines."""
    return IMAGE_ENGINES


def get_available_prompt_versions() -> list[dict]:
    """Get list of available prompt versions with metadata."""
    from storage_config import get_data_storage

    data_storage = get_data_storage()
    versions = []

    for version in PROMPT_VERSIONS:
        main_key = f"dialogue-prompt/prompt-{version}.md"
        refine_key = f"dialogue-prompt/prompt-{version}-step-2.md"

        if data_storage.exists(main_key) and data_storage.exists(refine_key):
            versions.append({
                "version": version,
                "label": f"Prompt v{version}",
                "files": {
                    "main": f"prompt-{version}.md",
                    "refine": f"prompt-{version}-step-2.md",
                }
            })

    return versions
