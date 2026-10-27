"""FantaBall database models (Flask-SQLAlchemy, same style as models/people.py).

The existing 'people' table is left untouched. FantaBall users live in 'managers',
keyed by the email that the existing JWT auth manager reports.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Text, UniqueConstraint, Index, text
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
    is_demo_bot: Mapped[bool] = mapped_column(default=False)      # True = computer-controlled manager (fills empty league seats)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Sport(db.Model):
    __tablename__ = "sports"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True)         # "nba"
    name: Mapped[str] = mapped_column(Text)
    data_source: Mapped[str] = mapped_column(Text)               # who supplied the data: "balldontlie" (tests use "mock")
    season: Mapped[int | None]                                   # provider season, e.g. 2026 = the 2026-27 NBA season
    season_start: Mapped[date | None]                            # Monday that is "day 1" of the sim-day numbering


class ProTeam(db.Model):
    """A professional team (e.g. an NBA franchise)."""
    __tablename__ = "pro_teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"))
    abbr: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)           # e.g. "balldontlie"
    provider_id: Mapped[int | None]
    conference: Mapped[str | None] = mapped_column(Text)
    division: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime | None]
    __table_args__ = (UniqueConstraint("sport_id", "abbr"), UniqueConstraint("sport_id", "provider", "provider_id"))


class Athlete(db.Model):
    __tablename__ = "athletes"
    id: Mapped[int] = mapped_column(primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"), index=True)
    pro_team_id: Mapped[int] = mapped_column(ForeignKey("pro_teams.id"))
    name: Mapped[str] = mapped_column(Text)
    positions: Mapped[str] = mapped_column(Text)            # comma separated, e.g. "PG,SG"
    age: Mapped[int | None]
    rank: Mapped[int]                                       # preseason consensus rank (1 = best); real data: derived from imported stats
    provider: Mapped[str | None] = mapped_column(Text)
    provider_id: Mapped[int | None]
    first_name: Mapped[str | None] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    height: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[str | None] = mapped_column(Text)
    provider_position: Mapped[str | None] = mapped_column(Text)   # raw provider value, e.g. "G-F"
    active: Mapped[bool] = mapped_column(default=True)
    meta: Mapped[dict | None] = mapped_column(db.JSON)            # extra provider fields (college, draft year ...)
    synced_at: Mapped[datetime | None]
    injury_start: Mapped[int | None]                        # first sim day missed
    injury_end: Mapped[int | None]                          # first sim day back
    injury_note: Mapped[str | None] = mapped_column(Text)
    pro_team: Mapped["ProTeam"] = relationship()
    __table_args__ = (UniqueConstraint("sport_id", "provider", "provider_id"),)

    @property
    def position_list(self):
        return [p for p in (self.positions or "").split(",") if p]

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
    provider: Mapped[str | None] = mapped_column(Text)
    provider_id: Mapped[int | None]
    season: Mapped[int | None]
    postseason: Mapped[bool] = mapped_column(default=False)
    starts_at: Mapped[datetime | None]                             # scheduled tip-off (UTC, naive)
    game_date: Mapped[date | None]
    status: Mapped[str] = mapped_column(Text, default="scheduled") # scheduled | in_progress | final
    home_score: Mapped[int | None]
    away_score: Mapped[int | None]
    synced_at: Mapped[datetime | None]
    stats_synced_at: Mapped[datetime | None]                       # last time box scores were imported for this game
    __table_args__ = (UniqueConstraint("sport_id", "provider", "provider_id"),)


class GameStat(db.Model):
    """An athlete's box-score line for one game."""
    __tablename__ = "game_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    pro_game_id: Mapped[int] = mapped_column(ForeignKey("pro_games.id"))
    day: Mapped[int]
    stats: Mapped[dict] = mapped_column(db.JSON)                  # scoring view: only stats the source actually reported
    # Typed source statistics. NULL = the provider did not report it (never silently 0).
    minutes: Mapped[float | None]
    pts: Mapped[int | None]
    reb: Mapped[int | None]
    oreb: Mapped[int | None]
    dreb: Mapped[int | None]
    ast: Mapped[int | None]
    stl: Mapped[int | None]
    blk: Mapped[int | None]
    tov: Mapped[int | None]
    fgm: Mapped[int | None]
    fga: Mapped[int | None]
    fg3m: Mapped[int | None]
    fg3a: Mapped[int | None]
    ftm: Mapped[int | None]
    fta: Mapped[int | None]
    pf: Mapped[int | None]
    plus_minus: Mapped[int | None]
    source: Mapped[str | None] = mapped_column(Text)              # provider name
    provider_stat_id: Mapped[int | None]
    provider_updated_at: Mapped[datetime | None]
    synced_at: Mapped[datetime | None]
    __table_args__ = (UniqueConstraint("athlete_id", "day"), UniqueConstraint("athlete_id", "pro_game_id"), Index("ix_game_stats_day", "day"))


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
    season: Mapped[int | None]
    first_week: Mapped[int] = mapped_column(default=1)            # first scoring week (leagues drafted mid-season start later)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    sport: Mapped["Sport"] = relationship()
    scoring: Mapped["ScoringConfig"] = relationship(back_populates="league", uselist=False)


class ScoringRuleSet(db.Model):
    """An immutable set of scoring weights. Leagues with identical rules share one row, and persisted fantasy
    scores point at it, so changing a league's rules never rewrites history (a new rule set is used instead)."""
    __tablename__ = "scoring_rulesets"
    id: Mapped[int] = mapped_column(primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"))
    rules_hash: Mapped[str] = mapped_column(Text)
    rules: Mapped[dict] = mapped_column(db.JSON)
    name: Mapped[str | None] = mapped_column(Text)                    # set for named templates
    is_template: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    __table_args__ = (UniqueConstraint("sport_id", "rules_hash"),)


class ScoringConfig(db.Model):
    __tablename__ = "scoring_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"), unique=True)
    rules: Mapped[dict] = mapped_column(db.JSON)                      # {"pts": 1.0, ...}
    ruleset_id: Mapped[int | None] = mapped_column(ForeignKey("scoring_rulesets.id"))
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
    acquired_via: Mapped[str | None] = mapped_column(Text)            # draft | add | trade
    acquired_at: Mapped[datetime | None]
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
    finalized_at: Mapped[datetime | None]


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


class PlayerFantasyScore(db.Model):
    """Fantasy points one player earned in one game under one scoring rule set (NULL points = a needed stat was missing)."""
    __tablename__ = "player_fantasy_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    game_stat_id: Mapped[int] = mapped_column(ForeignKey("game_stats.id"))
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    pro_game_id: Mapped[int] = mapped_column(ForeignKey("pro_games.id"))
    day: Mapped[int]
    ruleset_id: Mapped[int] = mapped_column(ForeignKey("scoring_rulesets.id"))
    points: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    calculated_at: Mapped[datetime] = mapped_column(default=utcnow)
    __table_args__ = (UniqueConstraint("game_stat_id", "ruleset_id"), Index("ix_pfs_ruleset_day", "ruleset_id", "day"),
                      Index("ix_pfs_ruleset_athlete", "ruleset_id", "athlete_id"))


class TeamPeriodScore(db.Model):
    """A fantasy team's total for one scoring period (week) of one matchup."""
    __tablename__ = "team_period_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    matchup_id: Mapped[int] = mapped_column(ForeignKey("matchups.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("fantasy_teams.id"))
    week: Mapped[int]
    points: Mapped[float] = mapped_column(default=0.0)
    final: Mapped[bool] = mapped_column(default=False)
    calculated_at: Mapped[datetime] = mapped_column(default=utcnow)
    __table_args__ = (UniqueConstraint("matchup_id", "team_id"),)


class DataSyncRun(db.Model):
    """One execution of an ingestion job (what ran, when, what changed, and how it ended)."""
    __tablename__ = "data_sync_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(Text)
    job_type: Mapped[str] = mapped_column(Text)                       # teams_players | schedule | stats | corrections | scores | daily | backfill
    status: Mapped[str] = mapped_column(Text, default="running")      # running | success | partial | failed | blocked
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]
    inserted: Mapped[int] = mapped_column(default=0)
    updated: Mapped[int] = mapped_column(default=0)
    skipped: Mapped[int] = mapped_column(default=0)
    requests_made: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    marker: Mapped[str | None] = mapped_column(Text)                  # what was covered, e.g. "2026-10-20..2026-10-26"
    params: Mapped[dict | None] = mapped_column(db.JSON)
    triggered_by: Mapped[str | None] = mapped_column(Text)            # cli | admin:<email> | schedule
    # Only ONE run per provider may be 'running' at a time (blocks duplicate scheduler / multi-worker runs)
    __table_args__ = (Index("uq_sync_one_running", "provider", unique=True, sqlite_where=text("status = 'running'")),)
