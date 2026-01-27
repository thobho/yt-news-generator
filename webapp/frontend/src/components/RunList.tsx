import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchRuns, RunSummary } from '../api/client'
import { useAuth } from '../context/AuthContext'
import NewRunDialog from './NewRunDialog'
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
      <span
        className={`icon ${run.has_video ? 'icon-active' : 'icon-inactive'}`}
        title={run.has_video ? 'Video available' : 'No video'}
      >
        🎬
      </span>
      <span
        className={`icon ${run.has_audio ? 'icon-active' : 'icon-inactive'}`}
        title={run.has_audio ? 'Audio available' : 'No audio'}
      >
        🔊
      </span>
      <span
        className={`icon ${run.has_images ? 'icon-active' : 'icon-inactive'}`}
        title={run.has_images ? `${run.image_count} images` : 'No images'}
      >
        🖼️ {run.image_count > 0 && <small>({run.image_count})</small>}
      </span>
    </div>
  )
}

export default function RunList() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isNewRunOpen, setIsNewRunOpen] = useState(false)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const { logout, isAuthEnabled } = useAuth()

  const loadRuns = () => {
    setLoading(true)
    fetchRuns()
      .then(setRuns)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadRuns()
  }, [])

  if (loading) {
    return <div className="loading">Loading runs...</div>
  }

  if (error) {
    return <div className="error">Error: {error}</div>
  }

  return (
    <div>
      <div className="page-header">
        <h1>YT News Generator Dashboard</h1>
        <div className="header-actions">
          <button
            className="settings-toggle"
            onClick={() => setIsSettingsOpen(!isSettingsOpen)}
          >
            Settings
          </button>
          <button className="primary new-run-btn" onClick={() => setIsNewRunOpen(true)}>
            + New Run
          </button>
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

      <NewRunDialog
        isOpen={isNewRunOpen}
        onClose={() => {
          setIsNewRunOpen(false)
          loadRuns()
        }}
      />

      {runs.length === 0 ? (
        <div className="card empty-state">
          <p>No runs found. Click "New Run" to create your first video.</p>
        </div>
      ) : (
        <table className="runs-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Title</th>
              <th>Status</th>
              <th>Media</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td>
                  <Link to={`/runs/${run.id}`}>{formatDate(run.timestamp)}</Link>
                </td>
                <td>
                  <Link to={`/runs/${run.id}`}>
                    {run.title || <em style={{ color: '#999' }}>No title</em>}
                  </Link>
                </td>
                <td>
                  <StatusBadge status={run.status} />
                </td>
                <td>
                  <MediaIcons run={run} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
