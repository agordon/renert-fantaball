"""Sport registry: everything that differs between sports (NBA now, NHL / NFL later) lives here.

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
}

# The real NBA regular season is ~24 weeks. (Other sports: add an entry above + a data provider, see README.)
SPORTS["nba"] = {**SPORTS["nba"], "season_days": 168}      # 24 weeks of 7 days

PLAYABLE_SPORTS = ["nba"]


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
