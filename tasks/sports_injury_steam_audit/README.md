# sports_injury_steam_audit

## Overview

This Quant Bench task asks the agent to audit sports betting games to detect whether injury-related line movement (steam) has been priced in by the market or if a stale line represents a betting opportunity.

The candidate must create `outputs/injury_steam_audit.json` and a reusable `injury_audit.py` module in the workspace. The verifier checks both the public slate in `events.json` and separate inline edge cases, so a static expected-output copy is not sufficient.

## Source Grounding & Provenance

- **Source**: *Winning Sports Betting* by Masaru Kanemoto.
- **Chapter 3 Textual Evidence**:
  - **Lines 259-281** discuss fake/setup steam and betting funnel timing.
  - **Lines 283-297** discuss injury/lineup steam, priced-in injuries, front-running, and overreaction.
  - **Lines 301-351** discuss line feeds, speed, and slow books.
- **Task Behavior vs. Source**:
  - The task maps these deep qualitative concepts from Chapter 3 into synthetic timestamp rules for deterministic verification.
  - Specifically, it operationalizes these qualitative market reactions into strict chronological conditions (comparing timestamps of line moves vs. news releases) to decide whether injury/line movement edge is already priced in by the market, versus when it presents a stale market betting opportunity, or when it looks like a fake steam move.
  - The source-to-verifier mapping is explicit, so there are no remaining promotion blockers.
- **Verifier Risk**: Medium. Since qualitative concepts are simplified into deterministic synthetic rules, the verifier tests rule adherence rather than authentic, complex market dynamics, but this guarantees test reliability and deterministic outcomes.
## What It Tests

- Correct identification of injury news timestamps relative to line movement.
- Detecting when a model double-counts an injury because the market has already reacted.
- Identifying stale market opportunities where a material injury is confirmed but the line has moved by less than 1.0 point, while model edge is at least 1.5.
- Detecting fake steam moves where a line moves before an unconfirmed rumor and reverses after it.
- Handling ISO 8601 timestamps and standard-library data parsing.
- Producing deterministic JSON output with precise rounding discipline.

## Environment

- Docker image: `python:3.13-slim-bookworm`
- Standard-library Python only.
- No internet, credentials, or live database access.
- The verifier uses pytest-style tests with plain asserts.

## Inputs

`workspace/events.json` contains:

- `games`: a list of games, each with:
  - `event_id`: unique game identifier.
  - `opening_line`: point spread/handicap at market open.
  - `current_line`: current point spread/handicap.
  - `model_fair_line`: model-estimated fair point spread/handicap.
  - `audit_timestamp`: the time at which the audit is performed.
  - `news_timestamp`: the time when the injury news was released (or `null` if none).
  - `injury_status`: `"confirmed_material"`, `"unconfirmed_rumor"`, or `"none"`.
  - `model_relies_on_injury_adjustment`: boolean indicating if the model fair line accounts for this injury.
  - `line_moves`: list of `{"timestamp": "...", "line": ...}` representing chronological market line changes.

## Required Outputs

Create `outputs/injury_steam_audit.json` under the workspace. For each game in the slate, include:

- `event_id`
- `edge_points` (model fair line - current line, rounded to 2 decimal places)
- `classification` (one of `"watch_fake_steam"`, `"no_bet_double_count"`, `"bet_stale_market"`, or `"no_bet_no_edge"`)

## Verification

The public verifier loads `TASK_WORKSPACE` if set, otherwise `/workspace`. It checks that:

1. `outputs/injury_steam_audit.json` exactly matches `tests/expected.json` for the public fixture.
2. The candidate module exposes the required audit functions.
3. Inline edge cases cover various scenarios of fake steam, double counting, stale lines, and no edge.

## Difficulty/Anti-cheat Notes

Difficulty is medium. The logic requires precise comparison of chronological events (timestamps of line moves vs news release) and direction of changes.
