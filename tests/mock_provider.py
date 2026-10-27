"""Fixture NBA provider for AUTOMATED TESTS ONLY (not part of the running application).

Everything it returns is invented so tests need no network and no paid plan. The application never uses it: tests
install it with app.config["NBA_PROVIDER_FACTORY"]. Rows imported through it are labelled `source="mock"`.

Test hooks (set as attributes): `revision` (2 = emit corrected values for a few rows), `stats_blocked`,
`fail_after_requests` (raise ProviderUnavailable once N calls have been made).
"""
import random
from datetime import date, datetime, timedelta
from typing import Iterable, Iterator

from fantaball.nba.provider import (GameRecord, NBADataProvider, PlayerRecord, ProviderAuthError, ProviderUnavailable, StatRecord, TeamRecord)

TEAMS = [(101, "AAA", "Alpha City", "Aces"), (102, "BBB", "Bravo Bay", "Bears"), (103, "CCC", "Charlie Creek", "Comets"),
         (104, "DDD", "Delta Dunes", "Dragons"), (105, "EEE", "Echo Eden", "Eagles"), (106, "FFF", "Foxtrot Falls", "Foxes")]
POSITIONS = ["PG", "SG", "SF", "PF", "C", "G", "F", "G-F"]      # raw provider-style values (BDL uses G, F, C, G-F, F-C ...)
SEASON_START = date(2026, 10, 19)                                 # a Monday


class MockNBAProvider(NBADataProvider):
    name = "mock"
    is_mock = True

    def __init__(self, today: date = date(2026, 10, 27), days: int = 14, seed: int = 7):
        self.today = today
        self.days = days
        self.seed = seed
        self.revision = 1
        self.stats_blocked = False
        self.fail_after_requests: int | None = None
        self._calls = 0
        self._players = self._build_players()
        self._games = self._build_games()

    # --- fixtures -----------------------------------------------------------
    def _build_players(self) -> list[PlayerRecord]:
        rng = random.Random(self.seed)
        out, pid = [], 1000
        for tid, _a, _c, _n in TEAMS:
            for i in range(8):
                pid += 1
                out.append(PlayerRecord(provider_id=pid, first_name=f"First{pid}", last_name=f"Last{pid}", position=POSITIONS[(pid + i) % len(POSITIONS)],
                                        height="6-7", weight="210", team_provider_id=tid, meta={"jersey_number": str(rng.randint(0, 99))}))
        # edge cases the importer must handle safely
        out.append(PlayerRecord(provider_id=2001, first_name="No", last_name="Position", position=None, team_provider_id=101))
        out.append(PlayerRecord(provider_id=2002, first_name="No", last_name="Team", position="C", team_provider_id=None))
        return out

    def _build_games(self) -> list[GameRecord]:
        games, gid = [], 5000
        ids = [t[0] for t in TEAMS]
        for d in range(self.days):
            day = SEASON_START + timedelta(days=d)
            order = ids[d % len(ids):] + ids[:d % len(ids)]
            for k in range(0, 6, 2):
                gid += 1
                final = day < self.today
                rng = random.Random(f"{self.seed}-{gid}")
                games.append(GameRecord(
                    provider_id=gid, season=2026, postseason=False, game_date=day, starts_at=datetime(day.year, day.month, day.day, 23, 30),
                    status="final" if final else "scheduled", home_team_id=order[k], away_team_id=order[k + 1],
                    home_score=rng.randint(95, 125) if final else None, away_score=rng.randint(95, 125) if final else None))
        return games

    def _tick(self):
        self._calls += 1
        if self.fail_after_requests is not None and self._calls > self.fail_after_requests:
            raise ProviderUnavailable("MOCK: injected provider outage")

    # --- interface ----------------------------------------------------------
    @property
    def requests_made(self) -> int:
        return self._calls

    def teams(self) -> list[TeamRecord]:
        self._tick()
        return [TeamRecord(provider_id=i, abbr=a, city=c, name=n, conference="East" if i < 104 else "West", division="Mock") for i, a, c, n in TEAMS]

    def players(self, team_ids: Iterable[int]) -> Iterator[PlayerRecord]:
        for tid in team_ids:
            self._tick()
            yield from (p for p in self._players if p.team_provider_id == tid)

    def games(self, *, season=None, start_date=None, end_date=None) -> Iterator[GameRecord]:
        self._tick()
        for g in self._games:
            if (start_date and g.game_date < start_date) or (end_date and g.game_date > end_date):
                continue
            yield g

    def stats(self, *, dates=None, game_ids=None) -> Iterator[StatRecord]:
        self._tick()
        if self.stats_blocked:
            raise ProviderAuthError("MOCK: plan does not include game player stats (HTTP 401)")
        wanted = [g for g in self._games if g.status == "final" and ((dates and g.game_date in dates) or (game_ids and g.provider_id in game_ids))]
        for g in wanted:
            for team in (g.home_team_id, g.away_team_id):
                for p in self._players:
                    if p.team_provider_id != team or p.position is None or p.provider_id >= 2000:
                        continue
                    yield self._line(p, g)

    def _line(self, p: PlayerRecord, g: GameRecord) -> StatRecord:
        rng = random.Random(f"{self.seed}-{p.provider_id}-{g.provider_id}")
        pts, reb, ast = rng.randint(2, 35), rng.randint(0, 14), rng.randint(0, 11)
        stl, blk, tov, fg3m = rng.randint(0, 4), rng.randint(0, 4), rng.randint(0, 6), rng.randint(0, 6)
        blk_value: int | None = blk
        if p.provider_id % 17 == 0 and g.provider_id % 2 == 0:
            blk_value = None            # a stat the provider did not report
        base = pts                       # derived numbers (shooting lines) never depend on the correction
        if self.revision >= 2 and p.provider_id % 5 == 0 and g.provider_id % 3 == 0:
            pts += 3                     # official stat correction: only the points figure changes
        return StatRecord(provider_stat_id=p.provider_id * 100000 + g.provider_id, player_provider_id=p.provider_id, game_provider_id=g.provider_id,
                          team_provider_id=p.team_provider_id, minutes=round(rng.uniform(8, 38), 1), pts=pts, reb=reb, oreb=reb // 3,
                          dreb=reb - reb // 3, ast=ast, stl=stl, blk=blk_value, tov=tov, fgm=base // 3, fga=base // 3 + 6, fg3m=min(fg3m, base // 3),
                          fg3a=fg3m + 3, ftm=base // 5, fta=base // 5 + 1, pf=rng.randint(0, 5), plus_minus=rng.randint(-15, 15), player=p)
