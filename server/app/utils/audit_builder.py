from typing import Optional


def build_status_transition_entry(
    case,
    to_status: str,
    user_id: Optional[int],
    notes: Optional[str],
) -> dict:
    """
    Build a dict suitable for AuditLog creation for a status transition.
    """
    return {
        "case_id": case.id,
        "user_id": user_id,
        "action": "STATUS_TRANSITION",
        "from_status": case.status,
        "to_status": to_status,
        "notes": notes,
        "metadata_json": None,
    }


def build_action_entry(
    case_id: int,
    user_id: Optional[int],
    action: str,
    notes: Optional[str],
) -> dict:
    """
    Build a dict suitable for AuditLog creation for a generic action.
    """
    return {
        "case_id": case_id,
        "user_id": user_id,
        "action": action,
        "from_status": None,
        "to_status": None,
        "notes": notes,
        "metadata_json": None,
    }
