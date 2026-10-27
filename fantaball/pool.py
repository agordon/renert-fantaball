"""Which athletes can be drafted / added: active players with at least one known fantasy position.

Real provider data can contain players without a position (so no slot rules apply) or players no longer on a roster;
they stay in the database (history is never deleted) but are not offered in player pools.
"""
from root import db
from models.fantasy import Athlete


def pool_filter(sport_id: int) -> list:
    return [Athlete.sport_id == sport_id, Athlete.positions != "", Athlete.active.is_(True)]


def pool_query(sport_id: int):
    return db.select(Athlete).where(*pool_filter(sport_id))
