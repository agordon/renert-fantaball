"""Sport registry: everything that differs between NBA / NHL / NFL lives here.

The rest of the app (scoring, roster rules, draft, trades) only reads these
definitions, so adding a sport = adding one entry to SPORTS (+ a data provider).
"""

SPORTS = {
    "nba": {
        "name": "NBA Basketball",
        "positions": ["PG", "SG", "SF", "PF", "C"],
        # Per-game stat keys and display labels
        "stats": {
            "min": "MIN", "pts": "PTS", "reb": "REB", "ast": "AST",
            "stl": "STL", "blk": "BLK", "tov": "TO", "fg3m": "3PM",
        },
        "default_scoring": {"pts": 1.0, "reb": 1.2, "ast": 1.5, "stl": 3.0, "blk": 3.0, "tov": -1.0, "fg3m": 0.5},
        # (slot, count) in display order. BN = bench, IR = injured reserve
        "roster": [("PG", 1), ("SG", 1), ("SF", 1), ("PF", 1), ("C", 1), ("G", 1), ("F", 1), ("UTIL", 2), ("BN", 4), ("IR", 1)],
        # Which player positions may fill each slot (UTIL/BN accept anyone, IR is injury-gated)
        "slot_positions": {
            "PG": ["PG"], "SG": ["SG"], "SF": ["SF"], "PF": ["PF"], "C": ["C"],
            "G": ["PG", "SG"], "F": ["SF", "PF"],
        },
        "season_days": 77,        # 11 weeks of 7 days
        "days_per_week": 7,
    },
    "nhl": {
        "name": "NHL Hockey",
        "positions": ["C", "LW", "RW", "D", "G"],
        "stats": {"g": "G", "a": "A", "sog": "SOG", "hit": "HIT", "blk": "BLK", "sv": "SV", "ga": "GA", "w": "W"},
        "default_scoring": {"g": 6.0, "a": 4.0, "sog": 0.9, "hit": 0.5, "blk": 1.0, "sv": 0.2, "ga": -3.0, "w": 5.0},
        "roster": [("C", 2), ("LW", 2), ("RW", 2), ("D", 4), ("G", 2), ("BN", 3), ("IR", 1)],
        "slot_positions": {"C": ["C"], "LW": ["LW"], "RW": ["RW"], "D": ["D"], "G": ["G"]},
        "season_days": 77,
        "days_per_week": 7,
    },
}

# "nba" is the REAL-data sport (filled by the data pipeline); "nba_demo" is the same game with SIMULATED fictional data.
# Both share one rule definition. Season length differs: the real NBA regular season is ~24 weeks.
SPORTS["nba_demo"] = {**SPORTS["nba"], "name": "NBA Basketball (simulated demo)"}
SPORTS["nba"] = {**SPORTS["nba"], "season_days": 168}      # 24 weeks of 7 days

PLAYABLE_SPORTS = ["nba", "nba_demo"]   # leagues can only be created for these (NHL is a demo dataset for now)


def family(code: str) -> str:
    """'nba_demo' -> 'nba' (the underlying game, independent of where its data comes from)."""
    return code.split("_")[0]


def get_sport(code: str) -> dict:
    if code not in SPORTS:
        raise ValueError(f"Unknown sport '{code}'")
    return SPORTS[code]


def roster_slots(sport_code: str, roster_config: list | None = None) -> list[str]:
    """Flat ordered list of slot names, e.g. ['PG','SG',...,'UTIL','UTIL','BN',...,'IR']."""
    cfg = roster_config or SPORTS[sport_code]["roster"]
    out = []
    for slot, count in cfg:
        out.extend([slot] * int(count))
    return out
