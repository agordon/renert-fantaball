"""Sim-day numbering for real seasons.

The whole engine counts "days" (1, 2, 3 ...). For real data, day 1 is Sport.season_start (a Monday) and
day N is season_start + N - 1, so a week is always Monday-Sunday. `today()` can be overridden (FLASK_FAKE_TODAY)
for tests and offline development.
"""
import os
from datetime import date, datetime, timedelta, timezone

from models.fantasy import Sport


def today() -> date:
    fake = os.environ.get("FLASK_FAKE_TODAY")
    if fake:
        return date.fromisoformat(fake)
    return datetime.now(timezone.utc).date()


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def monday_on_or_before(d: date) -> date:
    return d - timedelta(days=d.weekday())


def day_of(sport: Sport, d: date) -> int | None:
    """Day number of calendar date `d` (None if the season start is not known yet)."""
    if sport.season_start is None:
        return None
    return (d - sport.season_start).days + 1


def date_of(sport: Sport, day: int) -> date:
    return sport.season_start + timedelta(days=day - 1)


def today_day(sport: Sport) -> int:
    """Today's day number, 0 before the season starts or when the season start is unknown."""
    n = day_of(sport, today())
    return max(0, n) if n is not None else 0
