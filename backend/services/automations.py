import logging
from typing import Any, Optional
from redis_client import publish_event, invalidate_unread_cache

logger = logging.getLogger(__name__)


def get_active_automations(cur, agency_id: str, trigger_event: str) -> list[dict]:
    """Retrieve enabled automations for an agency matching a trigger event."""
    cur.execute(
        """
        SELECT id, agency_id, name, trigger_event, action_type, action_config, is_enabled
        FROM automations
        WHERE agency_id = %s AND trigger_event = %s AND is_enabled = TRUE
        """,
        (agency_id, trigger_event)
    )
    return cur.fetchall() or []


def create_notification(
    cur,
    agency_id: str,
    user_id: str,
    title: str,
    message: str,
    notif_type: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> dict:
    """Insert a notification into DB, invalidate Redis cache, and publish real-time notification."""
    cur.execute(
        """
        INSERT INTO notifications (agency_id, user_id, title, message, type, entity_type, entity_id, is_read)
        VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE)
        RETURNING *
        """,
        (agency_id, user_id, title, message, notif_type, entity_type, entity_id)
    )
    notif = cur.fetchone()

    # Redis invalidation and real-time publish
    invalidate_unread_cache(agency_id, str(user_id))
    publish_event(
        channel=f"agencydesk:notify:{user_id}",
        event_data={
            "type": "new_notification",
            "agency_id": str(agency_id),
            "user_id": str(user_id),
            "notification": {
                "id": str(notif["id"]),
                "title": notif["title"],
                "message": notif["message"],
                "type": notif["type"],
                "entity_type": notif["entity_type"],
                "entity_id": str(notif["entity_id"]) if notif["entity_id"] else None,
                "is_read": False,
                "created_at": str(notif["created_at"]),
            }
        }
    )
    return notif


def evaluate_and_run_automations(cur, agency_id: str, trigger_event: str, context: dict[str, Any]) -> list[dict]:
    """
    Evaluate active automation rules for a given trigger event and execute actions.
    Returns a list of executed automation results.
    """
    rules = get_active_automations(cur, agency_id, trigger_event)
    executed = []

    for rule in rules:
        action_type = rule["action_type"]
        action_config = rule.get("action_config") or {}
        rule_name = rule["name"]

        try:
            if action_type == "update_task_status":
                target_status = action_config.get("target_status", "in_progress")
                task_id = context.get("task_id")
                if task_id:
                    cur.execute(
                        "UPDATE tasks SET status = %s WHERE id = %s AND agency_id = %s RETURNING id, title, status, assignee_id",
                        (target_status, task_id, agency_id)
                    )
                    updated_task = cur.fetchone()
                    if updated_task:
                        executed.append({
                            "rule_id": str(rule["id"]),
                            "rule_name": rule_name,
                            "action": f"Updated task status to {target_status}",
                            "task_id": str(task_id),
                        })

                        # If task has an assignee, notify them of the automated status change
                        if updated_task.get("assignee_id"):
                            create_notification(
                                cur=cur,
                                agency_id=agency_id,
                                user_id=updated_task["assignee_id"],
                                title=f"⚡ Automation: Task Status Updated",
                                message=f"Task '{updated_task['title']}' was automatically moved to '{target_status}' by rule '{rule_name}'.",
                                notif_type="automation_triggered",
                                entity_type="task",
                                entity_id=str(task_id),
                            )

            elif action_type == "notify_assignee":
                task_id = context.get("task_id")
                assignee_id = context.get("assignee_id")
                task_title = context.get("task_title", "Task")
                details = context.get("message", "An event occurred on this task.")

                if not assignee_id and task_id:
                    cur.execute("SELECT assignee_id, title FROM tasks WHERE id = %s AND agency_id = %s", (task_id, agency_id))
                    t_row = cur.fetchone()
                    if t_row:
                        assignee_id = t_row.get("assignee_id")
                        task_title = t_row.get("title", task_title)

                if assignee_id:
                    create_notification(
                        cur=cur,
                        agency_id=agency_id,
                        user_id=assignee_id,
                        title=f"⚡ Automation: {task_title}",
                        message=details,
                        notif_type="automation_triggered",
                        entity_type="task",
                        entity_id=str(task_id) if task_id else None,
                    )
                    executed.append({
                        "rule_id": str(rule["id"]),
                        "rule_name": rule_name,
                        "action": f"Notified assignee {assignee_id}",
                    })

            elif action_type == "notify_admins":
                cur.execute(
                    "SELECT user_id FROM agency_memberships WHERE agency_id = %s AND role = 'agency_admin' AND removed_at IS NULL",
                    (agency_id,)
                )
                admin_rows = cur.fetchall()
                msg = context.get("message", f"Automation alert: {rule_name} triggered.")
                for admin in admin_rows:
                    create_notification(
                        cur=cur,
                        agency_id=agency_id,
                        user_id=admin["user_id"],
                        title=f"⚡ Automation Alert: {rule_name}",
                        message=msg,
                        notif_type="automation_triggered",
                        entity_type=context.get("entity_type"),
                        entity_id=context.get("entity_id"),
                    )
                executed.append({
                    "rule_id": str(rule["id"]),
                    "rule_name": rule_name,
                    "action": f"Notified {len(admin_rows)} agency admins",
                })

        except Exception as exc:
            logger.error(f"Error executing automation rule {rule.get('id')}: {exc}")

    return executed
