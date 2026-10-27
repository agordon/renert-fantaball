"""Advance a league one day at a time and keep matchup totals up to date.

Two sources of daily points, same downstream logic:
  * DEMO leagues (sport.data_source == "demo"): the simulated game logs already exist; "advancing" reveals the next day
    (commissioner button). Points = fantaball.scoring.score_stat_line over the day's stat line.
  * REAL leagues: advanced automatically by the data pipeline once every game of a day is final and its box score is
    imported (fantaball/nba/league_sync.py). Points come from PlayerFantasyScore (persisted, rule-set aware).
Each team's lineup AS IT STANDS that day is snapshotted in DailyScore; bots / auto-lineup teams re-optimize first.
"""
import random

from root import db
from models.fantasy import DailyScore, FantasyTeam, League, Matchup, RosterSlot, TeamPeriodScore, utcnow
from fantaball import stats as stats_svc
from fantaball.errors import conflict
from fantaball.leagues import log_activity, teams_of
from fantaball.lineups import auto_set_lineup, owner_map, rules_of, team_slots
from fantaball.pool import pool_query
from fantaball.scoring import score_stat_line
from fantaball.sports import SPORTS
from fantaball.transactions import add_drop


def is_demo(league: League) -> bool:
    return league.sport.data_source == "demo"


def week_of(league: League, day: int) -> int:
    return stats_svc.week_of_day(day, SPORTS[league.sport.code]["days_per_week"])


def _day_points(league: League, day: int) -> dict[int, float]:
    """{athlete_id: fantasy points} for every athlete who played on `day`."""
    if is_demo(league):
        rules = rules_of(league)
        out = {}
        for aid, games in stats_svc.game_log(league.sport_id).items():
            for d, s in games:
                if d == day:
                    out[aid] = score_stat_line(s, rules)
        return out
    from fantaball.nba import scoring_service
    return scoring_service.points_for_day(league.scoring.ruleset_id, day)


def advance_day(league: League) -> dict:
    sport = SPORTS[league.sport.code]
    if league.status != "active":
        raise conflict("The season has not started yet")
    if league.current_day >= sport["season_days"]:
        raise conflict("The regular season is over")
    day = league.current_day + 1
    week = week_of(league, day)

    teams = teams_of(league.id)
    for team in teams:
        if team.is_bot:
            _bot_waiver_move(league, team, day)
        if team.is_bot or team.auto_lineup:
            auto_set_lineup(league, team)
    db.session.flush()

    points = _day_points(league, day)
    for slot in db.session.scalars(db.select(RosterSlot).where(RosterSlot.league_id == league.id)):
        if slot.athlete_id in points:
            db.session.add(DailyScore(league_id=league.id, team_id=slot.team_id, athlete_id=slot.athlete_id, day=day, slot=slot.slot,
                                      points=points[slot.athlete_id], counted=slot.slot not in ("BN", "IR")))
    db.session.flush()
    league.current_day = day
    summary = recompute_week(league, week)
    db.session.commit()
    return dict(day=day, week=week, **summary)


def _team_points(league_id: int, team_id: int, first: int, last: int) -> float:
    total = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(DailyScore.points), 0.0)).where(
            DailyScore.league_id == league_id, DailyScore.team_id == team_id, DailyScore.counted.is_(True),
            DailyScore.day >= first, DailyScore.day <= last))
    return round(total, 1)


def recompute_week(league: League, week: int) -> dict:
    """(Re)calculate every matchup of `week` from stored daily scores. Safe to repeat - this is how corrections reach
    finalized weeks. A week is final once the league has played its last day."""
    dpw = SPORTS[league.sport.code]["days_per_week"]
    first, last = stats_svc.week_bounds(week, dpw)
    upto = min(league.current_day, last)
    names = {t.id: t.name for t in teams_of(league.id)}
    finals = []
    now = utcnow()
    for m in db.session.scalars(db.select(Matchup).where(Matchup.league_id == league.id, Matchup.week == week)):
        was_final = m.final
        m.home_score = _team_points(league.id, m.home_team_id, first, upto)
        m.away_score = _team_points(league.id, m.away_team_id, first, upto)
        if league.current_day >= last:
            m.final = True
            m.finalized_at = m.finalized_at or now
            if not was_final:
                winner = names[m.home_team_id] if m.home_score > m.away_score else names[m.away_team_id] if m.away_score > m.home_score else None
                msg = f"Week {week} final: {names[m.home_team_id]} {m.home_score} - {m.away_score} {names[m.away_team_id]}"
                log_activity(league.id, "matchup", msg + (f" ({winner} wins)" if winner else " (tie)"), last)
                finals.append(msg)
        db.session.flush()
        for team_id, score in ((m.home_team_id, m.home_score), (m.away_team_id, m.away_score)):
            tps = db.session.scalar(db.select(TeamPeriodScore).where(TeamPeriodScore.matchup_id == m.id, TeamPeriodScore.team_id == team_id))
            if tps is None:
                db.session.add(TeamPeriodScore(league_id=league.id, matchup_id=m.id, team_id=team_id, week=week, points=score, final=m.final, calculated_at=now))
            else:
                tps.points, tps.final, tps.calculated_at = score, m.final, now
    return dict(week_finalized=bool(finals))


def advance_days(league: League, n: int) -> dict:
    last = {}
    for _ in range(n):
        if league.current_day >= SPORTS[league.sport.code]["season_days"]:
            break
        last = advance_day(league)
    return last


def _bot_waiver_move(league: League, team: FantasyTeam, day: int):
    """Every few days a computer manager swaps its worst bench player for a clearly better free agent."""
    if (day + team.id) % 5 != 0:
        return
    rng = random.Random(f"waiver-{league.id}-{team.id}-{day}")
    if rng.random() > 0.6:
        return
    summ = stats_svc.summaries(league.sport_id, rules_of(league), day - 1)
    owned = owner_map(league.id)
    slots = team_slots(team.id)
    bench = [s for s in slots if s.slot == "BN"]
    if not bench:
        return
    worst = min(bench, key=lambda s: summ[s.athlete_id]["proj"])
    free = db.session.scalars(pool_query(league.sport_id))
    candidates = [a for a in free if a.id not in owned and a.injury_status(day) == "HEALTHY"]
    if not candidates:
        return
    best = max(candidates, key=lambda a: summ[a.id]["proj"])
    if summ[best.id]["proj"] > summ[worst.athlete_id]["proj"] + 3:
        add_drop(league, team, best.id, worst.athlete_id)
