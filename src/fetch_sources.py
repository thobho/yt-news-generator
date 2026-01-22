#!/usr/bin/env python3
"""
Fetch and summarize news sources.

Takes a news storage JSON file, fetches content from source URLs,
uses GPT to summarize each source (~200 words), and creates an
intermediate file for generate_dialogue.py.

Usage:
    python fetch_sources.py news.json -o enriched_news.json
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from openai import OpenAI


@dataclass
class FetchResult:
    """Result of fetching a source URL."""
    url: str
    name: str
    success: bool
    content: Optional[str] = None
    summary: Optional[str] = None
    error: Optional[str] = None


def fetch_url_content(url: str, timeout: int = 15) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Fetch and extract text content from a URL.

    Returns:
        (success, content, error_message)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl,en;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Remove script, style, nav, footer elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
            element.decompose()

        # Try to find main content
        main_content = None
        for selector in ["article", "main", '[role="main"]', ".article-content", ".post-content", ".entry-content"]:
            main_content = soup.select_one(selector)
            if main_content:
                break

        if main_content:
            text = main_content.get_text(separator="\n", strip=True)
        else:
            # Fallback to body
            body = soup.find("body")
            text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)

        # Clean up text - remove excessive whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines)

        # Limit content length for API
        if len(text) > 15000:
            text = text[:15000] + "..."

        if len(text) < 100:
            return False, None, "Content too short or empty"

        return True, text, None

    except requests.exceptions.Timeout:
        return False, None, "Request timed out"
    except requests.exceptions.ConnectionError:
        return False, None, "Connection failed"
    except requests.exceptions.HTTPError as e:
        return False, None, f"HTTP error: {e.response.status_code}"
    except requests.exceptions.TooManyRedirects:
        return False, None, "Too many redirects"
    except Exception as e:
        return False, None, f"Unexpected error: {str(e)}"


def load_prompt(prompt_path: Path) -> str:
    """Load prompt template from markdown file."""
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def summarize_content(
    client: OpenAI,
    content: str,
    source_name: str,
    language: str,
    prompt_template: str,
    model: str = "gpt-4o-mini",
) -> str:
    """
    Use GPT to summarize the fetched content.

    Returns a ~200 word summary in the specified language.
    """
    # Replace placeholders in prompt template
    system_prompt = prompt_template.replace("{language}", language)

    user_message = f"""Source: {source_name}

Article content:
{content}

Provide a concise summary (~200 words) of the key information from this article."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[Summary failed: {str(e)}]"


def process_sources(
    news: dict,
    prompt_template: str,
    model: str = "gpt-4o-mini",
    delay: float = 1.0,
) -> list[FetchResult]:
    """
    Process all sources from the news data.

    Args:
        news: News data dictionary
        prompt_template: Prompt template for summarization
        model: OpenAI model for summarization
        delay: Delay between requests (seconds)

    Returns:
        List of FetchResult objects
    """
    client = OpenAI()
    sources = news.get("sources", [])
    language = news.get("language", "en")
    results = []

    total = len(sources)
    for i, source in enumerate(sources, 1):
        url = source.get("url", "")
        name = source.get("name", "Unknown")

        print(f"[{i}/{total}] Fetching: {name}", file=sys.stderr)
        print(f"         URL: {url}", file=sys.stderr)

        success, content, error = fetch_url_content(url)

        if success:
            print(f"         ✓ Fetched ({len(content)} chars), summarizing...", file=sys.stderr)
            summary = summarize_content(client, content, name, language, prompt_template, model)
            results.append(FetchResult(
                url=url,
                name=name,
                success=True,
                content=content[:500] + "..." if len(content) > 500 else content,
                summary=summary,
            ))
            print(f"         ✓ Summary complete ({len(summary)} chars)", file=sys.stderr)
        else:
            print(f"         ✗ Failed: {error}", file=sys.stderr)
            results.append(FetchResult(
                url=url,
                name=name,
                success=False,
                error=error,
            ))

        # Rate limiting
        if i < total:
            time.sleep(delay)

    return results


def build_enriched_news(news: dict, results: list[FetchResult]) -> dict:
    """
    Build the enriched news data with summaries.
    """
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    summaries = []
    for r in successful:
        summaries.append({
            "name": r.name,
            "url": r.url,
            "summary": r.summary,
        })

    failed_sources = []
    for r in failed:
        failed_sources.append({
            "name": r.name,
            "url": r.url,
            "error": r.error,
        })

    return {
        "topic_id": news.get("topic_id"),
        "language": news.get("language"),
        "news_text": news.get("news_text"),
        "source_summaries": summaries,
        "failed_sources": failed_sources,
        "fetch_stats": {
            "total": len(results),
            "successful": len(successful),
            "failed": len(failed),
        },
    }


def get_default_prompt_path() -> Path:
    """Get the default prompt path relative to this script."""
    script_dir = Path(__file__).parent
    return script_dir.parent / "data" / "fetch_sources_summariser_prompt.md"


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and summarize news sources"
    )
    parser.add_argument("news", type=Path, help="Path to news.json file")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "-p", "--prompt", type=Path, default=None,
        help="Path to summarizer prompt file (default: data/fetch_sources_summariser_prompt.md)"
    )
    parser.add_argument(
        "-m", "--model", default="gpt-4o-mini",
        help="OpenAI model for summarization (default: gpt-4o-mini)"
    )
    parser.add_argument(
        "-d", "--delay", type=float, default=1.0,
        help="Delay between requests in seconds (default: 1.0)"
    )

    args = parser.parse_args()

    if not args.news.exists():
        print(f"Error: News file not found: {args.news}", file=sys.stderr)
        sys.exit(1)

    # Load prompt
    prompt_path = args.prompt if args.prompt else get_default_prompt_path()
    if not prompt_path.exists():
        print(f"Error: Prompt file not found: {prompt_path}", file=sys.stderr)
        sys.exit(1)

    prompt_template = load_prompt(prompt_path)
    print(f"Using prompt: {prompt_path}", file=sys.stderr)

    # Load news data
    with open(args.news, "r", encoding="utf-8") as f:
        news = json.load(f)

    print(f"\nProcessing {len(news.get('sources', []))} sources...\n", file=sys.stderr)

    # Process sources
    results = process_sources(news, prompt_template, args.model, args.delay)

    # Build enriched news
    enriched = build_enriched_news(news, results)

    # Output results
    output_json = json.dumps(enriched, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"\n✓ Output written to: {args.output}", file=sys.stderr)
    else:
        print(output_json)

    # Summary
    stats = enriched["fetch_stats"]
    print(f"\nSummary: {stats['successful']}/{stats['total']} sources fetched successfully", file=sys.stderr)
    if stats['failed'] > 0:
        print(f"Failed sources:", file=sys.stderr)
        for src in enriched["failed_sources"]:
            print(f"  - {src['name']}: {src['error']}", file=sys.stderr)


if __name__ == "__main__":
    main()
