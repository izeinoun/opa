from datetime import date, datetime
from typing import Optional


def days_until(target: date) -> int:
    """Number of days from today until target date."""
    return (target - date.today()).days


def days_since(start: date) -> int:
    """Number of days elapsed since start date."""
    return (date.today() - start).days


def aging_bucket(opened_at: date) -> str:
    """
    Return aging bucket label based on how many days a case has been open.
    Buckets: "0-15d", "16-30d", "31-45d", "46-60d", "60+d"
    """
    age = days_since(opened_at)
    if age <= 15:
        return "0-15d"
    elif age <= 30:
        return "16-30d"
    elif age <= 45:
        return "31-45d"
    elif age <= 60:
        return "46-60d"
    else:
        return "60+d"


def is_overdue(deadline: Optional[date]) -> bool:
    """Return True if deadline has passed (or if no deadline, returns False)."""
    if deadline is None:
        return False
    return date.today() > deadline


def format_date(d: date) -> str:
    """Format a date as 'YYYY-MM-DD'."""
    return d.strftime("%Y-%m-%d")
