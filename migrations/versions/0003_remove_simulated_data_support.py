"""remove simulated data support

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27 11:29:27.216107

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def _purge_simulated_data():
    """Delete the simulated demo world (fictional players / schedules / stat lines, and every league built on it).

    Only sports whose data_source is 'demo' are touched; real provider data and real leagues are never affected.
    """
    c = op.get_bind()
    demo_sports = "(SELECT id FROM sports WHERE data_source = 'demo')"
    leagues = f"(SELECT id FROM leagues WHERE sport_id IN {demo_sports})"
    teams = f"(SELECT id FROM fantasy_teams WHERE league_id IN {leagues})"
    sessions = f"(SELECT id FROM draft_sessions WHERE league_id IN {leagues})"
    offers = f"(SELECT id FROM trade_offers WHERE league_id IN {leagues})"
    athletes = f"(SELECT id FROM athletes WHERE sport_id IN {demo_sports})"
    steps = [
        f"DELETE FROM draft_picks WHERE session_id IN {sessions}",
        f"DELETE FROM draft_queue WHERE team_id IN {teams}",
        f"DELETE FROM trade_items WHERE offer_id IN {offers}",
    ] + [f"DELETE FROM {t} WHERE league_id IN {leagues}" for t in (
        "team_period_scores", "daily_scores", "matchups", "roster_slots", "player_transactions", "trade_offers",
        "waiver_claims", "league_activity", "draft_sessions", "fantasy_teams", "scoring_configs")] + [
        f"DELETE FROM leagues WHERE sport_id IN {demo_sports}",
        f"DELETE FROM player_fantasy_scores WHERE athlete_id IN {athletes}",
        f"DELETE FROM game_stats WHERE athlete_id IN {athletes}",
        f"DELETE FROM pro_games WHERE sport_id IN {demo_sports}",
        f"DELETE FROM athletes WHERE sport_id IN {demo_sports}",
        f"DELETE FROM pro_teams WHERE sport_id IN {demo_sports}",
        f"DELETE FROM scoring_rulesets WHERE sport_id IN {demo_sports}",
        f"DELETE FROM sports WHERE data_source = 'demo'",
        # computer managers that no longer belong to any team
        "DELETE FROM managers WHERE is_demo_bot = 1 AND id NOT IN (SELECT manager_id FROM fantasy_teams)",
    ]
    for sql in steps:
        c.execute(sa.text(sql))


def upgrade():
    _purge_simulated_data()
    with op.batch_alter_table('athletes', schema=None) as batch_op:
        batch_op.drop_column('is_simulated')

    with op.batch_alter_table('leagues', schema=None) as batch_op:
        batch_op.drop_column('is_demo')



def downgrade():
    raise NotImplementedError("Simulated data was deleted - restore the database backup instead.")
