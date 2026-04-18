import { useState } from 'react'
import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Typography from '@mui/material/Typography'
import Button from '@mui/material/Button'
import Alert from '@mui/material/Alert'
import CircularProgress from '@mui/material/CircularProgress'
import Chip from '@mui/material/Chip'
import Accordion from '@mui/material/Accordion'
import AccordionSummary from '@mui/material/AccordionSummary'
import AccordionDetails from '@mui/material/AccordionDetails'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh'
import {
  generatePromptReview,
  PromptReviewReport,
} from '../api/client'
import { useTenant } from '../context/TenantContext'

const PROMPT_TYPE_LABELS: Record<string, string> = {
  dialogue_step1: 'Dialogue — Step 1 (Creative)',
  dialogue_step2: 'Dialogue — Step 2 (Structure)',
  dialogue_step3: 'Dialogue — Step 3 (Polish)',
  image: 'Image Prompts',
  yt_metadata: 'YouTube Metadata',
}

export default function PromptReviewPage() {
  const { currentTenant } = useTenant()
  const tenantId = currentTenant?.id ?? 'pl'
  const [report, setReport] = useState<PromptReviewReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleGenerate = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await generatePromptReview(tenantId)
      setReport(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate report')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4">Prompt Review</Typography>
        <Button
          variant="contained"
          onClick={handleGenerate}
          disabled={loading}
          startIcon={loading ? <CircularProgress size={18} /> : <AutoFixHighIcon />}
        >
          {loading ? 'Analyzing...' : 'Generate Report'}
        </Button>
      </Box>

      {!report && !loading && !error && (
        <Card>
          <CardContent>
            <Typography variant="body1" color="text.secondary">
              Click "Generate Report" to analyze recent runs and get LLM-powered suggestions
              for improving your prompts. This compares your top and bottom performing videos
              to find patterns and recommend changes.
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Requires at least 5 runs with YouTube stats and prompt snapshots.
              The analysis may take up to a minute.
            </Typography>
          </CardContent>
        </Card>
      )}

      {loading && (
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', p: 6, gap: 2 }}>
          <CircularProgress size={48} />
          <Typography color="text.secondary">
            Analyzing performance data and generating suggestions...
          </Typography>
        </Box>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {report && !loading && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          {/* Summary */}
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Summary</Typography>
              <Typography variant="body1" sx={{ whiteSpace: 'pre-line' }}>
                {report.summary}
              </Typography>
            </CardContent>
          </Card>

          {/* Per-prompt analyses */}
          <Typography variant="h6">Prompt Analyses</Typography>
          {report.prompt_analyses.map((analysis) => (
            <Accordion key={analysis.prompt_type} defaultExpanded>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <Typography variant="subtitle1" fontWeight="bold">
                    {PROMPT_TYPE_LABELS[analysis.prompt_type] || analysis.prompt_type}
                  </Typography>
                  <Chip
                    label={analysis.current_prompt_id}
                    size="small"
                    variant="outlined"
                  />
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {/* Assessment */}
                  <Box>
                    <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                      Assessment
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-line' }}>
                      {analysis.assessment}
                    </Typography>
                  </Box>

                  {/* Suggested changes */}
                  <Box>
                    <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                      Suggested Changes
                    </Typography>
                    <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                      {analysis.suggested_changes.map((change, i) => (
                        <Typography component="li" variant="body2" key={i} sx={{ mb: 0.5 }}>
                          {change}
                        </Typography>
                      ))}
                    </Box>
                  </Box>

                  {/* Suggested prompt (collapsible) */}
                  <Accordion variant="outlined">
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Typography variant="subtitle2">Suggested Prompt</Typography>
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
                        {analysis.suggested_prompt}
                      </Box>
                    </AccordionDetails>
                  </Accordion>
                </Box>
              </AccordionDetails>
            </Accordion>
          ))}

          {/* Topic insights */}
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Topic Insights</Typography>
              <Typography variant="body1" sx={{ whiteSpace: 'pre-line' }}>
                {report.topic_insights}
              </Typography>
            </CardContent>
          </Card>

          {/* Experiment ideas */}
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Experiment Ideas</Typography>
              <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                {report.experiment_ideas.map((idea, i) => (
                  <Typography component="li" variant="body1" key={i} sx={{ mb: 1 }}>
                    {idea}
                  </Typography>
                ))}
              </Box>
            </CardContent>
          </Card>
        </Box>
      )}
    </Box>
  )
}
