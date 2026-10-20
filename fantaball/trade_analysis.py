"""Trade Impact Simulator - transparent before/after comparison. Estimates only, never guarantees.

For each team we build its best legal lineup (fantaball.roster.optimal_lineup) from projected points/game, then
    weekly projection = sum over starters of (projection per game x expected games per week)
    expected games/week = games the athlete's pro team plays in the next 14 days, scaled to 7 days
    rest-of-season value of a player = projection x games remaining on his team's schedule
The trade is summarised by the change in weekly projection, bench depth, positional strength and RoS value.
"""
from root import db
from models.fantasy import Athlete, FantasyTeam, League
from fantaball import stats as stats_svc
from fantaball.lineups import rules_of, team_slots
from fantaball.roster import optimal_lineup
from fantaball.sports import SPORTS


def _weekly_games(league: League, athlete: Athlete) -> float:
    day = league.current_day
    last = SPORTS[league.sport.code]["season_days"]
    window = min(14, last - day)
    if window <= 0:
        return 0.0
    n = stats_svc.games_in_window(league.sport_id, athlete.pro_team_id, day + 1, day + window)
    return n * 7 / window


def _games_remaining(league: League, athlete: Athlete) -> int:
    return stats_svc.games_in_window(league.sport_id, athlete.pro_team_id, league.current_day + 1, SPORTS[league.sport.code]["season_days"])


def evaluate_roster(league: League, athletes: list[Athlete], summ: dict) -> dict:
    sc = league.sport.code
    day = league.current_day
    players = [dict(id=a.id, positions=a.position_list, value=summ[a.id]["proj"], status=a.injury_status(day + 1)) for a in athletes]
    assign = optimal_lineup(sc, league.roster_config, players)
    by_id = {a.id: a for a in athletes}
    starters = [by_id[i] for i, s in assign.items() if s not in ("BN", "IR")]
    bench = [by_id[i] for i, s in assign.items() if s == "BN"]
    weekly = sum(summ[a.id]["proj"] * _weekly_games(league, a) for a in starters)
    positions = SPORTS[sc]["positions"]
    best_at = {p: max((summ[a.id]["proj"] for a in athletes if p in a.position_list), default=0.0) for p in positions}
    start_count = {p: sum(1 for a in starters if a.position_list[0] == p) for p in positions}
    bench_avg = sum(summ[a.id]["proj"] for a in bench) / len(bench) if bench else 0.0
    return dict(weekly=round(weekly, 1), bench_depth=round(bench_avg, 1), best_at=best_at, starters_by_position=start_count,
                starter_ids=[a.id for a in starters], n_players=len(athletes))


def analyze_trade(league: League, team_a: FantasyTeam, team_b: FantasyTeam, give_ids: list[int], get_ids: list[int]) -> dict:
    """A gives `give_ids` and receives `get_ids` from B. Ownership is validated by the caller."""
    summ = stats_svc.summaries(league.sport_id, rules_of(league), league.current_day)
    roster_a = [s.athlete for s in team_slots(team_a.id)]
    roster_b = [s.athlete for s in team_slots(team_b.id)]
    give = [a for a in roster_a if a.id in give_ids]
    get = [a for a in roster_b if a.id in get_ids]
    after_a = [a for a in roster_a if a.id not in give_ids] + get
    after_b = [a for a in roster_b if a.id not in get_ids] + give

    def side(before_roster, after_roster):
        b, a = evaluate_roster(league, before_roster, summ), evaluate_roster(league, after_roster, summ)
        return dict(before=b, after=a, weekly_change=round(a["weekly"] - b["weekly"], 1), depth_change=round(a["bench_depth"] - b["bench_depth"], 1),
                    position_change={p: round(a["best_at"][p] - b["best_at"][p], 1) for p in b["best_at"]})

    sa, sb = side(roster_a, after_a), side(roster_b, after_b)

    def ros(players):
        return round(sum(summ[x.id]["proj"] * _games_remaining(league, x) for x in players))

    value_a_gets, value_b_gets = ros(get), ros(give)
    total = (value_a_gets + value_b_gets) or 1
    diff = value_a_gets - value_b_gets

    def risks(players_in, players_out, who):
        out = []
        for a in players_in:
            st = a.injury_status(league.current_day + 1)
            if st != "HEALTHY":
                out.append(f"{who} would receive {a.name}, who is currently {st} ({a.injury_note}).")
            if summ[a.id]["gp"] < 8 and league.current_day > 0:
                out.append(f"{a.name} has only {summ[a.id]['gp']} games played - the projection is mostly the preseason prior.")
            if a.age >= 33:
                out.append(f"{a.name} is {a.age}: age/decline risk.")
        top_out = max(players_out, key=lambda a: summ[a.id]["proj"], default=None)
        if top_out and top_out.id in {i for i in evaluate_roster(league, (roster_a if who == team_a.name else roster_b), summ)["starter_ids"]}:
            out.append(f"{who} gives up a current starter ({top_out.name}).")
        if len(players_in) < len(players_out):
            out.append(f"{who} ends up with fewer players, which opens a roster spot (check depth).")
        return out

    # Verdict
    if sa["weekly_change"] > 0 and sb["weekly_change"] > 0:
        verdict = "Win-win: both rosters project to improve."
    elif sa["weekly_change"] <= 0 and sb["weekly_change"] <= 0:
        verdict = "Both sides project to lose weekly points (value may still be gained in depth or rest-of-season)."
    elif abs(diff) / total > 0.15:
        verdict = f"Lopsided toward {team_a.name if diff > 0 else team_b.name} on rest-of-season value."
    else:
        verdict = "Fairly balanced: one side gains weekly points, the other gains rest-of-season value."

    # Would a computer manager accept? It wants its own roster not to lose weekly points and not to lose much RoS value.
    bot_ok = sb["weekly_change"] >= -1 and (value_b_gets - value_a_gets) >= -0.03 * total
    return dict(
        team_a=dict(team_id=team_a.id, name=team_a.name, **sa, risks=risks(get, give, team_a.name)),
        team_b=dict(team_id=team_b.id, name=team_b.name, **sb, risks=risks(give, get, team_b.name)),
        value=dict(a_receives=value_a_gets, b_receives=value_b_gets, difference=diff, relative=round(diff / total, 3)),
        verdict=verdict, ai_would_accept=bool(bot_ok),
        ai_reason=("The computer manager's weekly projection does not drop and the value is close enough." if bot_ok
                   else "The computer manager would lose projected weekly points or too much rest-of-season value."),
        give=[a.id for a in give], get=[a.id for a in get],
        disclaimer="Projections are estimates from simulated demo data, not guarantees.",
        method="Weekly = best-lineup sum of projected points/game x expected games/week. Value = projection x remaining games.",
    )
