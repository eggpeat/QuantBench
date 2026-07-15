# sports_settlement_ledger_reconciliation

## Overview

This Terminal-Bench-style task asks the agent to reconcile a sports betting operator's internal ledger against settlement logs from an external payment gateway. The workspace contains transaction CSVs with duplicate entries, local timezone offsets, non-completed states that must be ignored, and different payment methods that govern gateway fee rules.

The candidate must create a module `reconcile.py` exposing `reconcile_ledgers()` and write a detailed audit report to `outputs/reconciliation_report.json`.

## Source Grounding & Provenance

- **Source**: *The Logic of Sports Betting* read-extracted lines 122-167 (explaining sportsbook operations, transaction tracking, deposits, withdrawals, and ledger settlements).
- **Task Behavior vs. Source**:
  - The task models real sportsbook financial operations where player deposits and payouts are logged both internally and by external payment processing gateways (e.g. credit card processors and ACH processors).
  - Normalizing, pairing, and auditing differences in amounts, fees, and timestamps reflects standard audit controls needed to maintain sports betting operator licenses.
- **Verifier Risk**: None. Verifier and expected outputs are aligned with banker's rounding rules and deterministic sorting requirements.

## What It Tests

- Parsing timestamps with timezone offsets and converting to UTC date.
- Normalizing messy correlation IDs (handling whitespace, case variations, and strip-prefixes).
- Filtering out invalid status rows (non-completed and non-success states).
- Implementing precise gateway fee calculations utilizing Python's `decimal.Decimal` and `ROUND_HALF_EVEN` rounding.
- Matching records chronologically for duplicate IDs, and flagging missing records or mismatches.
- Net unexplained variance calculation.
- Sorting and structuring deterministic JSON outputs.

## Environment

- Docker image: `python:3.13-slim-bookworm`
- Standard-library Python only.
- No external packages, live gateway access, or network access.

## Inputs

The workspace contains:
- `workspace/internal_ledger.csv`: Sportsbook internal transactions.
- `workspace/gateway_ledger.csv`: Gateway settlement transactions.
- `workspace/reconcile.py`: A stub module with required functions.
- `workspace/run_reconciliation.py`: A run script invoking the candidate's code.

## Required Outputs

Produce `outputs/reconciliation_report.json` matching the schema in `instruction.md`. It must have `summary`, `missing_internal`, `missing_gateway`, `amount_mismatches`, `fee_mismatches`, `duplicate_transactions`, and `late_adjustments` blocks. All lists must be sorted deterministically.

## Verification

The verifier checks:
1. That `outputs/reconciliation_report.json` exactly matches the expected public snapshot output.
2. That helper routines and core functions within `reconcile.py` are properly exposed and return correct results on custom inline test cases (e.g. validating rounding edge cases, time-zone transitions, ID normalization, and mismatch logic).

## Difficulty/Anti-cheat Notes

- Difficulty: Medium.
- Common pitfalls include incorrect banker's rounding of fees, failing to parse timezones correctly when checking UTC dates, miscounting or mismatching duplicates, and incorrect sorting order. Static copies of the JSON are not sufficient due to inline verifier checks on candidate functions.
