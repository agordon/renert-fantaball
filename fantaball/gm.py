"""Fantasy GM: rule-based roster intelligence. Every recommendation carries its own explanation and a points estimate.

Checks: (1) positional strength vs the league, (2) bench depth, (3) this week's schedule volume, (4) lineup improvements
(re-optimizing on projection x games left this week), (5) best free-agent upgrade, (6) injured-reserve housekeeping.
"""
from root import db
from models.fantasy import Athlete, League, FantasyTeam
from fantaball import stats as stats_svc
from fantaball.pool import pool_query
from fantaball.lineups import owner_map, rules_of, team_slots
from fantaball.roster import optimal_lineup
from fantaball.sports import SPORTS
from fantaball.trade_analysis import evaluate_roster


def _games_left_this_week(league: League, a: Athlete) -> int:
    dpw = SPORTS[league.sport.code]["days_per_week"]
    week = stats_svc.week_of_day(league.current_day + 1, dpw)
    first, last = stats_svc.week_bounds(week, dpw)
    return stats_svc.games_in_window(league.sport_id, a.pro_team_id, max(first, league.current_day + 1), last)


def analyze(league: League, team: FantasyTeam) -> dict:
    sc = league.sport.code
    day = league.current_day
    summ = stats_svc.summaries(league.sport_id, rules_of(league), day)
    positions = SPORTS[sc]["positions"]
    slots = team_slots(team.id)
    mine = [s.athlete for s in slots]
    cur_slot = {s.athlete_id: s.slot for s in slots}

    # 1) Positional strength vs league (rank among teams of the best player's projection at each position)
    teams = db.session.scalars(db.select(FantasyTeam).where(FantasyTeam.league_id == league.id)).all()
    best_by_team = {t.id: evaluate_roster(league, [s.athlete for s in team_slots(t.id)], summ)["best_at"] for t in teams}
    strengths = []
    for p in positions:
        vals = sorted((b[p] for b in best_by_team.values()), reverse=True)
        mine_v = best_by_team[team.id][p]
        rank = vals.index(mine_v) + 1
        label = "strength" if rank <= len(vals) / 3 else "weakness" if rank > 2 * len(vals) / 3 else "average"
        strengths.append(dict(position=p, best_proj=mine_v, league_rank=rank, of=len(vals), label=label))

    # 2) Bench depth vs league
    depth_by_team = {t.id: evaluate_roster(league, [s.athlete for s in team_slots(t.id)], summ)["bench_depth"] for t in teams}
    ordered = sorted(depth_by_team.values(), reverse=True)
    bench = dict(avg_proj=depth_by_team[team.id], league_rank=ordered.index(depth_by_team[team.id]) + 1, of=len(ordered))

    # 3) Schedule: games left this week for starters
    starters = [s.athlete for s in slots if s.slot not in ("BN", "IR")]
    schedule = [dict(athlete_id=a.id, name=a.name, games_left=_games_left_this_week(league, a)) for a in starters]
    schedule.sort(key=lambda r: r["games_left"])

    suggestions = []
    weekly = {a.id: summ[a.id]["proj"] * _games_left_this_week(league, a) for a in mine}

    # 4) Lineup optimization on points expected this week
    players = [dict(id=a.id, positions=a.position_list, value=weekly[a.id], status=a.injury_status(day + 1)) for a in mine]
    best = optimal_lineup(sc, league.roster_config, players)
    cur_total = sum(weekly[i] for i, s in cur_slot.items() if s not in ("BN", "IR"))
    best_total = sum(weekly[i] for i, s in best.items() if s not in ("BN", "IR"))
    if best_total - cur_total >= 5:
        ins = [i for i, s in best.items() if s not in ("BN", "IR") and cur_slot[i] in ("BN", "IR")]
        outs = [i for i, s in cur_slot.items() if s not in ("BN", "IR") and best[i] in ("BN", "IR")]
        names = {a.id: a.name for a in mine}
        suggestions.append(dict(
            type="lineup", title="Improve your lineup", impact=round(best_total - cur_total, 1),
            detail=f"Start {', '.join(names[i] for i in ins) or 'a different arrangement'}"
                   + (f" instead of {', '.join(names[i] for i in outs)}" if outs else "")
                   + f": about +{best_total - cur_total:.0f} expected points this week (projection x games left).",
            action=dict(kind="auto_lineup")))

    # 5) Best free agent vs worst player you could drop
    owned = owner_map(league.id)
    free = [a for a in db.session.scalars(pool_query(league.sport_id)) if a.id not in owned and a.injury_status(day + 1) == "HEALTHY"]
    droppable = [a for a in mine if cur_slot[a.id] in ("BN", "IR")] or mine
    if free and droppable:
        fa = max(free, key=lambda a: summ[a.id]["proj"] * max(_games_left_this_week(league, a), 1))
        worst = min(droppable, key=lambda a: summ[a.id]["proj"])
        gain = (summ[fa.id]["proj"] - summ[worst.id]["proj"]) * 4.0      # ~4 games/week
        if gain >= 8:
            suggestions.append(dict(type="add_drop", title=f"Add {fa.name}", impact=round(gain, 1),
                                    detail=f"{fa.name} projects {summ[fa.id]['proj']:.1f} pts/game vs {summ[worst.id]['proj']:.1f} for {worst.name} "
                                           f"(your weakest reserve): roughly +{gain:.0f} points per week of roster value.",
                                    action=dict(kind="add_drop", add_id=fa.id, drop_id=worst.id)))
        streamers = sorted(free, key=lambda a: (-_games_left_this_week(league, a), -summ[a.id]["proj"]))[:1]
        for s in streamers:
            g = _games_left_this_week(league, s)
            if g >= 4 and summ[s.id]["proj"] > summ[worst.id]["proj"] and s.id != fa.id:
                suggestions.append(dict(type="stream", title=f"Streaming option: {s.name}", impact=round((summ[s.id]["proj"] - summ[worst.id]["proj"]) * g, 1),
                                        detail=f"{s.name}'s team has {g} games left this week, the most among healthy free agents.",
                                        action=dict(kind="add_drop", add_id=s.id, drop_id=worst.id)))

    # 6) IR housekeeping
    for a in mine:
        st = a.injury_status(day + 1)
        if st != "HEALTHY" and cur_slot[a.id] not in ("IR", "BN"):
            suggestions.append(dict(type="injury", title=f"{a.name} is {st}", impact=round(summ[a.id]["proj"] * 3, 1),
                                    detail=f"{a.name} ({a.injury_note}) is in a starting slot but cannot play. Move him to IR/bench.", action=dict(kind="auto_lineup")))
        if st == "HEALTHY" and cur_slot[a.id] == "IR":
            suggestions.append(dict(type="injury", title=f"{a.name} is healthy again", impact=round(summ[a.id]["proj"] * 3, 1),
                                    detail=f"{a.name} is back from injury but still occupies your IR spot.", action=dict(kind="auto_lineup")))

    weakest = min(strengths, key=lambda s: s["league_rank"] * -1)
    summary = []
    strong = [s["position"] for s in strengths if s["label"] == "strength"]
    weak = [s["position"] for s in strengths if s["label"] == "weakness"]
    if strong:
        summary.append(f"Strongest spots: {', '.join(strong)}.")
    if weak:
        summary.append(f"Weakest spots vs the league: {', '.join(weak)} - consider upgrading via free agency or a trade.")
    summary.append(f"Bench depth ranks {bench['league_rank']} of {bench['of']}.")
    suggestions.sort(key=lambda s: -s["impact"])
    return dict(strengths=strengths, bench=bench, schedule=schedule, suggestions=suggestions[:6], summary=" ".join(summary),
                weakest_position=weakest["position"],
                method="Rule-based: positional ranks compare each team's best player per position; suggestions use projection x games left this week.")
