import logging
from typing import Any, Optional
from redis_client import publish_event
from services.automations import create_notification, evaluate_and_run_automations

logger = logging.getLogger(__name__)


def dispatch_task_created(cur, agency_id: str, task: dict, creator_id: str):
    """Handle event when a new task is created."""
    task_id = str(task["id"])
    assignee_id = str(task["assignee_id"]) if task.get("assignee_id") else None

    # Notify assignee if assigned by someone else
    if assignee_id and assignee_id != str(creator_id):
        create_notification(
            cur=cur,
            agency_id=agency_id,
            user_id=assignee_id,
            title="Task Assigned",
            message=f"You have been assigned to task: '{task['title']}'",
            notif_type="task_assigned",
            entity_type="task",
            entity_id=task_id,
        )

    # Publish to Redis event stream
    publish_event(
        channel=f"agencydesk:events:{agency_id}",
        event_data={
            "event": "task_created",
            "agency_id": agency_id,
            "task_id": task_id,
            "title": task["title"],
            "status": task["status"],
            "is_internal": task["is_internal"],
        }
    )


def dispatch_task_status_changed(cur, agency_id: str, task_id: str, new_status: str, actor_id: str):
    """Handle event when task status changes."""
    cur.execute(
        """
        SELECT t.id, t.title, t.status, t.is_internal, t.assignee_id, t.project_id, p.client_id
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        WHERE t.id = %s AND t.agency_id = %s
        """,
        (task_id, agency_id)
    )
    task = cur.fetchone()
    if not task:
        return

    assignee_id = str(task["assignee_id"]) if task.get("assignee_id") else None

    # If actor is different from assignee, notify assignee
    if assignee_id and assignee_id != str(actor_id):
        create_notification(
            cur=cur,
            agency_id=agency_id,
            user_id=assignee_id,
            title="Task Status Updated",
            message=f"Task '{task['title']}' was moved to '{new_status}'",
            notif_type="task_status_changed",
            entity_type="task",
            entity_id=task_id,
        )

    # If completed and client visible, notify client contacts
    if new_status == "done" and not task["is_internal"] and task.get("client_id"):
        cur.execute(
            """
            SELECT user_id FROM agency_memberships
            WHERE agency_id = %s AND client_id = %s AND role = 'client_user' AND removed_at IS NULL
            """,
            (agency_id, task["client_id"])
        )
        for client_member in cur.fetchall():
            create_notification(
                cur=cur,
                agency_id=agency_id,
                user_id=client_member["user_id"],
                title="Task Completed",
                message=f"Deliverable '{task['title']}' has been completed.",
                notif_type="task_status_changed",
                entity_type="task",
                entity_id=task_id,
            )

    # Trigger automations
    evaluate_and_run_automations(
        cur=cur,
        agency_id=agency_id,
        trigger_event=f"task_{new_status}",
        context={
            "task_id": task_id,
            "task_title": task["title"],
            "assignee_id": assignee_id,
            "new_status": new_status,
        }
    )

    publish_event(
        channel=f"agencydesk:events:{agency_id}",
        event_data={
            "event": "task_status_changed",
            "agency_id": agency_id,
            "task_id": task_id,
            "new_status": new_status,
            "actor_id": str(actor_id),
        }
    )


def dispatch_comment_created(cur, agency_id: str, task_id: str, comment: dict, author_id: str, is_client: bool):
    """Handle event when a new comment is posted."""
    cur.execute(
        """
        SELECT t.id, t.title, t.is_internal, t.assignee_id, t.project_id, p.client_id, u.full_name as author_name
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        CROSS JOIN (SELECT full_name FROM users WHERE id = %s) u
        WHERE t.id = %s AND t.agency_id = %s
        """,
        (author_id, task_id, agency_id)
    )
    row = cur.fetchone()
    if not row:
        return

    task_title = row["title"]
    assignee_id = str(row["assignee_id"]) if row.get("assignee_id") else None
    author_name = row.get("author_name") or "User"
    comment_snippet = (comment.get("content") or "")[:80]

    # Trigger automations for comment
    evaluate_and_run_automations(
        cur=cur,
        agency_id=agency_id,
        trigger_event="comment_created",
        context={
            "task_id": task_id,
            "task_title": task_title,
            "assignee_id": assignee_id,
            "message": f"{author_name} commented: \"{comment_snippet}\"",
        }
    )

    if is_client:
        # Client commented -> notify assignee, or admins if unassigned
        recipients = [assignee_id] if assignee_id else []
        if not recipients:
            cur.execute(
                "SELECT user_id FROM agency_memberships WHERE agency_id = %s AND role = 'agency_admin' AND removed_at IS NULL",
                (agency_id,)
            )
            recipients = [str(r["user_id"]) for r in cur.fetchall()]

        for uid in recipients:
            create_notification(
                cur=cur,
                agency_id=agency_id,
                user_id=uid,
                title="Client Comment",
                message=f"{author_name} commented on '{task_title}': \"{comment_snippet}\"",
                notif_type="comment_added",
                entity_type="task",
                entity_id=task_id,
            )
    else:
        # Agency staff commented -> notify client users ONLY if comment and task are public
        if not comment.get("is_internal") and not row["is_internal"] and row.get("client_id"):
            cur.execute(
                """
                SELECT user_id FROM agency_memberships
                WHERE agency_id = %s AND client_id = %s AND role = 'client_user' AND removed_at IS NULL
                """,
                (agency_id, row["client_id"])
            )
            for client_user in cur.fetchall():
                create_notification(
                    cur=cur,
                    agency_id=agency_id,
                    user_id=client_user["user_id"],
                    title="New Update on Task",
                    message=f"{author_name} posted an update on '{task_title}'",
                    notif_type="comment_added",
                    entity_type="task",
                    entity_id=task_id,
                )

    publish_event(
        channel=f"agencydesk:events:{agency_id}",
        event_data={
            "event": "comment_created",
            "agency_id": agency_id,
            "task_id": task_id,
            "author_id": str(author_id),
            "is_client": is_client,
        }
    )


def dispatch_file_status_changed(cur, agency_id: str, file_id: str, approval_status: str, actor_id: str):
    """Handle event when file approval status is updated (e.g. approved or needs_changes)."""
    cur.execute(
        """
        SELECT f.id as file_id, f.file_name, f.is_internal, f.task_id,
               t.title as task_title, t.assignee_id, t.status as task_status,
               u.full_name as actor_name
        FROM task_files f
        JOIN tasks t ON f.task_id = t.id
        CROSS JOIN (SELECT full_name FROM users WHERE id = %s) u
        WHERE f.id = %s AND f.agency_id = %s
        """,
        (actor_id, file_id, agency_id)
    )
    row = cur.fetchone()
    if not row:
        return

    task_id = str(row["task_id"])
    file_name = row["file_name"]
    task_title = row["task_title"]
    assignee_id = str(row["assignee_id"]) if row.get("assignee_id") else None
    actor_name = row.get("actor_name") or "Client"

    trigger_event = f"file_{approval_status}"

    # Evaluate automations (e.g. file_needs_changes triggers auto-reopen to 'in_progress'!)
    executed_rules = evaluate_and_run_automations(
        cur=cur,
        agency_id=agency_id,
        trigger_event=trigger_event,
        context={
            "task_id": task_id,
            "task_title": task_title,
            "assignee_id": assignee_id,
            "file_name": file_name,
            "file_id": str(file_id),
            "message": f"{actor_name} marked '{file_name}' as {approval_status}",
        }
    )

    # General notification to assignee or agency admins
    status_label = "Changes Requested" if approval_status == "needs_changes" else "Approved"
    icon = "⚠️" if approval_status == "needs_changes" else "✅"

    recipients = [assignee_id] if assignee_id else []
    if not recipients:
        cur.execute(
            "SELECT user_id FROM agency_memberships WHERE agency_id = %s AND role = 'agency_admin' AND removed_at IS NULL",
            (agency_id,)
        )
        recipients = [str(r["user_id"]) for r in cur.fetchall()]

    for uid in recipients:
        create_notification(
            cur=cur,
            agency_id=agency_id,
            user_id=uid,
            title=f"{icon} File {status_label}",
            message=f"{actor_name} marked '{file_name}' on '{task_title}' as {approval_status}.",
            notif_type="file_status_changed",
            entity_type="file",
            entity_id=str(file_id),
        )

    publish_event(
        channel=f"agencydesk:events:{agency_id}",
        event_data={
            "event": "file_status_changed",
            "agency_id": agency_id,
            "file_id": str(file_id),
            "task_id": task_id,
            "approval_status": approval_status,
            "actor_id": str(actor_id),
            "executed_automations": executed_rules,
        }
    )
