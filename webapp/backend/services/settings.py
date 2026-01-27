"""
Settings service - manages global webapp settings.
Settings are persisted to a JSON file.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

# Settings file location
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SETTINGS_FILE = PROJECT_ROOT / "webapp" / "settings.json"

# Available prompt versions
PROMPT_VERSIONS = ["5", "6"]
PromptVersion = Literal["5", "6"]

# Starting episode number for DYSKUSJA counter
DEFAULT_EPISODE_NUMBER = 6


class Settings(BaseModel):
    """Global webapp settings."""
    prompt_version: PromptVersion = "5"
    episode_counter: int = DEFAULT_EPISODE_NUMBER


def get_default_settings() -> Settings:
    """Return default settings."""
    return Settings()


def load_settings() -> Settings:
    """Load settings from file, or return defaults if not found."""
    if not SETTINGS_FILE.exists():
        return get_default_settings()

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Settings(**data)
    except (json.JSONDecodeError, ValueError):
        return get_default_settings()


def save_settings(settings: Settings) -> None:
    """Save settings to file."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings.model_dump(), f, indent=2)


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


def get_prompt_paths(version: PromptVersion) -> tuple[Path, Path]:
    """
    Get dialogue prompt paths for given version.
    Returns (main_prompt_path, refine_prompt_path).
    """
    data_dir = PROJECT_ROOT / "data" / "dialogue-prompt"
    main_prompt = data_dir / f"prompt-{version}.md"
    refine_prompt = data_dir / f"prompt-{version}-step-2.md"
    return main_prompt, refine_prompt


def get_available_prompt_versions() -> list[dict]:
    """Get list of available prompt versions with metadata."""
    data_dir = PROJECT_ROOT / "data" / "dialogue-prompt"
    versions = []

    for version in PROMPT_VERSIONS:
        main_prompt = data_dir / f"prompt-{version}.md"
        refine_prompt = data_dir / f"prompt-{version}-step-2.md"

        if main_prompt.exists() and refine_prompt.exists():
            versions.append({
                "version": version,
                "label": f"Prompt v{version}",
                "files": {
                    "main": f"prompt-{version}.md",
                    "refine": f"prompt-{version}-step-2.md",
                }
            })

    return versions
