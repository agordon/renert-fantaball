"""Imported statistics -> persisted fantasy scores -> league lineups -> matchup / team totals (mock provider, no network)."""
from datetime import date

import pytest

from root import db
from models.fantasy import (DailyScore, FantasyTeam, League, Matchup, PlayerFantasyScore, ProGame, ScoringRuleSet, Sport, TeamPeriodScore)
from fantaball.nba import ingest, league_sync, scoring_service
from tests.mock_provider import MockNBAProvider
from fantaball.rulesets import get_or_create_ruleset
from fantaball.scoring import score_decimal
from tests.helpers import SMALL_ROSTER, count, full_import



def nba_sport():
    return db.session.scalar(db.select(Sport).where(Sport.code == "nba"))


def make_real_league(client, name="Real League"):
    s, lg = client.post("/api/leagues", {"sport": "nba", "name": name, "num_teams": 4, "roster_config": SMALL_ROSTER})
    assert s == 201, lg
    lid = lg["id"]
    assert client.post(f"/api/leagues/{lid}/draft/start", {})[0] == 200
    assert client.post(f"/api/leagues/{lid}/draft/sim", {"to_end": True})[0] == 200
    return lid


@pytest.fixture()
def real_league(world, alice, monkeypatch):
    """A drafted real-data league created on 2026-10-24, then three days of games get imported."""
    monkeypatch.setenv("FLASK_FAKE_TODAY", "2026-10-24")
    p = MockNBAProvider(today=date(2026, 10, 24))
    full_import(p)
    lid = make_real_league(alice)
    monkeypatch.setenv("FLASK_FAKE_TODAY", "2026-10-27")
    p2 = MockNBAProvider(today=date(2026, 10, 27))
    run = ingest.job_daily(p2)
    assert run.status == "success", run.error
    return lid, p2


# ------------------------------------------------------------------ rule sets
def test_identical_rules_share_one_ruleset_and_changes_never_edit_history(world):
    p = MockNBAProvider(today=date(2026, 10, 27))
    full_import(p)
    sport = nba_sport()
    a = get_or_create_ruleset(sport.id, {"pts": 1, "reb": 1.2})
    assert get_or_create_ruleset(sport.id, {"reb": 1.2, "pts": 1.0}).id == a.id      # shared, not duplicated
    scoring_service.recalculate(sport, rulesets=[a])
    stat_count = count(PlayerFantasyScore, PlayerFantasyScore.ruleset_id == a.id)
    assert stat_count == 24 * 16
    snapshot = {r.game_stat_id: r.points for r in db.session.scalars(db.select(PlayerFantasyScore).where(PlayerFantasyScore.ruleset_id == a.id))}
    b = get_or_create_ruleset(sport.id, {"pts": 2, "reb": 1.2})                        # the league "changes" its scoring
    assert b.id != a.id
    scoring_service.recalculate(sport, rulesets=[b])
    after_a = {r.game_stat_id: r.points for r in db.session.scalars(db.select(PlayerFantasyScore).where(PlayerFantasyScore.ruleset_id == a.id))}
    assert after_a == snapshot                                                       # old results unchanged
    assert count(PlayerFantasyScore, PlayerFantasyScore.ruleset_id == b.id) == stat_count
    again = scoring_service.recalculate(sport, rulesets=[a, b])
    assert again.inserted == 0 and again.updated == 0                                # idempotent


def test_only_final_games_are_scored_and_days_complete_only_when_fully_imported(world, monkeypatch):
    monkeypatch.setenv("FLASK_FAKE_TODAY", "2026-10-24")
    p = MockNBAProvider(today=date(2026, 10, 24))
    full_import(p)
    sport = nba_sport()
    # today (Oct 24 = day 6) is not finished: scoring may use days up to day 5 only
    assert league_sync.completed_through_day(sport) == 5
    unfinished = db.session.scalars(db.select(ProGame.id).where(ProGame.sport_id == sport.id, ProGame.status != "final")).all()
    assert db.session.scalar(db.select(db.func.count(PlayerFantasyScore.id)).where(PlayerFantasyScore.pro_game_id.in_(unfinished))) == 0
    # a final game whose box score has not been imported blocks scoring beyond the previous day
    g = db.session.scalar(db.select(ProGame).where(ProGame.sport_id == sport.id, ProGame.game_date == date(2026, 10, 22)))
    g.stats_synced_at = None
    db.session.commit()
    assert league_sync.completed_through_day(sport) == 3                              # day 4 (Oct 22) is incomplete


# ------------------------------------------------------------------ leagues, lineups, matchups
def test_real_league_scores_use_imported_stats_and_totals_add_up(real_league, alice):
    lid, provider = real_league
    lg = db.session.get(League, lid)
    assert lg.sport.data_source == "mock" and lg.scoring.ruleset_id is not None
    assert lg.current_day == 8 and lg.first_week == 1                                 # drafted on day 6; scored days 7 and 8 since
    rules = lg.scoring.rules
    rows = db.session.scalars(db.select(DailyScore).where(DailyScore.league_id == lid)).all()
    assert rows and {r.day for r in rows} <= {7, 8}                                    # days before the draft were never scored for this league
    from models.fantasy import GameStat
    for r in rows:
        stat = db.session.scalar(db.select(GameStat).where(GameStat.athlete_id == r.athlete_id, GameStat.day == r.day))
        expected = score_decimal(stat.stats, rules)
        assert expected is not None and r.points == float(expected)                    # lineup points come straight from the imported stat line
        pfs = db.session.scalar(db.select(PlayerFantasyScore).where(PlayerFantasyScore.game_stat_id == stat.id, PlayerFantasyScore.ruleset_id == lg.scoring.ruleset_id))
        assert float(pfs.points) == r.points
    # matchup + team period totals = sum of counted lineup points; each game counted exactly once
    assert len({(r.team_id, r.athlete_id, r.day) for r in rows}) == len(rows)
    for m in db.session.scalars(db.select(Matchup).where(Matchup.league_id == lid, Matchup.week <= 2)):      # only weeks that have been scored
        days = range((m.week - 1) * 7 + 1, m.week * 7 + 1)
        for team_id, score in ((m.home_team_id, m.home_score), (m.away_team_id, m.away_score)):
            total = sum(r.points for r in rows if r.team_id == team_id and r.counted and r.day in days)
            assert score == pytest.approx(round(total, 1))
            tps = db.session.scalar(db.select(TeamPeriodScore).where(TeamPeriodScore.matchup_id == m.id, TeamPeriodScore.team_id == team_id))
            assert tps.points == pytest.approx(score) and tps.week == m.week
    wk1 = db.session.scalars(db.select(Matchup).where(Matchup.league_id == lid, Matchup.week == 1)).all()
    wk2 = db.session.scalars(db.select(Matchup).where(Matchup.league_id == lid, Matchup.week == 2)).all()
    assert wk1 and all(m.final and m.finalized_at for m in wk1)                        # week 1 ended on day 7
    assert wk2 and not any(m.final for m in wk2)                                       # week 2 is still in progress
    # the HTTP view reports the same numbers
    s, mu = alice.get(f"/api/leagues/{lid}/matchup?week=1")
    assert s == 200 and mu["matchup"]["final"] is True


def test_repeating_syncs_never_double_count(real_league):
    lid, provider = real_league
    before = {m.id: (m.home_score, m.away_score) for m in db.session.scalars(db.select(Matchup).where(Matchup.league_id == lid))}
    n_scores = db.session.scalar(db.select(db.func.count(DailyScore.id)).where(DailyScore.league_id == lid))
    for _ in range(2):
        assert ingest.job_daily(provider).status == "success"
        assert ingest.job_stats(provider, dates=[date(2026, 10, 25), date(2026, 10, 26)]).status == "success"   # forced re-import of the same stats
    assert db.session.get(League, lid).current_day == 8
    assert db.session.scalar(db.select(db.func.count(DailyScore.id)).where(DailyScore.league_id == lid)) == n_scores
    assert {m.id: (m.home_score, m.away_score) for m in db.session.scalars(db.select(Matchup).where(Matchup.league_id == lid))} == before


def test_corrections_flow_into_lineups_and_finalized_weeks(real_league):
    lid, provider = real_league
    lg = db.session.get(League, lid)
    # take a starter who scored on day 7 (week 1 is already final) and "correct" his official stat line by +10 fantasy points
    row = db.session.scalar(db.select(DailyScore).where(DailyScore.league_id == lid, DailyScore.day == 7, DailyScore.counted.is_(True)))
    pfs = db.session.scalar(db.select(PlayerFantasyScore).where(PlayerFantasyScore.athlete_id == row.athlete_id, PlayerFantasyScore.day == 7,
                                                                PlayerFantasyScore.ruleset_id == lg.scoring.ruleset_id))
    m = db.session.scalar(db.select(Matchup).where(Matchup.league_id == lid, Matchup.week == 1, db.or_(Matchup.home_team_id == row.team_id, Matchup.away_team_id == row.team_id)))
    home = m.home_team_id == row.team_id
    total_before = m.home_score if home else m.away_score
    pfs.points = pfs.points + 10
    db.session.commit()
    league_sync.rescore_leagues(nba_sport(), {7})
    db.session.refresh(row)
    db.session.refresh(m)
    assert row.points == pytest.approx(float(pfs.points))
    assert (m.home_score if home else m.away_score) == pytest.approx(total_before + 10, abs=0.11)    # the finalized week was recalculated
    tps = db.session.scalar(db.select(TeamPeriodScore).where(TeamPeriodScore.matchup_id == m.id, TeamPeriodScore.team_id == row.team_id))
    assert tps.points == pytest.approx(total_before + 10, abs=0.11) and m.final
    # running it again changes nothing (no double counting)
    league_sync.rescore_leagues(nba_sport(), {7})
    db.session.refresh(m)
    assert (m.home_score if home else m.away_score) == pytest.approx(total_before + 10, abs=0.11)


def test_league_requires_imported_data_and_a_data_set(world, alice):
    s, res = alice.post("/api/leagues", {"sport": "nba", "name": "No Data League", "num_teams": 4})
    assert s == 409 and "imported" in res["error"]                                    # no fake fallback data
    full_import(MockNBAProvider(today=date(2026, 10, 27)))
    lid = make_real_league(alice)
    assert alice.post(f"/api/leagues/{lid}/simulate", {"days": 1})[0] in (404, 405)    # real leagues are only scored from imported stats
    s, _ = alice.post("/api/leagues", {"name": "Missing sport"})
    assert s == 400
    assert alice.post("/api/leagues", {"sport": "nhl", "name": "Hockey"})[0] == 400


def test_real_players_cannot_be_owned_twice_in_a_league(real_league, alice, bob):
    lid, _ = real_league
    s, mine = alice.get(f"/api/leagues/{lid}/team")
    owned = mine["players"][0]["id"]
    s, d = alice.get(f"/api/leagues/{lid}")
    s, res = bob.post("/api/leagues/join", {"code": d["invite_code"]})
    assert s == 409                                                                   # the league already drafted
    s, res = alice.post(f"/api/leagues/{lid}/add-drop", {"add_id": owned, "drop_id": mine["players"][1]["id"]})
    assert s == 409


def test_draft_refuses_to_start_when_the_player_pool_is_too_small(world, alice):
    full_import(MockNBAProvider(today=date(2026, 10, 27)))                            # 48 draftable players
    s, lg = alice.post("/api/leagues", {"sport": "nba", "name": "Too Big", "num_teams": 4})   # default roster: 4 x 13 = 52 picks
    assert s == 201
    s, res = alice.post(f"/api/leagues/{lg['id']}/draft/start", {})
    assert s == 409 and "Not enough players" in res["error"]
    s, state = alice.get(f"/api/leagues/{lg['id']}/draft")
    assert state["session"] is None and state["league_status"] == "pre_draft"          # nothing half-started
