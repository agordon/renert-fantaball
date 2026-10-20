"""FantaBall REST API (JSON under /api). Core: profile, leagues, dashboard, roster, players, matchups, standings.
Draft and trade endpoints live in api_draft.py / api_trades.py. Business rules live in the `fantaball` package."""
from flask import current_app, request

from root import app, db
from models.fantasy import Activity, Athlete, FantasyTeam, League, Matchup, PlayerTransaction, ProGame, ProTeam, RosterSlot, TradeOffer
from fantaball import gm as gm_svc
from fantaball import leagues as league_svc
from fantaball import matchups as matchup_svc
from fantaball import simulation, stats as stats_svc
from fantaball import transactions as tx
from fantaball.errors import bad_request, forbidden, not_found
from fantaball.lineups import auto_set_lineup, set_lineup, team_slots
from fantaball.sports import PLAYABLE_SPORTS, SPORTS
from views.api_common import AthleteContext, api, body, clean_display_name, get_athlete, int_arg, int_list, league_json, need_int, team_json


@api("/health")
def health(me):
    return dict(ok=True)


# ----------------------------------------------------------------------------- profile
@api("/me")
def get_me(me):
    jwt_cfg = current_app.extensions.get("jwtauthmanager")
    demo = bool(jwt_cfg and jwt_cfg.dummy_user_if_no_proxy and not jwt_cfg.is_behind_proxy())
    return dict(id=me.id, email=me.email, display_name=me.display_name, auth_mode="demo" if demo else "sso",
                logout_url=None if demo else jwt_cfg.logout_path)


@api("/me", methods=("PATCH",))
def patch_me(me):
    me.display_name = clean_display_name(body().get("display_name"))
    db.session.commit()
    return dict(id=me.id, email=me.email, display_name=me.display_name)


@api("/sports")
def sports(me):
    return [dict(code=c, name=s["name"], positions=s["positions"], stats=s["stats"], default_scoring=s["default_scoring"],
                 roster=s["roster"], playable=c in PLAYABLE_SPORTS) for c, s in SPORTS.items()]


# ----------------------------------------------------------------------------- leagues
def _team_summary(league: League, team: FantasyTeam) -> dict:
    rows = league_svc.standings(league)
    mine = next(r for r in rows if r["team_id"] == team.id)
    return dict(team_id=team.id, team_name=team.name, wins=mine["w"], losses=mine["l"], ties=mine["t"], rank=mine["rank"], pf=mine["pf"])


@api("/leagues")
def list_leagues(me):
    teams = db.session.scalars(db.select(FantasyTeam).where(FantasyTeam.manager_id == me.id).order_by(FantasyTeam.id))
    out = []
    for t in teams:
        lg = db.session.get(League, t.league_id)
        out.append(dict(**league_json(lg, me, t), record=_team_summary(lg, t) if lg.status == "active" else None,
                        members=len(league_svc.teams_of(lg.id))))
    return out


@api("/leagues", methods=("POST",))
def create_league(me):
    d = body()
    lg = league_svc.create_league(me, d.get("name"), d.get("sport", "nba"), d.get("num_teams", 12), d.get("scoring_rules"),
                                  d.get("roster_config"), d.get("team_name"), fill_bots=bool(d.get("fill_bots", True)))
    team = db.session.scalar(db.select(FantasyTeam).where(FantasyTeam.league_id == lg.id, FantasyTeam.manager_id == me.id))
    return league_json(lg, me, team), 201


@api("/leagues/join", methods=("POST",))
def join_league(me):
    d = body()
    lg = league_svc.join_league(me, d.get("code"), d.get("team_name"))
    team = db.session.scalar(db.select(FantasyTeam).where(FantasyTeam.league_id == lg.id, FantasyTeam.manager_id == me.id))
    return league_json(lg, me, team)


@api("/leagues/<int:league_id>")
def league_detail(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    teams = league_svc.teams_of(lg.id)
    return dict(**league_json(lg, me, team), invite_code=lg.invite_code, scoring_rules=lg.scoring.rules, roster_config=lg.roster_config,
                stat_labels=SPORTS[lg.sport.code]["stats"],
                commissioner=next((t.manager.display_name for t in teams if t.manager_id == lg.commissioner_id), None),
                teams=[team_json(t, me) for t in teams], open_seats=lg.num_teams - len(teams))


@api("/leagues/<int:league_id>", methods=("PATCH",))
def league_update(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    league_svc.update_settings(me, lg, body())
    return league_detail.__wrapped__(me, league_id)


@api("/leagues/<int:league_id>/team-name", methods=("PATCH",))
def rename_team(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    team.name = league_svc.clean_team_name(body().get("name"))
    db.session.commit()
    return dict(id=team.id, name=team.name)


@api("/leagues/<int:league_id>/simulate", methods=("POST",))
def simulate(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    league_svc.require_commissioner(me, lg)
    days = body().get("days", 1)
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 14:
        raise bad_request("days must be a whole number from 1 to 14")
    res = simulation.advance_days(lg, days)
    return dict(league=league_json(lg, me, team), last=res)


# ----------------------------------------------------------------------------- roster
def _roster_payload(lg: League, me, team: FantasyTeam) -> dict:
    ctx = AthleteContext(lg)
    slots = team_slots(team.id)
    gm = gm_svc.analyze(lg, team) if lg.status == "active" else None
    rows = []
    for s in slots:
        r = ctx.row(s.athlete)
        r["slot"] = s.slot
        rows.append(r)
    order = {s: i for i, (s, _) in enumerate(lg.roster_config)}
    rows.sort(key=lambda r: (order.get(r["slot"], 99), -r["proj"]))
    layout = [s for s, c in lg.roster_config for _ in range(c)]
    sp = SPORTS[lg.sport.code]
    return dict(team=team_json(team, me), league=league_json(lg, me, team), slots=layout, players=rows, auto_lineup=team.auto_lineup,
                slot_positions=sp["slot_positions"], gm=gm, week=ctx.week, week_last_day=ctx.week_last)


@api("/leagues/<int:league_id>/team")
def get_team(me, league_id):
    lg, mine = league_svc.membership(me, league_id)
    tid = int_arg("team_id")
    team = mine if tid is None else db.session.get(FantasyTeam, tid)
    if team is None or team.league_id != lg.id:
        raise not_found("Team not found")
    return _roster_payload(lg, me, team)


@api("/leagues/<int:league_id>/lineup", methods=("PUT",))
def put_lineup(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    raw = body().get("assignment")
    if not isinstance(raw, dict):
        raise bad_request("assignment must be an object {athleteId: slot}")
    try:
        assignment = {int(k): v for k, v in raw.items()}
    except ValueError:
        raise bad_request("assignment keys must be player ids")
    if any(not isinstance(v, str) for v in assignment.values()):
        raise bad_request("slots must be text")
    set_lineup(lg, team, assignment)
    team.auto_lineup = False
    db.session.commit()
    return _roster_payload(lg, me, team)


@api("/leagues/<int:league_id>/lineup/auto", methods=("POST",))
def auto_lineup(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    auto_set_lineup(lg, team)
    team.auto_lineup = bool(body().get("keep_on", False))
    db.session.commit()
    return _roster_payload(lg, me, team)


@api("/leagues/<int:league_id>/add-drop", methods=("POST",))
def add_drop(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    d = body()
    add_id = need_int(d, "add_id") if d.get("add_id") is not None else None
    drop_id = need_int(d, "drop_id") if d.get("drop_id") is not None else None
    tx.add_drop(lg, team, add_id, drop_id)
    return _roster_payload(lg, me, team)


# ----------------------------------------------------------------------------- players
SORT_KEYS = {"name", "fpg", "total", "proj", "last5", "rank", "age", "gp", "games_week"}


@api("/leagues/<int:league_id>/players")
def players(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    ctx = AthleteContext(lg)
    q = (request.args.get("search") or "").strip().lower()[:40]
    pos = request.args.get("pos")
    pro = request.args.get("team")
    status = request.args.get("status", "all")          # all | available | owned | mine
    inj = request.args.get("injury")                    # healthy | injured
    sort = request.args.get("sort", "proj")
    if sort not in SORT_KEYS and not sort.startswith("avg."):
        raise bad_request("Unknown sort key")
    desc = request.args.get("dir", "desc") != "asc"
    limit = int_arg("limit", 50, 1, 200)
    offset = int_arg("offset", 0, 0)
    rows = []
    for a in db.session.scalars(db.select(Athlete).where(Athlete.sport_id == lg.sport_id)):
        if q and q not in a.name.lower():
            continue
        if pos and pos not in a.position_list:
            continue
        if pro and a.pro_team.abbr != pro:
            continue
        owner = ctx.owners.get(a.id)
        if (status == "available" and owner) or (status == "owned" and not owner) or (status == "mine" and owner != team.id):
            continue
        st = a.injury_status(ctx.day + 1)
        if (inj == "healthy" and st != "HEALTHY") or (inj == "injured" and st == "HEALTHY"):
            continue
        rows.append(ctx.row(a))
    keyf = (lambda r: r["avg"].get(sort[4:], 0)) if sort.startswith("avg.") else (lambda r: r[sort])
    rows.sort(key=keyf, reverse=desc)
    return dict(total=len(rows), players=rows[offset:offset + limit], simulated=True,
                teams=[dict(abbr=t.abbr, name=f"{t.city} {t.name}") for t in db.session.scalars(db.select(ProTeam).where(ProTeam.sport_id == lg.sport_id).order_by(ProTeam.abbr))],
                positions=SPORTS[lg.sport.code]["positions"], stat_labels=SPORTS[lg.sport.code]["stats"])


@api("/leagues/<int:league_id>/players/<int:athlete_id>")
def player_profile(me, league_id, athlete_id):
    lg, team = league_svc.membership(me, league_id)
    a = get_athlete(athlete_id)
    if a.sport_id != lg.sport_id:
        raise not_found("Player not found")
    ctx = AthleteContext(lg)
    log = [dict(day=d, stats=s, fp=stats_svc.score_stat_line(s, lg.scoring.rules)) for d, s in stats_svc.game_log(lg.sport_id).get(a.id, []) if d <= lg.current_day]
    upcoming = _upcoming_games(lg, a.pro_team_id, 7)
    return dict(player=ctx.row(a), game_log=log[::-1], upcoming=upcoming, injury_window=dict(start=a.injury_start, end=a.injury_end, note=a.injury_note))


@api("/leagues/<int:league_id>/compare")
def compare(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    try:
        ids = [int(x) for x in (request.args.get("ids") or "").split(",") if x]
    except ValueError:
        raise bad_request("ids must be comma-separated player ids")
    if not 2 <= len(ids) <= 4:
        raise bad_request("Choose 2-4 players to compare")
    ctx = AthleteContext(lg)
    out = []
    for i in ids:
        a = get_athlete(i)
        if a.sport_id != lg.sport_id:
            raise not_found("Player not found")
        out.append(ctx.row(a))
    return dict(players=out, stat_labels=SPORTS[lg.sport.code]["stats"])


def _upcoming_games(lg: League, pro_team_id: int, days: int) -> list[dict]:
    games = db.session.scalars(db.select(ProGame).where(
        ProGame.sport_id == lg.sport_id, ProGame.day > lg.current_day, ProGame.day <= lg.current_day + days,
        db.or_(ProGame.home_team_id == pro_team_id, ProGame.away_team_id == pro_team_id)).order_by(ProGame.day))
    teams = {t.id: t.abbr for t in db.session.scalars(db.select(ProTeam).where(ProTeam.sport_id == lg.sport_id))}
    return [dict(day=g.day, opponent=teams[g.away_team_id if g.home_team_id == pro_team_id else g.home_team_id], home=g.home_team_id == pro_team_id) for g in games]


# ----------------------------------------------------------------------------- matchups / standings / activity
@api("/leagues/<int:league_id>/matchup")
def my_matchup(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    info = matchup_svc.week_info(lg, int_arg("week", None, 1, 30))
    m = matchup_svc.find_matchup(lg.id, team.id, info["week"])
    if not m:
        raise not_found("No matchup scheduled for that week")
    history = []
    for hm in db.session.scalars(db.select(Matchup).where(Matchup.league_id == lg.id, Matchup.final.is_(True),
                                                          db.or_(Matchup.home_team_id == team.id, Matchup.away_team_id == team.id)).order_by(Matchup.week)):
        mine_home = hm.home_team_id == team.id
        opp = db.session.get(FantasyTeam, hm.away_team_id if mine_home else hm.home_team_id)
        history.append(dict(week=hm.week, opponent=opp.name, points=hm.home_score if mine_home else hm.away_score,
                            opponent_points=hm.away_score if mine_home else hm.home_score))
    return dict(matchup=matchup_svc.matchup_detail(lg, m), my_team_id=team.id, week=info["week"], current_week=info["current_week"],
                total_weeks=league_json(lg, me, team)["season_weeks"], history=history)


@api("/leagues/<int:league_id>/matchups")
def week_matchups(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    info = matchup_svc.week_info(lg, int_arg("week", None, 1, 30))
    names = {t.id: t.name for t in league_svc.teams_of(lg.id)}
    rows = [dict(id=m.id, week=m.week, home_id=m.home_team_id, away_id=m.away_team_id, home=names[m.home_team_id], away=names[m.away_team_id],
                 home_score=m.home_score, away_score=m.away_score, final=m.final,
                 mine=team.id in (m.home_team_id, m.away_team_id))
            for m in db.session.scalars(db.select(Matchup).where(Matchup.league_id == lg.id, Matchup.week == info["week"]))]
    return dict(week=info["week"], current_week=info["current_week"], matchups=rows)


@api("/leagues/<int:league_id>/standings")
def standings(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    ws = matchup_svc.weekly_scores(lg)
    names = {t.id: t.name for t in league_svc.teams_of(lg.id)}
    history = [dict(week=w, **{names[tid]: rows[w - 1]["points"] for tid, rows in ws.items() if len(rows) >= w}) for w in range(1, max((len(r) for r in ws.values()), default=0) + 1)]
    return dict(standings=league_svc.standings(lg), power=league_svc.power_rankings(lg), weekly=history, my_team_id=team.id,
                formula="Power = 50 x win% + 30 x (avg points / best avg) + 20 x (last-3 avg / best last-3)")


@api("/leagues/<int:league_id>/activity")
def activity(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    rows = db.session.scalars(db.select(Activity).where(Activity.league_id == lg.id).order_by(Activity.id.desc()).limit(int_arg("limit", 40, 1, 200)))
    return [dict(id=a.id, kind=a.kind, message=a.message, day=a.day, at=a.created_at.isoformat()) for a in rows]


@api("/leagues/<int:league_id>/transactions")
def transactions(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    names = {t.id: t.name for t in league_svc.teams_of(lg.id)}
    rows = db.session.scalars(db.select(PlayerTransaction).where(PlayerTransaction.league_id == lg.id).order_by(PlayerTransaction.id.desc()).limit(100))
    return [dict(id=t.id, kind=t.kind, team=names[t.team_id], player=t.athlete.name, positions=t.athlete.positions, day=t.day,
                 related_team=names.get(t.related_team_id)) for t in rows]


@api("/leagues/<int:league_id>/what-if/lineup", methods=("POST",))
def what_if_lineup(me, league_id):
    from fantaball import whatif
    lg, team = league_svc.membership(me, league_id)
    d = body()
    return whatif.lineup_swap(lg, team, need_int(d, "day"), need_int(d, "in_id"), need_int(d, "out_id"))


# ----------------------------------------------------------------------------- dashboard
@api("/leagues/<int:league_id>/dashboard")
def dashboard(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    data = dict(league=league_json(lg, me, team), team=team_json(team, me), simulated=True)
    if lg.status != "active":
        data["activity"] = activity.__wrapped__(me, league_id)
        return data
    info = matchup_svc.week_info(lg)
    m = matchup_svc.find_matchup(lg.id, team.id, info["week"])
    st = league_svc.standings(lg)
    mine = next(r for r in st if r["team_id"] == team.id)
    ws = matchup_svc.weekly_scores(lg).get(team.id, [])
    if m:
        d = matchup_svc.matchup_detail(lg, m)
        mine_home = m.home_team_id == team.id
        side, opp = (d["home"], d["away"]) if mine_home else (d["away"], d["home"])
        data["matchup"] = dict(week=info["week"], my_points=side["points"], opp_points=opp["points"], my_projected=side["projected"],
                               opp_projected=opp["projected"], opponent=opp["name"], daily=side["daily_totals"], opp_daily=opp["daily_totals"],
                               win_prob=_win_prob(side["projected"], opp["projected"]), first_day=d["first_day"], last_day=d["last_day"])
    data["record"] = dict(w=mine["w"], l=mine["l"], t=mine["t"], rank=mine["rank"], pf=mine["pf"], pa=mine["pa"], streak=mine["streak"], playoff=mine["playoff"])
    data["recent_scores"] = [dict(week=x["week"], points=x["points"], opponent_points=x["opponent_points"]) for x in ws[-8:]]
    data["standings_top"] = st[:6]
    data["upcoming_games"] = _my_upcoming(lg, team)
    data["activity"] = activity.__wrapped__(me, league_id)[:8]
    data["pending_trades"] = db.session.scalar(db.select(db.func.count(TradeOffer.id)).where(TradeOffer.league_id == lg.id, TradeOffer.status == "pending", TradeOffer.to_team_id == team.id))
    data["gm"] = gm_svc.analyze(lg, team)
    return data


def _win_prob(mine: float, theirs: float) -> float:
    """Rough logistic win chance from projected final scores (scale ~ 6% of the total)."""
    import math
    scale = max((mine + theirs) * 0.03, 1.0)
    return round(1 / (1 + math.exp(-(mine - theirs) / scale)), 3)


def _my_upcoming(lg: League, team: FantasyTeam) -> list[dict]:
    """Next 3 days of pro games involving my starters, grouped by day."""
    starters = [s.athlete for s in team_slots(team.id) if s.slot not in ("BN", "IR")]
    out = []
    for day in range(lg.current_day + 1, min(lg.current_day + 3, SPORTS[lg.sport.code]["season_days"]) + 1):
        games = []
        for a in starters:
            for g in _upcoming_games(lg, a.pro_team_id, 3):
                if g["day"] == day:
                    games.append(dict(player=a.name, team=a.pro_team.abbr, opponent=g["opponent"], home=g["home"]))
        out.append(dict(day=day, games=games))
    return out


# Register the draft and trade endpoints (importing the modules adds their routes)
import views.api_draft  # noqa: E402, F401
import views.api_trades  # noqa: E402, F401
