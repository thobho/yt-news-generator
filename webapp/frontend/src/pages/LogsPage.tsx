import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchLogs } from '../api/client'

// Log format: "2024-01-01 12:00:00 | LEVEL    | module | message"
const LEVEL_COLORS: Record<string, string> = {
  'ERROR':   '#ff6b6b',
  'WARNING': '#ffa94d',
  'INFO':    '#74c0fc',
  'DEBUG':   '#868e96',
}

function getLineColor(line: string): string {
  for (const [level, color] of Object.entries(LEVEL_COLORS)) {
    if (line.includes(`| ${level}`)) return color
  }
  return '#d4d4d4'
}

const LINE_OPTIONS = [100, 500, 1000, 5000]

export default function LogsPage() {
  const [file, setFile] = useState<'app' | 'error'>('app')
  const [lines, setLines] = useState(500)
  const [search, setSearch] = useState('')
  const [logLines, setLogLines] = useState<string[]>([])
  const [totalLines, setTotalLines] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchLogs(file, lines, search || undefined)
      setLogLines(data.lines)
      setTotalLines(data.total_lines)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [file, lines, search])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!autoRefresh) return
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [autoRefresh, load])

  return (
    <div>
      <div className="page-header">
        <h1>Logs</h1>
      </div>

      <div className="card" style={{ marginBottom: '16px' }}>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>

          <div className="schedule-buttons">
            <button
              type="button"
              className={`schedule-btn ${file === 'app' ? 'active' : ''}`}
              onClick={() => setFile('app')}
            >
              App
            </button>
            <button
              type="button"
              className={`schedule-btn ${file === 'error' ? 'active' : ''}`}
              onClick={() => setFile('error')}
            >
              Errors
            </button>
          </div>

          <select
            value={lines}
            onChange={e => setLines(Number(e.target.value))}
            style={{ padding: '4px 8px', borderRadius: '4px', border: '1px solid #ccc' }}
          >
            {LINE_OPTIONS.map(n => (
              <option key={n} value={n}>Last {n}</option>
            ))}
          </select>

          <input
            type="text"
            placeholder="Search..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && load()}
            style={{ padding: '4px 8px', borderRadius: '4px', border: '1px solid #ccc', minWidth: '200px' }}
          />

          <button onClick={load} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>

          <label style={{ display: 'flex', alignItems: 'center', gap: '6px', userSelect: 'none' }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={e => setAutoRefresh(e.target.checked)}
            />
            Auto (5s)
          </label>

          <button
            type="button"
            onClick={() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' })}
          >
            ↓ Bottom
          </button>

          <span style={{ marginLeft: 'auto', color: '#666', fontSize: '0.85rem' }}>
            {logLines.length.toLocaleString()} / {totalLines.toLocaleString()} lines
          </span>
        </div>
      </div>

      {error && <div className="error" style={{ marginBottom: '12px' }}>{error}</div>}

      <div style={{
        background: '#1e1e1e',
        borderRadius: '8px',
        padding: '12px',
        overflowX: 'auto',
        overflowY: 'auto',
        maxHeight: 'calc(100vh - 260px)',
        fontFamily: 'monospace',
        fontSize: '0.78rem',
        lineHeight: '1.6',
      }}>
        {logLines.length === 0 && !loading && (
          <span style={{ color: '#868e96' }}>No log entries found.</span>
        )}
        {logLines.map((line, i) => (
          <div key={i} style={{ color: getLineColor(line), whiteSpace: 'pre' }}>
            {line}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
