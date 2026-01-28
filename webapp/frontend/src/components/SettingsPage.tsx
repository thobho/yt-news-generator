import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  fetchAllPrompts,
  fetchPrompt,
  createPrompt,
  updatePrompt,
  deletePrompt,
  setActivePrompt,
  migratePrompts,
  PromptTypeInfo,
  PromptType,
} from '../api/client';

interface EditingPrompt {
  promptType: PromptType;
  promptId: string | null; // null for new prompt
  content: string;
  step2Content: string;
  isNew: boolean;
  newId: string;
}

export default function SettingsPage() {
  const [promptTypes, setPromptTypes] = useState<PromptTypeInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedType, setExpandedType] = useState<PromptType | null>(null);
  const [editingPrompt, setEditingPrompt] = useState<EditingPrompt | null>(null);
  const [saving, setSaving] = useState(false);
  const [migrating, setMigrating] = useState(false);

  useEffect(() => {
    loadPrompts();
  }, []);

  async function loadPrompts() {
    try {
      setLoading(true);
      const data = await fetchAllPrompts();
      setPromptTypes(data.types);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load prompts');
    } finally {
      setLoading(false);
    }
  }

  async function handleMigrate() {
    if (!confirm('This will migrate old prompts to the new structure. Continue?')) {
      return;
    }
    try {
      setMigrating(true);
      const result = await migratePrompts();
      const migrated = Object.entries(result.migrated)
        .filter(([_, prompts]) => prompts.length > 0)
        .map(([type, prompts]) => `${type}: ${prompts.join(', ')}`)
        .join('\n');
      if (migrated) {
        alert(`Migrated prompts:\n${migrated}`);
      } else {
        alert('No prompts needed migration.');
      }
      await loadPrompts();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Migration failed');
    } finally {
      setMigrating(false);
    }
  }

  async function handleSetActive(promptType: PromptType, promptId: string) {
    try {
      await setActivePrompt(promptType, promptId);
      await loadPrompts();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to set active prompt');
    }
  }

  async function handleDelete(promptType: PromptType, promptId: string) {
    if (!confirm(`Delete prompt "${promptId}"? This cannot be undone.`)) {
      return;
    }
    try {
      await deletePrompt(promptType, promptId);
      await loadPrompts();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete prompt');
    }
  }

  async function handleEdit(promptType: PromptType, promptId: string) {
    try {
      const prompt = await fetchPrompt(promptType, promptId);
      setEditingPrompt({
        promptType,
        promptId,
        content: prompt.content,
        step2Content: prompt.step2_content || '',
        isNew: false,
        newId: '',
      });
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to load prompt');
    }
  }

  function handleCreate(promptType: PromptType) {
    setEditingPrompt({
      promptType,
      promptId: null,
      content: '',
      step2Content: '',
      isNew: true,
      newId: '',
    });
  }

  async function handleSave() {
    if (!editingPrompt) return;

    const { promptType, promptId, content, step2Content, isNew, newId } = editingPrompt;
    const hasStep2 = promptTypes.find((t) => t.type === promptType)?.has_step2 ?? false;

    if (isNew && !newId.trim()) {
      alert('Please enter a prompt ID');
      return;
    }

    if (!content.trim()) {
      alert('Please enter prompt content');
      return;
    }

    try {
      setSaving(true);
      if (isNew) {
        await createPrompt(
          promptType,
          newId.trim(),
          content,
          hasStep2 ? step2Content || undefined : undefined
        );
      } else if (promptId) {
        await updatePrompt(
          promptType,
          promptId,
          content,
          hasStep2 ? step2Content || undefined : undefined
        );
      }
      setEditingPrompt(null);
      await loadPrompts();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to save prompt');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="container">
        <div className="loading">Loading prompts...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container">
        <div className="error">{error}</div>
        <button onClick={loadPrompts}>Retry</button>
      </div>
    );
  }

  return (
    <div className="settings-page">
      <div className="page-header">
        <div>
          <Link to="/" className="back-link">
            &larr; Back to Runs
          </Link>
          <h1>Prompt Settings</h1>
        </div>
        <button
          onClick={handleMigrate}
          disabled={migrating}
          className="migrate-btn"
        >
          {migrating ? 'Migrating...' : 'Migrate Old Prompts'}
        </button>
      </div>

      <div className="prompt-types">
        {promptTypes.map((typeInfo) => (
          <div key={typeInfo.type} className="prompt-type-section card">
            <div
              className="prompt-type-header"
              onClick={() =>
                setExpandedType(expandedType === typeInfo.type ? null : typeInfo.type)
              }
            >
              <div className="prompt-type-info">
                <h2>{typeInfo.label}</h2>
                <p className="prompt-type-description">{typeInfo.description}</p>
              </div>
              <div className="prompt-type-meta">
                <span className="prompt-count">
                  {typeInfo.prompts.length} prompt{typeInfo.prompts.length !== 1 ? 's' : ''}
                </span>
                <span className="expand-icon">
                  {expandedType === typeInfo.type ? '▼' : '▶'}
                </span>
              </div>
            </div>

            {expandedType === typeInfo.type && (
              <div className="prompt-type-content">
                <div className="prompt-list">
                  {typeInfo.prompts.length === 0 ? (
                    <p className="empty-state">No prompts yet. Create one to get started.</p>
                  ) : (
                    typeInfo.prompts.map((prompt) => (
                      <div
                        key={prompt.id}
                        className={`prompt-item ${prompt.is_active ? 'active' : ''}`}
                      >
                        <div className="prompt-item-info">
                          <span className="prompt-name">{prompt.name}</span>
                          {prompt.is_active && (
                            <span className="badge badge-active">Active</span>
                          )}
                          {typeInfo.has_step2 && prompt.has_step2 && (
                            <span className="badge badge-step2">+Step 2</span>
                          )}
                        </div>
                        <div className="prompt-item-actions">
                          {!prompt.is_active && (
                            <button
                              className="small"
                              onClick={() => handleSetActive(typeInfo.type, prompt.id)}
                            >
                              Set Active
                            </button>
                          )}
                          <button
                            className="small"
                            onClick={() => handleEdit(typeInfo.type, prompt.id)}
                          >
                            Edit
                          </button>
                          {!prompt.is_active && (
                            <button
                              className="small danger"
                              onClick={() => handleDelete(typeInfo.type, prompt.id)}
                            >
                              Delete
                            </button>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
                <button
                  className="create-prompt-btn"
                  onClick={() => handleCreate(typeInfo.type)}
                >
                  + Create New Prompt
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Edit/Create Dialog */}
      {editingPrompt && (
        <div className="dialog-overlay" onClick={() => setEditingPrompt(null)}>
          <div className="dialog prompt-editor-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-header">
              <h2>
                {editingPrompt.isNew ? 'Create' : 'Edit'}{' '}
                {promptTypes.find((t) => t.type === editingPrompt.promptType)?.label || 'Prompt'}
              </h2>
              <button className="dialog-close" onClick={() => setEditingPrompt(null)}>
                &times;
              </button>
            </div>
            <div className="dialog-body">
              {editingPrompt.isNew && (
                <div className="form-field">
                  <label>Prompt ID</label>
                  <input
                    type="text"
                    value={editingPrompt.newId}
                    onChange={(e) =>
                      setEditingPrompt({ ...editingPrompt, newId: e.target.value })
                    }
                    placeholder="e.g., prompt-8 or custom-name"
                  />
                  <span className="form-hint">
                    Use lowercase letters, numbers, and hyphens only
                  </span>
                </div>
              )}

              <div className="form-field">
                <label>
                  {promptTypes.find((t) => t.type === editingPrompt.promptType)?.has_step2
                    ? 'Main Prompt Content'
                    : 'Prompt Content'}
                </label>
                <textarea
                  value={editingPrompt.content}
                  onChange={(e) =>
                    setEditingPrompt({ ...editingPrompt, content: e.target.value })
                  }
                  rows={15}
                  placeholder="Enter the prompt content in Markdown format..."
                />
              </div>

              {promptTypes.find((t) => t.type === editingPrompt.promptType)?.has_step2 && (
                <div className="form-field">
                  <label>Step 2 (Refinement) Prompt</label>
                  <textarea
                    value={editingPrompt.step2Content}
                    onChange={(e) =>
                      setEditingPrompt({ ...editingPrompt, step2Content: e.target.value })
                    }
                    rows={10}
                    placeholder="Enter the refinement prompt content..."
                  />
                  <span className="form-hint">
                    Used for dialogue refinement step (optional)
                  </span>
                </div>
              )}
            </div>
            <div className="dialog-footer">
              <button onClick={() => setEditingPrompt(null)}>Cancel</button>
              <button className="primary" onClick={handleSave} disabled={saving}>
                {saving ? 'Saving...' : editingPrompt.isNew ? 'Create' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
