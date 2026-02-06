const API_BASE = '/api';

// Auth types and functions

export interface AuthStatus {
  authenticated: boolean;
  auth_enabled: boolean;
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  const response = await fetch(`${API_BASE}/auth/status`, {
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Failed to fetch auth status');
  }
  return response.json();
}

export async function login(password: string): Promise<void> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ password }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Login failed');
  }
}

export async function logout(): Promise<void> {
  const response = await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Logout failed');
  }
}

export interface RunSummary {
  id: string;
  timestamp: string;
  title: string | null;
  status: 'complete' | 'partial' | 'error';
  has_video: boolean;
  has_audio: boolean;
  has_images: boolean;
  has_youtube: boolean;
  image_count: number;
}

export interface RunFiles {
  video: string | null;
  audio: string | null;
  images: string[];
}

export interface DialogueSource {
  name: string;
  text: string;
}

export interface DialogueItem {
  speaker: string;
  text: string;
  emphasis?: string[];
  sources?: DialogueSource[];
}

export interface Dialogue {
  topic_id: string;
  script: DialogueItem[];
}

export interface SourceSummary {
  name: string;
  url: string;
  summary: string;
}

export interface NewsData {
  topic_id: string;
  language: string;
  news_text: string;
  source_summaries: SourceSummary[];
}

export interface WorkflowState {
  current_step: string;
  has_seed: boolean;
  has_dialogue: boolean;
  has_audio: boolean;
  has_images: boolean;
  has_video: boolean;
  has_yt_metadata: boolean;
  can_generate_dialogue: boolean;
  can_edit_dialogue: boolean;
  can_generate_audio: boolean;
  can_generate_images?: boolean;
  can_generate_video: boolean;
  can_upload: boolean;
  can_delete_youtube?: boolean;
  // Regeneration options
  can_drop_audio?: boolean;
  can_drop_images?: boolean;
  can_drop_video?: boolean;
}

export interface ImageInfo {
  id: string;
  purpose: string;
  prompt: string;
  file?: string | null;
  error?: string;
}

export interface YouTubeUpload {
  video_id: string;
  url: string;
  title?: string;
  publish_at?: string;
  status: string;
}

export interface ImagesMetadata {
  topic_summary?: string;
  visual_theme?: string;
  images: ImageInfo[];
}

export interface RunDetail {
  id: string;
  timestamp: string;
  dialogue: Dialogue | null;
  timeline: Record<string, unknown> | null;
  images: ImagesMetadata | null;
  yt_metadata: string | null;
  yt_upload: YouTubeUpload | null;
  news_data: NewsData | null;
  files: RunFiles;
  workflow: WorkflowState | null;
}

export interface TaskStatus {
  status: 'running' | 'completed' | 'error';
  message: string | null;
  result: Record<string, unknown> | null;
}

// Fetch functions

export async function fetchRuns(): Promise<RunSummary[]> {
  const response = await fetch(`${API_BASE}/runs`);
  if (!response.ok) {
    throw new Error(`Failed to fetch runs: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchRun(runId: string): Promise<RunDetail> {
  const response = await fetch(`${API_BASE}/runs/${runId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch run: ${response.statusText}`);
  }
  return response.json();
}

// Workflow functions

export async function createSeed(newsText: string): Promise<{ run_id: string; seed_path: string }> {
  const response = await fetch(`${API_BASE}/workflow/create-seed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ news_text: newsText }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create seed');
  }
  return response.json();
}

export async function generateDialogue(runId: string): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/generate-dialogue`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start dialogue generation');
  }
  return response.json();
}

export async function updateDialogue(runId: string, dialogue: Dialogue): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/dialogue`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dialogue }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to update dialogue');
  }
  return response.json();
}

export async function generateAudio(runId: string): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/generate-audio`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start audio generation');
  }
  return response.json();
}

export async function generateImages(runId: string): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/generate-images`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start image generation');
  }
  return response.json();
}

export async function generateVideo(runId: string): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/generate-video`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start video generation');
  }
  return response.json();
}

export type ScheduleOption = '8:00' | '18:00' | '1hour' | 'auto';

export async function uploadToYoutube(runId: string, scheduleOption: ScheduleOption = 'auto'): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/upload-youtube`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ schedule_option: scheduleOption }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start YouTube upload');
  }
  return response.json();
}

export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  const response = await fetch(`${API_BASE}/workflow/task/${taskId}`);
  if (!response.ok) {
    throw new Error('Failed to get task status');
  }
  return response.json();
}

// Polling helper
export async function pollTaskUntilDone(
  taskId: string,
  onProgress?: (status: TaskStatus) => void,
  intervalMs: number = 2000
): Promise<TaskStatus> {
  while (true) {
    const status = await getTaskStatus(taskId);
    if (onProgress) onProgress(status);

    if (status.status === 'completed' || status.status === 'error') {
      return status;
    }

    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
}

// Image functions

export async function updateImagesMetadata(
  runId: string,
  images: ImagesMetadata
): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/images`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ images }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to update images');
  }
  return response.json();
}

export async function regenerateImage(
  runId: string,
  imageId: string
): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/regenerate-image/${imageId}`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start image regeneration');
  }
  return response.json();
}

// Settings types and functions

export interface Settings {
  prompt_version: string;
  tts_engine: string;
  image_engine: string;
  fal_model: string;
}

export interface PromptVersionInfo {
  version: string;
  label: string;
  files: {
    main: string;
    refine: string;
  };
}

export interface TTSEngineInfo {
  id: string;
  label: string;
  description: string;
}

export interface ImageEngineInfo {
  id: string;
  label: string;
  description: string;
}

export interface FalModelInfo {
  id: string;
  label: string;
  description: string;
}

export interface AvailableSettings {
  prompt_versions: PromptVersionInfo[];
  tts_engines: TTSEngineInfo[];
  image_engines: ImageEngineInfo[];
  fal_models: FalModelInfo[];
}

export async function fetchSettings(): Promise<Settings> {
  const response = await fetch(`${API_BASE}/settings`);
  if (!response.ok) {
    throw new Error('Failed to fetch settings');
  }
  return response.json();
}

export async function updateSettings(settings: Partial<Settings>): Promise<Settings> {
  const response = await fetch(`${API_BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to update settings');
  }
  return response.json();
}

export async function fetchAvailableSettings(): Promise<AvailableSettings> {
  const response = await fetch(`${API_BASE}/settings/available`);
  if (!response.ok) {
    throw new Error('Failed to fetch available settings');
  }
  return response.json();
}

// Running tasks

export interface RunningTaskInfo {
  status: string;
  message: string | null;
}

export interface AllRunningTasks {
  [runId: string]: {
    [taskType: string]: RunningTaskInfo;
  };
}

export async function fetchAllRunningTasks(): Promise<AllRunningTasks> {
  const response = await fetch(`${API_BASE}/workflow/tasks/running`);
  if (!response.ok) {
    throw new Error('Failed to fetch running tasks');
  }
  return response.json();
}

export async function fetchRunningTasksForRun(runId: string): Promise<{
  run_id: string;
  tasks: { [taskType: string]: RunningTaskInfo };
}> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/tasks/running`);
  if (!response.ok) {
    throw new Error('Failed to fetch running tasks');
  }
  return response.json();
}

// Drop functions for regeneration

export async function dropAudio(runId: string): Promise<{ status: string; deleted: string[] }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/audio`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to drop audio');
  }
  return response.json();
}

export async function dropVideo(runId: string): Promise<{ status: string; deleted: string[] }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/video`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to drop video');
  }
  return response.json();
}

export async function dropImages(runId: string): Promise<{ status: string; deleted: string[] }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/images`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to drop images');
  }
  return response.json();
}

export async function deleteYoutube(runId: string): Promise<{ status: string; deleted_video_id: string }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/youtube`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete YouTube video');
  }
  return response.json();
}

// Delete run

export async function deleteRun(runId: string): Promise<{ status: string; deleted_count: number }> {
  const response = await fetch(`${API_BASE}/runs/${runId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete run');
  }
  return response.json();
}

// InfoPigula types and functions

export interface InfoPigulaSource {
  name: string
  url: string
}

export interface InfoPigulaNewsItem {
  id: string
  title: string | null
  content: string
  category: string
  rating: number
  total_votes: number
  source: InfoPigulaSource
}

export interface InfoPigulaNewsResponse {
  title: string
  publish_date: string
  items: InfoPigulaNewsItem[]
}

export async function fetchInfoPigulaNews(): Promise<InfoPigulaNewsResponse> {
  const response = await fetch(`${API_BASE}/infopigula/news`)
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to fetch news')
  }
  return response.json()
}

// Prompts types and functions

export type PromptType = 'dialogue' | 'image' | 'research' | 'yt-metadata';

export interface PromptInfo {
  id: string;
  name: string;
  prompt_type: PromptType;
  created_at: string | null;
  is_active: boolean;
  has_step2: boolean;
}

export interface PromptContent {
  id: string;
  name: string;
  prompt_type: PromptType;
  content: string;
  step2_content: string | null;
  is_active: boolean;
}

export interface PromptTypeInfo {
  type: PromptType;
  label: string;
  description: string;
  prompts: PromptInfo[];
  active_id: string | null;
  has_step2: boolean;
}

export interface AllPromptsResponse {
  types: PromptTypeInfo[];
}

export async function fetchAllPrompts(): Promise<AllPromptsResponse> {
  const response = await fetch(`${API_BASE}/prompts`);
  if (!response.ok) {
    throw new Error('Failed to fetch prompts');
  }
  return response.json();
}

export async function fetchPrompt(promptType: PromptType, promptId: string): Promise<PromptContent> {
  const response = await fetch(`${API_BASE}/prompts/${promptType}/${promptId}`);
  if (!response.ok) {
    throw new Error('Failed to fetch prompt');
  }
  return response.json();
}

export async function createPrompt(
  promptType: PromptType,
  promptId: string,
  content: string,
  step2Content?: string,
  setActive?: boolean
): Promise<PromptContent> {
  const response = await fetch(`${API_BASE}/prompts/${promptType}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      prompt_id: promptId,
      content,
      step2_content: step2Content,
      set_active: setActive,
    }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create prompt');
  }
  return response.json();
}

export async function updatePrompt(
  promptType: PromptType,
  promptId: string,
  content: string,
  step2Content?: string
): Promise<PromptContent> {
  const response = await fetch(`${API_BASE}/prompts/${promptType}/${promptId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content,
      step2_content: step2Content,
    }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to update prompt');
  }
  return response.json();
}

export async function deletePrompt(promptType: PromptType, promptId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/prompts/${promptType}/${promptId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete prompt');
  }
}

export async function setActivePrompt(promptType: PromptType, promptId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/prompts/${promptType}/active`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_id: promptId }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to set active prompt');
  }
}

export async function migratePrompts(): Promise<{ migrated: Record<string, string[]> }> {
  const response = await fetch(`${API_BASE}/prompts/migrate`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Failed to migrate prompts');
  }
  return response.json();
}

// Analytics types and functions

export interface YouTubeStats {
  views: number;
  estimatedMinutesWatched: number;
  averageViewPercentage: number;
  likes: number;
  comments: number;
  shares: number;
  subscribersGained: number;
}

export interface AnalyticsRun {
  id: string;
  timestamp: string;
  title: string | null;
  video_id: string;
  url: string;
  publish_at: string | null;
  episode_number: number | null;
  stats: YouTubeStats | null;
  stats_fetched_at: string | null;
}

export async function fetchAnalyticsRuns(): Promise<AnalyticsRun[]> {
  const response = await fetch(`${API_BASE}/analytics/runs`);
  if (!response.ok) {
    throw new Error('Failed to fetch analytics runs');
  }
  return response.json();
}

export async function refreshRunStats(runId: string): Promise<AnalyticsRun> {
  const response = await fetch(`${API_BASE}/analytics/runs/${runId}/refresh`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to refresh stats');
  }
  return response.json();
}

export async function refreshAllStats(): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_BASE}/analytics/refresh-all`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Failed to start refresh');
  }
  return response.json();
}
