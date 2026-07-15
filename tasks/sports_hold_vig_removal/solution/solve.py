#!/usr/bin/env python3
import json
import sys
from pathlib import Path

MODULE_SOURCE = r'''
import json
from pathlib import Path


def rounded(value, places=6):
    return round(float(value), places)


def american_to_decimal(odds):
    odds = int(odds)
    if odds == 0:
        raise ValueError("American odds cannot be zero")
    if odds > 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / abs(odds)


def implied_probability(odds):
    odds = int(odds)
    if odds == 0:
        raise ValueError("American odds cannot be zero")
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def analyze_market(market, bankroll, fractional_kelly, high_hold_threshold):
    raw_outcomes = market["outcomes"]
    implied = [implied_probability(outcome["american_odds"]) for outcome in raw_outcomes]
    sum_implied_raw = sum(implied)
    overround_raw = sum_implied_raw - 1.0
    hold_raw = 1.0 - 1.0 / sum_implied_raw
    high_hold = hold_raw >= high_hold_threshold

    outcomes = []
    for outcome, implied_prob in zip(raw_outcomes, implied):
        american = int(outcome["american_odds"])
        decimal = american_to_decimal(american)
        model_probability = float(outcome["model_probability"])
        b = decimal - 1.0
        ev = model_probability * b - (1.0 - model_probability)
        full_kelly = max(0.0, ev / b)
        stake = 0.0 if high_hold else bankroll * fractional_kelly * full_kelly
        rounded_stake = round(stake, 2)

        if high_hold:
            recommendation = "no_bet_high_hold"
        elif rounded_stake > 0.0:
            recommendation = "bet"
        else:
            recommendation = "no_bet"

        outcomes.append(
            {
                "name": outcome["name"],
                "american_odds": american,
                "decimal_odds": rounded(decimal),
                "implied_probability": rounded(implied_prob),
                "no_vig_probability": rounded(implied_prob / sum_implied_raw),
                "model_probability": rounded(model_probability),
                "ev_per_dollar": rounded(ev),
                "full_kelly": rounded(full_kelly),
                "recommended_stake": rounded_stake,
                "recommendation": recommendation,
            }
        )

    return {
        "market_id": market["market_id"],
        "sum_implied": rounded(sum_implied_raw),
        "overround": rounded(overround_raw),
        "hold": rounded(hold_raw),
        "high_hold": high_hold,
        "outcomes": outcomes,
    }


def build_report(data):
    bankroll = float(data["bankroll"])
    fractional_kelly = float(data["fractional_kelly"])
    high_hold_threshold = float(data["high_hold_threshold"])
    return {
        "bankroll": rounded(bankroll),
        "fractional_kelly": rounded(fractional_kelly),
        "markets": [
            analyze_market(market, bankroll, fractional_kelly, high_hold_threshold)
            for market in data["markets"]
        ],
    }


def main(workspace="."):
    workspace_path = Path(workspace)
    with (workspace_path / "markets.json").open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    report = build_report(data)
    output_dir = workspace_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "no_vig_kelly.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    return report


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else ".")
'''.lstrip()

RUN_SOURCE = r'''#!/usr/bin/env python3
import sys
from pathlib import Path
import no_vig_kelly


def main():
    workspace_path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent
    no_vig_kelly.main(workspace_path)


if __name__ == "__main__":
    main()
'''.lstrip()


def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    (workspace / "no_vig_kelly.py").write_text(MODULE_SOURCE, encoding="utf-8")
    (workspace / "run_no_vig_kelly.py").write_text(RUN_SOURCE, encoding="utf-8")
    sys.path.insert(0, str(workspace))
    import no_vig_kelly

    no_vig_kelly.main(str(workspace))


if __name__ == "__main__":
    main()
