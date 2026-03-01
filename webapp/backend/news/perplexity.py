#!/usr/bin/env python3
"""
Perplexity (via OpenRouter) → normalized Polish news enrichment JSON
"""

import argparse
import json
import re
import sys
import unicodedata
from hashlib import sha1
from pathlib import Path
from typing import Optional, Union

from ..core.logging_config import get_logger
from ..core.storage import StorageBackend
from ..services.openrouter import get_chat_client, PERPLEXITY_SEARCH

logger = get_logger(__name__)


# =========================
# CONSTANTS
# =========================

LANGUAGE = "pl"


# =========================
# CORE LOGIC
# =========================

def load_news_seed(path: Union[Path, str], storage: StorageBackend = None) -> str:
    """Load news seed from file.

    Args:
        path: Path to seed file
        storage: Optional storage backend. If None, reads from local filesystem.
    """
    if storage is not None:
        content = storage.read_text(str(path))
        data = json.loads(content)
    else:
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


def search_news(news_text: str, client=None):
    if client is None:
        client = get_chat_client()

    query = build_polish_query(news_text)

    response = client.chat.completions.create(
        model=PERPLEXITY_SEARCH,
        messages=[{"role": "user", "content": query}],
    )

    return response


def _domain_from_url(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")


def build_enriched_news_json(
    *,
    news_text: str,
    search_result,
) -> dict:
    sources = []
    model_extra = search_result.model_extra or {}

    # Prefer search_results (per-source objects with snippets) when OpenRouter passes them through
    raw_results = model_extra.get("search_results", [])
    if raw_results:
        for r in raw_results:
            snippet = (r.get("snippet") or "").strip()
            if not snippet:
                continue
            sources.append({
                "name": _domain_from_url(r.get("url", "")),
                "url": r.get("url", ""),
                "summary": snippet,
            })

    # Fallback: use citations (flat URL list) — OpenRouter always passes these through
    if not sources:
        answer = (search_result.choices[0].message.content or "").strip()
        for url in model_extra.get("citations", []):
            sources.append({
                "name": _domain_from_url(url),
                "url": url,
                "summary": answer,
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
    input_path: Union[Path, str],
    output_path: Union[Path, str],
    client=None,
    storage: StorageBackend = None,
):
    """Run Perplexity enrichment on a news seed via OpenRouter.

    Args:
        input_path: Path to input seed file
        output_path: Path to output enriched file
        client: Optional OpenAI-compatible client (defaults to OpenRouter)
        storage: Optional storage backend. If None, uses local filesystem.
    """
    logger.info("Loading news seed from: %s", input_path)
    news_text = load_news_seed(input_path, storage)
    logger.debug("News seed: %s...", news_text[:100])

    logger.info("Searching Perplexity for news sources...")
    search = search_news(news_text, client)

    enriched = build_enriched_news_json(
        news_text=news_text,
        search_result=search,
    )

    source_count = len(enriched.get("source_summaries", []))
    logger.info("Found %d sources", source_count)

    output_json = json.dumps(enriched, ensure_ascii=False, indent=2)

    if storage is not None:
        storage.write_text(str(output_path), output_json)
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output_json)

    logger.info("Enriched news saved to: %s", output_path)
    return enriched


# =========================
# CLI (MINIMAL)
# =========================

def main():
    parser = argparse.ArgumentParser(
        description="Perplexity (via OpenRouter) → Polish news enrichment JSON"
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
