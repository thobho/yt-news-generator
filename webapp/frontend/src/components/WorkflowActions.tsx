import { useState } from 'react'
import {
  WorkflowState,
  generateAudio,
  generateVideo,
  uploadToYoutube,
  pollTaskUntilDone,
  TaskStatus,
} from '../api/client'

interface WorkflowActionsProps {
  runId: string
  workflow: WorkflowState
  onEditDialogue: () => void
  onRefresh: () => void
}

export default function WorkflowActions({
  runId,
  workflow,
  onEditDialogue,
  onRefresh,
}: WorkflowActionsProps) {
  const [isRunning, setIsRunning] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const runTask = async (
    taskFn: (id: string) => Promise<{ task_id: string }>,
    taskName: string
  ) => {
    setIsRunning(true)
    setError(null)
    setStatus(`Starting ${taskName}...`)

    try {
      const { task_id } = await taskFn(runId)

      const result = await pollTaskUntilDone(task_id, (taskStatus: TaskStatus) => {
        if (taskStatus.message) {
          setStatus(taskStatus.message)
        }
      })

      if (result.status === 'error') {
        throw new Error(result.message || `${taskName} failed`)
      }

      setStatus(`${taskName} completed!`)
      setTimeout(() => {
        setStatus(null)
        onRefresh()
      }, 1500)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setIsRunning(false)
    }
  }

  const handleGenerateAudio = () => runTask(generateAudio, 'Audio generation')
  const handleGenerateVideo = () => runTask(generateVideo, 'Video rendering')
  const handleUploadYoutube = () => runTask(uploadToYoutube, 'YouTube upload')

  // Determine current step for display
  const getStepIndicator = () => {
    if (workflow.can_upload) return { step: 5, text: 'Ready to upload' }
    if (workflow.can_generate_video) return { step: 4, text: 'Ready for video' }
    if (workflow.can_generate_audio) return { step: 3, text: 'Ready for audio' }
    if (workflow.has_dialogue) return { step: 2, text: 'Dialogue ready' }
    if (workflow.has_seed) return { step: 1, text: 'Seed created' }
    return { step: 0, text: 'New' }
  }

  const { step, text } = getStepIndicator()

  return (
    <div className="workflow-actions">
      <div className="workflow-progress">
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${(step / 5) * 100}%` }} />
        </div>
        <span className="progress-text">{text}</span>
      </div>

      {(status || error) && (
        <div className={`workflow-status ${error ? 'error' : ''}`}>
          {status && !error && <span className="spinner"></span>}
          {error || status}
        </div>
      )}

      <div className="workflow-buttons">
        {workflow.can_edit_dialogue && (
          <button onClick={onEditDialogue} disabled={isRunning}>
            Edit Dialogue
          </button>
        )}

        {workflow.can_generate_audio && (
          <button onClick={handleGenerateAudio} disabled={isRunning} className="primary">
            Generate Audio & Images
          </button>
        )}

        {workflow.can_generate_video && (
          <button onClick={handleGenerateVideo} disabled={isRunning} className="primary">
            Render Video
          </button>
        )}

        {workflow.can_upload && (
          <button onClick={handleUploadYoutube} disabled={isRunning} className="primary upload">
            Upload to YouTube
          </button>
        )}
      </div>
    </div>
  )
}
