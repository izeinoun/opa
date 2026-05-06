from fastapi import Header, HTTPException, Depends


async def get_current_user_role(x_user_role: str = Header(default="analyst")) -> str:
    """Dev-mode: reads X-User-Role header. Returns role string."""
    if x_user_role not in ("analyst", "supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Invalid role")
    return x_user_role


def require_supervisor(role: str = Depends(get_current_user_role)) -> str:
    if role not in ("supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Supervisor access required")
    return role


def require_admin(role: str = Depends(get_current_user_role)) -> str:
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return role
