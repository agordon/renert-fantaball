"""Connect imported real data to fantasy leagues: advance leagues over completed days and re-score after corrections."""
from root import db
from models.fantasy import DailyScore, League, ProGame, Sport
from fantaball import simulation, timeline
from fantaball.nba import scoring_service

POSTPONED_AFTER_DAYS = 3        # a game still 'scheduled' this long after its date is treated as postponed, not blocking


def completed_through_day(sport: Sport) -> int:
    """Highest day D such that every counted game on days 1..D is final with its box score imported.

    Days with no games count as complete once a later day has games (so the schedule is known to cover them).
    Today and the future are never scored; stale 'scheduled' games (postponed) do not block progress.
    """
    today_day = timeline.today_day(sport)
    if today_day <= 0:
        return 0
    rows = db.session.execute(db.select(ProGame.day, ProGame.status, ProGame.stats_synced_at, ProGame.game_date).where(
        ProGame.sport_id == sport.id, ProGame.postseason.is_(False), ProGame.day >= 1)).all()
    if not rows:
        return 0
    last_scheduled = max(r.day for r in rows)
    by_day: dict[int, bool] = {}
    for r in rows:
        postponed = r.status == "scheduled" and (timeline.today() - r.game_date).days >= POSTPONED_AFTER_DAYS
        ok = postponed or (r.status == "final" and r.stats_synced_at is not None)
        by_day[r.day] = by_day.get(r.day, True) and ok
    done = 0
    for day in range(1, min(today_day, last_scheduled) + 1):
        if by_day.get(day, True):
            done = day
        else:
            break
    return done


def advance_leagues(sport: Sport) -> int:
    """Score every active league of this sport for each newly completed day. Returns days advanced (all leagues)."""
    target = completed_through_day(sport)
    advanced = 0
    for league in db.session.scalars(db.select(League).where(League.sport_id == sport.id, League.status == "active")):
        while league.current_day < target and league.current_day < sport_season_days(league):
            simulation.advance_day(league)
            advanced += 1
    return advanced


def sport_season_days(league: League) -> int:
    from fantaball.sports import SPORTS
    return SPORTS[league.sport.code]["season_days"]


def rescore_leagues(sport: Sport, days: set[int] | None):
    """After stat corrections: refresh stored lineup points for already-scored days and recompute matchup totals.

    `days=None` re-checks every scored day. Finalized weeks are recalculated too (corrections can change history)."""
    for league in db.session.scalars(db.select(League).where(League.sport_id == sport.id, League.status == "active")):
        ruleset_id = league.scoring.ruleset_id
        if ruleset_id is None:
            continue
        scored = db.select(DailyScore.day).where(DailyScore.league_id == league.id).distinct()
        target_days = sorted(d for d in db.session.scalars(scored) if days is None or d in days)
        weeks = set()
        for day in target_days:
            pts = scoring_service.points_for_day(ruleset_id, day)
            for row in db.session.scalars(db.select(DailyScore).where(DailyScore.league_id == league.id, DailyScore.day == day)):
                new = round(pts.get(row.athlete_id, row.points), 2)
                if new != row.points:
                    row.points = new
                    weeks.add(simulation.week_of(league, day))
        db.session.flush()
        for week in sorted(weeks):
            simulation.recompute_week(league, week)
        db.session.commit()
