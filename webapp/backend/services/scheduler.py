"""
Scheduler service - handles automated daily video generation.
Uses APScheduler with AsyncIOScheduler for job scheduling.
"""

import asyncio
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from logging_config import get_logger
from storage_config import get_config_storage, get_data_storage

from . import infopigula
from . import pipeline
from . import prompts as prompts_service
from . import youtube_analytics

logger = get_logger(__name__)

# State file location
SCHEDULER_STATE_KEY = "scheduler_state.json"

# Selection modes
SelectionMode = Literal["random", "llm"]


class PromptSelections(BaseModel):
    """Prompt selections for runs - allows overriding the active prompt per type."""
    dialogue: Optional[str] = None
    image: Optional[str] = None
    research: Optional[str] = None
    yt_metadata: Optional[str] = None


class ScheduledRunConfig(BaseModel):
    """Configuration for a single scheduled run."""
    enabled: bool = True  # Can disable individual runs
    selection_mode: SelectionMode = "random"  # Per-run selection mode
    prompts: Optional[PromptSelections] = None  # Override prompts for this run


class SchedulerConfig(BaseModel):
    """Scheduler configuration."""
    enabled: bool = False
    generation_time: str = "10:00"  # HH:MM format, Warsaw timezone
    publish_time: str = "evening"  # Schedule option: "now" or "evening"
    runs: list[ScheduledRunConfig] = []  # Per-run configurations


class SchedulerState(BaseModel):
    """Scheduler runtime state."""
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None  # success, partial, error
    last_run_runs: list[str] = []
    last_run_errors: list[str] = []
    next_run_at: Optional[str] = None


class SchedulerStatus(BaseModel):
    """Full scheduler status for API response."""
    enabled: bool
    config: SchedulerConfig
    state: SchedulerState
    scheduler_running: bool


# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None
_config: Optional[SchedulerConfig] = None


def _load_config() -> SchedulerConfig:
    """Load scheduler config from settings storage."""
    try:
        storage = get_config_storage()
        if storage.exists("scheduler_config.json"):
            content = storage.read_text("scheduler_config.json")
            data = json.loads(content)
            return SchedulerConfig(**data)
    except Exception as e:
        logger.warning("Failed to load scheduler config: %s", e)
    return SchedulerConfig()


def _save_config(config: SchedulerConfig) -> None:
    """Save scheduler config to storage."""
    storage = get_config_storage()
    content = json.dumps(config.model_dump(), indent=2)
    storage.write_text("scheduler_config.json", content)


def _load_state() -> SchedulerState:
    """Load scheduler state from storage."""
    try:
        storage = get_config_storage()
        if storage.exists(SCHEDULER_STATE_KEY):
            content = storage.read_text(SCHEDULER_STATE_KEY)
            data = json.loads(content)
            return SchedulerState(**data)
    except Exception as e:
        logger.warning("Failed to load scheduler state: %s", e)
    return SchedulerState()


def _save_state(state: SchedulerState) -> None:
    """Save scheduler state to storage."""
    storage = get_config_storage()
    content = json.dumps(state.model_dump(), indent=2)
    storage.write_text(SCHEDULER_STATE_KEY, content)


async def select_news_random(count: int, items: list[dict]) -> list[dict]:
    """
    Select news items randomly from provided list.

    Args:
        count: Number of news items to select
        items: List of available news items

    Returns:
        List of selected news items
    """
    logger.info("Selecting %d random news items from %d available", count, len(items))

    if not items:
        logger.warning("No news items available for random selection")
        return []

    selected = random.sample(items, min(count, len(items)))

    logger.info("Selected %d news items randomly", len(selected))
    for item in selected:
        logger.info("  - [%s] %s", item.get("category"), item.get("title", "No title")[:50])

    return selected


def _get_news_selection_prompt() -> tuple[str, float]:
    """
    Get the news selection prompt content and temperature.

    Returns:
        Tuple of (prompt_content, temperature)
    """
    active_id = prompts_service.get_active_prompt_id("news-selection")
    if active_id:
        prompt = prompts_service.get_prompt("news-selection", active_id)
        if prompt:
            return prompt.content, prompt.temperature

    # Default prompt if none configured
    default_prompt = """You are a YouTube growth strategist and content performance analyst.

## INPUT

You will receive:

1. HISTORICAL DATA: Up to 60 past videos with:
   - Title and category
   - YouTube statistics: Views, Likes, Comments, Watch time (minutes), Average retention (%)
   - The news seed (topic summary) that was used

2. AVAILABLE NEWS TODAY: New candidate news seeds to choose from.

---

## TASK

1. Analyze the historical data to identify patterns that correlate with:
   - High total views
   - High retention rate (averageViewPercentage)
   - Long watch time (estimatedMinutesWatched)
   - Strong engagement (likes, comments ratio)

2. Extract insights such as:
   - Topic categories that perform best (Polska vs Świat)
   - Emotional triggers that drive engagement
   - Timing sensitivity (breaking news vs evergreen)
   - Format tendencies (controversy, explainer, conflict, scandal, etc.)

3. From the available news, select exactly {count} items most likely to generate high views and retention, based strictly on patterns from historical data.

---

HISTORICAL DATA (last 60 videos):
{historical_data}

AVAILABLE NEWS TODAY:
{available_news}

Select exactly {count} news items that will perform best on YouTube based on historical patterns."""

    return default_prompt, 0.7


def _format_historical_data(runs_with_stats: list[dict]) -> str:
    """Format historical run data for the LLM prompt."""
    if not runs_with_stats:
        return "No historical data available yet."

    lines = []
    for run in runs_with_stats:
        stats = run.get("yt_stats", {})
        source = run.get("source_info", {})
        seed = run.get("news_seed", "")[:200]  # First 200 chars

        line = (
            f"- Title: {source.get('title', 'Unknown')}\n"
            f"  Category: {source.get('category', 'Unknown')}\n"
            f"  Views: {stats.get('views', 0)}, "
            f"Likes: {stats.get('likes', 0)}, "
            f"Comments: {stats.get('comments', 0)}\n"
            f"  Watch time: {stats.get('estimatedMinutesWatched', 0):.1f} min, "
            f"Avg retention: {stats.get('averageViewPercentage', 0):.1f}%\n"
            f"  Summary: {seed}..."
        )
        lines.append(line)

    return "\n\n".join(lines)


def _format_available_news(items: list[dict]) -> str:
    """Format available news items for the LLM prompt."""
    lines = []
    for item in items:
        line = (
            f"ID: {item.get('id')}\n"
            f"Category: {item.get('category')}\n"
            f"Title: {item.get('title', 'No title')}\n"
            f"Rating: {item.get('rating', 0):.1f}\n"
            f"Content: {item.get('content', '')[:300]}..."
        )
        lines.append(line)

    return "\n\n---\n\n".join(lines)


def _get_recent_runs_with_stats(limit: int = 60) -> list[dict]:
    """
    Get recent runs with their seeds and YouTube stats.

    Only returns runs that have YouTube uploads and stats.

    Args:
        limit: Maximum number of runs to return

    Returns:
        List of run dicts with seed and stats info
    """
    from storage_config import get_run_storage

    # Get all runs sorted by date (newest first)
    runs = pipeline.list_runs()
    keys = pipeline.get_run_keys()

    results = []
    for run_info in runs:
        run_id = run_info["run_id"]
        run_storage = get_run_storage(run_id)

        # Check if run has YouTube upload and stats
        if not run_storage.exists(keys["yt_upload"]):
            continue

        if not run_storage.exists("yt_stats.json"):
            continue

        try:
            # Get seed data
            seed_content = run_storage.read_text(keys["seed"])
            seed_data = json.loads(seed_content)

            # Get stats
            stats_content = run_storage.read_text("yt_stats.json")
            stats_data = json.loads(stats_content)

            results.append({
                "run_id": run_id,
                "created_at": run_info.get("created_at"),
                "news_seed": seed_data.get("news_seed", ""),
                "source_info": seed_data.get("source_info", {}),
                "yt_stats": stats_data.get("stats", {}),
            })

            if len(results) >= limit:
                break
        except Exception as e:
            logger.debug("Error reading run %s: %s", run_id, e)
            continue

    return results


def _refresh_stats_for_recent_runs(limit: int = 60) -> int:
    """
    Refresh YouTube stats for recent runs that have uploads.
    Only refreshes if stats are older than 24 hours.
    Parallelized to speed up the process.

    Args:
        limit: Maximum number of runs to process

    Returns:
        Number of runs updated
    """
    from concurrent.futures import ThreadPoolExecutor
    
    logger.info("Starting parallel YouTube stats refresh for up to %d runs", limit)
    runs = pipeline.list_runs()
    
    # Filter runs that actually have YT uploads to avoid unnecessary threads
    candidate_runs = []
    for run_info in runs[:limit]:
        run_id = run_info["run_id"]
        candidate_runs.append(run_id)

    def refresh_task(run_id):
        try:
            logger.info("  Starting refresh task for run: %s", run_id)
            # Only refresh if older than 24 hours
            result = youtube_analytics.get_or_fetch_stats(run_id, force=False, max_age_hours=24)
            logger.info("  Completed refresh task for run: %s (result: %s)", run_id, "updated" if result else "cached/skipped")
            return 1 if result else 0
        except Exception as e:
            logger.error("  Error in refresh task for %s: %s", run_id, e)
            return 0

    # Use max 10 threads to avoid hitting API rate limits too hard
    updated = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(refresh_task, candidate_runs))
        updated = sum(results)

    logger.info("Refreshed YouTube stats for %d runs (using 24h cache and parallel fetch)", updated)
    return updated


async def select_news_llm(count: int, items: list[dict]) -> list[dict]:
    """
    Select news items using LLM based on historical performance from provided list.

    Args:
        count: Number of news items to select
        items: List of available news items

    Returns:
        List of selected news items
    """
    logger.info("Selecting %d news items using LLM from %d available", count, len(items))

    if not items:
        logger.warning("No news items available for LLM selection")
        return []

    # Refresh stats for recent runs first
    logger.info("Refreshing YouTube stats for recent runs...")
    await asyncio.to_thread(_refresh_stats_for_recent_runs, 60)

    # Get historical data
    runs_with_stats = await asyncio.to_thread(_get_recent_runs_with_stats, 60)
    logger.info("Found %d historical runs with YouTube stats", len(runs_with_stats))

    # Get prompt
    prompt_template, temperature = _get_news_selection_prompt()

    # Format data for prompt
    historical_data = _format_historical_data(runs_with_stats)
    available_news = _format_available_news(items)

    prompt = prompt_template.format(
        historical_data=historical_data,
        available_news=available_news,
        count=count
    )

    # Log full prompt for debugging
    logger.info("=== FINAL LLM NEWS SELECTION PROMPT ===")
    logger.info(prompt)
    logger.info("========================================")

    # Call LLM with structured output
    try:
        import openai
        logger.info("Calling OpenAI API (model=gpt-4o)...")

        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "news_selection",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "patterns_identified": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Key performance patterns identified from historical data"
                            },
                            "selected_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Array of selected news item IDs"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "Data-driven justification for the selection, referencing historical parallels and patterns"
                            }
                        },
                        "required": ["patterns_identified", "selected_ids", "reasoning"],
                        "additionalProperties": False
                    }
                }
            }
        )

        result_text = response.choices[0].message.content.strip()
        logger.info("OpenAI API response received")
        logger.debug("Raw LLM response: %s", result_text)

        result = json.loads(result_text)
        selected_ids = result.get("selected_ids", [])
        reasoning = result.get("reasoning", "")

        logger.info("LLM reasoning: %s", reasoning)

        # Map IDs to news items
        id_to_item = {item.get("id"): item for item in items}
        selected = [id_to_item[id_] for id_ in selected_ids if id_ in id_to_item]

        # Attach reasoning to items for test display
        for item in selected:
            item["_llm_reasoning"] = reasoning

        logger.info("LLM selected %d news items", len(selected))
        for item in selected:
            logger.info("  - [%s] %s", item.get("category"), item.get("title", "No title")[:50])

        return selected[:count]

    except Exception as e:
        logger.error("LLM news selection failed: %s", e, exc_info=True)
        logger.info("Falling back to random selection")
        return await select_news_random(count, items)


async def select_news(mode: SelectionMode, count: int, items: list[dict]) -> list[dict]:
    """
    Select news items for video generation.

    Args:
        mode: Selection mode ("random" or "llm")
        count: Number of news items to select
        items: List of available news items

    Returns:
        List of selected news items
    """
    if mode == "llm":
        return await select_news_llm(count, items)
    else:
        return await select_news_random(count, items)


async def run_auto_generation_for_news(
    news_item: dict,
    publish_time: str,
    prompts: Optional[dict] = None
) -> tuple[str, Optional[str]]:
    """
    Run the full generation pipeline for a single news item.

    Args:
        news_item: News item dict from InfoPigula
        publish_time: Schedule option for YouTube
        prompts: Optional prompt selections

    Returns:
        Tuple of (run_id, error_message). error_message is None on success.
    """
    run_id = None
    try:
        source_info = {
            "infopigula_id": news_item.get("id"),
            "category": news_item.get("category"),
            "rating": news_item.get("rating"),
            "title": news_item.get("title"),
            "source": news_item.get("source", {}),
        }

        run_id, _ = pipeline.create_seed(
            news_text=news_item.get("content", ""),
            auto_generated=True,
            source_info=source_info,
            prompts=prompts
        )

        logger.info("Created run %s for auto-generation", run_id)

        # Generate dialogue
        logger.info("[%s] Generating dialogue...", run_id)
        await asyncio.to_thread(pipeline.generate_dialogue_for_run, run_id)

        # Generate audio
        logger.info("[%s] Generating audio...", run_id)
        await asyncio.to_thread(pipeline.generate_audio_for_run, run_id)

        # Generate images
        logger.info("[%s] Generating images...", run_id)
        await asyncio.to_thread(pipeline.generate_images_for_run, run_id)

        # Generate video
        logger.info("[%s] Generating video...", run_id)
        await asyncio.to_thread(pipeline.generate_video_for_run, run_id)

        # Generate YT metadata
        logger.info("[%s] Generating YouTube metadata...", run_id)
        await asyncio.to_thread(pipeline.generate_yt_metadata_for_run, run_id)

        # Upload to YouTube
        logger.info("[%s] Uploading to YouTube (schedule: %s)...", run_id, publish_time)
        await asyncio.to_thread(
            pipeline.upload_to_youtube_for_run,
            run_id,
            schedule_option=publish_time
        )

        logger.info("[%s] Auto-generation completed successfully", run_id)
        return run_id, None

    except Exception as e:
        error_msg = f"Failed at run {run_id or 'creation'}: {str(e)}"
        logger.error("[%s] Auto-generation failed: %s", run_id or "N/A", e, exc_info=True)
        return run_id or "unknown", error_msg


async def run_auto_generation() -> dict:
    """
    Main scheduled job: select news and generate videos.

    Returns:
        Dict with results summary
    """
    logger.info("=== Starting scheduled auto-generation ===")

    config = _load_config()
    state = _load_state()

    state.last_run_at = datetime.now().isoformat()
    state.last_run_runs = []
    state.last_run_errors = []

    # Get enabled runs from config
    enabled_runs = [r for r in config.runs if r.enabled]
    if not enabled_runs:
        state.last_run_status = "error"
        state.last_run_errors = ["No runs configured"]
        _save_state(state)
        logger.error("Auto-generation aborted: no runs configured")
        return {"status": "error", "message": "No runs configured"}

    # Fetch available news from InfoPigula
    try:
        data = await infopigula.fetch_news()
        available_items = data.get("items", [])
    except Exception as e:
        logger.error("Failed to fetch news from InfoPigula: %s", e)
        available_items = []

    if not available_items:
        state.last_run_status = "error"
        state.last_run_errors = ["No news items available from InfoPigula"]
        _save_state(state)
        logger.error("Auto-generation aborted: no news items available")
        return {"status": "error", "message": "No news available"}

    # Determine selection mode for each enabled run and group them
    runs_by_mode: dict[str, list[int]] = {"llm": [], "random": []}
    for i, run_config in enumerate(enabled_runs):
        mode = run_config.selection_mode or "random"
        runs_by_mode[mode].append(i)

    selected_news_map = {} # run_index -> news_item
    remaining_items = list(available_items)

    # First handle LLM selections
    if runs_by_mode["llm"]:
        count = len(runs_by_mode["llm"])
        selected = await select_news_llm(count, remaining_items)
        for i, idx in enumerate(runs_by_mode["llm"]):
            if i < len(selected):
                item = selected[i]
                selected_news_map[idx] = item
                # Remove selected items from remaining to avoid duplicates
                item_id = item.get("id")
                remaining_items = [it for it in remaining_items if it.get("id") != item_id]

    # Then handle random selections
    if runs_by_mode["random"]:
        count = len(runs_by_mode["random"])
        selected = await select_news_random(count, remaining_items)
        for i, idx in enumerate(runs_by_mode["random"]):
            if i < len(selected):
                item = selected[i]
                selected_news_map[idx] = item
                # Remove selected items from remaining
                item_id = item.get("id")
                remaining_items = [it for it in remaining_items if it.get("id") != item_id]

    if not selected_news_map:
        state.last_run_status = "error"
        state.last_run_errors = ["No news items selected"]
        _save_state(state)
        logger.error("Auto-generation aborted: no news selected")
        return {"status": "error", "message": "No news selected"}

    # Generate videos for each selected news with per-run config
    results = []
    # Use sorted indices to process in order
    for idx in sorted(selected_news_map.keys()):
        news_item = selected_news_map[idx]
        run_config = enabled_runs[idx]

        # Use run-specific prompts (or None to use active prompts)
        prompts_dict = None
        if run_config.prompts:
            prompts_dict = run_config.prompts.model_dump(exclude_none=True)

        logger.info("Processing run %d/%d (original index %d) with prompts: %s",
                    len(results) + 1, len(selected_news_map), idx, prompts_dict)

        run_id, error = await run_auto_generation_for_news(
            news_item,
            config.publish_time,
            prompts=prompts_dict
        )
        results.append({"run_id": run_id, "error": error})
        if run_id and run_id != "unknown":
            state.last_run_runs.append(run_id)
        if error:
            state.last_run_errors.append(error)

    # Determine overall status
    successful = sum(1 for r in results if r["error"] is None)
    if successful == len(results) and len(results) == len(enabled_runs):
        state.last_run_status = "success"
    elif successful > 0:
        state.last_run_status = "partial"
    else:
        state.last_run_status = "error"

    _save_state(state)

    logger.info("=== Auto-generation complete: %d/%d successful ===",
                successful, len(results))

    return {
        "status": state.last_run_status,
        "successful": successful,
        "total": len(enabled_runs),
        "runs": state.last_run_runs,
        "errors": state.last_run_errors,
    }


def _get_next_run_time() -> Optional[str]:
    """Get the next scheduled run time as ISO string."""
    global _scheduler
    if _scheduler is None:
        return None

    job = _scheduler.get_job("daily_generation")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


def _schedule_job(config: SchedulerConfig) -> None:
    """Schedule the daily generation job based on config."""
    global _scheduler
    if _scheduler is None:
        return

    existing = _scheduler.get_job("daily_generation")
    if existing:
        _scheduler.remove_job("daily_generation")

    if not config.enabled:
        logger.info("Scheduler is disabled, job not scheduled")
        return

    try:
        hour, minute = map(int, config.generation_time.split(":"))
    except ValueError:
        logger.error("Invalid generation_time format: %s", config.generation_time)
        return

    trigger = CronTrigger(
        hour=hour,
        minute=minute,
        timezone="Europe/Warsaw"
    )

    _scheduler.add_job(
        run_auto_generation,
        trigger=trigger,
        id="daily_generation",
        name="Daily Video Auto-Generation",
        replace_existing=True,
    )

    next_run = _get_next_run_time()
    logger.info("Scheduled daily generation at %s Warsaw time (next: %s)",
                config.generation_time, next_run)


def init_scheduler() -> None:
    """Initialize the scheduler on application startup."""
    global _scheduler, _config

    logger.info("Initializing scheduler...")

    _scheduler = AsyncIOScheduler()
    _config = _load_config()

    _scheduler.start()
    logger.info("Scheduler started")

    _schedule_job(_config)


def shutdown_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    global _scheduler

    if _scheduler:
        logger.info("Shutting down scheduler...")
        _scheduler.shutdown(wait=False)
        _scheduler = None


def get_scheduler_status() -> SchedulerStatus:
    """Get current scheduler status."""
    global _scheduler

    config = _load_config()
    state = _load_state()
    state.next_run_at = _get_next_run_time()

    return SchedulerStatus(
        enabled=config.enabled,
        config=config,
        state=state,
        scheduler_running=_scheduler is not None and _scheduler.running,
    )


def update_scheduler_config(updates: dict) -> SchedulerConfig:
    """Update scheduler configuration."""
    global _config

    config = _load_config()

    if "enabled" in updates:
        config.enabled = updates["enabled"]
    if "generation_time" in updates:
        config.generation_time = updates["generation_time"]
    if "publish_time" in updates:
        config.publish_time = updates["publish_time"]
    if "runs" in updates:
        runs_data = updates["runs"]
        if runs_data is None:
            config.runs = []
        else:
            config.runs = [
                ScheduledRunConfig(**r) if isinstance(r, dict) else r
                for r in runs_data
            ]

    _save_config(config)
    _config = config

    _schedule_job(config)

    return config


def enable_scheduler() -> SchedulerConfig:
    """Enable the scheduler."""
    return update_scheduler_config({"enabled": True})


def disable_scheduler() -> SchedulerConfig:
    """Disable the scheduler."""
    return update_scheduler_config({"enabled": False})


async def trigger_manual_run() -> dict:
    """Manually trigger a generation run (for testing)."""
    logger.info("Manual trigger requested")
    return await run_auto_generation()


async def test_news_selection() -> dict:
    """
    Test news selection without running generation.
    Returns selected news items for preview.
    """
    config = _load_config()

    # Get enabled runs from config
    enabled_runs = [r for r in config.runs if r.enabled]
    if not enabled_runs:
        # Default fallback if no runs
        enabled_runs = [ScheduledRunConfig(enabled=True, selection_mode="random")]

    logger.info("Testing news selection for %d runs", len(enabled_runs))

    # Fetch available news
    try:
        data = await infopigula.fetch_news()
        available_items = data.get("items", [])
    except Exception as e:
        logger.error("Failed to fetch news from InfoPigula: %s", e)
        available_items = []

    if not available_items:
        return {"selection_mode": "error", "count": 0, "selected": []}

    # Determine selection mode for each enabled run and group them
    runs_by_mode: dict[str, list[int]] = {"llm": [], "random": []}
    for i, run_config in enumerate(enabled_runs):
        mode = run_config.selection_mode or "random"
        if mode not in runs_by_mode:
            mode = "random"  # Fallback
        runs_by_mode[mode].append(i)

    selected_news_map = {} # run_index -> news_item
    remaining_items = list(available_items)

    # First handle LLM selections
    if runs_by_mode["llm"]:
        count = len(runs_by_mode["llm"])
        selected = await select_news_llm(count, remaining_items)
        for i, idx in enumerate(runs_by_mode["llm"]):
            if i < len(selected):
                item = selected[i]
                selected_news_map[idx] = item
                item_id = item.get("id")
                remaining_items = [it for it in remaining_items if it.get("id") != item_id]

    # Then handle random selections
    if runs_by_mode["random"]:
        count = len(runs_by_mode["random"])
        selected = await select_news_random(count, remaining_items)
        for i, idx in enumerate(runs_by_mode["random"]):
            if i < len(selected):
                item = selected[i]
                selected_news_map[idx] = item
                item_id = item.get("id")
                remaining_items = [it for it in remaining_items if it.get("id") != item_id]

    # Reassemble selected news in order
    selected_items = []
    for idx in sorted(selected_news_map.keys()):
        selected_items.append(selected_news_map[idx])

    # Extract reasoning if present (from LLM mode)
    reasoning = None
    if selected_items and "_llm_reasoning" in selected_items[0]:
        reasoning = selected_items[0]["_llm_reasoning"]

    # Determine mode label based on run configs
    if len(runs_by_mode["llm"]) > 0 and len(runs_by_mode["random"]) > 0:
        mode_label = "mixed"
    elif len(runs_by_mode["llm"]) > 0:
        mode_label = "llm"
    else:
        mode_label = "random"

    return {
        "selection_mode": mode_label,
        "count": len(selected_items),
        "reasoning": reasoning,
        "selected": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "category": item.get("category"),
                "rating": item.get("rating", 0),
                "content": item.get("content", "")[:300],
            }
            for item in selected_items
        ]
    }
