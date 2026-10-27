"""Provider-neutral records and the NBADataProvider interface.

The ingestion, scoring and web layers only ever see these plain dataclasses, so the data source (BALLDONTLIE today)
can be swapped without touching the fantasy scoring engine.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Iterator


# ------------------------------------------------------------------ errors
class ProviderError(Exception):
    """Base class: something went wrong talking to the data provider."""


class ProviderNotConfigured(ProviderError):
    """No API key / provider selected."""


class ProviderAuthError(ProviderError):
    """HTTP 401: key missing/invalid, OR the key's plan does not include this endpoint."""


class ProviderAccessError(ProviderError):
    """HTTP 403: forbidden for this key/plan."""


class ProviderRateLimited(ProviderError):
    """HTTP 429 persisted after all retries."""


class ProviderUnavailable(ProviderError):
    """5xx / network failure / timeout persisted after all retries."""


class ProviderBadResponse(ProviderError):
    """4xx other than 401/403/429, or a response that could not be parsed."""


# ------------------------------------------------------------------ records
@dataclass(frozen=True)
class TeamRecord:
    provider_id: int
    abbr: str
    city: str
    name: str
    conference: str | None = None
    division: str | None = None


@dataclass(frozen=True)
class PlayerRecord:
    provider_id: int
    first_name: str
    last_name: str
    position: str | None = None            # raw provider text, e.g. "G-F"
    height: str | None = None
    weight: str | None = None
    team_provider_id: int | None = None
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GameRecord:
    provider_id: int
    season: int
    postseason: bool
    game_date: date
    starts_at: datetime | None
    status: str                             # scheduled | in_progress | final
    home_team_id: int                       # provider team ids
    away_team_id: int
    home_score: int | None = None
    away_score: int | None = None


@dataclass(frozen=True)
class StatRecord:
    """One player's box-score line. None means 'the provider did not report this value'."""
    provider_stat_id: int | None
    player_provider_id: int
    game_provider_id: int
    team_provider_id: int | None
    minutes: float | None = None
    pts: int | None = None
    reb: int | None = None
    oreb: int | None = None
    dreb: int | None = None
    ast: int | None = None
    stl: int | None = None
    blk: int | None = None
    tov: int | None = None
    fgm: int | None = None
    fga: int | None = None
    fg3m: int | None = None
    fg3a: int | None = None
    ftm: int | None = None
    fta: int | None = None
    pf: int | None = None
    plus_minus: int | None = None
    player: PlayerRecord | None = None      # embedded player info (lets us create a missing player)


STAT_FIELDS = ("minutes", "pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pf", "plus_minus")


# ------------------------------------------------------------------ interface
class NBADataProvider(ABC):
    name: str                               # stored in Sport.data_source and on every imported row
    is_mock: bool = False

    @abstractmethod
    def teams(self) -> list[TeamRecord]: ...

    @abstractmethod
    def players(self, team_ids: Iterable[int]) -> Iterator[PlayerRecord]:
        """Current players of the given provider team ids."""

    @abstractmethod
    def games(self, *, season: int | None = None, start_date: date | None = None, end_date: date | None = None) -> Iterator[GameRecord]: ...

    @abstractmethod
    def stats(self, *, dates: list[date] | None = None, game_ids: list[int] | None = None) -> Iterator[StatRecord]:
        """Player box scores for the given dates or games."""

    @property
    def requests_made(self) -> int:
        return 0
