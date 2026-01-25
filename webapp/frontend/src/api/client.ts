const API_BASE = '/api';

export interface RunSummary {
  id: string;
  timestamp: string;
  title: string | null;
  status: 'complete' | 'partial' | 'error';
  has_video: boolean;
  has_audio: boolean;
  has_images: boolean;
  image_count: number;
}

export interface RunFiles {
  video: string | null;
  audio: string | null;
  images: string[];
}

export interface DialogueItem {
  speaker: string;
  text: string;
  emphasis?: string[];
  source?: {
    name: string;
    text: string;
  };
}

export interface Dialogue {
  topic_id: string;
  scene: string;
  hook: string;
  script: DialogueItem[];
  climax_line: string;
  viewer_question: string;
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
  can_generate_video: boolean;
  can_upload: boolean;
}

export interface ImageInfo {
  id: string;
  purpose: string;
  prompt: string;
  segment_indices?: number[];
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

export async function uploadToYoutube(runId: string): Promise<{ task_id: string }> {
  const response = await fetch(`${API_BASE}/workflow/${runId}/upload-youtube`, {
    method: 'POST',
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
