"""BALLDONTLIE NBA API provider  (https://docs.balldontlie.io/ , OpenAPI: https://www.balldontlie.io/openapi/nba.yml)

Verified against the provider documentation (checked 2026-10-27):
  * Auth: the key goes in the `Authorization` header (no "Bearer"). Base path: https://api.balldontlie.io/nba/v1
  * Pagination: cursor based. `per_page` max 100; follow `meta.next_cursor` until it is absent.
  * Plans: FREE = teams, players, games only, 5 requests/min.  ALL-STAR ($9.99/mo, 60 req/min) adds game player
    stats (/stats).  GOAT ($39.99/mo, 600 req/min) adds season averages, box scores, standings, etc.
    => WITHOUT a paid plan, /stats answers HTTP 401 and fantasy points cannot be computed from real box scores.
  * History: data back to 1946 (stats availability by endpoint differs).

Everything else about this module (field names) follows the OpenAPI spec; the parse_* functions are pure so they can be
unit-tested against recorded responses without network access.
"""
from datetime import date, datetime, timezone
from typing import Iterable, Iterator

from fantaball.nba.http import HttpClient
from fantaball.nba.provider import (GameRecord, NBADataProvider, PlayerRecord, ProviderBadResponse, ProviderNotConfigured, StatRecord, TeamRecord)

DEFAULT_BASE_URL = "https://api.balldontlie.io/nba/v1"
PER_PAGE = 100
MAX_PAGES = 500          # safety stop against a pagination loop


# ------------------------------------------------------------------ pure parsers
def _int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_minutes(v) -> float | None:
    """'34:12' -> 34.2, '34' -> 34.0, '' / None -> None (not reported)."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        if ":" in v:
            m, s = v.split(":", 1)
            return round(int(m) + int(s) / 60, 2)
        return float(v)
    except ValueError:
        return None


def parse_team(d: dict) -> TeamRecord:
    return TeamRecord(provider_id=int(d["id"]), abbr=d["abbreviation"], city=d.get("city") or "", name=d.get("name") or "",
                      conference=d.get("conference") or None, division=d.get("division") or None)


def parse_player(d: dict) -> PlayerRecord:
    team = d.get("team") or {}
    meta = {k: d.get(k) for k in ("jersey_number", "college", "country", "draft_year", "draft_round", "draft_number") if d.get(k) not in (None, "")}
    meta["roster"] = True            # this source states positions itself (unlike lineup-derived ones)
    return PlayerRecord(provider_id=int(d["id"]), first_name=d.get("first_name") or "", last_name=d.get("last_name") or "",
                        position=d.get("position") or None, height=d.get("height") or None,
                        weight=str(d["weight"]) if d.get("weight") not in (None, "") else None,
                        team_provider_id=_int(team.get("id")) if team else None, meta=meta)


def _parse_dt(v) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def parse_game(d: dict) -> GameRecord:
    status_text = (d.get("status") or "").strip()
    state = (d.get("status_state") or "").lower()
    if status_text.lower().startswith("final") or state in ("post", "final"):
        status = "final"
    elif state in ("in", "live") or (_int(d.get("period")) or 0) > 0:
        status = "in_progress"
    else:
        status = "scheduled"
    try:
        game_date = date.fromisoformat(str(d["date"])[:10])
    except (KeyError, ValueError) as exc:
        raise ProviderBadResponse("A game in the provider response had no valid date") from exc
    return GameRecord(provider_id=int(d["id"]), season=int(d["season"]), postseason=bool(d.get("postseason")), game_date=game_date,
                      starts_at=_parse_dt(d.get("datetime")), status=status, home_team_id=int(d["home_team"]["id"]),
                      away_team_id=int(d["visitor_team"]["id"]), home_score=_int(d.get("home_team_score")) if status != "scheduled" else None,
                      away_score=_int(d.get("visitor_team_score")) if status != "scheduled" else None)


def parse_stat(d: dict) -> StatRecord:
    player, game, team = d.get("player") or {}, d.get("game") or {}, d.get("team") or {}
    return StatRecord(
        provider_stat_id=_int(d.get("id")), player_provider_id=int(player["id"]), game_provider_id=int(game["id"]),
        team_provider_id=_int(team.get("id")), minutes=parse_minutes(d.get("min")), pts=_int(d.get("pts")), reb=_int(d.get("reb")),
        oreb=_int(d.get("oreb")), dreb=_int(d.get("dreb")), ast=_int(d.get("ast")), stl=_int(d.get("stl")), blk=_int(d.get("blk")),
        tov=_int(d.get("turnover")), fgm=_int(d.get("fgm")), fga=_int(d.get("fga")), fg3m=_int(d.get("fg3m")), fg3a=_int(d.get("fg3a")),
        ftm=_int(d.get("ftm")), fta=_int(d.get("fta")), pf=_int(d.get("pf")), plus_minus=_int(d.get("plus_minus")),
        player=parse_player({**player, "team": team}) if player else None)


# ------------------------------------------------------------------ provider
class BallDontLieProvider(NBADataProvider):
    name = "balldontlie"
    stats_plan_hint = ("BALLDONTLIE returns HTTP 401 for player stats on the free plan; box scores need the ALL-STAR plan ($9.99/month). "
                       "Teams, players and schedules still sync.")

    def __init__(self, api_key: str | None, *, base_url: str = DEFAULT_BASE_URL, requests_per_minute: float = 5.0, client: HttpClient | None = None, **client_opts):
        if not api_key and client is None:
            raise ProviderNotConfigured("BALLDONTLIE_API_KEY is not set. Create a free key at https://www.balldontlie.io/ and put it in .env as FLASK_BALLDONTLIE_API_KEY.")
        self.http = client or HttpClient(base_url, api_key, requests_per_minute=requests_per_minute, **client_opts)

    @property
    def requests_made(self) -> int:
        return self.http.requests_made

    def _paged(self, path: str, params: list[tuple[str, str]]) -> Iterator[dict]:
        cursor = None
        for _ in range(MAX_PAGES):
            page_params = params + [("per_page", str(PER_PAGE))] + ([("cursor", str(cursor))] if cursor is not None else [])
            body = self.http.get_json(path, page_params)
            if not isinstance(body, dict) or "data" not in body:
                raise ProviderBadResponse(f"Unexpected response shape from {path}")
            yield from body["data"]
            cursor = (body.get("meta") or {}).get("next_cursor")
            if cursor is None:
                return
        raise ProviderBadResponse(f"Pagination for {path} did not finish after {MAX_PAGES} pages")

    def teams(self) -> list[TeamRecord]:
        body = self.http.get_json("teams")
        if not isinstance(body, dict) or "data" not in body:
            raise ProviderBadResponse("Unexpected response shape from teams")
        # The provider also lists historical / special teams; real current franchises have a conference and division.
        return [parse_team(t) for t in body["data"] if t.get("conference") and t.get("division")]

    def players(self, team_ids: Iterable[int]) -> Iterator[PlayerRecord]:
        for tid in team_ids:       # one paginated query per team keeps us to current rosters instead of all players ever
            for row in self._paged("players", [("team_ids[]", str(tid))]):
                yield parse_player(row)

    def games(self, *, season=None, start_date=None, end_date=None) -> Iterator[GameRecord]:
        params: list[tuple[str, str]] = []
        if season is not None:
            params.append(("seasons[]", str(season)))
        if start_date:
            params.append(("start_date", start_date.isoformat()))
        if end_date:
            params.append(("end_date", end_date.isoformat()))
        for row in self._paged("games", params):
            yield parse_game(row)

    def stats(self, *, dates=None, game_ids=None) -> Iterator[StatRecord]:
        params = [("dates[]", d.isoformat()) for d in (dates or [])] + [("game_ids[]", str(g)) for g in (game_ids or [])]
        if not params:
            raise ValueError("stats() needs dates or game_ids")
        for row in self._paged("stats", params):
            yield parse_stat(row)
