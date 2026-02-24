#!/usr/bin/env python3
"""
Generate image prompts from dialogue JSON and create images using DALL-E.

Usage:
    python generate_images.py output.json data/image_prompt.md -o output/images
    python generate_images.py output.json data/image_prompt.md -o output/images --prompts-only
"""

import argparse
import base64
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Union

import requests
from openai import OpenAI

from ..core.logging_config import get_logger
from ..core.storage import StorageBackend

logger = get_logger(__name__)


def load_json(path: Union[Path, str], storage: StorageBackend = None) -> dict:
    """Load JSON file.

    Args:
        path: Path to JSON file
        storage: Optional storage backend. If None, reads from local filesystem.
    """
    if storage is not None:
        content = storage.read_text(str(path))
        return json.loads(content)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt(prompt_path: Union[Path, str], storage: StorageBackend = None) -> str:
    """Load prompt template from markdown file.

    Args:
        prompt_path: Path to prompt file
        storage: Optional storage backend. If None, reads from local filesystem.
    """
    if storage is not None:
        return storage.read_text(str(prompt_path))
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def build_user_message(dialogue_data: dict) -> str:
    """Build the user message with dialogue data."""
    all_text = []

    script = dialogue_data.get("script", [])
    all_text.append("DIALOGUE:")
    for i, entry in enumerate(script):
        all_text.append(f"  [{i}] Speaker {entry['speaker']}: {entry['text']}")

        # Add emphasis if present
        if emphasis := entry.get("emphasis"):
            all_text.append(f"      EMPHASIS: {', '.join(emphasis)}")

        # Add sources if present
        if sources := entry.get("sources"):
            source_strs = [f"{s['name']}: {s['text']}" for s in sources]
            all_text.append(f"      SOURCES: {'; '.join(source_strs)}")

    return f"""TOPIC ID: {dialogue_data.get('topic_id', 'unknown')}

{chr(10).join(all_text)}
"""


def generate_image_prompts(
    dialogue_path: Union[Path, str],
    prompt_path: Union[Path, str],
    model: str = "gpt-4o",
    dialogue_storage: StorageBackend = None,
    prompt_storage: StorageBackend = None
) -> dict:
    """Generate image prompts using ChatGPT.

    Args:
        dialogue_path: Path to dialogue JSON file
        prompt_path: Path to image prompt file
        model: OpenAI model to use
        dialogue_storage: Optional storage backend for dialogue file
        prompt_storage: Optional storage backend for prompt file
    """
    dialogue_data = load_json(dialogue_path, dialogue_storage)
    system_prompt = load_prompt(prompt_path, prompt_storage)
    user_message = build_user_message(dialogue_data)

    client = OpenAI()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
    )

    content = response.choices[0].message.content
    return json.loads(content)


def generate_image(
    client: OpenAI,
    prompt: str,
    output_path: Union[Path, str],
    storage: StorageBackend = None
) -> None:
    """Generate a single image using DALL-E and save it.

    Args:
        client: OpenAI client
        prompt: Image generation prompt
        output_path: Path to save the image
        storage: Optional storage backend. If None, saves to local filesystem.
    """
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1792",  # Vertical format for shorts
        quality="standard",
        n=1,
        response_format="url",
    )

    # Download the image
    image_url = response.data[0].url
    image_response = requests.get(image_url)
    image_response.raise_for_status()

    if storage is not None:
        storage.write_bytes(str(output_path), image_response.content)
    else:
        with open(output_path, "wb") as f:
            f.write(image_response.content)


def generate_all_images(
    prompts_data: dict,
    output_dir: Union[Path, str],
    storage: StorageBackend = None
) -> dict:
    """Generate all images from prompts and save to output directory (parallel).

    Args:
        prompts_data: Dict containing image prompts
        output_dir: Directory to save images (or key prefix for S3)
        storage: Optional storage backend. If None, uses local filesystem.
    """
    if storage is not None:
        storage.makedirs(str(output_dir))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    client = OpenAI()
    images = prompts_data.get("images", [])
    n_images = len(images)

    logger.info("Generating %d images in parallel with DALL-E...", n_images)

    def process_image(idx_and_info):
        idx, image_info = idx_and_info
        image_id = image_info["id"]
        prompt = image_info["prompt"]

        if storage is not None:
            output_path = f"{output_dir}/{image_id}.png"
        else:
            output_path = output_dir / f"{image_id}.png"

        logger.info("[%d/%d] Generating %s...", idx + 1, n_images, image_id)

        try:
            generate_image(client, prompt, output_path, storage)
            return image_id, f"{image_id}.png", None
        except Exception as e:
            logger.error("Failed to generate %s: %s", image_id, e)
            return image_id, None, str(e)

    # Run all image generations in parallel
    with ThreadPoolExecutor(max_workers=n_images) as executor:
        futures = {executor.submit(process_image, (i, img)): img for i, img in enumerate(images)}

        for future in as_completed(futures):
            image_info = futures[future]
            image_id, file, error = future.result()
            if error:
                image_info["file"] = None
                image_info["error"] = error
            else:
                image_info["file"] = file
                logger.debug("Saved: %s", file)

    return prompts_data


def main():
    parser = argparse.ArgumentParser(
        description="Generate image prompts and images from dialogue JSON"
    )
    parser.add_argument("dialogue", type=Path, help="Path to dialogue JSON file")
    parser.add_argument("prompt", type=Path, help="Path to image_prompt.md file")
    parser.add_argument(
        "-o", "--output", type=Path, required=True,
        help="Output directory for images (images.json will also be saved here)"
    )
    parser.add_argument(
        "-m", "--model", default="gpt-4o", help="OpenAI model to use (default: gpt-4o)"
    )
    parser.add_argument(
        "--prompts-only", action="store_true",
        help="Only generate prompts, don't create images"
    )

    args = parser.parse_args()

    if not args.dialogue.exists():
        logger.error("Dialogue file not found: %s", args.dialogue)
        sys.exit(1)

    if not args.prompt.exists():
        logger.error("Prompt file not found: %s", args.prompt)
        sys.exit(1)

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    # Step 1: Generate prompts
    logger.info("Generating image prompts with model=%s", args.model)
    prompts_data = generate_image_prompts(args.dialogue, args.prompt, args.model)
    logger.info("Generated %d image prompts", len(prompts_data.get('images', [])))

    # Step 2: Generate actual images (unless --prompts-only)
    if not args.prompts_only:
        prompts_data = generate_all_images(prompts_data, args.output)

    # Save prompts/metadata JSON
    json_path = args.output / "images.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(prompts_data, f, ensure_ascii=False, indent=2)
    logger.info("Metadata saved to: %s", json_path)


if __name__ == "__main__":
    main()
