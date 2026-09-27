import React, { useState, useEffect } from 'react';
import type { Task, TaskStatus, TaskComment, TaskFile, TimeEntry } from '../types';
import { useAuth } from '../context/AuthContext';
import { api } from '../api';

interface TaskModalProps {
  task: Task;
  onClose: () => void;
  onUpdateStatus: (taskId: string, status: TaskStatus) => void;
  onUpdateVisibility?: (taskId: string, isInternal: boolean) => void;
}

export const TaskModal: React.FC<TaskModalProps> = ({ task, onClose, onUpdateStatus, onUpdateVisibility }) => {
  const { isClientUser } = useAuth();
  const [activeTab, setActiveTab] = useState<'comments' | 'files' | 'time'>('comments');

  // Comments state
  const [comments, setComments] = useState<TaskComment[]>([]);
  const [newComment, setNewComment] = useState('');
  const [isInternalComment, setIsInternalComment] = useState(false);
  const [isSubmittingComment, setIsSubmittingComment] = useState(false);

  // Files state
  const [files, setFiles] = useState<TaskFile[]>([]);
  const [newFileName, setNewFileName] = useState('');
  const [newFileUrl, setNewFileUrl] = useState('');
  const [selectedUploadFile, setSelectedUploadFile] = useState<File | null>(null);
  const [isInternalFile, setIsInternalFile] = useState(false);
  const [showAttachForm, setShowAttachForm] = useState(false);
  const [isUploadingFile, setIsUploadingFile] = useState(false);

  // Time entries state
  const [timeEntries, setTimeEntries] = useState<TimeEntry[]>([]);
  const [logMinutes, setLogMinutes] = useState('60');
  const [logNote, setLogNote] = useState('');
  const [isLoggingTime, setIsLoggingTime] = useState(false);

  // Loading state
  const [isLoadingData, setIsLoadingData] = useState(true);

  const loadData = async () => {
    setIsLoadingData(true);
    try {
      const promises: [Promise<TaskComment[]>, Promise<TaskFile[]>, Promise<TimeEntry[]> | Promise<never[]>] = [
        api.getComments(task.id),
        api.getTaskFiles(task.id),
        !isClientUser ? api.getTaskTimeEntries(task.id) : Promise.resolve([]),
      ];

      const [c, f, t] = await Promise.all(promises);
      setComments(c);
      setFiles(f);
      setTimeEntries(t);
    } catch (err) {
      console.warn('Error loading task details:', err);
    } finally {
      setIsLoadingData(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [task.id, isClientUser]);

  // Handle Comment Submission
  const handleAddComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newComment.trim() || isSubmittingComment) return;

    try {
      setIsSubmittingComment(true);
      const added = await api.addComment(task.id, newComment.trim(), !isClientUser && isInternalComment);
      setComments((prev) => [...prev, added]);
      setNewComment('');
      setIsInternalComment(false);
    } catch (err) {
      alert(`Failed to add comment: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsSubmittingComment(false);
    }
  };

  // Handle File Upload
  const handleAddFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!newFileName.trim() && !selectedUploadFile) || isUploadingFile) return;

    try {
      setIsUploadingFile(true);
      let added: TaskFile;
      if (selectedUploadFile) {
        added = await api.uploadTaskFileMultipart(
          task.id,
          selectedUploadFile,
          !isClientUser && isInternalFile
        );
      } else {
        added = await api.uploadTaskFile(
          task.id,
          newFileName.trim(),
          newFileUrl.trim() || undefined,
          !isClientUser && isInternalFile
        );
      }
      setFiles((prev) => [added, ...prev]);
      setNewFileName('');
      setNewFileUrl('');
      setSelectedUploadFile(null);
      setIsInternalFile(false);
      setShowAttachForm(false);
    } catch (err) {
      alert(`Failed to attach deliverable: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsUploadingFile(false);
    }
  };

  // Handle File Approval
  const handleFileApproval = async (fileId: string, statusChoice: 'approved' | 'needs_changes') => {
    try {
      const updated = await api.updateFileApproval(fileId, statusChoice);
      setFiles((prev) =>
        prev.map((f) => (f.id === fileId ? { ...f, approval_status: updated.approval_status } : f))
      );
    } catch (err) {
      alert(`Failed to update deliverable status: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // Handle Log Time
  const handleLogTime = async (e: React.FormEvent) => {
    e.preventDefault();
    const mins = parseInt(logMinutes, 10);
    if (isNaN(mins) || mins <= 0 || isLoggingTime) return;

    try {
      setIsLoggingTime(true);
      const entry = await api.logTime(task.id, mins, logNote.trim());
      setTimeEntries((prev) => [entry, ...prev]);
      setLogNote('');
      setLogMinutes('60');
    } catch (err) {
      alert(`Failed to log time: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsLoggingTime(false);
    }
  };

  const totalMinutes = timeEntries.reduce((acc, curr) => acc + curr.duration_minutes, 0);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-window" onClick={(e) => e.stopPropagation()}>
        {/* Modal Top Bar */}
        <div className="modal-top">
          <span className="modal-top-title">{task.title}</span>
          <button type="button" className="modal-close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body">
          {/* Internal Task Alert */}
          {task.is_internal && (
            <div style={{ background: '#fff0b3', border: '1px solid #ffe380', padding: '8px 12px', borderRadius: 3, marginBottom: 12, fontSize: 13 }}>
              <strong>Staff Only:</strong> This task is flagged as internal and is completely invisible in the client portal.
            </div>
          )}

          {/* Quick Info Bar */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap', fontSize: 13 }}>
            <div>
              <span style={{ color: '#5e6c84', marginRight: 4 }}>Status:</span>
              {!isClientUser ? (
                <select
                  className="form-select"
                  style={{ width: 'auto', display: 'inline-block', padding: '3px 8px' }}
                  value={task.status}
                  onChange={(e) => onUpdateStatus(task.id, e.target.value as TaskStatus)}
                >
                  <option value="todo">To Do</option>
                  <option value="in_progress">In Progress</option>
                  <option value="review">In Review</option>
                  <option value="done">Done</option>
                </select>
              ) : (
                <span className="badge">{task.status.replace('_', ' ')}</span>
              )}
            </div>

            <div>
              <span style={{ color: '#5e6c84', marginRight: 4 }}>Priority:</span>
              <span className="badge">{task.priority}</span>
            </div>

            {task.assignee_name && (
              <div>
                <span style={{ color: '#5e6c84', marginRight: 4 }}>Assignee:</span>
                <strong>{task.assignee_name}</strong>
              </div>
            )}

            {task.due_date && (
              <div>
                <span style={{ color: '#5e6c84', marginRight: 4 }}>Due:</span>
                <span>{task.due_date}</span>
              </div>
            )}

            {!isClientUser && onUpdateVisibility && (
              <div>
                <span style={{ color: '#5e6c84', marginRight: 4 }}>Visibility:</span>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '2px 8px', fontSize: 12, cursor: 'pointer' }}
                  onClick={() => onUpdateVisibility(task.id, !task.is_internal)}
                  title={task.is_internal ? 'Make task visible to client' : 'Make task internal to agency'}
                >
                  {task.is_internal ? '🔒 Internal (Make Public)' : '🌐 Public (Make Internal)'}
                </button>
              </div>
            )}
          </div>

          {/* Tab Navigation */}
          <div className="modal-tabs">
            <button
              type="button"
              className={`modal-tab-btn ${activeTab === 'comments' ? 'active' : ''}`}
              onClick={() => setActiveTab('comments')}
            >
              Discussion ({comments.length})
            </button>
            <button
              type="button"
              className={`modal-tab-btn ${activeTab === 'files' ? 'active' : ''}`}
              onClick={() => setActiveTab('files')}
            >
              Deliverables ({files.length})
            </button>
            {!isClientUser && (
              <button
                type="button"
                className={`modal-tab-btn ${activeTab === 'time' ? 'active' : ''}`}
                onClick={() => setActiveTab('time')}
              >
                Time Log ({timeEntries.length})
              </button>
            )}
          </div>

          {isLoadingData ? (
            <div style={{ textAlign: 'center', padding: '24px', color: '#5e6c84' }}>
              Loading task data...
            </div>
          ) : (
            <>
              {/* TAB 1: COMMENTS */}
              {activeTab === 'comments' && (
                <div>
                  <div className="comments-list">
                    {comments.length === 0 ? (
                      <div style={{ color: '#5e6c84', fontStyle: 'italic', padding: 8 }}>
                        No comments yet. Post the first message below.
                      </div>
                    ) : (
                      comments.map((comment) => (
                        <div
                          key={comment.id}
                          className={`comment-box ${comment.is_internal ? 'internal' : ''}`}
                        >
                          <div className="comment-header">
                            <div>
                              <span className="comment-author">{comment.author_name || 'User'}</span>
                              {comment.is_internal && (
                                <span className="badge badge-internal" style={{ marginLeft: 6 }}>
                                  Internal Note
                                </span>
                              )}
                            </div>
                            <span className="comment-time">
                              {new Date(comment.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>
                          <div className="comment-text">{comment.content}</div>
                        </div>
                      ))
                    )}
                  </div>

                  {/* Add Comment Form */}
                  <form onSubmit={handleAddComment}>
                    <div className="form-group">
                      <textarea
                        rows={2}
                        className="form-textarea"
                        placeholder={isInternalComment ? 'Write an internal note (Staff only)...' : 'Write a comment...'}
                        value={newComment}
                        onChange={(e) => setNewComment(e.target.value)}
                      />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      {!isClientUser ? (
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={isInternalComment}
                            onChange={(e) => setIsInternalComment(e.target.checked)}
                          />
                          <span>Internal Note (Hidden from client)</span>
                        </label>
                      ) : (
                        <div></div>
                      )}
                      <button
                        type="submit"
                        className="btn btn-primary btn-sm"
                        disabled={!newComment.trim() || isSubmittingComment}
                      >
                        {isSubmittingComment ? 'Posting...' : 'Post Comment'}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* TAB 2: DELIVERABLES & FILES */}
              {activeTab === 'files' && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>Attached Files</span>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setShowAttachForm(!showAttachForm)}
                    >
                      {showAttachForm ? 'Cancel' : '+ Attach File'}
                    </button>
                  </div>

                  {/* Attach Form */}
                  {showAttachForm && (
                    <form onSubmit={handleAddFile} style={{ background: '#fafbfc', border: '1px solid #dfe1e6', padding: 10, borderRadius: 3, marginBottom: 12 }}>
                      <div className="form-group">
                        <label className="form-label">Upload File from Disk</label>
                        <input
                          type="file"
                          className="form-input"
                          onChange={(e) => {
                            const file = e.target.files?.[0] || null;
                            setSelectedUploadFile(file);
                            if (file && !newFileName) {
                              setNewFileName(file.name);
                            }
                          }}
                        />
                      </div>
                      <div className="form-group">
                        <label className="form-label">File Display Name</label>
                        <input
                          type="text"
                          required
                          className="form-input"
                          placeholder="e.g. design_v1.pdf"
                          value={newFileName}
                          onChange={(e) => setNewFileName(e.target.value)}
                        />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Or External File URL (Optional)</label>
                        <input
                          type="url"
                          className="form-input"
                          placeholder="https://example.com/file.pdf"
                          value={newFileUrl}
                          onChange={(e) => setNewFileUrl(e.target.value)}
                        />
                      </div>
                      {!isClientUser && (
                        <div className="form-group">
                          <label className="checkbox-label">
                            <input
                              type="checkbox"
                              checked={isInternalFile}
                              onChange={(e) => setIsInternalFile(e.target.checked)}
                            />
                            <span>Staff only file (Hidden from client)</span>
                          </label>
                        </div>
                      )}
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowAttachForm(false)}>
                          Cancel
                        </button>
                        <button type="submit" className="btn btn-primary btn-sm" disabled={(!newFileName.trim() && !selectedUploadFile) || isUploadingFile}>
                          Upload
                        </button>
                      </div>
                    </form>
                  )}

                  {/* Files List */}
                  <div className="files-list">
                    {files.length === 0 ? (
                      <div style={{ color: '#5e6c84', fontStyle: 'italic', padding: 8 }}>
                        No deliverables attached.
                      </div>
                    ) : (
                      files.map((file) => (
                        <div key={file.id} className="file-row">
                          <div>
                            <div>
                              <a
                                href={file.file_url.startsWith('/uploads/') ? '#' : api.resolveFileUrl(file.file_url)}
                                target={file.file_url.startsWith('/uploads/') ? undefined : '_blank'}
                                rel="noreferrer"
                                className="file-name"
                                onClick={file.file_url.startsWith('/uploads/') ? (event) => {
                                  event.preventDefault();
                                  void api.downloadTaskFile(file.id, file.file_name).catch((error: unknown) => {
                                    alert(error instanceof Error ? error.message : 'Could not download file');
                                  });
                                } : undefined}
                              >
                                📎 {file.file_name}
                              </a>
                              {file.is_internal && (
                                <span className="badge badge-internal" style={{ marginLeft: 6 }}>
                                  Internal
                                </span>
                              )}
                            </div>
                            <div className="file-meta">
                              Uploaded by {file.uploader_name || 'Staff'} • {new Date(file.created_at).toLocaleDateString()}
                            </div>
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span className="badge">
                              {file.approval_status === 'approved' && '✓ Approved'}
                              {file.approval_status === 'needs_changes' && '⚠ Needs Changes'}
                              {file.approval_status === 'pending' && 'Pending Review'}
                            </span>

                            {!file.is_internal && (
                              <>
                                {file.approval_status !== 'approved' && (
                                  <button
                                    type="button"
                                    className="btn btn-sm"
                                    style={{ background: '#e3fcef', color: '#006644', borderColor: '#abf5d1' }}
                                    onClick={() => handleFileApproval(file.id, 'approved')}
                                  >
                                    Approve
                                  </button>
                                )}
                                {file.approval_status !== 'needs_changes' && (
                                  <button
                                    type="button"
                                    className="btn btn-sm"
                                    style={{ background: '#ffebe6', color: '#de350b', borderColor: '#ffbdad' }}
                                    onClick={() => handleFileApproval(file.id, 'needs_changes')}
                                  >
                                    Request Changes
                                  </button>
                                )}
                              </>
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}

              {/* TAB 3: TIME TRACKING */}
              {activeTab === 'time' && !isClientUser && (
                <div>
                  <div style={{ background: '#fafbfc', border: '1px solid #dfe1e6', padding: '8px 12px', borderRadius: 3, marginBottom: 12, fontSize: 13 }}>
                    <strong>Total Logged:</strong> {(totalMinutes / 60).toFixed(1)} hrs ({totalMinutes} minutes)
                  </div>

                  {/* Log Time Form */}
                  <form onSubmit={handleLogTime} style={{ background: '#fafbfc', border: '1px solid #dfe1e6', padding: 10, borderRadius: 3, marginBottom: 12 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr auto', gap: 8, alignItems: 'flex-end' }}>
                      <div>
                        <label className="form-label">Minutes</label>
                        <input
                          type="number"
                          min="5"
                          step="5"
                          required
                          className="form-input"
                          value={logMinutes}
                          onChange={(e) => setLogMinutes(e.target.value)}
                        />
                      </div>
                      <div>
                        <label className="form-label">Work Note</label>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="e.g. Fixed database query..."
                          value={logNote}
                          onChange={(e) => setLogNote(e.target.value)}
                        />
                      </div>
                      <button type="submit" className="btn btn-primary" disabled={isLoggingTime}>
                        Log Time
                      </button>
                    </div>
                  </form>

                  {/* Time List */}
                  <div className="time-list">
                    {timeEntries.length === 0 ? (
                      <div style={{ color: '#5e6c84', fontStyle: 'italic', padding: 8 }}>
                        No time logged for this task yet.
                      </div>
                    ) : (
                      timeEntries.map((entry) => (
                        <div key={entry.id} className="time-row">
                          <div>
                            <strong>{entry.duration_minutes} mins</strong> ({(entry.duration_minutes / 60).toFixed(1)}h) — {entry.note || 'No notes'}
                          </div>
                          <div style={{ color: '#5e6c84' }}>
                            {entry.user_name || 'Staff'} • {entry.entry_date}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
