"""Ingestion into the database with the MOCK provider: upserts, duplicates, failure recovery, plan limits, corrections."""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from root import db
from models.fantasy import (Athlete, DataSyncRun, GameStat, PlayerFantasyScore, ProGame, ProTeam, ScoringRuleSet, Sport)
from fantaball.nba import ingest
from tests.helpers import TODAY, count, full_import
from tests.mock_provider import MockNBAProvider
from fantaball.nba.provider import ProviderUnavailable

# ------------------------------------------------------------------ players & teams
def test_import_teams_and_players_is_idempotent_and_safe_with_missing_data(world):
    p = MockNBAProvider(today=TODAY)
    run = ingest.job_teams_players(p)
    assert run.status == "success" and run.inserted > 0
    sport = db.session.scalar(db.select(Sport).where(Sport.code == "nba"))
    assert sport.data_source == "mock"
    assert count(ProTeam) == 6 and count(Athlete) == 49                    # 48 normal players + one with no position; the team-less player is skipped
    nopos = db.session.scalar(db.select(Athlete).where(Athlete.provider_id == 2001, Athlete.provider == "mock"))
    assert nopos.positions == "" and nopos.provider_position is None       # stored, but not draftable
    assert db.session.scalar(db.select(Athlete).where(Athlete.provider_id == 2002)) is None
    again = ingest.job_teams_players(p)
    assert again.inserted == 0 and again.updated == 0 and count(Athlete) == 49   # re-run: no duplicates, nothing changed


def test_player_team_change_and_inactive_players_keep_history(world):
    p = MockNBAProvider(today=TODAY)
    ingest.job_teams_players(p)
    moved = p._players[0]
    from dataclasses import replace
    p._players[0] = replace(moved, team_provider_id=102)                  # traded to another team
    p._players.pop(1)                                                     # and another player drops off every roster
    gone_id = 1002
    ingest.job_teams_players(p)
    a = db.session.scalar(db.select(Athlete).where(Athlete.provider_id == moved.provider_id))
    assert a.pro_team.provider_id == 102
    gone = db.session.scalar(db.select(Athlete).where(Athlete.provider_id == gone_id))
    assert gone is not None and gone.active is False                       # never deleted


# ------------------------------------------------------------------ schedule
def test_schedule_needs_full_season_first_and_is_idempotent(world):
    p = MockNBAProvider(today=TODAY)
    ingest.job_teams_players(p)
    run = ingest.job_schedule(p, start=date(2026, 10, 20), end=date(2026, 10, 22))
    assert run.status == "failed" and "season start" in run.error.lower()
    run = ingest.job_schedule(p, season=2026)
    assert run.status == "success" and count(ProGame) == 42
    sport = db.session.scalar(db.select(Sport).where(Sport.code == "nba"))
    assert sport.season_start == date(2026, 10, 19)                        # a Monday
    g = db.session.scalar(db.select(ProGame).where(ProGame.game_date == date(2026, 10, 19)))
    assert g.day == 1 and g.status == "final" and g.home_score is not None
    assert db.session.scalar(db.select(ProGame).where(ProGame.game_date == TODAY)).status == "scheduled"
    again = ingest.job_schedule(p, start=date(2026, 10, 20), end=date(2026, 10, 30))
    assert again.status == "success" and again.inserted == 0 and count(ProGame) == 42


# ------------------------------------------------------------------ box scores
def test_stats_import_unique_missing_values_and_no_duplicates(world):
    p = MockNBAProvider(today=TODAY)
    full_import(p)
    final_games = count(ProGame, ProGame.status == "final")
    stats = count(GameStat)
    assert final_games == 24 and stats == 24 * 16
    assert count(ProGame, ProGame.status == "final", ProGame.stats_synced_at.is_(None)) == 0
    # re-running (even with the same dates forced) never duplicates
    again = ingest.job_stats(p)
    assert again.inserted == 0 and count(GameStat) == stats
    forced = ingest.job_stats(p, dates=[date(2026, 10, 20)])
    assert forced.inserted == 0 and forced.updated == 0 and count(GameStat) == stats
    # database-level uniqueness: one row per (player, game)
    row = db.session.scalars(db.select(GameStat).where(GameStat.source == "mock").limit(1)).first()
    db.session.add(GameStat(athlete_id=row.athlete_id, pro_game_id=row.pro_game_id, day=row.day + 100, stats={}))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    # a stat the provider did not report is NULL (never 0) and that line is not scored
    missing = db.session.scalars(db.select(GameStat).where(GameStat.source == "mock", GameStat.blk.is_(None))).first()
    assert missing is not None and "blk" not in missing.stats
    nba = db.session.scalar(db.select(Sport).where(Sport.code == "nba"))
    default_rs = db.session.scalar(db.select(ScoringRuleSet).where(ScoringRuleSet.sport_id == nba.id, ScoringRuleSet.is_template.is_(True)))
    pfs = db.session.scalar(db.select(PlayerFantasyScore).where(PlayerFantasyScore.game_stat_id == missing.id, PlayerFantasyScore.ruleset_id == default_rs.id))
    assert pfs.points is None
    zero = db.session.scalars(db.select(GameStat).where(GameStat.source == "mock", GameStat.blk == 0)).first()
    assert "blk" in zero.stats and zero.stats["blk"] == 0                  # a real zero stays a zero


def test_future_and_unfinished_games_are_never_imported_as_stats(world):
    p = MockNBAProvider(today=TODAY)
    full_import(p)
    scheduled = db.session.scalars(db.select(ProGame.id).where(ProGame.status != "final")).all()
    assert scheduled and count(GameStat, GameStat.pro_game_id.in_(scheduled)) == 0
    assert count(PlayerFantasyScore, PlayerFantasyScore.pro_game_id.in_(scheduled)) == 0


def test_corrections_update_stats_and_scores_once(world):
    p = MockNBAProvider(today=TODAY)
    full_import(p)
    before = {r.id: r.points for r in db.session.scalars(db.select(PlayerFantasyScore))}
    p.revision = 2                                                          # the provider now reports corrected numbers
    run = ingest.job_corrections(p, days=30)
    assert run.status == "success" and run.updated > 0
    changed = [r for r in db.session.scalars(db.select(PlayerFantasyScore)) if before.get(r.id) != r.points]
    assert changed and len(changed) <= run.updated                         # corrected lines got new fantasy scores (+3 pts); lines that cannot be scored stay unscored
    assert all(r.points - before[r.id] == 3 for r in changed)
    assert count(GameStat) == 24 * 16 and count(PlayerFantasyScore) == len(before)
    again = ingest.job_corrections(p, days=30)
    assert again.updated == 0 and again.inserted == 0                      # applying the same correction twice changes nothing more


# ------------------------------------------------------------------ failures, locking, plan limits
def test_failed_sync_leaves_consistent_data_and_can_resume(world):
    p = MockNBAProvider(today=TODAY)
    ingest.job_teams_players(p)
    ingest.job_schedule(p, season=2026)
    p.fail_after_requests = p.requests_made + 1                             # first stats chunk works, the next request fails
    run = ingest.job_stats(p)
    assert run.status in ("partial", "failed") and "provider" in run.error.lower()
    done_games = db.session.scalars(db.select(ProGame).where(ProGame.stats_synced_at.is_not(None))).all()
    todo_games = db.session.scalars(db.select(ProGame).where(ProGame.status == "final", ProGame.stats_synced_at.is_(None))).all()
    assert done_games and todo_games                                        # a committed batch is complete; the rest untouched
    for g in done_games:
        assert count(GameStat, GameStat.pro_game_id == g.id) == 16
    for g in todo_games:
        assert count(GameStat, GameStat.pro_game_id == g.id) == 0
    p.fail_after_requests = None
    resumed = ingest.job_stats(p)
    assert resumed.status == "success" and count(GameStat) == 24 * 16       # nothing lost, nothing duplicated
    assert count(ProGame, ProGame.status == "final", ProGame.stats_synced_at.is_(None)) == 0


def test_only_one_sync_may_run_at_a_time(world):
    db.session.add(DataSyncRun(provider="mock", job_type="daily", status="running"))
    db.session.commit()
    with pytest.raises(ingest.SyncAlreadyRunning):
        ingest.start_run("mock", "stats", {}, "cli")
    db.session.add(DataSyncRun(provider="mock", job_type="stats", status="success"))   # finished runs are unlimited
    db.session.commit()


def test_stats_blocked_by_plan_is_reported_not_faked(world):
    p = MockNBAProvider(today=TODAY)
    p.stats_blocked = True
    assert ingest.job_teams_players(p).status == "success"
    assert ingest.job_schedule(p, season=2026).status == "success"
    run = ingest.job_stats(p)
    assert run.status == "blocked" and "plan" in run.error.lower()
    assert count(GameStat) == 0 and count(PlayerFantasyScore) == 0         # no invented data
    daily = ingest.job_daily(p)
    assert daily.status == "partial"
    steps = {s["name"]: s["status"] for s in daily.params["steps"]}
    assert steps["schedule"] == "ok" and steps["stats"] == "blocked"


def test_provider_mixing_is_refused(world):
    ingest.job_teams_players(MockNBAProvider(today=TODAY))

    class Other(MockNBAProvider):
        name = "balldontlie"
    with pytest.raises(ingest.IngestError, match="mix"):
        ingest.job_teams_players(Other(today=TODAY))


def test_provider_outage_is_recorded_not_raised(world):
    p = MockNBAProvider(today=TODAY)
    p.fail_after_requests = 0
    run = ingest.job_teams_players(p)
    assert run.status == "failed" and "outage" in run.error
    assert db.session.get(DataSyncRun, run.id).finished_at is not None
