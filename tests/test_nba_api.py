"""Data/admin API: onboarding, authorization, secrecy of the API key, sport-level player database, error handling."""
import json
import os
import subprocess
import sys
import textwrap
from datetime import date

import pytest

from root import db
from models.fantasy import DataSyncRun
from fantaball.nba import ingest
from fantaball.nba.mock import MockNBAProvider
from tests.test_nba_ingest import full_import, world, wipe_real_nba   # noqa: F401

TODAY = date(2026, 10, 27)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_status_shows_onboarding_when_no_real_data_exists(world, alice):
    s, st = alice.get("/api/data/status")
    assert s == 200 and st["has_real_data"] is False and "BALLDONTLIE_API_KEY" in st["onboarding"]
    assert st["counts"]["players"] == 0 and st["last_success"] is None


def test_status_after_import_reports_counts_freshness_and_never_the_key(world, alice, flask_app):
    flask_app.config["BALLDONTLIE_API_KEY"] = "SECRET-KEY-XYZ-123"
    try:
        full_import(MockNBAProvider(today=TODAY))
        s, st = alice.get("/api/data/status")
        assert s == 200 and st["has_real_data"] is True and st["data_source"] == "mock"
        assert st["counts"]["teams"] == 6 and st["counts"]["final_games"] == 24 and st["counts"]["player_game_stats"] == 24 * 16
        assert st["counts"]["final_games_missing_stats"] == 0
        assert st["last_success"]["job"] == "stats" and st["freshness_seconds"] is not None and st["freshness_seconds"] < 60
        assert st["provider"]["configured"] is True
        everything = json.dumps(st) + alice.get("/api/data/status")[1].__repr__()
        assert "SECRET-KEY-XYZ-123" not in everything
    finally:
        flask_app.config.pop("BALLDONTLIE_API_KEY", None)


def test_admin_endpoints_require_an_administrator(world, alice, admin):
    assert alice.post("/api/admin/sync", {"job": "teams_players"})[0] == 403
    assert alice.get("/api/data/runs")[0] == 403
    s, run = admin.post("/api/admin/sync", {"job": "teams_players"})
    assert s == 200 and run["status"] == "success" and run["triggered_by"] == "admin:admin@example.com"
    s, runs = admin.get("/api/data/runs")
    assert s == 200 and runs[0]["job"] == "teams_players"


def test_admin_sync_validates_input_and_reports_real_results(world, admin):
    assert admin.post("/api/admin/sync", {"job": "format_disk"})[0] == 400
    assert admin.post("/api/admin/sync", {"job": "schedule", "start": "not-a-date"})[0] == 400
    assert admin.post("/api/admin/sync", {"job": "schedule", "start": "2026-10-20", "end": "2026-01-01"})[0] == 400
    assert admin.post("/api/admin/sync", {"job": "schedule", "season": "2026"})[0] == 400
    assert admin.post("/api/admin/sync", {"job": "teams_players"})[0] == 200
    # schedule without a season anchor fails honestly (recorded, not hidden)
    s, run = admin.post("/api/admin/sync", {"job": "schedule", "start": "2026-10-20", "end": "2026-10-22"})
    assert s == 200 and run["status"] == "failed" and "season start" in run["error"].lower()
    s, run = admin.post("/api/admin/sync", {"job": "schedule", "season": 2026})
    assert run["status"] == "success" and run["inserted"] == 42
    s, run = admin.post("/api/admin/sync", {"job": "stats"})
    assert run["status"] == "success" and run["inserted"] == 24 * 16
    # re-importing a date range changes nothing when the provider's numbers did not change
    s, run = admin.post("/api/admin/sync", {"job": "stats", "start": "2026-10-19", "end": "2026-10-21"})
    assert run["status"] == "success" and run["inserted"] == 0 and run["updated"] == 0
    assert admin.post("/api/admin/sync", {"job": "stats", "start": "2026-01-01", "end": "2026-12-31"})[0] == 400


def test_second_sync_is_rejected_while_one_is_running(world, admin):
    db.session.add(DataSyncRun(provider="mock", job_type="daily", status="running"))
    db.session.commit()
    s, res = admin.post("/api/admin/sync", {"job": "teams_players"})
    assert s == 409 and "already running" in res["error"]


def test_unconfigured_provider_is_reported_clearly(world, admin, flask_app, monkeypatch):
    monkeypatch.setitem(flask_app.config, "NBA_PROVIDER", "balldontlie")
    monkeypatch.delenv("BALLDONTLIE_API_KEY", raising=False)
    monkeypatch.setitem(flask_app.config, "BALLDONTLIE_API_KEY", "")
    s, res = admin.post("/api/admin/sync", {"job": "teams_players"})
    assert s == 409 and "BALLDONTLIE_API_KEY" in res["error"]
    s, st = admin.get("/api/data/status")
    assert st["provider"]["configured"] is False and st["provider"]["provider"] == "balldontlie"


def test_sport_level_player_database_handles_missing_values(world, alice):
    assert alice.get("/api/data/players?sport=nba")[0] == 404                       # nothing imported yet: no fake fallback
    assert alice.get("/api/data/players?sport=cricket")[0] == 400
    full_import(MockNBAProvider(today=TODAY))
    s, res = alice.get("/api/data/players?sport=nba&limit=200&sort=proj")
    assert s == 200 and res["data_source"] == "mock" and res["simulated"] is False
    assert res["total"] == 48                                                        # the player with no position is not offered
    assert all(p["positions"] for p in res["players"])
    assert res["players"][0]["proj"] >= res["players"][-1]["proj"]
    # a mean is taken over the games that REPORTED the stat; unreported values are never counted as zero
    from models.fantasy import Athlete, GameStat
    flaky = db.session.scalar(db.select(Athlete).where(Athlete.provider == "mock", Athlete.provider_id == 1020))
    reported = [g.blk for g in db.session.scalars(db.select(GameStat).where(GameStat.athlete_id == flaky.id)) if g.blk is not None]
    all_games = db.session.scalar(db.select(db.func.count(GameStat.id)).where(GameStat.athlete_id == flaky.id))
    assert 0 < len(reported) < all_games
    _, row = alice.get("/api/data/players?sport=nba&search=Last1020")
    assert row["players"][0]["avg"]["blk"] == pytest.approx(round(sum(reported) / len(reported), 2))
    # a player with no games has no averages (null, not 0) and sorts last
    rookie = Athlete(sport_id=flaky.sport_id, pro_team_id=flaky.pro_team_id, name="No Games", positions="PG", rank=999, provider="mock", provider_id=9999, is_simulated=False)
    db.session.add(rookie)
    db.session.commit()
    s, res = alice.get("/api/data/players?sport=nba&sort=fpg&dir=desc&limit=200")
    assert res["players"][-1]["name"] == "No Games" and res["players"][-1]["fpg"] is None and res["players"][-1]["avg"] == {}
    s, res = alice.get("/api/data/players?sport=nba&sort=fpg&dir=asc&limit=200")
    assert res["players"][-1]["name"] == "No Games"
    db.session.delete(rookie)
    db.session.commit()
    s, res = alice.get("/api/data/players?sport=nba&search=Last1003")
    assert res["total"] == 1
    pid = res["players"][0]["id"]
    s, prof = alice.get(f"/api/data/players/{pid}")
    assert s == 200 and prof["game_log"] and prof["rulesets"] and prof["ruleset_id"]
    assert all("fp" in g for g in prof["game_log"])
    s, rs = alice.get("/api/data/rulesets?sport=nba")
    assert s == 200 and rs[0]["is_template"] is True


def test_profile_scores_under_a_selected_ruleset(world, alice):
    full_import(MockNBAProvider(today=TODAY))
    from models.fantasy import ScoringRuleSet, Sport
    from fantaball.rulesets import get_or_create_ruleset
    sport = db.session.scalar(db.select(Sport).where(Sport.code == "nba"))
    only_points = get_or_create_ruleset(sport.id, {"pts": 1}, name="Points only", template=True)
    db.session.commit()
    pid = alice.get("/api/data/players?sport=nba&limit=1")[1]["players"][0]["id"]
    _, default = alice.get(f"/api/data/players/{pid}")
    _, custom = alice.get(f"/api/data/players/{pid}?ruleset_id={only_points.id}")
    g_default, g_custom = default["game_log"][0], custom["game_log"][0]
    assert g_custom["fp"] == g_custom["stats"]["pts"]                                # points-only league: fantasy points = points
    assert g_default["fp"] != g_custom["fp"]
    assert alice.get(f"/api/data/players/{pid}?ruleset_id=999999")[0] == 400


def test_daily_sync_status_flags_plan_limitation(world, alice):
    p = MockNBAProvider(today=TODAY)
    p.stats_blocked = True
    ingest.job_daily(p)
    s, st = alice.get("/api/data/status")
    assert st["limitations"] and "ALL-STAR" in st["limitations"][0]
    assert st["last_attempt"]["status"] == "partial" and st["failures"]


# ------------------------------------------------------------------ migrations
def test_legacy_database_is_migrated_without_losing_data(tmp_path):
    """A database made by the old db.create_all() (baseline schema + rows) upgrades to the current schema with its data."""
    db_file = (tmp_path / "legacy.db").as_posix()
    script = textwrap.dedent(f"""
        import os, sys, json
        os.environ.update(FLASK_ENVIRONMENT="production", FLASK_SITE_NAME="t", FLASK_SKIP_DB_INIT="true",
                          FLASK_SQLALCHEMY_DATABASE_URI="sqlite:///{db_file}")
        sys.path.insert(0, r"{ROOT}")
        import app as appmod
        from flask_migrate import upgrade
        from sqlalchemy import text
        from root import db
        with appmod.app.app_context():
            upgrade(revision="0001")                                  # the schema the first prototype had
            c = db.session
            c.execute(text("INSERT INTO sports (id, code, name) VALUES (1, 'nba', 'NBA Basketball')"))
            c.execute(text("INSERT INTO managers (id, email, display_name, is_demo_bot, created_at) VALUES (1, 'a@b.c', 'A', 0, CURRENT_TIMESTAMP)"))
            c.execute(text("INSERT INTO leagues (id, name, sport_id, commissioner_id, invite_code, format, num_teams, roster_config, status, current_day, is_demo, created_at) "
                           "VALUES (1, 'L', 1, 1, 'ABCDEFGH', 'h2h_points', 4, '[]', 'active', 3, 1, CURRENT_TIMESTAMP)"))
            c.execute(text("INSERT INTO scoring_configs (id, league_id, rules) VALUES (1, 1, '{{\\"pts\\": 1.0}}')"))
            c.commit()
            upgrade()                                                 # -> head
            print(json.dumps([
                [list(r) for r in c.execute(text("SELECT code, data_source FROM sports"))],
                [list(r) for r in c.execute(text("SELECT ruleset_id IS NOT NULL FROM scoring_configs"))],
                [list(r) for r in c.execute(text("SELECT name, current_day FROM leagues"))],
                [list(r) for r in c.execute(text("SELECT version_num FROM alembic_version"))]]))
    """)
    out = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert out.returncode == 0, out.stderr[-2000:]
    sports, cfg, leagues, version = json.loads(out.stdout.strip().splitlines()[-1])
    assert sports == [["nba_demo", "demo"]]                          # the old simulated 'nba' is relabelled, not mistaken for real data
    assert cfg == [[1]] and leagues == [["L", 3]] and version == [["0002"]]
