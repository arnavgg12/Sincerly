"""Throwaway: run the remaining 9 test cases (7-15) with throttling to fit
Gemini free-tier's 5 RPM cap.

The first 6 already succeeded and saved as run_ids 59-64. This script runs
indices 6..14 (cases #7..#15) with a 65s upfront wait to clear the rate
window, then 13s between calls (~4.6 RPM, safely under 5).
"""

import os
import sys
import time
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

START = 6  # 0-indexed; case #7
THROTTLE_SEC = 13
INITIAL_WAIT = 65

print(f"Waiting {INITIAL_WAIT}s to clear rate-limit window...")
time.sleep(INITIAL_WAIT)

for i in range(START, len(paragraphs)):
    if i > START:
        time.sleep(THROTTLE_SEC)
    p = paragraphs[i]
    try:
        apology = call_model(client, system_prompt, p)
        run_id = save_run(conn, "eval", {"paragraph": p}, apology)
        print(f"#{i+1}/{len(paragraphs)} OK (run_id={run_id})")
    except Exception as e:
        print(f"#{i+1}/{len(paragraphs)} FAIL: {str(e)[:180]}")

conn.close()
