#!/usr/bin/env python3
"""Reference solution for the empirical Bayes true skill task."""

import csv
import json
import math
import sys
from pathlib import Path

EB_SKILL_SOURCE = '''"""Empirical Bayes Beta-Binomial Player Skill Estimation."""
import math


def fit_beta_prior(rows, min_attempts=10):
    """Estimate the global prior parameters alpha0 and beta0 from the rows using the Method of Moments.

    To avoid noisy, low-volume players distorting the prior estimation,
    this function should filter the data to players with at least 10 attempts (attempts >= 10).
    If fewer than 2 players remain, fall back to players with attempts > 0.
    If still fewer than 2 players remain, return (1.0, 1.0).

    Args:
        rows (list of dict): List of player dictionaries with keys 'successes' and 'attempts'.
        min_attempts (int): Minimum number of attempts for a player to be included in the prior fitting.

    Returns:
        tuple of (float, float): The fitted (alpha0, beta0) parameters.
    """
    valid_rows = [r for r in rows if r["attempts"] >= min_attempts]
    if len(valid_rows) < 2:
        valid_rows = [r for r in rows if r["attempts"] > 0]
    if len(valid_rows) < 2:
        return 1.0, 1.0

    rates = [r["successes"] / r["attempts"] for r in valid_rows]
    n_players = len(rates)

    mean_rate = sum(rates) / n_players
    if mean_rate <= 0.0 or mean_rate >= 1.0:
        return 1.0, 1.0

    var_rate = sum((x - mean_rate) ** 2 for x in rates) / (n_players - 1)

    if var_rate <= 0.0 or var_rate >= mean_rate * (1.0 - mean_rate):
        K = 10.0
        return mean_rate * K, (1.0 - mean_rate) * K

    S = mean_rate * (1.0 - mean_rate) / var_rate - 1.0
    alpha = mean_rate * S
    beta = (1.0 - mean_rate) * S
    return alpha, beta


def posterior_summary(row, alpha0, beta0):
    """Compute posterior statistics for a single player.

    This includes calculating raw rates, posterior parameters, posterior means,
    and the 95% credible interval using the Normal approximation to the Beta distribution.

    Args:
        row (dict): A player dictionary with keys 'player_id', 'successes', and 'attempts'.
        alpha0 (float): Prior alpha parameter.
        beta0 (float): Prior beta parameter.

    Returns:
        dict: Summary containing player info, raw statistics, posterior alpha/beta,
              posterior mean, and credible interval bounds. All floating-point fields
              must be rounded to exactly 6 decimal places.
    """
    player_id = row["player_id"]
    successes = int(row["successes"])
    attempts = int(row["attempts"])

    if successes < 0 or attempts < 0:
        raise ValueError("successes and attempts must be non-negative")
    if successes > attempts:
        raise ValueError("successes cannot exceed attempts")

    raw_rate = successes / attempts if attempts > 0 else 0.0

    post_alpha = successes + alpha0
    post_beta = (attempts - successes) + beta0
    post_mean = post_alpha / (post_alpha + post_beta)

    post_var = (post_alpha * post_beta) / ((post_alpha + post_beta)**2 * (post_alpha + post_beta + 1))
    post_sd = math.sqrt(post_var)

    ci_low = max(0.0, post_mean - 1.96 * post_sd)
    ci_high = min(1.0, post_mean + 1.96 * post_sd)

    return {
        "player_id": player_id,
        "successes": successes,
        "attempts": attempts,
        "raw_rate": round(raw_rate, 6),
        "posterior_alpha": round(post_alpha, 6),
        "posterior_beta": round(post_beta, 6),
        "posterior_mean": round(post_mean, 6),
        "credible_interval_low": round(ci_low, 6),
        "credible_interval_high": round(ci_high, 6),
    }


def rank_players(rows):
    """Fit the prior from the raw rows, compute posterior summaries, and rank all players.

    Sorts the players in descending order of posterior_mean, assigning a 1-based rank.

    Args:
        rows (list of dict): List of player dictionaries.

    Returns:
        list of dict: List of ranked player dictionaries.
    """
    alpha0, beta0 = fit_beta_prior(rows)
    summaries = []
    for r in rows:
        summaries.append(posterior_summary(r, alpha0, beta0))
    summaries.sort(key=lambda x: x["posterior_mean"], reverse=True)
    for rank, summary in enumerate(summaries, 1):
        summary["rank"] = rank
    return summaries
'''

RUN_EB_SKILL_SOURCE = '''"""Run empirical Bayes shrinkage model on player skill data."""

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
        fh.write("\\n")


if __name__ == "__main__":
    main()
'''


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    workspace = Path(argv[0]) if argv else Path.cwd()

    (workspace / "eb_skill.py").write_text(EB_SKILL_SOURCE, encoding="utf-8")
    (workspace / "run_eb_skill.py").write_text(RUN_EB_SKILL_SOURCE, encoding="utf-8")

    # Run the model logic to generate the output file
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

    # Execute dynamic module definition code to run it
    namespace = {}
    exec(EB_SKILL_SOURCE, namespace)

    alpha0, beta0 = namespace["fit_beta_prior"](rows)
    mean_prior = alpha0 / (alpha0 + beta0) if (alpha0 + beta0) > 0 else 0.0
    rankings = namespace["rank_players"](rows)

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
