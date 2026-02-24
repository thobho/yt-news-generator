import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Typography from '@mui/material/Typography'
import Switch from '@mui/material/Switch'
import FormControlLabel from '@mui/material/FormControlLabel'
import TextField from '@mui/material/TextField'
import Button from '@mui/material/Button'
import Alert from '@mui/material/Alert'
import CircularProgress from '@mui/material/CircularProgress'
import Divider from '@mui/material/Divider'
import Chip from '@mui/material/Chip'
import Stack from '@mui/material/Stack'
import Select from '@mui/material/Select'
import MenuItem from '@mui/material/MenuItem'
import FormControl from '@mui/material/FormControl'
import InputLabel from '@mui/material/InputLabel'
import IconButton from '@mui/material/IconButton'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import {
  fetchSchedulerStatus,
  fetchAllPrompts,
  enableScheduler,
  disableScheduler,
  updateSchedulerConfig,
  triggerSchedulerRun,
  SchedulerStatus,
  PromptTypeInfo,
  PromptSelections,
  ScheduledRunConfig,
} from '../api/client'
import { useTenant } from '../context/TenantContext'

function getTzAbbr(timezone: string): string {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: timezone, timeZoneName: 'short' })
    .formatToParts(new Date())
  return parts.find((p) => p.type === 'timeZoneName')?.value ?? timezone
}

function getEveningLabel(timezone: string | undefined): string {
  if (!timezone) return '18-20h'
  return timezone.startsWith('America/') ? '6–8 PM' : '18-20h'
}

function formatDateTime(isoString: string | null, timezone: string): string {
  if (!isoString) return 'N/A'
  const date = new Date(isoString)
  const locale = timezone.startsWith('America/') ? 'en-US' : 'pl-PL'
  return date.toLocaleString(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: timezone,
  })
}

function StatusChip({ status }: { status: string | null }) {
  if (!status) return null
  const color = status === 'success' ? 'success' : status === 'partial' ? 'warning' : 'error'
  return <Chip label={status} color={color} size="small" />
}

export default function SchedulerPage() {
  const { currentTenant } = useTenant()
  const tenantId = currentTenant?.id ?? 'pl'
  const tenantTz = currentTenant?.timezone ?? 'Europe/Warsaw'
  const [status, setStatus] = useState<SchedulerStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [isInitialized, setIsInitialized] = useState(false)
  const [saving, setSaving] = useState(false)
  const [triggering, setTriggering] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Form state
  const [generationTime, setGenerationTime] = useState('10:00')
  const [publishTime, setPublishTime] = useState('evening')

  // Per-run configuration state
  const [runs, setRuns] = useState<ScheduledRunConfig[]>([
    { enabled: true, prompts: null, selection_mode: 'random' },
    { enabled: true, prompts: null, selection_mode: 'random' },
  ])

  // Prompt types for selection
  const [promptTypes, setPromptTypes] = useState<PromptTypeInfo[]>([])

  const loadStatus = async (forceInit = false) => {
    try {
      const data = await fetchSchedulerStatus(tenantId)
      setStatus(data)

      // Only initialize form with current config on first load or forceInit
      if (forceInit || !isInitialized) {
        setGenerationTime(data.config.generation_time || '10:00')
        setPublishTime(data.config.publish_time || 'evening')

        // Initialize runs from config (or default to 2 runs if empty)
        if (data.config.runs && data.config.runs.length > 0) {
          setRuns(data.config.runs.map(r => ({
            enabled: r.enabled ?? true,
            prompts: r.prompts || null,
            selection_mode: r.selection_mode || 'random'
          })))
        } else {
          setRuns([
            { enabled: true, prompts: null, selection_mode: 'random' },
            { enabled: true, prompts: null, selection_mode: 'random' },
          ])
        }

        if (!isInitialized) setIsInitialized(true)
      }
    } catch (err) {
      console.error('Failed to load scheduler status:', err)
      setError(err instanceof Error ? err.message : 'Failed to load scheduler status')
    } finally {
      setLoading(false)
    }
  }

  // Reset form when tenant changes so it reinitializes from the new tenant's config
  useEffect(() => {
    setIsInitialized(false)
  }, [tenantId])

  useEffect(() => {
    loadStatus()
    // Poll status every 30 seconds - but don't overwrite form state
    const interval = setInterval(() => loadStatus(false), 30000)
    return () => clearInterval(interval)
  }, [isInitialized])

  useEffect(() => {
    fetchAllPrompts(tenantId)
      .then((data) => {
        setPromptTypes(data.types)
      })
      .catch((err) => {
        console.error('Failed to fetch prompts:', err)
      })
  }, [tenantId])

  const handleToggle = async () => {
    if (!status) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      if (status.enabled) {
        await disableScheduler(tenantId)
        setSuccess('Scheduler disabled')
      } else {
        await enableScheduler(tenantId)
        setSuccess('Scheduler enabled')
      }
      await loadStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle scheduler')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveConfig = async () => {
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      await updateSchedulerConfig(tenantId, {
        generation_time: generationTime,
        publish_time: publishTime,
        runs: runs,
      })
      setSuccess('Configuration saved')
      await loadStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save configuration')
    } finally {
      setSaving(false)
    }
  }

  // Run management functions
  const handleAddRun = () => {
    setRuns([...runs, { enabled: true, prompts: null, selection_mode: 'random' }])
  }

  const handleRemoveRun = (index: number) => {
    if (runs.length > 1) {
      setRuns(runs.filter((_, i) => i !== index))
    }
  }

  const handleRunEnabledChange = (index: number, enabled: boolean) => {
    const newRuns = [...runs]
    newRuns[index] = { ...newRuns[index], enabled }
    setRuns(newRuns)
  }

  const handleRunSelectionModeChange = (index: number, mode: 'random' | 'llm') => {
    const newRuns = [...runs]
    newRuns[index] = { ...newRuns[index], selection_mode: mode }
    setRuns(newRuns)
  }

  const handleRunPromptChange = (index: number, promptType: string, value: string) => {
    const keyMap: Record<string, keyof PromptSelections> = {
      'dialogue': 'dialogue',
      'image': 'image',
      'research': 'research',
      'yt-metadata': 'yt_metadata',
    }
    const key = keyMap[promptType]
    if (!key) return

    const newRuns = [...runs]
    const currentPrompts = newRuns[index].prompts || {}
    newRuns[index] = {
      ...newRuns[index],
      prompts: {
        ...currentPrompts,
        [key]: value === '' ? null : value,
      }
    }
    setRuns(newRuns)
  }

  const handleTrigger = async () => {
    setTriggering(true)
    setError(null)
    setSuccess(null)
    try {
      const result = await triggerSchedulerRun(tenantId)
      setSuccess(result.message)
      // Start polling more frequently after trigger
      setTimeout(loadStatus, 5000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to trigger run')
    } finally {
      setTriggering(false)
    }
  }

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Scheduler
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {/* Status Card */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6">Status</Typography>
            <FormControlLabel
              control={
                <Switch
                  checked={status?.enabled ?? false}
                  onChange={handleToggle}
                  disabled={saving}
                />
              }
              label={status?.enabled ? 'Enabled' : 'Disabled'}
            />
          </Box>

          <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
            <Chip
              label={status?.scheduler_running ? 'Running' : 'Stopped'}
              color={status?.scheduler_running ? 'success' : 'default'}
              size="small"
            />
            {status?.enabled && status?.state?.next_run_at && (
              <Typography variant="body2" color="text.secondary">
                Next run: {formatDateTime(status.state.next_run_at, tenantTz)}
              </Typography>
            )}
          </Stack>

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle2" gutterBottom>
            Last Run
          </Typography>

          {status?.state?.last_run_at ? (
            <Box>
              <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="body2">
                  {formatDateTime(status.state.last_run_at, tenantTz)}
                </Typography>
                <StatusChip status={status.state.last_run_status} />
              </Stack>

              {status.state.last_run_runs.length > 0 && (
                <Box sx={{ mb: 1 }}>
                  <Typography variant="body2" color="text.secondary">
                    Created runs:{' '}
                    {status.state.last_run_runs.map((runId, i) => (
                      <span key={runId}>
                        {i > 0 && ', '}
                        <Link to={`/runs/${runId}`}>{runId}</Link>
                      </span>
                    ))}
                  </Typography>
                </Box>
              )}

              {status.state.last_run_errors.length > 0 && (
                <Alert severity="warning" sx={{ mt: 1 }}>
                  {status.state.last_run_errors.map((err, i) => (
                    <Typography key={i} variant="body2">
                      {err}
                    </Typography>
                  ))}
                </Alert>
              )}
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No runs yet
            </Typography>
          )}
        </CardContent>
      </Card>

      {/* Configuration Card */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Configuration
          </Typography>

          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 3 }}>
            <TextField
              label={`Generation Time (${getTzAbbr(tenantTz)})`}
              value={generationTime}
              onChange={(e) => setGenerationTime(e.target.value)}
              size="small"
              placeholder="HH:MM"
              helperText={`Local time in ${tenantTz}`}
              sx={{ width: 220 }}
            />
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel>Publish Time</InputLabel>
              <Select
                value={publishTime}
                label="Publish Time"
                onChange={(e) => setPublishTime(e.target.value)}
              >
                <MenuItem value="now">Immediately</MenuItem>
                <MenuItem value="evening">Evening ({getEveningLabel(tenantTz)})</MenuItem>
              </Select>
            </FormControl>
          </Box>

          <Divider sx={{ my: 2 }} />

          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <Typography variant="subtitle2">
              Run Configurations ({runs.filter(r => r.enabled).length} active)
            </Typography>
            <IconButton size="small" onClick={handleAddRun} sx={{ ml: 1 }}>
              <AddIcon />
            </IconButton>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Configure each run independently. Each enabled run will generate one video.
          </Typography>

          {runs.map((run, index) => (
            <Card key={index} variant="outlined" sx={{ mb: 2, bgcolor: run.enabled ? 'background.paper' : 'grey.100' }}>
              <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                  <FormControlLabel
                    control={
                      <Switch
                        size="small"
                        checked={run.enabled}
                        onChange={(e) => handleRunEnabledChange(index, e.target.checked)}
                      />
                    }
                    label={<Typography variant="body2" fontWeight="bold">Run {index + 1}</Typography>}
                  />
                  <IconButton
                    size="small"
                    onClick={() => handleRemoveRun(index)}
                    disabled={runs.length <= 1}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Box>
                {run.enabled && (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    <FormControl size="small" sx={{ minWidth: 150 }}>
                      <InputLabel>News Selection</InputLabel>
                      <Select
                        value={run.selection_mode || 'random'}
                        label="News Selection"
                        onChange={(e) => handleRunSelectionModeChange(index, e.target.value as 'random' | 'llm')}
                      >
                        <MenuItem value="random">Random</MenuItem>
                        <MenuItem value="llm">LLM</MenuItem>
                      </Select>
                    </FormControl>
                    {promptTypes.filter(pt => ['dialogue', 'image', 'research', 'yt-metadata'].includes(pt.type)).map((pt) => {
                      const keyMap: Record<string, keyof PromptSelections> = {
                        'dialogue': 'dialogue',
                        'image': 'image',
                        'research': 'research',
                        'yt-metadata': 'yt_metadata',
                      }
                      const key = keyMap[pt.type]
                      const currentValue = key && run.prompts ? (run.prompts[key] ?? '') : ''
                      const activePrompt = pt.prompts.find(p => p.is_active)
                      return (
                        <FormControl key={pt.type} size="small" sx={{ minWidth: 150 }}>
                          <InputLabel>{pt.label}</InputLabel>
                          <Select
                            value={currentValue}
                            label={pt.label}
                            onChange={(e) => handleRunPromptChange(index, pt.type, e.target.value as string)}
                          >
                            <MenuItem value="">
                              <em>Default ({activePrompt?.name || 'active'})</em>
                            </MenuItem>
                            {pt.prompts.map((p) => (
                              <MenuItem key={p.id} value={p.id}>
                                {p.name}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      )
                    })}
                  </Box>
                )}
              </CardContent>
            </Card>
          ))}

          <Button
            variant="contained"
            onClick={handleSaveConfig}
            disabled={saving}
            sx={{ mt: 2 }}
          >
            {saving ? 'Saving...' : 'Save Configuration'}
          </Button>
        </CardContent>
      </Card>

      {/* Manual Trigger Card */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Manual Trigger
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Manually trigger a generation run for testing. This will select news and generate videos
            according to the current configuration.
          </Typography>
          <Button
            variant="outlined"
            color="primary"
            onClick={handleTrigger}
            disabled={triggering}
          >
            {triggering ? (
              <>
                <CircularProgress size={16} sx={{ mr: 1 }} />
                Starting...
              </>
            ) : (
              'Trigger Now'
            )}
          </Button>
        </CardContent>
      </Card>
    </Box>
  )
}
