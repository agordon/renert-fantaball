"""Draft room API: state, start, pick, bot/auto advance, queue, strategy assistant."""
from models.fantasy import DraftPick, DraftQueueItem, FantasyTeam
from root import db
from fantaball import draft as draft_svc
from fantaball import draft_assist
from fantaball import leagues as league_svc
from fantaball.errors import conflict, not_found
from fantaball.sports import SPORTS
from fantaball.pool import pool_query
from fantaball.lineups import rules_of
from fantaball import stats as stats_svc
from views.api_common import api, body, int_arg, int_list, need_int, team_json

POOL_LIMIT = 400


def _state(me, lg, team, include_pool=True) -> dict:
    session = draft_svc.session_of(lg.id)
    teams = league_svc.teams_of(lg.id)
    out = dict(league_status=lg.status, num_teams=lg.num_teams, my_team_id=team.id, is_commissioner=lg.commissioner_id == me.id,
               teams=[team_json(t, me) for t in teams], session=None, picks=[], pool=[], queue=[])
    if not session:
        return out
    picks = list(db.session.scalars(db.select(DraftPick).where(DraftPick.session_id == session.id).order_by(DraftPick.overall)))
    on_clock = draft_svc.team_on_clock(lg, session)
    total = draft_svc.total_picks(lg, session)
    from fantaball.utils import seconds_left
    out["session"] = dict(status=session.status, rounds=session.rounds, current_pick=session.current_pick, total_picks=total,
                          pick_seconds=session.pick_seconds, seconds_left=seconds_left(session.pick_deadline), on_clock_team_id=on_clock.id if on_clock else None,
                          current_round=draft_svc.pick_round(min(session.current_pick, total), lg.num_teams))
    dday = draft_svc.draft_day(lg)
    summ = stats_svc.summaries(lg.sport_id, rules_of(lg), dday)
    out["picks"] = [dict(overall=p.overall, round=p.round, team_id=p.team_id, auto=p.auto, athlete=dict(
        id=p.athlete_id, name=p.athlete.name, positions=p.athlete.positions, team=p.athlete.pro_team.abbr, proj=summ[p.athlete_id]["proj"])) for p in picks]
    if include_pool:
        taken = {p.athlete_id for p in picks}
        pool = []
        from models.fantasy import Athlete
        for a in db.session.scalars(pool_query(lg.sport_id).order_by(Athlete.rank)):
            if a.id in taken:
                continue
            s = summ[a.id]
            st = a.injury_status(dday + 1)
            pool.append(dict(id=a.id, name=a.name, positions=a.positions, team=a.pro_team.abbr, age=a.age, rank=a.rank, proj=s["proj"],
                             injury=st, injury_note=a.injury_note if st != "HEALTHY" else None))
        out["pool"] = pool[:POOL_LIMIT]
    out["queue"] = [q.athlete_id for q in db.session.scalars(db.select(DraftQueueItem).where(DraftQueueItem.team_id == team.id).order_by(DraftQueueItem.position))]
    return out


@api("/leagues/<int:league_id>/draft")
def draft_state(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    session = draft_svc.session_of(lg.id)
    if session and session.status == "live" and draft_svc._expired(session):
        # A human clock ran out: the server auto-picks (queue first, then best value)
        draft_svc.advance_one(lg, session)
    return _state(me, lg, team)


@api("/leagues/<int:league_id>/draft/start", methods=("POST",))
def draft_start(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    league_svc.require_commissioner(me, lg)
    secs = body().get("pick_seconds", 45)
    if isinstance(secs, bool) or not isinstance(secs, int):
        secs = 45
    draft_svc.start_draft(lg, secs)
    return _state(me, lg, team)


@api("/leagues/<int:league_id>/draft/pick", methods=("POST",))
def draft_pick(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    session = draft_svc.session_of(lg.id)
    if not session:
        raise not_found("The draft has not been set up")
    draft_svc.make_pick(lg, session, team, need_int(body(), "athlete_id"))
    return _state(me, lg, team)


@api("/leagues/<int:league_id>/draft/advance", methods=("POST",))
def draft_advance(me, league_id):
    """One computer pick (or one expired-clock auto pick). Lets the UI animate bot picks one at a time."""
    lg, team = league_svc.membership(me, league_id)
    session = draft_svc.session_of(lg.id)
    if not session:
        raise not_found("The draft has not been set up")
    made = draft_svc.advance_one(lg, session)
    state = _state(me, lg, team, include_pool=False)
    state["made"] = made
    return state


@api("/leagues/<int:league_id>/draft/sim", methods=("POST",))
def draft_sim(me, league_id):
    """Auto-draft: `to_end` completes the whole draft for everyone, including you (mock draft)."""
    lg, team = league_svc.membership(me, league_id)
    league_svc.require_commissioner(me, lg)
    session = draft_svc.session_of(lg.id)
    if not session or session.status != "live":
        raise conflict("The draft is not live")
    draft_svc.sim_until_human(lg, session, to_end=bool(body().get("to_end", False)))
    return _state(me, lg, team)


@api("/leagues/<int:league_id>/draft/queue", methods=("PUT",))
def draft_queue(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    draft_svc.set_queue(team, int_list(body(), "athlete_ids"), lg)
    return dict(queue=int_list(body(), "athlete_ids"))


@api("/leagues/<int:league_id>/draft/assistant")
def draft_assistant(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    session = draft_svc.session_of(lg.id)
    if not session or session.status != "live":
        raise conflict("The draft is not live")
    return draft_assist.assistant(lg, session, team)


@api("/leagues/<int:league_id>/draft/roster/<int:team_id>")
def draft_team_roster(me, league_id, team_id):
    """Picks made so far by one team (team roster summaries in the draft room)."""
    lg, mine = league_svc.membership(me, league_id)
    session = draft_svc.session_of(lg.id)
    t = db.session.get(FantasyTeam, team_id)
    if not session or not t or t.league_id != lg.id:
        raise not_found("Not found")
    picks = db.session.scalars(db.select(DraftPick).where(DraftPick.session_id == session.id, DraftPick.team_id == team_id).order_by(DraftPick.overall))
    return [dict(overall=p.overall, name=p.athlete.name, positions=p.athlete.positions, team=p.athlete.pro_team.abbr) for p in picks]
