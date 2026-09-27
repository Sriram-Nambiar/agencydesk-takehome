import React from 'react';
import type { Task, TaskStatus } from '../types';
import { useAuth } from '../context/AuthContext';

interface TaskBoardProps {
  tasks: Task[];
  onSelectTask: (task: Task) => void;
  onUpdateStatus: (taskId: string, status: TaskStatus) => void;
}

const COLUMNS: { id: TaskStatus; label: string }[] = [
  { id: 'todo', label: 'To Do' },
  { id: 'in_progress', label: 'In Progress' },
  { id: 'review', label: 'In Review' },
  { id: 'done', label: 'Done' },
];

export const TaskBoard: React.FC<TaskBoardProps> = ({ tasks, onSelectTask, onUpdateStatus }) => {
  const { isClientUser } = useAuth();

  const getPriorityClass = (priority: string) => {
    switch (priority) {
      case 'urgent':
        return 'badge-urgent';
      case 'high':
        return 'badge-high';
      case 'medium':
        return 'badge-medium';
      default:
        return 'badge-low';
    }
  };

  const getNextStatus = (current: TaskStatus): TaskStatus | null => {
    switch (current) {
      case 'todo':
        return 'in_progress';
      case 'in_progress':
        return 'review';
      case 'review':
        return 'done';
      default:
        return null;
    }
  };

  return (
    <div className="kanban-grid">
      {COLUMNS.map((col) => {
        const columnTasks = tasks.filter((t) => t.status === col.id);

        return (
          <div key={col.id} className="kanban-column">
            {/* Column Header */}
            <div className="column-header">
              <span>{col.label}</span>
              <span className="column-count">{columnTasks.length}</span>
            </div>

            {/* Task Card List */}
            {columnTasks.map((task) => {
              const nextStatus = getNextStatus(task.status);

              return (
                <div
                  key={task.id}
                  className="task-card"
                  onClick={() => onSelectTask(task)}
                >
                  {/* Top Badges */}
                  <div className="task-card-header">
                    <span className={`badge ${getPriorityClass(task.priority)}`}>
                      {task.priority}
                    </span>

                    {task.is_internal && (
                      <span className="badge badge-internal" title="Internal staff task">
                        Internal
                      </span>
                    )}
                  </div>

                  {/* Task Title */}
                  <div className="task-card-title">{task.title}</div>

                  {/* Meta: Assignee & Due Date */}
                  <div className="task-card-meta">
                    <span>
                      {task.assignee_name ? task.assignee_name.split(' ')[0] : 'Unassigned'}
                    </span>
                    {task.due_date && <span>{task.due_date}</span>}
                  </div>

                  {/* Advance Status button for agency staff */}
                  {!isClientUser && nextStatus && (
                    <div className="card-actions">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        title={`Move to ${nextStatus.replace('_', ' ')}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onUpdateStatus(task.id, nextStatus);
                        }}
                      >
                        Move → {nextStatus.replace('_', ' ')}
                      </button>
                    </div>
                  )}
                </div>
              );
            })}

            {columnTasks.length === 0 && (
              <div className="empty-col-msg">No tasks</div>
            )}
          </div>
        );
      })}
    </div>
  );
};
