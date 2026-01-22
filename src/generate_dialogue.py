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


def generate_dialogue(news_path: Path, prompt_path: Path, model: str = "gpt-4o") -> dict:
    """Generate dialogue by sending news and prompt to ChatGPT."""
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
        temperature=0.7,
    )

    content = response.choices[0].message.content
    return json.loads(content)


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
        print(f"Error: News file not found: {args.news}", file=sys.stderr)
        sys.exit(1)

    if not args.prompt.exists():
        print(f"Error: Prompt file not found: {args.prompt}", file=sys.stderr)
        sys.exit(1)

    result = generate_dialogue(args.news, args.prompt, args.model)

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"Output written to: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
