import { useEffect, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  fetchRun,
  RunDetail as RunDetailType,
  DialogueItem,
  Dialogue,
  ImagesMetadata,
  ImageInfo,
  YouTubeUpload,
  updateImagesMetadata,
  regenerateImage,
  pollTaskUntilDone,
} from '../api/client'
import WorkflowActions from './WorkflowActions'
import DialogueEditor from './DialogueEditor'

type TabName = 'dialogue' | 'media' | 'sources' | 'youtube'

function formatDate(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleString('pl-PL', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function StatusBadge({ status }: { status: string }) {
  const className = `badge badge-${status}`
  return <span className={className}>{status}</span>
}

function DialogueTab({
  dialogue,
  isEditing,
  runId,
  canEdit,
  onEdit,
  onSave,
  onCancelEdit,
}: {
  dialogue: RunDetailType['dialogue']
  isEditing: boolean
  runId: string
  canEdit: boolean
  onEdit: () => void
  onSave: (d: Dialogue) => void
  onCancelEdit: () => void
}) {
  if (!dialogue) {
    return <div className="card">No dialogue data available.</div>
  }

  if (isEditing) {
    return (
      <DialogueEditor
        runId={runId}
        dialogue={dialogue}
        onSave={onSave}
        onCancel={onCancelEdit}
      />
    )
  }

  return (
    <div>
      {canEdit && (
        <div className="card">
          <button onClick={onEdit}>
            Edit Dialogue
          </button>
        </div>
      )}

      <h3 style={{ marginBottom: '16px' }}>Script</h3>
      {Array.isArray(dialogue.script) && dialogue.script.length > 0 ? (
        dialogue.script.map((item: DialogueItem, index: number) => (
          <div key={index} className="dialogue-item">
            <div className={`dialogue-speaker ${item.speaker?.toLowerCase() ?? ''}`}>
              {item.speaker ?? 'Unknown'}
            </div>
            <div className="dialogue-text">{item.text ?? ''}</div>
            {item.source && (
              <div className="dialogue-source">
                <strong>{item.source.name}:</strong> {item.source.text}
              </div>
            )}
          </div>
        ))
      ) : (
        <div className="card">No script lines available.</div>
      )}
    </div>
  )
}

function MediaTab({
  runId,
  files,
  imagesMetadata,
  onImagesUpdate,
}: {
  runId: string
  files: RunDetailType['files']
  imagesMetadata: ImagesMetadata | null
  onImagesUpdate: (metadata: ImagesMetadata) => void
}) {
  const [selectedImage, setSelectedImage] = useState<string | null>(null)
  const [editingImageId, setEditingImageId] = useState<string | null>(null)
  const [editingPrompt, setEditingPrompt] = useState('')
  const [regeneratingIds, setRegeneratingIds] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)

  const getImageUrl = (imageInfo: ImageInfo): string | null => {
    if (!imageInfo.file) return null
    return `/api/runs/${runId}/images/${imageInfo.file}`
  }

  const handleEditPrompt = (image: ImageInfo) => {
    setEditingImageId(image.id)
    setEditingPrompt(image.prompt)
  }

  const handleSavePrompt = async () => {
    if (!editingImageId || !imagesMetadata) return

    setSaving(true)
    try {
      const updatedImages = imagesMetadata.images.map((img) =>
        img.id === editingImageId ? { ...img, prompt: editingPrompt } : img
      )
      const updatedMetadata = { ...imagesMetadata, images: updatedImages }
      await updateImagesMetadata(runId, updatedMetadata)
      onImagesUpdate(updatedMetadata)
      setEditingImageId(null)
    } catch (err) {
      console.error('Failed to save prompt:', err)
      alert('Failed to save prompt')
    } finally {
      setSaving(false)
    }
  }

  const handleRegenerate = async (imageId: string) => {
    setRegeneratingIds((prev) => new Set(prev).add(imageId))
    try {
      const { task_id } = await regenerateImage(runId, imageId)
      const result = await pollTaskUntilDone(task_id)
      if (result.status === 'error') {
        alert(`Regeneration failed: ${result.message}`)
      } else {
        // Refresh to get updated image
        window.location.reload()
      }
    } catch (err) {
      console.error('Failed to regenerate image:', err)
      alert('Failed to regenerate image')
    } finally {
      setRegeneratingIds((prev) => {
        const next = new Set(prev)
        next.delete(imageId)
        return next
      })
    }
  }

  return (
    <div>
      {files.video && (
        <div className="card">
          <h3 style={{ marginBottom: '16px' }}>Video</h3>
          <div className="video-container">
            <video controls preload="metadata">
              <source src={files.video} type="video/mp4" />
              Your browser does not support the video tag.
            </video>
          </div>
        </div>
      )}

      {files.audio && (
        <div className="card">
          <h3 style={{ marginBottom: '16px' }}>Audio</h3>
          <div className="audio-container">
            <audio controls preload="metadata">
              <source src={files.audio} type="audio/mpeg" />
              Your browser does not support the audio tag.
            </audio>
          </div>
        </div>
      )}

      {imagesMetadata && imagesMetadata.images.length > 0 && (
        <div className="card">
          <h3 style={{ marginBottom: '16px' }}>
            Images ({imagesMetadata.images.length})
          </h3>
          {imagesMetadata.topic_summary && (
            <p style={{ marginBottom: '8px', color: '#666' }}>
              <strong>Topic:</strong> {imagesMetadata.topic_summary}
            </p>
          )}
          {imagesMetadata.visual_theme && (
            <p style={{ marginBottom: '16px', color: '#666' }}>
              <strong>Theme:</strong> {imagesMetadata.visual_theme}
            </p>
          )}

          <div className="image-cards">
            {imagesMetadata.images.map((imageInfo) => {
              const imageUrl = getImageUrl(imageInfo)
              const isRegenerating = regeneratingIds.has(imageInfo.id)
              const isEditing = editingImageId === imageInfo.id

              return (
                <div key={imageInfo.id} className="image-card">
                  <div className="image-card-preview">
                    {imageUrl ? (
                      <img
                        src={imageUrl}
                        alt={imageInfo.purpose}
                        onClick={() => setSelectedImage(imageUrl)}
                      />
                    ) : (
                      <div className="image-placeholder">
                        {imageInfo.error ? (
                          <span className="error-text">{imageInfo.error}</span>
                        ) : (
                          <span>No image</span>
                        )}
                      </div>
                    )}
                    {isRegenerating && (
                      <div className="image-overlay">
                        <span>Regenerating...</span>
                      </div>
                    )}
                  </div>

                  <div className="image-card-info">
                    <div className="image-card-header">
                      <strong>{imageInfo.id}</strong>
                      <span className="image-purpose">{imageInfo.purpose}</span>
                    </div>

                    {isEditing ? (
                      <div className="prompt-editor">
                        <textarea
                          value={editingPrompt}
                          onChange={(e) => setEditingPrompt(e.target.value)}
                          rows={4}
                        />
                        <div className="prompt-editor-buttons">
                          <button
                            onClick={handleSavePrompt}
                            disabled={saving}
                            className="btn-primary"
                          >
                            {saving ? 'Saving...' : 'Save'}
                          </button>
                          <button
                            onClick={() => setEditingImageId(null)}
                            disabled={saving}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <p className="image-prompt">{imageInfo.prompt}</p>
                        <div className="image-card-actions">
                          <button
                            onClick={() => handleEditPrompt(imageInfo)}
                            disabled={isRegenerating}
                          >
                            Edit Prompt
                          </button>
                          <button
                            onClick={() => handleRegenerate(imageInfo.id)}
                            disabled={isRegenerating}
                            className="btn-primary"
                          >
                            {isRegenerating ? 'Regenerating...' : 'Regenerate'}
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {selectedImage && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.9)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            zIndex: 1000,
          }}
          onClick={() => setSelectedImage(null)}
        >
          <img
            src={selectedImage}
            alt="Full size"
            style={{ maxWidth: '90%', maxHeight: '90%', objectFit: 'contain' }}
          />
        </div>
      )}

      {!files.video && !files.audio && (!imagesMetadata || imagesMetadata.images.length === 0) && (
        <div className="card">No media files available yet.</div>
      )}
    </div>
  )
}

function SourcesTab({ newsData }: { newsData: RunDetailType['news_data'] }) {
  if (!newsData) {
    return <div className="card">No source data available.</div>
  }

  return (
    <div>
      <div className="card">
        <h3 style={{ marginBottom: '16px' }}>Topic</h3>
        <p>{newsData.news_text}</p>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: '16px' }}>Sources ({newsData.source_summaries.length})</h3>
        <ul className="sources-list">
          {newsData.source_summaries.map((source, index) => (
            <li key={index}>
              <div className="source-name">
                <a href={source.url} target="_blank" rel="noopener noreferrer">
                  {source.name}
                </a>
              </div>
              <div className="source-summary">
                {source.summary.substring(0, 300)}
                {source.summary.length > 300 && '...'}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function YouTubeTab({
  ytMetadata,
  ytUpload,
}: {
  ytMetadata: string | null
  ytUpload: YouTubeUpload | null
}) {
  return (
    <div>
      {ytUpload && (
        <div className="card">
          <h3 style={{ marginBottom: '16px' }}>Uploaded Video</h3>
          <div className="youtube-player">
            <iframe
              src={`https://www.youtube.com/embed/${ytUpload.video_id}`}
              title={ytUpload.title || 'YouTube video'}
              frameBorder="0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
          <div className="youtube-info">
            <p>
              <strong>Status:</strong>{' '}
              <span className="badge badge-complete">{ytUpload.status}</span>
            </p>
            {ytUpload.publish_at && (
              <p>
                <strong>Scheduled:</strong> {ytUpload.publish_at}
              </p>
            )}
            <p>
              <strong>Link:</strong>{' '}
              <a href={ytUpload.url} target="_blank" rel="noopener noreferrer">
                {ytUpload.url}
              </a>
            </p>
          </div>
        </div>
      )}

      {ytMetadata ? (
        <div className="card">
          <h3 style={{ marginBottom: '16px' }}>YouTube Metadata</h3>
          <pre className="yt-metadata">{ytMetadata}</pre>
        </div>
      ) : (
        !ytUpload && (
          <div className="card">No YouTube metadata available yet.</div>
        )
      )}
    </div>
  )
}

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const [run, setRun] = useState<RunDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabName>('dialogue')
  const [isEditingDialogue, setIsEditingDialogue] = useState(false)

  const loadRun = useCallback(async () => {
    if (!runId) return

    try {
      const data = await fetchRun(runId)
      setRun(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load run')
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    loadRun()
  }, [loadRun])

  const handleDialogueSave = (dialogue: Dialogue) => {
    if (run) {
      setRun({ ...run, dialogue })
    }
    setIsEditingDialogue(false)
  }

  if (loading) {
    return <div className="loading">Loading run details...</div>
  }

  if (error) {
    return (
      <div>
        <Link to="/" className="back-link">&larr; Back to runs</Link>
        <div className="error">Error: {error}</div>
      </div>
    )
  }

  if (!run) {
    return (
      <div>
        <Link to="/" className="back-link">&larr; Back to runs</Link>
        <div className="error">Run not found</div>
      </div>
    )
  }

  const getStatus = () => {
    const hasVideo = !!run.files.video
    const hasAudio = !!run.files.audio
    const hasDialogue = !!run.dialogue
    const hasImages = run.files.images.length > 0

    if (hasVideo && hasAudio && hasDialogue && hasImages) return 'complete'
    if (hasDialogue) return 'partial'
    return 'error'
  }

  const tabs: { name: TabName; label: string }[] = [
    { name: 'dialogue', label: 'Dialogue' },
    { name: 'media', label: 'Media' },
    { name: 'sources', label: 'Sources' },
    { name: 'youtube', label: 'YouTube' },
  ]

  return (
    <div>
      <Link to="/" className="back-link">&larr; Back to runs</Link>

      <div className="header">
        <h1>{run.dialogue?.topic_id || run.id}</h1>
        <div className="header-info">
          <span className="timestamp">{formatDate(run.timestamp)}</span>
          <StatusBadge status={getStatus()} />
        </div>
      </div>

      {run.workflow && (
        <WorkflowActions
          runId={run.id}
          workflow={run.workflow}
          onEditDialogue={() => {
            setActiveTab('dialogue')
            setIsEditingDialogue(true)
          }}
          onRefresh={loadRun}
        />
      )}

      <div className="tabs">
        {tabs.map((tab) => (
          <div
            key={tab.name}
            className={`tab ${activeTab === tab.name ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.name)}
          >
            {tab.label}
          </div>
        ))}
      </div>

      {activeTab === 'dialogue' && (
        <DialogueTab
          dialogue={run.dialogue}
          isEditing={isEditingDialogue}
          runId={run.id}
          canEdit={run.workflow?.can_edit_dialogue || false}
          onEdit={() => setIsEditingDialogue(true)}
          onSave={handleDialogueSave}
          onCancelEdit={() => setIsEditingDialogue(false)}
        />
      )}
      {activeTab === 'media' && (
        <MediaTab
          runId={run.id}
          files={run.files}
          imagesMetadata={run.images}
          onImagesUpdate={(metadata) => setRun({ ...run, images: metadata })}
        />
      )}
      {activeTab === 'sources' && <SourcesTab newsData={run.news_data} />}
      {activeTab === 'youtube' && (
        <YouTubeTab ytMetadata={run.yt_metadata} ytUpload={run.yt_upload} />
      )}
    </div>
  )
}
