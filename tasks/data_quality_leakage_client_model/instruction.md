# Data Quality & Leakage Audit for Client Modeling

Implement the functions inside the starter module `quality_model.py` to audit client datasets for data quality issues and target leakage, and construct a clean temporal validation split.

## Background & Tasks

In real-world data science, training on raw, unprocessed client data can lead to overly optimistic performance during validation due to data quality issues, label leakage, and target contamination.

You need to implement the following functions in `quality_model.py`:
1. `audit_dataset(rows, schema)`
2. `make_validation_split(rows, schema)`
3. `write_report(report_data, output_path)`

These functions are invoked by `run_quality_model.py` which reads `client_data.csv` and `schema.json`, audits the dataset, and outputs `outputs/model_audit.json`.

---

## Specification

### 1. Data Quality Checks & Row-Level Exclusions
Before splitting the dataset, we must detect and exclude rows that fail critical data quality checks. These checks use the attributes defined in `schema.json`:
- **Duplicate IDs**: Any row whose primary key (specified in `schema.json` as `primary_key`, which is `row_id` in this dataset) is duplicated (appears more than once) in the dataset. Count the number of unique primary key values that are duplicated. All rows sharing these duplicate IDs must be excluded.
- **Unstable Entity IDs**: Any entity ID (specified in `schema.json` as `entity_id`, which is `client_id` in this dataset) that is associated with more than one unique, non-missing value in any stable attribute column (defined in `schema.json` as `stable_attributes`, which is `["signup_date"]` here). Count the number of unique entity IDs that are unstable. All rows associated with these unstable entity IDs must be excluded.
- **Future Timestamps**: Any row with a timestamp (specified in `schema.json` as `timestamp`) strictly greater than the cutoff time (defined in `schema.json` as `cutoff_time`). Count the number of rows with future timestamps. All rows with future timestamps must be excluded.

### 2. Feature-Level Auditing & Exclusions
We must audit the feature/target columns (columns that are not the metadata columns: primary key, entity ID, or timestamp) and exclude them from training/validation if they represent a source of leakage, target contamination, or have high missingness:
- **Label Leakage**: A feature has label leakage if:
  - Its Pearson correlation with the target is exactly `1.0` or `-1.0` (computed over non-missing numeric values).
  - Or it exhibits "conditional presence leakage": the feature is non-missing only when the target is 1 (or only when the target is 0) while the overall target has variance (is not constant).
  - Or it exhibits "future lookahead leakage": when sorted chronologically for each entity ID, the feature's value at row $k$ is equal to the value of some other column at row $k+1$ for all steps where the timestamp strictly increases.
  Exclude these features under the `"leakage"` category.
- **Target Contamination**: A feature is contaminated if its value is constant per entity ID and represents a summary statistic (sum or mean) of another column (like `transaction_amount` or the target) over the entity's entire history (both past and future), and its value in the earliest chronological row differs from the reference column in that earliest row (to show it incorporates future information). Or if the column is explicitly defined in `schema.json` as a target contamination candidate.
  Exclude these features under the `"target_contamination"` category.
- **High Missingness**: Any feature column where more than 50% of the rows are missing (value is `None`, empty string `""`, `"nan"`, `"NaN"`, or `"null"`).
  Exclude these features under the `"high_missingness"` category.

*Note: Exclusions precedence is Leakage > Target Contamination > High Missingness. A column matching multiple criteria is categorized under the first one it meets in this order.*

### 3. Temporal Validation Split
After removing the rows that fail row-level exclusions (duplicate record IDs, unstable entity IDs, and future timestamps), split the remaining clean rows temporally:
- **Train Set**: Rows with a timestamp strictly less than `train_validation_cutoff` (from `schema.json`).
- **Validation Set**: Rows with a timestamp greater than or equal to `train_validation_cutoff`.

### 4. Output Report
`write_report(report_data, output_path)` must save a JSON report of the following structure to `outputs/model_audit.json`:
```json
{
  "excluded_columns": {
    "leakage": ["col1", ...],
    "target_contamination": ["col2", ...],
    "high_missingness": ["col3", ...]
  },
  "validation_split": {
    "train_ids": ["r1", ...],
    "validation_ids": ["r4", ...]
  },
  "quality_metrics": {
    "duplicate_ids_count": 0,
    "unstable_ids_count": 0,
    "future_timestamps_count": 0,
    "label_leakage_detected": true
  },
  "metric_sanity": {
    "train_size": 4,
    "validation_size": 1,
    "leakage_ratio_removed": 0.5
  }
}
```
All list fields in the JSON must be sorted alphabetically.
