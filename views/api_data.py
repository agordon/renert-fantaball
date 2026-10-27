"""Data pipeline API: sync status (everyone), sport-level player database (no league needed), admin sync controls.

The API key is never returned. Admin actions are restricted to FLASK_ADMIN_EMAILS."""
import threading
from datetime import date, timedelta

from flask import current_app, request

from root import app, db
from models.fantasy import (Athlete, DataSyncRun, GameStat, League, PlayerFantasyScore, ProGame, ProTeam, ScoringRuleSet, Sport, utcnow)
from fantaball import timeline
from fantaball.errors import bad_request, conflict, not_found
from fantaball.nba import config as nba_config
from fantaball.nba import ingest
from fantaball.nba.provider import ProviderError
from fantaball.pool import pool_filter
from fantaball.rulesets import ensure_default_template
from fantaball.sports import PLAYABLE_SPORTS, SPORTS
from views.api import player_list, player_profile_payload, upcoming_pro_games
from views.api_common import AthleteContext, api, body, get_athlete, int_arg, is_admin, require_admin

JOBS = ("teams_players", "schedule", "stats", "corrections", "scores", "daily")


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def _run_json(r: DataSyncRun, admin: bool = False) -> dict:
    out = dict(id=r.id, provider=r.provider, job=r.job_type, status=r.status, started_at=_iso(r.started_at), finished_at=_iso(r.finished_at),
               inserted=r.inserted, updated=r.updated, skipped=r.skipped, requests=r.requests_made, marker=r.marker, triggered_by=r.triggered_by)
    out["error"] = r.error
    if admin:
        out["steps"] = (r.params or {}).get("steps")
    return out


def _sport_for(code: str) -> Sport:
    if code not in PLAYABLE_SPORTS:
        raise bad_request("Unknown sport")
    sport = db.session.scalar(db.select(Sport).where(Sport.code == code))
    if sport is None or not db.session.scalar(db.select(db.func.count(Athlete.id)).where(*pool_filter(sport.id))):
        raise not_found("No data has been imported for that sport yet")
    return sport


# ----------------------------------------------------------------------------- status
@api("/data/status")
def data_status(me):
    cfg = nba_config.provider_status(current_app.config)
    sport = db.session.scalar(db.select(Sport).where(Sport.code == "nba"))
    provider = sport.data_source if sport else cfg["provider"]
    counts = dict(teams=0, players=0, games=0, final_games=0, upcoming_games=0, final_games_missing_stats=0, player_game_stats=0, fantasy_scores=0)
    if sport:
        counts = dict(
            teams=db.session.scalar(db.select(db.func.count(ProTeam.id)).where(ProTeam.sport_id == sport.id)),
            players=db.session.scalar(db.select(db.func.count(Athlete.id)).where(*pool_filter(sport.id))),
            games=db.session.scalar(db.select(db.func.count(ProGame.id)).where(ProGame.sport_id == sport.id)),
            final_games=db.session.scalar(db.select(db.func.count(ProGame.id)).where(ProGame.sport_id == sport.id, ProGame.status == "final")),
            upcoming_games=db.session.scalar(db.select(db.func.count(ProGame.id)).where(ProGame.sport_id == sport.id, ProGame.status == "scheduled")),
            final_games_missing_stats=db.session.scalar(db.select(db.func.count(ProGame.id)).where(ProGame.sport_id == sport.id, ProGame.status == "final", ProGame.stats_synced_at.is_(None))),
            player_game_stats=db.session.scalar(db.select(db.func.count(GameStat.id)).join(Athlete, Athlete.id == GameStat.athlete_id).where(Athlete.sport_id == sport.id)),
            fantasy_scores=db.session.scalar(db.select(db.func.count(PlayerFantasyScore.id)).join(Athlete, Athlete.id == PlayerFantasyScore.athlete_id).where(Athlete.sport_id == sport.id)))
    runs = list(db.session.scalars(db.select(DataSyncRun).where(DataSyncRun.provider == provider).order_by(DataSyncRun.id.desc()).limit(30)))
    last_attempt = runs[0] if runs else None
    last_success = next((r for r in runs if r.status == "success"), None)
    last_by_job = {}
    for r in runs:
        last_by_job.setdefault(r.job_type, _run_json(r))
    failures = [_run_json(r) for r in runs if r.status in ("failed", "blocked", "partial")][:5]

    limitations = []
    for r in runs:                       # most recent run that touched stats decides whether the plan limitation is current
        steps = (r.params or {}).get("steps") or []
        stats_step = next((s for s in steps if s["name"] == "stats"), None)
        if r.job_type == "stats" and r.status == "blocked" or (stats_step and stats_step["status"] == "blocked"):
            limitations.append("Game player statistics are not available with the current provider plan (BALLDONTLIE returns HTTP 401 for /stats on the free plan). "
                               "Fantasy points from real box scores need the ALL-STAR plan ($9.99/month). Teams, players and schedules still sync.")
            break
        if r.job_type in ("stats", "daily") and r.status in ("success", "partial"):
            break
    freshness_seconds = int((utcnow() - last_success.finished_at).total_seconds()) if last_success and last_success.finished_at else None
    running = any(r.status == "running" for r in runs)
    return dict(provider=cfg, data_source=provider, season=sport.season if sport else nba_config.current_season(current_app.config),
                season_start=sport.season_start.isoformat() if sport and sport.season_start else None, today=timeline.today().isoformat(),
                counts=counts, last_success=_run_json(last_success) if last_success else None, last_attempt=_run_json(last_attempt) if last_attempt else None,
                last_by_job=last_by_job, failures=failures, freshness_seconds=freshness_seconds, running=running, limitations=limitations,
                has_real_data=bool(sport and counts["players"]), demo_data_enabled=bool(current_app.config.get("DEMO_DATA")), is_admin=is_admin(me),
                onboarding=None if (sport and counts["players"]) else
                "No real NBA data has been imported yet. Set BALLDONTLIE_API_KEY in .env, then run `npm run sync` (or use the sync controls on the Data Admin page).")


@api("/data/runs")
def data_runs(me):
    require_admin(me)
    limit = int_arg("limit", 30, 1, 200)
    return [_run_json(r, admin=True) for r in db.session.scalars(db.select(DataSyncRun).order_by(DataSyncRun.id.desc()).limit(limit))]


# ----------------------------------------------------------------------------- admin sync
def _execute(job: str, params: dict, triggered_by: str):
    provider = nba_config.build_provider(current_app.config)
    if job == "teams_players":
        return ingest.job_teams_players(provider, triggered_by=triggered_by)
    if job == "schedule":
        return ingest.job_schedule(provider, season=params.get("season"), start=params.get("start"), end=params.get("end"), triggered_by=triggered_by)
    if job == "stats":
        return ingest.job_stats(provider, dates=params.get("dates"), triggered_by=triggered_by)
    if job == "corrections":
        return ingest.job_corrections(provider, days=params.get("days", 3), triggered_by=triggered_by)
    if job == "scores":
        return ingest.job_recalculate_scores(provider.name, triggered_by=triggered_by)
    return ingest.job_daily(provider, triggered_by=triggered_by)


def _parse_params(d: dict) -> dict:
    out = {}
    for key in ("start", "end"):
        if d.get(key):
            try:
                out[key] = date.fromisoformat(str(d[key]))
            except ValueError:
                raise bad_request(f"'{key}' must be a date like 2026-10-27")
    if d.get("season") not in (None, ""):
        if isinstance(d["season"], bool) or not isinstance(d["season"], int) or not 1990 <= d["season"] <= 2100:
            raise bad_request("'season' must be a start year such as 2026")
        out["season"] = d["season"]
    if d.get("days") not in (None, ""):
        if isinstance(d["days"], bool) or not isinstance(d["days"], int) or not 1 <= d["days"] <= 14:
            raise bad_request("'days' must be 1-14")
        out["days"] = d["days"]
    if out.get("start") and out.get("end") and out["end"] < out["start"]:
        raise bad_request("'end' must not be before 'start'")
    if out.get("start") and out.get("end") and (out["end"] - out["start"]).days > 400:
        raise bad_request("Date range too large")
    return out


@api("/admin/sync", methods=("POST",))
def admin_sync(me):
    """Start a sync job. It runs in the background (real syncs are slow on the free rate limit); poll /api/data/status."""
    require_admin(me)
    d = body()
    job = d.get("job")
    if job not in JOBS:
        raise bad_request(f"job must be one of: {', '.join(JOBS)}")
    params = _parse_params(d)
    if job == "stats" and params.get("start"):          # backfill / re-import box scores for a date range
        first, last = params["start"], params.get("end") or params["start"]
        if (last - first).days > 60:
            raise bad_request("Re-import at most 60 days of box scores at a time")
        params["dates"] = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    cfg = nba_config.provider_status(current_app.config)
    if not cfg["configured"] and job != "scores":
        raise conflict(cfg["message"] or "The data provider is not configured")
    if db.session.scalar(db.select(DataSyncRun.id).where(DataSyncRun.status == "running")):
        raise conflict("A data sync is already running.")
    triggered_by = f"admin:{me.email}"
    flask_app = current_app._get_current_object()
    if flask_app.config.get("SYNC_INLINE"):          # tests: run synchronously
        run = _execute(job, params, triggered_by)
        return _run_json(run, admin=True), 200

    def work():
        with flask_app.app_context():
            try:
                _execute(job, params, triggered_by)
            except Exception:                         # noqa: BLE001 - already recorded by run_job, or nothing started
                flask_app.logger.exception("admin sync %s failed to start", job)
            finally:
                db.session.remove()
    threading.Thread(target=work, name=f"sync-{job}", daemon=True).start()
    return dict(accepted=True, job=job), 202


# ----------------------------------------------------------------------------- sport-level player database (no league needed)
def _ruleset(sport: Sport) -> ScoringRuleSet:
    rid = int_arg("ruleset_id")
    if rid is None:
        return ensure_default_template(sport)
    rs = db.session.get(ScoringRuleSet, rid)
    if rs is None or rs.sport_id != sport.id:
        raise bad_request("Unknown scoring rule set")
    return rs


@api("/data/rulesets")
def data_rulesets(me):
    sport = _sport_for(request.args.get("sport", "nba"))
    from fantaball.nba.scoring_service import rulesets_in_use
    ensure_default_template(sport)
    return [dict(id=r.id, name=r.name or f"Custom rules #{r.id}", rules=r.rules, is_template=r.is_template) for r in rulesets_in_use(sport.id)]


@api("/data/players")
def data_players(me):
    sport = _sport_for(request.args.get("sport", "nba"))
    ctx = AthleteContext(None, sport=sport, ruleset=_ruleset(sport))
    out = player_list(ctx)
    out["ruleset_id"] = _ruleset(sport).id
    return out


@api("/data/players/<int:athlete_id>")
def data_player(me, athlete_id):
    a = get_athlete(athlete_id)
    sport = db.session.get(Sport, a.sport_id)
    rs = _ruleset(sport)
    out = player_profile_payload(AthleteContext(None, sport=sport, ruleset=rs), a)
    from fantaball.nba.scoring_service import rulesets_in_use
    out["rulesets"] = [dict(id=r.id, name=r.name or f"Custom rules #{r.id}", rules=r.rules) for r in rulesets_in_use(sport.id)]
    out["ruleset_id"] = rs.id
    return out


@api("/data/games/upcoming")
def data_upcoming(me):
    sport = _sport_for(request.args.get("sport", "nba"))
    from views.api_common import sport_day
    return upcoming_pro_games(sport, sport_day(sport), int_arg("days", 3, 1, 14))
