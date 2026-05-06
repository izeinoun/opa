from datetime import date
from typing import Optional


def normalize_tier(tier: int) -> float:
    """Normalize provider risk tier (1-5) to 0-1 range."""
    return (tier - 1) / 4.0


def amount_norm(amount: float, max_amount: float = 50_000.0) -> float:
    """Normalize a dollar amount to [0, 1], clamped at max_amount."""
    return min(amount / max_amount, 1.0)


def urgency_score(deadline: Optional[date]) -> float:
    """
    Compute urgency score based on days to deadline.
    Returns 0.5 if no deadline.
    """
    if deadline is None:
        return 0.5
    days_to_deadline = (deadline - date.today()).days
    return max(0.0, 1.0 - (days_to_deadline / 90.0))
