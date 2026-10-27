"""Highlightly provider: parsing of the documented response shapes, request economy, quota handling and ingestion.
Everything runs offline against a fake HTTP client that serves spec-shaped JSON."""
import io
import json
import urllib.error
from datetime import date, datetime

import pytest

from root import db
from models.fantasy import Athlete, DataSyncRun, GameStat, PlayerFantasyScore, ProGame, Sport
from fantaball.nba import ingest
from fantaball.nba.highlightly import (HighlightlyProvider, eastern_date, parse_box_score, parse_lineups, parse_match, parse_team, split_name)
from fantaball.nba.http import HttpClient
from fantaball.nba.provider import ProviderBadResponse, ProviderNotConfigured, ProviderRateLimited

TODAY = date(2026, 10, 27)


# ------------------------------------------------------------------ fixtures shaped like the documented responses
def team(i, abbr, city, name):
    return {"id": i, "name": name, "displayName": f"{city} {name}", "abbreviation": abbr, "league": "NBA", "logo": "x"}


TEAMS = [team(1, "MIA", "Miami", "Heat"), team(2, "BOS", "Boston", "Celtics"), team(3, "DEN", "Denver", "Nuggets"), team(4, "LAL", "Los Angeles", "Lakers")]


def match(mid, home, away, iso, state, season=2026):
    return {"id": mid, "league": "NBA", "season": season, "date": iso, "state": {"description": state, "period": 4, "clock": 0, "score": {"homeTeam": [25, 25, 25, 25], "awayTeam": [20, 20, 20, 20]}},
            "homeTeam": TEAMS[home - 1], "awayTeam": TEAMS[away - 1]}


def line(pid, name, **stats):
    names = {"minutes": "Total Minutes Played", "pts": "Total Points Scored", "fgm": "Successful Field Goals", "fga": "Total Field Goals", "fg3m": "Successful 3PT Field Goals",
             "fg3a": "Total 3PT Field Goals", "ftm": "Successful Free Throws", "fta": "Total Free Throws", "reb": "Total Rebounds", "ast": "Total Assists", "tov": "Total Turnovers",
             "stl": "Total Steals", "blk": "Total Blocks", "oreb": "Total Offensive Rebounds", "dreb": "Total Defensive Rebounds", "pf": "Total Fouls", "plus_minus": "Plus Minus"}
    return {"player": {"id": pid, "name": name, "jersey": 1}, "statistics": [{"name": names[k], "value": v} for k, v in stats.items()]}


FULL = dict(minutes=30, pts=20, fgm=8, fga=15, fg3m=2, fg3a=5, ftm=2, fta=2, reb=7, ast=5, tov=2, stl=1, blk=1, oreb=1, dreb=6, pf=3, plus_minus=4)


def box(match_id, home_lines, away_lines, h=1, a=2):
    """The REAL response layout: boxScores is a sibling of team."""
    return [{"team": {"id": h, "name": "home"}, "boxScores": home_lines}, {"team": {"id": a, "name": "away"}, "boxScores": away_lines}]


def box_spec_layout(home_lines, h=1):
    """The layout written in the OpenAPI spec: boxScores nested inside team."""
    return [{"team": {"id": h, "name": "home", "boxScores": home_lines}}]


def lineup_player(pid, name, pos, starter=False):
    return {"id": pid, "player": name, "position": pos, "positionAbbreviation": pos, "isStarter": starter}


class FakeHttp:
    """Plays the part of HttpClient: serves canned JSON by path and records every request."""

    def __init__(self, routes):
        self.routes, self.calls, self.requests_made = routes, [], 0

    def get_json(self, path, params=None):
        self.calls.append((path, dict(params or [])))
        self.requests_made += 1
        r = self.routes[path] if path in self.routes else self.routes[path.split("/")[0]]
        return r(dict(params or [])) if callable(r) else r

    def paths(self):
        return [p for p, _ in self.calls]


def provider(routes, **kw):
    return HighlightlyProvider(None, client=FakeHttp(routes), today=lambda: TODAY, **kw)


# ------------------------------------------------------------------ pure parsing
def test_eastern_dates_follow_us_daylight_saving():
    assert eastern_date(datetime(2026, 10, 28, 2, 30)) == date(2026, 10, 27)       # 10:30 pm EDT is already the next day in UTC
    assert eastern_date(datetime(2026, 12, 10, 1, 0)) == date(2026, 12, 9)         # winter: UTC-5
    # DST ends Sun 2026-11-01 at 06:00 UTC: before it UTC-4, after it UTC-5 (each instant differs between the two offsets)
    assert eastern_date(datetime(2026, 11, 1, 4, 30)) == date(2026, 11, 1)         # 00:30 EDT
    assert eastern_date(datetime(2026, 11, 2, 4, 30)) == date(2026, 11, 1)         # 23:30 EST
    # DST starts Sun 2026-03-08 at 07:00 UTC
    assert eastern_date(datetime(2026, 3, 8, 4, 30)) == date(2026, 3, 7)           # 23:30 EST
    assert eastern_date(datetime(2026, 3, 9, 4, 30)) == date(2026, 3, 9)           # 00:30 EDT


def test_parse_team_derives_city_and_name():
    t = parse_team(team(7, "DEN", "Denver", "Nuggets"))
    assert (t.provider_id, t.abbr, t.city, t.name) == (7, "DEN", "Denver", "Nuggets")
    assert parse_team({"id": 1, "displayName": "Mystery", "abbreviation": "MYS"}).city == ""


def test_parse_match_statuses_and_dates():
    m = parse_match(match(10, 1, 2, "2026-10-28T02:00:00.000Z", "Finished"))
    assert m.status == "final" and m.game_date == date(2026, 10, 27) and m.home_team_id == 1 and m.away_team_id == 2 and m.home_score is None
    assert parse_match(match(11, 1, 2, "2026-10-29T00:00:00.000Z", "Scheduled")).status == "scheduled"
    assert parse_match(match(12, 1, 2, "2026-10-27T23:00:00.000Z", "Half time")).status == "in_progress"
    assert parse_match(match(13, 1, 2, "2026-10-27T23:00:00.000Z", "Postponed")).status == "postponed"
    assert parse_match(match(14, 1, 2, "2026-10-27T23:00:00.000Z", "Cancelled")).status == "cancelled"
    assert parse_match(match(15, 1, 2, "2026-10-27T23:00:00.000Z", "Something New")).status == "scheduled"
    bad = match(16, 1, 2, "2026-10-27T23:00:00.000Z", "Finished")
    bad["date"] = None
    with pytest.raises(ProviderBadResponse):
        parse_match(bad)


def test_split_name():
    assert split_name("LeBron Raymone James") == ("LeBron Raymone", "James")
    assert split_name("Nene") == ("", "Nene")


def test_parse_box_score_maps_documented_stat_names_and_never_invents_zeros():
    body = box(5, [line(100, "Ann Lee", **FULL), line(101, "Bo Chen", minutes="12:30", pts=4, reb=None, ast=1, stl=0, blk=0, tov=1, fg3m=0)], [line(200, "Cy Diaz", **{**FULL, "pts": "18"})])
    recs = {r.player_provider_id: r for r in parse_box_score(5, body)}
    a = recs[100]
    assert (a.pts, a.reb, a.ast, a.stl, a.blk, a.tov, a.fg3m, a.fgm, a.fga, a.oreb, a.dreb, a.pf, a.plus_minus, a.minutes) == (20, 7, 5, 1, 1, 2, 2, 8, 15, 1, 6, 3, 4, 30.0)
    assert (a.team_provider_id, a.game_provider_id) == (1, 5) and a.player.first_name == "Ann" and a.player.last_name == "Lee"
    b = recs[101]
    assert b.minutes == 12.5 and b.reb is None and b.stl == 0 and b.fgm is None            # null stays null, a real 0 stays 0, an absent stat stays absent
    assert recs[200].pts == 18 and recs[200].team_provider_id == 2                          # numeric strings are accepted


def test_both_documented_and_real_box_score_layouts_parse_the_same():
    lines = [line(100, "Ann Lee", **FULL)]
    assert parse_box_score(5, box_spec_layout(lines)) == parse_box_score(5, box(5, lines, [])[:1])


FIXTURES = __import__("os").path.join(__import__("os").path.dirname(__file__), "fixtures")


def test_a_real_recorded_game_parses_with_positions():
    """highlightly_*_real.json are untouched responses recorded from the live API (match 1547001, 2026-10-20)."""
    box_body = json.load(open(FIXTURES + "/highlightly_box_score_real.json", encoding="utf-8"))
    lineup_body = json.load(open(FIXTURES + "/highlightly_lineups_real.json", encoding="utf-8"))
    recs = parse_box_score(1547001, box_body, parse_lineups(lineup_body))
    assert 14 <= len(recs) <= 30 and {r.team_provider_id for r in recs} >= {37}               # two teams, San Antonio among them
    wemby = next(r for r in recs if r.player.last_name == "Wembanyama")
    assert (wemby.pts, wemby.reb, wemby.ast, wemby.stl, wemby.blk, wemby.tov, wemby.fg3m, wemby.minutes) == (12, 13, 3, 1, 6, 4, 0, 34.0)
    assert wemby.player.position == "C" and wemby.team_provider_id == 37
    assert all(r.pts is not None and r.reb is not None and r.player.position in ("G", "F", "C") for r in recs)   # every line is scoreable and has a position
    from fantaball.scoring import default_rules, score_decimal
    stats = {("min" if k == "minutes" else k): getattr(wemby, k) for k in ("minutes", "pts", "reb", "ast", "stl", "blk", "tov", "fg3m")}
    assert float(score_decimal(stats, default_rules("nba"))) == 12 + 13 * 1.2 + 3 * 1.5 + 1 * 3 + 6 * 3 - 4 + 0     # 12+15.6+4.5+3+18-4 = 49.1


def test_players_who_did_not_play_have_no_stat_line():
    body = box(5, [line(100, "Ann Lee", **FULL), line(102, "Bench Warmer", minutes=0, pts=0, reb=0, ast=0), {"player": {"id": 103, "name": "No Stats"}, "statistics": []}], [])
    assert [r.player_provider_id for r in parse_box_score(5, body)] == [100]


def test_lineups_give_positions_by_id_and_name():
    body = {"home": {"team": TEAMS[0], "lineup": [lineup_player(100, "Ann Lee", "PG", True), lineup_player(101, "Bo Chen", "G-F")]},
            "away": {"team": TEAMS[1], "lineup": [lineup_player(200, "Cy Diaz", "C")]}}
    pos = parse_lineups(body)
    assert pos["id"] == {100: "PG", 101: "G-F", 200: "C"} and pos["name"]["cydiaz"] == "C"
    recs = parse_box_score(5, box(5, [line(100, "Ann Lee", **FULL)], [line(999, "Cy Diaz", **FULL)]), pos)
    assert {r.player_provider_id: r.player.position for r in recs} == {100: "PG", 999: "C"}     # second one matched by name


# ------------------------------------------------------------------ provider: requests, pagination, quota
def test_missing_key_message_names_the_variable():
    with pytest.raises(ProviderNotConfigured, match="HIGHLIGHTLY_API_KEY"):
        HighlightlyProvider(None)


REAL_TEAMS_RESPONSE = [   # shape and content taken from the real GET /teams?league=NBA answer (54 rows; a representative subset)
    {"id": 1, "name": "Heat", "displayName": "Miami Heat", "abbreviation": "MIA", "league": "NBA", "logo": "x"},
    {"id": 26, "name": "Knicks", "displayName": "New York Knicks", "abbreviation": "NY", "league": "NBA", "logo": "x"},
    {"id": 43, "name": "Warriors", "displayName": "Golden State Warriors", "abbreviation": "GS", "league": "NBA", "logo": "x"},
    {"id": 45, "name": "Jazz", "displayName": "Utah Jazz", "abbreviation": "UTAH", "league": "NBA", "logo": "x"},
    {"id": 8158, "name": "Breakers", "displayName": "NEWZEALAND Breakers", "abbreviation": "NZL", "league": "NBA", "logo": "x"},
    {"id": 8139, "name": "Real Madrid", "displayName": "Real Madrid", "abbreviation": "REAL", "league": "NBA", "logo": "x"},
    {"id": 11023, "name": "Ulm", "displayName": "Ulm", "abbreviation": "", "league": "NBA", "logo": "x"},
    {"id": 1116925, "name": "Stars", "displayName": "Stars", "abbreviation": "", "league": "NBA", "logo": "x"},
    {"id": 398768, "name": "Pnx", "displayName": "Melbourne Pnx", "abbreviation": "", "league": "NBA", "logo": "x"},
]


def test_teams_keep_only_real_franchises_and_players_are_not_listed():
    p = provider({"teams": REAL_TEAMS_RESPONSE})
    got = p.teams()
    assert [t.abbr for t in got] == ["MIA", "NY", "GS", "UTAH"]                                # international / exhibition / blank-abbreviation entries are dropped
    assert [t.city for t in got] == ["Miami", "New York", "Golden State", "Utah"]
    assert list(p.players([1, 2])) == [] and p.http.paths() == ["teams"]                       # no request wasted on /players
    assert p.http.calls[0][1] == {"league": "NBA"}


def test_every_real_nba_abbreviation_variant_is_recognised():
    from fantaball.nba.highlightly import NBA_FRANCHISES
    real_30 = "MIA BOS DEN LAL ATL ORL DET NY CHI HOU LAC POR SAC CHA TOR CLE IND SA OKC MIL DAL MIN MEM GS UTAH PHX BKN WSH NO PHI".split()
    assert len(real_30) == 30 and set(real_30) <= NBA_FRANCHISES


def test_matches_are_paged_by_offset_until_total_count():
    pages = {0: [match(i, 1, 2, "2026-10-20T23:00:00Z", "Finished") for i in range(1, 101)], 100: [match(i, 1, 2, "2026-10-21T23:00:00Z", "Finished") for i in range(101, 131)]}
    p = provider({"matches": lambda q: {"data": pages[int(q["offset"])], "pagination": {"totalCount": 130, "offset": int(q["offset"]), "limit": 100}, "plan": {}}})
    p._season_offset = 0
    games = list(p.games(season=2026))
    assert len(games) == 130 and [c[1]["offset"] for c in p.http.calls] == ["0", "100"] and all(c[1]["limit"] == "100" for c in p.http.calls)
    assert p.http.calls[0][1]["season"] == "2026" and p.http.calls[0][1]["league"] == "NBA"


def test_season_numbering_is_learned_from_a_real_match():
    seen = []

    def matches(q):
        seen.append(q)
        if "date" in q:
            return {"data": [match(1, 1, 2, "2026-10-27T00:00:00Z", "Finished", season=2027)], "pagination": {"totalCount": 1, "offset": 0, "limit": 100}}
        return {"data": [], "pagination": {"totalCount": 0, "offset": 0, "limit": 100}}
    p = provider({"matches": matches})
    list(p.games(season=2026))
    assert seen[0]["date"] == "2026-10-27" and seen[1]["season"] == "2027"                    # provider numbers seasons by END year -> 2026-27 is 2027


def test_date_window_costs_one_request_per_day_with_the_eastern_timezone():
    p = provider({"matches": {"data": [], "pagination": {"totalCount": 0, "offset": 0, "limit": 100}}})
    list(p.games(start_date=date(2026, 10, 25), end_date=date(2026, 10, 27)))
    assert [c[1]["date"] for c in p.http.calls] == ["2026-10-25", "2026-10-26", "2026-10-27"] and all(c[1]["timezone"] == "America/New_York" for c in p.http.calls)


def test_lineup_requested_only_for_players_without_a_known_position():
    routes = {"box-score": box(5, [line(100, "Ann Lee", **FULL)], [line(200, "Cy Diaz", **FULL)]),
              "lineups": {"home": {"team": TEAMS[0], "lineup": [lineup_player(100, "Ann Lee", "PG")]}, "away": {"team": TEAMS[1], "lineup": [lineup_player(200, "Cy Diaz", "C")]}}}
    p = provider(routes)
    recs = list(p.stats(game_ids=[5], known_player_ids=set()))
    assert p.http.paths() == ["box-score/5", "lineups/5"] and {r.player.position for r in recs} == {"PG", "C"}
    p2 = provider(routes)
    list(p2.stats(game_ids=[5], known_player_ids={100, 200}))
    assert p2.http.paths() == ["box-score/5"]                                                  # everyone known: a single request per game
    with pytest.raises(ValueError):
        list(p.stats(dates=[TODAY]))


def test_http_client_sends_the_documented_header_and_stops_at_zero_quota():
    class Resp:
        def __init__(self, remaining):
            self.headers = {"x-ratelimit-requests-remaining": str(remaining)}

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    sent = []

    def opener(req, timeout=None):
        sent.append(dict(req.header_items()))
        return Resp(1 if len(sent) == 1 else 0)
    c = HttpClient("https://nba.example.test", "SECRET", auth_header="x-rapidapi-key", quota_header="x-ratelimit-requests-remaining", opener=opener,
                   sleep=lambda s: None, clock=lambda: 0.0, requests_per_minute=0)
    c.get_json("teams")
    assert sent[0]["X-rapidapi-key"] == "SECRET" and "Authorization" not in sent[0]
    c.get_json("teams")                                                                         # this reply says: 0 requests left today
    with pytest.raises(ProviderRateLimited, match="quota"):
        c.get_json("teams")
    assert len(sent) == 2                                                                       # nothing more was sent


def test_request_budget_caps_a_client():
    c = HttpClient("https://x.test", "k", opener=lambda r, timeout=None: io.BytesIO(b"{}") and type("R", (), {"headers": {}, "read": lambda s: b"{}", "__enter__": lambda s: s, "__exit__": lambda *a: False})(),
                   sleep=lambda s: None, clock=lambda: 0.0, requests_per_minute=0, max_requests=2)
    c.get_json("a")
    c.get_json("b")
    with pytest.raises(ProviderRateLimited, match="budget"):
        c.get_json("c")
    assert c.requests_made == 2


# ------------------------------------------------------------------ ingestion with the Highlightly provider (offline)
def league_routes(extra_unknown=False):
    """Two finished games on Oct 26 (ET) and one scheduled game today."""
    games = [match(10, 1, 2, "2026-10-27T00:00:00Z", "Finished"), match(11, 3, 4, "2026-10-27T01:00:00Z", "Finished"), match(12, 1, 3, "2026-10-28T00:00:00Z", "Scheduled")]
    p_ids = {1: (100, 101), 2: (200, 201), 3: (300, 301), 4: (400, 401)}
    boxes = {}
    for gid, h, a in ((10, 1, 2), (11, 3, 4)):
        boxes[gid] = box(gid, [line(p, f"Hoop Player{p}", **FULL) for p in p_ids[h]], [line(p, f"Hoop Player{p}", **FULL) for p in p_ids[a]], h, a)
    lineups = {gid: {"home": {"lineup": [lineup_player(p, f"Hoop Player{p}", ["PG", "C"][i]) for i, p in enumerate(p_ids[h])]},
                     "away": {"lineup": [lineup_player(p, f"Hoop Player{p}", ["SG", "F"][i]) for i, p in enumerate(p_ids[a])]}} for gid, h, a in ((10, 1, 2), (11, 3, 4))}
    if extra_unknown:                                   # a player the lineup does not list: stats arrive, position stays unknown
        boxes[10][0]["boxScores"].append(line(150, "Mystery Man", **FULL))
    matches = lambda q: {"data": games if q.get("season") or q.get("date") else [], "pagination": {"totalCount": len(games), "offset": 0, "limit": 100}}
    return {"teams": TEAMS, "matches": matches, "box-score": lambda q: None, "lineups": lambda q: None}, boxes, lineups


class RoutedHttp(FakeHttp):
    def __init__(self, base_routes, boxes, lineups):
        super().__init__(base_routes)
        self.boxes, self.lineups = boxes, lineups

    def get_json(self, path, params=None):
        if path.startswith("box-score/"):
            self.calls.append((path, {}))
            self.requests_made += 1
            return self.boxes[int(path.split("/")[1])]
        if path.startswith("lineups/"):
            self.calls.append((path, {}))
            self.requests_made += 1
            return self.lineups[int(path.split("/")[1])]
        return super().get_json(path, params)


def hl_provider(extra_unknown=False):
    routes, boxes, lineups = league_routes(extra_unknown)
    p = HighlightlyProvider(None, client=RoutedHttp(routes, boxes, lineups), today=lambda: TODAY)
    p._season_offset = 0
    return p


def test_full_import_creates_players_from_box_scores_scores_them_and_is_idempotent(world):
    p = hl_provider()
    assert ingest.job_teams_players(p).status == "success"
    assert db.session.scalar(db.select(db.func.count(Athlete.id)).where(Athlete.provider == "highlightly")) == 0       # nobody until box scores exist
    assert ingest.job_schedule(p, season=2026).status == "success"
    sport = db.session.scalar(db.select(Sport).where(Sport.code == "nba"))
    assert sport.data_source == "highlightly" and sport.season_start == date(2026, 10, 26)      # the Monday of the first game (Oct 26 ET)
    assert db.session.scalar(db.select(db.func.count(ProGame.id)).where(ProGame.provider == "highlightly")) == 3
    run = ingest.job_stats(p)
    assert run.status == "success" and run.inserted >= 8 + 8                        # 8 new players + 8 stat lines
    players = db.session.scalars(db.select(Athlete).where(Athlete.provider == "highlightly")).all()
    assert len(players) == 8 and all(a.positions for a in players)                  # positions came from the lineups
    assert {a.positions for a in players} == {"PG", "C", "SG", "SF,PF"}              # provider "F" -> our SF,PF
    stats = db.session.scalars(db.select(GameStat).where(GameStat.source == "highlightly")).all()
    assert len(stats) == 8 and all(s.pts == 20 and s.fg3m == 2 for s in stats)
    default_rules_total = db.session.scalar(db.select(db.func.count(PlayerFantasyScore.id)).join(Athlete, Athlete.id == PlayerFantasyScore.athlete_id).where(Athlete.provider == "highlightly"))
    assert default_rules_total == 8
    # the lineup requests were only made for games that introduced new players
    assert [c for c in p.http.paths() if c.startswith("lineups/")] == ["lineups/10", "lineups/11"]
    again = ingest.job_stats(p)
    assert again.inserted == 0 and again.updated == 0
    assert db.session.scalar(db.select(db.func.count(GameStat.id)).where(GameStat.source == "highlightly")) == 8
    # a re-run of the corrections job re-reads yesterday's games, finds no change and never calls the lineup endpoint again
    before = [c for c in p.http.paths() if c.startswith("lineups/")]
    assert ingest.job_corrections(p, days=5).updated == 0
    assert [c for c in p.http.paths() if c.startswith("lineups/")] == before


def test_player_with_unknown_position_keeps_his_stats_but_is_not_draftable(world):
    p = hl_provider(extra_unknown=True)
    ingest.job_teams_players(p)
    ingest.job_schedule(p, season=2026)
    assert ingest.job_stats(p).status == "success"
    mystery = db.session.scalar(db.select(Athlete).where(Athlete.provider_id == 150, Athlete.provider == "highlightly"))
    assert mystery is not None and mystery.positions == ""
    assert db.session.scalar(db.select(db.func.count(GameStat.id)).where(GameStat.athlete_id == mystery.id)) == 1
    from fantaball.pool import pool_filter
    pool = db.session.scalars(db.select(Athlete.id).where(*pool_filter(mystery.sport_id), Athlete.provider == "highlightly")).all()
    assert mystery.id not in pool and len(pool) == 8


def test_daily_job_uses_the_small_window_and_a_full_refresh_on_mondays(world, monkeypatch):
    p = hl_provider()
    ingest.job_teams_players(p)
    ingest.job_schedule(p, season=2026)
    ingest.job_stats(p)
    for today, expect_full in ((date(2026, 10, 27), False), (date(2026, 11, 2), True)):         # a Tuesday, then a Monday
        monkeypatch.setenv("FLASK_FAKE_TODAY", today.isoformat())
        p.http.calls.clear()
        ingest.job_daily(p)
        match_calls = [q for path, q in p.http.calls if path == "matches"]
        if expect_full:
            assert match_calls and "season" in match_calls[0]
        else:
            back, ahead = p.daily_window
            assert len(match_calls) == back + ahead + 1 and all("date" in q for q in match_calls)       # one request per day in the window


def test_budget_exhaustion_is_reported_without_corrupting_data(world):
    p = hl_provider()
    p.http.max_requests = None
    ingest.job_teams_players(p)
    ingest.job_schedule(p, season=2026)
    real_get = p.http.get_json
    calls = {"n": 0}

    def limited(path, params=None):
        if path.startswith("box-score/"):
            calls["n"] += 1
            if calls["n"] > 1:
                raise ProviderRateLimited("Today's request budget for this plan is used up.")
        return real_get(path, params)
    p.http.get_json = limited
    run = ingest.job_stats(p)
    assert run.status in ("partial", "failed") and "budget" in run.error
    done = db.session.scalars(db.select(ProGame).where(ProGame.stats_synced_at.is_not(None))).all()
    assert len(done) in (0, 2)                                       # whole batches only (both games are one batch of 6)
    p.http.get_json = real_get
    assert ingest.job_stats(p).status == "success"
    assert db.session.scalar(db.select(db.func.count(GameStat.id)).where(GameStat.source == "highlightly")) == 8


def test_partial_import_still_scores_what_was_committed(world):
    """The real first import hit the daily quota half-way: everything committed before that must be scored anyway."""
    p = hl_provider()
    p.stats_chunk = 1                                                # one game per commit batch
    ingest.job_teams_players(p)
    ingest.job_schedule(p, season=2026)
    real_get, calls = p.http.get_json, {"n": 0}

    def limited(path, params=None):
        if path.startswith("box-score/"):
            calls["n"] += 1
            if calls["n"] > 1:
                raise ProviderRateLimited("The provider's daily request quota is used up.")
        return real_get(path, params)
    p.http.get_json = limited
    run = ingest.job_stats(p)
    assert run.status in ("partial", "failed") and "quota" in run.error
    assert db.session.scalar(db.select(db.func.count(GameStat.id)).where(GameStat.source == "highlightly")) == 4          # game 1 only
    assert db.session.scalar(db.select(db.func.count(PlayerFantasyScore.id)).join(Athlete, Athlete.id == PlayerFantasyScore.athlete_id).where(Athlete.provider == "highlightly")) == 4
    p.http.get_json = real_get
    assert ingest.job_stats(p).status == "success"                    # tomorrow: the rest arrives, nothing is duplicated
    assert db.session.scalar(db.select(db.func.count(GameStat.id)).where(GameStat.source == "highlightly")) == 8


def test_a_known_position_is_not_flipped_by_a_later_lineup(world):
    """Lineups show the slot a player STARTED in (G one night, F the next): the first known position is kept, with no churn."""
    routes, boxes, lineups = league_routes()
    p = HighlightlyProvider(None, client=RoutedHttp(routes, boxes, lineups), today=lambda: TODAY)
    p._season_offset = 0
    ingest.job_teams_players(p)
    ingest.job_schedule(p, season=2026)
    ingest.job_stats(p)
    player = db.session.scalar(db.select(Athlete).where(Athlete.provider_id == 100, Athlete.provider == "highlightly"))
    assert player.positions == "PG"
    lineups[10]["home"]["lineup"][0]["positionAbbreviation"] = "F"          # the same player listed as a forward in a later re-import
    ingest.job_stats(p, dates=[date(2026, 10, 26)])
    db.session.refresh(player)
    assert player.positions == "PG"
