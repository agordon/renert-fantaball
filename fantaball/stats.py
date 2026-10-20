"""Player statistics, fantasy points and projections.

PROJECTION FORMULA (deterministic, no look-ahead - only games on days <= `through_day` are used):

    prior(rank)  = 8 + 44 * (1 - (rank-1)/N) ** 1.7            # preseason expectation from consensus rank
    shrunk       = (prior * K + total_fantasy_points) / (games_played + K)     # K = 8 pseudo-games
    projection   = 0.7 * shrunk + 0.3 * last10_avg      (last10 only once >= 3 games are played)

Shrinking toward the prior stops a 2-game hot streak from looking like a superstar.
"""
import json

from root import db
from models.fantasy import Athlete, GameStat, ProGame
from fantaball.scoring import score_stat_line

PRIOR_GAMES = 8

_log_cache: dict = {}        # sport_id -> {athlete_id: [(day, stats), ...]}
_sched_cache: dict = {}      # sport_id -> {pro_team_id: [days]}
_summary_cache: dict = {}    # (sport_id, rules_key, day) -> summaries


def clear_cache():
    _log_cache.clear()
    _sched_cache.clear()
    _summary_cache.clear()


def game_log(sport_id: int) -> dict:
    if sport_id not in _log_cache:
        rows = db.session.execute(
            db.select(GameStat.athlete_id, GameStat.day, GameStat.stats)
            .join(Athlete, Athlete.id == GameStat.athlete_id)
            .where(Athlete.sport_id == sport_id).order_by(GameStat.day)
        ).all()
        log = {}
        for aid, day, stats in rows:
            log.setdefault(aid, []).append((day, stats))
        _log_cache[sport_id] = log
    return _log_cache[sport_id]


def team_schedule(sport_id: int) -> dict:
    """{pro_team_id: sorted list of days the team plays}"""
    if sport_id not in _sched_cache:
        sched = {}
        for g in db.session.scalars(db.select(ProGame).where(ProGame.sport_id == sport_id)):
            sched.setdefault(g.home_team_id, []).append(g.day)
            sched.setdefault(g.away_team_id, []).append(g.day)
        for days in sched.values():
            days.sort()
        _sched_cache[sport_id] = sched
    return _sched_cache[sport_id]


def prior_fpg(rank: int, n_players: int) -> float:
    return 8 + 44 * (1 - (rank - 1) / max(n_players, 1)) ** 1.7


def projection(rank: int, n_players: int, fps: list[float]) -> float:
    prior = prior_fpg(rank, n_players)
    gp = len(fps)
    shrunk = (prior * PRIOR_GAMES + sum(fps)) / (gp + PRIOR_GAMES)
    if gp >= 3:
        last10 = fps[-10:]
        return round(0.7 * shrunk + 0.3 * (sum(last10) / len(last10)), 2)
    return round(shrunk, 2)


def summaries(sport_id: int, rules: dict, through_day: int) -> dict:
    """{athlete_id: {gp, avg:{stat:..}, total, fpg, last5, proj, recent:[{day, fp}]}} for every athlete in the sport."""
    key = (sport_id, json.dumps(rules, sort_keys=True), through_day)
    if key in _summary_cache:
        return _summary_cache[key]
    log = game_log(sport_id)
    athletes = db.session.execute(db.select(Athlete.id, Athlete.rank).where(Athlete.sport_id == sport_id)).all()
    n = len(athletes)
    out = {}
    for aid, rank in athletes:
        games = [(d, s) for d, s in log.get(aid, []) if d <= through_day]
        fps = [score_stat_line(s, rules) for _, s in games]
        gp = len(games)
        avg = {}
        if gp:
            for stat in games[0][1]:
                avg[stat] = round(sum(s.get(stat, 0) for _, s in games) / gp, 2)
        out[aid] = dict(
            gp=gp, avg=avg, total=round(sum(fps), 1),
            fpg=round(sum(fps) / gp, 2) if gp else 0.0,
            last5=round(sum(fps[-5:]) / len(fps[-5:]), 2) if gp else 0.0,
            proj=projection(rank, n, fps),
            recent=[dict(day=d, fp=f) for (d, _), f in list(zip(games, fps))[-10:]],
        )
    if len(_summary_cache) > 40:
        _summary_cache.clear()
    _summary_cache[key] = out
    return out


def games_in_window(sport_id: int, pro_team_id: int, first_day: int, last_day: int) -> int:
    return sum(1 for d in team_schedule(sport_id).get(pro_team_id, []) if first_day <= d <= last_day)


def week_bounds(week: int, days_per_week: int) -> tuple[int, int]:
    return (week - 1) * days_per_week + 1, week * days_per_week


def week_of_day(day: int, days_per_week: int) -> int:
    return (max(day, 1) - 1) // days_per_week + 1
