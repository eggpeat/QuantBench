#!/usr/bin/env python3
import sqlite3
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

def build_deterministic_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.executescript("""
    DROP TABLE IF EXISTS matches;
    DROP TABLE IF EXISTS odds;
    DROP TABLE IF EXISTS predictions;

    CREATE TABLE matches (
        game_id INTEGER PRIMARY KEY,
        sport TEXT,
        kickoff_time TEXT,
        home_team TEXT,
        away_team TEXT,
        home_score INTEGER,
        away_score INTEGER
    );

    CREATE TABLE odds (
        odds_id INTEGER PRIMARY KEY,
        game_id INTEGER,
        bookmaker TEXT,
        odds_value REAL,
        recorded_at TEXT
    );

    CREATE TABLE predictions (
        prediction_id INTEGER PRIMARY KEY,
        game_id INTEGER,
        model_name TEXT,
        pred_value REAL,
        generated_at TEXT
    );
    """)

    random.seed(42)
    start_date = datetime(2024, 1, 1, 12, 0, 0)

    # 1500 matches
    sports = ['soccer', 'basketball', 'tennis', 'hockey']
    matches_data = []
    for g_id in range(1, 1501):
        sport = sports[g_id % len(sports)]
        kickoff = start_date + timedelta(minutes=g_id * 357) # spread across the year
        kickoff_str = kickoff.strftime("%Y-%m-%d %H:%M:%S")
        matches_data.append((
            g_id,
            sport,
            kickoff_str,
            f"Home_{g_id}",
            f"Away_{g_id}",
            random.randint(0, 5),
            random.randint(0, 5)
        ))
    cursor.executemany("INSERT INTO matches VALUES (?,?,?,?,?,?,?)", matches_data)

    # Generate odds
    odds_data = []
    odds_id = 1
    for g_id in range(1, 1501):
        kickoff_str = matches_data[g_id-1][2]
        kickoff = datetime.strptime(kickoff_str, "%Y-%m-%d %H:%M:%S")
        for bookmaker in ['BookieA', 'BookieB', 'BookieC']:
            # Generate 3 odds updates for each game
            for hours_before in [8, 4, 1]:
                recorded = kickoff - timedelta(hours=hours_before)
                odds_val = round(1.5 + (g_id % 7) * 0.4 + (hours_before * 0.05) + random.uniform(-0.1, 0.1), 2)
                odds_data.append((
                    odds_id,
                    g_id,
                    bookmaker,
                    odds_val,
                    recorded.strftime("%Y-%m-%d %H:%M:%S")
                ))
                odds_id += 1
    cursor.executemany("INSERT INTO odds VALUES (?,?,?,?,?)", odds_data)

    # Generate predictions
    predictions_data = []
    pred_id = 1
    for g_id in range(1, 1501):
        kickoff_str = matches_data[g_id-1][2]
        kickoff = datetime.strptime(kickoff_str, "%Y-%m-%d %H:%M:%S")
        for model in ['AlphaModel', 'BetaModel']:
            # Generate 2 prediction updates
            for hours_before in [10, 5]:
                generated = kickoff - timedelta(hours=hours_before)
                pred_val = round(0.3 + ((g_id + hours_before) % 5) * 0.1 + random.uniform(-0.02, 0.02), 3)
                predictions_data.append((
                    pred_id,
                    g_id,
                    model,
                    pred_val,
                    generated.strftime("%Y-%m-%d %H:%M:%S")
                ))
                pred_id += 1
    cursor.executemany("INSERT INTO predictions VALUES (?,?,?,?,?)", predictions_data)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    db_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "backtest.db"
    build_deterministic_db(db_file)
