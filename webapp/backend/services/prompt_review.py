"""
Prompt Performance Review service.

Collects recent runs with YouTube stats and prompt snapshots,
ranks them by a composite performance score, and uses an LLM
to generate actionable improvement suggestions for each prompt type.
"""

import json
from collections import Counter

from ..core.logging_config import get_logger
from ..core.storage_config import get_run_storage
from ..services import pipeline

logger = get_logger(__name__)


def _get_recent_runs_with_full_data(limit: int = 60) -> list[dict]:
    """Get recent runs that have both yt_stats.json and prompts_snapshot/config.json."""
    runs = pipeline.list_runs()
    keys = pipeline.get_run_keys()

    results = []
    for run_info in runs:
        run_id = run_info["run_id"]
        run_storage = get_run_storage(run_id)

        if not run_storage.exists("yt_stats.json"):
            continue
        if not run_storage.exists("prompts_snapshot/config.json"):
            continue

        try:
            stats_data = json.loads(run_storage.read_text("yt_stats.json"))
            seed_data = json.loads(run_storage.read_text(keys["seed"]))
            snapshot_config = json.loads(
                run_storage.read_text("prompts_snapshot/config.json")
            )

            # Script excerpt: first 2 + last 2 lines
            dialogue_excerpt = ""
            if run_storage.exists(keys["dialogue"]):
                dialogue = json.loads(run_storage.read_text(keys["dialogue"]))
                lines = dialogue.get("lines", [])
                if len(lines) > 4:
                    excerpt_lines = lines[:2] + lines[-2:]
                else:
                    excerpt_lines = lines
                dialogue_excerpt = json.dumps(excerpt_lines, ensure_ascii=False)

            # Title from yt_metadata.md
            title = ""
            if run_storage.exists(keys["yt_metadata"]):
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
                "source_info": seed_data.get("source_info", {}),
                "news_seed": seed_data.get("news_seed", ""),
                "prompt_config": snapshot_config.get("prompts", {}),
                "dialogue_excerpt": dialogue_excerpt,
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


def _read_prompt_file(run_storage, filename: str) -> str:
    """Read a prompt .md file from prompts_snapshot/."""
    key = f"prompts_snapshot/{filename}"
    if run_storage.exists(key):
        return run_storage.read_text(key)
    return ""


def _format_run_for_prompt(run: dict, score: float) -> str:
    """Format a single run's data for the LLM prompt."""
    stats = run["yt_stats"]
    source = run["source_info"]
    prompts = run["prompt_config"]

    prompt_ids = {}
    for ptype, pdata in prompts.items():
        prompt_ids[ptype] = pdata.get("id", "unknown")

    return (
        f"Run: {run['run_id']}\n"
        f"Score: {score:.0f}\n"
        f"Title: {run['title']}\n"
        f"Category: {source.get('category', 'N/A')}\n"
        f"Stats: views={stats.get('views', 0)}, "
        f"avgViewPct={stats.get('averageViewPercentage', 0):.1f}%, "
        f"likes={stats.get('likes', 0)}, "
        f"comments={stats.get('comments', 0)}, "
        f"subscribersGained={stats.get('subscribersGained', 0)}\n"
        f"Prompt IDs: {json.dumps(prompt_ids)}\n"
        f"Script excerpt: {run['dialogue_excerpt'][:600]}"
    )


def generate_prompt_review(limit: int = 60) -> dict:
    """Generate a prompt performance review report via LLM analysis."""
    runs = _get_recent_runs_with_full_data(limit)
    logger.info("Collected %d runs with full data for prompt review", len(runs))

    if len(runs) < 5:
        return {
            "summary": "Not enough data — need at least 5 runs with YouTube stats and prompt snapshots.",
            "prompt_analyses": [],
            "topic_insights": "",
            "experiment_ideas": [],
        }

    # Score and sort
    scored = [(run, _score_run(run["yt_stats"])) for run in runs]
    scored.sort(key=lambda x: x[1], reverse=True)

    top_n = min(5, len(scored))
    bottom_n = min(5, len(scored))
    top_runs = scored[:top_n]
    bottom_runs = scored[-bottom_n:]

    # Find most-used prompt ID per type (the "current" prompt)
    prompt_type_ids: dict[str, list[str]] = {}
    for run, _ in scored:
        for ptype, pdata in run["prompt_config"].items():
            prompt_type_ids.setdefault(ptype, []).append(pdata.get("id", ""))

    current_prompts: dict[str, str] = {}
    for ptype, ids in prompt_type_ids.items():
        counter = Counter(ids)
        current_prompts[ptype] = counter.most_common(1)[0][0]

    # Read full prompt content from the top-scoring run's snapshot
    best_run_id = top_runs[0][0]["run_id"]
    best_storage = get_run_storage(best_run_id)

    prompt_files = {
        "dialogue": ("dialogue_step1.md", "dialogue_step2.md", "dialogue_step3.md"),
        "image": ("image.md",),
        "yt-metadata": ("yt_metadata.md",),
    }

    current_prompt_texts: dict[str, str] = {}
    for ptype, files in prompt_files.items():
        parts = []
        for f in files:
            content = _read_prompt_file(best_storage, f)
            if content:
                parts.append(f"--- {f} ---\n{content}")
        if parts:
            current_prompt_texts[ptype] = "\n\n".join(parts)

    # Build the meta-prompt
    top_section = "\n\n---\n\n".join(
        _format_run_for_prompt(r, s) for r, s in top_runs
    )
    bottom_section = "\n\n---\n\n".join(
        _format_run_for_prompt(r, s) for r, s in bottom_runs
    )

    prompts_section = ""
    for ptype, text in current_prompt_texts.items():
        prompts_section += f"\n\n=== PROMPT TYPE: {ptype} (current ID: {current_prompts.get(ptype, '?')}) ===\n{text}"

    meta_prompt = f"""You are an expert prompt engineer analyzing a YouTube video generation pipeline.

The pipeline generates videos through these steps:
1. dialogue_step1 — creative dialogue generation (two hosts discussing news)
2. dialogue_step2 — structural refinement and fact-checking
3. dialogue_step3 — Polish language naturalness polish
4. image — generating visual prompts for video illustrations
5. yt_metadata — generating YouTube title, description, tags

Below are the CURRENT PROMPTS used in the pipeline:
{prompts_section}

Here are the TOP {top_n} PERFORMING runs (highest composite score):

{top_section}

Here are the BOTTOM {bottom_n} PERFORMING runs (lowest composite score):

{bottom_section}

Scoring formula: views + (averageViewPercentage * 20) + (likes * 5) + (comments * 10) + (subscribersGained * 50)

Analyze the patterns between high-performing and low-performing runs. For each prompt type, provide:
1. What's working well in top runs
2. What might be causing poor performance in bottom runs
3. Concrete, specific changes to improve the prompt
4. A full revised prompt text incorporating your suggestions

Focus on actionable improvements, not generic advice. Reference specific data from the runs."""

    # Call LLM
    from .openrouter import PROMPT_REVIEW, get_chat_client

    logger.info("Calling LLM for prompt review (model=%s)...", PROMPT_REVIEW)
    client = get_chat_client()

    response = client.chat.completions.create(
        model=PROMPT_REVIEW,
        messages=[{"role": "user", "content": meta_prompt}],
        temperature=0.7,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "prompt_review_report",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Overall patterns and key findings",
                        },
                        "prompt_analyses": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "prompt_type": {
                                        "type": "string",
                                        "description": "One of: dialogue_step1, dialogue_step2, dialogue_step3, image, yt_metadata",
                                    },
                                    "current_prompt_id": {
                                        "type": "string",
                                        "description": "ID of the current most-used prompt for this type",
                                    },
                                    "assessment": {
                                        "type": "string",
                                        "description": "What is working and what is not",
                                    },
                                    "suggested_changes": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Specific changes to make",
                                    },
                                    "suggested_prompt": {
                                        "type": "string",
                                        "description": "Full revised prompt text",
                                    },
                                },
                                "required": [
                                    "prompt_type",
                                    "current_prompt_id",
                                    "assessment",
                                    "suggested_changes",
                                    "suggested_prompt",
                                ],
                                "additionalProperties": False,
                            },
                            "description": "Per-prompt-type analysis",
                        },
                        "topic_insights": {
                            "type": "string",
                            "description": "Which topics and categories perform best",
                        },
                        "experiment_ideas": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Ideas for A/B testing or experiments",
                        },
                    },
                    "required": [
                        "summary",
                        "prompt_analyses",
                        "topic_insights",
                        "experiment_ideas",
                    ],
                    "additionalProperties": False,
                },
            },
        },
    )

    result_text = response.choices[0].message.content.strip()
    logger.info("LLM prompt review response received")
    logger.debug("Raw response: %s", result_text[:500])

    return json.loads(result_text)
