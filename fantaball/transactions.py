"""Free-agent add/drop and trades. Every function validates on the server and commits atomically
(one commit at the end; any error rolls the whole transaction back)."""
from root import db
from models.fantasy import Athlete, FantasyTeam, League, PlayerTransaction, RosterSlot, TradeItem, TradeOffer, utcnow
from fantaball.errors import ApiError, bad_request, conflict, forbidden, not_found
from fantaball.leagues import log_activity
from fantaball.lineups import auto_set_lineup, owner_map, place_new_players, roster_capacity, team_slots


def _require_active(league: League):
    if league.status != "active":
        raise conflict("Transactions open once the draft is complete")


def add_drop(league: League, team: FantasyTeam, add_id: int | None, drop_id: int | None) -> dict:
    _require_active(league)
    if add_id is None and drop_id is None:
        raise bad_request("Nothing to add or drop")
    slots = {s.athlete_id: s for s in team_slots(team.id)}
    drop_slot = None
    if drop_id is not None:
        drop_slot = slots.get(drop_id)
        if drop_slot is None:
            raise forbidden("You can only drop players on your own roster")
    add_athlete = None
    if add_id is not None:
        add_athlete = db.session.get(Athlete, add_id)
        if not add_athlete or add_athlete.sport_id != league.sport_id:
            raise not_found("Player not found")
        if add_id in owner_map(league.id):
            raise conflict(f"{add_athlete.name} is already on a team in this league")
        if len(slots) - (1 if drop_slot else 0) + 1 > roster_capacity(league):
            raise conflict("Your roster is full - choose a player to drop")

    day = league.current_day
    keep_slot = drop_slot.slot if drop_slot else None
    try:
        if drop_slot is not None:
            dropped = drop_slot.athlete
            db.session.delete(drop_slot)
            db.session.flush()
            db.session.add(PlayerTransaction(league_id=league.id, team_id=team.id, kind="drop", athlete_id=drop_id, day=day))
            log_activity(league.id, "drop", f"{team.name} dropped {dropped.name}", day)
        if add_athlete is not None:
            new = RosterSlot(league_id=league.id, team_id=team.id, athlete_id=add_id, slot="BN", acquired_via="add", acquired_at=utcnow())
            db.session.add(new)
            db.session.flush()
            place_new_players(league, team, [add_id], {add_id: keep_slot} if keep_slot else None)
            db.session.add(PlayerTransaction(league_id=league.id, team_id=team.id, kind="add", athlete_id=add_id, day=day))
            log_activity(league.id, "add", f"{team.name} added {add_athlete.name}", day)
        if team.auto_lineup:
            auto_set_lineup(league, team)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return {"added": add_id, "dropped": drop_id}


# ---------------------------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------------------------
def validate_trade_terms(league: League, from_team: FantasyTeam, to_team: FantasyTeam, give_ids: list[int], get_ids: list[int]):
    """Ownership + roster-size checks shared by proposing, previewing and accepting."""
    if from_team.id == to_team.id:
        raise bad_request("You cannot trade with yourself")
    if from_team.league_id != league.id or to_team.league_id != league.id:
        raise forbidden("Both teams must be in this league")
    if not give_ids or not get_ids:
        raise bad_request("A trade must include at least one player from each side")
    if len(set(give_ids)) != len(give_ids) or len(set(get_ids)) != len(get_ids) or set(give_ids) & set(get_ids):
        raise bad_request("Duplicate players in trade")
    mine = {s.athlete_id for s in team_slots(from_team.id)}
    theirs = {s.athlete_id for s in team_slots(to_team.id)}
    if not set(give_ids) <= mine:
        raise forbidden("You can only offer players on your own roster")
    if not set(get_ids) <= theirs:
        raise conflict("A requested player is no longer on that team")
    cap = roster_capacity(league)
    if len(mine) - len(give_ids) + len(get_ids) > cap or len(theirs) - len(get_ids) + len(give_ids) > cap:
        raise conflict("This trade would put a roster over its size limit")


def propose_trade(league: League, from_team: FantasyTeam, to_team_id: int, give_ids: list[int], get_ids: list[int], note: str | None = None) -> TradeOffer:
    _require_active(league)
    to_team = db.session.get(FantasyTeam, to_team_id)
    if not to_team:
        raise not_found("Trade partner not found")
    validate_trade_terms(league, from_team, to_team, give_ids, get_ids)
    offer = TradeOffer(league_id=league.id, from_team_id=from_team.id, to_team_id=to_team.id, note=(note or "")[:300] or None)
    for aid in give_ids:
        offer.items.append(TradeItem(athlete_id=aid, from_team_id=from_team.id))
    for aid in get_ids:
        offer.items.append(TradeItem(athlete_id=aid, from_team_id=to_team.id))
    db.session.add(offer)
    log_activity(league.id, "trade_offer", f"{from_team.name} sent a trade offer to {to_team.name}", league.current_day)
    db.session.commit()
    return offer


def _offer_sides(offer: TradeOffer):
    give = [i.athlete_id for i in offer.items if i.from_team_id == offer.from_team_id]
    get = [i.athlete_id for i in offer.items if i.from_team_id == offer.to_team_id]
    return give, get


def accept_trade(league: League, offer: TradeOffer, acting_team: FantasyTeam, response_note: str | None = None) -> TradeOffer:
    """Only the receiving team may accept. Re-validates ownership, then swaps both sides in one commit."""
    _require_active(league)
    if offer.league_id != league.id:
        raise not_found("Offer not found")
    if offer.to_team_id != acting_team.id:
        raise forbidden("Only the team receiving the offer can accept it")
    if offer.status != "pending":
        raise conflict(f"This offer is already {offer.status}")
    from_team = db.session.get(FantasyTeam, offer.from_team_id)
    give, get = _offer_sides(offer)
    try:
        validate_trade_terms(league, from_team, acting_team, give, get)
        slots = {s.athlete_id: s for s in team_slots(from_team.id) + team_slots(acting_team.id)}
        for aid in give:
            slots[aid].team_id = acting_team.id
            slots[aid].slot = "BN"
            slots[aid].acquired_via, slots[aid].acquired_at = "trade", utcnow()
        for aid in get:
            slots[aid].team_id = from_team.id
            slots[aid].slot = "BN"
            slots[aid].acquired_via, slots[aid].acquired_at = "trade", utcnow()
        db.session.flush()
        # Pending offers that involve a moved player are void now
        for other in db.session.scalars(db.select(TradeOffer).where(TradeOffer.league_id == league.id, TradeOffer.status == "pending", TradeOffer.id != offer.id)):
            if any(i.athlete_id in set(give) | set(get) for i in other.items):
                other.status, other.resolved_at, other.response_note = "cancelled", utcnow(), "A player in this offer was traded"
        place_new_players(league, acting_team, give)
        place_new_players(league, from_team, get)
        for t in (acting_team, from_team):
            if t.auto_lineup:
                auto_set_lineup(league, t)
        day = league.current_day
        for aid in give:
            db.session.add(PlayerTransaction(league_id=league.id, team_id=from_team.id, kind="trade_out", athlete_id=aid, day=day, related_team_id=acting_team.id))
            db.session.add(PlayerTransaction(league_id=league.id, team_id=acting_team.id, kind="trade_in", athlete_id=aid, day=day, related_team_id=from_team.id))
        for aid in get:
            db.session.add(PlayerTransaction(league_id=league.id, team_id=acting_team.id, kind="trade_out", athlete_id=aid, day=day, related_team_id=from_team.id))
            db.session.add(PlayerTransaction(league_id=league.id, team_id=from_team.id, kind="trade_in", athlete_id=aid, day=day, related_team_id=acting_team.id))
        offer.status, offer.resolved_at, offer.response_note = "accepted", utcnow(), (response_note or None)
        names = {i.athlete_id: i.athlete.name for i in offer.items}
        log_activity(league.id, "trade", f"TRADE: {from_team.name} sends {', '.join(names[a] for a in give)} to {acting_team.name} for {', '.join(names[a] for a in get)}", day)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return offer


def decline_or_cancel(league: League, offer: TradeOffer, acting_team: FantasyTeam, response_note: str | None = None) -> TradeOffer:
    if offer.league_id != league.id:
        raise not_found("Offer not found")
    if offer.status != "pending":
        raise conflict(f"This offer is already {offer.status}")
    if acting_team.id == offer.to_team_id:
        offer.status = "declined"
    elif acting_team.id == offer.from_team_id:
        offer.status = "cancelled"
    else:
        raise forbidden("You are not part of this trade")
    offer.resolved_at, offer.response_note = utcnow(), (response_note or None)
    db.session.commit()
    return offer
