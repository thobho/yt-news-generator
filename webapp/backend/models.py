from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


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
