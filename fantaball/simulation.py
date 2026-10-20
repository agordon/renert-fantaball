"""Demo season simulator: advance a league one day at a time.

The (simulated) game logs already exist in the database; "advancing" reveals the next day's games and scores each
team's lineup AS IT STANDS THAT DAY. Points come from fantasy scoring rules stored on the league (fantaball.scoring).
Bots and auto-lineup teams re-optimize their lineup first; computer managers also make occasional free-agent pickups.
"""
import random

from root import db
from models.fantasy import Athlete, DailyScore, FantasyTeam, League, Matchup, RosterSlot
from fantaball import stats as stats_svc
from fantaball.errors import conflict
from fantaball.leagues import log_activity, teams_of
from fantaball.lineups import auto_set_lineup, owner_map, rules_of, team_slots
from fantaball.scoring import score_stat_line
from fantaball.sports import SPORTS
from fantaball.transactions import add_drop


def advance_day(league: League) -> dict:
    sport = SPORTS[league.sport.code]
    if league.status != "active":
        raise conflict("The season has not started yet")
    if league.current_day >= sport["season_days"]:
        raise conflict("The regular season is over")
    day = league.current_day + 1
    dpw = sport["days_per_week"]
    week = stats_svc.week_of_day(day, dpw)
    rules = rules_of(league)

    teams = teams_of(league.id)
    for team in teams:
        if team.is_bot:
            _bot_waiver_move(league, team, day)
        if team.is_bot or team.auto_lineup:
            auto_set_lineup(league, team)
    db.session.flush()

    log = stats_svc.game_log(league.sport_id)
    day_stats = {}      # athlete_id -> stat dict for this day
    for aid, games in log.items():
        for d, s in games:
            if d == day:
                day_stats[aid] = s
    for slot in db.session.scalars(db.select(RosterSlot).where(RosterSlot.league_id == league.id)):
        s = day_stats.get(slot.athlete_id)
        if s is not None:
            db.session.add(DailyScore(league_id=league.id, team_id=slot.team_id, athlete_id=slot.athlete_id, day=day,
                                      slot=slot.slot, points=score_stat_line(s, rules), counted=slot.slot not in ("BN", "IR")))
    db.session.flush()
    league.current_day = day
    summary = _update_matchups(league, week, day, dpw, teams)
    db.session.commit()
    stats_svc._summary_cache.clear()
    return dict(day=day, week=week, **summary)


def _team_points(league_id: int, team_id: int, first: int, last: int) -> float:
    total = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(DailyScore.points), 0.0)).where(
            DailyScore.league_id == league_id, DailyScore.team_id == team_id, DailyScore.counted.is_(True),
            DailyScore.day >= first, DailyScore.day <= last))
    return round(total, 1)


def _update_matchups(league: League, week: int, day: int, dpw: int, teams) -> dict:
    first, last = stats_svc.week_bounds(week, dpw)
    names = {t.id: t.name for t in teams}
    finals = []
    for m in db.session.scalars(db.select(Matchup).where(Matchup.league_id == league.id, Matchup.week == week)):
        m.home_score = _team_points(league.id, m.home_team_id, first, day)
        m.away_score = _team_points(league.id, m.away_team_id, first, day)
        if day == last:
            m.final = True
            winner = names[m.home_team_id] if m.home_score > m.away_score else names[m.away_team_id] if m.away_score > m.home_score else None
            msg = f"Week {week} final: {names[m.home_team_id]} {m.home_score} - {m.away_score} {names[m.away_team_id]}"
            log_activity(league.id, "matchup", msg + (f" ({winner} wins)" if winner else " (tie)"), day)
            finals.append(msg)
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
    free = db.session.scalars(db.select(Athlete).where(Athlete.sport_id == league.sport_id))
    candidates = [a for a in free if a.id not in owned and a.injury_status(day) == "HEALTHY"]
    if not candidates:
        return
    best = max(candidates, key=lambda a: summ[a.id]["proj"])
    if summ[best.id]["proj"] > summ[worst.athlete_id]["proj"] + 3:
        add_drop(league, team, best.id, worst.athlete_id)
