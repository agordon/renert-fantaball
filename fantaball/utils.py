from datetime import datetime


def seconds_left(deadline: datetime | None) -> int | None:
    """Whole seconds until a (naive UTC) deadline, never negative; None when there is no clock."""
    if deadline is None:
        return None
    from models.fantasy import utcnow
    return max(0, int((deadline - utcnow()).total_seconds()))
