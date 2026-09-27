import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import type { AutomationRule } from '../types';

interface AutomationsModalProps {
  isOpen: boolean;
  onClose: () => void;
  isAdmin: boolean;
}

export const AutomationsModal: React.FC<AutomationsModalProps> = ({
  isOpen,
  onClose,
  isAdmin,
}) => {
  const [automations, setAutomations] = useState<AutomationRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const loadAutomations = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getAutomations();
      setAutomations(data);
    } catch {
      // Ignored
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      // Opening the modal synchronizes it with the agency's saved rules.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadAutomations();
    }
  }, [isOpen, loadAutomations]);

  const handleToggle = async (rule: AutomationRule) => {
    if (!isAdmin) return;
    setUpdatingId(rule.id);
    try {
      const updated = await api.updateAutomation(rule.id, {
        is_enabled: !rule.is_enabled,
      });
      setAutomations((prev) =>
        prev.map((a) => (a.id === rule.id ? updated : a))
      );
    } catch {
      // Ignored
    } finally {
      setUpdatingId(null);
    }
  };

  if (!isOpen) return null;

  const formatTrigger = (trigger: string) => {
    switch (trigger) {
      case 'file_needs_changes':
        return 'When file marked "Needs Changes"';
      case 'file_approved':
        return 'When file marked "Approved"';
      case 'comment_created':
        return 'When comment is posted';
      case 'task_done':
        return 'When task marked "Done"';
      default:
        return trigger;
    }
  };

  const formatAction = (rule: AutomationRule) => {
    if (rule.action_type === 'update_task_status') {
      const target = rule.action_config?.target_status ?? 'in_progress';
      return `Auto-update task status to "${target}"`;
    }
    if (rule.action_type === 'notify_assignee') {
      return 'Send high-priority notification to task assignee';
    }
    if (rule.action_type === 'notify_admins') {
      return 'Send instant alert notification to all agency admins';
    }
    return rule.action_type;
  };

  return (
    <div className="modal-backdrop" onClick={onClose} data-testid="automations-modal">
      <div className="modal-box modal-lg" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3>⚡ Redis-Powered Workflow Automations</h3>
            <p className="subtitle">
              Event-driven automation rules executed across tasks, comments, and client file approvals.
            </p>
          </div>
          <button type="button" className="btn-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="modal-body">
          {loading ? (
            <div className="empty-state">Loading automation rules...</div>
          ) : automations.length === 0 ? (
            <div className="empty-state">No automations configured for this agency.</div>
          ) : (
            <div className="automations-list">
              {automations.map((rule) => (
                <div key={rule.id} className="automation-card">
                  <div className="automation-info">
                    <div className="automation-title-row">
                      <span className="automation-name">{rule.name}</span>
                      <span className="badge badge-redis">Redis Event Bus</span>
                    </div>
                    <div className="automation-flow">
                      <span className="flow-trigger">⚡ {formatTrigger(rule.trigger_event)}</span>
                      <span className="flow-arrow">➔</span>
                      <span className="flow-action">⚙️ {formatAction(rule)}</span>
                    </div>
                  </div>

                  <div className="automation-toggle">
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={rule.is_enabled}
                        disabled={!isAdmin || updatingId === rule.id}
                        onChange={() => handleToggle(rule)}
                        aria-label={`Toggle ${rule.name}`}
                      />
                      <span className="slider round"></span>
                    </label>
                    <span className="toggle-label">
                      {rule.is_enabled ? 'Active' : 'Disabled'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
