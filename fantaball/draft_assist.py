"""Draft Strategy Assistant: explainable recommendations (no external AI).

Per candidate we compute
  VOR   = projection - replacement level at the player's best position          (fantaball.draft.value_over_replacement)
  need  = does he fill an EMPTY starting seat on your roster?  (+3 to the recommendation score)
  survive = estimated chance he is still there at your next pick (logistic in his rank among the available pool vs. picks in between)
  opportunity cost of waiting = VOR - VOR of the best player expected to be left at his position by your next pick
"""
import math

from root import db
from models.fantasy import DraftPick, DraftSession, FantasyTeam, League
from fantaball import stats as stats_svc
from fantaball.draft import (available_athletes, draft_day, replacement_levels, slots_per_position, snake_team_slot, team_needs, value_over_replacement)
from fantaball.lineups import rules_of
from fantaball.sports import SPORTS

NEED_BONUS = 3.0


def picks_until_next_turn(league: League, session: DraftSession, team: FantasyTeam) -> int:
    """Number of OTHER teams' picks that will happen before `team` picks again (after its current/next turn)."""
    n = league.num_teams
    total = n * session.rounds
    cur = session.current_pick
    first_mine = next((o for o in range(cur, total + 1) if snake_team_slot(o, n) == team.draft_slot), None)
    if first_mine is None:
        return 0
    nxt = next((o for o in range(first_mine + 1, total + 1) if snake_team_slot(o, n) == team.draft_slot), None)
    return (nxt - first_mine - 1) if nxt else 0


def survive_probability(index_in_pool: int, picks_between: int) -> float:
    """P(player still available after `picks_between` picks), given he is the `index_in_pool`-th most desirable player left."""
    if picks_between <= 0:
        return 1.0
    return round(1 / (1 + math.exp(-(index_in_pool - picks_between) / (0.3 * picks_between + 1))), 2)


def assistant(league: League, session: DraftSession, team: FantasyTeam) -> dict:
    sc = league.sport.code
    positions = SPORTS[sc]["positions"]
    available = available_athletes(league, session)
    dday = draft_day(league)
    summ = stats_svc.summaries(league.sport_id, rules_of(league), dday)
    proj = {a.id: summ[a.id]["proj"] for a in available}
    levels = replacement_levels(league, available, proj)
    mine = [p.athlete for p in db.session.scalars(db.select(DraftPick).where(DraftPick.session_id == session.id, DraftPick.team_id == team.id))]
    needs = team_needs(league, mine)
    between = picks_until_next_turn(league, session, team)
    seats = slots_per_position(league)
    total_seats = sum(seats.values()) or 1

    vor = {a.id: value_over_replacement(a, proj, levels) for a in available}
    ranked = sorted(available, key=lambda a: -(vor[a.id] + (NEED_BONUS if any(needs[p] for p in a.position_list) else 0)))

    def row(a, idx):
        need = [p for p in a.position_list if needs[p] > 0]
        reasons = [f"{vor[a.id]:+.1f} pts/game over a replacement-level {a.position_list[0]}"]
        if need:
            reasons.append(f"fills an open {'/'.join(need)} starting spot")
        if a.injury_status(dday + 1) != "HEALTHY":
            reasons.append(f"injury risk: {a.injury_note}")
        return dict(id=a.id, name=a.name, positions=a.positions, team=a.pro_team.abbr, rank=a.rank, proj=proj[a.id], vor=vor[a.id],
                    fills_need=bool(need), survive_prob=survive_probability(idx, between), reasons=reasons)

    best = [row(a, i) for i, a in enumerate(ranked[:8])]

    # Remaining depth: how many players above replacement level are left at each position
    depth = {}
    for p in positions:
        pool = [a for a in available if p in a.position_list]
        depth[p] = dict(left=len(pool), above_replacement=sum(1 for a in pool if proj[a.id] > levels[p]),
                        top_proj=max((proj[a.id] for a in pool), default=0))

    # Roster balance (how many of each position drafted so far)
    balance = {p: sum(1 for a in mine if p in a.position_list) for p in positions}

    # Steals: consensus rank much better than the current pick number
    cur = session.current_pick
    steals = [dict(id=a.id, name=a.name, positions=a.positions, rank=a.rank, falls_by=cur - a.rank, proj=proj[a.id])
              for a in available if cur - a.rank >= 8][:4]

    # Opportunity cost of waiting on the top recommendation
    opp = None
    if ranked:
        top = ranked[0]
        pos = top.position_list[0]
        pool = [a for a in ranked if pos in a.position_list and a.id != top.id]
        expected_gone = round(between * seats.get(pos, 1) / total_seats)
        left_then = pool[min(expected_gone, len(pool) - 1)] if pool else None
        if left_then:
            opp = dict(player=top.name, position=pos, vor_now=vor[top.id], expected_alternative=left_then.name,
                       vor_alternative=vor[left_then.id], cost=round(vor[top.id] - vor[left_then.id], 1),
                       explanation=f"If you wait, the best {pos} you can expect at your next pick is about {left_then.name} "
                                   f"({vor[left_then.id]:+.1f} VOR) - a drop of {vor[top.id] - vor[left_then.id]:.1f} pts/game.")

    return dict(on_clock_overall=cur, picks_until_next_turn=between, best_available=best, positions_of_need={p: n for p, n in needs.items() if n > 0},
                balance=balance, depth=depth, steals=steals, opportunity_cost=opp, replacement_levels={p: round(v, 1) for p, v in levels.items()},
                method="VOR = projected fantasy points/game minus replacement level at the position (the Nth best player, N = league starting seats). "
                       "Need bonus +3 for an open starting spot. Availability uses a logistic estimate based on picks before your next turn.")
