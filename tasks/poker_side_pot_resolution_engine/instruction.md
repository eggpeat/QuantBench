# Poker Side Pot Resolution Engine

Implement a deterministic transactional allocation engine for no-limit poker side pots, chops, folds, all-in caps, and odd chips in `side_pots.py`.

In a table-stakes no-limit poker hand, multiple side pots are created when players are all-in for different amounts. Under standard rules:
1. **Table Stakes**: A player cannot win more from any other player than they have contributed to the pot themselves.
2. **Side Pots**: The total money in the pot is divided into levels (main pot and side pots) based on the bet sizes of all players (both active and folded).
3. **Folds**: A player who has folded cannot win any portion of any pot. Their contribution remains in the pot as "dead money" and is won by eligible active players, or refunded if no active player is eligible.
4. **Eligibility**: A player is only eligible to win a pot level if they are active (not folded) and they contributed the full amount required for that level (i.e., their total bet is greater than or equal to the level's upper bet limit).
5. **Chops and Odd Chips**:
   - If multiple eligible players tie with the same highest hand strength for a pot level, the pot at that level is split equally among them.
   - Any remainder/odd chips from integer division are distributed 1 chip at a time to the tied players in ascending order of their seat numbers (the earliest seat number gets the first odd chip, the next gets the second, and so on), until the remainder is exhausted.
6. **Refunds/Uncalled Bets**: If no active player is eligible for a pot level (i.e., all active players bet less than the lower limit of that level, which can happen if the highest bettors folded), the pot at that level is refunded to the players who contributed to it in proportion to their contributions (which is exactly the amount they contributed to that specific level).

### Required API
In `side_pots.py`, implement:
- `settle_hand(hand: dict) -> dict`: Settle a single hand.
- `settle_all(hands: list[dict]) -> list[dict]`: Settle a list of hands.

#### Input Hand Schema
```json
{
  "hand_id": "hand_001",
  "players": [
    {
      "seat": 1,
      "name": "Alice",
      "bet": 100,
      "folded": false,
      "hand_strength": 5
    },
    ...
  ]
}
```

#### Output Settlement Schema
```json
{
  "hand_id": "hand_001",
  "payouts": {
    "Alice": 400,
    "Bob": 0,
    "Charlie": 350,
    "Dave": 0
  },
  "conservation": {
    "total_bets": 750,
    "total_payouts": 750,
    "is_conserved": true
  }
}
```
All keys in the `payouts` dictionary must match the player `name` strings from the input.

Use only Python's standard library. Do not use external services, credentials, or third-party libraries.
