"""BALLDONTLIE provider: response parsing, pagination, retries / error handling. No network: a fake opener plays canned responses."""
import io
import json
import urllib.error

import pytest

from fantaball.nba.balldontlie import BallDontLieProvider, parse_game, parse_minutes, parse_player, parse_stat, parse_team
from fantaball.nba.http import HttpClient
from fantaball.nba.provider import (ProviderAccessError, ProviderAuthError, ProviderBadResponse, ProviderNotConfigured, ProviderRateLimited,
                                    ProviderUnavailable)

SECRET = "SUPER-SECRET-KEY-123"


class FakeResponse:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, headers=None):
    return urllib.error.HTTPError("http://x", code, "err", headers or {}, io.BytesIO(b"{}"))


class Script:
    """Opener that plays a list of results (payload dict or exception) and records requests."""

    def __init__(self, *results):
        self.results = list(results)
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append((req.full_url, dict(req.header_items()), timeout))
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return FakeResponse(r)


def client(script, **kw):
    sleeps = []
    c = HttpClient("https://api.example.test/nba/v1", SECRET, opener=script, sleep=sleeps.append, clock=lambda: 0.0, requests_per_minute=0, **kw)
    return c, sleeps


# ------------------------------------------------------------------ parsing
def test_parse_minutes():
    assert parse_minutes("34:12") == 34.2
    assert parse_minutes("34") == 34.0
    assert parse_minutes("") is None and parse_minutes(None) is None
    assert parse_minutes("garbage") is None


def test_parse_team_player_game_stat():
    team = parse_team({"id": 5, "conference": "East", "division": "Atlantic", "city": "Boston", "name": "Celtics", "abbreviation": "BOS"})
    assert (team.provider_id, team.abbr, team.conference) == (5, "BOS", "East")

    player = parse_player({"id": 9, "first_name": "A", "last_name": "B", "position": "G-F", "height": "6-5", "weight": "205", "college": "X", "team": {"id": 5}})
    assert player.position == "G-F" and player.team_provider_id == 5 and player.meta == {"college": "X"}
    nobody = parse_player({"id": 10, "first_name": "C", "last_name": "D", "position": "", "team": None})
    assert nobody.position is None and nobody.team_provider_id is None            # missing stays missing

    final = parse_game({"id": 1, "date": "2026-10-21", "season": 2026, "status": "Final", "period": 4, "postseason": False,
                        "datetime": "2026-10-22T00:30:00.000Z", "home_team_score": 100, "visitor_team_score": 90,
                        "home_team": {"id": 1}, "visitor_team": {"id": 2}})
    assert final.status == "final" and final.home_score == 100 and final.starts_at.hour == 0
    sched = parse_game({"id": 2, "date": "2026-10-28", "season": 2026, "status": "2026-10-29T00:00:00Z", "period": 0, "postseason": False,
                        "home_team_score": 0, "visitor_team_score": 0, "home_team": {"id": 1}, "visitor_team": {"id": 2}})
    assert sched.status == "scheduled" and sched.home_score is None                 # a scheduled game has no score yet
    live = parse_game({"id": 3, "date": "2026-10-27", "season": 2026, "status": "3rd Qtr", "period": 3, "home_team_score": 60, "visitor_team_score": 55,
                       "home_team": {"id": 1}, "visitor_team": {"id": 2}})
    assert live.status == "in_progress"

    stat = parse_stat({"id": 7, "min": "30:30", "pts": 20, "reb": 5, "ast": 4, "stl": 0, "blk": None, "turnover": 2, "fg3m": 3, "pf": 1,
                       "player": {"id": 9, "first_name": "A", "last_name": "B", "position": "G"}, "team": {"id": 5}, "game": {"id": 1}})
    assert stat.minutes == 30.5 and stat.pts == 20 and stat.stl == 0               # a real zero is kept as 0
    assert stat.blk is None and stat.fgm is None                                   # not reported -> None, never 0
    assert stat.tov == 2 and stat.player.provider_id == 9


# ------------------------------------------------------------------ http client
def test_http_retries_429_honouring_retry_after_then_succeeds():
    script = Script(http_error(429, {"Retry-After": "7"}), {"data": []})
    c, sleeps = client(script)
    assert c.get_json("games") == {"data": []}
    assert sleeps == [7.0] and c.requests_made == 2


def test_http_exponential_backoff_on_server_errors_then_gives_up():
    script = Script(*[http_error(503)] * 3)
    c, sleeps = client(script, max_retries=2, backoff_base=2.0)
    with pytest.raises(ProviderUnavailable):
        c.get_json("games")
    assert sleeps == [2.0, 4.0]                      # 2 retries -> backoff 2s then 4s
    assert c.requests_made == 3


def test_http_429_exhausted_raises_rate_limited():
    c, _ = client(Script(*[http_error(429)] * 2), max_retries=1)
    with pytest.raises(ProviderRateLimited):
        c.get_json("games")


@pytest.mark.parametrize("code, exc", [(401, ProviderAuthError), (403, ProviderAccessError), (404, ProviderBadResponse), (400, ProviderBadResponse)])
def test_http_client_errors_are_not_retried(code, exc):
    script = Script(http_error(code), {"data": []})
    c, sleeps = client(script)
    with pytest.raises(exc):
        c.get_json("stats")
    assert c.requests_made == 1 and sleeps == []


def test_http_network_error_retried_and_key_never_leaks():
    script = Script(urllib.error.URLError("boom"), TimeoutError(), {"data": [1]})
    c, sleeps = client(script, max_retries=3)
    assert c.get_json("teams", [("x", "1")]) == {"data": [1]}
    assert len(sleeps) == 2
    url, headers, timeout = script.requests[0]
    assert SECRET not in url and headers["Authorization"] == SECRET and timeout == c.timeout   # key only in the header
    c2, _ = client(Script(http_error(401)))
    with pytest.raises(ProviderAuthError) as info:
        c2.get_json("stats")
    assert SECRET not in str(info.value)


def test_http_rate_limit_spacing():
    sleeps, now = [], [0.0]
    script = Script({"data": []}, {"data": []})
    c = HttpClient("https://x.test", "k", opener=script, sleep=lambda s: (sleeps.append(s), now.__setitem__(0, now[0] + s)), clock=lambda: now[0], requests_per_minute=5)
    c.get_json("a")
    c.get_json("b")
    assert sleeps == [12.0]                           # 5 per minute -> at least 12 s between requests


def test_http_invalid_json_is_bad_response():
    class Bad(Script):
        def __call__(self, req, timeout=None):
            r = FakeResponse({})
            r._raw = b"<html>"
            return r
    c, _ = client(Bad())
    with pytest.raises(ProviderBadResponse):
        c.get_json("games")


# ------------------------------------------------------------------ provider: pagination, filtering, configuration
def test_pagination_follows_cursor_and_requests_max_page_size():
    p1 = {"data": [{"id": 1, "date": "2026-10-20", "season": 2026, "status": "Final", "home_team": {"id": 1}, "visitor_team": {"id": 2}}], "meta": {"next_cursor": 55, "per_page": 100}}
    p2 = {"data": [{"id": 2, "date": "2026-10-21", "season": 2026, "status": "Final", "home_team": {"id": 1}, "visitor_team": {"id": 2}}], "meta": {"per_page": 100}}
    script = Script(p1, p2)
    c, _ = client(script)
    provider = BallDontLieProvider("k", client=c)
    games = list(provider.games(season=2026))
    assert [g.provider_id for g in games] == [1, 2]
    first_url, second_url = script.requests[0][0], script.requests[1][0]
    assert "per_page=100" in first_url and "seasons%5B%5D=2026" in first_url and "cursor" not in first_url
    assert "cursor=55" in second_url


def test_pagination_loop_is_stopped(monkeypatch):
    import fantaball.nba.balldontlie as bdl
    monkeypatch.setattr(bdl, "MAX_PAGES", 3)
    loop = {"data": [], "meta": {"next_cursor": 1}}
    c, _ = client(Script(loop, loop, loop, loop))
    with pytest.raises(ProviderBadResponse):
        list(BallDontLieProvider("k", client=c).games(season=2026))


def test_teams_filters_out_non_franchises_and_unexpected_shape_is_rejected():
    c, _ = client(Script({"data": [
        {"id": 1, "conference": "East", "division": "Atlantic", "city": "Boston", "name": "Celtics", "abbreviation": "BOS"},
        {"id": 99, "conference": "", "division": "", "city": "", "name": "Special", "abbreviation": "SPC"}]}, {"unexpected": True}))
    provider = BallDontLieProvider("k", client=c)
    assert [t.abbr for t in provider.teams()] == ["BOS"]
    with pytest.raises(ProviderBadResponse):
        provider.teams()


def test_players_queried_per_team_and_stats_need_dates_or_games():
    script = Script({"data": [{"id": 1, "first_name": "A", "last_name": "B", "position": "C", "team": {"id": 7}}], "meta": {}},
                    {"data": [], "meta": {}})
    c, _ = client(script)
    provider = BallDontLieProvider("k", client=c)
    assert [p.provider_id for p in provider.players([7, 8])] == [1]
    assert "team_ids%5B%5D=7" in script.requests[0][0] and "team_ids%5B%5D=8" in script.requests[1][0]
    with pytest.raises(ValueError):
        list(provider.stats())


def test_missing_api_key_is_reported_clearly():
    with pytest.raises(ProviderNotConfigured, match="BALLDONTLIE_API_KEY"):
        BallDontLieProvider(None)
