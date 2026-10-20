"""Matchup read-models: score breakdown per player/day, projected final score, season score history."""
from root import db
from models.fantasy import Athlete, DailyScore, FantasyTeam, League, Matchup, RosterSlot
from fantaball import stats as stats_svc
from fantaball.lineups import rules_of, team_slots
from fantaball.sports import SPORTS


def week_info(league: League, week: int | None = None) -> dict:
    dpw = SPORTS[league.sport.code]["days_per_week"]
    cur_week = stats_svc.week_of_day(league.current_day + 1, dpw)
    week = week or cur_week
    first, last = stats_svc.week_bounds(week, dpw)
    return dict(week=week, first_day=first, last_day=last, current_week=cur_week, dpw=dpw)


def find_matchup(league_id: int, team_id: int, week: int) -> Matchup | None:
    return db.session.scalar(db.select(Matchup).where(
        Matchup.league_id == league_id, Matchup.week == week, db.or_(Matchup.home_team_id == team_id, Matchup.away_team_id == team_id)))


def team_side(league: League, team: FantasyTeam, info: dict, summ: dict) -> dict:
    """Per-player breakdown for one team in one week: daily points, games left, projection for the rest of the week."""
    first, last, day = info["first_day"], info["last_day"], league.current_day
    scores = list(db.session.scalars(db.select(DailyScore).where(
        DailyScore.league_id == league.id, DailyScore.team_id == team.id, DailyScore.day >= first, DailyScore.day <= last)))
    by_ath = {}
    for s in scores:
        by_ath.setdefault(s.athlete_id, []).append(s)
    ath_ids = set(by_ath) | {s.athlete_id for s in team_slots(team.id)}
    athletes = {a.id: a for a in db.session.scalars(db.select(Athlete).where(Athlete.id.in_(ath_ids)))}
    cur_slot = {s.athlete_id: s.slot for s in team_slots(team.id)}

    players = []
    for aid in ath_ids:
        a = athletes[aid]
        rows = by_ath.get(aid, [])
        counted = sum(r.points for r in rows if r.counted)
        bench_pts = sum(r.points for r in rows if not r.counted)
        left = stats_svc.games_in_window(league.sport_id, a.pro_team_id, max(first, day + 1), last)
        slot = cur_slot.get(aid)
        proj_rest = round(summ[aid]["proj"] * left, 1) if slot and slot not in ("BN", "IR") and info["week"] >= info["current_week"] else 0.0
        players.append(dict(
            athlete_id=aid, name=a.name, positions=a.positions, team=a.pro_team.abbr, slot=slot, on_roster=slot is not None,
            points=round(counted, 1), bench_points=round(bench_pts, 1), games_played=len(rows), games_left=left, proj_rest=proj_rest,
            injury=a.injury_status(day + 1),
            daily={r.day: round(r.points, 1) for r in rows if r.counted},
        ))
    order = {s: i for i, (s, _) in enumerate(league.roster_config)}
    players.sort(key=lambda p: (order.get(p["slot"], 99), -p["points"]))
    points = round(sum(p["points"] for p in players), 1)
    projected = round(points + sum(p["proj_rest"] for p in players), 1)
    bench_total = round(sum(p["bench_points"] for p in players), 1)
    daily_totals = {d: round(sum(p["daily"].get(d, 0) for p in players), 1) for d in range(first, min(last, day) + 1)}
    return dict(team_id=team.id, name=team.name, manager=team.manager.display_name, points=points, projected=projected,
                bench_points=bench_total, players=players, daily_totals=daily_totals)


def matchup_detail(league: League, m: Matchup, week: int | None = None) -> dict:
    info = week_info(league, m.week)
    summ = stats_svc.summaries(league.sport_id, rules_of(league), league.current_day)
    home = db.session.get(FantasyTeam, m.home_team_id)
    away = db.session.get(FantasyTeam, m.away_team_id)
    hs, as_ = team_side(league, home, info, summ), team_side(league, away, info, summ)
    return dict(id=m.id, week=m.week, final=m.final, first_day=info["first_day"], last_day=info["last_day"], current_day=league.current_day,
                home=hs, away=as_, simulated=True)


def weekly_scores(league: League) -> dict:
    """{team_id: [score per finalized week]} - feeds the season performance chart."""
    out = {}
    for m in db.session.scalars(db.select(Matchup).where(Matchup.league_id == league.id, Matchup.final.is_(True)).order_by(Matchup.week)):
        out.setdefault(m.home_team_id, []).append(dict(week=m.week, points=m.home_score, opponent_id=m.away_team_id, opponent_points=m.away_score))
        out.setdefault(m.away_team_id, []).append(dict(week=m.week, points=m.away_score, opponent_id=m.home_team_id, opponent_points=m.home_score))
    return out
