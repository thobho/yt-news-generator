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
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from logging_config import get_logger
from storage_config import get_config_storage

from . import infopigula
from . import pipeline
from . import settings as settings_service

logger = get_logger(__name__)

# State file location
SCHEDULER_STATE_KEY = "scheduler_state.json"


class PromptSelections(BaseModel):
    """Prompt selections for runs - allows overriding the active prompt per type."""
    dialogue: Optional[str] = None  # prompt ID, None = use active
    image: Optional[str] = None
    research: Optional[str] = None
    yt_metadata: Optional[str] = None


class SchedulerConfig(BaseModel):
    """Scheduler configuration stored in settings."""
    enabled: bool = False
    generation_time: str = "10:00"  # HH:MM format, Warsaw timezone
    publish_time: str = "evening"  # Schedule option: "now" or "evening" (18-20h)
    poland_count: int = 5  # Top N Poland news to consider
    world_count: int = 3  # Top N World news to consider
    videos_count: int = 2  # Number of videos to generate
    prompts: Optional[PromptSelections] = None  # Prompt overrides


class SchedulerState(BaseModel):
    """Scheduler runtime state."""
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None  # success, partial, error
    last_run_runs: list[str] = []  # Run IDs created
    last_run_errors: list[str] = []  # Error messages if any
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


async def select_daily_news(
    poland_count: int = 5,
    world_count: int = 3,
    pick_count: int = 2
) -> list[dict]:
    """
    Select news items for video generation.

    Args:
        poland_count: Number of top Poland news to consider
        world_count: Number of top World news to consider
        pick_count: Number of news to randomly select from candidates

    Returns:
        List of selected news items
    """
    logger.info("Selecting daily news (poland=%d, world=%d, pick=%d)",
                poland_count, world_count, pick_count)

    try:
        data = await infopigula.fetch_news()
        items = data.get("items", [])
    except Exception as e:
        logger.error("Failed to fetch news from InfoPigula: %s", e)
        return []

    if not items:
        logger.warning("No news items available from InfoPigula")
        return []

    # Filter by category and sort by rating
    poland_news = sorted(
        [n for n in items if n.get("category") == "Polska"],
        key=lambda x: x.get("rating", 0),
        reverse=True
    )[:poland_count]

    world_news = sorted(
        [n for n in items if n.get("category") == "Świat"],
        key=lambda x: x.get("rating", 0),
        reverse=True
    )[:world_count]

    # Combine candidates
    candidates = poland_news + world_news

    if not candidates:
        logger.warning("No news candidates found after filtering")
        return []

    # Random selection
    selected = random.sample(candidates, min(pick_count, len(candidates)))

    logger.info("Selected %d news items for generation", len(selected))
    for item in selected:
        logger.info("  - [%s] %s (rating: %.1f)",
                   item.get("category"),
                   item.get("title", "No title")[:50],
                   item.get("rating", 0))

    return selected


async def run_auto_generation_for_news(
    news_item: dict,
    publish_time: str,
    prompts: Optional[dict] = None
) -> tuple[str, Optional[str]]:
    """
    Run the full generation pipeline for a single news item.

    Args:
        news_item: News item dict from InfoPigula
        publish_time: Schedule option for YouTube (e.g., "18:00")
        prompts: Optional prompt selections (dialogue, image, research, yt_metadata IDs)

    Returns:
        Tuple of (run_id, error_message). error_message is None on success.
    """
    run_id = None
    try:
        # Create seed with metadata
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

        # Upload to YouTube with scheduled time
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

    # Update state
    state.last_run_at = datetime.now().isoformat()
    state.last_run_runs = []
    state.last_run_errors = []

    # Select news
    selected_news = await select_daily_news(
        poland_count=config.poland_count,
        world_count=config.world_count,
        pick_count=config.videos_count
    )

    if not selected_news:
        state.last_run_status = "error"
        state.last_run_errors = ["No news items available"]
        _save_state(state)
        logger.error("Auto-generation aborted: no news available")
        return {"status": "error", "message": "No news available"}

    # Get prompt selections from config
    prompts_dict = None
    if config.prompts:
        prompts_dict = config.prompts.model_dump(exclude_none=True)

    # Generate videos for each selected news
    results = []
    for news_item in selected_news:
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
    if successful == len(results):
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
        "total": len(results),
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

    # Remove existing job if any
    existing = _scheduler.get_job("daily_generation")
    if existing:
        _scheduler.remove_job("daily_generation")

    if not config.enabled:
        logger.info("Scheduler is disabled, job not scheduled")
        return

    # Parse time
    try:
        hour, minute = map(int, config.generation_time.split(":"))
    except ValueError:
        logger.error("Invalid generation_time format: %s", config.generation_time)
        return

    # Schedule with Warsaw timezone
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

    # Schedule job if enabled
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

    # Apply updates
    if "enabled" in updates:
        config.enabled = updates["enabled"]
    if "generation_time" in updates:
        config.generation_time = updates["generation_time"]
    if "publish_time" in updates:
        config.publish_time = updates["publish_time"]
    if "poland_count" in updates:
        config.poland_count = updates["poland_count"]
    if "world_count" in updates:
        config.world_count = updates["world_count"]
    if "videos_count" in updates:
        config.videos_count = updates["videos_count"]
    if "prompts" in updates:
        prompts_data = updates["prompts"]
        if prompts_data is None:
            config.prompts = None
        elif isinstance(prompts_data, PromptSelections):
            config.prompts = prompts_data
        else:
            config.prompts = PromptSelections(**prompts_data)

    _save_config(config)
    _config = config

    # Reschedule job
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
