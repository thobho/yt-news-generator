import { useEffect, useRef, useState } from 'react'
import {
  fetchSettings,
  fetchAvailableSettings,
  updateSettings,
  fetchYouTubeToken,
  startYouTubeOAuth,
  fetchSpeakers,
  uploadSpeaker,
  deleteSpeaker,
  moveSpeaker,
  Settings as SettingsType,
  AvailableSettings,
  Speaker,
} from '../api/client'
import { useTenant } from '../context/TenantContext'

interface SettingsProps {
  onClose?: () => void
}

export default function Settings({ onClose }: SettingsProps) {
  const { currentTenant } = useTenant()
  const tenantId = currentTenant?.id ?? 'pl'
  const [settings, setSettings] = useState<SettingsType | null>(null)
  const [available, setAvailable] = useState<AvailableSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [speakerUploading, setSpeakerUploading] = useState(false)
  const [speakerName, setSpeakerName] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setSettings(null)
    setLoading(true)
    Promise.all([
      fetchSettings(tenantId),
      fetchAvailableSettings(tenantId),
      fetchSpeakers(tenantId),
    ])
      .then(([settingsData, availableData, speakersData]) => {
        setSettings(settingsData)
        setAvailable(availableData)
        setSpeakers(speakersData)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [tenantId])

  const handleUploadSpeaker = async () => {
    const file = fileInputRef.current?.files?.[0]
    if (!file) return
    setSpeakerUploading(true)
    setError(null)
    try {
      const updated = await uploadSpeaker(tenantId, file, speakerName || undefined)
      setSpeakers(updated)
      setSpeakerName('')
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setSpeakerUploading(false)
    }
  }

  const handleDeleteSpeaker = async (index: number, name: string) => {
    if (!confirm(`Delete speaker "${name}"?`)) return
    setError(null)
    try {
      const updated = await deleteSpeaker(tenantId, index)
      setSpeakers(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  const handleMoveSpeaker = async (index: number, direction: 'up' | 'down') => {
    setError(null)
    try {
      const updated = await moveSpeaker(tenantId, index, direction)
      setSpeakers(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Move failed')
    }
  }

  const handleSettingChange = async (update: Partial<SettingsType>) => {
    if (!settings) return

    setSaving(true)
    setError(null)

    try {
      const updated = await updateSettings(tenantId, update)
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
      {onClose && (
        <div className="settings-header">
          <h3>Settings</h3>
          <button className="close-btn" onClick={onClose}>
            x
          </button>
        </div>
      )}

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

      <div className="settings-section">
        <label className="settings-label">Speakers</label>
        <div className="settings-description">
          Voice samples for audio generation. First speaker = voice A, second = voice B. Optimal format: WAV, 24kHz, mono, 10–30s.
        </div>

        {speakers.length > 0 && (
          <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {speakers.map((speaker, i) => (
              <div
                key={speaker.storage_key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '6px 8px',
                  borderRadius: '4px',
                  border: '1px solid var(--border-color, #ccc)',
                  background: 'var(--input-bg, #f9f9f9)',
                }}
              >
                <span style={{ flex: 1, fontSize: '14px' }}>
                  <span style={{ opacity: 0.5, marginRight: '6px' }}>{i + 1}.</span>
                  {speaker.name}
                </span>
                <button
                  onClick={() => handleMoveSpeaker(i, 'up')}
                  disabled={i === 0}
                  title="Move up"
                  style={{ padding: '2px 6px', fontSize: '12px' }}
                >
                  ↑
                </button>
                <button
                  onClick={() => handleMoveSpeaker(i, 'down')}
                  disabled={i === speakers.length - 1}
                  title="Move down"
                  style={{ padding: '2px 6px', fontSize: '12px' }}
                >
                  ↓
                </button>
                <button
                  onClick={() => handleDeleteSpeaker(i, speaker.name)}
                  title="Delete"
                  style={{ padding: '2px 6px', fontSize: '12px', color: 'var(--danger-color, #c00)' }}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <input
            type="text"
            placeholder="Speaker name (optional)"
            value={speakerName}
            onChange={(e) => setSpeakerName(e.target.value)}
            disabled={speakerUploading}
            style={{
              padding: '6px 8px',
              borderRadius: '4px',
              border: '1px solid var(--border-color, #ccc)',
              background: 'var(--input-bg, #fff)',
              color: 'var(--text-color, #333)',
              fontSize: '14px',
            }}
          />
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <input
              ref={fileInputRef}
              type="file"
              accept=".wav,.mp3"
              disabled={speakerUploading}
              style={{ flex: 1, fontSize: '13px' }}
            />
            <button
              onClick={handleUploadSpeaker}
              disabled={speakerUploading}
              className="primary"
            >
              {speakerUploading ? 'Uploading...' : 'Upload'}
            </button>
          </div>
        </div>
      </div>

      <div className="settings-section">
        <label className="settings-label">YouTube Token</label>
        <div className="settings-description">
          Refresh expired token or download for GitHub secrets
        </div>
        <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
          <button
            onClick={async () => {
              try {
                const { auth_url } = await startYouTubeOAuth(tenantId)
                window.location.href = auth_url
              } catch (err) {
                alert(err instanceof Error ? err.message : 'Failed to start OAuth')
              }
            }}
            className="primary"
          >
            Refresh Token
          </button>
          <button
            onClick={async () => {
              try {
                const token = await fetchYouTubeToken(tenantId)
                const blob = new Blob([JSON.stringify(token)], { type: 'application/json' })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = 'token.json'
                a.click()
                URL.revokeObjectURL(url)
              } catch (err) {
                alert(err instanceof Error ? err.message : 'Failed to download token')
              }
            }}
          >
            Download
          </button>
        </div>
      </div>
    </div>
  )
}
