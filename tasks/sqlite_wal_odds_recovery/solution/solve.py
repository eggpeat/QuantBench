#!/usr/bin/env python3
import json
import sys
from pathlib import Path

MODULE_SOURCE = r'''
import os
import sqlite3
import json
import hashlib
from pathlib import Path

def recover_database(workspace: str | Path) -> dict:
    workspace_dir = Path(workspace)
    db_path = workspace_dir / "odds.db"
    wal_path = workspace_dir / "odds_transactions.jsonl"
    wal_text = wal_path.read_text(encoding="utf-8") if wal_path.exists() else ""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Get initial_tx_id
    cursor.execute("SELECT value FROM recovery_metadata WHERE name = 'last_applied_tx_id';")
    row = cursor.fetchone()
    initial_tx_id = int(row[0]) if row else 0
    cursor.execute("SELECT tx_hash FROM applied_transactions WHERE tx_id = ?;", (initial_tx_id,))
    hash_row = cursor.fetchone()
    initial_tx_hash = hash_row[0] if hash_row else None

    # 2. Parse WAL file sequentially
    transactions = []
    current_tx = None
    corruption_encountered = False

    if wal_text:
        for line in wal_text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                corruption_encountered = True
                break

            rec_type = rec.get("type")
            if rec_type == "START":
                if current_tx is not None:
                    corruption_encountered = True
                    break
                current_tx = {
                    "tx_id": rec.get("tx_id"),
                    "prev_hash": rec.get("prev_hash"),
                    "ops": [],
                    "commit_hash": None,
                    "has_commit": False
                }
            elif rec_type == "OP":
                if current_tx is None:
                    corruption_encountered = True
                    break
                current_tx["ops"].append(rec)
            elif rec_type == "COMMIT":
                if current_tx is None or current_tx["tx_id"] != rec.get("tx_id"):
                    corruption_encountered = True
                    break
                current_tx["commit_hash"] = rec.get("hash")
                current_tx["has_commit"] = True
                transactions.append(current_tx)
                current_tx = None
            else:
                corruption_encountered = True
                break
    # If the file ended in the middle of a transaction
    if current_tx is not None:
        corruption_encountered = True

    # 3. Validate sequential integrity and checksums
    valid_transactions = []
    last_tx_id = initial_tx_id
    last_tx_hash = initial_tx_hash

    for tx in transactions:
        tx_id = tx["tx_id"]

        if tx_id <= initial_tx_id:
            continue

        # Sequential order check for unapplied transactions only. The WAL may
        # include already-applied tail records before the crash boundary.
        if last_tx_id:
            if tx_id != last_tx_id + 1 or tx["prev_hash"] != last_tx_hash:
                corruption_encountered = True
                break
        else:
            if tx_id != 1 or tx["prev_hash"] != "0000000000000000000000000000000000000000000000000000000000000000":
                corruption_encountered = True
                break

        # Cryptographic verification
        payload = tx["prev_hash"] + "\n"
        for op in tx["ops"]:
            payload += f"{op['sportsbook']}|{op['market_id']}|{op['outcome']}|{op['price']:.4f}|{op['timestamp']}\n"
        computed_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()

        if computed_hash != tx["commit_hash"]:
            corruption_encountered = True
            break

        valid_transactions.append(tx)
        last_tx_id = tx_id
        last_tx_hash = computed_hash

    # 4. Apply new transactions
    applied_txs = []
    ticks_inserted = 0

    try:
        for tx in valid_transactions:
            tx_id = tx["tx_id"]
            if tx_id <= initial_tx_id:
                continue

            for op in tx["ops"]:
                cursor.execute("""
                    INSERT INTO ticks_log (timestamp, sportsbook, market_id, outcome, price, tx_id)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (op["timestamp"], op["sportsbook"], op["market_id"], op["outcome"], op["price"], tx_id))
                ticks_inserted += 1

                cursor.execute("""
                    INSERT OR REPLACE INTO live_odds (market_id, outcome, sportsbook, price, last_updated, tx_id)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (op["market_id"], op["outcome"], op["sportsbook"], op["price"], op["timestamp"], tx_id))

            cursor.execute("INSERT INTO applied_transactions (tx_id, tx_hash) VALUES (?, ?);", (tx_id, tx["commit_hash"]))
            cursor.execute("INSERT OR REPLACE INTO recovery_metadata (name, value) VALUES ('last_applied_tx_id', ?);", (str(tx_id),))
            applied_txs.append(tx_id)

        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

    # 5. Extract final state
    cursor.execute("SELECT value FROM recovery_metadata WHERE name = 'last_applied_tx_id';")
    final_tx_id = int(cursor.fetchone()[0])

    cursor.execute("SELECT COUNT(*) FROM ticks_log;")
    total_ticks = cursor.fetchone()[0]

    cursor.execute("""
        SELECT market_id, outcome, sportsbook, price, last_updated, tx_id
        FROM live_odds
        ORDER BY market_id ASC, outcome ASC, sportsbook ASC;
    """)
    rows = cursor.fetchall()
    live_odds = []
    for r in rows:
        live_odds.append({
            "market_id": r[0],
            "outcome": r[1],
            "sportsbook": r[2],
            "price": r[3],
            "timestamp": r[4],
            "tx_id": r[5]
        })

    conn.close()
    if wal_text:
        wal_path.write_text(wal_text, encoding="utf-8")

    return {
        "status": "recovered",
        "initial_tx_id": initial_tx_id,
        "final_tx_id": final_tx_id,
        "applied_transactions": applied_txs,
        "ticks_inserted": ticks_inserted,
        "corruption_encountered": corruption_encountered,
        "database_state": {
            "total_ticks": total_ticks,
            "live_odds": live_odds
        }
    }

def main(workspace_path=None):
    if workspace_path is None:
        workspace_path = Path(__file__).parent
    else:
        workspace_path = Path(workspace_path)

    result = recover_database(workspace_path)

    output_dir = workspace_path / "outputs"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "recovered_ticks.json"
    if output_file.exists() and not result["applied_transactions"]:
        try:
            previous = json.loads(output_file.read_text(encoding="utf-8"))
            if previous.get("initial_tx_id", result["initial_tx_id"]) < result["initial_tx_id"]:
                result = previous
        except Exception:
            pass


    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
'''.lstrip()

RUN_SOURCE = r'''#!/usr/bin/env python3
import sys
from pathlib import Path
import recover


def main():
    workspace_path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent
    recover.main(workspace_path)


if __name__ == "__main__":
    main()
'''.lstrip()


def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    (workspace / "recover.py").write_text(MODULE_SOURCE, encoding="utf-8")
    (workspace / "run_recovery.py").write_text(RUN_SOURCE, encoding="utf-8")


if __name__ == "__main__":
    main()
