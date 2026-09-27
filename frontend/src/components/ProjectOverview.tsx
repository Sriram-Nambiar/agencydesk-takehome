import React from 'react';
import type { Project } from '../types';
import { useAuth } from '../context/AuthContext';

interface ProjectOverviewProps {
  projects: Project[];
  selectedProject: Project | null;
  onSelectProject: (project: Project) => void;
  viewMode: 'board' | 'list';
  onChangeViewMode: (mode: 'board' | 'list') => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  priorityFilter: string;
  onPriorityFilterChange: (p: string) => void;
  showInternalOnly: boolean;
  onToggleInternalOnly: (val: boolean) => void;
  onOpenNewTaskModal: () => void;
  onOpenNewProjectModal?: () => void;
  totalHoursLogged?: number;
  tasksCount: number;
  completedTasksCount: number;
}

export const ProjectOverview: React.FC<ProjectOverviewProps> = ({
  projects,
  selectedProject,
  onSelectProject,
  viewMode,
  onChangeViewMode,
  searchQuery,
  onSearchChange,
  priorityFilter,
  onPriorityFilterChange,
  showInternalOnly,
  onToggleInternalOnly,
  onOpenNewTaskModal,
  onOpenNewProjectModal,
  totalHoursLogged = 0,
  tasksCount,
  completedTasksCount,
}) => {
  const { isClientUser } = useAuth();

  const progressPercent = tasksCount > 0 ? Math.round((completedTasksCount / tasksCount) * 100) : 0;

  return (
    <div className="box project-box">
      {/* Top Project Selector */}
      <div className="project-top-row">
        <div className="project-tabs">
          <span style={{ fontSize: 13, fontWeight: 700, marginRight: 4, color: '#5e6c84' }}>Project:</span>
          {projects.map((proj) => {
            const isSelected = selectedProject?.id === proj.id;
            return (
              <button
                key={proj.id}
                type="button"
                className={`project-tab ${isSelected ? 'active' : ''}`}
                onClick={() => onSelectProject(proj)}
              >
                {proj.name} {proj.client_name ? `(${proj.client_name})` : ''}
              </button>
            );
          })}
          {!isClientUser && onOpenNewProjectModal && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ marginLeft: 6 }}
              onClick={onOpenNewProjectModal}
              title="Create a new project"
            >
              + New Project
            </button>
          )}
        </div>

        {/* New Task Button (Agency only) */}
        {!isClientUser && (
          <button type="button" className="btn btn-primary" onClick={onOpenNewTaskModal}>
            + Add New Task
          </button>
        )}
      </div>

      {/* Selected Project Details */}
      {selectedProject && (
        <>
          <div className="project-details-grid">
            <div>
              <div className="detail-item-title">Client</div>
              <div className="detail-item-value">{selectedProject.client_name || 'Direct Client'}</div>
            </div>
            <div>
              <div className="detail-item-title">Task Progress</div>
              <div className="detail-item-value">
                {completedTasksCount} of {tasksCount} completed ({progressPercent}%)
              </div>
            </div>
            {!isClientUser && (
              <div>
                <div className="detail-item-title">Logged Time</div>
                <div className="detail-item-value">{totalHoursLogged} hrs</div>
              </div>
            )}
          </div>

          {/* Client Notice */}
          {isClientUser && (
            <div className="client-shield-notice">
              <strong>Client Portal:</strong> Internal tasks, draft notes, and staff time entries are protected and filtered from your view.
            </div>
          )}
        </>
      )}

      {/* Search & Filter Toolbar */}
      <div className="controls-bar">
        <div className="controls-left">
          <input
            type="text"
            className="search-box"
            placeholder="Search tasks by title..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
          />

          <select
            className="filter-select"
            value={priorityFilter}
            onChange={(e) => onPriorityFilterChange(e.target.value)}
          >
            <option value="all">All Priorities</option>
            <option value="urgent">Urgent</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          {!isClientUser && (
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={showInternalOnly}
                onChange={(e) => onToggleInternalOnly(e.target.checked)}
              />
              <span>Staff only tasks</span>
            </label>
          )}
        </div>

        <div className="controls-right">
          <button
            type="button"
            className={`btn btn-sm ${viewMode === 'board' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => onChangeViewMode('board')}
          >
            Board View
          </button>
          <button
            type="button"
            className={`btn btn-sm ${viewMode === 'list' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => onChangeViewMode('list')}
          >
            List View
          </button>
        </div>
      </div>
    </div>
  );
};
