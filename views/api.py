"""FantaBall REST API (JSON under /api). Core: profile, leagues, dashboard, roster, players, matchups, standings.
Draft and trade endpoints live in api_draft.py / api_trades.py. Business rules live in the `fantaball` package."""
from datetime import timedelta

from flask import current_app, request

from root import app, db
from models.fantasy import Activity, Athlete, FantasyTeam, League, Matchup, PlayerTransaction, ProGame, ProTeam, RosterSlot, TradeOffer
from fantaball import gm as gm_svc
from fantaball import leagues as league_svc
from fantaball import matchups as matchup_svc
from fantaball import stats as stats_svc
from fantaball import transactions as tx
from fantaball.errors import bad_request, conflict, forbidden, not_found
from fantaball.pool import pool_query
from fantaball.lineups import auto_set_lineup, set_lineup, team_slots
from fantaball.sports import PLAYABLE_SPORTS, SPORTS
from fantaball import timeline
from fantaball.scoring import score_float
from views.api_common import (AthleteContext, api, body, clean_display_name, get_athlete, int_arg, int_list, is_admin, league_json, need_int,
                              team_json)


@api("/health")
def health(me):
    return dict(ok=True)


# ----------------------------------------------------------------------------- profile
@api("/me")
def get_me(me):
    jwt_cfg = current_app.extensions.get("jwtauthmanager")
    local_login = bool(jwt_cfg and jwt_cfg.dummy_user_if_no_proxy and not jwt_cfg.is_behind_proxy())
    return dict(id=me.id, email=me.email, display_name=me.display_name, auth_mode="local" if local_login else "sso",
                logout_url=None if local_login else jwt_cfg.logout_path, is_admin=is_admin(me))


@api("/me", methods=("PATCH",))
def patch_me(me):
    me.display_name = clean_display_name(body().get("display_name"))
    db.session.commit()
    return dict(id=me.id, email=me.email, display_name=me.display_name)


@api("/sports")
def sports(me):
    """Sport definitions plus whether data for each is actually loaded (a sport with no data cannot host a league)."""
    from models.fantasy import Sport
    from fantaball.pool import pool_filter
    rows = {sp.code: sp for sp in db.session.scalars(db.select(Sport))}
    out = []
    for c, s in SPORTS.items():
        sp = rows.get(c)
        n = db.session.scalar(db.select(db.func.count(Athlete.id)).where(*pool_filter(sp.id))) if sp else 0
        out.append(dict(code=c, name=s["name"], positions=s["positions"], stats=s["stats"], default_scoring=s["default_scoring"],
                        roster=s["roster"], playable=c in PLAYABLE_SPORTS, players=n, available=bool(n) and c in PLAYABLE_SPORTS,
                        data_source=sp.data_source if sp else None, season=sp.season if sp else None))
    return out


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
    if not isinstance(d.get("sport"), str):
        raise bad_request("Choose which data the league uses ('sport' is required)")
    lg = league_svc.create_league(me, d.get("name"), d["sport"], d.get("num_teams", 12), d.get("scoring_rules"),
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


def player_list(ctx: AthleteContext, my_team_id: int | None = None) -> dict:
    """Filtered / sorted / paged player rows for one AthleteContext (a league, or a whole sport with league=None)."""
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
    for a in db.session.scalars(pool_query(ctx.sport_id)):
        if q and q not in a.name.lower():
            continue
        if pos and pos not in a.position_list:
            continue
        if pro and a.pro_team.abbr != pro:
            continue
        owner = ctx.owners.get(a.id)
        if (status == "available" and owner) or (status == "owned" and not owner) or (status == "mine" and owner != my_team_id):
            continue
        st = a.injury_status(ctx.day + 1)
        if (inj == "healthy" and st != "HEALTHY") or (inj == "injured" and st == "HEALTHY"):
            continue
        rows.append(ctx.row(a))
    value = (lambda r: r["avg"].get(sort[4:])) if sort.startswith("avg.") else (lambda r: r[sort])
    present = [r for r in rows if value(r) is not None]
    missing = [r for r in rows if value(r) is None]          # players with no data for this column always sort last
    present.sort(key=value, reverse=desc)
    rows = present + missing
    sport_code = ctx.sport.code
    return dict(total=len(rows), players=rows[offset:offset + limit], data_source=ctx.sport.data_source,
                as_of_day=ctx.day, empty=not rows and not (q or pos or pro or inj or status != "all"),
                teams=[dict(abbr=t.abbr, name=f"{t.city} {t.name}") for t in db.session.scalars(db.select(ProTeam).where(ProTeam.sport_id == ctx.sport_id).order_by(ProTeam.abbr))],
                positions=SPORTS[sport_code]["positions"], stat_labels=SPORTS[sport_code]["stats"])


@api("/leagues/<int:league_id>/players")
def players(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    return player_list(AthleteContext(lg), team.id)


def fantasy_points(sport, stats: dict, rules: dict):
    """Fantasy points for one stat line, or None when a stat the rules need was not reported (never a silent 0)."""
    return score_float(stats, rules)


def player_profile_payload(ctx: AthleteContext, a: Athlete) -> dict:
    sport = ctx.sport
    log = [dict(day=d, date=(timeline.date_of(sport, d).isoformat() if sport.season_start else None), stats=s, fp=fantasy_points(sport, s, ctx.rules))
           for d, s in stats_svc.game_log(ctx.sport_id).get(a.id, []) if d <= ctx.day]
    games = {g.day: g for g in db.session.scalars(db.select(ProGame).where(
        ProGame.sport_id == ctx.sport_id, ProGame.day.in_([x["day"] for x in log]), db.or_(ProGame.home_team_id == a.pro_team_id, ProGame.away_team_id == a.pro_team_id)))} if log else {}
    teams = {t.id: t.abbr for t in db.session.scalars(db.select(ProTeam).where(ProTeam.sport_id == ctx.sport_id))}
    for entry in log:
        g = games.get(entry["day"])
        if g and a.pro_team_id in (g.home_team_id, g.away_team_id):
            entry["opponent"] = teams[g.away_team_id if g.home_team_id == a.pro_team_id else g.home_team_id]
            entry["home"] = g.home_team_id == a.pro_team_id
    return dict(player=ctx.row(a), game_log=log[::-1], upcoming=upcoming_games(ctx.sport, a.pro_team_id, ctx.day, 7),
                stat_labels=SPORTS[ctx.sport.code]["stats"], injury_window=dict(start=a.injury_start, end=a.injury_end, note=a.injury_note))


@api("/leagues/<int:league_id>/players/<int:athlete_id>")
def player_profile(me, league_id, athlete_id):
    lg, team = league_svc.membership(me, league_id)
    a = get_athlete(athlete_id)
    if a.sport_id != lg.sport_id:
        raise not_found("Player not found")
    ctx = AthleteContext(lg)
    out = player_profile_payload(ctx, a)
    from fantaball.nba.scoring_service import rulesets_in_use
    out["rulesets"] = [dict(id=r.id, name="This league's rules" if r.id == lg.scoring.ruleset_id else (r.name or f"Custom rules #{r.id}"), rules=r.rules)
                       for r in rulesets_in_use(lg.sport_id)]
    out["ruleset_id"] = lg.scoring.ruleset_id
    return out


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


def upcoming_games(sport, pro_team_id: int, day: int, days: int) -> list[dict]:
    """A pro team's next games: from today on, not yet finished."""
    today = timeline.today()
    q = db.select(ProGame).where(ProGame.sport_id == sport.id, db.or_(ProGame.home_team_id == pro_team_id, ProGame.away_team_id == pro_team_id),
                                 ProGame.game_date >= today, ProGame.game_date <= today + timedelta(days=days), ProGame.status != "final")
    teams = {t.id: t.abbr for t in db.session.scalars(db.select(ProTeam).where(ProTeam.sport_id == sport.id))}
    return [dict(day=g.day, date=g.game_date.isoformat() if g.game_date else None, opponent=teams[g.away_team_id if g.home_team_id == pro_team_id else g.home_team_id],
                 home=g.home_team_id == pro_team_id) for g in db.session.scalars(q.order_by(ProGame.day))]


def _upcoming_games(lg: League, pro_team_id: int, days: int) -> list[dict]:
    return upcoming_games(lg.sport, pro_team_id, lg.current_day, days)


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
    data = dict(league=league_json(lg, me, team), team=team_json(team, me))
    data["data"] = data_block(lg)
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
    data["data"] = data_block(lg)
    data["upcoming_nba_games"] = upcoming_pro_games(lg.sport, lg.current_day, 3)
    data["recent_performances"] = recent_performances(lg, 8)
    data["pending_trades"] = db.session.scalar(db.select(db.func.count(TradeOffer.id)).where(TradeOffer.league_id == lg.id, TradeOffer.status == "pending", TradeOffer.to_team_id == team.id))
    data["gm"] = gm_svc.analyze(lg, team)
    return data


def data_block(lg: League) -> dict:
    """Where this league's numbers come from and how fresh they are (shown next to every statistic)."""
    from models.fantasy import DataSyncRun
    sport = lg.sport
    last_ok = db.session.scalar(db.select(db.func.max(DataSyncRun.finished_at)).where(DataSyncRun.provider == sport.data_source, DataSyncRun.status.in_(("success", "partial"))))
    last_stat = db.session.scalar(db.select(db.func.max(ProGame.stats_synced_at)).where(ProGame.sport_id == sport.id))
    return dict(source=sport.data_source, season=sport.season, last_sync=last_ok.isoformat() + "Z" if last_ok else None,
                stats_as_of=last_stat.isoformat() + "Z" if last_stat else None, scored_through=_scored_through(lg))


def _scored_through(lg: League):
    if lg.sport.season_start is None or lg.current_day < 1:
        return None
    return timeline.date_of(lg.sport, lg.current_day).isoformat()


def upcoming_pro_games(sport, day: int, days: int) -> list[dict]:
    """Next professional games (all teams) for the dashboard: from today on, not yet finished."""
    today = timeline.today()
    q = db.select(ProGame).where(ProGame.sport_id == sport.id, ProGame.postseason.is_(False), ProGame.game_date >= today,
                                 ProGame.game_date <= today + timedelta(days=days), ProGame.status != "final")
    teams = {t.id: t.abbr for t in db.session.scalars(db.select(ProTeam).where(ProTeam.sport_id == sport.id))}
    return [dict(day=g.day, date=g.game_date.isoformat() if g.game_date else None, starts_at=g.starts_at.isoformat() + "Z" if g.starts_at else None,
                 status=g.status, home=teams[g.home_team_id], away=teams[g.away_team_id]) for g in db.session.scalars(q.order_by(ProGame.day, ProGame.starts_at).limit(24))]


def recent_performances(lg: League, n: int) -> list[dict]:
    """Best fantasy performances of the last 3 scored days under the league's rules."""
    first = max(1, lg.current_day - 2)
    rules = lg.scoring.rules
    rows = []
    for aid, games in stats_svc.game_log(lg.sport_id).items():
        for d, st in games:
            if first <= d <= lg.current_day:
                fp = fantasy_points(lg.sport, st, rules)
                if fp is not None:
                    rows.append((fp, aid, d, st))
    rows.sort(key=lambda r: -r[0])
    out = []
    for fp, aid, d, st in rows[:n]:
        a = db.session.get(Athlete, aid)
        out.append(dict(athlete_id=aid, name=a.name, team=a.pro_team.abbr, positions=a.positions, day=d, fp=fp,
                        line={k: st.get(k) for k in ("pts", "reb", "ast", "stl", "blk", "tov", "fg3m")}))
    return out


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
import views.api_data  # noqa: E402, F401
