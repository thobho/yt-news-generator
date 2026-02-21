import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  fetchAllPrompts,
  deletePrompt,
  setActivePrompt,
  PromptTypeInfo,
  PromptType,
} from '../api/client';
import { useTenant } from '../context/TenantContext';

export default function SettingsPage() {
  const { currentTenant } = useTenant();
  const tenantId = currentTenant?.id ?? 'pl';
  const [promptTypes, setPromptTypes] = useState<PromptTypeInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedType, setExpandedType] = useState<PromptType | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    loadPrompts();
  }, []);

  async function loadPrompts() {
    try {
      setLoading(true);
      const data = await fetchAllPrompts(tenantId);
      setPromptTypes(data.types);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load prompts');
    } finally {
      setLoading(false);
    }
  }

  async function handleSetActive(promptType: PromptType, promptId: string) {
    try {
      await setActivePrompt(tenantId, promptType, promptId);
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
      await deletePrompt(tenantId, promptType, promptId);
      await loadPrompts();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete prompt');
    }
  }

  function handleEdit(promptType: PromptType, promptId: string) {
    navigate(`/settings/prompts/${promptType}/${promptId}`);
  }

  function handleCreate(promptType: PromptType) {
    navigate(`/settings/prompts/${promptType}/new`);
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
                          {typeInfo.has_step2 && prompt.has_step3 && (
                            <span className="badge badge-step3">+Step 3</span>
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
    </div>
  );
}
