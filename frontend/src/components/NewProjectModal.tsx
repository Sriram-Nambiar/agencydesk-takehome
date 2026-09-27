import React, { useState, useEffect } from 'react';
import type { Project, AgencyClient } from '../types';
import { api } from '../api';

interface NewProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onProjectCreated: (project: Project) => void;
}

export const NewProjectModal: React.FC<NewProjectModalProps> = ({
  isOpen,
  onClose,
  onProjectCreated,
}) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [clients, setClients] = useState<AgencyClient[]>([]);
  const [selectedClientId, setSelectedClientId] = useState('');
  const [isNewClientMode, setIsNewClientMode] = useState(false);
  const [newClientName, setNewClientName] = useState('');
  const [isLoadingClients, setIsLoadingClients] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsLoadingClients(true);

    api
      .getAgencyClients()
      .then((data) => {
        setClients(data);
        if (data.length > 0) {
          setSelectedClientId(data[0].id);
          setIsNewClientMode(false);
        } else {
          setIsNewClientMode(true);
        }
      })
      .catch((err) => {
        console.warn('Could not load clients:', err);
        setIsNewClientMode(true);
      })
      .finally(() => {
        setIsLoadingClients(false);
      });
  }, [isOpen]);

  if (!isOpen) return null;

  const handleClose = () => {
    setName('');
    setDescription('');
    setNewClientName('');
    setError(null);
    onClose();
  };

  const handleClientSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    if (val === '__new__') {
      setIsNewClientMode(true);
      setSelectedClientId('');
    } else {
      setIsNewClientMode(false);
      setSelectedClientId(val);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || isSubmitting) return;

    setIsSubmitting(true);
    setError(null);

    try {
      let clientId = selectedClientId;

      // Create client on the fly if needed
      if (isNewClientMode) {
        if (!newClientName.trim()) {
          setError('Please provide a client name');
          setIsSubmitting(false);
          return;
        }
        const createdClient = await api.createClient(newClientName.trim());
        clientId = createdClient.id;
      }

      if (!clientId) {
        setError('Please select or specify a client for this project');
        setIsSubmitting(false);
        return;
      }

      const createdProject = await api.createProject({
        name: name.trim(),
        client_id: clientId,
        description: description.trim() || undefined,
      });

      onProjectCreated(createdProject);
      handleClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create project');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={handleClose} data-testid="new-project-modal">
      <div className="modal-window" style={{ maxWidth: 520 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-top">
          <span className="modal-top-title">Create New Project</span>
          <button type="button" className="modal-close-btn" onClick={handleClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          {error && <div className="error-banner">{error}</div>}

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Project Name *</label>
              <input
                type="text"
                required
                autoFocus
                placeholder="e.g. Website Redesign, Marketing Campaign"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="form-input"
              />
            </div>

            {/* Client Selection / Creation */}
            <div className="form-group">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <label className="form-label" style={{ marginBottom: 0 }}>Client *</label>
                {clients.length > 0 && (
                  <button
                    type="button"
                    style={{ background: 'none', border: 'none', color: '#0052cc', fontSize: 12, cursor: 'pointer', padding: 0 }}
                    onClick={() => {
                      setIsNewClientMode(!isNewClientMode);
                      if (isNewClientMode && clients.length > 0) {
                        setSelectedClientId(clients[0].id);
                      }
                    }}
                  >
                    {isNewClientMode ? '← Pick existing client' : '+ Create new client'}
                  </button>
                )}
              </div>

              {isLoadingClients ? (
                <div style={{ fontSize: 12, color: '#5e6c84', padding: '6px 0' }}>Loading clients...</div>
              ) : isNewClientMode ? (
                <div>
                  <input
                    type="text"
                    required
                    placeholder="Enter new client name (e.g. Acme Corp)"
                    value={newClientName}
                    onChange={(e) => setNewClientName(e.target.value)}
                    className="form-input"
                  />
                  <div style={{ fontSize: 11.5, color: '#5e6c84', marginTop: 4 }}>
                    A new client record will be added to your agency automatically.
                  </div>
                </div>
              ) : (
                <select
                  value={selectedClientId}
                  onChange={handleClientSelectChange}
                  className="form-select"
                >
                  {clients.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                  <option value="__new__">+ Add New Client...</option>
                </select>
              )}
            </div>

            <div className="form-group">
              <label className="form-label">Description (Optional)</label>
              <textarea
                rows={3}
                placeholder="Brief project goals, key deliverables, and client notes..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="form-textarea"
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 20 }}>
              <button type="button" className="btn btn-secondary" onClick={handleClose} disabled={isSubmitting}>
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={!name.trim() || (isNewClientMode && !newClientName.trim()) || isSubmitting}
              >
                {isSubmitting ? 'Creating Project...' : 'Create Project'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
