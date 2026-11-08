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
from fantaball.pool import pool_filter
from fantaball.scoring import score_float

PRIOR_GAMES = 8

_log_cache: dict = {}        # sport_id -> (signature, {athlete_id: [(day, stats), ...]})
_sched_cache: dict = {}      # sport_id -> (signature, {pro_team_id: [days]})
_summary_cache: dict = {}    # (sport_id, rules_key, day, signature) -> summaries


def _log_signature(sport_id: int):
    """Changes whenever stat rows or athletes are added / re-imported - so caches built before an import (possibly by
    another process, e.g. the sync CLI) are never served afterwards."""
    stats = tuple(db.session.execute(
        db.select(db.func.count(GameStat.id), db.func.max(GameStat.id), db.func.max(GameStat.synced_at))
        .join(Athlete, Athlete.id == GameStat.athlete_id).where(Athlete.sport_id == sport_id)).one())
    athletes = tuple(db.session.execute(
        db.select(db.func.count(Athlete.id), db.func.max(Athlete.id), db.func.max(Athlete.synced_at), db.func.sum(Athlete.rank)).where(Athlete.sport_id == sport_id)).one())
    return stats + athletes


def _sched_signature(sport_id: int):
    return tuple(db.session.execute(
        db.select(db.func.count(ProGame.id), db.func.max(ProGame.id), db.func.max(ProGame.synced_at)).where(ProGame.sport_id == sport_id)).one())


def clear_cache():
    _log_cache.clear()
    _sched_cache.clear()
    _summary_cache.clear()


def game_log(sport_id: int) -> dict:
    sig = _log_signature(sport_id)
    if sport_id not in _log_cache or _log_cache[sport_id][0] != sig:
        rows = db.session.execute(
            db.select(GameStat.athlete_id, GameStat.day, GameStat.stats)
            .join(Athlete, Athlete.id == GameStat.athlete_id)
            .where(Athlete.sport_id == sport_id).order_by(GameStat.day)
        ).all()
        log = {}
        for aid, day, stats in rows:
            log.setdefault(aid, []).append((day, stats))
        _log_cache[sport_id] = (sig, log)
    return _log_cache[sport_id][1]


def team_schedule(sport_id: int) -> dict:
    """{pro_team_id: sorted list of days the team plays}"""
    sig = _sched_signature(sport_id)
    if sport_id not in _sched_cache or _sched_cache[sport_id][0] != sig:
        sched = {}
        for g in db.session.scalars(db.select(ProGame).where(ProGame.sport_id == sport_id)):
            sched.setdefault(g.home_team_id, []).append(g.day)
            sched.setdefault(g.away_team_id, []).append(g.day)
        for days in sched.values():
            days.sort()
        _sched_cache[sport_id] = (sig, sched)
    return _sched_cache[sport_id][1]


def prior_fpg(rank: int, n_players: int) -> float:
    share = min(max(1 - (rank - 1) / max(n_players, 1), 0.0), 1.0)      # ranks beyond the pool (inactive / unranked players) floor at the minimum
    return 8 + 44 * share ** 1.7


def projection(rank: int, n_players: int, fps: list[float]) -> float:
    prior = prior_fpg(rank, n_players)
    gp = len(fps)
    shrunk = (prior * PRIOR_GAMES + sum(fps)) / (gp + PRIOR_GAMES)
    if gp >= 3:
        last10 = fps[-10:]
        return round(0.7 * shrunk + 0.3 * (sum(last10) / len(last10)), 2)
    return round(shrunk, 2)


def summaries(sport_id: int, rules: dict, through_day: int) -> dict:
    """{athlete_id: {gp, gp_scored, avg:{stat:..}, total, fpg, last5, proj, recent:[{day, fp}]}} for every athlete in the sport.

    Missing data is never turned into zero:
      * avg[stat] is the mean over games that REPORTED the stat (absent when no game did);
      * a game whose needed stats were not all reported is not scored (strict Decimal scoring) and is left out of fpg;
      * fpg / last5 are None when there is nothing to average.
    """
    log = game_log(sport_id)
    key = (sport_id, json.dumps(rules, sort_keys=True), through_day, _log_signature(sport_id))
    if key in _summary_cache:
        return _summary_cache[key]
    athletes = db.session.execute(db.select(Athlete.id, Athlete.rank).where(Athlete.sport_id == sport_id)).all()
    n = db.session.scalar(db.select(db.func.count(Athlete.id)).where(*pool_filter(sport_id))) or len(athletes)
    out = {}
    for aid, rank in athletes:
        games = [(d, s) for d, s in log.get(aid, []) if d <= through_day]
        scored = []                                   # (day, fantasy points) for games that could be scored
        for d, s in games:
            pts = score_float(s, rules)
            if pts is not None:
                scored.append((d, pts))
        fps = [f for _, f in scored]
        avg = {}
        for stat in {k for _, s in games for k in s}:
            vals = [s[stat] for _, s in games if s.get(stat) is not None]
            if vals:
                avg[stat] = round(sum(vals) / len(vals), 2)
        out[aid] = dict(
            gp=len(games), gp_scored=len(fps), avg=avg, total=round(sum(fps), 1),
            fpg=round(sum(fps) / len(fps), 2) if fps else None,
            last5=round(sum(fps[-5:]) / len(fps[-5:]), 2) if fps else None,
            proj=projection(rank, n, fps),
            recent=[dict(day=d, fp=f) for d, f in scored[-10:]],
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
