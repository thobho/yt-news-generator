import { useState } from 'react'
import { Dialogue, DialogueItem, updateDialogue } from '../api/client'

interface DialogueEditorProps {
  runId: string
  dialogue: Dialogue
  onSave: (dialogue: Dialogue) => void
  onCancel: () => void
}

export default function DialogueEditor({ runId, dialogue, onSave, onCancel }: DialogueEditorProps) {
  const [editedDialogue, setEditedDialogue] = useState<Dialogue>({ ...dialogue })
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateScriptItem = (index: number, field: keyof DialogueItem, value: string) => {
    const newScript = [...editedDialogue.script]
    newScript[index] = { ...newScript[index], [field]: value }
    setEditedDialogue({ ...editedDialogue, script: newScript })
  }

  const handleSave = async () => {
    setIsSaving(true)
    setError(null)

    try {
      await updateDialogue(runId, editedDialogue)
      onSave(editedDialogue)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="dialogue-editor">
      <div className="editor-header">
        <h3>Edit Dialogue</h3>
        <p className="editor-hint">Edit the dialogue before generating audio. Changes cannot be made after audio is generated.</p>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="editor-section">
        <label>Script</label>
        {editedDialogue.script.map((item, index) => (
          <div key={index} className="script-item-editor">
            <div className="script-item-header">
              <select
                value={item.speaker}
                onChange={(e) => updateScriptItem(index, 'speaker', e.target.value)}
                disabled={isSaving}
              >
                <option value="Adam">Adam</option>
                <option value="Bella">Bella</option>
              </select>
              {item.sources && item.sources.length > 0 && (
                <span className="source-badges">
                  {item.sources.map((src, srcIdx) => (
                    <span key={srcIdx} className="source-badge" title={src.text}>
                      {src.name}
                    </span>
                  ))}
                </span>
              )}
            </div>
            <textarea
              value={item.text}
              onChange={(e) => updateScriptItem(index, 'text', e.target.value)}
              rows={2}
              disabled={isSaving}
            />
          </div>
        ))}
      </div>

      <div className="editor-actions">
        <button onClick={onCancel} disabled={isSaving}>
          Cancel
        </button>
        <button onClick={handleSave} className="primary" disabled={isSaving}>
          {isSaving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </div>
  )
}
