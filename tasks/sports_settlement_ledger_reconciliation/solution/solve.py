#!/usr/bin/env python3
import json
import sys
from pathlib import Path

MODULE_SOURCE = r'''
import csv
import json
from decimal import Decimal, ROUND_HALF_EVEN
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter, defaultdict


def normalize_correlation_id(correlation_id: str) -> str:
    if not correlation_id:
        return ""
    cid = correlation_id.strip().lower()
    for prefix in ["txn_", "tx_", "txn-", "tx-"]:
        if cid.startswith(prefix):
            cid = cid[len(prefix):]
            break
    return cid


def calculate_expected_fee(amount: Decimal, payment_method: str) -> Decimal:
    if payment_method == "card":
        fee = amount * Decimal("0.025") + Decimal("0.30")
    elif payment_method == "ach":
        fee = amount * Decimal("0.01") + Decimal("0.15")
        if fee > Decimal("5.00"):
            fee = Decimal("5.00")
    else:
        fee = Decimal("0.00")
    return fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def parse_iso_to_utc_date(timestamp_str: str) -> tuple[datetime, str]:
    ts_str = timestamp_str.replace(" ", "T")
    dt = datetime.fromisoformat(ts_str)
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt, utc_dt.date().isoformat()


def reconcile_ledgers(internal_csv: str | Path, gateway_csv: str | Path) -> dict:
    internal_rows = []
    with open(internal_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") != "COMPLETED":
                continue
            cid = normalize_correlation_id(row["correlation_id"])
            dt, date_utc = parse_iso_to_utc_date(row["timestamp"])
            internal_rows.append({
                "transaction_id": row["transaction_id"],
                "correlation_id": cid,
                "amount": Decimal(row["amount"]),
                "timestamp": dt,
                "date_utc": date_utc
            })

    gateway_rows = []
    with open(gateway_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") != "SUCCESS":
                continue
            cid = normalize_correlation_id(row["correlation_id"])
            dt, date_utc = parse_iso_to_utc_date(row["created_at"])
            gateway_rows.append({
                "gateway_id": row["gateway_id"],
                "correlation_id": cid,
                "amount": Decimal(row["amount"]),
                "fee": Decimal(row["fee"]),
                "payment_method": row["payment_method"],
                "created_at": dt,
                "date_utc": date_utc
            })

    # Duplicate detection
    internal_cids = [r["correlation_id"] for r in internal_rows]
    gateway_cids = [r["correlation_id"] for r in gateway_rows]

    internal_counts = Counter(internal_cids)
    gateway_counts = Counter(gateway_cids)

    internal_duplicates = sorted([
        {"correlation_id": cid, "occurrences": count}
        for cid, count in internal_counts.items() if count > 1
    ], key=lambda x: x["correlation_id"])

    gateway_duplicates = sorted([
        {"correlation_id": cid, "occurrences": count}
        for cid, count in gateway_counts.items() if count > 1
    ], key=lambda x: x["correlation_id"])

    # Group by correlation ID and sort chronologically
    internal_by_cid = defaultdict(list)
    for r in internal_rows:
        internal_by_cid[r["correlation_id"]].append(r)
    for cid in internal_by_cid:
        internal_by_cid[cid].sort(key=lambda x: x["timestamp"])

    gateway_by_cid = defaultdict(list)
    for r in gateway_rows:
        gateway_by_cid[r["correlation_id"]].append(r)
    for cid in gateway_by_cid:
        gateway_by_cid[cid].sort(key=lambda x: x["created_at"])

    all_cids = set(internal_by_cid.keys()).union(gateway_by_cid.keys())

    matched = []
    missing_internal = []
    missing_gateway = []

    for cid in sorted(all_cids):
        ints = internal_by_cid.get(cid, [])
        gats = gateway_by_cid.get(cid, [])
        n_int = len(ints)
        n_gat = len(gats)
        n_min = min(n_int, n_gat)

        for i in range(n_min):
            matched.append((ints[i], gats[i]))

        if n_int > n_gat:
            for i in range(n_min, n_int):
                missing_gateway.append(ints[i])
        elif n_gat > n_int:
            for i in range(n_min, n_gat):
                missing_internal.append(gats[i])

    amount_mismatches = []
    fee_mismatches = []
    late_adjustments = []

    for internal, gateway in matched:
        cid = internal["correlation_id"]
        int_amt = internal["amount"]
        gat_amt = gateway["amount"]

        if int_amt != gat_amt:
            amount_mismatches.append({
                "correlation_id": cid,
                "internal_amount": float(int_amt),
                "gateway_amount": float(gat_amt),
                "difference": float(int_amt - gat_amt)
            })

        expected_fee = calculate_expected_fee(gat_amt, gateway["payment_method"])
        actual_fee = gateway["fee"]
        if expected_fee != actual_fee:
            fee_mismatches.append({
                "correlation_id": cid,
                "payment_method": gateway["payment_method"],
                "amount": float(gat_amt),
                "expected_fee": float(expected_fee),
                "actual_fee": float(actual_fee),
                "difference": float(expected_fee - actual_fee)
            })

        int_date = internal["date_utc"]
        gat_date = gateway["date_utc"]
        if gat_date > int_date:
            d1 = datetime.strptime(int_date, "%Y-%m-%d")
            d2 = datetime.strptime(gat_date, "%Y-%m-%d")
            late_adjustments.append({
                "correlation_id": cid,
                "internal_date_utc": int_date,
                "gateway_date_utc": gat_date,
                "days_difference": (d2 - d1).days
            })

    missing_internal_out = [
        {
            "correlation_id": r["correlation_id"],
            "gateway_amount": float(r["amount"]),
            "gateway_date_utc": r["date_utc"]
        } for r in missing_internal
    ]
    missing_internal_out.sort(key=lambda x: (x["gateway_date_utc"], x["correlation_id"]))

    missing_gateway_out = [
        {
            "correlation_id": r["correlation_id"],
            "internal_amount": float(r["amount"]),
            "internal_date_utc": r["date_utc"]
        } for r in missing_gateway
    ]
    missing_gateway_out.sort(key=lambda x: (x["internal_date_utc"], x["correlation_id"]))

    amount_mismatches.sort(key=lambda x: x["correlation_id"])
    fee_mismatches.sort(key=lambda x: x["correlation_id"])
    late_adjustments.sort(key=lambda x: x["correlation_id"])

    total_internal_amt = sum(r["amount"] for r in internal_rows)
    total_gateway_amt = sum(r["amount"] for r in gateway_rows)
    net_unexplained = total_internal_amt - total_gateway_amt

    return {
        "summary": {
            "total_internal_rows_processed": len(internal_rows),
            "total_gateway_rows_processed": len(gateway_rows),
            "total_matched_transactions": len(matched),
            "total_missing_internal": len(missing_internal_out),
            "total_missing_gateway": len(missing_gateway_out),
            "total_amount_mismatches": len(amount_mismatches),
            "total_fee_mismatches": len(fee_mismatches),
            "total_duplicates_internal": len(internal_duplicates),
            "total_duplicates_gateway": len(gateway_duplicates),
            "total_late_adjustments": len(late_adjustments),
            "net_unexplained_dollars": float(net_unexplained)
        },
        "missing_internal": missing_internal_out,
        "missing_gateway": missing_gateway_out,
        "amount_mismatches": amount_mismatches,
        "fee_mismatches": fee_mismatches,
        "duplicate_transactions": {
            "internal": internal_duplicates,
            "gateway": gateway_duplicates
        },
        "late_adjustments": late_adjustments
    }


def main(workspace_path: str | Path = None):
    if workspace_path is None:
        workspace_path = Path.cwd()
    else:
        workspace_path = Path(workspace_path)

    internal_csv = workspace_path / "internal_ledger.csv"
    gateway_csv = workspace_path / "gateway_ledger.csv"

    report = reconcile_ledgers(internal_csv, gateway_csv)

    output_dir = workspace_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "reconciliation_report.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
'''.lstrip()

RUN_SOURCE = r'''#!/usr/bin/env python3
import sys
from pathlib import Path
import reconcile


def main():
    workspace_path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent
    reconcile.main(workspace_path)


if __name__ == "__main__":
    main()
'''.lstrip()


def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    (workspace / "reconcile.py").write_text(MODULE_SOURCE, encoding="utf-8")
    (workspace / "run_reconciliation.py").write_text(RUN_SOURCE, encoding="utf-8")
    sys.path.insert(0, str(workspace))
    import reconcile
    reconcile.main(str(workspace))


if __name__ == "__main__":
    main()
