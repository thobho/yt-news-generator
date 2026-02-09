"""
Prompts service - manages prompt templates with CRUD operations.
Prompts are organized by type in S3:
  data/prompts/dialogue/
  data/prompts/image/
  data/prompts/research/
  data/prompts/yt-metadata/
Each type has an active.json file that stores which prompt is currently active.
"""

import json
import sys
from pathlib import Path
from typing import Literal
from datetime import datetime

from pydantic import BaseModel

# Add src to path for storage imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from storage_config import get_data_storage

# Prompt types
PromptType = Literal["dialogue", "image", "research", "yt-metadata"]
PROMPT_TYPES: list[PromptType] = ["dialogue", "image", "research", "yt-metadata"]

# For dialogue prompts, we have 3 steps (main + step-2 + step-3)
DIALOGUE_STEP2_SUFFIX = "-step-2"
DIALOGUE_STEP3_SUFFIX = "-step-3"


class PromptInfo(BaseModel):
    """Information about a single prompt."""
    id: str
    name: str
    prompt_type: PromptType
    created_at: str | None = None
    is_active: bool = False
    # For dialogue prompts, indicates which steps exist
    has_step2: bool = False
    has_step3: bool = False


class PromptContent(BaseModel):
    """Full prompt content."""
    id: str
    name: str
    prompt_type: PromptType
    content: str
    temperature: float = 0.7  # Temperature for main prompt (0-1)
    # For dialogue prompts (3-step system)
    step2_content: str | None = None  # Logic/structure fixes
    step2_temperature: float = 0.5  # Temperature for step 2
    step3_content: str | None = None  # Language/style polish
    step3_temperature: float = 0.6  # Temperature for step 3
    is_active: bool = False


class ActiveConfig(BaseModel):
    """Active prompt configuration for a type."""
    active: str  # prompt id


def _get_prompts_prefix(prompt_type: PromptType) -> str:
    """Get S3 prefix for prompt type."""
    return f"prompts/{prompt_type}"


def _get_active_key(prompt_type: PromptType) -> str:
    """Get key for active.json file."""
    return f"{_get_prompts_prefix(prompt_type)}/active.json"


def _get_prompt_key(prompt_type: PromptType, prompt_id: str) -> str:
    """Get key for a prompt file."""
    return f"{_get_prompts_prefix(prompt_type)}/{prompt_id}.md"


def _get_step2_key(prompt_id: str) -> str:
    """Get key for dialogue step-2 prompt file."""
    return f"{_get_prompts_prefix('dialogue')}/{prompt_id}{DIALOGUE_STEP2_SUFFIX}.md"


def _get_step3_key(prompt_id: str) -> str:
    """Get key for dialogue step-3 prompt file."""
    return f"{_get_prompts_prefix('dialogue')}/{prompt_id}{DIALOGUE_STEP3_SUFFIX}.md"


def _get_config_key(prompt_type: PromptType, prompt_id: str) -> str:
    """Get key for prompt config file (stores temperature, etc.)."""
    return f"{_get_prompts_prefix(prompt_type)}/{prompt_id}.config.json"


def _load_prompt_config(prompt_type: PromptType, prompt_id: str) -> dict:
    """Load prompt config (temperature settings)."""
    storage = get_data_storage()
    config_key = _get_config_key(prompt_type, prompt_id)

    defaults = {
        "temperature": 0.7,
        "step2_temperature": 0.5,
        "step3_temperature": 0.6,
    }

    if storage.exists(config_key):
        try:
            content = storage.read_text(config_key)
            config = json.loads(content)
            # Merge with defaults
            return {**defaults, **config}
        except Exception:
            pass
    return defaults


def _save_prompt_config(
    prompt_type: PromptType,
    prompt_id: str,
    temperature: float | None = None,
    step2_temperature: float | None = None,
    step3_temperature: float | None = None
) -> None:
    """Save prompt config (temperature settings)."""
    storage = get_data_storage()
    config_key = _get_config_key(prompt_type, prompt_id)

    # Load existing config
    config = _load_prompt_config(prompt_type, prompt_id)

    # Update with new values
    if temperature is not None:
        config["temperature"] = max(0.0, min(1.0, temperature))
    if step2_temperature is not None:
        config["step2_temperature"] = max(0.0, min(1.0, step2_temperature))
    if step3_temperature is not None:
        config["step3_temperature"] = max(0.0, min(1.0, step3_temperature))

    storage.write_text(config_key, json.dumps(config, indent=2))


def get_active_prompt_id(prompt_type: PromptType) -> str | None:
    """Get the active prompt ID for a type."""
    storage = get_data_storage()
    active_key = _get_active_key(prompt_type)

    if storage.exists(active_key):
        try:
            content = storage.read_text(active_key)
            config = json.loads(content)
            return config.get("active")
        except Exception:
            pass
    return None


def set_active_prompt(prompt_type: PromptType, prompt_id: str) -> None:
    """Set the active prompt for a type."""
    storage = get_data_storage()

    # Verify prompt exists
    prompt_key = _get_prompt_key(prompt_type, prompt_id)
    if not storage.exists(prompt_key):
        raise ValueError(f"Prompt {prompt_id} does not exist for type {prompt_type}")

    # Write active config
    active_key = _get_active_key(prompt_type)
    config = {"active": prompt_id, "updated_at": datetime.now().isoformat()}
    storage.write_text(active_key, json.dumps(config, indent=2))


def list_prompts(prompt_type: PromptType) -> list[PromptInfo]:
    """List all prompts of a given type."""
    storage = get_data_storage()
    prefix = _get_prompts_prefix(prompt_type)
    active_id = get_active_prompt_id(prompt_type)

    # List all .md files in the prefix
    all_keys = storage.list_keys(prefix)

    prompts: dict[str, PromptInfo] = {}
    step2_ids: set[str] = set()
    step3_ids: set[str] = set()

    for key in all_keys:
        if not key.endswith(".md"):
            continue

        # Extract prompt ID from key
        filename = key.split("/")[-1]
        prompt_id = filename[:-3]  # Remove .md

        # Check if this is a step-2 or step-3 file (for dialogue)
        if prompt_type == "dialogue":
            if prompt_id.endswith(DIALOGUE_STEP3_SUFFIX):
                base_id = prompt_id[:-len(DIALOGUE_STEP3_SUFFIX)]
                step3_ids.add(base_id)
                continue
            if prompt_id.endswith(DIALOGUE_STEP2_SUFFIX):
                base_id = prompt_id[:-len(DIALOGUE_STEP2_SUFFIX)]
                step2_ids.add(base_id)
                continue

        # Create prompt info
        prompts[prompt_id] = PromptInfo(
            id=prompt_id,
            name=_format_prompt_name(prompt_id),
            prompt_type=prompt_type,
            is_active=(prompt_id == active_id),
            has_step2=False,
            has_step3=False
        )

    # Mark dialogue prompts that have step-2 and step-3
    for base_id in step2_ids:
        if base_id in prompts:
            prompts[base_id].has_step2 = True
    for base_id in step3_ids:
        if base_id in prompts:
            prompts[base_id].has_step3 = True

    # Sort by ID (which typically includes version number)
    return sorted(prompts.values(), key=lambda p: p.id)


def _format_prompt_name(prompt_id: str) -> str:
    """Format prompt ID into display name."""
    # e.g., "prompt-7" -> "Prompt v7", "default" -> "Default"
    if prompt_id.startswith("prompt-"):
        version = prompt_id.replace("prompt-", "")
        return f"Prompt v{version}"
    return prompt_id.replace("-", " ").replace("_", " ").title()


def get_prompt(prompt_type: PromptType, prompt_id: str) -> PromptContent | None:
    """Get full prompt content."""
    storage = get_data_storage()
    prompt_key = _get_prompt_key(prompt_type, prompt_id)

    if not storage.exists(prompt_key):
        return None

    content = storage.read_text(prompt_key)
    active_id = get_active_prompt_id(prompt_type)

    # Load temperature config
    config = _load_prompt_config(prompt_type, prompt_id)

    # For dialogue, also get step-2 and step-3 content
    step2_content = None
    step3_content = None
    if prompt_type == "dialogue":
        step2_key = _get_step2_key(prompt_id)
        if storage.exists(step2_key):
            step2_content = storage.read_text(step2_key)
        step3_key = _get_step3_key(prompt_id)
        if storage.exists(step3_key):
            step3_content = storage.read_text(step3_key)

    return PromptContent(
        id=prompt_id,
        name=_format_prompt_name(prompt_id),
        prompt_type=prompt_type,
        content=content,
        temperature=config.get("temperature", 0.7),
        step2_content=step2_content,
        step2_temperature=config.get("step2_temperature", 0.5),
        step3_content=step3_content,
        step3_temperature=config.get("step3_temperature", 0.6),
        is_active=(prompt_id == active_id)
    )


def create_prompt(
    prompt_type: PromptType,
    prompt_id: str,
    content: str,
    temperature: float | None = None,
    step2_content: str | None = None,
    step2_temperature: float | None = None,
    step3_content: str | None = None,
    step3_temperature: float | None = None,
    set_active: bool = False
) -> PromptContent:
    """Create a new prompt."""
    storage = get_data_storage()
    prompt_key = _get_prompt_key(prompt_type, prompt_id)

    # Check if already exists
    if storage.exists(prompt_key):
        raise ValueError(f"Prompt {prompt_id} already exists for type {prompt_type}")

    # Validate prompt_id
    if not prompt_id or "/" in prompt_id or "\\" in prompt_id:
        raise ValueError("Invalid prompt ID")

    # Write main prompt
    storage.write_text(prompt_key, content)

    # Save temperature config
    _save_prompt_config(
        prompt_type, prompt_id,
        temperature=temperature,
        step2_temperature=step2_temperature,
        step3_temperature=step3_temperature
    )

    # Write step-2 and step-3 for dialogue
    if prompt_type == "dialogue":
        if step2_content:
            step2_key = _get_step2_key(prompt_id)
            storage.write_text(step2_key, step2_content)
        if step3_content:
            step3_key = _get_step3_key(prompt_id)
            storage.write_text(step3_key, step3_content)

    # Set as active if requested
    if set_active:
        set_active_prompt(prompt_type, prompt_id)

    return get_prompt(prompt_type, prompt_id)  # type: ignore


def update_prompt(
    prompt_type: PromptType,
    prompt_id: str,
    content: str,
    temperature: float | None = None,
    step2_content: str | None = None,
    step2_temperature: float | None = None,
    step3_content: str | None = None,
    step3_temperature: float | None = None
) -> PromptContent:
    """Update an existing prompt."""
    storage = get_data_storage()
    prompt_key = _get_prompt_key(prompt_type, prompt_id)

    # Check if exists
    if not storage.exists(prompt_key):
        raise ValueError(f"Prompt {prompt_id} does not exist for type {prompt_type}")

    # Write main prompt
    storage.write_text(prompt_key, content)

    # Save temperature config
    _save_prompt_config(
        prompt_type, prompt_id,
        temperature=temperature,
        step2_temperature=step2_temperature,
        step3_temperature=step3_temperature
    )

    # Write step-2 and step-3 for dialogue
    if prompt_type == "dialogue":
        step2_key = _get_step2_key(prompt_id)
        if step2_content:
            storage.write_text(step2_key, step2_content)
        elif storage.exists(step2_key):
            # Remove step-2 if not provided but exists
            storage.delete(step2_key)

        step3_key = _get_step3_key(prompt_id)
        if step3_content:
            storage.write_text(step3_key, step3_content)
        elif storage.exists(step3_key):
            # Remove step-3 if not provided but exists
            storage.delete(step3_key)

    return get_prompt(prompt_type, prompt_id)  # type: ignore


def delete_prompt(prompt_type: PromptType, prompt_id: str) -> bool:
    """Delete a prompt. Cannot delete active prompt."""
    storage = get_data_storage()
    prompt_key = _get_prompt_key(prompt_type, prompt_id)

    # Check if exists
    if not storage.exists(prompt_key):
        return False

    # Cannot delete active prompt
    active_id = get_active_prompt_id(prompt_type)
    if prompt_id == active_id:
        raise ValueError("Cannot delete the active prompt. Set another prompt as active first.")

    # Delete main prompt
    storage.delete(prompt_key)

    # Delete step-2 and step-3 for dialogue
    if prompt_type == "dialogue":
        step2_key = _get_step2_key(prompt_id)
        if storage.exists(step2_key):
            storage.delete(step2_key)
        step3_key = _get_step3_key(prompt_id)
        if storage.exists(step3_key):
            storage.delete(step3_key)

    return True


def get_active_prompt_content(prompt_type: PromptType) -> str | None:
    """Get the content of the active prompt for a type."""
    active_id = get_active_prompt_id(prompt_type)
    if not active_id:
        return None

    prompt = get_prompt(prompt_type, active_id)
    if prompt:
        return prompt.content
    return None


def get_active_dialogue_prompts() -> tuple[str | None, str | None, str | None]:
    """
    Get the active dialogue prompts (main, step-2, step-3).
    Returns (main_content, step2_content, step3_content).
    """
    active_id = get_active_prompt_id("dialogue")
    if not active_id:
        return None, None, None

    prompt = get_prompt("dialogue", active_id)
    if prompt:
        return prompt.content, prompt.step2_content, prompt.step3_content
    return None, None, None


def get_active_dialogue_temperatures() -> tuple[float, float, float]:
    """
    Get the temperature settings for active dialogue prompts.
    Returns (main_temp, step2_temp, step3_temp).
    """
    active_id = get_active_prompt_id("dialogue")
    if not active_id:
        return 0.7, 0.5, 0.6  # Defaults

    prompt = get_prompt("dialogue", active_id)
    if prompt:
        return prompt.temperature, prompt.step2_temperature, prompt.step3_temperature
    return 0.7, 0.5, 0.6  # Defaults


# Migration helper: migrate old prompts to new structure
def migrate_old_prompts() -> dict[str, list[str]]:
    """
    Migrate prompts from old locations to new structure.
    Returns dict of migrated prompts by type.
    """
    storage = get_data_storage()
    migrated: dict[str, list[str]] = {t: [] for t in PROMPT_TYPES}

    # Migrate dialogue prompts from dialogue-prompt/
    old_dialogue_keys = storage.list_keys("dialogue-prompt")
    for key in old_dialogue_keys:
        if not key.endswith(".md"):
            continue
        filename = key.split("/")[-1]
        prompt_id = filename[:-3]  # Remove .md

        # Read old content
        content = storage.read_text(key)

        # Write to new location
        new_key = f"prompts/dialogue/{filename}"
        if not storage.exists(new_key):
            storage.write_text(new_key, content)
            migrated["dialogue"].append(prompt_id)

    # Set default active for dialogue if not set
    if not get_active_prompt_id("dialogue"):
        prompts = list_prompts("dialogue")
        if prompts:
            # Pick highest version
            set_active_prompt("dialogue", prompts[-1].id)

    # Migrate image_prompt.md
    if storage.exists("image_prompt.md"):
        content = storage.read_text("image_prompt.md")
        new_key = "prompts/image/default.md"
        if not storage.exists(new_key):
            storage.write_text(new_key, content)
            migrated["image"].append("default")
        if not get_active_prompt_id("image"):
            set_active_prompt("image", "default")

    # Migrate fetch_sources_summariser_prompt.md (research)
    for old_name in ["fetch_sources_summariser_prompt.md", "perplexity_reaserch_prompt.md"]:
        if storage.exists(old_name):
            content = storage.read_text(old_name)
            new_key = "prompts/research/default.md"
            if not storage.exists(new_key):
                storage.write_text(new_key, content)
                migrated["research"].append("default")
            break
    if not get_active_prompt_id("research"):
        if list_prompts("research"):
            set_active_prompt("research", "default")

    # Migrate yt_metadata_prompt.md
    if storage.exists("yt_metadata_prompt.md"):
        content = storage.read_text("yt_metadata_prompt.md")
        new_key = "prompts/yt-metadata/default.md"
        if not storage.exists(new_key):
            storage.write_text(new_key, content)
            migrated["yt-metadata"].append("default")
        if not get_active_prompt_id("yt-metadata"):
            set_active_prompt("yt-metadata", "default")

    return migrated
