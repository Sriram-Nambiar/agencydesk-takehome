from typing import Any
from psycopg2.extras import Json


def record_audit_event(
    cur,
    *,
    agency_id: str,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Write a minimal audit record in the same transaction as the change."""
    cur.execute(
        """INSERT INTO audit_events
           (agency_id, actor_id, action, entity_type, entity_id, details)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (agency_id, actor_id, action, entity_type, entity_id, Json(details or {})),
    )
