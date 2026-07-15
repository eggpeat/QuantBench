def american_to_decimal(odds):
    """
    Convert American odds to decimal odds.
    - positive odds: 1 + odds / 100
    - negative odds: 1 + 100 / abs(odds)
    """
    # TODO: Implement american odds conversion
    pass


def evaluate_ticket(ticket):
    """
    Evaluate parlay risk metrics for a single ticket.

    The ticket dictionary has the following structure:
    {
      "ticket_id": "ticket_1",
      "stake": 100.0,
      "legs": [
        {"leg_id": "leg_1", "american_odds": -110, "true_win_prob": 0.5},
        ...
      ],
      "offered_payout": 600.0 (optional)
    }

    Returns a dictionary of calculated metrics rounded to 6 decimal places:
    {
      "ticket_id": "ticket_1",
      "true_rollover_decimal": float,
      "offered_decimal": float,
      "short_pay_margin": float,
      "expected_synthetic_handle": float,
      "expected_return": float,
      "hold_on_stake": float,
      "hold_on_synthetic_handle": float
    }
    """
    # TODO: Implement ticket metrics evaluation
    pass


def evaluate_tickets(tickets):
    """
    Evaluate a list of tickets and return a dictionary ready for JSON output:
    {
      "tickets": [
         { ... },
         ...
      ]
    }
    """
    # TODO: Implement list-wise evaluation
    pass


def main(workspace_path=None):
    """
    Main entry point. Loads tickets.json from the workspace,
    evaluates them, and writes the results to outputs/parlay_risk.json.
    """
    # TODO: Implement loading, evaluation, and saving
    pass
