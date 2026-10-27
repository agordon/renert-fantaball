import pytest

from fantaball.roster import RosterError, eligible, optimal_lineup, validate_lineup
from fantaball.sports import SPORTS

CFG = SPORTS["nba"]["roster"]


def test_slot_eligibility():
    assert eligible("nba", "PG", ["PG", "SG"])
    assert not eligible("nba", "C", ["PG"])
    assert eligible("nba", "G", ["SG"])
    assert not eligible("nba", "G", ["SF"])
    assert eligible("nba", "F", ["PF"])
    assert eligible("nba", "UTIL", ["C"])
    assert eligible("nba", "BN", ["C"])


def test_ir_only_for_injured():
    assert not eligible("nba", "IR", ["PG"], "HEALTHY")
    assert eligible("nba", "IR", ["PG"], "OUT")


def p(i, pos, value, status="HEALTHY"):
    return dict(id=i, positions=pos.split(","), value=value, status=status)


def test_optimal_lineup_fills_specific_slots_and_never_starts_injured():
    players = [p(1, "PG", 50), p(2, "SG", 45), p(3, "SF", 40), p(4, "PF", 38), p(5, "C", 36), p(6, "PG", 30), p(7, "C", 29),
               p(8, "SF,PF", 28), p(9, "SG", 27), p(10, "C", 20), p(11, "PG", 60, "OUT"), p(12, "SG", 10), p(13, "PF", 9)]
    a = optimal_lineup("nba", CFG, players)
    assert a[11] == "IR"                       # best player is injured -> IR, not a starter
    assert all(s not in ("BN", "IR") for s in (a[1], a[2], a[3], a[4], a[5]))
    starters = [i for i, s in a.items() if s not in ("BN", "IR")]
    assert len(starters) == 9
    assert set(a) == {x["id"] for x in players}


class FakeAthlete:
    def __init__(self, name, positions, status="HEALTHY"):
        self.name, self.positions, self._s = name, positions, status
        self.position_list = positions.split(",")

    def injury_status(self, day):
        return self._s


def test_validate_lineup_rejects_wrong_position_injured_starter_and_overfull_slot():
    ath = {1: FakeAthlete("A", "PG"), 2: FakeAthlete("B", "C"), 3: FakeAthlete("Hurt", "SG", "OUT"), 4: FakeAthlete("Healthy", "SG")}
    validate_lineup("nba", CFG, {1: "PG", 2: "C", 3: "IR", 4: "SG"}, ath, 1)
    with pytest.raises(RosterError):
        validate_lineup("nba", CFG, {1: "C"}, ath, 1)                   # PG cannot play C
    with pytest.raises(RosterError):
        validate_lineup("nba", CFG, {3: "SG"}, ath, 1)                  # injured cannot start
    with pytest.raises(RosterError):
        validate_lineup("nba", CFG, {4: "IR"}, ath, 1)                  # healthy cannot take IR
    with pytest.raises(RosterError):
        validate_lineup("nba", CFG, {1: "PG", 4: "PG"}, ath, 1)         # only one PG slot... 4 is SG-only
    with pytest.raises(RosterError):
        validate_lineup("nba", CFG, {1: "XX"}, ath, 1)                  # unknown slot


def test_bench_may_grow_into_a_starting_slot_nobody_can_fill():
    """No eligible center on the roster: the C slot stays empty, so one extra player may sit on the bench."""
    ath = {i: FakeAthlete(f"P{i}", pos) for i, pos in enumerate(["PG", "SG", "SF", "PF", "SG", "SF"], start=1)}
    cfg = [["PG", 1], ["SG", 1], ["SF", 1], ["PF", 1], ["C", 1], ["BN", 1]]
    ok = {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "BN", 6: "BN"}                  # 2 on the bench, 1 bench slot + 1 empty C slot
    validate_lineup("nba", cfg, ok, ath, 1)
    with pytest.raises(RosterError):
        validate_lineup("nba", cfg, {1: "BN", 2: "BN", 3: "BN", 4: "BN", 5: "BN", 6: "PG"}, ath, 1)   # far too many on the bench
