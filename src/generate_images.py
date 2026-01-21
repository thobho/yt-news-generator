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
from pathlib import Path

import requests
from openai import OpenAI


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt(prompt_path: Path) -> str:
    """Load prompt template from markdown file."""
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def build_user_message(dialogue_data: dict) -> str:
    """Build the user message with dialogue data."""
    # Extract all text for context
    all_text = []

    if hook := dialogue_data.get("hook"):
        all_text.append(f"HOOK: {hook}")

    all_text.append("\nDIALOGUE:")
    for i, entry in enumerate(dialogue_data.get("dialogue", [])):
        all_text.append(f"  [{i}] Speaker {entry['speaker']}: {entry['text']}")

    all_text.append("\nCOMMON GROUND:")
    for i, entry in enumerate(dialogue_data.get("common_ground", [])):
        idx = len(dialogue_data.get("dialogue", [])) + i
        all_text.append(f"  [{idx}] Speaker {entry['speaker']}: {entry['text']}")

    if viewer_question := dialogue_data.get("viewer_question"):
        all_text.append(f"\nVIEWER QUESTION: {viewer_question}")

    if call_to_action := dialogue_data.get("call_to_action"):
        all_text.append(f"CALL TO ACTION: {call_to_action}")

    return f"""TOPIC ID: {dialogue_data.get('topic_id', 'unknown')}
LANGUAGE: {dialogue_data.get('language', 'en')}

{chr(10).join(all_text)}

Generate image prompts for this debate video. Create 4 images total:
1. A hook image for the opening
2-3. Topic images showing different aspects of the debate
4. A discussion/engagement image for the ending
"""


def generate_image_prompts(
    dialogue_path: Path,
    prompt_path: Path,
    model: str = "gpt-4o"
) -> dict:
    """Generate image prompts using ChatGPT."""
    dialogue_data = load_json(dialogue_path)
    system_prompt = load_prompt(prompt_path)
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


def generate_image(client: OpenAI, prompt: str, output_path: Path) -> None:
    """Generate a single image using DALL-E and save it."""
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1792",  # Vertical format for shorts
        quality="standard",
        n=1,
        response_format="url",
    )

    # Download and save the image
    image_url = response.data[0].url
    image_response = requests.get(image_url)
    image_response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(image_response.content)


def generate_all_images(
    prompts_data: dict,
    output_dir: Path,
) -> dict:
    """Generate all images from prompts and save to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    client = OpenAI()
    images = prompts_data.get("images", [])

    print(f"Generating {len(images)} images...", file=sys.stderr)

    for i, image_info in enumerate(images):
        image_id = image_info["id"]
        prompt = image_info["prompt"]
        output_path = output_dir / f"{image_id}.png"

        print(f"  [{i + 1}/{len(images)}] Generating {image_id}...", file=sys.stderr)

        try:
            generate_image(client, prompt, output_path)
            image_info["file"] = str(output_path.name)
            print(f"    Saved: {output_path}", file=sys.stderr)
        except Exception as e:
            print(f"    Error generating {image_id}: {e}", file=sys.stderr)
            image_info["file"] = None
            image_info["error"] = str(e)

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
        print(f"Error: Dialogue file not found: {args.dialogue}", file=sys.stderr)
        sys.exit(1)

    if not args.prompt.exists():
        print(f"Error: Prompt file not found: {args.prompt}", file=sys.stderr)
        sys.exit(1)

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    # Step 1: Generate prompts
    print("Generating image prompts...", file=sys.stderr)
    prompts_data = generate_image_prompts(args.dialogue, args.prompt, args.model)
    print(f"Generated {len(prompts_data.get('images', []))} image prompts.", file=sys.stderr)

    # Step 2: Generate actual images (unless --prompts-only)
    if not args.prompts_only:
        print("\nGenerating images with DALL-E...", file=sys.stderr)
        prompts_data = generate_all_images(prompts_data, args.output)

    # Save prompts/metadata JSON
    json_path = args.output / "images.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(prompts_data, f, ensure_ascii=False, indent=2)
    print(f"\nMetadata saved to: {json_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
