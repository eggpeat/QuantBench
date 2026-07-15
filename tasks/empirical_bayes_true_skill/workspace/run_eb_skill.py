"""Run empirical Bayes shrinkage model on player skill data."""

import csv
import json
from pathlib import Path
from eb_skill import fit_beta_prior, rank_players


def main():
    workspace = Path.cwd()
    csv_path = workspace / "players.csv"
    output_path = workspace / "outputs" / "skill_rankings.json"

    rows = []
    with csv_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({
                "player_id": row["player_id"],
                "successes": int(row["successes"]),
                "attempts": int(row["attempts"])
            })

    # Fit the prior
    alpha0, beta0 = fit_beta_prior(rows)
    mean_prior = alpha0 / (alpha0 + beta0) if (alpha0 + beta0) > 0 else 0.0

    # Rank the players
    rankings = rank_players(rows)

    report = {
        "prior": {
            "alpha": round(alpha0, 6),
            "beta": round(beta0, 6),
            "mean": round(mean_prior, 6)
        },
        "rankings": rankings
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
