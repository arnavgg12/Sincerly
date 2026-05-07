"""Throwaway: dump all eval runs from sincerely_runs.db for prompt review."""
import json
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "sincerely_runs.db"
conn = sqlite3.connect(DB)
rows = conn.execute(
    "select id, input_json, apology from runs where id >= 59 order by id"
).fetchall()

for rid, ij, ap in rows:
    paragraph = json.loads(ij).get("paragraph", "")
    print(f"\n{'=' * 78}\n#{rid}\n{'=' * 78}")
    print(f"INPUT:\n{paragraph}\n")
    print(f"APOLOGY:\n{ap}")
