#!/usr/bin/env python3
"""
Perplexity → normalized Polish news enrichment JSON
"""

import argparse
import json
import re
import sys
import unicodedata
from hashlib import sha1
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from perplexity import Perplexity

from logging_config import get_logger

logger = get_logger(__name__)


# =========================
# CONSTANTS
# =========================

LANGUAGE = "pl"


# =========================
# CORE LOGIC
# =========================

def load_news_seed(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    news_seed = data.get("news_seed", "").strip()
    if not news_seed:
        raise ValueError("Missing or empty 'news_seed' field")

    return news_seed


def generate_topic_id(news_text: str, max_words: int = 6) -> str:
    """
    Generate stable, URL-safe topic_id from Polish text.
    """
    normalized = unicodedata.normalize("NFKD", news_text)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()

    words = re.findall(r"[a-z0-9]+", normalized)[:max_words]
    base = "_".join(words) if words else "topic"

    # hash suffix to avoid collisions
    digest = sha1(news_text.encode("utf-8")).hexdigest()[:6]

    return f"{base}_{digest}"


def build_polish_query(news_text: str) -> str:
    """
    Force Perplexity toward Polish-language, Poland-based sources.
    """
    return (
        f"{news_text}\n\n"
        "Szukaj wyłącznie w polskich źródłach prasowych. "
        "Język odpowiedzi: polski. "
        "Preferuj media ogólnopolskie."
    )


def search_news(
    news_text: str,
    client: Optional[Perplexity] = None,
):
    if client is None:
        client = Perplexity()

    query = build_polish_query(news_text)

    return client.search.create(
        query=[query]
    )


def extract_source_name(result) -> str:
    try:
        domain = urlparse(result.url).netloc
        return domain.replace("www.", "")
    except Exception:
        return result.title


def build_enriched_news_json(
    *,
    news_text: str,
    search_result,
) -> dict:
    sources = []

    for r in getattr(search_result, "results", []):
        snippet = getattr(r, "snippet", "").strip()
        if not snippet:
            continue

        sources.append({
            "name": extract_source_name(r),
            "url": r.url,
            "summary": snippet,
        })

    total = len(sources)

    return {
        "topic_id": generate_topic_id(news_text),
        "language": LANGUAGE,
        "news_text": news_text,
        "source_summaries": sources,
        "fetch_stats": {
            "total": total,
            "successful": total,
            "failed": 0,
        },
    }


def run_perplexity_enrichment(
    *,
    input_path: Path,
    output_path: Path,
    client: Optional[Perplexity] = None,
):
    logger.info("Loading news seed from: %s", input_path)
    news_text = load_news_seed(input_path)
    logger.debug("News seed: %s...", news_text[:100])

    logger.info("Searching Perplexity for news sources...")
    search = search_news(news_text, client)

    enriched = build_enriched_news_json(
        news_text=news_text,
        search_result=search,
    )

    source_count = len(enriched.get("source_summaries", []))
    logger.info("Found %d sources", source_count)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    logger.info("Enriched news saved to: %s", output_path)
    return enriched


# =========================
# CLI (MINIMAL)
# =========================

def main():
    parser = argparse.ArgumentParser(
        description="Perplexity → Polish news enrichment JSON"
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)

    args = parser.parse_args()

    try:
        run_perplexity_enrichment(
            input_path=args.input,
            output_path=args.output,
        )

    except Exception as e:
        logger.error("Perplexity search failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
