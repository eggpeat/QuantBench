#!/usr/bin/env python3
"""Reference solution for the client data-quality and leakage modeling task."""

import json
import csv
import sys
from pathlib import Path

QUALITY_MODEL_SOURCE = """\"\"\"Data Quality & Leakage Detection for Client Modeling.

This module provides tools for auditing datasets to identify data quality issues,
specifically:
- Target contamination (features containing lookahead or global statistics that bleed future target information)
- Label leakage (features that are proxy targets or only present for specific target values)
- Unstable entity IDs (entity IDs with conflicting stable attributes)
- Duplicate record IDs
- Future timestamps
- Columns with high missingness

It also provides functions to create a clean temporal split.
\"\"\"

import math
import json
from pathlib import Path

def calculate_pearson_correlation(rows, col1, col2):
    x_vals = []
    y_vals = []
    for r in rows:
        val1 = r.get(col1)
        val2 = r.get(col2)
        if val1 is None or val1 == "" or str(val1).lower() in ("nan", "null"):
            continue
        if val2 is None or val2 == "" or str(val2).lower() in ("nan", "null"):
            continue
        try:
            x_vals.append(float(val1))
            y_vals.append(float(val2))
        except ValueError:
            continue
    if len(x_vals) < 2:
        return None

    mean_x = sum(x_vals) / len(x_vals)
    mean_y = sum(y_vals) / len(y_vals)

    num = 0.0
    den_x = 0.0
    den_y = 0.0
    for x, y in zip(x_vals, y_vals):
        dx = x - mean_x
        dy = y - mean_y
        num += dx * dy
        den_x += dx * dx
        den_y += dy * dy

    if den_x == 0.0 or den_y == 0.0:
        return None
    return num / math.sqrt(den_x * den_y)

def audit_dataset(rows, schema):
    pk = schema["primary_key"]
    entity_id = schema["entity_id"]
    timestamp = schema["timestamp"]
    target = schema["target"]
    cutoff_time = schema["cutoff_time"]
    stable_attributes = schema.get("stable_attributes", [])
    contamination_candidates = schema.get("contamination_candidates", [])

    metadata_cols = {pk, entity_id, timestamp, target}
    all_cols = list(rows[0].keys()) if rows else []
    feature_cols = [c for c in all_cols if c not in metadata_cols]

    excluded_columns = {
        "leakage": [],
        "target_contamination": [],
        "high_missingness": []
    }

    if not rows:
        return excluded_columns

    # Group rows by client for sequence checks
    clients_data = {}
    for r in rows:
        cid = r[entity_id]
        if cid not in clients_data:
            clients_data[cid] = []
        clients_data[cid].append(r)

    for cid in clients_data:
        clients_data[cid].sort(key=lambda x: x[timestamp])

    for col in feature_cols:

        # 1. Check label leakage:
        # Check Pearson correlation
        corr = calculate_pearson_correlation(rows, col, target)
        is_leakage = False
        if corr is not None and abs(abs(corr) - 1.0) < 1e-9:
            is_leakage = True

        # Check conditional presence leakage
        if not is_leakage:
            non_missing_targets = []
            for r in rows:
                val = r.get(col)
                if val is not None and val != "" and str(val).lower() not in ("nan", "null"):
                    non_missing_targets.append(r[target])
            if len(non_missing_targets) > 0:
                unique_targets = set(non_missing_targets)
                if len(unique_targets) == 1 and 1 in unique_targets:
                    overall_targets = {r[target] for r in rows}
                    if len(overall_targets) > 1:
                        is_leakage = True

        # Check future lookahead leakage (value at row k equals value of another col at row k+1)
        if not is_leakage:
            for ref_col in all_cols:
                if ref_col == col:
                    continue
                match = True
                has_mult = False
                for cid, crows in clients_data.items():
                    # filter rows to unique timestamps
                    unique_t_rows = []
                    seen_t = set()
                    for r in crows:
                        t = r[timestamp]
                        if t not in seen_t:
                            seen_t.add(t)
                            unique_t_rows.append(r)
                    if len(unique_t_rows) < 2:
                        continue
                    has_mult = True
                    for k in range(len(unique_t_rows) - 1):
                        val_curr = unique_t_rows[k][col]
                        val_next = unique_t_rows[k+1][ref_col]
                        if val_curr != val_next:
                            match = False
                            break
                    if not match:
                        break
                if has_mult and match:
                    is_leakage = True
                    break

        if is_leakage:
            excluded_columns["leakage"].append(col)
            continue

        # 2. Check target contamination
        is_contamination = False
        for ref_col in all_cols:
            if ref_col == col:
                continue
            match_sum = True
            match_mean = True
            has_mult = False
            for cid, crows in clients_data.items():
                if len(crows) < 2:
                    continue
                has_mult = True
                vals = [r.get(col) for r in crows]
                if len(set(vals)) != 1:
                    match_sum = False
                    match_mean = False
                    break
                try:
                    ref_vals = [float(r[ref_col]) for r in crows]
                    const_val = float(vals[0])
                except ValueError:
                    match_sum = False
                    match_mean = False
                    break

                if abs(const_val - sum(ref_vals)) > 1e-9:
                    match_sum = False
                if abs(const_val - (sum(ref_vals)/len(ref_vals))) > 1e-9:
                    match_mean = False
                if not match_sum and not match_mean:
                    break

            if has_mult and (match_sum or match_mean):
                n_diff = 0
                for cid, crows in clients_data.items():
                    if len(crows) >= 2:
                        if crows[0][col] != crows[0][ref_col]:
                            n_diff += 1
                if n_diff > 0:
                    is_contamination = True
                    break

        if is_contamination or col in contamination_candidates:
            excluded_columns["target_contamination"].append(col)
            continue

        # 3. Check missingness
        missing_count = sum(1 for r in rows if r.get(col) is None or r.get(col) == "" or str(r.get(col)).lower() in ("nan", "null"))
        pct = missing_count / len(rows)
        if pct > 0.5:
            excluded_columns["high_missingness"].append(col)


    # Sort output lists
    for k in excluded_columns:
        excluded_columns[k].sort()

    return excluded_columns

def make_validation_split(rows, schema=None):
    if schema is None:
        # Fallback to load schema.json from current directory if possible
        schema_path = Path("schema.json")
        if schema_path.exists():
            with schema_path.open("r", encoding="utf-8") as fh:
                schema = json.load(fh)
        else:
            raise ValueError("schema is required and schema.json not found")

    if not rows:
        return {
            "train_ids": [],
            "validation_ids": [],
            "duplicate_ids_count": 0,
            "unstable_ids_count": 0,
            "future_timestamps_count": 0,
            "train_size": 0,
            "validation_size": 0
        }

    pk = schema["primary_key"]
    entity_id = schema["entity_id"]
    timestamp = schema["timestamp"]
    cutoff_time = schema["cutoff_time"]
    train_val_cutoff = schema["train_validation_cutoff"]
    stable_attributes = schema.get("stable_attributes", [])

    # 1. Identify duplicate primary keys
    pk_counts = {}
    for r in rows:
        val = r[pk]
        pk_counts[val] = pk_counts.get(val, 0) + 1
    duplicate_pks = {k for k, v in pk_counts.items() if v > 1}
    duplicate_ids_count = len(duplicate_pks)

    # 2. Identify unstable entity IDs
    entity_stable_vals = {}
    for r in rows:
        eid = r[entity_id]
        if eid not in entity_stable_vals:
            entity_stable_vals[eid] = {attr: set() for attr in stable_attributes}
        for attr in stable_attributes:
            val = r.get(attr)
            if val is not None and val != "" and str(val).lower() not in ("nan", "null"):
                entity_stable_vals[eid][attr].add(val)

    unstable_entities = set()
    for eid, attr_map in entity_stable_vals.items():
        for attr, vals in attr_map.items():
            if len(vals) > 1:
                unstable_entities.add(eid)
                break
    unstable_ids_count = len(unstable_entities)

    # 3. Identify future timestamps
    future_rows = []
    for r in rows:
        t_str = r[timestamp]
        if t_str > cutoff_time:
            future_rows.append(r[pk])
    future_timestamps_count = len(future_rows)

    # Filter rows based on exclusions
    clean_rows = []
    for r in rows:
        row_id = r[pk]
        eid = r[entity_id]
        t_str = r[timestamp]

        # Check exclusions
        if row_id in duplicate_pks:
            continue
        if eid in unstable_entities:
            continue
        if t_str > cutoff_time:
            continue

        clean_rows.append(r)

    # Split into train and validation
    train_ids = []
    val_ids = []
    for r in clean_rows:
        row_id = r[pk]
        t_str = r[timestamp]
        if t_str < train_val_cutoff:
            train_ids.append(row_id)
        else:
            val_ids.append(row_id)

    # Sort IDs for deterministic output
    train_ids.sort()
    val_ids.sort()

    return {
        "train_ids": train_ids,
        "validation_ids": val_ids,
        "duplicate_ids_count": duplicate_ids_count,
        "unstable_ids_count": unstable_ids_count,
        "future_timestamps_count": future_timestamps_count,
        "train_size": len(train_ids),
        "validation_size": len(val_ids)
    }

def write_report(report_data, output_path):
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with out_p.open("w", encoding="utf-8") as fh:
        json.dump(report_data, fh, indent=2)
        fh.write("\\n")
"""

RUN_QUALITY_MODEL_SOURCE = """#!/usr/bin/env python3
\"\"\"Run data-quality and leakage audit on client data.\"\"\"

import json
import csv
from pathlib import Path
import sys
from quality_model import audit_dataset, make_validation_split, write_report

def main():
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
"""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    workspace = Path(argv[0]) if argv else Path.cwd()

    (workspace / "quality_model.py").write_text(QUALITY_MODEL_SOURCE, encoding="utf-8")
    (workspace / "run_quality_model.py").write_text(RUN_QUALITY_MODEL_SOURCE, encoding="utf-8")

    # Run the model logic to generate the output file
    config_path = workspace / "schema.json"
    csv_path = workspace / "client_data.csv"
    output_path = workspace / "outputs" / "model_audit.json"

    with config_path.open("r", encoding="utf-8") as fh:
        schema = json.load(fh)

    rows = []
    with csv_path.open("r", encoding="utf-8") as fh:
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

    namespace = {}
    exec(QUALITY_MODEL_SOURCE, namespace)

    excluded_columns = namespace["audit_dataset"](rows, schema)
    split_info = namespace["make_validation_split"](rows, schema)

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

    report = {
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
