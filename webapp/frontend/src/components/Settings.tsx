import { useEffect, useState } from 'react'
import {
  fetchSettings,
  fetchAvailableSettings,
  updateSettings,
  Settings as SettingsType,
  AvailableSettings,
} from '../api/client'

interface SettingsProps {
  onClose?: () => void
}

export default function Settings({ onClose }: SettingsProps) {
  const [settings, setSettings] = useState<SettingsType | null>(null)
  const [available, setAvailable] = useState<AvailableSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([fetchSettings(), fetchAvailableSettings()])
      .then(([settingsData, availableData]) => {
        setSettings(settingsData)
        setAvailable(availableData)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const handleSettingChange = async (update: Partial<SettingsType>) => {
    if (!settings) return

    setSaving(true)
    setError(null)

    try {
      const updated = await updateSettings(update)
      setSettings(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="settings-panel">
        <div className="settings-header">
          <h3>Settings</h3>
          {onClose && (
            <button className="close-btn" onClick={onClose}>
              x
            </button>
          )}
        </div>
        <div className="loading">Loading settings...</div>
      </div>
    )
  }

  if (error && !settings) {
    return (
      <div className="settings-panel">
        <div className="settings-header">
          <h3>Settings</h3>
          {onClose && (
            <button className="close-btn" onClick={onClose}>
              x
            </button>
          )}
        </div>
        <div className="error">Error: {error}</div>
      </div>
    )
  }

  return (
    <div className="settings-panel">
      <div className="settings-header">
        <h3>Settings</h3>
        {onClose && (
          <button className="close-btn" onClick={onClose}>
            x
          </button>
        )}
      </div>

      {error && <div className="error" style={{ marginBottom: '12px' }}>{error}</div>}

      <div className="settings-section">
        <label className="settings-label">TTS Engine</label>
        <div className="settings-description">
          Select which text-to-speech engine to use for audio generation
        </div>

        <div className="prompt-version-options">
          {saving && <div className="saving-indicator">Saving...</div>}
          {available?.tts_engines.map((engine) => (
            <label
              key={engine.id}
              className={`prompt-version-option ${
                settings?.tts_engine === engine.id ? 'selected' : ''
              }`}
            >
              <input
                type="radio"
                name="tts_engine"
                value={engine.id}
                checked={settings?.tts_engine === engine.id}
                onChange={(e) => handleSettingChange({ tts_engine: e.target.value })}
                disabled={saving}
              />
              <span className="option-content">
                <span className="option-label">{engine.label}</span>
                <span className="option-files">{engine.description}</span>
              </span>
            </label>
          ))}
        </div>
      </div>

      <div className="settings-section">
        <label className="settings-label">Image Engine</label>
        <div className="settings-description">
          Select which image generation engine to use
        </div>

        <div className="prompt-version-options">
          {saving && <div className="saving-indicator">Saving...</div>}
          {available?.image_engines.map((engine) => (
            <label
              key={engine.id}
              className={`prompt-version-option ${
                settings?.image_engine === engine.id ? 'selected' : ''
              }`}
            >
              <input
                type="radio"
                name="image_engine"
                value={engine.id}
                checked={settings?.image_engine === engine.id}
                onChange={(e) => handleSettingChange({ image_engine: e.target.value })}
                disabled={saving}
              />
              <span className="option-content">
                <span className="option-label">{engine.label}</span>
                <span className="option-files">{engine.description}</span>
              </span>
            </label>
          ))}
        </div>

        {settings?.image_engine === 'fal' && available?.fal_models && (
          <div style={{ marginTop: '12px' }}>
            <label className="settings-label">FLUX Model</label>
            <select
              value={settings.fal_model}
              onChange={(e) => handleSettingChange({ fal_model: e.target.value })}
              disabled={saving}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '4px',
                border: '1px solid var(--border-color, #ccc)',
                background: 'var(--input-bg, #fff)',
                color: 'var(--text-color, #333)',
                fontSize: '14px',
              }}
            >
              {available.fal_models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.label} — {model.description}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
    </div>
  )
}
