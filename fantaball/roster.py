"""Roster rules: slot eligibility, lineup validation and the auto-lineup (optimizer).

Pure functions work on plain data so they are easy to unit-test; the DB helpers at the
bottom apply the results to RosterSlot rows.
"""
from fantaball.sports import SPORTS, roster_slots


class RosterError(ValueError):
    """A roster / lineup rule was broken (shown to the user as a 400)."""


def eligible(sport_code: str, slot: str, positions: list[str], injury_status: str = "HEALTHY") -> bool:
    """Can an athlete with `positions` and `injury_status` occupy `slot`?"""
    if slot == "BN":
        return True
    if slot == "IR":
        return injury_status in ("OUT", "DTD")           # IR is only for injured athletes
    if slot == "UTIL":
        return True
    allowed = SPORTS[sport_code]["slot_positions"].get(slot, [])
    return any(p in allowed for p in positions)


def slot_order_for_assignment(sport_code: str, roster_config) -> list[str]:
    """Starting slots from most restrictive to least (so flexible slots are filled last)."""
    slots = [s for s in roster_slots(sport_code, roster_config) if s not in ("BN", "IR")]
    sp = SPORTS[sport_code]["slot_positions"]

    def flexibility(s):
        return len(sp.get(s, [])) if s != "UTIL" else 99

    return sorted(slots, key=flexibility)


def optimal_lineup(sport_code, roster_config, players: list[dict]) -> dict:
    """Greedy lineup optimizer.

    players: [{id, positions: [..], value: float (projected points), status: str}]
    Returns {athlete_id: slot}. Algorithm: best-to-worst by value, each player takes the most
    restrictive open starting slot he is eligible for; leftovers go to IR (if injured and room) or bench.
    Injured players are never started.
    """
    slots_open = slot_order_for_assignment(sport_code, roster_config)
    ir_cap = sum(c for s, c in (roster_config or SPORTS[sport_code]["roster"]) if s == "IR")
    assignment = {}
    healthy = [p for p in players if p["status"] == "HEALTHY"]
    for p in sorted(healthy, key=lambda p: -p["value"]):
        for s in slots_open:
            if eligible(sport_code, s, p["positions"], p["status"]):
                assignment[p["id"]] = s
                slots_open.remove(s)
                break
    ir_used = 0
    # Injured first (to IR where room), then the rest to the bench
    rest = [p for p in players if p["id"] not in assignment]
    rest.sort(key=lambda p: (p["status"] == "HEALTHY", -p["value"]))
    for p in rest:
        if p["status"] != "HEALTHY" and ir_used < ir_cap:
            assignment[p["id"]] = "IR"
            ir_used += 1
        else:
            assignment[p["id"]] = "BN"
    return assignment


def validate_lineup(sport_code, roster_config, assignment: dict, athletes: dict, day: int):
    """Raise RosterError unless `assignment` ({athlete_id: slot}) is a legal lineup.

    athletes: {athlete_id: Athlete}. Checks slot names, capacities and position / injury eligibility.
    """
    capacity = {}
    for slot, count in roster_config:
        capacity[slot] = capacity.get(slot, 0) + int(count)
    used = {}
    for aid, slot in assignment.items():
        if slot not in capacity:
            raise RosterError(f"'{slot}' is not a slot in this league")
        used[slot] = used.get(slot, 0) + 1
        if used[slot] > capacity[slot]:
            raise RosterError(f"Too many players in slot {slot} (max {capacity[slot]})")
        a = athletes[aid]
        status = a.injury_status(day)
        if not eligible(sport_code, slot, a.position_list, status):
            if slot == "IR":
                raise RosterError(f"{a.name} is healthy and cannot be placed on injured reserve")
            raise RosterError(f"{a.name} ({a.positions}) is not eligible for {slot}")
        if slot not in ("BN", "IR") and status != "HEALTHY":
            raise RosterError(f"{a.name} is injured ({status}) and cannot start")
