"""Configurable scoring engine.

A league stores a dict of {stat_key: points_per_unit}. Scoring a stat line is a plain weighted sum, so any sport
(NBA today, other sports later) works with the same code.

score_decimal() is STRICT and exact (Decimal): if a stat that has a non-zero weight was not reported (None / absent)
the result is None ("cannot be scored"), never a silent 0.
"""
import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal

from fantaball.sports import get_sport

CENT = Decimal("0.01")


def score_decimal(stats: dict, rules: dict) -> Decimal | None:
    """Exact fantasy points for one stat line, rounded half-up to 2 decimals; None if a needed stat is missing.

    fantasy = sum(stat * weight) over every rule; weights may be negative (turnovers) or fractional (0.5 per 3PM).
    """
    total = Decimal(0)
    for key, weight in rules.items():
        w = Decimal(str(weight))
        if w == 0:
            continue
        value = stats.get(key)
        if value is None:
            return None
        total += Decimal(str(value)) * w
    return total.quantize(CENT, rounding=ROUND_HALF_UP)


def score_float(stats: dict, rules: dict) -> float | None:
    """score_decimal as a float (for displays and averages); None when the line cannot be scored."""
    pts = score_decimal(stats, rules)
    return float(pts) if pts is not None else None


def rules_hash(rules: dict) -> str:
    """Stable fingerprint of a rule set: identical weights => identical hash (so leagues can share one stored rule set)."""
    canon = json.dumps({k: round(float(v), 4) for k, v in sorted(rules.items())}, sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()[:32]


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
