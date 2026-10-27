"""Data-provider abstraction.

The app only talks to a `DataProvider`. The bundled `DemoProvider` generates a
deterministic, clearly SIMULATED world (fictional athletes, invented schedules and
stat lines) so no real player data / photos / paid feeds are involved.

To plug in a real feed later: subclass DataProvider, return the same plain dicts,
and pass it to fantaball.seed.load_world(). Only use sources whose terms allow it.
"""
import math
import random

from fantaball.sports import SPORTS, family


class DataProvider:
    """Interface. All methods return plain dicts/lists so the DB layer stays provider-agnostic."""
    sport_code: str

    def pro_teams(self) -> list[dict]:           # [{abbr, city, name}]
        raise NotImplementedError

    def athletes(self) -> list[dict]:            # [{name, team, positions, age, rank, injury_start, injury_end, injury_note, ratings}]
        raise NotImplementedError

    def schedule(self) -> list[dict]:            # [{day, home, away}]
        raise NotImplementedError

    def game_stats(self, athletes, schedule) -> list[dict]:   # [{athlete_index, game_index, day, stats}]
        raise NotImplementedError


NBA_TEAMS = [
    ("ATL", "Atlanta", "Hawks"), ("BOS", "Boston", "Celtics"), ("BKN", "Brooklyn", "Nets"),
    ("CHA", "Charlotte", "Hornets"), ("CHI", "Chicago", "Bulls"), ("CLE", "Cleveland", "Cavaliers"),
    ("DAL", "Dallas", "Mavericks"), ("DEN", "Denver", "Nuggets"), ("DET", "Detroit", "Pistons"),
    ("GSW", "Golden State", "Warriors"), ("HOU", "Houston", "Rockets"), ("IND", "Indiana", "Pacers"),
    ("LAC", "Los Angeles", "Clippers"), ("LAL", "Los Angeles", "Lakers"), ("MEM", "Memphis", "Grizzlies"),
    ("MIA", "Miami", "Heat"), ("MIL", "Milwaukee", "Bucks"), ("MIN", "Minnesota", "Timberwolves"),
    ("NOP", "New Orleans", "Pelicans"), ("NYK", "New York", "Knicks"), ("OKC", "Oklahoma City", "Thunder"),
    ("ORL", "Orlando", "Magic"), ("PHI", "Philadelphia", "76ers"), ("PHX", "Phoenix", "Suns"),
    ("POR", "Portland", "Trail Blazers"), ("SAC", "Sacramento", "Kings"), ("SAS", "San Antonio", "Spurs"),
    ("TOR", "Toronto", "Raptors"), ("UTA", "Utah", "Jazz"), ("WAS", "Washington", "Wizards"),
]

NHL_TEAMS = [
    ("ANA", "Anaheim", "Ducks"), ("BOS", "Boston", "Bruins"), ("BUF", "Buffalo", "Sabres"),
    ("CGY", "Calgary", "Flames"), ("CAR", "Carolina", "Hurricanes"), ("CHI", "Chicago", "Blackhawks"),
    ("COL", "Colorado", "Avalanche"), ("CBJ", "Columbus", "Blue Jackets"), ("DAL", "Dallas", "Stars"),
    ("DET", "Detroit", "Red Wings"), ("EDM", "Edmonton", "Oilers"), ("FLA", "Florida", "Panthers"),
    ("LAK", "Los Angeles", "Kings"), ("MIN", "Minnesota", "Wild"), ("MTL", "Montreal", "Canadiens"),
    ("NSH", "Nashville", "Predators"), ("NJD", "New Jersey", "Devils"), ("NYI", "New York", "Islanders"),
    ("NYR", "New York", "Rangers"), ("OTT", "Ottawa", "Senators"), ("PHI", "Philadelphia", "Flyers"),
    ("PIT", "Pittsburgh", "Penguins"), ("SJS", "San Jose", "Sharks"), ("SEA", "Seattle", "Kraken"),
    ("STL", "St. Louis", "Blues"), ("TBL", "Tampa Bay", "Lightning"), ("TOR", "Toronto", "Maple Leafs"),
    ("UTA", "Utah", "Mammoth"), ("VAN", "Vancouver", "Canucks"), ("VGK", "Vegas", "Golden Knights"),
    ("WSH", "Washington", "Capitals"), ("WPG", "Winnipeg", "Jets"),
]

FIRST = ("Aaron Adrian Alec Andre Anton Ari Beau Blake Caleb Cam Carter Cole Dante Darius Devin Dominic Eli Elijah "
         "Emmett Felix Gabe Grant Hayes Isaiah Jabari Jalen Jamal Jonah Jordan Kai Kellen Khalil Landon Leo Malik "
         "Marcus Mateo Micah Miles Nico Noah Omar Owen Quinn Rafael Reese Rhys Roman Rowan Sam Silas Soren Tariq "
         "Theo Tobias Tyrese Victor Wes Xavier Zane Zion").split()
LAST = ("Abbott Alvarez Archer Baptiste Barlow Beckett Bishop Bryant Calloway Castillo Chambers Cruz Dalton Delgado "
        "Donovan Ellison Fairfax Farrow Gaines Garrity Gentry Hale Hargrove Holloway Hutchins Ibarra Jennings Keller "
        "Kingsley Lawson Leclerc Mackey Maddox Navarro Okafor Osei Pruitt Quarles Ramsey Reyes Rutledge Sandoval "
        "Sinclair Stanton Strickland Sutherland Talbot Thorne Tillman Underwood Vance Whitaker Winslow Yates Zimmer").split()

INJURIES = ["Ankle sprain", "Knee soreness", "Hamstring strain", "Illness", "Back spasms", "Wrist sprain", "Groin strain", "Concussion protocol"]

# Per-game stat profile of a star-level player (u = 1.0) by position
NBA_PROFILE = {
    "PG": dict(pts=26, reb=5.0, ast=9.0, stl=1.7, blk=0.4, tov=3.5, fg3m=3.0),
    "SG": dict(pts=27, reb=5.5, ast=5.5, stl=1.5, blk=0.5, tov=3.0, fg3m=3.2),
    "SF": dict(pts=26, reb=8.0, ast=5.0, stl=1.3, blk=0.8, tov=3.0, fg3m=2.2),
    "PF": dict(pts=24, reb=10.0, ast=4.0, stl=1.1, blk=1.2, tov=2.8, fg3m=1.5),
    "C": dict(pts=22, reb=12.5, ast=3.5, stl=0.9, blk=2.3, tov=2.8, fg3m=0.6),
}
ADJACENT = {"PG": "SG", "SG": "SF", "SF": "PF", "PF": "C", "C": "PF"}


def _poisson(rng, lam):
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _clip_int(x, lo=0):
    return max(lo, int(round(x)))


class DemoProvider(DataProvider):
    """Deterministic simulated world. Same seed => identical athletes, schedule and stat lines."""

    def __init__(self, sport_code: str, seed: int = 2026):
        self.sport_code = sport_code
        self.seed = seed
        self.cfg = SPORTS[sport_code]
        self.family = family(sport_code)
        self._teams = NBA_TEAMS if self.family == "nba" else NHL_TEAMS

    def _rng(self, label):
        return random.Random(f"{self.sport_code}-{self.seed}-{label}")

    def pro_teams(self):
        return [dict(abbr=a, city=c, name=n) for a, c, n in self._teams]

    # ---------- athletes ----------
    def athletes(self):
        rng = self._rng("athletes")
        n_teams = len(self._teams)
        if self.family == "nba":
            per_team_positions = ["PG", "PG", "SG", "SG", "SF", "SF", "PF", "PF", "C", "C"]
        else:
            per_team_positions = ["C", "C", "LW", "LW", "RW", "RW", "D", "D", "G"]
        total = n_teams * len(per_team_positions)

        used = set()

        def make_name():
            while True:
                nm = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                if nm not in used:
                    used.add(nm)
                    return nm

        # Talent level u by rank: a few stars, a long tail of role players
        levels = [0.12 + 0.88 * (1 - i / total) ** 1.9 for i in range(total)]
        positions_pool = per_team_positions * n_teams
        rng.shuffle(positions_pool)

        athletes = []
        for i in range(total):
            primary = positions_pool[i]
            positions = [primary]
            if self.family == "nba" and rng.random() < 0.35:
                positions.append(ADJACENT[primary])
            athletes.append(dict(
                name=make_name(), positions=",".join(positions), age=rng.randint(20, 37),
                rank=i + 1, level=levels[i], injury_start=None, injury_end=None, injury_note=None,
            ))

        # Assign to pro teams with a balanced snake by rank, respecting per-team position counts
        slots_left = {t: list(per_team_positions) for t in range(n_teams)}
        order = list(range(n_teams))
        rng.shuffle(order)
        t_idx = 0
        direction = 1
        for a in athletes:
            primary = a["positions"].split(",")[0]
            placed = False
            for _ in range(n_teams):
                team = order[t_idx]
                if primary in slots_left[team]:
                    slots_left[team].remove(primary)
                    a["team"] = self._teams[team][0]
                    placed = True
                t_idx += direction
                if t_idx in (-1, n_teams):
                    direction *= -1
                    t_idx += direction
                if placed:
                    break
            if not placed:   # fallback: any team with a free slot of that position
                for team in range(n_teams):
                    if primary in slots_left[team]:
                        slots_left[team].remove(primary)
                        a["team"] = self._teams[team][0]
                        break

        # ~8% injured at some point in the season
        for a in athletes:
            if rng.random() < 0.08:
                start = rng.randint(4, 62)
                a["injury_start"], a["injury_end"] = start, start + rng.randint(2, 21)
                a["injury_note"] = rng.choice(INJURIES)
        return athletes

    # ---------- schedule ----------
    def schedule(self):
        rng = self._rng("schedule")
        n = len(self._teams)
        abbrs = [t[0] for t in self._teams]
        days = self.cfg["season_days"]
        dpw = self.cfg["days_per_week"]
        games, week_counts = [], {}
        for day in range(1, days + 1):
            if (day - 1) % dpw == 0:
                week_counts = {a: 0 for a in abbrs}
            pool = sorted(abbrs, key=lambda a: (week_counts[a], rng.random()))
            playing = pool[: (n * 2 // 3) // 2 * 2]      # about two thirds of teams play each day
            rng.shuffle(playing)
            for k in range(0, len(playing), 2):
                home, away = playing[k], playing[k + 1]
                week_counts[home] += 1
                week_counts[away] += 1
                games.append(dict(day=day, home=home, away=away))
        return games

    # ---------- stat lines ----------
    def game_stats(self, athletes, schedule):
        rng = self._rng("stats")
        team_games = {}
        for gi, g in enumerate(schedule):
            team_games.setdefault(g["home"], []).append((gi, g["day"], g["away"]))
            team_games.setdefault(g["away"], []).append((gi, g["day"], g["home"]))

        rows = []
        for ai, a in enumerate(athletes):
            if self.family == "nba":
                means = self._nba_means(a, rng)
            else:
                means = self._nhl_means(a, rng)
            is_goalie = a["positions"] == "G"
            for gi, day, _opp in team_games.get(a["team"], []):
                if a["injury_start"] is not None and a["injury_start"] <= day < a["injury_end"]:
                    continue
                if is_goalie and rng.random() > 0.62:
                    continue
                stats = self._nba_line(means, a, rng) if self.family == "nba" else self._nhl_line(means, a, rng)
                rows.append(dict(athlete_index=ai, game_index=gi, day=day, stats=stats))
        return rows

    # NBA ------------------------------------------------------------------
    def _nba_means(self, a, rng):
        u = a["level"]
        profs = [NBA_PROFILE[p] for p in a["positions"].split(",")]
        means = {k: sum(p[k] for p in profs) / len(profs) for k in profs[0]}
        scale = {"pts": u, "reb": u ** 0.9, "ast": u ** 0.95, "stl": u ** 0.7, "blk": u ** 0.8, "tov": u ** 0.7, "fg3m": u ** 0.9}
        out = {k: max(0.05, means[k] * scale[k] * rng.uniform(0.82, 1.18)) for k in means}
        out["min"] = 12 + 26 * u
        return out

    def _nba_line(self, m, a, rng):
        form = rng.uniform(0.7, 1.3)          # hot / cold night
        pts = _clip_int(rng.gauss(m["pts"] * form, 0.28 * m["pts"] + 2.0))
        return dict(
            min=_clip_int(rng.gauss(m["min"], 3.5), 4),
            pts=pts,
            reb=_clip_int(rng.gauss(m["reb"], 0.4 * m["reb"] + 1.0)),
            ast=_clip_int(rng.gauss(m["ast"], 0.4 * m["ast"] + 0.8)),
            stl=_poisson(rng, m["stl"]),
            blk=_poisson(rng, m["blk"]),
            tov=_poisson(rng, m["tov"]),
            fg3m=min(_poisson(rng, m["fg3m"] * form), max(pts // 3, 0)),
        )

    # NHL ------------------------------------------------------------------
    def _nhl_means(self, a, rng):
        u = a["level"]
        pos = a["positions"]
        if pos == "G":
            return dict(sv=22 + 8 * u, ga=3.4 - 1.3 * u, w=0.35 + 0.35 * u)
        d = 1.0 if pos != "D" else 0.6
        return dict(
            g=(0.08 + 0.42 * u) * d, a=(0.12 + 0.55 * u) * (1.2 if pos == "D" else 1),
            sog=(1.2 + 2.4 * u) * (0.7 if pos == "D" else 1),
            hit=(0.6 + 1.6 * u) * (1.5 if pos == "D" else 1), blk=(0.3 + 1.0 * u) * (2.0 if pos == "D" else 1),
        )

    def _nhl_line(self, m, a, rng):
        if a["positions"] == "G":
            sv = _clip_int(rng.gauss(m["sv"], 5))
            ga = _poisson(rng, m["ga"])
            return dict(sv=sv, ga=ga, w=1 if rng.random() < m["w"] else 0)
        return dict(g=_poisson(rng, m["g"]), a=_poisson(rng, m["a"]), sog=_poisson(rng, m["sog"]),
                    hit=_poisson(rng, m["hit"]), blk=_poisson(rng, m["blk"]))
