#!/usr/bin/env python3
"""
Generate YouTube metadata (title, description, hashtags) using ChatGPT.

Usage:
    python generate_yt_metadata.py news.json prompt.md -o yt_metadata.json
"""

import argparse
import json
import sys
from pathlib import Path

from openai import OpenAI


def load_news(news_path: Path) -> dict:
    """Load news data from JSON file."""
    with open(news_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_prompt(prompt_path: Path) -> str:
    """Load prompt template from markdown file."""
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def build_user_message(news: dict) -> str:
    """Build the user message with news context.

    Supports both formats:
    - Original: sources with name/url
    - Enriched: source_summaries with name/url/summary
    """
    # Check if this is enriched format (from fetch_sources.py)
    if "source_summaries" in news:
        summaries_text = ""
        for i, s in enumerate(news.get("source_summaries", []), 1):
            summaries_text += f"\n### Source {i}: {s['name']}\n{s['summary']}\n"

        return f"""NEWS TEXT:
{news.get("news_text", "")}

SOURCE SUMMARIES:
{summaries_text}

LANGUAGE: {news.get("language", "en")}
TOPIC ID: {news.get("topic_id", "unknown")}

TASK:
Create YouTube Shorts metadata that maximizes CTR and watch time.
"""
    else:
        # Original format - just URLs
        sources_text = "\n".join(
            f"- {s['name']}: {s['url']}" for s in news.get("sources", [])
        )

        return f"""NEWS TEXT:
{news.get("news_text", "")}

SOURCES:
{sources_text}

LANGUAGE: {news.get("language", "en")}
TOPIC ID: {news.get("topic_id", "unknown")}

TASK:
Create YouTube Shorts metadata that maximizes CTR and watch time.
"""


def generate_yt_metadata(
    news_path: Path,
    prompt_path: Path,
    model: str = "gpt-4o",
) -> dict:
    """Generate YouTube metadata using ChatGPT."""
    news = load_news(news_path)
    system_prompt = load_prompt(prompt_path)
    user_message = build_user_message(news)

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


def main():
    parser = argparse.ArgumentParser(
        description="Generate YouTube metadata (title, description, hashtags)"
    )
    parser.add_argument("news", type=Path, help="Path to news.json file")
    parser.add_argument("prompt", type=Path, help="Path to yt_metadata_prompt.md")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output JSON file (default: stdout)"
    )
    parser.add_argument(
        "-m", "--model", default="gpt-4o", help="OpenAI model to use (default: gpt-4o)"
    )

    args = parser.parse_args()

    if not args.news.exists():
        print(f"Error: News file not found: {args.news}", file=sys.stderr)
        sys.exit(1)

    if not args.prompt.exists():
        print(f"Error: Prompt file not found: {args.prompt}", file=sys.stderr)
        sys.exit(1)

    result = generate_yt_metadata(args.news, args.prompt, args.model)

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"Output written to: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
