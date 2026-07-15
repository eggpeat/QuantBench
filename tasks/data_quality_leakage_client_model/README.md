# Data Quality & Leakage Audit for Client Modeling

## Overview

This Quant Bench task asks the agent to implement a data quality and leakage detection pipeline to audit client datasets for model training suitability. The pipeline detects duplicate record IDs, unstable entity IDs, future timestamps, high missingness, target contamination, and label leakage. It produces a clean temporal split and outputs a standardized JSON report detailing the exclusions and split statistics.

## Source Grounding & Provenance
 - **Source**: *Data Science Projects with Python* by Stephen Klosterman (Chapter 1, Section 1.5, and Chapter 5, Section 5.3).
 - **Task Behavior vs. Source**:
  - Klosterman describes data leakage and temporal splitting in the context of machine learning model building.
  - This task codifies these principles into a strict programmatic audit script, enforcing specific heuristics for target contamination, lookahead leakage, stable attributes, and duplicate IDs, resolving common real-world data issues in standard Python.

## What It Tests
The task checks whether the agent can correctly implement data auditing logic using Python's standard library:
- Column exclusions (precedence: Leakage > Target Contamination > High Missingness).
- Specific leakage checks (Pearson correlation, conditional presence, and sequence lookahead).
- Target contamination (client-level aggregation lookaheads).
- Row exclusions (duplicate primary keys, unstable stable attributes per entity, and future timestamps).
- Correct temporal train/validation split.

## Environment
Python 3.13 workspace using only standard library modules.

## Inputs
- `client_data.csv`: A client record dataset with various fields, duplicates, and leakage sources.
- `schema.json`: Metadata configuration defining schema keys, targets, stable attributes, and cutoffs.
- `quality_model.py`: Starter implementation module.
- `run_quality_model.py`: Execute wrapper that loads data, calls audit functions, and writes the report.

## Required Outputs
Create `outputs/model_audit.json` with keys `excluded_columns`, `validation_split`, `quality_metrics`, and `metric_sanity`.

## Verification
Pytest-compatible tests run assertions comparing the generated output with `tests/expected.json`, and run unit/edge tests on the candidate module.
