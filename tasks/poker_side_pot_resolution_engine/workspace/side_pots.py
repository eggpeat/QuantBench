"""Poker side pot resolution engine."""


def settle_hand(hand: dict) -> dict:
    """Settle a single poker hand, allocating pots, handling chops, folds, all-ins,

    and odd chips. Returns a dictionary with hand_id, payouts, and conservation info.
    """
    # TODO: Implement side pot transactional allocation.
    raise NotImplementedError("Implement settle_hand")


def settle_all(hands: list[dict]) -> list[dict]:
    """Settle a list of poker hands."""
    # TODO: Implement settle_all.
    raise NotImplementedError("Implement settle_all")
