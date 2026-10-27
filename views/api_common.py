"""Shared helpers for the FantaBall REST API: auth -> Manager, JSON errors, CORS, CSRF-style checks, serializers."""
import re
from functools import wraps

from flask import current_app, jsonify, request

from flask_jwt_auth_manager import current_jwt_user
from root import app, db
from models.fantasy import Athlete, FantasyTeam, GameStat, League, Manager
from fantaball import stats as stats_svc
from fantaball.errors import ApiError, bad_request, not_found
from fantaball.lineups import owner_map, rules_of
from fantaball.sports import SPORTS

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def allowed_origins() -> list[str]:
    origins = current_app.config.get("CORS_ORIGINS") or []
    return origins if isinstance(origins, list) else [origins]


@app.after_request
def _cors(resp):
    if request.path.startswith("/api/"):
        origin = request.headers.get("Origin")
        if origin and origin in allowed_origins():
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            resp.headers["Vary"] = "Origin"
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(ApiError)
def _api_error(err):
    db.session.rollback()
    return jsonify(error=err.message), err.status


@app.errorhandler(Exception)
def _unhandled(err):
    from werkzeug.exceptions import HTTPException
    if isinstance(err, HTTPException):
        if request.path.startswith("/api/"):
            return jsonify(error=err.description if err.code < 500 else "Server error"), err.code
        return err
    db.session.rollback()
    if request.path.startswith("/api/"):
        current_app.logger.exception("Unhandled API error")
        return jsonify(error="Unexpected server error"), 500
    raise err


def current_manager() -> Manager:
    """The FantaBall Manager for the authenticated (JWT / dev dummy) user; created on first sight."""
    user = current_jwt_user._get_current_object()
    email = getattr(user, "email", None) if user is not None else None
    if not email:
        raise ApiError("Not authenticated", 401)
    email = email.strip().lower()
    mgr = db.session.scalar(db.select(Manager).where(Manager.email == email))
    if not mgr:
        name = getattr(user, "name", None) or email.split("@")[0]
        mgr = Manager(email=email, display_name=str(name)[:40])
        db.session.add(mgr)
        db.session.commit()
    return mgr


def api(rule: str, methods=("GET",)):
    """Route decorator: /api prefix, JSON-only mutations, Origin check, authenticated manager passed as first argument."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if request.method in MUTATING:
                origin = request.headers.get("Origin")
                if origin and origin not in allowed_origins() and origin.split("://", 1)[-1] != request.host:
                    raise ApiError("Origin not allowed", 403)
                if request.content_length and not request.is_json:
                    raise ApiError("Content-Type must be application/json", 415)
            return fn(current_manager(), *args, **kwargs)
        app.add_url_rule("/api" + rule, endpoint=fn.__name__, view_func=wrapper, methods=list(methods))
        return wrapper
    return deco


def body() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise bad_request("JSON body must be an object")
    return data


def int_arg(name, default=None, lo=None, hi=None):
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        v = int(raw)
    except ValueError:
        raise bad_request(f"'{name}' must be a whole number")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise bad_request(f"'{name}' is out of range")
    return v


def need_int(data: dict, key: str) -> int:
    v = data.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise bad_request(f"'{key}' must be a whole number")
    return v


def int_list(data: dict, key: str) -> list[int]:
    v = data.get(key)
    if not isinstance(v, list) or any(isinstance(i, bool) or not isinstance(i, int) for i in v):
        raise bad_request(f"'{key}' must be a list of whole numbers")
    return v


# ---------------------------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------------------------
def team_json(t: FantasyTeam, me: Manager | None = None) -> dict:
    return dict(id=t.id, name=t.name, manager=t.manager.display_name, is_bot=t.is_bot, is_me=bool(me and t.manager_id == me.id),
                draft_slot=t.draft_slot)


def league_json(league: League, me: Manager, team: FantasyTeam | None = None) -> dict:
    sp = SPORTS[league.sport.code]
    simulated = league.sport.data_source == "demo"
    return dict(id=league.id, name=league.name, sport=league.sport.code, sport_name=league.sport.name, format=league.format,
                num_teams=league.num_teams, status=league.status, current_day=league.current_day,
                current_week=stats_svc.week_of_day(league.current_day + 1, sp["days_per_week"]),
                season_days=sp["season_days"], season_weeks=sp["season_days"] // sp["days_per_week"],
                is_demo=league.is_demo, is_commissioner=league.commissioner_id == me.id, my_team_id=team.id if team else None,
                data_source=league.sport.data_source, is_simulated=simulated, is_mock=league.sport.data_source == "mock",
                season=league.season, auto_scored=not simulated,
                scored_through=_date_of_day(league.sport, league.current_day) if not simulated else None)


def _date_of_day(sport, day: int):
    from fantaball import timeline
    if sport.season_start is None or day < 1:
        return None
    return timeline.date_of(sport, day).isoformat()


class AthleteContext:
    """Per-request bundle so athlete rows are cheap to build. Works for a league (ownership, league scoring rules) or,
    with league=None, for a whole sport browsed without a league (stored scoring rule set `ruleset`)."""

    def __init__(self, league: League | None = None, day: int | None = None, *, sport=None, ruleset=None):
        self.league = league
        self.sport = league.sport if league else sport
        self.sport_id = self.sport.id
        if league is not None:
            self.day = league.current_day if day is None else day
            self.rules = rules_of(league)
            self.owners = owner_map(league.id)
            self.team_names = {t.id: t.name for t in db.session.scalars(db.select(FantasyTeam).where(FantasyTeam.league_id == league.id))}
        else:
            self.day = sport_day(self.sport) if day is None else day
            self.rules = ruleset.rules
            self.owners, self.team_names = {}, {}
        self.summ = stats_svc.summaries(self.sport_id, self.rules, self.day)
        sp = SPORTS[self.sport.code]
        self.week = stats_svc.week_of_day(self.day + 1, sp["days_per_week"])
        self.week_first, self.week_last = stats_svc.week_bounds(self.week, sp["days_per_week"])

    def row(self, a: Athlete, full=False) -> dict:
        s = self.summ[a.id]
        owner = self.owners.get(a.id)
        status = a.injury_status(self.day + 1)
        return dict(
            id=a.id, name=a.name, positions=a.positions, team=a.pro_team.abbr, team_name=f"{a.pro_team.city} {a.pro_team.name}", age=a.age,
            rank=a.rank, injury=status, injury_note=a.injury_note if status != "HEALTHY" else None,
            gp=s["gp"], avg=s["avg"], total=s["total"], fpg=s["fpg"], last5=s["last5"], proj=s["proj"],
            owner_team_id=owner, owner_team=self.team_names.get(owner), available=owner is None,
            games_week=stats_svc.games_in_window(self.sport_id, a.pro_team_id, self.week_first, self.week_last),
            games_left_week=stats_svc.games_in_window(self.sport_id, a.pro_team_id, max(self.week_first, self.day + 1), self.week_last),
            recent=[r["fp"] for r in s["recent"]], simulated=self.sport.data_source == "demo", data_source=self.sport.data_source,
            height=a.height, weight=a.weight, active=a.active,
        )


def sport_day(sport) -> int:
    """'Now' for a sport browsed without a league: last day with scored games (real) / last simulated day with stats (demo)."""
    from fantaball import timeline
    if sport.data_source == "demo":
        return db.session.scalar(db.select(db.func.max(GameStat.day)).join(Athlete, Athlete.id == GameStat.athlete_id).where(Athlete.sport_id == sport.id)) or 0
    from fantaball.nba import league_sync
    return league_sync.completed_through_day(sport)


def admin_emails() -> set[str]:
    raw = current_app.config.get("ADMIN_EMAILS") or []
    if isinstance(raw, str):
        raw = [x for x in raw.replace(";", ",").split(",")]
    return {str(e).strip().lower() for e in raw if str(e).strip()}


def is_admin(me: Manager) -> bool:
    return me.email.lower() in admin_emails()


def require_admin(me: Manager):
    if not is_admin(me):
        raise ApiError("Administrator access required", 403)


def get_athlete(athlete_id: int) -> Athlete:
    a = db.session.get(Athlete, athlete_id)
    if not a:
        raise not_found("Player not found")
    return a


_name_re = re.compile(r"[\x00-\x1f<>]")


def clean_display_name(raw) -> str:
    if not isinstance(raw, str):
        raise bad_request("Display name must be text")
    name = " ".join(_name_re.sub("", raw).split())
    if not 2 <= len(name) <= 40:
        raise bad_request("Display name must be 2-40 characters")
    return name
