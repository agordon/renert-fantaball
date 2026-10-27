"""Highlightly NBA API provider  (https://highlightly.net/nba-api/documentation/ , OpenAPI: .../nba-api/documentation/docs.json)

Facts taken from the provider documentation and OpenAPI spec (read 2026-10-27) and confirmed against the live service
(no header -> HTTP 403 "Missing mandatory HTTP Headers"; invalid key -> HTTP 401 "Invalid request token"):
  * Base URL https://nba.highlightly.net ; the key goes in the `x-rapidapi-key` header (no host header when calling directly).
  * FREE plan: 100 requests/day, player stats and box scores included (no highlights / odds). Terms allow storing the data and
    using it in apps; they exclude cash-prize fantasy sports and betting (FantaBall has neither). Do not circumvent rate limits.
  * /teams?league=NBA, /matches (limit<=100, paginated; filters: date, season, league, timezone), /box-score/{matchId},
    /lineups/{matchId} (positions, isStarter). /players only lists id + name (no team, no position), so players are DISCOVERED
    from box scores and their positions come from lineups.
  * Responses carry `x-ratelimit-requests-remaining`; at zero further requests fail until the daily quota resets.

Request economy (the quota is small): one request per match for the box score, plus one lineup request ONLY when a player's
position is not yet known; scheduling uses date queries around today; the full-season list is fetched rarely.

Everything that interprets responses is a pure parse_* function so it can be unit-tested without a network.
"""
import re
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Iterator

from fantaball.nba.http import HttpClient
from fantaball.nba.provider import (GameRecord, NBADataProvider, PlayerRecord, ProviderBadResponse, ProviderNotConfigured, StatRecord, TeamRecord)

DEFAULT_BASE_URL = "https://nba.highlightly.net"
PAGE = 100
MAX_PAGES = 60
ET_ZONE = "America/New_York"

# FINDING (real response, 2026-10-27): GET /teams?league=NBA returns 54 entries labelled "NBA" - the 30 franchises PLUS international
# clubs, All-Star teams and exhibition opponents (NZ Breakers, Real Madrid, "Team LeBron" ...), some with an empty abbreviation.
# Real franchises are recognised by abbreviation; the aliases are the provider's spellings (NY, GS, SA, UTAH, WSH, NO ...).
NBA_FRANCHISES = frozenset("""ATL BOS BKN BRK CHA CHO CHI CLE DAL DEN DET GS GSW HOU IND LAC LAL MEM MIA MIL MIN NO NOP NY NYK OKC ORL PHI PHX PHO POR SAC
SA SAS TOR UTA UTAH WAS WSH""".split())

STATUS_MAP = {
    "finished": "final", "scheduled": "scheduled", "in progress": "in_progress", "end period": "in_progress", "half time": "in_progress",
    "postponed": "postponed", "cancelled": "cancelled", "canceled": "cancelled", "abandoned": "cancelled", "suspended": "postponed",
}

# box-score stat names (as documented) -> StatRecord field. Matching is case-insensitive; abbreviations are accepted too.
STAT_NAMES = {
    "total minutes played": "minutes", "minutes": "minutes", "min": "minutes",
    "total points scored": "pts", "points": "pts", "pts": "pts",
    "successful field goals": "fgm", "fgm": "fgm", "total field goals": "fga", "fga": "fga",
    "successful 3pt field goals": "fg3m", "3pm": "fg3m", "total 3pt field goals": "fg3a", "3pa": "fg3a",
    "successful free throws": "ftm", "ftm": "ftm", "total free throws": "fta", "fta": "fta",
    "total rebounds": "reb", "reb": "reb", "total assists": "ast", "ast": "ast", "total turnovers": "tov", "tov": "tov", "to": "tov",
    "total steals": "stl", "stl": "stl", "total blocks": "blk", "blk": "blk",
    "total offensive rebounds": "oreb", "oreb": "oreb", "total defensive rebounds": "dreb", "dreb": "dreb",
    "total fouls": "pf", "pf": "pf", "plus minus": "plus_minus", "+/-": "plus_minus",
}
COUNTING = ("pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "pf")


# ------------------------------------------------------------------ pure helpers / parsers
def _is_us_dst(utc: datetime) -> bool:
    """US daylight saving time: from the 2nd Sunday of March 02:00 local to the 1st Sunday of November 02:00 local."""
    y = utc.year

    def nth_sunday(month: int, n: int) -> date:
        first = date(y, month, 1)
        return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))
    start = datetime.combine(nth_sunday(3, 2), datetime.min.time()) + timedelta(hours=7)     # 02:00 EST == 07:00 UTC
    end = datetime.combine(nth_sunday(11, 1), datetime.min.time()) + timedelta(hours=6)      # 02:00 EDT == 06:00 UTC
    return start <= utc < end


def eastern_date(utc: datetime) -> date:
    """The calendar date in US Eastern time (NBA game days are Eastern; a 10 pm ET tip-off is the next day in UTC)."""
    return (utc - timedelta(hours=4 if _is_us_dst(utc) else 5)).date()


def _num(v):
    """number | numeric string | 'MM:SS' | None -> float | None (anything else is 'not reported')."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        if ":" in s:
            m, sec = s.split(":", 1)
            return round(int(m) + int(sec) / 60, 2)
        return float(s)
    except ValueError:
        return None


def _int(v):
    n = _num(v)
    return int(round(n)) if n is not None else None


def _utc(iso) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def split_name(full: str) -> tuple[str, str]:
    parts = (full or "").split()
    if len(parts) <= 1:
        return "", (parts[0] if parts else "")
    return " ".join(parts[:-1]), parts[-1]


def parse_team(d: dict) -> TeamRecord:
    name = d.get("name") or ""
    display = d.get("displayName") or name
    city = display[: -len(name)].strip() if name and display.endswith(name) else ""
    return TeamRecord(provider_id=int(d["id"]), abbr=d["abbreviation"], city=city, name=name or display)


def parse_match(d: dict) -> GameRecord:
    state = d.get("state") or {}
    description = str(state.get("description") or "").strip().lower()
    started = _utc(d.get("date"))
    if started is None:
        raise ProviderBadResponse("A match in the provider response had no valid date")
    # Final scores are not read: the documented `state.score` arrays are described per "inning" (copied from baseball), so their
    # meaning for basketball is unclear. Fantasy points never need them.
    return GameRecord(provider_id=int(d["id"]), season=int(d.get("season") or 0), postseason=False, game_date=eastern_date(started), starts_at=started,
                      status=STATUS_MAP.get(description, "scheduled"), home_team_id=int((d.get("homeTeam") or {})["id"]),
                      away_team_id=int((d.get("awayTeam") or {})["id"]))


def parse_lineups(body) -> dict:
    """{player id: position text} and {normalised name: position} from /lineups/{id} (home + away)."""
    by_id, by_name = {}, {}
    if isinstance(body, list):
        body = body[0] if body else {}
    for side in ("home", "away"):
        for p in ((body.get(side) or {}).get("lineup") or []):
            pos = p.get("positionAbbreviation") or p.get("position")
            if not pos:
                continue
            if p.get("id") is not None:
                by_id[int(p["id"])] = pos
            by_name[_norm(p.get("player"))] = pos
    return {"id": by_id, "name": by_name}


def _norm(name) -> str:
    return re.sub(r"[^a-z]", "", str(name or "").lower())


def parse_box_score(match_id: int, body, positions: dict | None = None) -> list[StatRecord]:
    """Player lines from /box-score/{matchId}. Players who did not play are skipped - they have no stat line.

    A stat the provider omitted or sent as null stays None (never 0), so such a game is later left unscored instead of wrong."""
    items = body if isinstance(body, list) else [body]
    positions = positions or {"id": {}, "name": {}}
    out = []
    for item in items:
        team = (item or {}).get("team", item) or {}
        team_id = int(team["id"]) if team.get("id") is not None else None
        # REAL response (2026-10-27): [{"team": {id, logo, name}, "boxScores": [...]}, ...] - boxScores NEXT TO team.
        # The OpenAPI spec nests it inside team; both layouts are accepted.
        for entry in (item or {}).get("boxScores") or team.get("boxScores") or []:
            player = entry.get("player") or {}
            if player.get("id") is None:
                continue
            values = {}
            for s in entry.get("statistics") or []:
                field = STAT_NAMES.get(str(s.get("name") or "").strip().lower())
                if field:
                    values[field] = _num(s.get("value"))
            if (values.get("minutes") or 0) == 0 and all((values.get(f) or 0) == 0 for f in COUNTING):
                continue                                                    # did not play
            pid = int(player["id"])
            first, last = split_name(player.get("name", ""))
            position = positions["id"].get(pid) or positions["name"].get(_norm(player.get("name")))
            fields = {f: (_int(values[f]) if f != "minutes" else values[f]) for f in values}
            out.append(StatRecord(provider_stat_id=None, player_provider_id=pid, game_provider_id=int(match_id), team_provider_id=team_id,
                                  player=PlayerRecord(provider_id=pid, first_name=first, last_name=last, position=position, team_provider_id=team_id), **fields))
    return out


# ------------------------------------------------------------------ provider
class HighlightlyProvider(NBADataProvider):
    name = "highlightly"
    supports_rosters = False        # /players has no team or position: players are discovered from box scores
    stats_by = "game"
    stats_chunk = 6
    daily_window = (2, 6)           # yesterday-ish .. next week: ~9 date queries; the full season is refreshed on Mondays
    corrections_days = 1
    stats_plan_hint = "Highlightly's free plan includes player box scores; check that your key is valid and the daily quota is not used up."

    def __init__(self, api_key: str | None, *, base_url: str = DEFAULT_BASE_URL, requests_per_minute: float = 10.0, max_requests: int | None = None,
                 daily_quota: int | None = 100, today=None, client: HttpClient | None = None):
        if not api_key and client is None:
            raise ProviderNotConfigured("HIGHLIGHTLY_API_KEY is not set. Create a free account at https://highlightly.net/ and put the key in .env as HIGHLIGHTLY_API_KEY.")
        self.http = client or HttpClient(base_url, api_key, auth_header="x-rapidapi-key", requests_per_minute=requests_per_minute, max_requests=max_requests,
                                         quota_header="x-ratelimit-requests-remaining")
        self.daily_quota = daily_quota
        self._today = today or (lambda: datetime.now(timezone.utc).date())
        self._season_offset: int | None = None

    @property
    def requests_made(self) -> int:
        return self.http.requests_made

    # --- paging ---------------------------------------------------------------------------------------------
    def _matches(self, params: dict, max_pages: int = MAX_PAGES) -> Iterator[dict]:
        offset = 0
        for _ in range(max_pages):
            body = self.http.get_json("matches", [(k, str(v)) for k, v in params.items()] + [("limit", str(PAGE)), ("offset", str(offset))])
            if not isinstance(body, dict) or "data" not in body:
                raise ProviderBadResponse("Unexpected response shape from matches")
            rows = body["data"]
            yield from rows
            total = (body.get("pagination") or {}).get("totalCount")
            offset += PAGE
            if not rows or total is None or offset >= total:
                return

    def _season_param(self, season: int) -> int:
        """Highlightly may number seasons by start or end year; learn it once from a real match near today."""
        if self._season_offset is None:
            today = self._today()
            for back in range(4):
                d = today - timedelta(days=back)
                first = next(self._matches({"league": "NBA", "date": d.isoformat(), "timezone": ET_ZONE}, max_pages=1), None)
                if first is not None and first.get("season"):
                    start_year = d.year if d.month >= 9 else d.year - 1
                    self._season_offset = int(first["season"]) - start_year
                    break
            else:
                raise ProviderBadResponse("Could not work out how Highlightly numbers seasons (no NBA matches found around today)")
        return season + self._season_offset

    # --- interface --------------------------------------------------------------------------------------------
    def teams(self) -> list[TeamRecord]:
        body = self.http.get_json("teams", [("league", "NBA")])
        rows = body.get("data") if isinstance(body, dict) else body
        if not isinstance(rows, list):
            raise ProviderBadResponse("Unexpected response shape from teams")
        return [parse_team(t) for t in rows if t.get("league") == "NBA" and str(t.get("abbreviation") or "").upper() in NBA_FRANCHISES]

    def players(self, team_ids: Iterable[int]) -> Iterator[PlayerRecord]:
        return iter(())             # see module docstring: rosters cannot be listed; players arrive with their box scores

    def games(self, *, season=None, start_date=None, end_date=None) -> Iterator[GameRecord]:
        if start_date or end_date:
            first = start_date or end_date
            last = end_date or start_date
            for i in range((last - first).days + 1):
                d = first + timedelta(days=i)
                for row in self._matches({"league": "NBA", "date": d.isoformat(), "timezone": ET_ZONE}):
                    yield parse_match(row)
        else:
            for row in self._matches({"league": "NBA", "season": self._season_param(season)}):
                yield parse_match(row)

    def stats(self, *, dates=None, game_ids=None, known_player_ids=None) -> Iterator[StatRecord]:
        if not game_ids:
            raise ValueError("Highlightly box scores are fetched per game: pass game_ids")
        known = known_player_ids or set()
        for gid in game_ids:
            lines = parse_box_score(gid, self.http.get_json(f"box-score/{gid}"))
            if any(rec.player_provider_id not in known for rec in lines):       # a new player: one lineup request teaches us the positions
                lines = _with_positions(lines, parse_lineups(self.http.get_json(f"lineups/{gid}")))
            yield from lines


def _with_positions(lines: list[StatRecord], positions: dict) -> list[StatRecord]:
    """Fill in missing player positions from a lineup (id first, then normalised name)."""
    from dataclasses import replace
    out = []
    for rec in lines:
        p = rec.player
        if p is not None and not p.position:
            pos = positions["id"].get(p.provider_id) or positions["name"].get(_norm(f"{p.first_name} {p.last_name}"))
            if pos:
                rec = replace(rec, player=replace(p, position=pos))
        out.append(rec)
    return out
