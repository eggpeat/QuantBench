"""Run empirical Bayes shrinkage model on ad click data."""

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
        fh.write("\n")


if __name__ == "__main__":
    main()
