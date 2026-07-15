import importlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")

def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)

def import_candidate_module():
    sys.path.insert(0, str(WORKSPACE))
    try:
        return importlib.import_module("optimize_query")
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
    import runpy
    import os
    import sys

    # Make sure output directory exists
    (WORKSPACE / "outputs").mkdir(exist_ok=True)

    old_cwd = os.getcwd()
    old_argv = sys.argv
    try:
        os.chdir(str(WORKSPACE))
        sys.argv = [str(WORKSPACE / "run_query.py"), str(WORKSPACE)]
        runpy.run_path(str(WORKSPACE / "run_query.py"), run_name="__main__")
    except SystemExit:
        # Candidate-controlled wrappers must not be able to terminate the verifier.
        pass
    except Exception:
        # Fallback to direct call in case run_query.py is missing or fails
        try:
            sys.path.insert(0, str(WORKSPACE))
            import optimize_query
            importlib.reload(optimize_query)
            optimize_query.optimize_query(
                WORKSPACE / "backtest.db",
                WORKSPACE / "query.sql",
                WORKSPACE / "outputs"
            )
        except Exception:
            pass
        finally:
            try:
                sys.path.remove(str(WORKSPACE))
            except ValueError:
                pass
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)
    _run_once = True
def test_public_fixture_output_matches_expected_snapshot():
    run_candidate()
    output_path = WORKSPACE / "outputs" / "query_result.json"
    assert output_path.exists(), "missing outputs/query_result.json"

    actual = load_json(output_path)
    expected = load_json(EXPECTED_PATH)
    assert actual == expected, "Query results do not match expected snapshot."

def test_public_query_plan_is_efficient():
    run_candidate()
    plan_path = WORKSPACE / "outputs" / "query_plan.json"
    assert plan_path.exists(), "missing outputs/query_plan.json"

    plan = load_json(plan_path)
    assert isinstance(plan, list), "query_plan.json must be a list of records."
    assert len(plan) > 0, "query_plan.json is empty."

    search_found = False
    for row in plan:
        detail = row.get("detail", "").upper()
        # Verify no full table scans on matches, odds, predictions
        assert "SCAN" not in detail, f"Query plan contains SCAN: '{row.get('detail')}'"
        # Verify no automatic covering indexes were created on the fly
        assert "AUTOMATIC" not in detail, f"Query plan contains AUTOMATIC index: '{row.get('detail')}'"
        # Verify no bloom filters
        assert "BLOOM" not in detail, f"Query plan contains BLOOM filter: '{row.get('detail')}'"
        if "SEARCH" in detail:
            search_found = True

    assert search_found, "Query plan does not contain any SEARCH operations, indicating indexes were not used."

def test_inline_fresh_db():
    # Build a fresh database with a different random seed
    import random
    from datetime import datetime, timedelta

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        db_path = tmp_path / "inline.db"
        query_path = tmp_path / "query.sql"
        output_dir = tmp_path / "outputs"
        output_dir.mkdir()

        # Copy query.sql from workspace
        query_src = WORKSPACE / "query.sql"
        query_path.write_text(query_src.read_text(encoding="utf-8"), encoding="utf-8")

        # Build DB
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.executescript("""
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

        # Generate 400 matches deterministically with a different seed
        random.seed(999)
        start_date = datetime(2024, 1, 1, 12, 0, 0)
        sports = ['soccer', 'basketball', 'tennis', 'hockey']
        matches_data = []
        for g_id in range(1, 401):
            sport = sports[g_id % len(sports)]
            kickoff = start_date + timedelta(minutes=g_id * 511)
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

        odds_data = []
        odds_id = 1
        for g_id in range(1, 401):
            kickoff_str = matches_data[g_id-1][2]
            kickoff = datetime.strptime(kickoff_str, "%Y-%m-%d %H:%M:%S")
            for bookmaker in ['BookieA', 'BookieB', 'BookieC']:
                for hours_before in [8, 4, 1]:
                    recorded = kickoff - timedelta(hours=hours_before)
                    odds_val = round(1.3 + (g_id % 5) * 0.5 + (hours_before * 0.08) + random.uniform(-0.15, 0.15), 2)
                    odds_data.append((
                        odds_id,
                        g_id,
                        bookmaker,
                        odds_val,
                        recorded.strftime("%Y-%m-%d %H:%M:%S")
                    ))
                    odds_id += 1
        cursor.executemany("INSERT INTO odds VALUES (?,?,?,?,?)", odds_data)

        predictions_data = []
        pred_id = 1
        for g_id in range(1, 401):
            kickoff_str = matches_data[g_id-1][2]
            kickoff = datetime.strptime(kickoff_str, "%Y-%m-%d %H:%M:%S")
            for model in ['AlphaModel', 'BetaModel']:
                for hours_before in [10, 5]:
                    generated = kickoff - timedelta(hours=hours_before)
                    pred_val = round(0.25 + ((g_id + hours_before) % 6) * 0.08 + random.uniform(-0.03, 0.03), 3)
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

        # Let's run the query on un-indexed db to get the reference results
        query_sql = query_path.read_text(encoding="utf-8")
        cursor.execute(query_sql)
        raw_rows = cursor.fetchall()
        keys = [col[0] for col in cursor.description]
        expected_inline_results = [dict(zip(keys, r)) for r in raw_rows]
        conn.close()

        # Now import and execute the candidate's optimize_query module
        mod = import_candidate_module()
        mod.optimize_query(db_path, query_path, output_dir)

        # 1. Verify files are created
        res_json_path = output_dir / "query_result.json"
        plan_json_path = output_dir / "query_plan.json"
        assert res_json_path.exists(), "optimize_query did not write query_result.json"
        assert plan_json_path.exists(), "optimize_query did not write query_plan.json"

        # 2. Check result parity
        actual_results = load_json(res_json_path)
        assert actual_results == expected_inline_results, "Results on the fresh inline database do not match reference results."

        # 3. Check query plan contains no scans/automatics/bloom filters
        actual_plan = load_json(plan_json_path)
        search_found = False
        for row in actual_plan:
            detail = row.get("detail", "").upper()
            assert "SCAN" not in detail, f"Inline query plan contains SCAN: '{row.get('detail')}'"
            assert "AUTOMATIC" not in detail, f"Inline query plan contains AUTOMATIC index: '{row.get('detail')}'"
            assert "BLOOM" not in detail, f"Inline query plan contains BLOOM filter: '{row.get('detail')}'"
            if "SEARCH" in detail:
                search_found = True
        assert search_found, "Inline query plan did not use indexes (no SEARCH operations found)."

        # 4. Verify indexes are actually created in the DB schema
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [r[0] for r in cursor.fetchall() if not r[0].startswith("sqlite_")]
        conn.close()
        assert len(indexes) > 0, "No user-defined indexes found in the database schema."
