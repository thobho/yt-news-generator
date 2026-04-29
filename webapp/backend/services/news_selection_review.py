"""
News Selection Prompt Review service.

Collects recent runs with YouTube stats and topic/category data,
ranks them by a composite performance score, and uses an LLM
to generate actionable improvement suggestions for the news-selection prompt.
"""

import json
from collections import defaultdict

from ..core.logging_config import get_logger
from ..core.storage_config import get_run_storage
from ..services import pipeline

logger = get_logger(__name__)


def _get_recent_runs_with_topic_data(limit: int = 60) -> list[dict]:
    """Get recent runs that have yt_stats.json and seed.json with topic data."""
    runs = pipeline.list_runs()
    keys = pipeline.get_run_keys()

    results = []
    for run_info in runs:
        run_id = run_info["run_id"]
        run_storage = get_run_storage(run_id)

        if not run_storage.exists("yt_stats.json"):
            continue
        if not run_storage.exists(keys["seed"]):
            continue

        try:
            stats_data = json.loads(run_storage.read_text("yt_stats.json"))
            seed_data = json.loads(run_storage.read_text(keys["seed"]))

            source_info = seed_data.get("source_info", {})
            news_seed = seed_data.get("news_seed", "")
            category = source_info.get("category", "Unknown")
            title = source_info.get("title", "")

            # Also try to get title from yt_metadata
            if not title and run_storage.exists(keys["yt_metadata"]):
                md = run_storage.read_text(keys["yt_metadata"])
                for i, line in enumerate(md.split("\n")):
                    if line.startswith("## Tytu"):
                        md_lines = md.split("\n")
                        if i + 1 < len(md_lines):
                            title = md_lines[i + 1].strip()
                        break

            results.append({
                "run_id": run_id,
                "created_at": run_info.get("created_at"),
                "yt_stats": stats_data.get("stats", {}),
                "source_info": source_info,
                "news_seed": news_seed,
                "category": category,
                "title": title,
            })

            if len(results) >= limit:
                break
        except Exception as e:
            logger.debug("Error reading run %s: %s", run_id, e)
            continue

    return results


def _score_run(stats: dict) -> float:
    """Composite performance score for a run."""
    return (
        stats.get("views", 0)
        + stats.get("averageViewPercentage", 0) * 20
        + stats.get("likes", 0) * 5
        + stats.get("comments", 0) * 10
        + stats.get("subscribersGained", 0) * 50
    )


def _get_current_news_selection_prompt() -> tuple[str, str | None]:
    """Return (content, active_id) for the current news-selection prompt.

    Falls back to the hardcoded default from scheduler if no versioned prompt exists.
    """
    from ..services import prompts as prompts_service

    active_id = prompts_service.get_active_prompt_id("news-selection")
    if active_id:
        prompt = prompts_service.get_prompt("news-selection", active_id)
        if prompt:
            return prompt.content, active_id

    # Fall back to scheduler default
    from ..services.scheduler import _get_news_selection_prompt
    content, _ = _get_news_selection_prompt()
    return content, None


def _format_category_breakdown(scored_runs: list[tuple[dict, float]]) -> str:
    """Aggregate stats per category: count, avg score, avg views, avg retention."""
    categories: dict[str, list[tuple[dict, float]]] = defaultdict(list)
    for run, score in scored_runs:
        categories[run["category"]].append((run, score))

    lines = []
    for cat, items in sorted(categories.items(), key=lambda x: -len(x[1])):
        count = len(items)
        avg_score = sum(s for _, s in items) / count
        avg_views = sum(r["yt_stats"].get("views", 0) for r, _ in items) / count
        avg_retention = sum(
            r["yt_stats"].get("averageViewPercentage", 0) for r, _ in items
        ) / count
        lines.append(
            f"- {cat}: {count} runs, avg score={avg_score:.0f}, "
            f"avg views={avg_views:.0f}, avg retention={avg_retention:.1f}%"
        )
    return "\n".join(lines)


def _format_run_for_topic_analysis(run: dict, score: float) -> str:
    """Format a single run emphasizing topic/category/news_seed."""
    stats = run["yt_stats"]
    return (
        f"Run: {run['run_id']}\n"
        f"Score: {score:.0f}\n"
        f"Title: {run['title']}\n"
        f"Category: {run['category']}\n"
        f"Stats: views={stats.get('views', 0)}, "
        f"avgViewPct={stats.get('averageViewPercentage', 0):.1f}%, "
        f"likes={stats.get('likes', 0)}, "
        f"comments={stats.get('comments', 0)}, "
        f"subscribersGained={stats.get('subscribersGained', 0)}\n"
        f"News seed: {run['news_seed'][:500]}"
    )


def generate_news_selection_review(limit: int = 60) -> dict:
    """Generate a news selection prompt review report via LLM analysis."""
    runs = _get_recent_runs_with_topic_data(limit)
    logger.info("Collected %d runs with topic data for news selection review", len(runs))

    if len(runs) < 5:
        return {
            "summary": "Not enough data — need at least 5 runs with YouTube stats and seed data.",
            "topic_performance": [],
            "current_prompt_assessment": "",
            "suggested_changes": [],
            "suggested_prompt": "",
            "experiment_ideas": [],
        }

    # Score and sort
    scored = [(run, _score_run(run["yt_stats"])) for run in runs]
    scored.sort(key=lambda x: x[1], reverse=True)

    top_n = min(10, len(scored))
    bottom_n = min(10, len(scored))
    top_runs = scored[:top_n]
    bottom_runs = scored[-bottom_n:]

    # Category breakdown
    category_breakdown = _format_category_breakdown(scored)

    # Current prompt
    current_prompt, active_id = _get_current_news_selection_prompt()
    prompt_id_label = active_id or "(hardcoded default)"

    # Build the meta-prompt
    top_section = "\n\n---\n\n".join(
        _format_run_for_topic_analysis(r, s) for r, s in top_runs
    )
    bottom_section = "\n\n---\n\n".join(
        _format_run_for_topic_analysis(r, s) for r, s in bottom_runs
    )

    meta_prompt = f"""You are an expert YouTube growth strategist analyzing a news-selection prompt for a YouTube Shorts video generation pipeline.

The pipeline selects news topics each day using an LLM prompt. The prompt receives historical performance data, available news items, and a count — then selects the best-performing topics.

## CURRENT NEWS-SELECTION PROMPT (ID: {prompt_id_label})

{current_prompt}

## CATEGORY BREAKDOWN (all {len(scored)} scored runs)

{category_breakdown}

## TOP {top_n} PERFORMING RUNS (highest composite score)

{top_section}

## BOTTOM {bottom_n} PERFORMING RUNS (lowest composite score)

{bottom_section}

## SCORING FORMULA
views + (averageViewPercentage * 20) + (likes * 5) + (comments * 10) + (subscribersGained * 50)

## YOUR TASK

Analyze the patterns in topic/category performance and the current news-selection prompt. Provide:

1. **Topic performance insights** — which categories/types of topics perform best and worst
2. **Assessment of the current prompt** — what it does well and what it misses
3. **Concrete suggested changes** — specific improvements
4. **A full revised prompt** — incorporating your suggestions. CRITICAL: The revised prompt MUST preserve the template placeholders {{historical_data}}, {{available_news}}, and {{count}} exactly as-is (with single curly braces).
5. **Experiment ideas** — ways to test different topic selection strategies

Focus on actionable improvements based on the actual data, not generic advice."""

    # Call LLM
    from .openrouter import PROMPT_REVIEW, get_chat_client

    logger.info("Calling LLM for news selection review (model=%s)...", PROMPT_REVIEW)
    client = get_chat_client()

    response = client.chat.completions.create(
        model=PROMPT_REVIEW,
        messages=[{"role": "user", "content": meta_prompt}],
        temperature=0.7,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "news_selection_review_report",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Overall patterns and key findings about topic selection performance",
                        },
                        "topic_performance": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "category": {"type": "string"},
                                    "run_count": {"type": "integer"},
                                    "avg_score": {"type": "number"},
                                    "avg_views": {"type": "number"},
                                    "avg_retention": {"type": "number"},
                                    "insight": {"type": "string"},
                                },
                                "required": [
                                    "category",
                                    "run_count",
                                    "avg_score",
                                    "avg_views",
                                    "avg_retention",
                                    "insight",
                                ],
                                "additionalProperties": False,
                            },
                            "description": "Per-category performance analysis",
                        },
                        "current_prompt_assessment": {
                            "type": "string",
                            "description": "Assessment of what the current prompt does well and what it misses",
                        },
                        "suggested_changes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific changes to make to the news-selection prompt",
                        },
                        "suggested_prompt": {
                            "type": "string",
                            "description": "Full revised news-selection prompt text preserving {historical_data}, {available_news}, {count} placeholders",
                        },
                        "experiment_ideas": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Ideas for testing different topic selection strategies",
                        },
                    },
                    "required": [
                        "summary",
                        "topic_performance",
                        "current_prompt_assessment",
                        "suggested_changes",
                        "suggested_prompt",
                        "experiment_ideas",
                    ],
                    "additionalProperties": False,
                },
            },
        },
    )

    result_text = response.choices[0].message.content.strip()
    logger.info("LLM news selection review response received")
    logger.debug("Raw response: %s", result_text[:500])

    return json.loads(result_text)
