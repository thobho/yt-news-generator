import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createSeed, generateDialogue, pollTaskUntilDone } from '../api/client'

interface NewRunDialogProps {
  isOpen: boolean
  onClose: () => void
}

export default function NewRunDialog({ isOpen, onClose }: NewRunDialogProps) {
  const navigate = useNavigate()
  const [newsText, setNewsText] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!newsText.trim()) {
      setError('Please enter news text')
      return
    }

    setIsSubmitting(true)
    setError(null)
    setStatus('Creating seed...')

    try {
      // Step 1: Create seed
      const { run_id } = await createSeed(newsText.trim())
      setStatus('Starting dialogue generation...')

      // Step 2: Start dialogue generation
      const { task_id } = await generateDialogue(run_id)

      // Step 3: Poll for completion
      setStatus('Generating dialogue (this may take a minute)...')
      const result = await pollTaskUntilDone(task_id, (taskStatus) => {
        if (taskStatus.message) {
          setStatus(taskStatus.message)
        }
      })

      if (result.status === 'error') {
        throw new Error(result.message || 'Dialogue generation failed')
      }

      // Success - navigate to the new run
      setStatus('Done!')
      onClose()
      navigate(`/runs/${run_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleClose = () => {
    if (!isSubmitting) {
      setNewsText('')
      setStatus(null)
      setError(null)
      onClose()
    }
  }

  return (
    <div className="dialog-overlay" onClick={handleClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <h2>New Run</h2>
          <button className="dialog-close" onClick={handleClose} disabled={isSubmitting}>
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="dialog-body">
            <label htmlFor="newsText">News Text (seed)</label>
            <textarea
              id="newsText"
              value={newsText}
              onChange={(e) => setNewsText(e.target.value)}
              placeholder="Enter the news topic or summary to generate a video from..."
              rows={6}
              disabled={isSubmitting}
            />

            {status && (
              <div className="status-message">
                <span className="spinner"></span>
                {status}
              </div>
            )}

            {error && <div className="error-message">{error}</div>}
          </div>

          <div className="dialog-footer">
            <button type="button" onClick={handleClose} disabled={isSubmitting}>
              Cancel
            </button>
            <button type="submit" className="primary" disabled={isSubmitting || !newsText.trim()}>
              {isSubmitting ? 'Creating...' : 'Create & Generate Dialogue'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
