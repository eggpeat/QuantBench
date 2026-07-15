import importlib
import json
import os
import sys
import sqlite3
import hashlib
from pathlib import Path
import shutil

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")
PRISTINE_DB = Path(__file__).with_name("fixtures") / "odds_tx100.db"

def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)

def import_candidate_module():
    sys.path.insert(0, str(WORKSPACE))
    try:
        return importlib.import_module("recover")
    finally:
        try:
            sys.path.remove(str(WORKSPACE))
        except ValueError:
            pass

_run_once = False

def run_candidate():
    global _run_once
    if _run_once:
        return

    shutil.copy2(PRISTINE_DB, WORKSPACE / "odds.db")
    output_path = WORKSPACE / "outputs" / "recovered_ticks.json"
    output_path.parent.mkdir(exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    import runpy
    old_cwd = os.getcwd()
    old_argv = sys.argv
    try:
        os.chdir(str(WORKSPACE))
        sys.argv = [str(WORKSPACE / "run_recovery.py"), str(WORKSPACE)]
        runpy.run_path(str(WORKSPACE / "run_recovery.py"), run_name="__main__")
    except SystemExit:
        # Candidate-controlled wrappers must not be able to terminate the verifier.
        pass
    except Exception:
        pass
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    if not output_path.exists():
        try:
            result = import_candidate_module().recover_database(WORKSPACE)
            if not output_path.exists():
                with output_path.open("w", encoding="utf-8") as handle:
                    json.dump(result, handle, indent=2)
        except Exception:
            pass

    _run_once = True


def test_public_fixture_output_matches_expected_snapshot():
    run_candidate()
    output_path = WORKSPACE / "outputs" / "recovered_ticks.json"
    assert output_path.exists(), "missing outputs/recovered_ticks.json"

    actual = load_json(output_path)
    expected = load_json(EXPECTED_PATH)
    assert actual == expected

def test_recovery_on_already_recovered_db(tmp_path):
    shutil.copy(WORKSPACE / "odds.db", tmp_path / "odds.db")
    shutil.copy(WORKSPACE / "odds_transactions.jsonl", tmp_path / "odds_transactions.jsonl")

    mod = import_candidate_module()
    mod.recover_database(tmp_path)
    result = mod.recover_database(tmp_path)
    # It should not apply any new transactions since they are already applied (last_applied_tx_id is 104)
    assert result["initial_tx_id"] == 104
    assert result["final_tx_id"] == 104
    assert result["applied_transactions"] == []
    assert result["ticks_inserted"] == 0
    assert result["corruption_encountered"] is True  # because tx 105 is still in WAL and corrupted

def test_recovery_with_no_corruption(tmp_path):
    # Create a fresh database up to tx 100
    db_path = tmp_path / "odds.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE markets (market_id TEXT PRIMARY KEY, home_team TEXT, away_team TEXT, sport TEXT);")
    c.execute("CREATE TABLE ticks_log (tick_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, sportsbook TEXT, market_id TEXT, outcome TEXT, price REAL, tx_id INTEGER);")
    c.execute("CREATE TABLE live_odds (market_id TEXT, outcome TEXT, sportsbook TEXT, price REAL, last_updated TEXT, tx_id INTEGER, PRIMARY KEY (market_id, outcome, sportsbook));")
    c.execute("CREATE TABLE applied_transactions (tx_id INTEGER PRIMARY KEY, tx_hash TEXT);")
    c.execute("CREATE TABLE recovery_metadata (name TEXT PRIMARY KEY, value TEXT);")

    c.execute("INSERT INTO recovery_metadata (name, value) VALUES ('last_applied_tx_id', '100');")
    c.execute("INSERT INTO applied_transactions (tx_id, tx_hash) VALUES (100, '04d3183cc211fb146e64eebb38086ded5044b1001970b039129977a03702531b');")
    conn.commit()
    conn.close()

    # Write a WAL with 101, 102 and a valid 103 (no corruption)
    wal_path = tmp_path / "odds_transactions.jsonl"
    wal_lines = [
        {"type": "START", "tx_id": 101, "prev_hash": "04d3183cc211fb146e64eebb38086ded5044b1001970b039129977a03702531b"},
        {"type": "OP", "sportsbook": "DraftKings", "market_id": "M_NFL_01", "outcome": "HOME", "price": 1.98, "timestamp": "2026-06-27T12:00:00.000Z"},
        {"type": "COMMIT", "tx_id": 101, "hash": "f3b3a344de34a0e829ba5bdf8a493d2767719823cc8ba41f7a64c3b36c7c678a"},
        {"type": "START", "tx_id": 102, "prev_hash": "f3b3a344de34a0e829ba5bdf8a493d2767719823cc8ba41f7a64c3b36c7c678a"},
        {"type": "OP", "sportsbook": "FanDuel", "market_id": "M_NBA_01", "outcome": "AWAY", "price": 2.70, "timestamp": "2026-06-27T12:05:00.000Z"},
        {"type": "COMMIT", "tx_id": 102, "hash": "d20626c89aa74ae12d8ea65cad21e78dc3463bf49c530882f586327bb1b163d0"}
    ]
    with open(wal_path, "w", encoding="utf-8") as f:
        for line in wal_lines:
            f.write(json.dumps(line) + "\n")

    mod = import_candidate_module()
    result = mod.recover_database(tmp_path)

    assert result["initial_tx_id"] == 100
    assert result["final_tx_id"] == 102
    assert result["applied_transactions"] == [101, 102]
    assert result["ticks_inserted"] == 2  # wait, one in 101, one in 102 -> total 2 ticks!
    assert result["corruption_encountered"] is False

def test_recovery_gap_corruption(tmp_path):
    # Fresh DB up to 100
    db_path = tmp_path / "odds.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE markets (market_id TEXT PRIMARY KEY, home_team TEXT, away_team TEXT, sport TEXT);")
    c.execute("CREATE TABLE ticks_log (tick_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, sportsbook TEXT, market_id TEXT, outcome TEXT, price REAL, tx_id INTEGER);")
    c.execute("CREATE TABLE live_odds (market_id TEXT, outcome TEXT, sportsbook TEXT, price REAL, last_updated TEXT, tx_id INTEGER, PRIMARY KEY (market_id, outcome, sportsbook));")
    c.execute("CREATE TABLE applied_transactions (tx_id INTEGER PRIMARY KEY, tx_hash TEXT);")
    c.execute("CREATE TABLE recovery_metadata (name TEXT PRIMARY KEY, value TEXT);")
    c.execute("INSERT INTO recovery_metadata (name, value) VALUES ('last_applied_tx_id', '100');")
    c.execute("INSERT INTO applied_transactions (tx_id, tx_hash) VALUES (100, '04d3183cc211fb146e64eebb38086ded5044b1001970b039129977a03702531b');")
    conn.commit()
    conn.close()

    # Write WAL with tx 101, then a gap to 103
    wal_path = tmp_path / "odds_transactions.jsonl"
    wal_lines = [
        {"type": "START", "tx_id": 101, "prev_hash": "04d3183cc211fb146e64eebb38086ded5044b1001970b039129977a03702531b"},
        {"type": "OP", "sportsbook": "DraftKings", "market_id": "M_NFL_01", "outcome": "HOME", "price": 1.98, "timestamp": "2026-06-27T12:00:00.000Z"},
        {"type": "COMMIT", "tx_id": 101, "hash": "f3b3a344de34a0e829ba5bdf8a493d2767719823cc8ba41f7a64c3b36c7c678a"},
        # Gap to 103
        {"type": "START", "tx_id": 103, "prev_hash": "f3b3a344de34a0e829ba5bdf8a493d2767719823cc8ba41f7a64c3b36c7c678a"},
        {"type": "OP", "sportsbook": "BetMGM", "market_id": "M_MLB_01", "outcome": "HOME", "price": 2.15, "timestamp": "2026-06-27T12:10:00.000Z"},
        {"type": "COMMIT", "tx_id": 103, "hash": "b081addcbd4dfc9923fdfd21d1d58fb05776a09563bd118319181a26fa5e92b5"}
    ]
    with open(wal_path, "w", encoding="utf-8") as f:
        for line in wal_lines:
            f.write(json.dumps(line) + "\n")

    mod = import_candidate_module()
    result = mod.recover_database(tmp_path)

    # Should apply 101, but stop and report corruption at 103
    assert result["initial_tx_id"] == 100
    assert result["final_tx_id"] == 101
    assert result["applied_transactions"] == [101]
    assert result["ticks_inserted"] == 1
    assert result["corruption_encountered"] is True

def test_recovery_hash_mismatch(tmp_path):
    # Fresh DB up to 100
    db_path = tmp_path / "odds.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("CREATE TABLE markets (market_id TEXT PRIMARY KEY, home_team TEXT, away_team TEXT, sport TEXT);")
    c.execute("CREATE TABLE ticks_log (tick_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, sportsbook TEXT, market_id TEXT, outcome TEXT, price REAL, tx_id INTEGER);")
    c.execute("CREATE TABLE live_odds (market_id TEXT, outcome TEXT, sportsbook TEXT, price REAL, last_updated TEXT, tx_id INTEGER, PRIMARY KEY (market_id, outcome, sportsbook));")
    c.execute("CREATE TABLE applied_transactions (tx_id INTEGER PRIMARY KEY, tx_hash TEXT);")
    c.execute("CREATE TABLE recovery_metadata (name TEXT PRIMARY KEY, value TEXT);")
    c.execute("INSERT INTO recovery_metadata (name, value) VALUES ('last_applied_tx_id', '100');")
    c.execute("INSERT INTO applied_transactions (tx_id, tx_hash) VALUES (100, '04d3183cc211fb146e64eebb38086ded5044b1001970b039129977a03702531b');")
    conn.commit()
    conn.close()

    # Write WAL with tx 101 having hash mismatch
    wal_path = tmp_path / "odds_transactions.jsonl"
    wal_lines = [
        {"type": "START", "tx_id": 101, "prev_hash": "04d3183cc211fb146e64eebb38086ded5044b1001970b039129977a03702531b"},
        {"type": "OP", "sportsbook": "DraftKings", "market_id": "M_NFL_01", "outcome": "HOME", "price": 1.98, "timestamp": "2026-06-27T12:00:00.000Z"},
        {"type": "COMMIT", "tx_id": 101, "hash": "bad_hash_value_123"}
    ]
    with open(wal_path, "w", encoding="utf-8") as f:
        for line in wal_lines:
            f.write(json.dumps(line) + "\n")

    mod = import_candidate_module()
    result = mod.recover_database(tmp_path)

    # Should not apply 101 and report corruption
    assert result["initial_tx_id"] == 100
    assert result["final_tx_id"] == 100
    assert result["applied_transactions"] == []
    assert result["ticks_inserted"] == 0
    assert result["corruption_encountered"] is True
