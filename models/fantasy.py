"""FantaBall database models (Flask-SQLAlchemy, same style as models/people.py).

The existing 'people' table is left untouched. FantaBall users live in 'managers',
keyed by the email that the existing JWT auth manager reports.
"""
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from root import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Manager(db.Model):
    """A FantaBall user (profile for an authenticated email)."""
    __tablename__ = "managers"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    is_demo_bot: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Sport(db.Model):
    __tablename__ = "sports"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)


class ProTeam(db.Model):
    """A professional team (e.g. an NBA franchise)."""
    __tablename__ = "pro_teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"))
    abbr: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("sport_id", "abbr"),)


class Athlete(db.Model):
    __tablename__ = "athletes"
    id: Mapped[int] = mapped_column(primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"), index=True)
    pro_team_id: Mapped[int] = mapped_column(ForeignKey("pro_teams.id"))
    name: Mapped[str] = mapped_column(Text)
    positions: Mapped[str] = mapped_column(Text)            # comma separated, e.g. "PG,SG"
    age: Mapped[int]
    rank: Mapped[int]                                       # preseason consensus rank (1 = best)
    injury_start: Mapped[int | None]                        # first sim day missed
    injury_end: Mapped[int | None]                          # first sim day back
    injury_note: Mapped[str | None] = mapped_column(Text)
    is_simulated: Mapped[bool] = mapped_column(default=True)
    pro_team: Mapped["ProTeam"] = relationship()

    @property
    def position_list(self):
        return self.positions.split(",")

    def injury_status(self, day: int) -> str:
        """HEALTHY, DTD (out 3 days or fewer) or OUT on sim day `day`."""
        if self.injury_start is None or not (self.injury_start <= day < self.injury_end):
            return "HEALTHY"
        return "DTD" if (self.injury_end - self.injury_start) <= 3 else "OUT"


class ProGame(db.Model):
    """One scheduled professional game."""
    __tablename__ = "pro_games"
    id: Mapped[int] = mapped_column(primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"))
    day: Mapped[int] = mapped_column(index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("pro_teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("pro_teams.id"))


class GameStat(db.Model):
    """An athlete's (simulated) stat line for one game."""
    __tablename__ = "game_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    pro_game_id: Mapped[int] = mapped_column(ForeignKey("pro_games.id"))
    day: Mapped[int]
    stats: Mapped[dict] = mapped_column(db.JSON)
    __table_args__ = (UniqueConstraint("athlete_id", "day"), Index("ix_game_stats_day", "day"))


class League(db.Model):
    __tablename__ = "leagues"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"))
    commissioner_id: Mapped[int] = mapped_column(ForeignKey("managers.id"))
    invite_code: Mapped[str] = mapped_column(Text, unique=True)
    format: Mapped[str] = mapped_column(Text, default="h2h_points")   # future: h2h_cats, roto
    num_teams: Mapped[int] = mapped_column(default=12)
    roster_config: Mapped[list] = mapped_column(db.JSON)              # [["PG",1],...]
    status: Mapped[str] = mapped_column(Text, default="pre_draft")     # pre_draft | drafting | active
    current_day: Mapped[int] = mapped_column(default=0)
    is_demo: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    sport: Mapped["Sport"] = relationship()
    scoring: Mapped["ScoringConfig"] = relationship(back_populates="league", uselist=False)


class ScoringConfig(db.Model):
    __tablename__ = "scoring_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), unique=True)
    rules: Mapped[dict] = mapped_column(db.JSON)                      # {"pts": 1.0, ...}
    league: Mapped["League"] = relationship(back_populates="scoring")


class FantasyTeam(db.Model):
    """A team in a league. Computer-controlled teams have is_bot=True and their own manager row."""
    __tablename__ = "fantasy_teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("managers.id"))
    name: Mapped[str] = mapped_column(Text)
    is_bot: Mapped[bool] = mapped_column(default=False)
    auto_lineup: Mapped[bool] = mapped_column(default=False)
    draft_slot: Mapped[int | None]                                    # 1-based position in round 1
    manager: Mapped["Manager"] = relationship()
    __table_args__ = (UniqueConstraint("league_id", "manager_id"),)


class RosterSlot(db.Model):
    """One athlete on one team, in one lineup slot.

    UNIQUE(league_id, athlete_id) guarantees an athlete is owned by at most one team per league.
    """
    __tablename__ = "roster_slots"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("fantasy_teams.id"), index=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    slot: Mapped[str] = mapped_column(Text)                           # PG.. UTIL, BN, IR
    athlete: Mapped["Athlete"] = relationship()
    __table_args__ = (UniqueConstraint("league_id", "athlete_id"),)


class DraftSession(db.Model):
    __tablename__ = "draft_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), unique=True)
    status: Mapped[str] = mapped_column(Text, default="pending")      # pending | live | complete
    rounds: Mapped[int] = mapped_column(default=13)
    pick_seconds: Mapped[int] = mapped_column(default=45)
    current_pick: Mapped[int] = mapped_column(default=1)              # overall pick number on the clock
    pick_deadline: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class DraftPick(db.Model):
    __tablename__ = "draft_picks"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("draft_sessions.id"), index=True)
    overall: Mapped[int]
    round: Mapped[int]
    team_id: Mapped[int] = mapped_column(ForeignKey("fantasy_teams.id"))
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    auto: Mapped[bool] = mapped_column(default=False)
    made_at: Mapped[datetime] = mapped_column(default=utcnow)
    athlete: Mapped["Athlete"] = relationship()
    __table_args__ = (UniqueConstraint("session_id", "overall"), UniqueConstraint("session_id", "athlete_id"))


class DraftQueueItem(db.Model):
    __tablename__ = "draft_queue"
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("fantasy_teams.id"), index=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    position: Mapped[int]
    __table_args__ = (UniqueConstraint("team_id", "athlete_id"),)


class Matchup(db.Model):
    __tablename__ = "matchups"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    week: Mapped[int]
    home_team_id: Mapped[int] = mapped_column(ForeignKey("fantasy_teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("fantasy_teams.id"))
    home_score: Mapped[float] = mapped_column(default=0.0)
    away_score: Mapped[float] = mapped_column(default=0.0)
    final: Mapped[bool] = mapped_column(default=False)


class DailyScore(db.Model):
    """Lineup snapshot: points an athlete scored on a day, and whether his slot counted."""
    __tablename__ = "daily_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("fantasy_teams.id"))
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    day: Mapped[int]
    slot: Mapped[str] = mapped_column(Text)
    points: Mapped[float]
    counted: Mapped[bool]
    __table_args__ = (Index("ix_daily_team_day", "team_id", "day"),)


class PlayerTransaction(db.Model):
    """Add / drop / trade ledger."""
    __tablename__ = "player_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("fantasy_teams.id"))
    kind: Mapped[str] = mapped_column(Text)                           # add | drop | trade_in | trade_out
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    day: Mapped[int]
    related_team_id: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    athlete: Mapped["Athlete"] = relationship()


class TradeOffer(db.Model):
    __tablename__ = "trade_offers"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    from_team_id: Mapped[int] = mapped_column(ForeignKey("fantasy_teams.id"))
    to_team_id: Mapped[int] = mapped_column(ForeignKey("fantasy_teams.id"))
    status: Mapped[str] = mapped_column(Text, default="pending")      # pending | accepted | declined | cancelled
    note: Mapped[str | None] = mapped_column(Text)
    response_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_at: Mapped[datetime | None]
    items: Mapped[list["TradeItem"]] = relationship(cascade="all, delete-orphan")


class TradeItem(db.Model):
    __tablename__ = "trade_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("trade_offers.id"))
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    from_team_id: Mapped[int] = mapped_column(ForeignKey("fantasy_teams.id"))   # owner when proposed
    athlete: Mapped["Athlete"] = relationship()


class WaiverClaim(db.Model):
    """Schema only (stretch goal): claims can be stored but are not processed yet."""
    __tablename__ = "waiver_claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("fantasy_teams.id"))
    add_athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    drop_athlete_id: Mapped[int | None] = mapped_column(ForeignKey("athletes.id"))
    priority: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Activity(db.Model):
    """League activity feed."""
    __tablename__ = "league_activity"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    day: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
