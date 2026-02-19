from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class YouTubeStats(BaseModel):
    views: int
    estimatedMinutesWatched: float
    averageViewPercentage: float
    likes: int
    comments: int
    shares: int
    subscribersGained: int = 0


class AnalyticsRun(BaseModel):
    id: str
    timestamp: datetime
    title: Optional[str] = None
    video_id: str
    url: str
    publish_at: Optional[str] = None
    episode_number: Optional[int] = None
    stats: Optional[YouTubeStats] = None
    stats_fetched_at: Optional[str] = None


class RunSummary(BaseModel):
    id: str
    timestamp: datetime
    title: Optional[str] = None
    status: str  # complete | partial | error
    has_video: bool
    has_audio: bool
    has_images: bool
    has_youtube: bool
    image_count: int
    auto_generated: bool = False


class RunFiles(BaseModel):
    video: Optional[str] = None
    audio: Optional[str] = None
    images: list[str] = []


class WorkflowState(BaseModel):
    current_step: str
    has_seed: bool
    has_dialogue: bool
    has_audio: bool
    has_images: bool
    has_video: bool
    has_yt_metadata: bool
    can_generate_dialogue: bool
    can_edit_dialogue: bool
    can_generate_audio: bool
    can_generate_images: bool = False
    can_generate_video: bool
    can_upload: bool
    can_delete_youtube: bool = False
    # Regeneration options
    can_drop_audio: bool = False
    can_drop_images: bool = False
    can_drop_video: bool = False


class YouTubeUpload(BaseModel):
    video_id: str
    url: str
    title: Optional[str] = None
    publish_at: Optional[str] = None
    status: str


class RunDetail(BaseModel):
    id: str
    timestamp: datetime
    dialogue: Optional[dict[str, Any]] = None
    timeline: Optional[dict[str, Any]] = None
    images: Optional[dict[str, Any]] = None
    yt_metadata: Optional[str] = None
    yt_upload: Optional[YouTubeUpload] = None
    news_data: Optional[dict[str, Any]] = None
    files: RunFiles
    workflow: Optional[WorkflowState] = None
    auto_generated: bool = False
    source_info: Optional[dict[str, Any]] = None


# Prompt selection models

class PromptSelections(BaseModel):
    """Prompt selections for runs - allows overriding the active prompt per type."""
    dialogue: Optional[str] = None  # prompt ID, None = use active
    image: Optional[str] = None
    research: Optional[str] = None
    yt_metadata: Optional[str] = None


# Scheduler models

class ScheduledRunConfig(BaseModel):
    """Configuration for a single scheduled run."""
    enabled: bool = True  # Can disable individual runs
    selection_mode: str = "random"  # "random" or "llm"
    prompts: Optional[PromptSelections] = None  # Override prompts for this run


class SchedulerConfig(BaseModel):
    """Scheduler configuration."""
    enabled: bool = False
    generation_time: str = "10:00"
    publish_time: str = "evening"
    runs: list[ScheduledRunConfig] = []  # Per-run configurations


class SchedulerState(BaseModel):
    """Scheduler runtime state."""
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None
    last_run_runs: list[str] = []
    last_run_errors: list[str] = []
    next_run_at: Optional[str] = None


class SchedulerStatus(BaseModel):
    """Full scheduler status."""
    enabled: bool
    config: SchedulerConfig
    state: SchedulerState
    scheduler_running: bool
