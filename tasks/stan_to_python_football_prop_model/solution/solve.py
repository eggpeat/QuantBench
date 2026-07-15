#!/usr/bin/env python3
import sys
import os
from pathlib import Path

MODULE_SOURCE = r'''# football_prop_model.py
# Reference implementation of Football Passing TD Prop Poisson GLM Model.
# Fits Poisson GLM using IRLS in pure Python, computes Poisson tail, and analyzes props.

import math
import csv
import json
from pathlib import Path


def solve_linear_system(A, b):
    n = len(A)
    M = [A[i][:] for i in range(n)]
    y_vec = b[:]
    for i in range(n):
        max_row = i
        for r in range(i + 1, n):
            if abs(M[r][i]) > abs(M[max_row][i]):
                max_row = r
        if abs(M[max_row][i]) < 1e-12:
            raise ValueError("Matrix is singular or near-singular")
        M[i], M[max_row] = M[max_row], M[i]
        y_vec[i], y_vec[max_row] = y_vec[max_row], y_vec[i]

        pivot = M[i][i]
        for j in range(i, n):
            M[i][j] /= pivot
        y_vec[i] /= pivot

        for r in range(n):
            if r != i:
                factor = M[r][i]
                for j in range(i, n):
                    M[r][j] -= factor * M[i][j]
                y_vec[r] -= factor * y_vec[i]
    return y_vec


def fit_poisson_model(rows):
    """
    Fits a Poisson GLM to historical passing touchdowns data using Iteratively
    Reweighted Least Squares (IRLS).
    """
    X = []
    y = []
    for row in rows:
        X.append([
            1.0,
            float(row["passer_rating"]),
            float(row["opp_defense_rating"]),
            float(row["is_home"])
        ])
        y.append(int(row["passing_tds"]))

    K = 4
    N = len(X)
    beta = [0.0, 0.0, 0.0, 0.0]

    for iteration in range(100):
        lambdas = []
        for i in range(N):
            lin_pred = sum(X[i][j] * beta[j] for j in range(K))
            lin_pred = max(-20.0, min(20.0, lin_pred))
            lambdas.append(math.exp(lin_pred))

        I = [[0.0]*K for _ in range(K)]
        for j in range(K):
            for k in range(K):
                I[j][k] = sum(X[i][j] * X[i][k] * lambdas[i] for i in range(N))

        g = [0.0]*K
        for j in range(K):
            g[j] = sum(X[i][j] * (y[i] - lambdas[i]) for i in range(N))

        try:
            d = solve_linear_system(I, g)
        except ValueError:
            break

        beta = [beta[j] + d[j] for j in range(K)]
        diff = sum(abs(x) for x in d)
        if diff < 1e-9:
            break

    return {
        "intercept": beta[0],
        "passer_rating": beta[1],
        "opp_defense_rating": beta[2],
        "is_home": beta[3]
    }


def predict_lambda(coeffs, row):
    """
    Predicts the lambda (expected touchdowns) parameter for a single player match-up.
    """
    lin_pred = (
        coeffs["intercept"] +
        coeffs["passer_rating"] * float(row["passer_rating"]) +
        coeffs["opp_defense_rating"] * float(row["opp_defense_rating"]) +
        coeffs["is_home"] * float(row["is_home"])
    )
    return math.exp(lin_pred)


def poisson_tail(lambda_value, threshold):
    """
    Calculates the probability of a Poisson random variable strictly exceeding a threshold.
    """
    limit = int(math.floor(threshold))
    if limit < 0:
        return 1.0
    prob_le = 0.0
    term = math.exp(-lambda_value)
    prob_le += term
    for k in range(1, limit + 1):
        term = term * lambda_value / k
        prob_le += term
    return 1.0 - prob_le


def american_to_implied(odds):
    if odds > 0:
        return 100.0 / (odds + 100.0)
    else:
        return abs(odds) / (abs(odds) + 100.0)


def prob_to_american(p):
    if p <= 0.0 or p >= 1.0:
        return 0
    if p >= 0.5:
        return int(round(-100 * p / (1 - p)))
    else:
        return int(round(100 * (1 - p) / p))


def analyze_props(data_csv, props_csv):
    """
    Reads training data, fits the Poisson GLM, analyzes props, and saves opinions.
    """
    # 1. Load training data
    rows = []
    with open(data_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "passer_rating": float(r["passer_rating"]),
                "opp_defense_rating": float(r["opp_defense_rating"]),
                "is_home": int(r["is_home"]),
                "passing_tds": int(r["passing_tds"])
            })

    # Fit model
    coeffs = fit_poisson_model(rows)

    # 2. Load props
    props = []
    with open(props_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            props.append({
                "prop_id": r["prop_id"],
                "passer": r["passer"],
                "opponent": r["opponent"],
                "is_home": int(r["is_home"]),
                "passer_rating": float(r["passer_rating"]),
                "opp_defense_rating": float(r["opp_defense_rating"]),
                "line": float(r["line"]),
                "over_odds": int(r["over_odds"]),
                "under_odds": int(r["under_odds"])
            })

    prop_opinions = []
    for prop in props:
        lam = predict_lambda(coeffs, prop)
        prob_over = poisson_tail(lam, prop["line"])
        prob_under = 1.0 - prob_over

        be_over = american_to_implied(prop["over_odds"])
        be_under = american_to_implied(prop["under_odds"])

        fair_over = prob_to_american(prob_over)
        fair_under = prob_to_american(prob_under)

        edge_over = prob_over - be_over
        edge_under = prob_under - be_under

        opinion = "NO_BET"
        if edge_over > 0:
            opinion = "OVER"
        elif edge_under > 0:
            opinion = "UNDER"

        prop_opinions.append({
            "prop_id": prop["prop_id"],
            "passer": prop["passer"],
            "opponent": prop["opponent"],
            "line": prop["line"],
            "lambda": round(lam, 6),
            "model_prob_over": round(prob_over, 6),
            "model_prob_under": round(prob_under, 6),
            "market_be_over": round(be_over, 6),
            "market_be_under": round(be_under, 6),
            "fair_odds_over": fair_over,
            "fair_odds_under": fair_under,
            "edge_over": round(edge_over, 6),
            "edge_under": round(edge_under, 6),
            "opinion": opinion
        })

    res = {
        "coefficients": {
            "intercept": round(coeffs["intercept"], 6),
            "passer_rating": round(coeffs["passer_rating"], 6),
            "opp_defense_rating": round(coeffs["opp_defense_rating"], 6),
            "is_home": round(coeffs["is_home"], 6)
        },
        "prop_opinions": prop_opinions
    }

    output_path = Path(props_csv).parent.parent / "outputs" / "prop_opinions.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
'''.lstrip()

RUN_SOURCE = r'''#!/usr/bin/env python3
import sys
from pathlib import Path

# Add current workspace to path
sys.path.insert(0, str(Path(__file__).parent))
import football_prop_model


def main():
    workspace_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent

    data_csv = workspace_dir / "data" / "passing_tds.csv"
    props_csv = workspace_dir / "data" / "prop_bets.csv"

    # Ensure outputs directory exists
    outputs_dir = workspace_dir / "outputs"
    outputs_dir.mkdir(exist_ok=True)

    print(f"Running prop analysis in workspace: {workspace_dir}")
    football_prop_model.analyze_props(str(data_csv), str(props_csv))
    print("Done!")


if __name__ == "__main__":
    main()
'''.lstrip()


def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    (workspace / "football_prop_model.py").write_text(MODULE_SOURCE, encoding="utf-8")
    (workspace / "run_model.py").write_text(RUN_SOURCE, encoding="utf-8")

    # Execute the solution
    sys.path.insert(0, str(workspace))
    import football_prop_model

    data_csv = workspace / "data" / "passing_tds.csv"
    props_csv = workspace / "data" / "prop_bets.csv"
    football_prop_model.analyze_props(str(data_csv), str(props_csv))


if __name__ == "__main__":
    main()
