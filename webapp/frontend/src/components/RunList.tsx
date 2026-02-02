import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchRuns, deleteRun, fetchAllRunningTasks, RunSummary, AllRunningTasks } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Settings from './Settings'

function formatDate(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleString('pl-PL', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function StatusBadge({ status }: { status: string }) {
  const className = `badge badge-${status}`
  return <span className={className}>{status}</span>
}

function MediaIcons({ run }: { run: RunSummary }) {
  return (
    <div style={{ display: 'flex', gap: '8px' }}>
      {run.has_audio && <span className="icon icon-active" title="Audio available">🔊</span>}
      {run.has_images && <span className="icon icon-active" title={`${run.image_count} images`}>🖼️</span>}
      {run.has_video && <span className="icon icon-active" title="Video available">🎬</span>}
      {run.has_youtube && <span className="icon icon-active" title="Uploaded to YouTube">▶️</span>}
    </div>
  )
}

export default function RunList() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [runningTasks, setRunningTasks] = useState<AllRunningTasks>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const { logout, isAuthEnabled } = useAuth()

  const loadRuns = () => {
    setLoading(true)
    fetchRuns()
      .then(setRuns)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  const loadRunningTasks = () => {
    fetchAllRunningTasks()
      .then(setRunningTasks)
      .catch(() => {}) // Silently fail
  }

  const handleDeleteRun = async (runId: string, title: string | null) => {
    const displayName = title || runId
    if (!confirm(`Are you sure you want to delete "${displayName}"? This cannot be undone.`)) {
      return
    }
    try {
      await deleteRun(runId)
      loadRuns()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete run')
    }
  }

  useEffect(() => {
    loadRuns()
    loadRunningTasks()
    // Poll for running tasks every 3 seconds
    const interval = setInterval(loadRunningTasks, 3000)
    return () => clearInterval(interval)
  }, [])

  const getRunningTaskInfo = (runId: string) => {
    const tasks = runningTasks[runId]
    if (!tasks) return null
    const taskTypes = Object.keys(tasks)
    if (taskTypes.length === 0) return null
    const firstTask = tasks[taskTypes[0]]
    return firstTask.message || taskTypes[0]
  }

  if (loading) {
    return <div className="loading">Loading runs...</div>
  }

  if (error) {
    return <div className="error">Error: {error}</div>
  }

  return (
    <div>
      <div className="page-header">
        <h1>&#x1F4F0; YT News Generator</h1>
        <div className="header-actions">
          <Link to="/settings" className="settings-toggle">
            Prompt Settings
          </Link>
          <button
            className="settings-toggle"
            onClick={() => setIsSettingsOpen(!isSettingsOpen)}
          >
            Quick Settings
          </button>
          <Link to="/new-run" className="new-run-btn">
            + New Run
          </Link>
          {isAuthEnabled && (
            <button className="logout-btn" onClick={logout}>
              Logout
            </button>
          )}
        </div>
      </div>

      {isSettingsOpen && (
        <Settings onClose={() => setIsSettingsOpen(false)} />
      )}

      {runs.length === 0 ? (
        <div className="card empty-state">
          <p>No runs found. Click "New Run" to create your first video.</p>
        </div>
      ) : (
        <>
          <table className="runs-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Title</th>
                <th>Status</th>
                <th>Media</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const processingInfo = getRunningTaskInfo(run.id)
                return (
                  <tr key={run.id} className={processingInfo ? 'processing' : ''}>
                    <td>
                      <Link to={`/runs/${run.id}`}>{formatDate(run.timestamp)}</Link>
                    </td>
                    <td>
                      <Link to={`/runs/${run.id}`}>
                        {run.title || <em style={{ color: '#999' }}>No title</em>}
                      </Link>
                      {processingInfo && (
                        <div className="processing-indicator">
                          <span className="spinner small"></span>
                          <span className="processing-text">{processingInfo}</span>
                        </div>
                      )}
                    </td>
                    <td>
                      <StatusBadge status={run.status} />
                    </td>
                    <td>
                      <MediaIcons run={run} />
                    </td>
                    <td>
                      <button
                        className="delete-btn small"
                        onClick={() => handleDeleteRun(run.id, run.title)}
                        title="Delete run"
                      >
                        🗑️
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          <div className="runs-cards">
            {runs.map((run) => {
              const processingInfo = getRunningTaskInfo(run.id)
              return (
                <div key={run.id} className={`run-card ${processingInfo ? 'processing' : ''}`}>
                  <div className="run-card-header">
                    <Link to={`/runs/${run.id}`} className="run-card-title">
                      {run.title || <em style={{ color: '#999' }}>No title</em>}
                    </Link>
                    <button
                      className="delete-btn small"
                      onClick={() => handleDeleteRun(run.id, run.title)}
                      title="Delete run"
                    >
                      🗑️
                    </button>
                  </div>
                  {processingInfo && (
                    <div className="processing-indicator">
                      <span className="spinner small"></span>
                      <span className="processing-text">{processingInfo}</span>
                    </div>
                  )}
                  <div className="run-card-footer">
                    <span className="run-card-date">{formatDate(run.timestamp)}</span>
                    <StatusBadge status={run.status} />
                    <MediaIcons run={run} />
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
