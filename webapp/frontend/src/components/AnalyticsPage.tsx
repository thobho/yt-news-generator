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
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Accordion from '@mui/material/Accordion'
import AccordionSummary from '@mui/material/AccordionSummary'
import AccordionDetails from '@mui/material/AccordionDetails'
import Dialog from '@mui/material/Dialog'
import DialogTitle from '@mui/material/DialogTitle'
import DialogContent from '@mui/material/DialogContent'
import DialogContentText from '@mui/material/DialogContentText'
import DialogActions from '@mui/material/DialogActions'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import RefreshIcon from '@mui/icons-material/Refresh'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import {
  fetchAnalyticsRuns,
  refreshRunStats,
  refreshAllStats,
  AnalyticsRun,
  generateNewsSelectionReview,
  applyNewsSelectionSuggestion,
  NewsSelectionReviewReport,
} from '../api/client'
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

  // News Selection Review state
  const [nsReport, setNsReport] = useState<NewsSelectionReviewReport | null>(null)
  const [nsLoading, setNsLoading] = useState(false)
  const [nsError, setNsError] = useState<string | null>(null)
  const [nsApplying, setNsApplying] = useState(false)
  const [nsAppliedId, setNsAppliedId] = useState<string | null>(null)
  const [nsConfirmOpen, setNsConfirmOpen] = useState(false)

  const loadRuns = async () => {
    try {
      setLoading(true)
      setRuns([])
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
  }, [tenantId])

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

  const handleGenerateNsReview = async () => {
    setNsLoading(true)
    setNsError(null)
    setNsAppliedId(null)
    try {
      const data = await generateNewsSelectionReview(tenantId)
      setNsReport(data)
    } catch (err) {
      setNsError(err instanceof Error ? err.message : 'Failed to generate news selection review')
    } finally {
      setNsLoading(false)
    }
  }

  const handleApplyNsSuggestion = async () => {
    if (!nsReport) return
    setNsConfirmOpen(false)
    setNsApplying(true)
    try {
      const result = await applyNewsSelectionSuggestion(tenantId, nsReport.suggested_prompt)
      setNsAppliedId(result.prompt_id)
    } catch (err) {
      setNsError(err instanceof Error ? err.message : 'Failed to apply suggestion')
    } finally {
      setNsApplying(false)
    }
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

      {/* News Selection Prompt Optimizer */}
      <Divider sx={{ my: 4 }} />

      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5">News Selection Prompt Optimizer</Typography>
        <Button
          variant="contained"
          onClick={handleGenerateNsReview}
          disabled={nsLoading}
          startIcon={nsLoading ? <CircularProgress size={18} /> : <AutoFixHighIcon />}
        >
          {nsLoading ? 'Analyzing...' : 'Optimize News Selection'}
        </Button>
      </Box>

      {nsError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setNsError(null)}>
          {nsError}
        </Alert>
      )}

      {!nsReport && !nsLoading && !nsError && (
        <Card>
          <CardContent>
            <Typography variant="body1" color="text.secondary">
              Click "Optimize News Selection" to analyze topic and category performance across recent
              videos and get LLM-powered suggestions for improving the news-selection prompt.
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Requires at least 5 runs with YouTube stats and seed data.
            </Typography>
          </CardContent>
        </Card>
      )}

      {nsLoading && (
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', p: 6, gap: 2 }}>
          <CircularProgress size={48} />
          <Typography color="text.secondary">
            Analyzing topic performance and generating suggestions...
          </Typography>
        </Box>
      )}

      {nsReport && !nsLoading && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          {/* Summary */}
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Summary</Typography>
              <Typography variant="body1" sx={{ whiteSpace: 'pre-line' }}>
                {nsReport.summary}
              </Typography>
            </CardContent>
          </Card>

          {/* Topic Performance Table */}
          {nsReport.topic_performance.length > 0 && (
            <Accordion defaultExpanded>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="h6">Topic Performance by Category</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Category</TableCell>
                        <TableCell align="right">Runs</TableCell>
                        <TableCell align="right">Avg Score</TableCell>
                        <TableCell align="right">Avg Views</TableCell>
                        <TableCell align="right">Avg Retention</TableCell>
                        <TableCell>Insight</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {nsReport.topic_performance.map((tp) => (
                        <TableRow key={tp.category} hover>
                          <TableCell>{tp.category}</TableCell>
                          <TableCell align="right">{tp.run_count}</TableCell>
                          <TableCell align="right">{tp.avg_score.toFixed(0)}</TableCell>
                          <TableCell align="right">{tp.avg_views.toFixed(0)}</TableCell>
                          <TableCell align="right">{tp.avg_retention.toFixed(1)}%</TableCell>
                          <TableCell>
                            <Typography variant="body2" sx={{ maxWidth: 300 }}>
                              {tp.insight}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </AccordionDetails>
            </Accordion>
          )}

          {/* Current Prompt Assessment */}
          {nsReport.current_prompt_assessment && (
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>Current Prompt Assessment</Typography>
                <Typography variant="body1" sx={{ whiteSpace: 'pre-line' }}>
                  {nsReport.current_prompt_assessment}
                </Typography>
              </CardContent>
            </Card>
          )}

          {/* Suggested Changes */}
          {nsReport.suggested_changes.length > 0 && (
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>Suggested Changes</Typography>
                <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                  {nsReport.suggested_changes.map((change, i) => (
                    <Typography component="li" variant="body1" key={i} sx={{ mb: 0.5 }}>
                      {change}
                    </Typography>
                  ))}
                </Box>
              </CardContent>
            </Card>
          )}

          {/* Suggested Prompt */}
          {nsReport.suggested_prompt && (
            <Accordion variant="outlined">
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="h6">Suggested Prompt</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Box
                  component="pre"
                  sx={{
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    bgcolor: 'grey.50',
                    p: 2,
                    borderRadius: 1,
                    fontSize: '0.8rem',
                    maxHeight: 400,
                    overflow: 'auto',
                    border: '1px solid',
                    borderColor: 'grey.200',
                  }}
                >
                  {nsReport.suggested_prompt}
                </Box>

                <Box sx={{ mt: 2, display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  {nsAppliedId ? (
                    <Chip
                      icon={<CheckCircleIcon />}
                      label={`Applied as ${nsAppliedId}`}
                      color="success"
                      variant="outlined"
                    />
                  ) : (
                    <Button
                      variant="contained"
                      size="small"
                      onClick={() => setNsConfirmOpen(true)}
                      disabled={nsApplying}
                      startIcon={
                        nsApplying
                          ? <CircularProgress size={16} />
                          : <AutoFixHighIcon />
                      }
                    >
                      {nsApplying ? 'Applying...' : 'Apply Suggestion'}
                    </Button>
                  )}
                </Box>
              </AccordionDetails>
            </Accordion>
          )}

          {/* Experiment Ideas */}
          {nsReport.experiment_ideas.length > 0 && (
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>Experiment Ideas</Typography>
                <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                  {nsReport.experiment_ideas.map((idea, i) => (
                    <Typography component="li" variant="body1" key={i} sx={{ mb: 1 }}>
                      {idea}
                    </Typography>
                  ))}
                </Box>
              </CardContent>
            </Card>
          )}
        </Box>
      )}

      {/* Confirmation dialog */}
      <Dialog open={nsConfirmOpen} onClose={() => setNsConfirmOpen(false)}>
        <DialogTitle>Apply News Selection Suggestion</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will create a new news-selection prompt version from the suggestion and set it as
            the active prompt. Future scheduled and manual runs will use this new prompt for topic
            selection.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNsConfirmOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleApplyNsSuggestion}>
            Apply
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
