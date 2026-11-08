"""Shared test helpers. The database only ever holds REAL-data-shaped rows imported from the offline fixture provider
(tests/mock_provider.py) - there is no simulated world in the application any more."""
from datetime import date

from root import db
from models import fantasy as m
from models.fantasy import Athlete, GameStat, PlayerFantasyScore, ProGame, ProTeam, Sport
from fantaball.nba import ingest

TODAY = date(2026, 10, 27)

# Small rosters: the fixture provider has 48 draftable players (6 teams x 8).
SMALL_ROSTER = [["PG", 1], ["SG", 1], ["SF", 1], ["PF", 1], ["C", 1], ["BN", 1]]                                  # 6 rounds
FULL_ROSTER = [["PG", 1], ["SG", 1], ["SF", 1], ["PF", 1], ["C", 1], ["G", 1], ["F", 1], ["UTIL", 1], ["BN", 2], ["IR", 1]]   # 10 rounds


def wipe_real_nba():
    """Remove the NBA sport and everything that points at it (leagues included) so tests are independent."""
    sport = db.session.scalar(db.select(Sport).where(Sport.code == "nba"))
    db.session.execute(db.delete(m.DataSyncRun))
    if sport is not None:
        leagues = db.select(m.League.id).where(m.League.sport_id == sport.id)
        teams = db.select(m.FantasyTeam.id).where(m.FantasyTeam.league_id.in_(leagues))
        sessions = db.select(m.DraftSession.id).where(m.DraftSession.league_id.in_(leagues))
        offers = db.select(m.TradeOffer.id).where(m.TradeOffer.league_id.in_(leagues))
        # children first (picks / items / queue reference rows that are deleted further down)
        db.session.execute(db.delete(m.DraftPick).where(m.DraftPick.session_id.in_(sessions)))
        db.session.execute(db.delete(m.TradeItem).where(m.TradeItem.offer_id.in_(offers)))
        db.session.execute(db.delete(m.DraftQueueItem).where(m.DraftQueueItem.team_id.in_(teams)))
        db.session.execute(db.delete(m.TeamPeriodScore).where(m.TeamPeriodScore.league_id.in_(leagues)))
        for model in (m.DailyScore, m.Matchup, m.RosterSlot, m.PlayerTransaction, m.TradeOffer, m.WaiverClaim, m.Activity, m.DraftSession):
            db.session.execute(db.delete(model).where(model.league_id.in_(leagues)))
        db.session.execute(db.delete(m.FantasyTeam).where(m.FantasyTeam.league_id.in_(leagues)))
        db.session.execute(db.delete(m.ScoringConfig).where(m.ScoringConfig.league_id.in_(leagues)))
        db.session.execute(db.delete(m.League).where(m.League.sport_id == sport.id))
        db.session.commit()
        ingest.purge_sport_data(sport)
    db.session.commit()


def full_import(provider):
    ingest.job_teams_players(provider)
    ingest.job_schedule(provider, season=2026)
    return ingest.job_stats(provider)


def count(model, *where):
    """Row count restricted to the fixture provider's rows."""
    scope = {ProTeam: ProTeam.provider == "mock", Athlete: Athlete.provider == "mock", ProGame: ProGame.provider == "mock", GameStat: GameStat.source == "mock",
             PlayerFantasyScore: PlayerFantasyScore.athlete_id.in_(db.select(Athlete.id).where(Athlete.provider == "mock"))}
    return db.session.scalar(db.select(db.func.count(model.id)).where(scope[model], *where))


def make_active_league(client, name="Active League", teams=4, roster=None):
    """Create a league through the API, draft everyone automatically and return its id (status: active)."""
    s, lg = client.post("/api/leagues", {"sport": "nba", "name": name, "num_teams": teams, "roster_config": roster or FULL_ROSTER})
    assert s == 201, lg
    lid = lg["id"]
    assert client.post(f"/api/leagues/{lid}/draft/start", {})[0] == 200
    assert client.post(f"/api/leagues/{lid}/draft/sim", {"to_end": True})[0] == 200
    return lid
