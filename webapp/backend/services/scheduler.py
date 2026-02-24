"""
Scheduler service - handles automated daily video generation.
Uses APScheduler with AsyncIOScheduler for job scheduling.
One APScheduler job per tenant: generate_pl, generate_us, etc.
"""

import asyncio
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel

from ..core.logging_config import get_logger
from ..core.storage_config import get_config_storage, get_data_storage, set_tenant_prefix, set_credentials_dir

from . import settings as settings_service
from . import pipeline
from . import prompts as prompts_service
from . import youtube_analytics
from .news_source import get_news_source

from ..config.tenant_registry import TenantConfig, load_tenants

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
    generation_time: str = "10:00"  # HH:MM format
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


# ---------------------------------------------------------------------------
# Tenant context helper
# ---------------------------------------------------------------------------

def _set_tenant_context(tenant: TenantConfig) -> None:
    """Set storage ContextVars for the given tenant (needed in scheduled jobs)."""
    set_tenant_prefix(tenant.storage_prefix)
    set_credentials_dir(tenant.credentials_dir)


# ---------------------------------------------------------------------------
# Config / state I/O  (use ContextVar-based storage — caller must set context)
# ---------------------------------------------------------------------------

def _load_config() -> SchedulerConfig:
    """Load scheduler config from tenant's config storage."""
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
    """Save scheduler config to tenant's config storage."""
    storage = get_config_storage()
    content = json.dumps(config.model_dump(), indent=2)
    storage.write_text("scheduler_config.json", content)


def _load_state() -> SchedulerState:
    """Load scheduler state from tenant's config storage."""
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
    """Save scheduler state to tenant's config storage."""
    storage = get_config_storage()
    content = json.dumps(state.model_dump(), indent=2)
    storage.write_text(SCHEDULER_STATE_KEY, content)


# ---------------------------------------------------------------------------
# News selection helpers (unchanged — work on whatever tenant context is set)
# ---------------------------------------------------------------------------

async def select_news_random(count: int, items: list[dict]) -> list[dict]:
    """Select news items randomly from provided list."""
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
    """Get the news selection prompt content and temperature."""
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
        seed = run.get("news_seed", "")[:200]

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
    """Get recent runs with their seeds and YouTube stats."""
    from ..core.storage_config import get_run_storage

    runs = pipeline.list_runs()
    keys = pipeline.get_run_keys()

    results = []
    for run_info in runs:
        run_id = run_info["run_id"]
        run_storage = get_run_storage(run_id)

        if not run_storage.exists(keys["yt_upload"]):
            continue

        if not run_storage.exists("yt_stats.json"):
            continue

        try:
            seed_content = run_storage.read_text(keys["seed"])
            seed_data = json.loads(seed_content)

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
    """Refresh YouTube stats for recent runs that have uploads."""
    from concurrent.futures import ThreadPoolExecutor

    logger.info("Starting parallel YouTube stats refresh for up to %d runs", limit)
    runs = pipeline.list_runs()

    candidate_runs = []
    for run_info in runs[:limit]:
        run_id = run_info["run_id"]
        candidate_runs.append(run_id)

    def refresh_task(run_id):
        try:
            logger.info("  Starting refresh task for run: %s", run_id)
            result = youtube_analytics.get_or_fetch_stats(run_id, force=False, max_age_hours=24)
            logger.info("  Completed refresh task for run: %s (result: %s)", run_id, "updated" if result else "cached/skipped")
            return 1 if result else 0
        except Exception as e:
            logger.error("  Error in refresh task for %s: %s", run_id, e)
            return 0

    updated = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(refresh_task, candidate_runs))
        updated = sum(results)

    logger.info("Refreshed YouTube stats for %d runs", updated)
    return updated


async def select_news_llm(count: int, items: list[dict]) -> list[dict]:
    """Select news items using LLM based on historical performance."""
    logger.info("Selecting %d news items using LLM from %d available", count, len(items))

    if not items:
        logger.warning("No news items available for LLM selection")
        return []

    logger.info("Refreshing YouTube stats for recent runs...")
    await asyncio.to_thread(_refresh_stats_for_recent_runs, 60)

    runs_with_stats = await asyncio.to_thread(_get_recent_runs_with_stats, 60)
    logger.info("Found %d historical runs with YouTube stats", len(runs_with_stats))

    prompt_template, temperature = _get_news_selection_prompt()

    historical_data = _format_historical_data(runs_with_stats)
    available_news = _format_available_news(items)

    prompt = (
        prompt_template
        .replace("{historical_data}", historical_data)
        .replace("{available_news}", available_news)
        .replace("{count}", str(count))
    )

    logger.info("=== FINAL LLM NEWS SELECTION PROMPT ===")
    logger.info(prompt)
    logger.info("========================================")

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
                                "description": "Data-driven justification for the selection"
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

        id_to_item = {item.get("id"): item for item in items}
        selected = [id_to_item[id_] for id_ in selected_ids if id_ in id_to_item]

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
    """Select news items for video generation."""
    if mode == "llm":
        return await select_news_llm(count, items)
    else:
        return await select_news_random(count, items)


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

async def run_auto_generation_for_news(
    news_item: dict,
    publish_time: str,
    prompts: Optional[dict] = None
) -> tuple[str, Optional[str]]:
    """Run the full generation pipeline for a single news item."""
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

        logger.info("[%s] Generating dialogue...", run_id)
        await asyncio.to_thread(pipeline.generate_dialogue_for_run, run_id)

        logger.info("[%s] Generating audio...", run_id)
        await asyncio.to_thread(pipeline.generate_audio_for_run, run_id)

        logger.info("[%s] Generating images...", run_id)
        await asyncio.to_thread(pipeline.generate_images_for_run, run_id)

        logger.info("[%s] Generating video...", run_id)
        await asyncio.to_thread(pipeline.generate_video_for_run, run_id)

        logger.info("[%s] Generating YouTube metadata...", run_id)
        await asyncio.to_thread(pipeline.generate_yt_metadata_for_run, run_id)

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


async def run_auto_generation(tenant: TenantConfig) -> dict:
    """
    Main scheduled job: select news and generate videos for a specific tenant.
    Caller must have already set tenant context (or call _set_tenant_context first).
    """
    logger.info("=== Starting auto-generation for tenant: %s ===", tenant.id)

    config = _load_config()
    state = _load_state()

    state.last_run_at = datetime.now().isoformat()
    state.last_run_runs = []
    state.last_run_errors = []

    enabled_runs = [r for r in config.runs if r.enabled]
    if not enabled_runs:
        state.last_run_status = "error"
        state.last_run_errors = ["No runs configured"]
        _save_state(state)
        logger.error("Auto-generation aborted for %s: no runs configured", tenant.id)
        return {"status": "error", "message": "No runs configured"}

    # Fetch news using the tenant's configured news source
    try:
        source = get_news_source(tenant)
        data = await source.fetch_news()
        available_items = data.get("items", [])
    except Exception as e:
        logger.error("Failed to fetch news for tenant %s: %s", tenant.id, e)
        available_items = []

    if not available_items:
        state.last_run_status = "error"
        state.last_run_errors = ["No news items available"]
        _save_state(state)
        logger.error("Auto-generation aborted for %s: no news available", tenant.id)
        return {"status": "error", "message": "No news available"}

    # Group runs by selection mode
    runs_by_mode: dict[str, list[int]] = {"llm": [], "random": []}
    for i, run_config in enumerate(enabled_runs):
        mode = run_config.selection_mode or "random"
        runs_by_mode[mode].append(i)

    selected_news_map: dict[int, dict] = {}
    remaining_items = list(available_items)

    if runs_by_mode["llm"]:
        count = len(runs_by_mode["llm"])
        selected = await select_news_llm(count, remaining_items)
        for i, idx in enumerate(runs_by_mode["llm"]):
            if i < len(selected):
                item = selected[i]
                selected_news_map[idx] = item
                item_id = item.get("id")
                remaining_items = [it for it in remaining_items if it.get("id") != item_id]

    if runs_by_mode["random"]:
        count = len(runs_by_mode["random"])
        selected = await select_news_random(count, remaining_items)
        for i, idx in enumerate(runs_by_mode["random"]):
            if i < len(selected):
                item = selected[i]
                selected_news_map[idx] = item
                item_id = item.get("id")
                remaining_items = [it for it in remaining_items if it.get("id") != item_id]

    if not selected_news_map:
        state.last_run_status = "error"
        state.last_run_errors = ["No news items selected"]
        _save_state(state)
        logger.error("Auto-generation aborted for %s: no news selected", tenant.id)
        return {"status": "error", "message": "No news selected"}

    results = []
    for idx in sorted(selected_news_map.keys()):
        news_item = selected_news_map[idx]
        run_config = enabled_runs[idx]

        prompts_dict = None
        if run_config.prompts:
            prompts_dict = run_config.prompts.model_dump(exclude_none=True)

        logger.info("Processing run %d/%d (index %d) for tenant %s",
                    len(results) + 1, len(selected_news_map), idx, tenant.id)

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

    successful = sum(1 for r in results if r["error"] is None)
    if successful == len(results) and len(results) == len(enabled_runs):
        state.last_run_status = "success"
    elif successful > 0:
        state.last_run_status = "partial"
    else:
        state.last_run_status = "error"

    _save_state(state)

    logger.info("=== Auto-generation complete for %s: %d/%d successful ===",
                tenant.id, successful, len(results))

    return {
        "status": state.last_run_status,
        "successful": successful,
        "total": len(enabled_runs),
        "runs": state.last_run_runs,
        "errors": state.last_run_errors,
    }


async def _run_tenant_pipeline(tenant: TenantConfig) -> None:
    """APScheduler job coroutine — sets tenant context then runs auto-generation."""
    _set_tenant_context(tenant)
    logger.info("=== Scheduled job fired for tenant: %s ===", tenant.id)
    try:
        result = await run_auto_generation(tenant)
        logger.info("=== Scheduled job complete for tenant: %s (status: %s) ===",
                    tenant.id, result.get("status"))
    except Exception as e:
        logger.error("Scheduled job error for tenant %s: %s", tenant.id, e, exc_info=True)


# ---------------------------------------------------------------------------
# Scheduler management
# ---------------------------------------------------------------------------

def _schedule_tenant_job(tenant: TenantConfig, config: SchedulerConfig, timezone: str) -> None:
    """Schedule (or reschedule) the cron job for a specific tenant."""
    global _scheduler
    if _scheduler is None:
        return

    job_id = f"generate_{tenant.id}"
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)

    if not config.enabled:
        logger.info("Scheduler disabled for tenant %s — job not scheduled", tenant.id)
        return

    try:
        hour, minute = map(int, config.generation_time.split(":"))
    except ValueError:
        logger.error("Invalid generation_time '%s' for tenant %s", config.generation_time, tenant.id)
        return

    trigger = CronTrigger(hour=hour, minute=minute, timezone=timezone)
    _scheduler.add_job(
        _run_tenant_pipeline,
        trigger=trigger,
        id=job_id,
        name=f"Daily generation ({tenant.id})",
        replace_existing=True,
        args=[tenant],
    )

    job = _scheduler.get_job(job_id)
    next_run = str(job.next_run_time) if job and job.next_run_time else None
    logger.info("Scheduled job %s at %s %s (next: %s)", job_id, config.generation_time, timezone, next_run)


def init_scheduler(tenants: list[TenantConfig]) -> None:
    """Initialize the scheduler on application startup with one job per tenant."""
    global _scheduler

    logger.info("Initializing scheduler for %d tenant(s)...", len(tenants))

    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    logger.info("Scheduler started")

    for tenant in tenants:
        _set_tenant_context(tenant)
        config = _load_config()
        tenant_settings = settings_service.load_settings()
        if config.enabled:
            _schedule_tenant_job(tenant, config, tenant_settings.timezone)
        else:
            logger.info("Scheduler disabled for tenant %s — skipping job", tenant.id)


def shutdown_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    global _scheduler

    if _scheduler:
        logger.info("Shutting down scheduler...")
        _scheduler.shutdown(wait=False)
        _scheduler = None


# ---------------------------------------------------------------------------
# Per-tenant API functions (called by route handlers)
# ---------------------------------------------------------------------------

def get_tenant_scheduler_status(tenant: TenantConfig) -> SchedulerStatus:
    """Get scheduler status for a specific tenant."""
    _set_tenant_context(tenant)
    config = _load_config()
    state = _load_state()

    job_id = f"generate_{tenant.id}"
    job = _scheduler.get_job(job_id) if _scheduler else None
    if job and job.next_run_time:
        state.next_run_at = str(job.next_run_time)

    return SchedulerStatus(
        enabled=config.enabled,
        config=config,
        state=state,
        scheduler_running=_scheduler is not None and _scheduler.running,
    )


def enable_tenant_scheduler(tenant: TenantConfig) -> SchedulerConfig:
    """Enable the scheduler for a specific tenant."""
    _set_tenant_context(tenant)
    config = _load_config()
    config.enabled = True
    _save_config(config)
    tenant_settings = settings_service.load_settings()
    _schedule_tenant_job(tenant, config, tenant_settings.timezone)
    return config


def disable_tenant_scheduler(tenant: TenantConfig) -> SchedulerConfig:
    """Disable the scheduler for a specific tenant."""
    _set_tenant_context(tenant)
    config = _load_config()
    config.enabled = False
    _save_config(config)
    job_id = f"generate_{tenant.id}"
    if _scheduler and _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
        logger.info("Removed job %s", job_id)
    return config


def update_tenant_scheduler_config(tenant: TenantConfig, updates: dict) -> SchedulerConfig:
    """Update scheduler configuration for a specific tenant and reschedule."""
    _set_tenant_context(tenant)
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
    tenant_settings = settings_service.load_settings()
    _schedule_tenant_job(tenant, config, tenant_settings.timezone)
    return config


async def trigger_tenant_run(tenant: TenantConfig) -> dict:
    """Manually trigger a generation run for a specific tenant."""
    _set_tenant_context(tenant)
    logger.info("Manual trigger requested for tenant: %s", tenant.id)
    return await run_auto_generation(tenant)


async def test_tenant_news_selection(tenant: TenantConfig) -> dict:
    """Test news selection without running generation for a specific tenant."""
    _set_tenant_context(tenant)
    config = _load_config()

    enabled_runs = [r for r in config.runs if r.enabled]
    if not enabled_runs:
        enabled_runs = [ScheduledRunConfig(enabled=True, selection_mode="random")]

    logger.info("Testing news selection for tenant %s (%d runs)", tenant.id, len(enabled_runs))

    try:
        source = get_news_source(tenant)
        data = await source.fetch_news()
        available_items = data.get("items", [])
    except Exception as e:
        logger.error("Failed to fetch news for tenant %s: %s", tenant.id, e)
        available_items = []

    if not available_items:
        return {"selection_mode": "error", "count": 0, "selected": []}

    runs_by_mode: dict[str, list[int]] = {"llm": [], "random": []}
    for i, run_config in enumerate(enabled_runs):
        mode = run_config.selection_mode or "random"
        if mode not in runs_by_mode:
            mode = "random"
        runs_by_mode[mode].append(i)

    selected_news_map: dict[int, dict] = {}
    remaining_items = list(available_items)

    if runs_by_mode["llm"]:
        count = len(runs_by_mode["llm"])
        selected = await select_news_llm(count, remaining_items)
        for i, idx in enumerate(runs_by_mode["llm"]):
            if i < len(selected):
                item = selected[i]
                selected_news_map[idx] = item
                item_id = item.get("id")
                remaining_items = [it for it in remaining_items if it.get("id") != item_id]

    if runs_by_mode["random"]:
        count = len(runs_by_mode["random"])
        selected = await select_news_random(count, remaining_items)
        for i, idx in enumerate(runs_by_mode["random"]):
            if i < len(selected):
                item = selected[i]
                selected_news_map[idx] = item
                item_id = item.get("id")
                remaining_items = [it for it in remaining_items if it.get("id") != item_id]

    selected_items = [selected_news_map[idx] for idx in sorted(selected_news_map.keys())]

    reasoning = None
    if selected_items and "_llm_reasoning" in selected_items[0]:
        reasoning = selected_items[0]["_llm_reasoning"]

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
