#!/usr/bin/env python3
import json
import sys
from pathlib import Path

MODULE_SOURCE = r'''
import json
from pathlib import Path

def american_to_decimal(odds):
    if odds >= 100:
        return 1.0 + odds / 100.0
    elif odds <= -100:
        return 1.0 + 100.0 / abs(odds)
    else:
        raise ValueError("Invalid American odds")

def evaluate_ticket(ticket):
    stake = float(ticket["stake"])
    legs = ticket["legs"]
    offered_payout = ticket.get("offered_payout")

    decimals = [american_to_decimal(l["american_odds"]) for l in legs]
    probs = [float(l["true_win_prob"]) for l in legs]

    true_rollover_decimal = 1.0
    for d in decimals:
        true_rollover_decimal *= d

    if offered_payout is not None:
        offered_decimal = float(offered_payout) / stake
    else:
        offered_decimal = true_rollover_decimal

    short_pay_margin = 1.0 - (offered_decimal / true_rollover_decimal)

    # expected_synthetic_handle
    N = len(legs)
    handle_sum = 0.0
    for k in range(N):
        prod = 1.0
        for i in range(k):
            prod *= decimals[i] * probs[i]
        handle_sum += prod
    expected_synthetic_handle = stake * handle_sum

    # expected_return
    prob_product = 1.0
    for p in probs:
        prob_product *= p
    expected_return = stake * offered_decimal * prob_product

    # hold_on_stake
    hold_on_stake = 1.0 - offered_decimal * prob_product

    # hold_on_synthetic_handle
    hold_on_synthetic_handle = (stake - expected_return) / expected_synthetic_handle

    return {
        "ticket_id": ticket["ticket_id"],
        "true_rollover_decimal": round(true_rollover_decimal, 6),
        "offered_decimal": round(offered_decimal, 6),
        "short_pay_margin": round(short_pay_margin, 6),
        "expected_synthetic_handle": round(expected_synthetic_handle, 6),
        "expected_return": round(expected_return, 6),
        "hold_on_stake": round(hold_on_stake, 6),
        "hold_on_synthetic_handle": round(hold_on_synthetic_handle, 6)
    }

def evaluate_tickets(tickets):
    return {
        "tickets": [evaluate_ticket(t) for t in tickets]
    }

def main(workspace_path=None):
    workspace = Path(workspace_path) if workspace_path else Path.cwd()
    tickets_file = workspace / "tickets.json"

    with open(tickets_file, "r", encoding="utf-8") as f:
        tickets = json.load(f)

    results = evaluate_tickets(tickets)

    outputs_dir = workspace / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    output_file = outputs_dir / "parlay_risk.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
'''.lstrip()

RUN_SOURCE = r'''#!/usr/bin/env python3
import sys
from pathlib import Path
import parlay_risk


def main():
    workspace_path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent
    parlay_risk.main(workspace_path)


if __name__ == "__main__":
    main()
'''.lstrip()


def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    (workspace / "parlay_risk.py").write_text(MODULE_SOURCE, encoding="utf-8")
    (workspace / "run_parlay_risk.py").write_text(RUN_SOURCE, encoding="utf-8")
    sys.path.insert(0, str(workspace))
    import parlay_risk

    parlay_risk.main(str(workspace))


if __name__ == "__main__":
    main()
