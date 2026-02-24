#!/usr/bin/env python3
"""
Generate dialogue from news using ChatGPT.

Usage:
    python generate_dialogue.py news.json prompt.md -o output.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Union

from openai import OpenAI

from ..core.logging_config import get_logger
from ..core.storage import StorageBackend
from ..core.storage_config import get_data_storage

logger = get_logger(__name__)

# JSON Schema for dialogue output - enforced by OpenAI Structured Outputs
DIALOGUE_SCHEMA = {
    "name": "dialogue_output",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "topic_id": {"type": "string"},
            "script": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "speaker": {"type": "string"},
                        "text": {"type": "string"},
                        "emphasis": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "text": {"type": "string"}
                                },
                                "required": ["name", "text"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["speaker", "text", "emphasis", "sources"],
                    "additionalProperties": False
                }
            }
        },
        "required": ["topic_id", "script"],
        "additionalProperties": False
    }
}

def load_prompt(prompt_path: Union[Path, str], storage: StorageBackend = None) -> str:
    """Load prompt template from markdown file.

    Args:
        prompt_path: Path to prompt file (relative to data/ for storage, or absolute Path)
        storage: Optional storage backend. If None, reads from local filesystem.
    """
    if storage is not None:
        return storage.read_text(str(prompt_path))
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def build_user_message(news: dict) -> str:
    """Build the user message with news data.

    Supports both formats:
    - Original: sources with name/url
    - Enriched: source_summaries with name/url/summary
    """
    # Check if this is enriched format (from fetch_sources.py)
    if "source_summaries" in news:
        summaries_text = ""
        for i, s in enumerate(news.get("source_summaries", []), 1):
            summaries_text += f"\n### Source {i}: {s['name']}\n{s['summary']}\n"

        failed_info = ""
        if news.get("failed_sources"):
            failed_names = [f['name'] for f in news['failed_sources']]
            failed_info = f"\n(Note: {len(failed_names)} sources could not be fetched: {', '.join(failed_names)})"

        return f"""NEWS TEXT:
{news.get('news_text', '')}

SOURCE SUMMARIES:
{summaries_text}
{failed_info}

LANGUAGE: {news.get('language', 'en')}
TOPIC ID: {news.get('topic_id', 'unknown')}
"""
    else:
        # Original format - just URLs
        sources_text = "\n".join(
            f"- {s['name']}: {s['url']}" for s in news.get("sources", [])
        )

        return f"""NEWS TEXT:
{news.get('news_text', '')}

SOURCES:
{sources_text}

LANGUAGE: {news.get('language', 'en')}
TOPIC ID: {news.get('topic_id', 'unknown')}
"""


def generate_dialogue(
    news: dict,
    prompt_path: Union[Path, str],
    model: str = "gpt-4o",
    storage: StorageBackend = None,
    temperature: float = 0.7
) -> dict:
    """Generate dialogue by sending news and prompt to ChatGPT.

    Args:
        news: News data dict
        prompt_path: Path to prompt file
        model: OpenAI model to use
        storage: Optional storage backend for reading prompt
        temperature: Model temperature (0-1)
    """
    system_prompt = load_prompt(prompt_path, storage)
    user_message = build_user_message(news)
    logger.debug("User message for dialogue generation:\n%s", user_message)
    logger.info("Generating dialogue with model=%s, temperature=%.2f", model, temperature)
    client = OpenAI()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_schema", "json_schema": DIALOGUE_SCHEMA},
        temperature=temperature,
    )

    content = response.choices[0].message.content
    return json.loads(content)


def log_corrections(original: dict, refined: dict) -> list[str]:
    """Compare original and refined dialogue, return list of changes."""
    changes = []

    if original.get("hook") != refined.get("hook"):
        changes.append(f"HOOK: '{original.get('hook')}' → '{refined.get('hook')}'")

    if original.get("climax_line") != refined.get("climax_line"):
        changes.append(f"CLIMAX: '{original.get('climax_line')}' → '{refined.get('climax_line')}'")

    if original.get("viewer_question") != refined.get("viewer_question"):
        changes.append(f"QUESTION: '{original.get('viewer_question')}' → '{refined.get('viewer_question')}'")

    orig_script = original.get("script", [])
    new_script = refined.get("script", [])

    for i, (orig, new) in enumerate(zip(orig_script, new_script)):
        if orig.get("text") != new.get("text"):
            changes.append(f"SCRIPT[{i}] ({orig.get('speaker')}): '{orig.get('text')}' → '{new.get('text')}'")
        if orig.get("emphasis") != new.get("emphasis"):
            changes.append(f"SCRIPT[{i}] emphasis: {orig.get('emphasis')} → {new.get('emphasis')}")

    return changes


def refine_dialogue(
    dialogue: dict,
    news: dict,
    prompt_path: Union[Path, str],
    model: str = "gpt-4o",
    storage: StorageBackend = None,
    temperature: float = 0.5
) -> dict:
    """Refine dialogue using a second LLM pass for logic/structure corrections.

    Args:
        dialogue: Generated dialogue dict
        news: News data dict
        prompt_path: Path to refinement prompt file
        model: OpenAI model to use
        storage: Optional storage backend for reading prompt
        temperature: Model temperature (0-1)
    """
    system_prompt = load_prompt(prompt_path, storage)

    user_message = f"""## dialogue.json
```json
{json.dumps(dialogue, ensure_ascii=False, indent=2)}
```

## data_source.json
```json
{json.dumps(news, ensure_ascii=False, indent=2)}
```
"""

    logger.info("Step 2: Refining dialogue (logic/structure) with model=%s, temperature=%.2f", model, temperature)
    client = OpenAI()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_schema", "json_schema": DIALOGUE_SCHEMA},
        temperature=temperature,
    )

    content = response.choices[0].message.content
    refined = json.loads(content)

    # Log corrections
    changes = log_corrections(dialogue, refined)
    if changes:
        logger.info("Refinement made %d correction(s):", len(changes))
        for change in changes:
            logger.info("  - %s", change)
    else:
        logger.info("Step 2: No corrections needed")

    return refined


def polish_dialogue(
    dialogue: dict,
    prompt_path: Union[Path, str],
    model: str = "gpt-4o",
    storage: StorageBackend = None,
    temperature: float = 0.6
) -> dict:
    """Polish dialogue using a third LLM pass for language and style.

    Args:
        dialogue: Refined dialogue dict
        prompt_path: Path to polish prompt file
        model: OpenAI model to use
        storage: Optional storage backend for reading prompt
        temperature: Model temperature (0-1)
    """
    system_prompt = load_prompt(prompt_path, storage)

    user_message = f"""## dialogue.json
```json
{json.dumps(dialogue, ensure_ascii=False, indent=2)}
```
"""

    logger.info("Step 3: Polishing dialogue (language/style) with model=%s, temperature=%.2f", model, temperature)
    client = OpenAI()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_schema", "json_schema": DIALOGUE_SCHEMA},
        temperature=temperature,
    )

    content = response.choices[0].message.content
    polished = json.loads(content)

    # Log changes
    changes = log_corrections(dialogue, polished)
    if changes:
        logger.info("Polish made %d change(s):", len(changes))
        for change in changes:
            logger.info("  - %s", change)
    else:
        logger.info("Step 3: No changes needed")

    return polished


def main():
    parser = argparse.ArgumentParser(
        description="Generate dialogue from news using ChatGPT"
    )
    parser.add_argument("news", type=Path, help="Path to news.json file")
    parser.add_argument("prompt", type=Path, help="Path to prompt.md file")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "-m", "--model", default="gpt-4o", help="OpenAI model to use (default: gpt-4o)"
    )

    args = parser.parse_args()

    if not args.news.exists():
        logger.error("News file not found: %s", args.news)
        sys.exit(1)

    if not args.prompt.exists():
        logger.error("Prompt file not found: %s", args.prompt)
        sys.exit(1)

    result = generate_dialogue(args.news, args.prompt, args.model)

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        logger.info("Dialogue written to: %s", args.output)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
