"""Configurable scoring engine.

A league stores a dict of {stat_key: points_per_unit}. Scoring a stat line is a
plain weighted sum, so any sport (NBA, NHL, ...) works with the same code.
"""
from fantaball.sports import get_sport


def score_stat_line(stats: dict, rules: dict) -> float:
    """Fantasy points for one stat line. Unknown / missing stats count as 0."""
    total = 0.0
    for key, weight in rules.items():
        total += float(stats.get(key, 0) or 0) * float(weight)
    return round(total, 2)


def validate_rules(sport_code: str, rules: dict) -> dict:
    """Return a cleaned copy of `rules`, or raise ValueError if a key/value is invalid."""
    valid_keys = set(get_sport(sport_code)["stats"])
    if not isinstance(rules, dict) or not rules:
        raise ValueError("Scoring rules must be a non-empty object")
    cleaned = {}
    for key, val in rules.items():
        if key not in valid_keys:
            raise ValueError(f"Unknown stat '{key}' for {sport_code}")
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError(f"Scoring value for '{key}' must be a number")
        if not -20 <= val <= 20:
            raise ValueError(f"Scoring value for '{key}' must be between -20 and 20")
        cleaned[key] = float(val)
    return cleaned


def default_rules(sport_code: str) -> dict:
    return dict(get_sport(sport_code)["default_scoring"])
