# Poker Range Equity Engine

Implement the card/range equity engine in `range_equity.py` and run it via `run_equity.py` to evaluate the scenarios in `scenarios.json` and produce `outputs/equity.json`.

## Domain Rules & Calculations

### 1. Card Parsing
Cards are represented by two-character strings:
- **Rank**: `2`, `3`, `4`, `5`, `6`, `7`, `8`, `9`, `T` (10), `J` (Jack), `Q` (Queen), `K` (King), `A` (Ace).
- **Suit**: `h` (hearts), `d` (diamonds), `c` (clubs), `s` (spades).

For example, `"Ah"` is the Ace of Hearts, and `"Td"` is the Ten of Diamonds.

### 2. Hand Evaluation (5-7 Cards)
Implement a Texas Hold'em hand evaluator that takes between 5 and 7 cards (representing a player's hole cards plus the community board) and determines the best 5-card poker hand combination. The standard poker hand rankings apply (from highest to lowest):
1. **Straight Flush**: 5 cards of consecutive ranks and the same suit. (Ace-low straight flush `5-4-3-2-A` is allowed, with `5` as the high card).
2. **Four of a Kind**: 4 cards of the same rank.
3. **Full House**: 3 cards of one rank and 2 cards of another rank.
4. **Flush**: 5 cards of the same suit.
5. **Straight**: 5 cards of consecutive ranks. (Ace-low straight `5-4-3-2-A` is allowed, with `5` as the high card).
6. **Three of a Kind**: 3 cards of the same rank.
7. **Two Pair**: 2 cards of one rank and 2 cards of another rank.
8. **One Pair**: 2 cards of the same rank.
9. **High Card**: Hands that do not fit any of the categories above.

Tie-breaking must follow standard poker rules (comparing the ranks of pairs, trips, or kickers in descending order).

### 3. Range Equity Calculation
For each scenario in `scenarios.json`, you are given:
- `p1_range`: a list of starting hands for Player 1, where each hand is represented as a string of two cards (e.g. `"AhKd"`).
- `p2_range`: a list of starting hands for Player 2 (e.g. `"QhQd"`).
- `board`: a list of 0, 3, 4, or 5 community cards.

Your engine must compute the showdown equity for both players.
For each pair of starting hands $(h_1, h_2)$ from `p1_range` and `p2_range`:
- If $h_1$ and $h_2$ share any cards, or if either shares a card with the `board`, that combination is dead/invalid due to card removal and must be ignored.
- If valid, determine the outcome (Player 1 wins, Player 2 wins, or they tie) across all possible ways to complete the board from the remaining cards in the deck.
- If the number of possible board completions is small (e.g. 5-card board, or 4-card board with 44 completions, or 3-card board with 990 completions), perform **exact enumeration**.
- If the board is empty (preflop) or the combination space is large, you may use a **fixed-seed simulation** (with `random.seed(42)`) using at least 10,000 samples to approximate the equity. Note: public fixtures are designed to be small enough for exact enumeration.

Equity is defined as:
- `p1_equity = (p1_wins + 0.5 * ties) / total_valid_trials`
- `p2_equity = (p2_wins + 0.5 * ties) / total_valid_trials`
- `tie_probability = ties / total_valid_trials`

## Required Output

Produce `outputs/equity.json` with the following structure:
```json
{
  "scenarios": [
    {
      "scenario_id": "flop_hand_vs_hand",
      "p1_equity": 0.54321,
      "p2_equity": 0.45679,
      "tie_probability": 0.00000
    }
  ]
}
```
Round the values to 5 decimal places.

Use only Python's standard library. Do not use external libraries (like `treys` or `eval7`).

### Source Grounding
This task operationalizes showdown equity and hand comparisons from David Sklansky and Ed Miller's *No-Limit Hold'em: Theory and Practice* (specifically page 2 and surrounding sections discussing expectation and hand/range values).
