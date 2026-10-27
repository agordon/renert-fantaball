"""DB-aware roster helpers: load a team's roster, apply lineups, repair lineups after add/drop/trade."""
from root import db
from models.fantasy import Athlete, FantasyTeam, League, RosterSlot
from fantaball import stats as stats_svc
from fantaball.errors import bad_request
from fantaball.roster import RosterError, eligible, optimal_lineup, slot_order_for_assignment, validate_lineup
from fantaball.sports import roster_slots


def rules_of(league: League) -> dict:
    return league.scoring.rules


def sport_code(league: League) -> str:
    return league.sport.code


def roster_capacity(league: League) -> int:
    return len(roster_slots(sport_code(league), league.roster_config))


def team_slots(team_id: int) -> list[RosterSlot]:
    return list(db.session.scalars(db.select(RosterSlot).where(RosterSlot.team_id == team_id)))


def owner_map(league_id: int) -> dict:
    """{athlete_id: team_id} for every owned athlete in the league."""
    return dict(db.session.execute(db.select(RosterSlot.athlete_id, RosterSlot.team_id).where(RosterSlot.league_id == league_id)).all())


def player_inputs(league: League, athletes: list[Athlete], through_day: int | None = None) -> list[dict]:
    day = league.current_day if through_day is None else through_day
    summ = stats_svc.summaries(league.sport_id, rules_of(league), day)
    return [dict(id=a.id, positions=a.position_list, value=summ[a.id]["proj"], status=a.injury_status(day + 1)) for a in athletes]


def auto_set_lineup(league: League, team: FantasyTeam):
    """Re-assign every player on `team` to the best legal slots (projection-optimal)."""
    slots = team_slots(team.id)
    assignment = optimal_lineup(sport_code(league), league.roster_config, player_inputs(league, [s.athlete for s in slots]))
    for s in slots:
        s.slot = assignment[s.athlete_id]


def set_lineup(league: League, team: FantasyTeam, assignment: dict[int, str]):
    """Apply a user-provided {athlete_id: slot}. Must cover exactly the team's roster and be legal."""
    slots = {s.athlete_id: s for s in team_slots(team.id)}
    if set(assignment) != set(slots):
        raise bad_request("Lineup must include exactly the players on your roster")
    try:
        validate_lineup(sport_code(league), league.roster_config, assignment, {aid: s.athlete for aid, s in slots.items()}, league.current_day + 1)
    except RosterError as e:
        raise bad_request(str(e))
    for aid, slot in assignment.items():
        slots[aid].slot = slot


def place_new_players(league: League, team: FantasyTeam, new_athlete_ids: list[int], preferred: dict[int, str] | None = None):
    """Give just-acquired players (already RosterSlot rows with a temporary slot) a legal slot.

    Existing players keep their slots. Newcomers take a preferred slot if legal and free, else the first free eligible
    slot (starters, then bench, then IR). If nothing fits we fall back to re-optimizing the whole team.
    """
    sc = sport_code(league)
    day = league.current_day + 1
    slots = team_slots(team.id)
    new_set = set(new_athlete_ids)
    cap = {}
    for slot, count in league.roster_config:
        cap[slot] = cap.get(slot, 0) + int(count)
    taken = {}
    for s in slots:
        if s.athlete_id not in new_set:
            taken[s.slot] = taken.get(s.slot, 0) + 1
    order = slot_order_for_assignment(sc, league.roster_config) + ["BN", "IR"]
    for s in sorted((s for s in slots if s.athlete_id in new_set), key=lambda s: s.athlete.rank):
        a = s.athlete
        status = a.injury_status(day)
        candidates = ([preferred[a.id]] if preferred and a.id in preferred else []) + order
        placed = False
        for cand in candidates:
            if taken.get(cand, 0) < cap.get(cand, 0) and eligible(sc, cand, a.position_list, status) \
                    and (cand in ("BN", "IR") or status == "HEALTHY"):
                s.slot = cand
                taken[cand] = taken.get(cand, 0) + 1
                placed = True
                break
        if not placed:
            auto_set_lineup(league, team)
            return
