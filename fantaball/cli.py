"""Command line tools:   python -m flask --app app nba --help

Every command is safe to run repeatedly (idempotent upserts) and records a DataSyncRun you can inspect with `nba status`.
"""
import sys
from datetime import date, timedelta

import click
from flask import current_app
from flask.cli import AppGroup

from root import db
from models.fantasy import DataSyncRun, Sport
from fantaball.errors import ApiError
from fantaball.nba import config as nba_config
from fantaball.nba import ingest
from fantaball.nba.provider import ProviderError

nba = AppGroup("nba", help="Real NBA data pipeline (BALLDONTLIE) and fantasy scoring.")


def _provider():
    try:
        p = nba_config.build_provider(current_app.config)
    except ProviderError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(2)
    return p


def _show(run: DataSyncRun):
    colour = {"success": "green", "partial": "yellow", "blocked": "red", "failed": "red"}.get(run.status, None)
    click.secho(f"[{run.job_type}] {run.status.upper()}  inserted={run.inserted} updated={run.updated} skipped={run.skipped} "
                f"requests={run.requests_made}  {run.marker or ''}", fg=colour)
    if run.error:
        click.secho(f"    {run.error}", fg="red")
    return run.status in ("success",)


def _run(fn):
    try:
        return _show(fn())
    except ApiError as exc:
        click.secho(f"ERROR: {exc.message}", fg="red", err=True)
        return False


def _date(value):
    return date.fromisoformat(value) if value else None


@nba.command("status")
def status_cmd():
    """Show provider configuration, data counts and the last sync runs."""
    cfg = nba_config.provider_status(current_app.config)
    click.echo(f"provider: {cfg['provider']}  configured: {cfg['configured']}  rate limit: {cfg['requests_per_minute']}/min")
    if cfg["message"]:
        click.secho(cfg["message"], fg="yellow")
    sport = db.session.scalar(db.select(Sport).where(Sport.code == "nba"))
    if sport:
        click.echo(f"nba data source: {sport.data_source}  season: {sport.season}  season start (day 1): {sport.season_start}")
    for r in db.session.scalars(db.select(DataSyncRun).order_by(DataSyncRun.id.desc()).limit(8)):
        click.echo(f"#{r.id} {r.started_at:%Y-%m-%d %H:%M} {r.job_type:<14} {r.status:<8} +{r.inserted} ~{r.updated} ={r.skipped}  {r.error or ''}"[:200])


@nba.command("sync-teams")
def sync_teams_cmd():
    """Import / update NBA teams and current players."""
    sys.exit(0 if _run(lambda: ingest.job_teams_players(_provider())) else 1)


@nba.command("sync-games")
@click.option("--season", type=int, help="Whole season by start year (e.g. 2026). Needed once to anchor the season.")
@click.option("--start", help="First date YYYY-MM-DD")
@click.option("--end", help="Last date YYYY-MM-DD")
def sync_games_cmd(season, start, end):
    """Import the game schedule/results for a season or a date range."""
    if not (season or start):
        raise click.UsageError("Give --season, or --start/--end")
    sys.exit(0 if _run(lambda: ingest.job_schedule(_provider(), season=season, start=_date(start), end=_date(end))) else 1)


@nba.command("sync-stats")
@click.option("--date", "one_date", help="Re-import box scores for one date YYYY-MM-DD")
@click.option("--start", help="First date (re-imports the range)")
@click.option("--end", help="Last date")
def sync_stats_cmd(one_date, start, end):
    """Import box scores. With no options: only games whose stats are missing. With dates: re-import them."""
    dates = None
    if one_date:
        dates = [date.fromisoformat(one_date)]
    elif start:
        a, b = date.fromisoformat(start), date.fromisoformat(end or start)
        dates = [a + timedelta(days=i) for i in range((b - a).days + 1)]
    sys.exit(0 if _run(lambda: ingest.job_stats(_provider(), dates=dates)) else 1)


@nba.command("corrections")
@click.option("--days", default=3, show_default=True, help="Re-check games finished in the last N days")
def corrections_cmd(days):
    """Re-fetch recent box scores to pick up official statistic corrections."""
    sys.exit(0 if _run(lambda: ingest.job_corrections(_provider(), days=days)) else 1)


@nba.command("recalc")
def recalc_cmd():
    """Recalculate every stored fantasy score and league total from the imported statistics."""
    sys.exit(0 if _run(lambda: ingest.job_recalculate_scores(nba_config.provider_name(current_app.config))) else 1)


@nba.command("daily")
def daily_cmd():
    """The scheduled job: schedule window, missing box scores, corrections, fantasy scores, league scoring."""
    sys.exit(0 if _run(lambda: ingest.job_daily(_provider(), triggered_by="schedule")) else 1)


@nba.command("bootstrap")
@click.option("--season", type=int, help="Season start year (default: the current season)")
def bootstrap_cmd(season):
    """First-time import: teams + players, the full season schedule, then every available box score."""
    p = _provider()
    season = season or nba_config.current_season(current_app.config)
    ok = _run(lambda: ingest.job_teams_players(p)) and _run(lambda: ingest.job_schedule(p, season=season)) and _run(lambda: ingest.job_stats(p))
    sys.exit(0 if ok else 1)


@nba.command("purge-data")
@click.option("--yes", is_flag=True, help="Confirm deleting all imported NBA rows (only allowed while no league uses them)")
def purge_cmd(yes):
    """Delete imported NBA data (only allowed while no league uses it)."""
    sport = db.session.scalar(db.select(Sport).where(Sport.code == "nba"))
    if sport is None:
        click.echo("Nothing to purge.")
        return
    if not yes:
        raise click.UsageError("Add --yes to confirm")
    try:
        ingest.purge_sport_data(sport)
    except ApiError as exc:
        click.secho(f"ERROR: {exc.message}", fg="red", err=True)
        sys.exit(1)
    click.echo("Purged.")


def register(app):
    app.cli.add_command(nba)
