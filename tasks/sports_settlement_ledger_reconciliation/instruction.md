Reconcile a sports betting operator's internal ledger against external payment gateway settlements.

Implement the calculations in standard-library Python; do not use external packages, live services, or network access.

### Workspace Files

- `internal_ledger.csv`: A CSV containing transaction logs recorded internally by the sportsbook operator. Columns:
  - `transaction_id`: unique internal transaction ID
  - `correlation_id`: correlation ID shared with the payment gateway (may have prefix/whitespace)
  - `amount`: gross transaction amount (positive float)
  - `status`: transaction status (e.g. `COMPLETED`, `FAILED`, `PENDING`)
  - `timestamp`: ISO-8601 timestamp with offset (e.g., `2026-06-27T10:00:00-04:00`)
- `gateway_ledger.csv`: A CSV containing settlement records from the payment gateway. Columns:
  - `gateway_id`: gateway's unique transaction ID
  - `correlation_id`: correlation ID (may have prefix/whitespace)
  - `amount`: gross transaction amount (positive float)
  - `fee`: transaction fee charged by the gateway
  - `payment_method`: payment type (`card` or `ach`)
  - `status`: transaction status (`SUCCESS`, `FAILED`)
  - `created_at`: ISO-8601 timestamp with offset (e.g., `2026-06-27T14:00:00Z`)
- `reconcile.py`: Contains stubs for your implementation.
- `run_reconciliation.py`: A wrapper script that imports and runs your `reconcile.main()` function.

### Required API

Your `reconcile.py` file must expose the following:

- `reconcile_ledgers(internal_csv: str | Path, gateway_csv: str | Path) -> dict`
- `main(workspace_path: str | Path = None)`

Your `main()` function should parse arguments (or use the workspace path), run the reconciliation, and write the output report to `outputs/reconciliation_report.json`.

---

### Reconciliation Rules

1. **Filtering**:
   - Only process rows with status `COMPLETED` in the internal ledger and status `SUCCESS` in the gateway ledger.
   - Ignore all failed, pending, retrying, or other non-successful rows.

2. **Correlation ID Normalization**:
   - Correlation IDs must be normalized before matching or checking:
     1. Trim any leading or trailing whitespace.
     2. Convert the string to lowercase.
     3. If the string starts with `tx_`, `txn_`, `tx-`, or `txn-`, strip that prefix.

3. **Duplicate Detection**:
   - Within the filtered completed rows, detect any normalized correlation ID that appears more than once in the internal ledger (internal duplicates) or more than once in the gateway ledger (gateway duplicates).
   - Report the occurrences count for each duplicate ID.

4. **Chronological Pairing**:
   - To match internal records to gateway records:
     - For each normalized correlation ID, sort its completed internal records chronologically by UTC timestamp.
     - Sort its completed gateway records chronologically by UTC timestamp.
     - Pair the $j$-th completed internal record with the $j$-th completed gateway record for $j = 1 \dots \min(N_{int}, N_{gat})$.
     - Unpaired internal records (indices $j \ge N_{gat}$) are reported as missing in gateway.
     - Unpaired gateway records (indices $j \ge N_{int}$) are reported as missing in internal.

5. **Gateway Fee Rules**:
   - For payment method `card`: Expected fee is `2.5%` of the gateway gross amount + `$0.30`.
   - For payment method `ach`: Expected fee is `1.0%` of the gateway gross amount + `$0.15`, with a maximum cap of `$5.00` per transaction.
   - All calculations must be computed using `decimal.Decimal` and rounded to 2 decimal places using `ROUND_HALF_EVEN` (half-even / banker's rounding).

6. **Reconciliation Checks**:
   - **Amount Mismatch**: For matched pairs, check if the gross internal amount differs from the gross gateway amount. If they differ, calculate `difference = internal_amount - gateway_amount`.
   - **Fee Mismatch**: For matched pairs, calculate the expected fee using the rule above. If it differs from the gateway's actual `fee`, calculate `difference = expected_fee - actual_fee`.
   - **Late Adjustment**: For matched pairs, compare their UTC dates (derived from UTC timestamps as `YYYY-MM-DD`). A transaction is a late adjustment if the gateway UTC date is strictly later than the internal UTC date (`gateway_date_utc > internal_date_utc`). Calculate the days difference: `days_difference = gateway_date_utc - internal_date_utc`.

7. **Net Unexplained Dollars**:
   - Calculate net unexplained dollars as `total_completed_internal_amount - total_completed_gateway_amount`. This is equivalent to:
     `sum(internal_amount of missing_gateway) - sum(gateway_amount of missing_internal) + sum(internal_amount - gateway_amount of matched)`
   - Report this value as a float rounded to 2 decimal places.

---

### Output JSON Format

Write your report to `outputs/reconciliation_report.json` with this schema. All monetary float fields must be rounded to exactly 2 decimal places.

```json
{
  "summary": {
    "total_internal_rows_processed": 8,
    "total_gateway_rows_processed": 8,
    "total_matched_transactions": 6,
    "total_missing_internal": 2,
    "total_missing_gateway": 2,
    "total_amount_mismatches": 1,
    "total_fee_mismatches": 1,
    "total_duplicates_internal": 1,
    "total_duplicates_gateway": 1,
    "total_late_adjustments": 1,
    "net_unexplained_dollars": 75.0
  },
  "missing_internal": [
    {
      "correlation_id": "103",
      "gateway_amount": 75.0,
      "gateway_date_utc": "2026-06-27"
    },
    {
      "correlation_id": "108",
      "gateway_amount": 60.0,
      "gateway_date_utc": "2026-06-27"
    }
  ],
  "missing_gateway": [
    {
      "correlation_id": "107",
      "internal_amount": 80.0,
      "internal_date_utc": "2026-06-27"
    },
    {
      "correlation_id": "104",
      "internal_amount": 120.0,
      "internal_date_utc": "2026-06-28"
    }
  ],
  "amount_mismatches": [
    {
      "correlation_id": "105",
      "internal_amount": 200.0,
      "gateway_amount": 190.0,
      "difference": 10.0
    }
  ],
  "fee_mismatches": [
    {
      "correlation_id": "106",
      "payment_method": "ach",
      "amount": 500.0,
      "expected_fee": 5.0,
      "actual_fee": 4.5,
      "difference": 0.5
    }
  ],
  "duplicate_transactions": {
    "internal": [
      {
        "correlation_id": "107",
        "occurrences": 2
      }
    ],
    "gateway": [
      {
        "correlation_id": "108",
        "occurrences": 2
      }
    ]
  },
  "late_adjustments": [
    {
      "correlation_id": "109",
      "internal_date_utc": "2026-06-25",
      "gateway_date_utc": "2026-06-27",
      "days_difference": 2
    }
  ]
}
```

### Sorting Constraints in Output Lists

To guarantee a deterministic output:
1. `missing_internal` must be sorted by `gateway_date_utc` (ascending), then by `correlation_id` (ascending).
2. `missing_gateway` must be sorted by `internal_date_utc` (ascending), then by `correlation_id` (ascending).
3. `amount_mismatches`, `fee_mismatches`, and `late_adjustments` must be sorted by `correlation_id` (ascending).
4. `duplicate_transactions.internal` and `duplicate_transactions.gateway` must be sorted by `correlation_id` (ascending).
