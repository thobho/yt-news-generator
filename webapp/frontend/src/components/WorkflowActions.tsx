import { useState, useEffect } from 'react'
import {
  WorkflowState,
  generateAudio,
  generateImages,
  generateVideo,
  uploadToYoutube,
  pollTaskUntilDone,
  TaskStatus,
  dropAudio,
  dropVideo,
  dropImages,
  deleteYoutube,
  fetchRunningTasksForRun,
  ScheduleOption,
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
  const [currentTask, setCurrentTask] = useState<string | null>(null)
  const [scheduleOption, setScheduleOption] = useState<ScheduleOption>('8:00')

  // Poll for running tasks (to show progress even after page refresh)
  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null

    const checkRunningTasks = async () => {
      try {
        const result = await fetchRunningTasksForRun(runId)
        const taskTypes = Object.keys(result.tasks)
        if (taskTypes.length > 0) {
          const firstTask = result.tasks[taskTypes[0]]
          setIsRunning(true)
          setCurrentTask(taskTypes[0])
          setStatus(firstTask.message || `${taskTypes[0]} in progress...`)
        } else if (currentTask && isRunning) {
          // Task just completed
          setIsRunning(false)
          setCurrentTask(null)
          setStatus(null)
          onRefresh()
        }
      } catch {
        // Ignore errors
      }
    }

    checkRunningTasks()
    interval = setInterval(checkRunningTasks, 2000)

    return () => {
      if (interval) clearInterval(interval)
    }
  }, [runId, currentTask, isRunning, onRefresh])

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
  const handleGenerateImages = () => runTask(generateImages, 'Image generation')
  const handleGenerateVideo = () => runTask(generateVideo, 'Video rendering')
  const handleUploadYoutube = () => runTask(
    (id: string) => uploadToYoutube(id, scheduleOption),
    'YouTube upload'
  )

  const handleDrop = async (
    dropFn: (id: string) => Promise<{ status: string; deleted: string[] }>,
    itemName: string
  ) => {
    if (!confirm(`Are you sure you want to drop ${itemName}? This cannot be undone.`)) {
      return
    }
    setIsRunning(true)
    setError(null)
    setStatus(`Dropping ${itemName}...`)

    try {
      await dropFn(runId)
      setStatus(`${itemName} dropped!`)
      setTimeout(() => {
        setStatus(null)
        onRefresh()
      }, 1000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setIsRunning(false)
    }
  }

  const handleDropAudio = () => handleDrop(dropAudio, 'Audio')
  const handleDropVideo = () => handleDrop(dropVideo, 'Video')
  const handleDropImages = () => handleDrop(dropImages, 'Images')

  const handleDeleteYoutube = async () => {
    if (!confirm('Are you sure you want to remove this video from YouTube? This cannot be undone.')) {
      return
    }
    setIsRunning(true)
    setError(null)
    setStatus('Removing from YouTube...')

    try {
      await deleteYoutube(runId)
      setStatus('Removed from YouTube!')
      setTimeout(() => {
        setStatus(null)
        onRefresh()
      }, 1000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setIsRunning(false)
    }
  }

  // Determine current step for display
  const getStepIndicator = () => {
    if (workflow.can_delete_youtube) return { step: 6, text: 'Uploaded to YouTube' }
    if (workflow.can_upload) return { step: 6, text: 'Ready to upload' }
    if (workflow.can_generate_video) return { step: 5, text: 'Ready for video' }
    if (workflow.can_generate_images) return { step: 4, text: 'Ready for images' }
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
          <div className="progress-fill" style={{ width: `${(step / 6) * 100}%` }} />
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
            Generate Audio
          </button>
        )}

        {workflow.can_generate_images && (
          <button onClick={handleGenerateImages} disabled={isRunning} className="primary">
            Generate Images
          </button>
        )}

        {workflow.can_generate_video && (
          <button onClick={handleGenerateVideo} disabled={isRunning} className="primary">
            Render Video
          </button>
        )}

        {workflow.can_upload && (
          <div className="upload-section">
            <div className="schedule-options">
              <label className="schedule-label">Schedule:</label>
              <div className="schedule-buttons">
                <button
                  type="button"
                  className={`schedule-btn ${scheduleOption === '8:00' ? 'active' : ''}`}
                  onClick={() => setScheduleOption('8:00')}
                  disabled={isRunning}
                >
                  8:00
                </button>
                <button
                  type="button"
                  className={`schedule-btn ${scheduleOption === '18:00' ? 'active' : ''}`}
                  onClick={() => setScheduleOption('18:00')}
                  disabled={isRunning}
                >
                  18:00
                </button>
                <button
                  type="button"
                  className={`schedule-btn ${scheduleOption === '1hour' ? 'active' : ''}`}
                  onClick={() => setScheduleOption('1hour')}
                  disabled={isRunning}
                >
                  +1h
                </button>
              </div>
            </div>
            <button onClick={handleUploadYoutube} disabled={isRunning} className="primary upload">
              Upload to YouTube
            </button>
          </div>
        )}
      </div>

      {/* Drop/Regenerate section */}
      {(workflow.can_drop_audio || workflow.can_drop_images || workflow.can_drop_video || workflow.can_delete_youtube) && (
        <div className="workflow-drop-section">
          <span className="drop-label">Drop to regenerate:</span>
          <div className="drop-buttons">
            {workflow.can_drop_audio && (
              <button onClick={handleDropAudio} disabled={isRunning} className="danger small">
                Drop Audio
              </button>
            )}
            {workflow.can_drop_images && (
              <button onClick={handleDropImages} disabled={isRunning} className="danger small">
                Drop Images
              </button>
            )}
            {workflow.can_drop_video && (
              <button onClick={handleDropVideo} disabled={isRunning} className="danger small">
                Drop Video
              </button>
            )}
            {workflow.can_delete_youtube && (
              <button onClick={handleDeleteYoutube} disabled={isRunning} className="danger small">
                Remove from YouTube
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
