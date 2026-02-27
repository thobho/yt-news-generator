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

// ─── Section wrapper ────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      marginBottom: '28px',
      paddingBottom: '24px',
      borderBottom: '1px solid #eee',
    }}>
      <h4 style={{
        margin: '0 0 16px 0',
        fontSize: '13px',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: '#888',
      }}>
        {title}
      </h4>
      {children}
    </div>
  )
}

// ─── Main component ──────────────────────────────────────────────────────────

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
      setSpeakers(await deleteSpeaker(tenantId, index))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  const handleMoveSpeaker = async (index: number, direction: 'up' | 'down') => {
    setError(null)
    try {
      setSpeakers(await moveSpeaker(tenantId, index, direction))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Move failed')
    }
  }

  if (loading) {
    return (
      <div className="settings-panel">
        <div className="settings-header">
          <h3>Settings</h3>
          {onClose && <button className="close-btn" onClick={onClose}>×</button>}
        </div>
        <div className="loading">Loading settings…</div>
      </div>
    )
  }

  if (error && !settings) {
    return (
      <div className="settings-panel">
        <div className="settings-header">
          <h3>Settings</h3>
          {onClose && <button className="close-btn" onClick={onClose}>×</button>}
        </div>
        <div className="error">Error: {error}</div>
      </div>
    )
  }

  return (
    <div className="settings-panel">
      <div className="settings-header">
        <h3>Settings</h3>
        {onClose && <button className="close-btn" onClick={onClose}>×</button>}
      </div>

      {error && (
        <div className="error" style={{ marginBottom: '16px' }}>{error}</div>
      )}

      {saving && (
        <div className="saving-indicator" style={{ marginBottom: '12px' }}>Saving…</div>
      )}

      {/* ── Audio ─────────────────────────────────────────── */}
      <Section title="Audio">
        <p className="settings-description" style={{ marginBottom: '12px' }}>
          Voice samples used for audio generation. Speaker 1 = voice A, Speaker 2 = voice B.
          Optimal: WAV, 24 kHz, mono, 10–30 s.
        </p>

        {speakers.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '12px' }}>
            {speakers.map((speaker, i) => (
              <div
                key={speaker.storage_key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 10px',
                  borderRadius: '6px',
                  border: '1px solid #e0e0e0',
                  background: '#fafafa',
                }}
              >
                <span style={{
                  width: '20px',
                  height: '20px',
                  borderRadius: '50%',
                  background: '#e3f2fd',
                  color: '#0066cc',
                  fontSize: '11px',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  {i + 1}
                </span>
                <span style={{ flex: 1, fontSize: '14px', color: '#333' }}>{speaker.name}</span>
                <button
                  onClick={() => handleMoveSpeaker(i, 'up')}
                  disabled={i === 0}
                  title="Move up"
                  style={{ padding: '3px 7px', fontSize: '12px', lineHeight: 1 }}
                >↑</button>
                <button
                  onClick={() => handleMoveSpeaker(i, 'down')}
                  disabled={i === speakers.length - 1}
                  title="Move down"
                  style={{ padding: '3px 7px', fontSize: '12px', lineHeight: 1 }}
                >↓</button>
                <button
                  onClick={() => handleDeleteSpeaker(i, speaker.name)}
                  title="Remove"
                  style={{ padding: '3px 7px', fontSize: '12px', lineHeight: 1, color: '#c00' }}
                >✕</button>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <input
            type="text"
            placeholder="Speaker name (optional)"
            value={speakerName}
            onChange={(e) => setSpeakerName(e.target.value)}
            disabled={speakerUploading}
            style={{
              padding: '7px 10px',
              borderRadius: '5px',
              border: '1px solid #ddd',
              fontSize: '14px',
              color: '#333',
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
              {speakerUploading ? 'Uploading…' : 'Upload'}
            </button>
          </div>
        </div>
      </Section>

      {/* ── Image Generation ──────────────────────────────── */}
      <Section title="Image Generation">
        <div className="prompt-version-options">
          {available?.image_engines.map((engine) => (
            <label
              key={engine.id}
              className={`prompt-version-option ${settings?.image_engine === engine.id ? 'selected' : ''}`}
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
            <label className="settings-label" style={{ marginBottom: '6px' }}>FLUX Model</label>
            <select
              value={settings.fal_model}
              onChange={(e) => handleSettingChange({ fal_model: e.target.value })}
              disabled={saving}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: '5px',
                border: '1px solid #ddd',
                background: '#fff',
                color: '#333',
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
      </Section>

      {/* ── YouTube ───────────────────────────────────────── */}
      <Section title="YouTube">
        <p className="settings-description" style={{ marginBottom: '12px' }}>
          Refresh an expired OAuth token or download it for use in GitHub secrets.
        </p>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className="primary"
            onClick={async () => {
              try {
                const { auth_url } = await startYouTubeOAuth(tenantId)
                window.location.href = auth_url
              } catch (err) {
                alert(err instanceof Error ? err.message : 'Failed to start OAuth')
              }
            }}
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
      </Section>
    </div>
  )
}
