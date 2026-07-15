# Poker Hand History State Machine Parser

Implement the hand history parser in `hand_parser.py` and output the parsed hands to `outputs/parsed_hands.json` by running `run_parser.py`.

## Goal
Implement a robust state-machine parser that converts raw-text poker hand histories into a canonical structured JSON format.

Your parser must handle:
1. **Metadata Parsing**: Hand ID, Table Name, blinds stakes, and button seat.
2. **Seat & Stack Tracking**: Record starting stacks, and update them based on posts, bets, raises, calls, uncalled bets returned, and showdown collections.
3. **Chronological Action Log**: Track all folds, checks, calls, bets, and raises across preflop, flop, turn, and river.
4. **Stateful Validation**: Detect malformed or illegal hands, including:
   - Action by a player who is not seated.
   - Action by a player who has already folded.
   - Player checking when facing an outstanding bet (must call, raise, or fold).
   - Insufficient stack (betting or calling more chips than a player has).
5. **Chat Filtering**: Ignore chat lines and other non-action text, even if they contain poker keywords (e.g., a player typing `"I bet $100"` in chat).

## Inputs & Output

### Input Format
The input file `hand_histories.txt` contains multiple hand histories separated by blank lines. Each hand follows a PokerStars-style text formatting. Here is an example of a valid hand:

```text
PokerStars Hand #123456789: Hold'em No Limit ($1.00/$2.00 USD) - 2026/06/27 12:00:00 ET
Table 'Redwood' 9-max Seat #3 is the button
Seat 1: PlayerA ($200.00 in chips)
Seat 2: PlayerB ($150.00 in chips)
Seat 3: PlayerC ($100.00 in chips)
PlayerA: posts small blind $1.00
PlayerB: posts big blind $2.00
*** HOLE CARDS ***
PlayerC: raises $4.00 to $6.00
PlayerA: calls $5.00
PlayerB: folds
*** FLOP *** [2d 5h As]
PlayerA: checks
PlayerC: bets $10.00
PlayerA: calls $10.00
*** TURN *** [2d 5h As] [Js]
PlayerA: checks
PlayerC: bets $20.00
PlayerA: folds
Uncalled bet ($20.00) returned to PlayerC
PlayerC collected $34.00 from pot
*** SUMMARY ***
Total pot $34.00 | Rake $0.00
Board [2d 5h As Js]
Seat 1: PlayerA (small blind) folded on the Turn
Seat 2: PlayerB (big blind) folded before Flop
Seat 3: PlayerC (button) collected ($34.00)
```

### Required Output format
The output must be written to `outputs/parsed_hands.json` and contain a list of objects (one per hand history in the input file, in the same order):

```json
[
  {
    "hand_id": "123456789",
    "table_name": "Redwood",
    "button_seat": 3,
    "small_blind": 1.0,
    "big_blind": 2.0,
    "seats": [
      { "seat_number": 1, "player_name": "PlayerA", "chips": 200.0 },
      { "seat_number": 2, "player_name": "PlayerB", "chips": 150.0 },
      { "seat_number": 3, "player_name": "PlayerC", "chips": 100.0 }
    ],
    "blinds_posted": [
      { "player_name": "PlayerA", "type": "small", "amount": 1.0 },
      { "player_name": "PlayerB", "type": "big", "amount": 2.0 }
    ],
    "actions": [
      { "street": "preflop", "player_name": "PlayerC", "action_type": "raise", "amount": 6.0, "to_amount": 6.0 },
      { "street": "preflop", "player_name": "PlayerA", "action_type": "call", "amount": 5.0, "to_amount": 6.0 },
      { "street": "preflop", "player_name": "PlayerB", "action_type": "fold", "amount": 0.0, "to_amount": 2.0 },
      { "street": "flop", "player_name": "PlayerA", "action_type": "check", "amount": 0.0, "to_amount": 0.0 },
      { "street": "flop", "player_name": "PlayerC", "action_type": "bet", "amount": 10.0, "to_amount": 10.0 },
      { "street": "flop", "player_name": "PlayerA", "action_type": "call", "amount": 10.0, "to_amount": 10.0 },
      { "street": "turn", "player_name": "PlayerA", "action_type": "check", "amount": 0.0, "to_amount": 0.0 },
      { "street": "turn", "player_name": "PlayerC", "action_type": "bet", "amount": 20.0, "to_amount": 20.0 },
      { "street": "turn", "player_name": "PlayerA", "action_type": "fold", "amount": 0.0, "to_amount": 0.0 }
    ],
    "uncalled_bet_returned": {
      "player_name": "PlayerC",
      "amount": 20.0
    },
    "total_pot": 34.0,
    "rake": 0.0,
    "winners": [
      { "player_name": "PlayerC", "amount": 34.0, "showed": false }
    ],
    "valid": true,
    "errors": []
  }
]
```

### Rules & Details
- **Stakes/Currencies**: Remove any currency symbols (like `$`) when converting to floats. All numerical values must be parsed as floats.
- **Actions and Amounts**:
  - `amount` is the *incremental* chips added to the pot by this specific action.
  - `to_amount` is the *total* chips contributed by this player on the *current street* up to and including this action.
  - For a `fold` or `check`, `amount` is `0.0`, and `to_amount` is the player's current street contribution.
  - Preflop street contributions start at the posted blind amount (e.g., Small Blind has $1.00 contributed already, so calling to $6.00 adds an incremental `amount` of $5.00, resulting in `to_amount` of $6.00).
- **All-ins**:
  - If a player goes all-in, their action can be `call` or `raise` with ` and is all-in` appended in the history.
  - If a player is facing a bet larger than their remaining chips and they call, their stack becomes `0.0`, and the action is legal (their `amount` is whatever chips they had remaining).
- **Validation Rules**:
  - If a hand is invalid, set `"valid": false` and add a message to `"errors"`. You do not need to populate `"actions"`, `"winners"`, etc. for invalid hands, but `"hand_id"` must be populated if it was successfully parsed.
  - Validation checks:
    - `"Player acting is not seated"`: An action is taken by a player not in the seat list.
    - `"Player acting has already folded"`: A player who folded on a prior street/action tries to check, call, bet, or raise.
    - `"Player checking when facing a bet"`: A player checks when the current bet on the street is greater than their current street contribution.
    - `"Insufficient stack"`: A player bets or calls an amount that exceeds their remaining stack size.
- **Chat vs Actions**:
  - Chat lines are formatted as `PlayerName: "message"` (in double quotes) or `Table Chat: ...`. These must be ignored.
  - Player names can contain action verbs (e.g., a player named `folds` or `calls`). A regex-only pattern like `r"(\w+): folds"` will fail. You must track the active players seated at the table and distinguish player actions from chat and verbs.

Implement your solution in `hand_parser.py`. Do not import external packages; use only Python's standard library.
