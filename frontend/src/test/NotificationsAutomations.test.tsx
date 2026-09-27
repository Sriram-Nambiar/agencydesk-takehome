import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { Header } from '../components/Header';
import { NotificationPopover } from '../components/NotificationPopover';
import { AutomationsModal } from '../components/AutomationsModal';
import * as AuthContextModule from '../context/AuthContext';
import { api } from '../api';

describe('Notifications and Automations Frontend Components', () => {
  const baseAuthMock = {
    token: 'fake-jwt',
    user: { id: 'u1', email: 'alex@example.com', full_name: 'Alex Rivera' },
    memberships: [
      { agency_id: 'a1', agency_name: 'Acme Digital Agency', role: 'agency_admin', client_id: null },
    ],
    activeAgency: { agency_id: 'a1', agency_name: 'Acme Digital Agency', role: 'agency_admin', client_id: null },
    activeRole: 'agency_admin' as const,
    activeClientId: null,
    isClientUser: false,
    switchAgency: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    quickLogin: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders notification bell with unread badge and opens popover', async () => {
    vi.spyOn(api, 'getUnreadNotificationCount').mockResolvedValue({ unread_count: 2 });
    vi.spyOn(api, 'getNotifications').mockResolvedValue({
      notifications: [
        {
          id: 'n1',
          agency_id: 'a1',
          user_id: 'u1',
          title: 'Task Assigned',
          message: 'Assigned to wireframes',
          type: 'task_assigned',
          is_read: false,
          created_at: new Date().toISOString(),
        },
      ],
      unread_count: 2,
    });

    render(<NotificationPopover />);

    // Unread count badge appears
    await waitFor(() => {
      expect(screen.getByText('2')).toBeInTheDocument();
    });

    // Click bell
    const bellBtn = screen.getByTitle('Notifications');
    fireEvent.click(bellBtn);

    // Dropdown is open
    expect(screen.getByTestId('notification-dropdown')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Task Assigned')).toBeInTheDocument();
      expect(screen.getByText('Assigned to wireframes')).toBeInTheDocument();
    });
  });

  it('hides Automations button from client users in Header', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      ...baseAuthMock,
      activeRole: 'client_user',
      isClientUser: true,
    } as any);

    render(<Header />);

    // Automations button must NOT be rendered for client
    expect(screen.queryByText(/⚡ Automations/)).not.toBeInTheDocument();
  });

  it('renders Automations button for agency staff and opens modal', async () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue(baseAuthMock as any);
    vi.spyOn(api, 'getAutomations').mockResolvedValue([
      {
        id: 'auto-1',
        agency_id: 'a1',
        name: 'Auto-reopen on Changes Requested',
        trigger_event: 'file_needs_changes',
        action_type: 'update_task_status',
        action_config: { target_status: 'in_progress' },
        is_enabled: true,
        created_at: new Date().toISOString(),
      },
    ]);

    render(<Header />);

    const autoBtn = screen.getByText(/⚡ Automations/);
    expect(autoBtn).toBeInTheDocument();

    fireEvent.click(autoBtn);

    // Automations modal should appear
    expect(screen.getByTestId('automations-modal')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Auto-reopen on Changes Requested')).toBeInTheDocument();
      expect(screen.getByText(/Redis Event Bus/)).toBeInTheDocument();
    });
  });
});
