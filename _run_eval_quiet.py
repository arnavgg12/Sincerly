"""Throwaway: run the eval without Rich console output.

Used when stdout is redirected (e.g. from agent shells) where Rich's Windows
console renderer trips on cp1252 encoding. Same DB schema, same model,
same prompts — just plain print() instead of Rich panels.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from openai import OpenAI

from sincerely import (
    GEMINI_BASE_URL,
    PROMPT_FREEDUMP,
    TEST_FILE,
    call_model,
    init_db,
    load_prompt,
    save_run,
)


HERE = Path(__file__).parent
load_dotenv(dotenv_path=HERE / ".env")
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("ERROR: GEMINI_API_KEY not set")
    sys.exit(1)

client = OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL)
conn = init_db()
system_prompt = load_prompt(PROMPT_FREEDUMP)

paragraphs = [
    line.strip()
    for line in TEST_FILE.read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.strip().startswith("#")
]

ok = 0
fail = 0
for i, p in enumerate(paragraphs, start=1):
    try:
        apology = call_model(client, system_prompt, p)
        run_id = save_run(conn, "eval", {"paragraph": p}, apology)
        print(f"#{i}/{len(paragraphs)} OK (run_id={run_id})")
        ok += 1
    except Exception as e:
        print(f"#{i}/{len(paragraphs)} FAIL: {e}")
        fail += 1

print(f"\n{ok}/{len(paragraphs)} succeeded, {fail} failed")
conn.close()
