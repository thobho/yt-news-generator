#!/usr/bin/env python3
"""
Generate YouTube metadata (title, description, hashtags) using ChatGPT.

Usage:
    python generate_yt_metadata.py enriched_news.json -o yt_metadata.json
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Union

from ..core.logging_config import get_logger
from ..services.openrouter import YT_METADATA, get_chat_client
from ..core.storage import StorageBackend
from ..core.storage_config import get_data_storage, get_project_root

logger = get_logger(__name__)

PROJECT_ROOT = get_project_root()
YT_METADATA_PROMPT_KEY = "yt_metadata_prompt.md"


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


def load_prompt(path: Union[Path, str], storage: StorageBackend = None) -> str:
    """Load prompt from file.

    Args:
        path: Path to prompt file
        storage: Optional storage backend. If None, reads from local filesystem.
    """
    if storage is not None:
        return storage.read_text(str(path))
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_user_message(news: dict) -> str:
    """Build user message from enriched news data."""
    summaries_text = ""
    for i, s in enumerate(news.get("source_summaries", []), 1):
        summaries_text += f"\n### Source {i}: {s['name']}\n{s.get('summary', '')}\n"

    sources_text = ""
    for s in news.get("sources", []):
        sources_text += f"- {s['name']}: {s.get('url', '')}\n"

    return f"""NEWS TEXT:
{news.get("news_text", "")}

{f"SOURCE SUMMARIES:{summaries_text}" if summaries_text else f"SOURCES:{sources_text}"}

LANGUAGE: {news.get("language", "pl")}
TOPIC ID: {news.get("topic_id", "unknown")}
"""


def extract_source_links(news: dict) -> list[dict]:
    """Extract source name/url pairs from enriched news."""
    links = []
    for s in news.get("source_summaries", news.get("sources", [])):
        name = s.get("name", "")
        url = s.get("url", "")
        if name and url:
            links.append({"name": name, "url": url})
    return links


def assemble_description(summary: str, hashtags: list[str], source_links: list[dict]) -> str:
    """Assemble the full YT description from parts."""
    parts = []

    # 1. Call to action
    parts.append("🔔 Subskrybuj i włącz dzwonek, żeby nie przegapić kolejnych debat!")

    # 2. Summary
    parts.append("")
    parts.append(f"💬 {summary}")

    # 3. Source links
    if source_links:
        parts.append("")
        parts.append("📰 Źródła:")
        for link in source_links:
            parts.append(f"▸ {link['name']}:")
            parts.append(link['url'])

    # 4. Hashtags
    parts.append("")
    parts.append(" ".join(hashtags))

    # 5. AI disclosure
    parts.append("")
    parts.append("🤖 Cała treść tego filmu (dialog, obrazy, audio) została wygenerowana przez AI w ramach projektu badającego, jak sztuczna inteligencja może wspierać rzeczowy dialog społeczny.")

    return "\n".join(parts)


def format_as_markdown(title: str, description: str) -> str:
    """Format metadata as a markdown file ready to copy-paste."""
    return f"""# 🎬 YouTube Metadata

## Tytuł
{title}

## Opis
{description}
"""


def generate_yt_metadata(
    enriched_news_path: Union[Path, str],
    model: str = YT_METADATA,
    storage: StorageBackend = None,
    prompt_key: str = None
) -> str:
    """Generate YouTube metadata using enriched news data.

    Args:
        enriched_news_path: Path to enriched news JSON
        model: OpenAI model to use
        storage: Optional storage backend for reading news file
        prompt_key: Custom prompt key (default: YT_METADATA_PROMPT_KEY)
    """
    logger.info("Generating YouTube metadata from: %s", enriched_news_path)
    news = load_json(enriched_news_path, storage)

    # Load prompt from data storage
    data_storage = get_data_storage()
    system_prompt = load_prompt(prompt_key or YT_METADATA_PROMPT_KEY, data_storage)
    user_message = build_user_message(news)

    client = get_chat_client()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    content = response.choices[0].message.content
    try:
        llm_result = json.loads(content)
    except json.JSONDecodeError:
        # LLMs sometimes emit invalid JSON escape sequences (e.g. \s, \p, \A).
        # Process \X pairs: keep valid escapes, double the backslash for invalid ones.
        def _fix_escape(m):
            c = m.group(1)
            return m.group(0) if c in '"\\/bfnrtu' else '\\\\' + c
        fixed = re.sub(r'\\(.)', _fix_escape, content)
        llm_result = json.loads(fixed)

    # Extract parts from LLM response
    title = llm_result.get("title", "")
    summary = llm_result.get("summary", "")
    hashtags = llm_result.get("hashtags", [])

    # Get source links from enriched news
    source_links = extract_source_links(news)

    # Assemble full description
    description = assemble_description(summary, hashtags, source_links)

    return format_as_markdown(title, description)


def main():
    parser = argparse.ArgumentParser(
        description="Generate YouTube metadata (title, description)"
    )
    parser.add_argument("news", type=Path, help="Path to enriched_news.json")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output JSON file (default: stdout)"
    )
    parser.add_argument(
        "-m", "--model", default=YT_METADATA, help=f"Model to use via OpenRouter (default: {YT_METADATA})"
    )

    args = parser.parse_args()

    if not args.news.exists():
        logger.error("File not found: %s", args.news)
        sys.exit(1)

    result = generate_yt_metadata(args.news, args.model)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        logger.info("YouTube metadata written to: %s", args.output)
    else:
        print(result)


if __name__ == "__main__":
    main()
