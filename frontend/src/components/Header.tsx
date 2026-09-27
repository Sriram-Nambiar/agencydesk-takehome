import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { NotificationPopover } from './NotificationPopover';
import { AutomationsModal } from './AutomationsModal';

export const Header: React.FC = () => {
  const { user, memberships, activeAgency, activeRole, switchAgency, logout, quickLogin } = useAuth();
  const [isAutomationsOpen, setIsAutomationsOpen] = useState(false);

  const getRoleBadge = () => {
    if (activeRole === 'agency_admin') {
      return <span className="badge badge-admin">Agency Admin</span>;
    }
    if (activeRole === 'agency_member') {
      return <span className="badge badge-member">Agency Staff</span>;
    }
    return <span className="badge badge-client">Client Portal</span>;
  };

  return (
    <header className="app-header">
      <div className="header-left">
        <span className="brand-title">AgencyDesk</span>

        {/* Agency Switcher Dropdown */}
        {memberships.length > 0 && (
          <div className="agency-select-wrap">
            <label htmlFor="agency-select">Agency:</label>
            <select
              id="agency-select"
              value={activeAgency?.agency_id || ''}
              onChange={(e) => switchAgency(e.target.value)}
            >
              {memberships.map((m) => (
                <option key={m.agency_id} value={m.agency_id}>
                  {m.agency_name} ({m.role === 'agency_admin' ? 'Admin' : m.role === 'agency_member' ? 'Staff' : 'Client'})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div className="header-right">
        {/* Quick Demo Switcher */}
        <div className="quick-demo-strip">
          <span className="demo-title">Quick Demo:</span>
          <button
            type="button"
            className={`demo-chip ${user?.email === 'alex@example.com' ? 'active' : ''}`}
            onClick={() => quickLogin('admin')}
            title="Log in as Alex (Admin)"
          >
            Alex (Admin)
          </button>
          <button
            type="button"
            className={`demo-chip ${user?.email === 'sarah@acme.com' ? 'active' : ''}`}
            onClick={() => quickLogin('member')}
            title="Log in as Sarah (Staff)"
          >
            Sarah (Staff)
          </button>
          <button
            type="button"
            className={`demo-chip ${user?.email === 'john@starlight.com' ? 'active' : ''}`}
            onClick={() => quickLogin('client')}
            title="Log in as John (Client)"
          >
            John (Client)
          </button>
        </div>

        {/* Automations button for agency staff */}
        {activeRole !== 'client_user' && (
          <button
            type="button"
            className="btn btn-secondary btn-sm automations-trigger"
            onClick={() => setIsAutomationsOpen(true)}
            title="Configure Redis Workflow Automations"
          >
            ⚡ Automations
          </button>
        )}

        {/* Notifications Bell Popover */}
        <NotificationPopover />

        {/* User Info & Role */}
        <div className="user-info">
          <span>{user?.full_name}</span>
          {getRoleBadge()}
        </div>

        {/* Sign out */}
        <button type="button" className="btn btn-secondary btn-sm" onClick={logout}>
          Sign Out
        </button>
      </div>

      {/* Automations Config Modal */}
      <AutomationsModal
        isOpen={isAutomationsOpen}
        onClose={() => setIsAutomationsOpen(false)}
        isAdmin={activeRole === 'agency_admin'}
      />
    </header>
  );
};
