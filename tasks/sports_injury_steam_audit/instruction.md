Read `events.json` from the workspace and create `outputs/injury_steam_audit.json`.

You are auditing a slate of sports betting events to decide when injury/line movement edge is already priced in by the market, versus when it presents a stale market betting opportunity, or when it looks like a fake steam move.

Implement the calculations in boring standard-library Python; do not use external services, live odds, credentials, or network access.

### Required Implementation

1. Create a workspace module named `injury_audit.py` exposing at least these functions:
   - `audit_game(game)`: Audits a single game and returns a dictionary with `"event_id"`, `"edge_points"`, and `"classification"`.
   - `audit_slate(games)`: Audits a list of games and returns a list of dictionaries.
2. Process every game in `events.json`.
3. Running `python run_audit.py` from the workspace must read `events.json` and write `outputs/injury_steam_audit.json` with this shape:

```json
{
  "games": [
    {
      "event_id": "game_1",
      "edge_points": -0.5,
      "classification": "no_bet_double_count"
    }
  ]
}
```

### Calculation Rules

For each game event, calculate:
1. **Edge Points**:
   `edge_points = model_fair_line - current_line`
   - Sign convention: A positive value indicates the model is more positive/favorable on the team (or has a higher spread value) than the current market line (e.g. model fair line of +3.5 vs current line of +2.0 is +1.5). A negative value means the model is more negative/unfavorable than the current line (e.g. model fair line of -5.5 vs current line of -5.0 is -0.5).
   - Round `edge_points` to exactly 2 decimal places.

2. **Classification**:
   Classify each game into exactly one of four categories, checked in order:

   * **`watch_fake_steam`**:
     - `injury_status` is `"unconfirmed_rumor"` and `news_timestamp` is not null.
     - There exists a line move in `line_moves` at a timestamp $t_1 < \text{news\_timestamp}$ where the line value $L_1 \neq \text{opening\_line}$.
     - There exists a subsequent line move in `line_moves` at a timestamp $t_2$ where $\text{news\_timestamp} < t_2 \le \text{audit\_timestamp}$ and the line value $L_2$ moves in the opposite direction from the movement between `opening_line` and $L_1$. That is, $(L_2 - L_1) \times (L_1 - \text{opening\_line}) < 0$.

   * **`no_bet_double_count`**:
     - `model_relies_on_injury_adjustment` is `true`.
     - `injury_status` is `"confirmed_material"` and `news_timestamp` is not null.
     - `news_timestamp` $\le$ `audit_timestamp`.
     - The market has already moved after the confirmed injury news. Specifically, there exists a line move in `line_moves` at a timestamp $t$ where $\text{news\_timestamp} < t \le \text{audit\_timestamp}$ and the line value $L_t \neq L_{\text{injury}}$.
       - *Note*: $L_{\text{injury}}$ is the active line at `news_timestamp` (the line value of the last line move at or before `news_timestamp`, or `opening_line` if there are no line moves at or before `news_timestamp` in `line_moves`).

   * **`bet_stale_market`**:
     - `injury_status` is `"confirmed_material"` and `news_timestamp` is not null.
     - `news_timestamp` $\le$ `audit_timestamp`.
     - The model edge is at least 1.5: $\text{abs}(\text{model\_fair\_line} - \text{current\_line}) \ge 1.5$.
     - No line move of at least 1.0 point happened since the confirmed injury. Specifically, for all line moves at a timestamp $t$ where $\text{news\_timestamp} < t \le \text{audit\_timestamp}$, we have $\text{abs}(L_t - L_{\text{injury}}) < 1.0$, where $L_{\text{injury}}$ is the active line at `news_timestamp` (defined above). Additionally, `current_line` is the active audit-time line (occurring at `audit_timestamp`) and should be considered when determining whether the market has already moved by at least 1.0 point since the injury news. That is, we must also have $\text{abs}(\text{current\_line} - L_{\text{injury}}) < 1.0$.

   * **`no_bet_no_edge`**:
     - Any game that does not fit the criteria for `watch_fake_steam`, `no_bet_double_count`, or `bet_stale_market`.

### Date/Time Parsing
All timestamps in `events.json` are UTC strings in ISO 8601 format (e.g. `2026-06-26T15:00:00Z`). You can compare them as strings directly or parse them to datetime objects (handling the "Z" suffix as UTC).

### Source Grounding & Synthetic Rules Mapping

This task is grounded in the qualitative sports betting market efficiency concepts described in Masaru Kanemoto's *Winning Sports Betting*, Chapter 3:
1. **Fake/Setup Steam & Betting Funnel Timing** (discussed in lines 259-281 of Chapter 3): Operationalized programmatically via the `watch_fake_steam` classification rule, which detects whether a line moved away from opening before an unconfirmed rumor, then moved back in the opposite direction after the rumor.
2. **Injury/Lineup Steam, Priced-In Injuries, Front-Running, & Overreaction** (discussed in lines 283-297 of Chapter 3): Operationalized via the `no_bet_double_count` classification rule. If the model accounts for the injury and the market has already moved since the confirmed injury announcement, any edge from that injury is already priced in.
3. **Line Feeds, Speed, & Slow Books** (discussed in lines 301-351 of Chapter 3): Operationalized via the `bet_stale_market` classification rule, which identifies stale betting opportunities at slower books where a confirmed material injury has occurred, but the market line has not yet moved by at least 1.0 point despite a significant model edge.

These timestamp-based criteria are synthetic operationalizations of these qualitative concepts to facilitate deterministic verification of the model audit logic.
