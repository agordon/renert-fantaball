"""Snake draft engine + computer-manager decision algorithm.

BOT PICK ALGORITHM (explainable):
    score(player) = value_over_replacement(player) + need_bonus(player) - injury_penalty + small random noise
  * value_over_replacement: projected fantasy points/game minus the replacement level at the player's best position.
    Replacement level = projection of the Nth best player at that position, N = teams * starting slots that position can fill.
  * need_bonus: +4 if a starting slot he can fill is still empty on the bot's roster (so bots don't draft 5 centers).
  * noise: Gaussian (sd 1.5) seeded by league+pick, so drafts differ per league but are reproducible.
"""
import random
from datetime import timedelta

from root import db
from models.fantasy import Athlete, DraftPick, DraftQueueItem, DraftSession, FantasyTeam, League, RosterSlot, utcnow
from fantaball import stats as stats_svc
from fantaball.errors import bad_request, conflict, forbidden, not_found
from fantaball.pool import pool_filter, pool_query
from fantaball.leagues import fill_with_bots, generate_schedule, log_activity, teams_of
from fantaball.lineups import rules_of
from fantaball.roster import optimal_lineup
from fantaball.sports import SPORTS


def draft_day(league: League) -> int:
    """Statistics are used up to today when valuing players (day 0 before the season starts)."""
    from fantaball import timeline
    return min(timeline.today_day(league.sport), SPORTS[league.sport.code]["season_days"])


def snake_team_slot(overall: int, n_teams: int) -> int:
    """1-based draft slot that owns overall pick `overall` in a snake draft."""
    rnd, idx = divmod(overall - 1, n_teams)
    return idx + 1 if rnd % 2 == 0 else n_teams - idx


def pick_round(overall: int, n_teams: int) -> int:
    return (overall - 1) // n_teams + 1


# ---------------------------------------------------------------------------------------------
def session_of(league_id: int) -> DraftSession | None:
    return db.session.scalar(db.select(DraftSession).where(DraftSession.league_id == league_id))


def total_picks(league: League, session: DraftSession) -> int:
    return league.num_teams * session.rounds


def team_on_clock(league: League, session: DraftSession) -> FantasyTeam | None:
    if session.status != "live":
        return None
    slot = snake_team_slot(session.current_pick, league.num_teams)
    return db.session.scalar(db.select(FantasyTeam).where(FantasyTeam.league_id == league.id, FantasyTeam.draft_slot == slot))


def default_rounds(league: League) -> int:
    """One round per non-IR roster spot (starters + bench)."""
    return sum(c for s, c in league.roster_config if s != "IR")


def start_draft(league: League, pick_seconds: int = 45) -> DraftSession:
    """Fill empty seats with bots, randomize the draft order, open the draft room. (Commissioner action.)"""
    if league.status != "pre_draft":
        raise conflict("The draft has already started")
    if not 10 <= pick_seconds <= 300:
        raise bad_request("Pick clock must be between 10 and 300 seconds")
    fill_with_bots(league)
    needed = league.num_teams * default_rounds(league)
    available = db.session.scalar(db.select(db.func.count(Athlete.id)).where(*pool_filter(league.sport_id))) or 0
    if available < needed:
        db.session.rollback()
        raise conflict(f"Not enough players to draft: {league.num_teams} teams x {default_rounds(league)} rounds needs {needed} players but only "
                       f"{available} are available. Import more players, use fewer teams, or shrink the roster.")
    teams = teams_of(league.id)
    order = list(range(1, len(teams) + 1))
    random.Random(f"order-{league.id}-{league.invite_code}").shuffle(order)
    for t, slot in zip(teams, order):
        t.draft_slot = slot
    session = DraftSession(league_id=league.id, status="live", rounds=default_rounds(league), pick_seconds=pick_seconds,
                           current_pick=1, pick_deadline=utcnow() + timedelta(seconds=pick_seconds))
    db.session.add(session)
    league.status = "drafting"
    log_activity(league.id, "draft", "The draft has started")
    db.session.commit()
    return session


def drafted_ids(session: DraftSession) -> set[int]:
    return set(db.session.scalars(db.select(DraftPick.athlete_id).where(DraftPick.session_id == session.id)))


def available_athletes(league: League, session: DraftSession) -> list[Athlete]:
    taken = drafted_ids(session)
    q = pool_query(league.sport_id).order_by(Athlete.rank)
    return [a for a in db.session.scalars(q) if a.id not in taken]


def make_pick(league: League, session: DraftSession, team: FantasyTeam, athlete_id: int, auto: bool = False) -> DraftPick:
    """Validate and record one pick (turn order, availability), advance the clock, finish the draft after the last pick."""
    if session.status != "live":
        raise conflict("The draft is not live")
    on_clock = team_on_clock(league, session)
    if on_clock is None or on_clock.id != team.id:
        raise forbidden("It is not your turn to pick")
    athlete = db.session.get(Athlete, athlete_id)
    if not athlete or athlete.sport_id != league.sport_id:
        raise not_found("Player not found")
    if athlete_id in drafted_ids(session):
        raise conflict(f"{athlete.name} has already been drafted")
    overall = session.current_pick
    pick = DraftPick(session_id=session.id, overall=overall, round=pick_round(overall, league.num_teams),
                     team_id=team.id, athlete_id=athlete_id, auto=auto)
    db.session.add(pick)
    for qi in db.session.scalars(db.select(DraftQueueItem).where(DraftQueueItem.athlete_id == athlete_id)):
        if db.session.get(FantasyTeam, qi.team_id).league_id == league.id:
            db.session.delete(qi)
    session.current_pick = overall + 1
    session.pick_deadline = utcnow() + timedelta(seconds=session.pick_seconds)
    db.session.flush()
    if overall >= total_picks(league, session):
        complete_draft(league, session)
    db.session.commit()
    return pick


def complete_draft(league: League, session: DraftSession):
    """Turn picks into rosters (best legal lineup), create the season schedule, activate the league."""
    day = draft_day(league)
    summ = stats_svc.summaries(league.sport_id, rules_of(league), day)
    sc = league.sport.code
    for team in teams_of(league.id):
        picks = list(db.session.scalars(db.select(DraftPick).where(DraftPick.session_id == session.id, DraftPick.team_id == team.id)))
        players = [dict(id=p.athlete_id, positions=p.athlete.position_list, value=summ[p.athlete_id]["proj"],
                        status=p.athlete.injury_status(day + 1)) for p in picks]
        assignment = optimal_lineup(sc, league.roster_config, players)
        for p in picks:
            db.session.add(RosterSlot(league_id=league.id, team_id=team.id, athlete_id=p.athlete_id, slot=assignment[p.athlete_id], acquired_via="draft", acquired_at=utcnow()))
    session.status = "complete"
    session.pick_deadline = None
    league.status = "active"
    league.current_day = day
    # A league drafted mid-season starts scoring TOMORROW (current_day = today's day number) in the current week.
    generate_schedule(league, first_week=stats_svc.week_of_day(day + 1, SPORTS[league.sport.code]["days_per_week"]) if day else 1)
    log_activity(league.id, "draft", "The draft is complete - the season is ready to start")


# ---------------------------------------------------------------------------------------------
# Valuation helpers (shared with the draft assistant)
# ---------------------------------------------------------------------------------------------
def slots_per_position(league: League) -> dict[str, float]:
    """How many starting 'seats' per position a team has (flex slots are split between the positions that can fill them)."""
    sc = league.sport.code
    positions = SPORTS[sc]["positions"]
    seats = {p: 0.0 for p in positions}
    for slot, count in league.roster_config:
        if slot in ("BN", "IR"):
            continue
        allowed = positions if slot == "UTIL" else SPORTS[sc]["slot_positions"].get(slot, [])
        for p in allowed:
            seats[p] += count / len(allowed)
    return seats


def replacement_levels(league: League, athletes: list[Athlete], proj: dict) -> dict[str, float]:
    """Projection of the Nth best player at each position (N = league seats at that position)."""
    seats = slots_per_position(league)
    levels = {}
    for pos, per_team in seats.items():
        vals = sorted((proj[a.id] for a in athletes if pos in a.position_list), reverse=True)
        n = max(1, round(per_team * league.num_teams))
        levels[pos] = vals[min(n, len(vals)) - 1] if vals else 0.0
    return levels


def value_over_replacement(athlete: Athlete, proj: dict, levels: dict) -> float:
    return round(max(proj[athlete.id] - levels[p] for p in athlete.position_list), 2)


def team_needs(league: League, drafted: list[Athlete]) -> dict[str, int]:
    """Empty starting seats a roster still has, per position, after greedily seating the drafted players."""
    sc = league.sport.code
    players = [dict(id=a.id, positions=a.position_list, value=a.rank * -1.0, status="HEALTHY") for a in drafted]
    assignment = optimal_lineup(sc, league.roster_config, players)
    filled = {s: 0 for s, _ in league.roster_config}
    for slot in assignment.values():
        filled[slot] = filled.get(slot, 0) + 1
    needs = {p: 0 for p in SPORTS[sc]["positions"]}
    for slot, count in league.roster_config:
        if slot in ("BN", "IR", "UTIL"):
            continue
        open_n = count - filled.get(slot, 0)
        if open_n > 0:
            for p in SPORTS[sc]["slot_positions"][slot]:
                needs[p] += open_n
    return needs


def bot_choose(league: League, session: DraftSession, team: FantasyTeam, available: list[Athlete]) -> Athlete:
    if not available:
        raise conflict("There are no players left to draft. Import more players, or ask the commissioner to restart with fewer teams.")
    summ = stats_svc.summaries(league.sport_id, rules_of(league), draft_day(league))
    proj = {a.id: summ[a.id]["proj"] for a in available}
    all_ath = available   # replacement levels from the still-available pool keep scarcity realistic
    levels = replacement_levels(league, all_ath, proj)
    mine = [p.athlete for p in db.session.scalars(db.select(DraftPick).where(DraftPick.session_id == session.id, DraftPick.team_id == team.id))]
    needs = team_needs(league, mine)
    rng = random.Random(f"{league.id}-{session.current_pick}")
    best, best_score = None, -1e9
    for a in available:
        score = value_over_replacement(a, proj, levels)
        if any(needs[p] > 0 for p in a.position_list):
            score += 4
        if a.injury_status(draft_day(league) + 1) != "HEALTHY":
            score -= 8
        score += rng.gauss(0, 1.5)
        if score > best_score:
            best, best_score = a, score
    return best


def autopick_for(league: League, session: DraftSession, team: FantasyTeam) -> Athlete:
    """Queue first (first still-available player), otherwise the algorithm's best choice."""
    available = available_athletes(league, session)
    avail_ids = {a.id for a in available}
    for qi in db.session.scalars(db.select(DraftQueueItem).where(DraftQueueItem.team_id == team.id).order_by(DraftQueueItem.position)):
        if qi.athlete_id in avail_ids:
            return next(a for a in available if a.id == qi.athlete_id)
    return bot_choose(league, session, team, available)


def advance_one(league: League, session: DraftSession) -> dict | None:
    """Make ONE pick if the team on the clock is a bot, or a human whose clock has expired. Returns pick info or None."""
    team = team_on_clock(league, session)
    if team is None:
        return None
    expired = session.pick_deadline is not None and utcnow() >= session.pick_deadline
    if team.is_bot or expired:
        athlete = autopick_for(league, session, team) if not team.is_bot else bot_choose(league, session, team, available_athletes(league, session))
        pick = make_pick(league, session, team, athlete.id, auto=True)
        return dict(overall=pick.overall, team_id=team.id, athlete_id=athlete.id)
    return None


def sim_until_human(league: League, session: DraftSession, to_end: bool = False) -> int:
    """Run bot picks (and expired human picks) until a live human is on the clock (or the draft ends)."""
    n = 0
    while session.status == "live":
        team = team_on_clock(league, session)
        if team is None or (not team.is_bot and not to_end and not _expired(session)):
            break
        athlete = bot_choose(league, session, team, available_athletes(league, session)) if (team.is_bot or to_end) \
            else autopick_for(league, session, team)
        make_pick(league, session, team, athlete.id, auto=True)
        n += 1
    return n


def _expired(session: DraftSession) -> bool:
    return session.pick_deadline is not None and utcnow() >= session.pick_deadline


def set_queue(team: FantasyTeam, athlete_ids: list[int], league: League):
    ids = list(dict.fromkeys(athlete_ids))       # de-dupe, keep order
    if len(ids) > 60:
        raise bad_request("Queue is limited to 60 players")
    valid = set(db.session.scalars(db.select(Athlete.id).where(Athlete.sport_id == league.sport_id, Athlete.id.in_(ids))))
    if set(ids) - valid:
        raise bad_request("Queue contains unknown players")
    for qi in db.session.scalars(db.select(DraftQueueItem).where(DraftQueueItem.team_id == team.id)):
        db.session.delete(qi)
    db.session.flush()
    for i, aid in enumerate(ids):
        db.session.add(DraftQueueItem(team_id=team.id, athlete_id=aid, position=i))
    db.session.commit()
