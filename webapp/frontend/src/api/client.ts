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

// Tenant types and functions

export interface Tenant {
  id: string;
  display_name: string;
}

export async function fetchTenants(): Promise<Tenant[]> {
  const res = await fetch(`${API_BASE}/tenants`);
  if (!res.ok) throw new Error('Failed to fetch tenants');
  return res.json();
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
  auto_generated: boolean;
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
  can_fast_upload?: boolean;
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

export interface SourceInfo {
  infopigula_id?: string;
  category?: string;
  rating?: number;
  title?: string;
  source?: {
    name: string;
    url: string;
  };
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
  auto_generated: boolean;
  source_info: SourceInfo | null;
}

export interface TaskStatus {
  status: 'running' | 'completed' | 'error';
  message: string | null;
  result: Record<string, unknown> | null;
}

// Fetch functions

export interface RunsListResponse {
  runs: RunSummary[];
  total: number;
  has_more: boolean;
}

export async function fetchRuns(tenantId: string, limit: number = 20, offset: number = 0): Promise<RunsListResponse> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/runs?limit=${limit}&offset=${offset}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch runs: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchRun(tenantId: string, runId: string): Promise<RunDetail> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/runs/${runId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch run: ${response.statusText}`);
  }
  return response.json();
}

// Workflow functions

export async function createSeed(
  tenantId: string,
  newsText: string,
  prompts?: PromptSelections
): Promise<{ run_id: string; seed_path: string }> {
  const body: { news_text: string; prompts?: PromptSelections } = { news_text: newsText };
  if (prompts) {
    body.prompts = prompts;
  }
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/create-seed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create seed');
  }
  return response.json();
}

export async function generateDialogue(tenantId: string, runId: string): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/generate-dialogue`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start dialogue generation');
  }
  return response.json();
}

export async function updateDialogue(tenantId: string, runId: string, dialogue: Dialogue): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/dialogue`, {
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

export async function generateAudio(tenantId: string, runId: string): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/generate-audio`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start audio generation');
  }
  return response.json();
}

export async function generateImages(tenantId: string, runId: string): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/generate-images`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start image generation');
  }
  return response.json();
}

export async function generateVideo(tenantId: string, runId: string): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/generate-video`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start video generation');
  }
  return response.json();
}

export type ScheduleOption = 'now' | 'evening';

export async function uploadToYoutube(tenantId: string, runId: string, scheduleOption: ScheduleOption = 'evening'): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/upload-youtube`, {
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

export async function fastUpload(tenantId: string, runId: string, scheduleOption: ScheduleOption = 'evening'): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/fast-upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ schedule_option: scheduleOption }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start fast upload');
  }
  return response.json();
}

export async function getTaskStatus(tenantId: string, taskId: string): Promise<TaskStatus> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/task/${taskId}`);
  if (!response.ok) {
    throw new Error('Failed to get task status');
  }
  return response.json();
}

// Polling helper
export async function pollTaskUntilDone(
  tenantId: string,
  taskId: string,
  onProgress?: (status: TaskStatus) => void,
  intervalMs: number = 2000
): Promise<TaskStatus> {
  while (true) {
    const status = await getTaskStatus(tenantId, taskId);
    if (onProgress) onProgress(status);

    if (status.status === 'completed' || status.status === 'error') {
      return status;
    }

    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
}

// Image functions

export async function updateImagesMetadata(
  tenantId: string,
  runId: string,
  images: ImagesMetadata
): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/images`, {
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
  tenantId: string,
  runId: string,
  imageId: string
): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/regenerate-image/${imageId}`, {
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

export async function fetchSettings(tenantId: string): Promise<Settings> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/settings`);
  if (!response.ok) {
    throw new Error('Failed to fetch settings');
  }
  return response.json();
}

export async function updateSettings(tenantId: string, settings: Partial<Settings>): Promise<Settings> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/settings`, {
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

export async function fetchAvailableSettings(tenantId: string): Promise<AvailableSettings> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/settings/available`);
  if (!response.ok) {
    throw new Error('Failed to fetch available settings');
  }
  return response.json();
}

export async function fetchYouTubeToken(tenantId: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/settings/youtube-token`);
  if (!response.ok) {
    throw new Error('Failed to fetch YouTube token');
  }
  return response.json();
}

export async function startYouTubeOAuth(tenantId: string): Promise<{ auth_url: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/settings/youtube-token/refresh`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Failed to start OAuth flow');
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

export async function fetchAllRunningTasks(tenantId: string): Promise<AllRunningTasks> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/tasks/running`);
  if (!response.ok) {
    throw new Error('Failed to fetch running tasks');
  }
  return response.json();
}

export async function fetchRunningTasksForRun(tenantId: string, runId: string): Promise<{
  run_id: string;
  tasks: { [taskType: string]: RunningTaskInfo };
}> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/tasks/running`);
  if (!response.ok) {
    throw new Error('Failed to fetch running tasks');
  }
  return response.json();
}

// Drop functions for regeneration

export async function dropAudio(tenantId: string, runId: string): Promise<{ status: string; deleted: string[] }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/audio`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to drop audio');
  }
  return response.json();
}

export async function dropVideo(tenantId: string, runId: string): Promise<{ status: string; deleted: string[] }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/video`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to drop video');
  }
  return response.json();
}

export async function dropImages(tenantId: string, runId: string): Promise<{ status: string; deleted: string[] }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/images`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to drop images');
  }
  return response.json();
}

export async function deleteYoutube(tenantId: string, runId: string): Promise<{ status: string; deleted_video_id: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/workflow/${runId}/youtube`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete YouTube video');
  }
  return response.json();
}

// Delete run

export async function deleteRun(tenantId: string, runId: string): Promise<{ status: string; deleted_count: number }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/runs/${runId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete run');
  }
  return response.json();
}

// News types and functions

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

export async function fetchInfoPigulaNews(tenantId: string): Promise<InfoPigulaNewsResponse> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/news`)
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
  has_step3: boolean;
}

export interface PromptContent {
  id: string;
  name: string;
  prompt_type: PromptType;
  content: string;
  temperature: number;
  step2_content: string | null;
  step2_temperature: number;
  step3_content: string | null;
  step3_temperature: number;
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

export async function fetchAllPrompts(tenantId: string): Promise<AllPromptsResponse> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/prompts`);
  if (!response.ok) {
    throw new Error('Failed to fetch prompts');
  }
  return response.json();
}

export async function fetchPrompt(tenantId: string, promptType: PromptType, promptId: string): Promise<PromptContent> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/prompts/${promptType}/${promptId}`);
  if (!response.ok) {
    throw new Error('Failed to fetch prompt');
  }
  return response.json();
}

export interface CreatePromptParams {
  content: string;
  temperature?: number;
  step2Content?: string;
  step2Temperature?: number;
  step3Content?: string;
  step3Temperature?: number;
  setActive?: boolean;
}

export async function createPrompt(
  tenantId: string,
  promptType: PromptType,
  promptId: string,
  params: CreatePromptParams
): Promise<PromptContent> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/prompts/${promptType}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      prompt_id: promptId,
      content: params.content,
      temperature: params.temperature,
      step2_content: params.step2Content,
      step2_temperature: params.step2Temperature,
      step3_content: params.step3Content,
      step3_temperature: params.step3Temperature,
      set_active: params.setActive,
    }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create prompt');
  }
  return response.json();
}

export interface UpdatePromptParams {
  content: string;
  temperature?: number;
  step2Content?: string;
  step2Temperature?: number;
  step3Content?: string;
  step3Temperature?: number;
}

export async function updatePrompt(
  tenantId: string,
  promptType: PromptType,
  promptId: string,
  params: UpdatePromptParams
): Promise<PromptContent> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/prompts/${promptType}/${promptId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content: params.content,
      temperature: params.temperature,
      step2_content: params.step2Content,
      step2_temperature: params.step2Temperature,
      step3_content: params.step3Content,
      step3_temperature: params.step3Temperature,
    }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to update prompt');
  }
  return response.json();
}

export async function deletePrompt(tenantId: string, promptType: PromptType, promptId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/prompts/${promptType}/${promptId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete prompt');
  }
}

export async function setActivePrompt(tenantId: string, promptType: PromptType, promptId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/prompts/${promptType}/active`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_id: promptId }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to set active prompt');
  }
}

export async function migratePrompts(tenantId: string): Promise<{ migrated: Record<string, string[]> }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/prompts/migrate`, {
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

export async function fetchAnalyticsRuns(tenantId: string): Promise<AnalyticsRun[]> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/analytics/runs`);
  if (!response.ok) {
    throw new Error('Failed to fetch analytics runs');
  }
  return response.json();
}

export async function refreshRunStats(tenantId: string, runId: string): Promise<AnalyticsRun> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/analytics/runs/${runId}/refresh`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to refresh stats');
  }
  return response.json();
}

export async function refreshAllStats(tenantId: string): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/analytics/refresh-all`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Failed to start refresh');
  }
  return response.json();
}

// Prompt selections for runs

export interface PromptSelections {
  dialogue?: string | null;
  image?: string | null;
  research?: string | null;
  yt_metadata?: string | null;
}

// Scheduler types and functions

export interface ScheduledRunConfig {
  enabled: boolean;
  selection_mode: 'random' | 'llm';
  prompts?: PromptSelections | null;
}

export interface SchedulerConfig {
  enabled: boolean;
  generation_time: string;
  publish_time: string;
  runs: ScheduledRunConfig[];  // Per-run configurations
}

export interface SchedulerState {
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_runs: string[];
  last_run_errors: string[];
  next_run_at: string | null;
}

export interface SchedulerStatus {
  enabled: boolean;
  config: SchedulerConfig;
  state: SchedulerState;
  scheduler_running: boolean;
}

export async function fetchSchedulerStatus(tenantId: string): Promise<SchedulerStatus> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/scheduler/status`);
  if (!response.ok) {
    throw new Error('Failed to fetch scheduler status');
  }
  return response.json();
}

export async function enableScheduler(tenantId: string): Promise<SchedulerConfig> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/scheduler/enable`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Failed to enable scheduler');
  }
  return response.json();
}

export async function disableScheduler(tenantId: string): Promise<SchedulerConfig> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/scheduler/disable`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Failed to disable scheduler');
  }
  return response.json();
}

export async function updateSchedulerConfig(tenantId: string, config: Partial<SchedulerConfig>): Promise<SchedulerConfig> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/scheduler/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to update scheduler config');
  }
  return response.json();
}

export async function triggerSchedulerRun(tenantId: string): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/scheduler/trigger`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Failed to trigger scheduler run');
  }
  return response.json();
}
