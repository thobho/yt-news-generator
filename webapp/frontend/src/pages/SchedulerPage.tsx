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
} from '../api/client'

function formatDateTime(isoString: string | null): string {
  if (!isoString) return 'N/A'
  const date = new Date(isoString)
  return date.toLocaleString('pl-PL', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function StatusChip({ status }: { status: string | null }) {
  if (!status) return null
  const color = status === 'success' ? 'success' : status === 'partial' ? 'warning' : 'error'
  return <Chip label={status} color={color} size="small" />
}

export default function SchedulerPage() {
  const [status, setStatus] = useState<SchedulerStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [triggering, setTriggering] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Form state
  const [generationTime, setGenerationTime] = useState('10:00')
  const [publishTime, setPublishTime] = useState('18:00')
  const [polandCount, setPolandCount] = useState(5)
  const [worldCount, setWorldCount] = useState(3)
  const [videosCount, setVideosCount] = useState(2)

  // Prompt selection state
  const [promptTypes, setPromptTypes] = useState<PromptTypeInfo[]>([])
  const [selectedPrompts, setSelectedPrompts] = useState<PromptSelections>({})

  const loadStatus = async () => {
    try {
      const data = await fetchSchedulerStatus()
      setStatus(data)
      // Initialize form with current config
      setGenerationTime(data.config.generation_time)
      setPublishTime(data.config.publish_time)
      setPolandCount(data.config.poland_count)
      setWorldCount(data.config.world_count)
      setVideosCount(data.config.videos_count)
      // Initialize prompt selections from config
      if (data.config.prompts) {
        setSelectedPrompts(data.config.prompts)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scheduler status')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStatus()
    // Poll status every 30 seconds
    const interval = setInterval(loadStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    fetchAllPrompts()
      .then((data) => {
        setPromptTypes(data.types)
      })
      .catch((err) => {
        console.error('Failed to fetch prompts:', err)
      })
  }, [])

  const handleToggle = async () => {
    if (!status) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      if (status.enabled) {
        await disableScheduler()
        setSuccess('Scheduler disabled')
      } else {
        await enableScheduler()
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
      // Only include prompts if at least one is selected
      const hasPromptSelections = Object.values(selectedPrompts).some(v => v !== null && v !== undefined)
      await updateSchedulerConfig({
        generation_time: generationTime,
        publish_time: publishTime,
        poland_count: polandCount,
        world_count: worldCount,
        videos_count: videosCount,
        prompts: hasPromptSelections ? selectedPrompts : undefined,
      })
      setSuccess('Configuration saved')
      await loadStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save configuration')
    } finally {
      setSaving(false)
    }
  }

  const handlePromptChange = (promptType: string, value: string) => {
    const keyMap: Record<string, keyof PromptSelections> = {
      'dialogue': 'dialogue',
      'image': 'image',
      'research': 'research',
      'yt-metadata': 'yt_metadata',
    }
    const key = keyMap[promptType]
    if (key) {
      setSelectedPrompts(prev => ({
        ...prev,
        [key]: value === '' ? null : value,
      }))
    }
  }

  const handleTrigger = async () => {
    setTriggering(true)
    setError(null)
    setSuccess(null)
    try {
      const result = await triggerSchedulerRun()
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
                Next run: {formatDateTime(status.state.next_run_at)}
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
                  {formatDateTime(status.state.last_run_at)}
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

          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 2 }}>
            <TextField
              label="Generation Time (Warsaw)"
              value={generationTime}
              onChange={(e) => setGenerationTime(e.target.value)}
              size="small"
              placeholder="HH:MM"
              helperText="Time to generate videos"
              sx={{ width: 180 }}
            />
            <TextField
              label="Publish Time"
              value={publishTime}
              onChange={(e) => setPublishTime(e.target.value)}
              size="small"
              placeholder="HH:MM"
              helperText="YouTube schedule time"
              sx={{ width: 180 }}
            />
          </Box>

          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 3 }}>
            <TextField
              label="Poland News Count"
              type="number"
              value={polandCount}
              onChange={(e) => setPolandCount(parseInt(e.target.value) || 0)}
              size="small"
              helperText="Top N Polska news"
              inputProps={{ min: 0, max: 20 }}
              sx={{ width: 150 }}
            />
            <TextField
              label="World News Count"
              type="number"
              value={worldCount}
              onChange={(e) => setWorldCount(parseInt(e.target.value) || 0)}
              size="small"
              helperText="Top N Swiat news"
              inputProps={{ min: 0, max: 20 }}
              sx={{ width: 150 }}
            />
            <TextField
              label="Videos to Generate"
              type="number"
              value={videosCount}
              onChange={(e) => setVideosCount(parseInt(e.target.value) || 0)}
              size="small"
              helperText="Random pick count"
              inputProps={{ min: 1, max: 10 }}
              sx={{ width: 150 }}
            />
          </Box>

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle2" gutterBottom>
            Prompt Selection (optional)
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Override the active prompt for each step. Leave empty to use the currently active prompt.
          </Typography>

          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 3 }}>
            {promptTypes.map((pt) => {
              const keyMap: Record<string, keyof PromptSelections> = {
                'dialogue': 'dialogue',
                'image': 'image',
                'research': 'research',
                'yt-metadata': 'yt_metadata',
              }
              const key = keyMap[pt.type]
              const currentValue = key ? selectedPrompts[key] ?? '' : ''
              const activePrompt = pt.prompts.find(p => p.is_active)
              return (
                <FormControl key={pt.type} size="small" sx={{ minWidth: 200 }}>
                  <InputLabel>{pt.label}</InputLabel>
                  <Select
                    value={currentValue}
                    label={pt.label}
                    onChange={(e) => handlePromptChange(pt.type, e.target.value as string)}
                  >
                    <MenuItem value="">
                      <em>Active ({activePrompt?.name || 'none'})</em>
                    </MenuItem>
                    {pt.prompts.map((p) => (
                      <MenuItem key={p.id} value={p.id}>
                        {p.name}{p.is_active ? ' (active)' : ''}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              )
            })}
          </Box>

          <Button
            variant="contained"
            onClick={handleSaveConfig}
            disabled={saving}
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
