"""Database ingestion for the NBA data pipeline.

Design rules
  * The provider (network) is kept apart from this module (database): jobs take any NBADataProvider.
  * Every write is an IDEMPOTENT upsert keyed by the provider's stable ids, so re-running a job never duplicates rows.
  * Work is committed in small batches (one per team / date-chunk); a failure rolls back the current batch only,
    leaving every committed batch complete and consistent. Re-running resumes where it stopped.
  * Every job is recorded in DataSyncRun. A partial unique index allows ONE running job per provider, so two
    schedulers / web workers can never run the same job at once.
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from flask import current_app
from sqlalchemy.exc import IntegrityError

from root import db
from models.fantasy import Athlete, DataSyncRun, GameStat, League, ProGame, ProTeam, Sport, utcnow
from fantaball import timeline
from fantaball.errors import ApiError
from fantaball.nba import config as nba_config
from fantaball.nba.provider import (NBADataProvider, ProviderAccessError, ProviderAuthError, ProviderError, STAT_FIELDS, StatRecord)
from fantaball.rulesets import ensure_default_template
from fantaball.scoring import score_float

log = logging.getLogger("fantaball.nba.ingest")

STATS_DATE_CHUNK = 5          # dates per stats request series (each date ~ 3 pages of 100 rows)
GIVE_UP_NO_BOX_SCORE_DAYS = 3  # a final game with no box score after this many days stops being retried
STALE_RUN_AFTER = timedelta(hours=3)

# provider position text -> our fantasy positions (PG SG SF PF C). Unknown -> "" (stored, but not draftable).
POSITION_MAP = {"G": "PG,SG", "F": "SF,PF", "C": "C", "G-F": "SG,SF", "F-G": "SF,SG", "F-C": "PF,C", "C-F": "C,PF",
                "PG": "PG", "SG": "SG", "SF": "SF", "PF": "PF", "PG-SG": "PG,SG", "SG-SF": "SG,SF", "SF-PF": "SF,PF", "PF-C": "PF,C"}


def map_position(raw: str | None) -> str:
    return POSITION_MAP.get((raw or "").strip().upper(), "")


class IngestError(ApiError):
    """A pipeline precondition failed (e.g. teams not imported yet). Safe to show to the user."""


class SyncAlreadyRunning(IngestError):
    def __init__(self):
        super().__init__("A data sync is already running. Wait for it to finish (see Data Administration).", 409)


@dataclass
class Counts:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    notes: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    changed_stat_ids: set = field(default_factory=set)       # GameStat ids inserted/changed -> fantasy scores need recalculation
    changed_days: set = field(default_factory=set)
    blocked: bool = False


def _apply(obj, **values) -> bool:
    changed = False
    for k, v in values.items():
        if getattr(obj, k) != v:
            setattr(obj, k, v)
            changed = True
    return changed


# ---------------------------------------------------------------------------------------------
# Sport / season bookkeeping
# ---------------------------------------------------------------------------------------------
def ensure_sport(provider: NBADataProvider) -> Sport:
    sport = db.session.scalar(db.select(Sport).where(Sport.code == "nba"))
    if sport is None:
        sport = Sport(code="nba", name="NBA Basketball", data_source=provider.name, season=nba_config.current_season(current_app.config))
        configured_start = nba_config._get(current_app.config, "NBA_SEASON_START")
        if configured_start:
            sport.season_start = timeline.monday_on_or_before(date.fromisoformat(str(configured_start)))
        db.session.add(sport)
        db.session.flush()
        ensure_default_template(sport)
        db.session.commit()
    elif sport.data_source != provider.name:
        raise IngestError(f"NBA data in this database came from '{sport.data_source}'. Refusing to mix in data from '{provider.name}'. "
                          "Use a separate database, or run `flask nba purge-data --yes` (only possible while no league uses the NBA data).")
    return sport


def purge_sport_data(sport: Sport):
    """Delete all imported rows for the real-data sport (dev tool for switching providers). Refuses if leagues exist."""
    if db.session.scalar(db.select(db.func.count(League.id)).where(League.sport_id == sport.id)):
        raise IngestError("Leagues already use this data - purge is not allowed.", 409)
    from models.fantasy import PlayerFantasyScore
    aid = db.select(Athlete.id).where(Athlete.sport_id == sport.id)
    db.session.execute(db.delete(PlayerFantasyScore).where(PlayerFantasyScore.athlete_id.in_(aid)))
    db.session.execute(db.delete(GameStat).where(GameStat.athlete_id.in_(aid)))
    db.session.execute(db.delete(ProGame).where(ProGame.sport_id == sport.id))
    db.session.execute(db.delete(Athlete).where(Athlete.sport_id == sport.id))
    db.session.execute(db.delete(ProTeam).where(ProTeam.sport_id == sport.id))
    from models.fantasy import ScoringRuleSet
    db.session.execute(db.delete(ScoringRuleSet).where(ScoringRuleSet.sport_id == sport.id))
    db.session.delete(sport)
    db.session.commit()


# ---------------------------------------------------------------------------------------------
# Jobs (functions taking provider + Counts; they commit their own batches)
# ---------------------------------------------------------------------------------------------
def sync_teams_and_players(provider: NBADataProvider, sport: Sport, counts: Counts) -> str:
    now = utcnow()
    existing = {t.provider_id: t for t in db.session.scalars(db.select(ProTeam).where(ProTeam.sport_id == sport.id, ProTeam.provider == provider.name))}
    for rec in provider.teams():
        values = dict(abbr=rec.abbr, city=rec.city, name=rec.name, conference=rec.conference, division=rec.division)
        team = existing.get(rec.provider_id)
        if team is None:
            db.session.add(ProTeam(sport_id=sport.id, provider=provider.name, provider_id=rec.provider_id, synced_at=now, **values))
            counts.inserted += 1
        elif _apply(team, **values):
            team.synced_at = now
            counts.updated += 1
        else:
            counts.skipped += 1
    db.session.commit()
    team_by_pid = {t.provider_id: t for t in db.session.scalars(db.select(ProTeam).where(ProTeam.sport_id == sport.id, ProTeam.provider == provider.name))}

    if not provider.supports_rosters:       # players are created from box scores (see sync_stats)
        recompute_ranks(sport)
        return f"{len(team_by_pid)} teams (this provider cannot list players: they are added from box scores)"
    athletes = {a.provider_id: a for a in db.session.scalars(db.select(Athlete).where(Athlete.sport_id == sport.id, Athlete.provider == provider.name))}
    seen: set[int] = set()
    for team_pid, team in team_by_pid.items():
        batch = list(provider.players([team_pid]))              # a failure here aborts before touching this team's rows
        for rec in batch:
            if rec.team_provider_id not in team_by_pid:
                counts.skipped += 1
                continue
            seen.add(rec.provider_id)
            _upsert_player(sport, provider.name, rec, team_by_pid[rec.team_provider_id], athletes, counts, now)
        db.session.commit()
    # Players of this provider who were not listed on any current roster become inactive (history is kept).
    for pid, a in athletes.items():
        if pid not in seen and a.active:
            a.active = False
            counts.updated += 1
    db.session.commit()
    recompute_ranks(sport)
    return f"{len(team_by_pid)} teams, {len(seen)} players"


def _upsert_player(sport, provider_name, rec, team, athletes, counts, now):
    name = f"{rec.first_name} {rec.last_name}".strip()
    values = dict(name=name, first_name=rec.first_name, last_name=rec.last_name, positions=map_position(rec.position), provider_position=rec.position,
                  height=rec.height, weight=rec.weight, pro_team_id=team.id, meta=rec.meta or None, active=True)
    a = athletes.get(rec.provider_id)
    if a is not None:                       # never erase information a later response happens not to repeat
        for keep in ("positions", "provider_position", "height", "weight", "meta"):
            if not values[keep]:
                values.pop(keep)
    if a is None:
        a = Athlete(sport_id=sport.id, provider=provider_name, provider_id=rec.provider_id, rank=1_000_000, age=None, synced_at=now, **values)
        db.session.add(a)
        athletes[rec.provider_id] = a
        counts.inserted += 1
    elif _apply(a, **values):
        a.synced_at = now
        counts.updated += 1
    else:
        counts.skipped += 1
    return a


def recompute_ranks(sport: Sport):
    """Rank = order of season-to-date fantasy points per game (damped for tiny samples), default scoring. No stats -> by name."""
    from fantaball.rulesets import ensure_default_template
    rules = ensure_default_template(sport).rules
    totals: dict[int, list] = {}
    rows = db.session.execute(db.select(GameStat.athlete_id, GameStat.stats).join(Athlete, Athlete.id == GameStat.athlete_id).where(Athlete.sport_id == sport.id)).all()
    for aid, stats in rows:
        t = totals.setdefault(aid, [0.0, 0])
        fp = score_float(stats, rules)
        if fp is not None:                       # lines that cannot be scored do not count towards the ranking
            t[0] += fp
            t[1] += 1
    athletes = list(db.session.scalars(db.select(Athlete).where(Athlete.sport_id == sport.id)))

    def key(a: Athlete):
        eligible = bool(a.positions) and a.active
        total, gp = totals.get(a.id, [0.0, 0])
        value = (total / gp) * (gp / (gp + 3)) if gp else -1.0
        return (not eligible, -value, a.last_name or "", a.first_name or "", a.id)

    for rank, a in enumerate(sorted(athletes, key=key), start=1):
        if a.rank != rank:
            a.rank = rank
    db.session.commit()


def sync_games(provider: NBADataProvider, sport: Sport, counts: Counts, *, season: int | None = None, start: date | None = None, end: date | None = None) -> str:
    team_by_pid = {t.provider_id: t for t in db.session.scalars(db.select(ProTeam).where(ProTeam.sport_id == sport.id, ProTeam.provider == provider.name))}
    if not team_by_pid:
        raise IngestError("No NBA teams imported yet - run the teams/players sync first.")
    records = list(provider.games(season=season, start_date=start, end_date=end))
    configured_start = nba_config._get(current_app.config, "NBA_SEASON_START")      # an explicit setting always wins (e.g. a provider that also lists preseason)
    if configured_start:
        sport.season_start = timeline.monday_on_or_before(date.fromisoformat(str(configured_start)))
    if sport.season_start is None:
        if season is None or start is not None or end is not None:
            raise IngestError("The season start date is not known yet. Run a FULL-season schedule sync first (flask nba sync-games --season).")
        regular = [r.game_date for r in records if not r.postseason]
        if not regular:
            raise IngestError("The provider returned no regular-season games, so the season start cannot be determined.")
        sport.season_start = timeline.monday_on_or_before(min(regular))
        if season is not None:
            sport.season = season
    now = utcnow()
    existing = {g.provider_id: g for g in db.session.scalars(db.select(ProGame).where(ProGame.sport_id == sport.id, ProGame.provider == provider.name))}
    for rec in records:
        home, away = team_by_pid.get(rec.home_team_id), team_by_pid.get(rec.away_team_id)
        day = timeline.day_of(sport, rec.game_date)
        if home is None or away is None or day is None or day < 1:
            counts.skipped += 1                 # unknown team (e.g. exhibition) or before the regular season
            continue
        values = dict(home_team_id=home.id, away_team_id=away.id, day=day, game_date=rec.game_date, starts_at=rec.starts_at, season=rec.season,
                      postseason=rec.postseason, status=rec.status, home_score=rec.home_score, away_score=rec.away_score)
        g = existing.get(rec.provider_id)
        if g is None:
            g = ProGame(sport_id=sport.id, provider=provider.name, provider_id=rec.provider_id, synced_at=now, **values)
            db.session.add(g)
            existing[rec.provider_id] = g
            counts.inserted += 1
        elif _apply(g, **values):
            g.synced_at = now
            counts.updated += 1
        else:
            counts.skipped += 1
    db.session.commit()
    lo = min((r.game_date for r in records), default=None)
    hi = max((r.game_date for r in records), default=None)
    note = "" if configured_start or sport.season_start is None else f"; season day 1 = {sport.season_start} (earliest game {lo})"
    return f"{lo}..{hi} ({len(records)} games){note}" if records else "no games returned"


def _stat_values(rec: StatRecord) -> tuple[dict, dict]:
    typed = {f: getattr(rec, f) for f in STAT_FIELDS}
    scoring_view = {("min" if k == "minutes" else k): v for k, v in typed.items() if v is not None}
    return typed, scoring_view


def sync_stats(provider: NBADataProvider, sport: Sport, counts: Counts, *, dates: list[date] | None = None, only_missing: bool = True) -> str:
    """Import box scores for FINAL games. Default: only games whose stats were never imported (the minimum number of requests).
    With explicit `dates` (corrections) the dates are re-fetched and rows are updated when the provider's numbers changed."""
    q = db.select(ProGame).where(ProGame.sport_id == sport.id, ProGame.provider == provider.name, ProGame.status == "final")
    if dates:
        q = q.where(ProGame.game_date.in_(dates))
    elif only_missing:
        q = q.where(ProGame.stats_synced_at.is_(None))
    games = list(db.session.scalars(q.order_by(ProGame.game_date)))
    if not games:
        return "nothing to import"
    by_date: dict[date, list[ProGame]] = {}
    for g in games:
        by_date.setdefault(g.game_date, []).append(g)
    date_list = sorted(by_date)
    team_by_pid = {t.provider_id: t for t in db.session.scalars(db.select(ProTeam).where(ProTeam.sport_id == sport.id, ProTeam.provider == provider.name))}
    athletes = {a.provider_id: a for a in db.session.scalars(db.select(Athlete).where(Athlete.sport_id == sport.id, Athlete.provider == provider.name))}
    game_by_pid = {g.provider_id: g for g in games}
    today = timeline.today()

    if provider.stats_by == "game":         # one request per game: commit in small batches so a failure loses little work
        chunks = [([], games[i:i + provider.stats_chunk]) for i in range(0, len(games), provider.stats_chunk)]
    else:
        chunks = [(date_list[i:i + STATS_DATE_CHUNK], [g for d in date_list[i:i + STATS_DATE_CHUNK] for g in by_date[d]])
                  for i in range(0, len(date_list), STATS_DATE_CHUNK)]
    known_positions = {pid for pid, a in athletes.items() if a.positions}

    for chunk_dates, chunk_games in chunks:
        if provider.stats_by == "game":
            rows = list(provider.stats(game_ids=[g.provider_id for g in chunk_games], known_player_ids=known_positions))
        else:
            rows = list(provider.stats(dates=chunk_dates))           # may raise (blocked plan / outage): earlier chunks stay committed
        try:
            existing = {(s.athlete_id, s.pro_game_id): s for s in db.session.scalars(
                db.select(GameStat).where(GameStat.pro_game_id.in_([g.id for g in chunk_games])))}
            now = utcnow()
            games_with_rows: set[int] = set()
            latest: dict[tuple[int, int], StatRecord] = {}
            for rec in rows:                                       # duplicates in a response: the last one wins
                latest[(rec.player_provider_id, rec.game_provider_id)] = rec
            for (ppid, gpid), rec in latest.items():
                game = game_by_pid.get(gpid)
                if game is None:
                    counts.skipped += 1
                    continue
                athlete = athletes.get(ppid)
                if rec.player and rec.player.team_provider_id in team_by_pid:
                    team = team_by_pid[rec.player.team_provider_id]
                    # create the player, or refresh him when a team change or a newly learned position needs recording
                    if athlete is None or athlete.pro_team_id != team.id or (rec.player.position and map_position(rec.player.position) != athlete.positions):
                        athlete = _upsert_player(sport, provider.name, rec.player, team, athletes, counts, now)
                        db.session.flush()
                if athlete is None:
                    counts.skipped += 1
                    counts.notes.append(f"unknown player {ppid}")
                    continue
                typed, view = _stat_values(rec)
                row = existing.get((athlete.id, game.id))
                games_with_rows.add(game.id)
                if row is None:
                    row = GameStat(athlete_id=athlete.id, pro_game_id=game.id, day=game.day, stats=view, source=provider.name,
                                   provider_stat_id=rec.provider_stat_id, synced_at=now, **typed)
                    db.session.add(row)
                    db.session.flush()
                    counts.inserted += 1
                    counts.changed_stat_ids.add(row.id)
                    counts.changed_days.add(game.day)
                else:
                    changed = _apply(row, stats=view, **typed)
                    if changed:
                        row.synced_at = now
                        counts.updated += 1
                        counts.changed_stat_ids.add(row.id)
                        counts.changed_days.add(game.day)
                    else:
                        counts.skipped += 1
            known_positions.update(pid for pid, a in athletes.items() if a.positions)
            for g in chunk_games:
                if g.id in games_with_rows or (today - g.game_date).days >= GIVE_UP_NO_BOX_SCORE_DAYS:
                    g.stats_synced_at = now
                    if g.id not in games_with_rows:
                        counts.notes.append(f"no box score for game {g.provider_id}")
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    return f"{date_list[0]}..{date_list[-1]} ({len(games)} games)"


def sync_corrections(provider: NBADataProvider, sport: Sport, counts: Counts, *, days: int | None = None) -> str:
    """Re-fetch box scores of games that finished in the last `days` days; changed rows are updated (official corrections)."""
    days = provider.corrections_days if days is None else days
    since = timeline.today() - timedelta(days=days)
    dates = sorted({g.game_date for g in db.session.scalars(db.select(ProGame).where(
        ProGame.sport_id == sport.id, ProGame.provider == provider.name, ProGame.status == "final", ProGame.game_date >= since, ProGame.stats_synced_at.is_not(None)))})
    if not dates:
        return "no recent games to re-check"
    return sync_stats(provider, sport, counts, dates=dates, only_missing=False)


# ---------------------------------------------------------------------------------------------
# Run tracking
# ---------------------------------------------------------------------------------------------
def _expire_stale_runs(provider_name: str):
    cutoff = utcnow() - STALE_RUN_AFTER
    for run in db.session.scalars(db.select(DataSyncRun).where(DataSyncRun.provider == provider_name, DataSyncRun.status == "running", DataSyncRun.started_at < cutoff)):
        run.status, run.finished_at, run.error = "failed", utcnow(), "Marked failed: the job never finished (process stopped?)."
    db.session.commit()


def start_run(provider_name: str, job_type: str, params: dict | None, triggered_by: str) -> DataSyncRun:
    _expire_stale_runs(provider_name)
    run = DataSyncRun(provider=provider_name, job_type=job_type, params=params or {}, triggered_by=triggered_by)
    db.session.add(run)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise SyncAlreadyRunning() from None
    return run


def run_job(provider: NBADataProvider, job_type: str, fn, params: dict | None = None, triggered_by: str = "cli") -> DataSyncRun:
    """Run `fn(counts) -> marker` as a tracked job. Never raises provider errors: the outcome is stored on the DataSyncRun."""
    run = start_run(provider.name, job_type, params, triggered_by)
    run_id = run.id
    counts = Counts()
    status, error, marker = "success", None, None
    try:
        marker = fn(counts)
        if counts.errors:
            ok = [s for s in counts.steps if s["status"] == "ok"]
            status = "partial" if ok else ("blocked" if counts.blocked and all(s["status"] == "blocked" for s in counts.steps) else "failed")
            error = " | ".join(counts.errors)
    except (ProviderAuthError, ProviderAccessError) as exc:
        db.session.rollback()
        status, error = "blocked", str(exc)
    except ProviderError as exc:
        db.session.rollback()
        status, error = ("partial" if counts.inserted + counts.updated else "failed"), str(exc)
    except Exception as exc:                                   # noqa: BLE001 - recorded, then visible in the admin page
        db.session.rollback()
        log.exception("sync job %s crashed", job_type)
        status, error = "failed", f"{type(exc).__name__}: {exc}"
    run = db.session.get(DataSyncRun, run_id)
    run.status, run.finished_at, run.error, run.marker = status, utcnow(), (error or "")[:2000] or None, marker
    run.inserted, run.updated, run.skipped, run.requests_made = counts.inserted, counts.updated, counts.skipped, provider.requests_made
    if counts.steps:
        run.params = {**(run.params or {}), "steps": counts.steps}
    db.session.commit()
    return run


# ---------------------------------------------------------------------------------------------
# Public job entry points (CLI, admin API, scheduler)
# ---------------------------------------------------------------------------------------------
def job_teams_players(provider, triggered_by="cli"):
    sport = ensure_sport(provider)
    return run_job(provider, "teams_players", lambda c: sync_teams_and_players(provider, sport, c), triggered_by=triggered_by)


def job_schedule(provider, *, season=None, start=None, end=None, triggered_by="cli"):
    sport = ensure_sport(provider)
    return run_job(provider, "schedule", lambda c: sync_games(provider, sport, c, season=season, start=start, end=end),
                   {"season": season, "start": str(start) if start else None, "end": str(end) if end else None}, triggered_by)


def job_stats(provider, *, dates=None, triggered_by="cli"):
    sport = ensure_sport(provider)
    return run_job(provider, "stats", lambda c: _stats_then_scores(provider, sport, c, dates), {"dates": [str(d) for d in dates or []]}, triggered_by)


def _stats_then_scores(provider, sport, counts, dates):
    marker = sync_stats(provider, sport, counts, dates=dates, only_missing=dates is None)
    _after_stats(sport, counts)
    return marker


def _after_stats(sport: Sport, counts: Counts):
    """Recalculate fantasy scores for changed stats, re-score affected league days, refresh ranks."""
    from fantaball.nba import league_sync, scoring_service
    if counts.changed_stat_ids:
        scoring_service.recalculate(sport, stat_ids=counts.changed_stat_ids)
        recompute_ranks(sport)
        league_sync.rescore_leagues(sport, counts.changed_days)
    league_sync.advance_leagues(sport)


def job_corrections(provider, *, days=None, triggered_by="cli"):
    sport = ensure_sport(provider)

    def fn(counts):
        marker = sync_corrections(provider, sport, counts, days=days)
        _after_stats(sport, counts)
        return marker
    return run_job(provider, "corrections", fn, {"days": days}, triggered_by)


def job_recalculate_scores(provider_name: str, triggered_by="cli"):
    from fantaball.nba import league_sync, scoring_service
    sport = db.session.scalar(db.select(Sport).where(Sport.code == "nba"))
    if sport is None:
        raise IngestError("No NBA data imported yet.")

    class _P:   # recalculation needs no provider; this only labels the run
        name = provider_name
        requests_made = 0

    def fn(counts):
        c = scoring_service.recalculate(sport)
        counts.inserted, counts.updated, counts.skipped = c.inserted, c.updated, c.skipped
        league_sync.rescore_leagues(sport, None)
        league_sync.advance_leagues(sport)
        return "all final games"
    return run_job(_P(), "scores", fn, triggered_by=triggered_by)


def job_daily(provider, triggered_by="schedule"):
    """The scheduled job: schedule window -> missing box scores -> corrections -> fantasy scores -> league scoring."""
    sport = ensure_sport(provider)

    def fn(counts: Counts):
        def step(name, fn_):
            try:
                note = fn_()
                counts.steps.append({"name": name, "status": "ok", "note": note})
            except (ProviderAuthError, ProviderAccessError) as exc:
                db.session.rollback()
                counts.blocked = True
                counts.steps.append({"name": name, "status": "blocked", "error": str(exc)})
                counts.errors.append(f"{name}: {exc}")
            except ProviderError as exc:
                db.session.rollback()
                counts.steps.append({"name": name, "status": "failed", "error": str(exc)})
                counts.errors.append(f"{name}: {exc}")
            except IngestError as exc:
                db.session.rollback()
                counts.steps.append({"name": name, "status": "failed", "error": exc.message})
                counts.errors.append(f"{name}: {exc.message}")

        last_ref = db.session.scalar(db.select(db.func.max(DataSyncRun.finished_at)).where(
            DataSyncRun.provider == provider.name, DataSyncRun.job_type == "teams_players", DataSyncRun.status == "success"))
        if last_ref is None or utcnow() - last_ref > timedelta(days=7) or not db.session.scalar(db.select(ProTeam.id).where(ProTeam.sport_id == sport.id)):
            step("teams_players", lambda: sync_teams_and_players(provider, sport, counts))
        today = timeline.today()
        back, ahead = provider.daily_window
        if sport.season_start is None or today.weekday() == 0:      # the whole season once to anchor it, then every Monday
            step("schedule", lambda: sync_games(provider, sport, counts, season=sport.season or nba_config.current_season(current_app.config)))
        else:
            step("schedule", lambda: sync_games(provider, sport, counts, start=today - timedelta(days=back), end=today + timedelta(days=ahead)))
        step("stats", lambda: sync_stats(provider, sport, counts))
        step("corrections", lambda: sync_corrections(provider, sport, counts))
        step("scores", lambda: (_after_stats(sport, counts), "scores and leagues updated")[1])
        return f"daily sync {today}"
    return run_job(provider, "daily", fn, triggered_by=triggered_by)
