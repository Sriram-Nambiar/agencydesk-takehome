import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Header } from './components/Header';
import { ProjectOverview } from './components/ProjectOverview';
import { TaskBoard } from './components/TaskBoard';
import { TaskList } from './components/TaskList';
import { TaskModal } from './components/TaskModal';
import { NewTaskModal } from './components/NewTaskModal';
import { LoginModal } from './components/LoginModal';
import type { Project, Task, TaskStatus } from './types';
import { api } from './api';
import './App.css';

const WorkspaceDashboard: React.FC = () => {
  const { user, activeAgency, isClientUser, isLoading: authLoading } = useAuth();

  // State
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [totalHoursLogged, setTotalHoursLogged] = useState<number>(0);
  const [isLoadingProjects, setIsLoadingProjects] = useState(false);
  const [isLoadingTasks, setIsLoadingTasks] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const projectRequest = useRef(0);
  const taskRequest = useRef(0);

  // View & Filter state
  const [viewMode, setViewMode] = useState<'board' | 'list'>('board');
  const [searchQuery, setSearchQuery] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [showInternalOnly, setShowInternalOnly] = useState(false);

  // Modal state
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [isNewTaskModalOpen, setIsNewTaskModalOpen] = useState(false);

  // Fetch Projects for Active Agency
  const loadProjects = useCallback(async () => {
    const requestId = ++projectRequest.current;
    taskRequest.current += 1;
    if (!activeAgency) {
      setProjects([]);
      setSelectedProject(null);
      setIsLoadingProjects(false);
      return;
    }

    setIsLoadingProjects(true);
    setError(null);
    try {
      const list = await api.getProjects(isClientUser);
      if (requestId !== projectRequest.current) return;
      setProjects(list);
      if (list.length > 0) {
        setSelectedProject((prev) => {
          const found = list.find((p) => p.id === prev?.id);
          return found || list[0];
        });
      } else {
        setSelectedProject(null);
      }
    } catch (err: unknown) {
      if (requestId !== projectRequest.current) return;
      setError(err instanceof Error ? err.message : 'Failed to fetch projects');
    } finally {
      if (requestId === projectRequest.current) setIsLoadingProjects(false);
    }
  }, [activeAgency, isClientUser]);

  useEffect(() => {
    // Fetching projects synchronizes this screen with the selected tenant.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadProjects();
  }, [loadProjects]);

  // Fetch Tasks for Selected Project
  const loadTasks = useCallback(async () => {
    const requestId = ++taskRequest.current;
    if (!selectedProject) {
      setTasks([]);
      setTotalHoursLogged(0);
      setIsLoadingTasks(false);
      return;
    }

    setIsLoadingTasks(true);
    try {
      const details = await api.getProjectDetails(selectedProject.id, isClientUser);
      if (requestId !== taskRequest.current) return;
      setTasks(details.tasks || []);
      setTotalHoursLogged(details.total_hours_logged || 0);
    } catch (err: unknown) {
      if (requestId !== taskRequest.current) return;
      console.warn('Failed to load tasks:', err);
    } finally {
      if (requestId === taskRequest.current) setIsLoadingTasks(false);
    }
  }, [selectedProject, isClientUser]);

  useEffect(() => {
    // Fetching tasks synchronizes this screen with the selected project.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadTasks();
  }, [loadTasks]);

  // Task Status Update
  const handleUpdateStatus = async (taskId: string, newStatus: TaskStatus) => {
    try {
      await api.updateTaskStatus(taskId, newStatus);
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, status: newStatus } : t))
      );
      if (activeTask && activeTask.id === taskId) {
        setActiveTask((prev) => (prev ? { ...prev, status: newStatus } : null));
      }
    } catch (err) {
      alert(`Could not update status: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // Task Visibility Update
  const handleUpdateVisibility = async (taskId: string, isInternal: boolean) => {
    try {
      await api.updateTaskVisibility(taskId, isInternal);
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, is_internal: isInternal } : t))
      );
      if (activeTask && activeTask.id === taskId) {
        setActiveTask((prev) => (prev ? { ...prev, is_internal: isInternal } : null));
      }
    } catch (err) {
      alert(`Could not update visibility: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // Filter Tasks
  const filteredTasks = useMemo(() => {
    return tasks.filter((t) => {
      // Search query
      if (searchQuery.trim() && !t.title.toLowerCase().includes(searchQuery.toLowerCase())) {
        return false;
      }
      // Priority filter
      if (priorityFilter !== 'all' && t.priority !== priorityFilter) {
        return false;
      }
      // Internal-only filter
      if (showInternalOnly && !t.is_internal) {
        return false;
      }
      return true;
    });
  }, [tasks, searchQuery, priorityFilter, showInternalOnly]);

  const completedCount = useMemo(
    () => tasks.filter((t) => t.status === 'done').length,
    [tasks]
  );

  // Loading state
  if (authLoading) {
    return (
      <div style={{ padding: '60px', textAlign: 'center', color: '#5e6c84' }}>
        Loading AgencyDesk...
      </div>
    );
  }

  // Not logged in
  if (!user) {
    return <LoginModal />;
  }

  return (
    <div className="app-container">
      {/* Navigation Header */}
      <Header />

      {/* Main Workspace Body */}
      <main className="main-content">
        {error && (
          <div className="error-banner">
            {error}
          </div>
        )}

        {isLoadingProjects ? (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#5e6c84' }}>
            Loading workspaces & projects...
          </div>
        ) : projects.length === 0 ? (
          <div className="box" style={{ textAlign: 'center', padding: '40px 20px' }}>
            <h3 style={{ fontSize: 16, marginBottom: 6 }}>No Projects Found</h3>
            <p style={{ color: '#5e6c84', fontSize: 13 }}>
              There are no projects created yet for <strong>{activeAgency?.agency_name}</strong>.
            </p>
          </div>
        ) : (
          <>
            {/* Project Overview Bar & Filters */}
            <ProjectOverview
              projects={projects}
              selectedProject={selectedProject}
              onSelectProject={setSelectedProject}
              viewMode={viewMode}
              onChangeViewMode={setViewMode}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              priorityFilter={priorityFilter}
              onPriorityFilterChange={setPriorityFilter}
              showInternalOnly={showInternalOnly}
              onToggleInternalOnly={setShowInternalOnly}
              onOpenNewTaskModal={() => setIsNewTaskModalOpen(true)}
              totalHoursLogged={totalHoursLogged}
              tasksCount={tasks.length}
              completedTasksCount={completedCount}
            />

            {/* Task View: Board or List */}
            {isLoadingTasks ? (
              <div style={{ textAlign: 'center', padding: '30px 0', color: '#5e6c84' }}>
                Loading tasks...
              </div>
            ) : viewMode === 'board' ? (
              <TaskBoard
                tasks={filteredTasks}
                onSelectTask={setActiveTask}
                onUpdateStatus={handleUpdateStatus}
              />
            ) : (
              <TaskList
                tasks={filteredTasks}
                onSelectTask={setActiveTask}
                onUpdateStatus={handleUpdateStatus}
              />
            )}
          </>
        )}
      </main>

      {/* Task Detail Modal */}
      {activeTask && (
        <TaskModal
          task={activeTask}
          onClose={() => setActiveTask(null)}
          onUpdateStatus={handleUpdateStatus}
          onUpdateVisibility={handleUpdateVisibility}
        />
      )}

      {/* Create New Task Modal */}
      {isNewTaskModalOpen && selectedProject && (
        <NewTaskModal
          project={selectedProject}
          onClose={() => setIsNewTaskModalOpen(false)}
          onTaskCreated={loadTasks}
        />
      )}
    </div>
  );
};

export default function App() {
  return (
    <AuthProvider>
      <WorkspaceDashboard />
    </AuthProvider>
  );
}
