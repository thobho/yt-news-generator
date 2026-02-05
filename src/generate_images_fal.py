"""
Generate images using fal.ai FLUX 2 Pro model.

Uses the same prompt generation as DALL-E (from generate_images.py),
but calls the fal.ai API for image creation.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Union

import requests

from logging_config import get_logger
from storage import StorageBackend

logger = get_logger(__name__)

DEFAULT_FAL_MODEL = "fal-ai/flux-2-pro"


def generate_image(
    prompt: str,
    output_path: Union[Path, str],
    storage: StorageBackend = None,
    model: str = DEFAULT_FAL_MODEL,
) -> None:
    """Generate a single image using fal.ai FLUX and save it.

    Args:
        prompt: Image generation prompt
        output_path: Path to save the image
        storage: Optional storage backend. If None, saves to local filesystem.
        model: fal.ai model identifier (e.g. "fal-ai/flux-2-pro")
    """
    token = os.environ.get("FAL_TOKEN")
    if not token:
        raise ValueError("FAL_TOKEN environment variable is not set")

    api_url = f"https://fal.run/{model}"

    response = requests.post(
        api_url,
        headers={
            "Authorization": f"Key {token}",
            "Content-Type": "application/json",
        },
        json={
            "prompt": prompt,
            "image_size": {"width": 1024, "height": 1792},
            "num_images": 1,
            "output_format": "png",
        },
    )
    response.raise_for_status()

    data = response.json()
    image_url = data["images"][0]["url"]

    # Download the image
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
    storage: StorageBackend = None,
    model: str = DEFAULT_FAL_MODEL,
) -> dict:
    """Generate all images from prompts using fal.ai FLUX (parallel).

    Args:
        prompts_data: Dict containing image prompts
        output_dir: Directory to save images (or key prefix for S3)
        storage: Optional storage backend. If None, uses local filesystem.
        model: fal.ai model identifier (e.g. "fal-ai/flux-2-pro")
    """
    if storage is not None:
        storage.makedirs(str(output_dir))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    images = prompts_data.get("images", [])
    n_images = len(images)

    logger.info("Generating %d images in parallel with fal.ai FLUX (%s)...", n_images, model)

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
            generate_image(prompt, output_path, storage, model=model)
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
