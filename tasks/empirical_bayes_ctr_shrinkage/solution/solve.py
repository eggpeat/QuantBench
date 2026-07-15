#!/usr/bin/env python3
"""Reference solution for the empirical Bayes CTR shrinkage task."""

import csv
import json
import sys
from pathlib import Path

CTR_SHRINKAGE_SOURCE = '''"""Empirical Bayes Beta-Binomial CTR Shrinkage helpers."""


def fit_global_prior(rows, prior_strength):
    """Estimate the global prior parameters from all ad clicks and impressions."""
    total_clicks = 0
    total_impressions = 0
    for row in rows:
        impressions = int(row["impressions"])
        clicks = int(row["clicks"])
        if impressions < 0 or clicks < 0:
            raise ValueError("impressions and clicks must be non-negative")
        if clicks > impressions:
            raise ValueError("clicks cannot exceed impressions")
        total_clicks += clicks
        total_impressions += impressions

    if total_impressions == 0:
        global_ctr = 0.0
    else:
        global_ctr = total_clicks / total_impressions

    alpha0 = round(global_ctr * prior_strength, 6)
    beta0 = round((1.0 - global_ctr) * prior_strength, 6)
    return round(global_ctr, 6), alpha0, beta0


def posterior_summary(row, alpha0, beta0):
    """Compute the posterior statistics for a single ad."""
    impressions = int(row["impressions"])
    clicks = int(row["clicks"])
    if impressions < 0 or clicks < 0:
        raise ValueError("impressions and clicks must be non-negative")
    if clicks > impressions:
        raise ValueError("clicks cannot exceed impressions")

    prior_strength = alpha0 + beta0
    raw_ctr = clicks / impressions if impressions > 0 else 0.0
    posterior_alpha = clicks + alpha0
    posterior_beta = (impressions - clicks) + beta0

    if impressions + prior_strength == 0:
        posterior_mean = 0.0
    else:
        posterior_mean = (clicks + alpha0) / (impressions + prior_strength)

    return {
        "ad_id": row["ad_id"],
        "impressions": impressions,
        "clicks": clicks,
        "raw_ctr": round(raw_ctr, 6),
        "posterior_alpha": round(posterior_alpha, 6),
        "posterior_beta": round(posterior_beta, 6),
        "posterior_mean": round(posterior_mean, 6)
    }


def rank_ads(rows, prior_strength):
    """Compute posterior summaries for all ads and sort them by posterior mean in descending order."""
    global_ctr, alpha0, beta0 = fit_global_prior(rows, prior_strength)
    summaries = []
    for row in rows:
        summaries.append(posterior_summary(row, alpha0, beta0))
    summaries.sort(key=lambda x: x["posterior_mean"], reverse=True)
    return summaries
'''

RUN_CTR_SOURCE = '''"""Run empirical Bayes shrinkage model on ad click data."""

import csv
import json
from pathlib import Path
from ctr_shrinkage import fit_global_prior, rank_ads


def main():
    workspace = Path.cwd()
    config_path = workspace / "config.json"
    csv_path = workspace / "ad_clicks.csv"
    output_path = workspace / "outputs" / "ctr_report.json"

    with config_path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    prior_strength = float(config["prior_strength"])
    top_k = int(config["top_k"])

    rows = []
    with csv_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({
                "ad_id": row["ad_id"],
                "impressions": int(row["impressions"]),
                "clicks": int(row["clicks"])
            })

    global_ctr, alpha0, beta0 = fit_global_prior(rows, prior_strength)
    ranking = rank_ads(rows, prior_strength)

    # Slice to top_k
    ranking_top_k = ranking[:top_k]

    report = {
        "prior": {
            "global_ctr": round(global_ctr, 6),
            "prior_strength": round(prior_strength, 6),
            "alpha0": round(alpha0, 6),
            "beta0": round(beta0, 6)
        },
        "ranking": ranking_top_k
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\\n")


if __name__ == "__main__":
    main()
'''


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    workspace = Path(argv[0]) if argv else Path.cwd()

    (workspace / "ctr_shrinkage.py").write_text(CTR_SHRINKAGE_SOURCE, encoding="utf-8")
    (workspace / "run_ctr.py").write_text(RUN_CTR_SOURCE, encoding="utf-8")

    # Run the model logic to generate the output file
    config_path = workspace / "config.json"
    csv_path = workspace / "ad_clicks.csv"
    output_path = workspace / "outputs" / "ctr_report.json"

    with config_path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    prior_strength = float(config["prior_strength"])
    top_k = int(config["top_k"])

    rows = []
    with csv_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({
                "ad_id": row["ad_id"],
                "impressions": int(row["impressions"]),
                "clicks": int(row["clicks"])
            })

    # Execute dynamic module definition code to run it
    namespace = {}
    exec(CTR_SHRINKAGE_SOURCE, namespace)

    global_ctr, alpha0, beta0 = namespace["fit_global_prior"](rows, prior_strength)
    ranking = namespace["rank_ads"](rows, prior_strength)
    ranking_top_k = ranking[:top_k]

    report = {
        "prior": {
            "global_ctr": round(global_ctr, 6),
            "prior_strength": round(prior_strength, 6),
            "alpha0": round(alpha0, 6),
            "beta0": round(beta0, 6)
        },
        "ranking": ranking_top_k
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
