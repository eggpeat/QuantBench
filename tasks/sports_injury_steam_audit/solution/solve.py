#!/usr/bin/env python3
import sys
from pathlib import Path
import subprocess

IMPLEMENTATION = r'''from datetime import datetime


def parse_timestamp(ts):
    if not ts:
        return None
    # Support Z suffix correctly in all Python versions
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def audit_game(game: dict) -> dict:
    event_id = game["event_id"]
    opening_line = game["opening_line"]
    current_line = game["current_line"]
    model_fair_line = game["model_fair_line"]
    audit_ts = parse_timestamp(game["audit_timestamp"])
    news_ts = parse_timestamp(game.get("news_timestamp"))
    injury_status = game.get("injury_status", "none")
    model_relies = game.get("model_relies_on_injury_adjustment", False)
    line_moves = game.get("line_moves", [])

    # Calculate edge_points
    edge_points = round(model_fair_line - current_line, 2)

    # Helper: get active line at timestamp
    def get_active_line_at(ts):
        active_line = opening_line
        last_move_ts = None
        for move in line_moves:
            move_ts = parse_timestamp(move["timestamp"])
            if move_ts <= ts:
                if last_move_ts is None or move_ts >= last_move_ts:
                    active_line = move["line"]
                    last_move_ts = move_ts
        return active_line

    # Filter line moves up to audit_timestamp
    valid_moves = []
    for move in line_moves:
        move_ts = parse_timestamp(move["timestamp"])
        if move_ts <= audit_ts:
            valid_moves.append((move_ts, move["line"]))

    classification = "no_bet_no_edge"

    # 1. Check watch_fake_steam
    is_fake_steam = False
    if injury_status == "unconfirmed_rumor" and news_ts is not None:
        for t1, l1 in valid_moves:
            if t1 < news_ts and l1 != opening_line:
                for t2, l2 in valid_moves:
                    if news_ts < t2 <= audit_ts:
                        d1 = l1 - opening_line
                        d2 = l2 - l1
                        if d1 * d2 < 0:
                            is_fake_steam = True
                            break
                if is_fake_steam:
                    break

    if is_fake_steam:
        classification = "watch_fake_steam"
    else:
        line_at_injury = get_active_line_at(news_ts) if news_ts is not None else opening_line

        # 2. Check no_bet_double_count
        is_double_count = False
        if model_relies and injury_status == "confirmed_material" and news_ts is not None and news_ts <= audit_ts:
            for t_move, l_move in valid_moves:
                if news_ts < t_move <= audit_ts:
                    if l_move != line_at_injury:
                        is_double_count = True
                        break

        if is_double_count:
            classification = "no_bet_double_count"
        else:
            # 3. Check bet_stale_market
            is_stale_market = False
            if injury_status == "confirmed_material" and news_ts is not None and news_ts <= audit_ts:
                model_edge = abs(model_fair_line - current_line)
                if model_edge >= 1.5:
                    no_large_moves = True
                    for t_move, l_move in valid_moves:
                        if news_ts < t_move <= audit_ts:
                            if abs(l_move - line_at_injury) >= 1.0:
                                no_large_moves = False
                                break
                    if abs(current_line - line_at_injury) >= 1.0:
                        no_large_moves = False

                    if no_large_moves:
                        is_stale_market = True

            if is_stale_market:
                classification = "bet_stale_market"
            else:
                classification = "no_bet_no_edge"

    return {
        "event_id": event_id,
        "edge_points": edge_points,
        "classification": classification
    }


def audit_slate(games: list) -> list:
    return [audit_game(game) for game in games]
'''


def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    # Patch the implementation in injury_audit.py
    (workspace / "injury_audit.py").write_text(IMPLEMENTATION, encoding="utf-8")

    # Run the audit script
    run_script = workspace / "run_audit.py"
    subprocess.run([sys.executable, str(run_script)], check=True)


if __name__ == "__main__":
    main()
