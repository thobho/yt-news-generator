import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import Slider from '@mui/material/Slider';
import Divider from '@mui/material/Divider';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import {
  fetchPrompt,
  createPrompt,
  updatePrompt,
  PromptType,
} from '../api/client';

const PROMPT_TYPE_LABELS: Record<PromptType, string> = {
  dialogue: 'Dialogue Prompt',
  image: 'Image Prompt',
  research: 'Research Prompt',
  'yt-metadata': 'YouTube Metadata Prompt',
};

interface TemperatureSliderProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  helperText?: string;
}

function TemperatureSlider({ label, value, onChange, helperText }: TemperatureSliderProps) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="body2" gutterBottom>
        {label}: <strong>{value.toFixed(2)}</strong>
      </Typography>
      <Slider
        value={value}
        onChange={(_, v) => onChange(v as number)}
        min={0}
        max={1}
        step={0.05}
        marks={[
          { value: 0, label: '0' },
          { value: 0.5, label: '0.5' },
          { value: 1, label: '1' },
        ]}
        sx={{ width: 300 }}
      />
      {helperText && (
        <Typography variant="caption" color="text.secondary">
          {helperText}
        </Typography>
      )}
    </Box>
  );
}

export default function PromptEditorPage() {
  const { promptType, promptId } = useParams<{ promptType: PromptType; promptId: string }>();
  const navigate = useNavigate();
  const isNew = promptId === 'new';

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [newId, setNewId] = useState('');
  const [content, setContent] = useState('');
  const [temperature, setTemperature] = useState(0.7);
  const [step2Content, setStep2Content] = useState('');
  const [step2Temperature, setStep2Temperature] = useState(0.5);
  const [step3Content, setStep3Content] = useState('');
  const [step3Temperature, setStep3Temperature] = useState(0.6);

  const isDialogue = promptType === 'dialogue';

  useEffect(() => {
    if (!isNew && promptType && promptId) {
      loadPrompt();
    }
  }, [promptType, promptId, isNew]);

  async function loadPrompt() {
    if (!promptType || !promptId) return;
    try {
      setLoading(true);
      const prompt = await fetchPrompt(promptType, promptId);
      setContent(prompt.content);
      setTemperature(prompt.temperature);
      setStep2Content(prompt.step2_content || '');
      setStep2Temperature(prompt.step2_temperature);
      setStep3Content(prompt.step3_content || '');
      setStep3Temperature(prompt.step3_temperature);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load prompt');
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!promptType) return;

    if (isNew && !newId.trim()) {
      setError('Please enter a prompt ID');
      return;
    }

    if (!content.trim()) {
      setError('Please enter prompt content');
      return;
    }

    try {
      setSaving(true);
      setError(null);

      if (isNew) {
        await createPrompt(promptType, newId.trim(), {
          content,
          temperature,
          step2Content: isDialogue ? step2Content || undefined : undefined,
          step2Temperature: isDialogue ? step2Temperature : undefined,
          step3Content: isDialogue ? step3Content || undefined : undefined,
          step3Temperature: isDialogue ? step3Temperature : undefined,
        });
      } else if (promptId) {
        await updatePrompt(promptType, promptId, {
          content,
          temperature,
          step2Content: isDialogue ? step2Content || undefined : undefined,
          step2Temperature: isDialogue ? step2Temperature : undefined,
          step3Content: isDialogue ? step3Content || undefined : undefined,
          step3Temperature: isDialogue ? step3Temperature : undefined,
        });
      }
      navigate('/settings');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save prompt');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
        <Button
          component={Link}
          to="/settings"
          startIcon={<ArrowBackIcon />}
          color="inherit"
        >
          Back to Settings
        </Button>
      </Box>

      <Typography variant="h4" gutterBottom>
        {isNew ? 'Create' : 'Edit'} {promptType ? PROMPT_TYPE_LABELS[promptType] : 'Prompt'}
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Main Prompt */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            {isDialogue ? 'Step 1: Main Prompt (Structure)' : 'Prompt Content'}
          </Typography>

          {isNew && (
            <TextField
              label="Prompt ID"
              value={newId}
              onChange={(e) => setNewId(e.target.value)}
              fullWidth
              size="small"
              placeholder="e.g., prompt-8 or custom-name"
              helperText="Use lowercase letters, numbers, and hyphens only"
              sx={{ mb: 2 }}
            />
          )}

          <TemperatureSlider
            label="Temperature"
            value={temperature}
            onChange={setTemperature}
            helperText="Lower = more focused, Higher = more creative"
          />

          <TextField
            label="Prompt Content"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            multiline
            rows={15}
            fullWidth
            placeholder="Enter the prompt content in Markdown format..."
          />
        </CardContent>
      </Card>

      {/* Step 2 - Dialogue only */}
      {isDialogue && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Step 2: Logic/Structure Fix Prompt
            </Typography>

            <TemperatureSlider
              label="Temperature"
              value={step2Temperature}
              onChange={setStep2Temperature}
              helperText="Lower values recommended for logic fixes"
            />

            <TextField
              label="Step 2 Prompt Content"
              value={step2Content}
              onChange={(e) => setStep2Content(e.target.value)}
              multiline
              rows={12}
              fullWidth
              placeholder="Enter the logic/structure refinement prompt..."
              helperText="Fixes logical issues and structure problems"
            />
          </CardContent>
        </Card>
      )}

      {/* Step 3 - Dialogue only */}
      {isDialogue && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Step 3: Language/Style Polish Prompt (Optional)
            </Typography>

            <TemperatureSlider
              label="Temperature"
              value={step3Temperature}
              onChange={setStep3Temperature}
              helperText="Moderate values for creative polish"
            />

            <TextField
              label="Step 3 Prompt Content"
              value={step3Content}
              onChange={(e) => setStep3Content(e.target.value)}
              multiline
              rows={12}
              fullWidth
              placeholder="Enter the language/style polish prompt..."
              helperText="Polishes language and style (optional - leave empty to skip)"
            />
          </CardContent>
        </Card>
      )}

      <Divider sx={{ my: 3 }} />

      <Box sx={{ display: 'flex', gap: 2 }}>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={saving}
          size="large"
        >
          {saving ? 'Saving...' : isNew ? 'Create Prompt' : 'Save Changes'}
        </Button>
        <Button
          variant="outlined"
          component={Link}
          to="/settings"
          size="large"
        >
          Cancel
        </Button>
      </Box>
    </Box>
  );
}
