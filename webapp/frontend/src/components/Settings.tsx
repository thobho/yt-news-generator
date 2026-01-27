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

  const handlePromptVersionChange = async (version: string) => {
    if (!settings) return

    setSaving(true)
    setError(null)

    try {
      const updated = await updateSettings({ prompt_version: version })
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
        <label className="settings-label">Dialogue Prompt Version</label>
        <div className="settings-description">
          Select which prompt template to use for dialogue generation
        </div>

        <div className="prompt-version-options">
          {available?.prompt_versions.map((pv) => (
            <label
              key={pv.version}
              className={`prompt-version-option ${
                settings?.prompt_version === pv.version ? 'selected' : ''
              }`}
            >
              <input
                type="radio"
                name="prompt_version"
                value={pv.version}
                checked={settings?.prompt_version === pv.version}
                onChange={(e) => handlePromptVersionChange(e.target.value)}
                disabled={saving}
              />
              <span className="option-content">
                <span className="option-label">{pv.label}</span>
                <span className="option-files">
                  {pv.files.main}, {pv.files.refine}
                </span>
              </span>
            </label>
          ))}
        </div>

        {saving && <div className="saving-indicator">Saving...</div>}
      </div>
    </div>
  )
}
