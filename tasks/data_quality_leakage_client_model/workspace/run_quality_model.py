#!/usr/bin/env python3
\"\"\"Run data-quality and leakage audit on client data.\"\"\"

import json
import csv
from pathlib import Path
import sys
from quality_model import audit_dataset, make_validation_split, write_report

def main():
    # Allow workspace path override from command line or default to current directory
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

    csv_path = workspace / "client_data.csv"
    schema_path = workspace / "schema.json"
    output_path = workspace / "outputs" / "model_audit.json"

    if not csv_path.exists():
        print(f"Error: {csv_path} does not exist.")
        sys.exit(1)
    if not schema_path.exists():
        print(f"Error: {schema_path} does not exist.")
        sys.exit(1)

    with open(schema_path, "r", encoding="utf-8") as fh:
        schema = json.load(fh)

    rows = []
    with open(csv_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            parsed_row = {}
            for k, v in row.items():
                if v == "":
                    parsed_row[k] = ""
                else:
                    try:
                        parsed_row[k] = int(v)
                    except ValueError:
                        try:
                            parsed_row[k] = float(v)
                        except ValueError:
                            parsed_row[k] = v
            rows.append(parsed_row)

    # Perform audit
    excluded_columns = audit_dataset(rows, schema)

    # Perform split
    split_info = make_validation_split(rows, schema)

    # Construct final report
    pk = schema["primary_key"]
    entity_id = schema["entity_id"]
    timestamp = schema["timestamp"]
    metadata_cols = {pk, entity_id, timestamp}
    total_feature_target_cols = sum(1 for col in rows[0].keys() if col not in metadata_cols)

    num_excluded = (
        len(excluded_columns["leakage"]) +
        len(excluded_columns["target_contamination"]) +
        len(excluded_columns["high_missingness"])
    )
    leakage_ratio = num_excluded / total_feature_target_cols if total_feature_target_cols > 0 else 0.0

    report_data = {
        "excluded_columns": excluded_columns,
        "validation_split": {
            "train_ids": split_info["train_ids"],
            "validation_ids": split_info["validation_ids"]
        },
        "quality_metrics": {
            "duplicate_ids_count": split_info["duplicate_ids_count"],
            "unstable_ids_count": split_info["unstable_ids_count"],
            "future_timestamps_count": split_info["future_timestamps_count"],
            "label_leakage_detected": len(excluded_columns["leakage"]) > 0
        },
        "metric_sanity": {
            "train_size": split_info["train_size"],
            "validation_size": split_info["validation_size"],
            "leakage_ratio_removed": round(leakage_ratio, 4)
        }
    }

    write_report(report_data, output_path)
    print(f"Report successfully written to {output_path}")

if __name__ == "__main__":
    main()
