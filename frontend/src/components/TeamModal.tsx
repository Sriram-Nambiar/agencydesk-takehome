import React, { useState, useEffect, useCallback } from 'react';
import type { AgencyMember, AgencyClient } from '../types';
import { api } from '../api';

interface TeamModalProps {
  isOpen: boolean;
  onClose: () => void;
  isAdmin: boolean;
}

export const TeamModal: React.FC<TeamModalProps> = ({ isOpen, onClose, isAdmin }) => {
  const [tab, setTab] = useState<'invite' | 'directory'>('invite');
  const [members, setMembers] = useState<AgencyMember[]>([]);
  const [clients, setClients] = useState<AgencyClient[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Invite Form State
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'agency_member' | 'client_user'>('agency_member');
  const [inviteClientId, setInviteClientId] = useState('');
  const [newClientName, setNewClientName] = useState('');
  const [isNewClientForInvite, setIsNewClientForInvite] = useState(false);
  const [isSendingInvite, setIsSendingInvite] = useState(false);
  const [inviteSuccessMsg, setInviteSuccessMsg] = useState<string | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);

  // Quick Client Add State
  const [quickClientName, setQuickClientName] = useState('');
  const [isAddingClient, setIsAddingClient] = useState(false);
  const [clientError, setClientError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [membersData, clientsData] = await Promise.all([
        api.getAgencyMembers().catch(() => []),
        api.getAgencyClients().catch(() => []),
      ]);
      setMembers(membersData);
      setClients(clientsData);
      if (clientsData.length > 0) {
        setInviteClientId(clientsData[0].id);
        setIsNewClientForInvite(false);
      } else {
        setIsNewClientForInvite(true);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadData();
    }
  }, [isOpen, loadData]);

  if (!isOpen) return null;

  const handleClose = () => {
    setInviteSuccessMsg(null);
    setInviteError(null);
    setClientError(null);
    setInviteEmail('');
    setNewClientName('');
    setQuickClientName('');
    onClose();
  };

  const handleSendInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim() || isSendingInvite) return;

    setIsSendingInvite(true);
    setInviteError(null);
    setInviteSuccessMsg(null);

    try {
      let clientId: string | null = null;
      if (inviteRole === 'client_user') {
        if (isNewClientForInvite) {
          if (!newClientName.trim()) {
            setInviteError('Please specify the client name for this client user');
            setIsSendingInvite(false);
            return;
          }
          const created = await api.createClient(newClientName.trim());
          clientId = created.id;
          await loadData();
        } else {
          clientId = inviteClientId || null;
        }
        if (!clientId) {
          setInviteError('Client users must be associated with a client');
          setIsSendingInvite(false);
          return;
        }
      }

      await api.createInvite({
        email: inviteEmail.trim(),
        role: inviteRole,
        client_id: clientId,
      });

      setInviteSuccessMsg(
        `Invite successfully created for ${inviteEmail.trim()} as ${
          inviteRole === 'agency_member' ? 'Agency Staff' : 'Client User'
        }!`
      );
      setInviteEmail('');
      setNewClientName('');
    } catch (err: unknown) {
      setInviteError(err instanceof Error ? err.message : 'Failed to send invite');
    } finally {
      setIsSendingInvite(false);
    }
  };

  const handleAddQuickClient = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickClientName.trim() || isAddingClient) return;

    setIsAddingClient(true);
    setClientError(null);
    try {
      await api.createClient(quickClientName.trim());
      setQuickClientName('');
      await loadData();
    } catch (err: unknown) {
      setClientError(err instanceof Error ? err.message : 'Failed to add client');
    } finally {
      setIsAddingClient(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={handleClose} data-testid="team-modal">
      <div className="modal-window" style={{ maxWidth: 580 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-top">
          <span className="modal-top-title">👥 Team & Clients Management</span>
          <button type="button" className="modal-close-btn" onClick={handleClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          {/* Tabs */}
          <div className="modal-tabs">
            <button
              type="button"
              className={`modal-tab-btn ${tab === 'invite' ? 'active' : ''}`}
              onClick={() => setTab('invite')}
            >
              Invite User
            </button>
            <button
              type="button"
              className={`modal-tab-btn ${tab === 'directory' ? 'active' : ''}`}
              onClick={() => setTab('directory')}
            >
              Members & Clients ({members.length + clients.length})
            </button>
          </div>

          {tab === 'invite' && (
            <div>
              {inviteSuccessMsg && (
                <div style={{ background: '#e3fcef', color: '#006644', padding: '10px 14px', borderRadius: 3, marginBottom: 14, fontSize: 13, border: '1px solid #abf5d1' }}>
                  {inviteSuccessMsg}
                </div>
              )}
              {inviteError && <div className="error-banner">{inviteError}</div>}

              {!isAdmin ? (
                <div style={{ color: '#5e6c84', fontSize: 13, padding: '16px 0', textAlign: 'center' }}>
                  Only Agency Admins can create and send invites.
                </div>
              ) : (
                <form onSubmit={handleSendInvite}>
                  <div className="form-group">
                    <label className="form-label">Email Address *</label>
                    <input
                      type="email"
                      required
                      placeholder="e.g. colleague@agency.com or client@company.com"
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      className="form-input"
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Role Type *</label>
                    <select
                      value={inviteRole}
                      onChange={(e) => setInviteRole(e.target.value as 'agency_member' | 'client_user')}
                      className="form-select"
                    >
                      <option value="agency_member">Agency Staff (Can work on assigned projects, view internal notes)</option>
                      <option value="client_user">Client User (Strictly scoped to deliverables for their client company)</option>
                    </select>
                  </div>

                  {inviteRole === 'client_user' && (
                    <div className="form-group" style={{ background: '#fafbfc', border: '1px solid #dfe1e6', padding: 12, borderRadius: 3 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <label className="form-label" style={{ marginBottom: 0 }}>Assign to Client Company *</label>
                        {clients.length > 0 && (
                          <button
                            type="button"
                            style={{ background: 'none', border: 'none', color: '#0052cc', fontSize: 11.5, cursor: 'pointer', padding: 0 }}
                            onClick={() => setIsNewClientForInvite(!isNewClientForInvite)}
                          >
                            {isNewClientForInvite ? '← Select existing client' : '+ Create new client'}
                          </button>
                        )}
                      </div>

                      {isNewClientForInvite ? (
                        <input
                          type="text"
                          required
                          placeholder="Client Company Name (e.g. Acme Corp)"
                          value={newClientName}
                          onChange={(e) => setNewClientName(e.target.value)}
                          className="form-input"
                        />
                      ) : (
                        <select
                          value={inviteClientId}
                          onChange={(e) => setInviteClientId(e.target.value)}
                          className="form-select"
                        >
                          {clients.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  )}

                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
                    <button type="button" className="btn btn-secondary" onClick={handleClose}>
                      Close
                    </button>
                    <button
                      type="submit"
                      className="btn btn-primary"
                      disabled={!inviteEmail.trim() || isSendingInvite}
                    >
                      {isSendingInvite ? 'Sending...' : 'Send Invite'}
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}

          {tab === 'directory' && (
            <div>
              {isLoading ? (
                <div style={{ textAlign: 'center', padding: '24px 0', color: '#5e6c84' }}>Loading directory...</div>
              ) : (
                <>
                  {/* Agency Staff Section */}
                  <h4 style={{ fontSize: 13, fontWeight: 700, color: '#5e6c84', textTransform: 'uppercase', marginBottom: 8 }}>
                    Agency Staff ({members.length})
                  </h4>
                  <div style={{ border: '1px solid #dfe1e6', borderRadius: 3, marginBottom: 20, maxHeight: 150, overflowY: 'auto' }}>
                    {members.map((m) => (
                      <div
                        key={m.id}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '8px 12px',
                          borderBottom: '1px solid #f4f5f7',
                          fontSize: 13,
                        }}
                      >
                        <div>
                          <strong>{m.full_name}</strong>
                          <span style={{ color: '#5e6c84', marginLeft: 8, fontSize: 12 }}>{m.email}</span>
                        </div>
                        <span className={`badge ${m.role === 'agency_admin' ? 'badge-admin' : 'badge-member'}`}>
                          {m.role === 'agency_admin' ? 'Admin' : 'Staff'}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* Clients Section */}
                  <h4 style={{ fontSize: 13, fontWeight: 700, color: '#5e6c84', textTransform: 'uppercase', marginBottom: 8 }}>
                    Clients ({clients.length})
                  </h4>
                  {clientError && <div className="error-banner">{clientError}</div>}
                  <div style={{ border: '1px solid #dfe1e6', borderRadius: 3, marginBottom: 14, maxHeight: 150, overflowY: 'auto' }}>
                    {clients.length === 0 ? (
                      <div style={{ padding: '12px', color: '#5e6c84', fontSize: 12, textAlign: 'center' }}>
                        No clients added yet.
                      </div>
                    ) : (
                      clients.map((c) => (
                        <div
                          key={c.id}
                          style={{
                            padding: '8px 12px',
                            borderBottom: '1px solid #f4f5f7',
                            fontSize: 13,
                            fontWeight: 500,
                          }}
                        >
                          🏢 {c.name}
                        </div>
                      ))
                    )}
                  </div>

                  {/* Quick Add Client */}
                  {isAdmin && (
                    <form onSubmit={handleAddQuickClient} style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                      <input
                        type="text"
                        placeholder="Add new client name..."
                        value={quickClientName}
                        onChange={(e) => setQuickClientName(e.target.value)}
                        className="form-input"
                        style={{ flex: 1 }}
                      />
                      <button
                        type="submit"
                        className="btn btn-secondary"
                        disabled={!quickClientName.trim() || isAddingClient}
                      >
                        {isAddingClient ? 'Adding...' : '+ Add Client'}
                      </button>
                    </form>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
