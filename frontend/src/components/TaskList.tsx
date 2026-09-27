import React from 'react';
import type { Task, TaskStatus } from '../types';
import { useAuth } from '../context/AuthContext';

interface TaskListProps {
  tasks: Task[];
  onSelectTask: (task: Task) => void;
  onUpdateStatus: (taskId: string, status: TaskStatus) => void;
}

export const TaskList: React.FC<TaskListProps> = ({ tasks, onSelectTask, onUpdateStatus }) => {
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

  const getStatusLabel = (status: TaskStatus) => {
    switch (status) {
      case 'todo':
        return 'To Do';
      case 'in_progress':
        return 'In Progress';
      case 'review':
        return 'In Review';
      case 'done':
        return 'Done';
      default:
        return status;
    }
  };

  return (
    <div className="table-box">
      <table className="task-table">
        <thead>
          <tr>
            <th style={{ width: '140px' }}>Status</th>
            <th>Task Title</th>
            <th style={{ width: '100px' }}>Priority</th>
            <th style={{ width: '160px' }}>Assignee</th>
            <th style={{ width: '120px' }}>Due Date</th>
            <th style={{ width: '80px', textAlign: 'center' }}>Action</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr key={task.id} onClick={() => onSelectTask(task)}>
              {/* Status */}
              <td onClick={(e) => e.stopPropagation()}>
                {!isClientUser ? (
                  <select
                    className="form-select"
                    style={{ padding: '3px 6px', fontSize: '12px' }}
                    value={task.status}
                    onChange={(e) => onUpdateStatus(task.id, e.target.value as TaskStatus)}
                  >
                    <option value="todo">To Do</option>
                    <option value="in_progress">In Progress</option>
                    <option value="review">In Review</option>
                    <option value="done">Done</option>
                  </select>
                ) : (
                  <span className="badge">{getStatusLabel(task.status)}</span>
                )}
              </td>

              {/* Title & Internal Guard */}
              <td>
                <span style={{ fontWeight: 600 }}>{task.title}</span>
                {task.is_internal && (
                  <span className="badge badge-internal" style={{ marginLeft: 8 }}>
                    Internal
                  </span>
                )}
              </td>

              {/* Priority */}
              <td>
                <span className={`badge ${getPriorityClass(task.priority)}`}>
                  {task.priority}
                </span>
              </td>

              {/* Assignee */}
              <td>
                {task.assignee_name || <span style={{ color: '#5e6c84' }}>Unassigned</span>}
              </td>

              {/* Due Date */}
              <td>
                {task.due_date || <span style={{ color: '#5e6c84' }}>—</span>}
              </td>

              {/* Action */}
              <td style={{ textAlign: 'center' }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => onSelectTask(task)}
                >
                  View
                </button>
              </td>
            </tr>
          ))}

          {tasks.length === 0 && (
            <tr>
              <td colSpan={6} style={{ textAlign: 'center', padding: '30px', color: '#5e6c84' }}>
                No tasks found matching criteria.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
};
