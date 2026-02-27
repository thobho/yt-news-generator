import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  fetchInfoPigulaNews,
  fetchAllPrompts,
  createSeed,
  generateDialogue,
  fastUpload,
  pollTaskUntilDone,
  TaskStatus,
  InfoPigulaNewsItem,
  PromptTypeInfo,
  PromptSelections,
  ScheduleOption,
} from '../api/client'
import { useTenant } from '../context/TenantContext'

type Tab = 'browse' | 'custom'

function formatSeedText(items: InfoPigulaNewsItem[]): string {
  return items
    .map((item) => {
      let text = ''
      if (item.title) {
        text += `## ${item.title}\n\n`
      }
      text += item.content
      if (item.source.name || item.source.url) {
        text += `\n\nSource: ${item.source.name}`
        if (item.source.url) {
          text += ` (${item.source.url})`
        }
      }
      return text
    })
    .join('\n\n---\n\n')
}

export default function NewRunPage() {
  const navigate = useNavigate()
  const { currentTenant } = useTenant()
  const tenantId = currentTenant?.id ?? 'pl'
  const [activeTab, setActiveTab] = useState<Tab>('browse')

  // Browse tab state
  const [newsItems, setNewsItems] = useState<InfoPigulaNewsItem[]>([])
  const [newsTitle, setNewsTitle] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [loadingNews, setLoadingNews] = useState(true)
  const [newsError, setNewsError] = useState<string | null>(null)

  // Custom tab state
  const [customText, setCustomText] = useState('')

  // Advanced options state
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [promptTypes, setPromptTypes] = useState<PromptTypeInfo[]>([])
  const [selectedPrompts, setSelectedPrompts] = useState<PromptSelections>({})

  // Shared submit state
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitStatus, setSubmitStatus] = useState<string | null>(null)
  const [scheduleOption, setScheduleOption] = useState<ScheduleOption>('evening')

  useEffect(() => {
    setNewsItems([])
    setSelectedIds(new Set())
    setNewsError(null)
    setLoadingNews(true)

    fetchInfoPigulaNews(tenantId)
      .then((data) => {
        setNewsItems(data.items)
        setNewsTitle(data.title)
      })
      .catch((err) => {
        setNewsError(err instanceof Error ? err.message : 'Failed to fetch news')
      })
      .finally(() => setLoadingNews(false))

    fetchAllPrompts(tenantId)
      .then((data) => {
        setPromptTypes(data.types)
      })
      .catch((err) => {
        console.error('Failed to fetch prompts:', err)
      })
  }, [tenantId])

  const toggleItem = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handlePromptChange = (promptType: string, value: string) => {
    // Map prompt type to PromptSelections key
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

  const getPromptSelectionsForSubmit = (): PromptSelections | undefined => {
    // Only return if at least one prompt is selected (not null/empty)
    const hasSelections = Object.values(selectedPrompts).some(v => v !== null && v !== undefined)
    return hasSelections ? selectedPrompts : undefined
  }

  const handleSubmit = async () => {
    let seedText = ''
    if (activeTab === 'browse') {
      const selected = newsItems.filter((item) => selectedIds.has(item.id))
      if (selected.length === 0) return
      seedText = formatSeedText(selected)
    } else {
      if (!customText.trim()) return
      seedText = customText.trim()
    }

    const promptSelections = getPromptSelectionsForSubmit()

    setIsSubmitting(true)
    setSubmitError(null)
    try {
      if (activeTab === 'browse') {
        const selected = newsItems.filter((item) => selectedIds.has(item.id))
        const total = selected.length
        for (let index = 0; index < total; index += 1) {
          const item = selected[index]
          const itemSeedText = formatSeedText([item])
          const itemLabel = item.title || `item ${index + 1}`
          setSubmitStatus(`Creating seed for ${itemLabel} (${index + 1}/${total})...`)
          const { run_id } = await createSeed(tenantId, itemSeedText, promptSelections)
          setSubmitStatus(`Starting dialogue generation (${index + 1}/${total})...`)
          const { task_id } = await generateDialogue(tenantId, run_id)
          setSubmitStatus(`Generating dialogue (${index + 1}/${total})...`)
          const result = await pollTaskUntilDone(tenantId, task_id, (taskStatus: TaskStatus) => {
            if (taskStatus.message) {
              setSubmitStatus(`${taskStatus.message} (${index + 1}/${total})`)
            }
          })
          if (result.status === 'error') {
            throw new Error(result.message || 'Dialogue generation failed')
          }
        }
        setSubmitStatus('Done!')
        navigate('/')
      } else {
        setSubmitStatus('Creating seed...')
        const { run_id } = await createSeed(tenantId, seedText, promptSelections)
        setSubmitStatus('Starting dialogue generation...')
        const { task_id } = await generateDialogue(tenantId, run_id)
        setSubmitStatus('Generating dialogue (this may take a minute)...')
        const result = await pollTaskUntilDone(tenantId, task_id, (taskStatus: TaskStatus) => {
          if (taskStatus.message) {
            setSubmitStatus(taskStatus.message)
          }
        })
        if (result.status === 'error') {
          throw new Error(result.message || 'Dialogue generation failed')
        }
        setSubmitStatus('Done!')
        navigate(`/runs/${run_id}`)
      }
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to create seed')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleFastUpload = async () => {
    const selected = newsItems.filter((item) => selectedIds.has(item.id))
    if (selected.length === 0) return

    setIsSubmitting(true)
    setSubmitError(null)
    const promptSelections = getPromptSelectionsForSubmit()
    const total = selected.length

    try {
      for (let index = 0; index < total; index += 1) {
        const item = selected[index]
        const itemSeedText = formatSeedText([item])
        const itemLabel = item.title || `item ${index + 1}`

        setSubmitStatus(`Creating seed for ${itemLabel} (${index + 1}/${total})...`)
        const { run_id } = await createSeed(tenantId, itemSeedText, promptSelections)

        setSubmitStatus(`Generating dialogue (${index + 1}/${total})...`)
        const { task_id: dialogueTaskId } = await generateDialogue(tenantId, run_id)
        const dialogueResult = await pollTaskUntilDone(tenantId, dialogueTaskId, (taskStatus: TaskStatus) => {
          if (taskStatus.message) setSubmitStatus(`${taskStatus.message} (${index + 1}/${total})`)
        })
        if (dialogueResult.status === 'error') {
          throw new Error(dialogueResult.message || 'Dialogue generation failed')
        }

        setSubmitStatus(`Starting fast upload (${index + 1}/${total})...`)
        const { task_id: uploadTaskId } = await fastUpload(tenantId, run_id, scheduleOption)
        const uploadResult = await pollTaskUntilDone(tenantId, uploadTaskId, (taskStatus: TaskStatus) => {
          if (taskStatus.message) setSubmitStatus(`${taskStatus.message} (${index + 1}/${total})`)
        })
        if (uploadResult.status === 'error') {
          throw new Error(uploadResult.message || 'Fast upload failed')
        }
      }
      setSubmitStatus('Done!')
      navigate('/')
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Fast upload failed')
    } finally {
      setIsSubmitting(false)
    }
  }

  const selectedItems = newsItems.filter((item) => selectedIds.has(item.id))
  const canSubmitBrowse = selectedIds.size > 0 && !isSubmitting
  const canSubmitCustom = customText.trim().length > 0 && !isSubmitting

  // Group items by category, preserving order
  const categories: { name: string; items: InfoPigulaNewsItem[] }[] = []
  for (const item of newsItems) {
    const last = categories[categories.length - 1]
    if (last && last.name === item.category) {
      last.items.push(item)
    } else {
      categories.push({ name: item.category, items: [item] })
    }
  }

  return (
    <div>
      <Link to="/" className="back-link">
        &larr; Back to runs
      </Link>

      <div className="page-header">
        <h1>New Run</h1>
      </div>

      <div className="tabs">
        <div
          className={`tab ${activeTab === 'browse' ? 'active' : ''}`}
          onClick={() => setActiveTab('browse')}
        >
          Browse News
        </div>
        <div
          className={`tab ${activeTab === 'custom' ? 'active' : ''}`}
          onClick={() => setActiveTab('custom')}
        >
          Custom Seed
        </div>
      </div>

      {activeTab === 'browse' && (
        <div>
          {loadingNews && <div className="loading">Loading news...</div>}

          {newsError && <div className="error-message">{newsError}</div>}

          {newsTitle && <h2 className="news-release-title">{newsTitle}</h2>}

          {categories.map((cat) => (
            <div key={cat.name} className="news-category-section">
              <h3 className="news-category-title">{cat.name}</h3>
              <div className="news-grid">
                {cat.items.map((item) => (
                  <div
                    key={item.id}
                    className={`news-card ${selectedIds.has(item.id) ? 'selected' : ''}`}
                    onClick={() => toggleItem(item.id)}
                  >
                    <div className="news-card-header">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(item.id)}
                        onChange={() => toggleItem(item.id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                      {item.rating > 0 && (
                        <span className="news-card-rating" title={`${item.total_votes} votes`}>
                          {item.rating.toFixed(1)}
                        </span>
                      )}
                    </div>
                    {item.title && <h3 className="news-card-title">{item.title}</h3>}
                    <p className="news-card-content">{item.content}</p>
                    {item.source.name && (
                      <div className="news-card-source">{item.source.name}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Advanced Options */}
          <div className="advanced-options">
            <button
              type="button"
              className="advanced-toggle"
              onClick={() => setShowAdvanced(!showAdvanced)}
            >
              {showAdvanced ? '▼' : '▶'} Advanced Options
            </button>
            {showAdvanced && (
              <div className="prompt-selectors">
                {promptTypes.map((pt) => {
                  const keyMap: Record<string, keyof PromptSelections> = {
                    'dialogue': 'dialogue',
                    'image': 'image',
                    'research': 'research',
                    'yt-metadata': 'yt_metadata',
                  }
                  const key = keyMap[pt.type]
                  const currentValue = key ? selectedPrompts[key] ?? '' : ''
                  return (
                    <div key={pt.type} className="prompt-selector">
                      <label>{pt.label}</label>
                      <select
                        value={currentValue}
                        onChange={(e) => handlePromptChange(pt.type, e.target.value)}
                        disabled={isSubmitting}
                      >
                        <option value="">
                          Active ({pt.prompts.find(p => p.is_active)?.name || 'none'})
                        </option>
                        {pt.prompts.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}{p.is_active ? ' (active)' : ''}
                          </option>
                        ))}
                      </select>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {selectedIds.size > 0 && (
            <div className="selection-summary">
              <div className="selection-info">
                <strong>{selectedIds.size}</strong> item{selectedIds.size !== 1 ? 's' : ''} selected
                {selectedItems.length > 0 && (
                  <span className="selection-titles">
                    : {selectedItems.map((i) => i.title || 'Untitled').join(', ')}
                  </span>
                )}
              </div>
              <div className="selection-actions">
                <div className="schedule-options">
                  <label className="schedule-label">Schedule:</label>
                  <div className="schedule-buttons">
                    <button
                      type="button"
                      className={`schedule-btn ${scheduleOption === 'now' ? 'active' : ''}`}
                      onClick={() => setScheduleOption('now')}
                      disabled={isSubmitting}
                    >
                      Now
                    </button>
                    <button
                      type="button"
                      className={`schedule-btn ${scheduleOption === 'evening' ? 'active' : ''}`}
                      onClick={() => setScheduleOption('evening')}
                      disabled={isSubmitting}
                    >
                      Evening
                    </button>
                  </div>
                </div>
                <button
                  className="primary"
                  onClick={handleSubmit}
                  disabled={!canSubmitBrowse}
                >
                  {isSubmitting ? 'Creating...' : 'Create Seed'}
                </button>
                <button
                  className="primary upload"
                  onClick={handleFastUpload}
                  disabled={!canSubmitBrowse}
                >
                  {isSubmitting ? 'Running...' : '⚡ Fast YT Upload'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'custom' && (
        <div className="custom-seed-tab">
          <label htmlFor="customSeed">News Text (seed)</label>
          <textarea
            id="customSeed"
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
            placeholder="Enter the news topic or summary to generate a video from..."
            rows={10}
            disabled={isSubmitting}
          />

          {/* Advanced Options */}
          <div className="advanced-options">
            <button
              type="button"
              className="advanced-toggle"
              onClick={() => setShowAdvanced(!showAdvanced)}
            >
              {showAdvanced ? '▼' : '▶'} Advanced Options
            </button>
            {showAdvanced && (
              <div className="prompt-selectors">
                {promptTypes.map((pt) => {
                  const keyMap: Record<string, keyof PromptSelections> = {
                    'dialogue': 'dialogue',
                    'image': 'image',
                    'research': 'research',
                    'yt-metadata': 'yt_metadata',
                  }
                  const key = keyMap[pt.type]
                  const currentValue = key ? selectedPrompts[key] ?? '' : ''
                  return (
                    <div key={pt.type} className="prompt-selector">
                      <label>{pt.label}</label>
                      <select
                        value={currentValue}
                        onChange={(e) => handlePromptChange(pt.type, e.target.value)}
                        disabled={isSubmitting}
                      >
                        <option value="">
                          Active ({pt.prompts.find(p => p.is_active)?.name || 'none'})
                        </option>
                        {pt.prompts.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}{p.is_active ? ' (active)' : ''}
                          </option>
                        ))}
                      </select>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div className="custom-seed-actions">
            <button
              className="primary"
              onClick={handleSubmit}
              disabled={!canSubmitCustom}
            >
              {isSubmitting ? 'Creating...' : 'Create Seed'}
            </button>
          </div>
        </div>
      )}

      {submitError && <div className="error-message">{submitError}</div>}
      {submitStatus && !submitError && (
        <div className="status-message">
          <span className="spinner"></span>
          {submitStatus}
        </div>
      )}
    </div>
  )
}
