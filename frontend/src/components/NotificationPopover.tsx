import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api';
import type { AppNotification } from '../types';

export const NotificationPopover: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  const fetchCount = async () => {
    try {
      const res = await api.getUnreadNotificationCount();
      setUnreadCount(res.unread_count);
    } catch {
      // Ignored if unauthenticated or network drop
    }
  };

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const res = await api.getNotifications();
      setNotifications(res.notifications);
      setUnreadCount(res.unread_count);
    } catch {
      // Ignored
    } finally {
      setLoading(false);
    }
  };

  // Poll for notifications periodically
  useEffect(() => {
    fetchCount();
    const interval = setInterval(fetchCount, 15000);
    return () => clearInterval(interval);
  }, []);

  // Close popover when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const toggleOpen = () => {
    if (!isOpen) {
      fetchNotifications();
    }
    setIsOpen(!isOpen);
  };

  const handleMarkAsRead = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.markNotificationAsRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      // Ignored
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await api.markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      // Ignored
    }
  };

  const getIcon = (type: string) => {
    switch (type) {
      case 'task_status_changed':
      case 'task_assigned':
        return '📋';
      case 'file_status_changed':
        return '📁';
      case 'comment_added':
        return '💬';
      case 'automation_triggered':
        return '⚡';
      default:
        return '🔔';
    }
  };

  const formatTime = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  return (
    <div className="notification-wrapper" ref={popoverRef}>
      <button
        type="button"
        className="btn-notification-bell"
        onClick={toggleOpen}
        aria-label="View notifications"
        title="Notifications"
      >
        <span className="bell-icon">🔔</span>
        {unreadCount > 0 && <span className="notification-badge">{unreadCount}</span>}
      </button>

      {isOpen && (
        <div className="notification-dropdown" data-testid="notification-dropdown">
          <div className="notification-header">
            <span className="notification-title">Notifications</span>
            {unreadCount > 0 && (
              <button
                type="button"
                className="btn-link-action"
                onClick={handleMarkAllRead}
              >
                Mark all read
              </button>
            )}
          </div>

          <div className="notification-list">
            {loading ? (
              <div className="notification-empty">Loading notifications...</div>
            ) : notifications.length === 0 ? (
              <div className="notification-empty">No notifications yet</div>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.id}
                  className={`notification-item ${!n.is_read ? 'unread' : ''}`}
                  onClick={(e) => !n.is_read && handleMarkAsRead(n.id, e)}
                >
                  <span className="item-icon">{getIcon(n.type)}</span>
                  <div className="item-content">
                    <div className="item-header-row">
                      <span className="item-title">{n.title}</span>
                      <span className="item-time">{formatTime(n.created_at)}</span>
                    </div>
                    <p className="item-message">{n.message}</p>
                  </div>
                  {!n.is_read && (
                    <span
                      className="unread-dot"
                      title="Mark as read"
                      onClick={(e) => handleMarkAsRead(n.id, e)}
                    />
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
