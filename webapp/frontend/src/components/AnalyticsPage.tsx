import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Box from '@mui/material/Box'
import Paper from '@mui/material/Paper'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TableSortLabel from '@mui/material/TableSortLabel'
import IconButton from '@mui/material/IconButton'
import Button from '@mui/material/Button'
import Tooltip from '@mui/material/Tooltip'
import CircularProgress from '@mui/material/CircularProgress'
import Typography from '@mui/material/Typography'
import Alert from '@mui/material/Alert'
import RefreshIcon from '@mui/icons-material/Refresh'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import { fetchAnalyticsRuns, refreshRunStats, refreshAllStats, AnalyticsRun } from '../api/client'
import { useTenant } from '../context/TenantContext'

type Order = 'asc' | 'desc'
type OrderBy = 'title' | 'publish_at' | 'views' | 'averageViewPercentage' | 'likes' | 'comments' | 'shares' | 'subscribersGained'

interface HeadCell {
  id: OrderBy
  label: string
  numeric: boolean
}

const headCells: HeadCell[] = [
  { id: 'title', label: 'Title', numeric: false },
  { id: 'publish_at', label: 'Published', numeric: false },
  { id: 'views', label: 'Views', numeric: true },
  { id: 'averageViewPercentage', label: 'Avg Watch %', numeric: true },
  { id: 'likes', label: 'Likes', numeric: true },
  { id: 'comments', label: 'Comments', numeric: true },
  { id: 'shares', label: 'Shares', numeric: true },
  { id: 'subscribersGained', label: 'Subscribers', numeric: true },
]

function formatDate(timestamp: string | null): string {
  if (!timestamp) return '-'
  const date = new Date(timestamp)
  return date.toLocaleString('pl-PL', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatNumber(num: number | undefined): string {
  if (num === undefined) return '-'
  return num.toLocaleString()
}

function formatPercentage(num: number | undefined): string {
  if (num === undefined) return '-'
  return `${num.toFixed(1)}%`
}

function getComparator(order: Order, orderBy: OrderBy): (a: AnalyticsRun, b: AnalyticsRun) => number {
  return (a, b) => {
    let aValue: number | string | null
    let bValue: number | string | null

    switch (orderBy) {
      case 'title':
        aValue = a.title ?? ''
        bValue = b.title ?? ''
        break
      case 'publish_at':
        aValue = a.publish_at ?? ''
        bValue = b.publish_at ?? ''
        break
      case 'views':
        aValue = a.stats?.views ?? 0
        bValue = b.stats?.views ?? 0
        break
      case 'averageViewPercentage':
        aValue = a.stats?.averageViewPercentage ?? 0
        bValue = b.stats?.averageViewPercentage ?? 0
        break
      case 'likes':
        aValue = a.stats?.likes ?? 0
        bValue = b.stats?.likes ?? 0
        break
      case 'comments':
        aValue = a.stats?.comments ?? 0
        bValue = b.stats?.comments ?? 0
        break
      case 'shares':
        aValue = a.stats?.shares ?? 0
        bValue = b.stats?.shares ?? 0
        break
      case 'subscribersGained':
        aValue = a.stats?.subscribersGained ?? 0
        bValue = b.stats?.subscribersGained ?? 0
        break
      default:
        return 0
    }

    if (aValue < bValue) return order === 'asc' ? -1 : 1
    if (aValue > bValue) return order === 'asc' ? 1 : -1
    return 0
  }
}

export default function AnalyticsPage() {
  const { currentTenant } = useTenant()
  const tenantId = currentTenant?.id ?? 'pl'
  const [runs, setRuns] = useState<AnalyticsRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshingRuns, setRefreshingRuns] = useState<Set<string>>(new Set())
  const [refreshingAll, setRefreshingAll] = useState(false)
  const [order, setOrder] = useState<Order>('desc')
  const [orderBy, setOrderBy] = useState<OrderBy>('publish_at')

  const loadRuns = async () => {
    try {
      setLoading(true)
      const data = await fetchAnalyticsRuns(tenantId)
      setRuns(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load analytics')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadRuns()
  }, [])

  const handleRefreshRun = async (runId: string) => {
    setRefreshingRuns((prev) => new Set(prev).add(runId))
    try {
      const updated = await refreshRunStats(tenantId, runId)
      setRuns((prev) => prev.map((r) => (r.id === runId ? updated : r)))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh stats')
    } finally {
      setRefreshingRuns((prev) => {
        const next = new Set(prev)
        next.delete(runId)
        return next
      })
    }
  }

  const handleRefreshAll = async () => {
    setRefreshingAll(true)
    try {
      await refreshAllStats(tenantId)
      // Wait a bit then reload to see updated stats
      setTimeout(loadRuns, 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start refresh')
    } finally {
      setRefreshingAll(false)
    }
  }

  const handleSort = (property: OrderBy) => {
    const isAsc = orderBy === property && order === 'asc'
    setOrder(isAsc ? 'desc' : 'asc')
    setOrderBy(property)
  }

  const sortedRuns = [...runs].sort(getComparator(order, orderBy))

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5">YouTube Analytics</Typography>
        <Button
          variant="outlined"
          startIcon={refreshingAll ? <CircularProgress size={16} /> : <RefreshIcon />}
          onClick={handleRefreshAll}
          disabled={refreshingAll}
        >
          Refresh All
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {runs.length === 0 ? (
        <Paper sx={{ p: 3, textAlign: 'center' }}>
          <Typography color="text.secondary">
            No videos found older than 48 hours. Analytics will appear here once videos are published.
          </Typography>
        </Paper>
      ) : (
        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {headCells.map((headCell) => (
                  <TableCell
                    key={headCell.id}
                    align={headCell.numeric ? 'right' : 'left'}
                    sortDirection={orderBy === headCell.id ? order : false}
                  >
                    <TableSortLabel
                      active={orderBy === headCell.id}
                      direction={orderBy === headCell.id ? order : 'asc'}
                      onClick={() => handleSort(headCell.id)}
                    >
                      {headCell.label}
                    </TableSortLabel>
                  </TableCell>
                ))}
                <TableCell align="center">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sortedRuns.map((run) => (
                <TableRow key={run.id} hover>
                  <TableCell>
                    <Link to={`/runs/${run.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
                      {run.title || <em style={{ color: '#999' }}>No title</em>}
                    </Link>
                  </TableCell>
                  <TableCell>{formatDate(run.publish_at)}</TableCell>
                  <TableCell align="right">{formatNumber(run.stats?.views)}</TableCell>
                  <TableCell align="right">{formatPercentage(run.stats?.averageViewPercentage)}</TableCell>
                  <TableCell align="right">{formatNumber(run.stats?.likes)}</TableCell>
                  <TableCell align="right">{formatNumber(run.stats?.comments)}</TableCell>
                  <TableCell align="right">{formatNumber(run.stats?.shares)}</TableCell>
                  <TableCell align="right">{formatNumber(run.stats?.subscribersGained)}</TableCell>
                  <TableCell align="center">
                    <Box sx={{ display: 'flex', gap: 0.5, justifyContent: 'center' }}>
                      <Tooltip title="Refresh stats">
                        <span>
                          <IconButton
                            size="small"
                            onClick={() => handleRefreshRun(run.id)}
                            disabled={refreshingRuns.has(run.id)}
                          >
                            {refreshingRuns.has(run.id) ? (
                              <CircularProgress size={16} />
                            ) : (
                              <RefreshIcon fontSize="small" />
                            )}
                          </IconButton>
                        </span>
                      </Tooltip>
                      <Tooltip title="Open on YouTube">
                        <IconButton
                          size="small"
                          component="a"
                          href={run.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <OpenInNewIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {runs.length > 0 && runs.some((r) => r.stats_fetched_at) && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
          Stats are cached. Click refresh to get the latest data from YouTube.
        </Typography>
      )}
    </Box>
  )
}
