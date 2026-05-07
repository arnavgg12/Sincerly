"""Sincerely — sincere-apology text generator.

Single-file CLI. Two input modes:
- free-dump: user pastes one messy paragraph
- structured: user answers 7 quick questions (recipient, relationship, what
  happened, what to take responsibility for, tone, format, optional reparation)

Output is a copy-paste-ready apology in the user's voice. Each run is saved
to sincerely_runs.db for later review during prompt iteration.

Backed by Google's Gemini API via the OpenAI-compatible endpoint at AI Studio.
Adjust MODEL below if your tier doesn't include the default.

Usage:
  python sincerely.py                       # interactive (asks mode first)
  python sincerely.py --mode freedump       # free-dump only
  python sincerely.py --mode structured     # structured only
  python sincerely.py --eval                # batch run free-dump against test_apologies.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt


HERE = Path(__file__).parent
PROMPT_DIR = HERE / "prompts"
PROMPT_FREEDUMP = PROMPT_DIR / "system_freedump.md"
PROMPT_STRUCTURED = PROMPT_DIR / "system_structured.md"
DB_PATH = HERE / "sincerely_runs.db"
TEST_FILE = HERE / "test_apologies.txt"

# Adjust if your AI Studio tier doesn't include this model.
# Common alternatives: "gemini-2.5-pro" (most capable, slower),
# "gemini-2.5-flash-lite" (cheapest, fastest, less nuanced).
MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.6
MAX_TOKENS = 2048
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

TONE_CHOICES = ["heartfelt", "casual", "formal", "brief", "quiet"]
FORMAT_CHOICES = ["text", "email", "letter", "in-person"]


console = Console()


def load_prompt(path: Path) -> str:
    if not path.exists():
        console.print(f"[red]Missing prompt at {path}[/red]")
        sys.exit(1)
    return path.read_text(encoding="utf-8").strip()


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            mode TEXT NOT NULL,
            input_json TEXT NOT NULL,
            apology TEXT NOT NULL,
            model TEXT NOT NULL,
            temperature REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def save_run(
    conn: sqlite3.Connection,
    mode: str,
    input_data: dict,
    apology: str,
) -> int:
    cursor = conn.execute(
        """INSERT INTO runs (timestamp, mode, input_json, apology, model, temperature)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(timespec="seconds"),
            mode,
            json.dumps(input_data, ensure_ascii=False),
            apology,
            MODEL,
            TEMPERATURE,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def call_model(client: OpenAI, system_prompt: str, user_message: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    content = response.choices[0].message.content
    return (content or "").strip()


def ask_freedump_input() -> str:
    return Prompt.ask(
        "\n[bold]Describe the situation[/bold] "
        "[dim](one or two lines — who, what happened, what you did, why you're sorry)[/dim]"
    )


def ask_structured_input() -> dict[str, str]:
    console.print("\n[bold]Quick questions[/bold] [dim](press Enter to skip optional ones)[/dim]")
    recipient = Prompt.ask("Recipient (name or how you address them)")
    relationship = Prompt.ask("Your relationship to them [dim](e.g. close friend, my mom, manager)[/dim]")
    what_happened = Prompt.ask("What happened [dim](what you did, what they're upset about)[/dim]")
    responsibility = Prompt.ask(
        "What you want to take responsibility for [dim](be specific — the part that was actually yours)[/dim]"
    )
    tone = Prompt.ask(
        f"Tone [dim]({' / '.join(TONE_CHOICES)})[/dim]",
        choices=TONE_CHOICES,
        default="heartfelt",
    )
    fmt = Prompt.ask(
        f"Format [dim]({' / '.join(FORMAT_CHOICES)})[/dim]",
        choices=FORMAT_CHOICES,
        default="text",
    )
    reparation = Prompt.ask(
        "How you'd like to make it right [dim](optional — leave blank to skip)[/dim]",
        default="",
    )
    return {
        "recipient": recipient,
        "relationship": relationship,
        "what_happened": what_happened,
        "responsibility": responsibility,
        "tone": tone,
        "format": fmt,
        "reparation": reparation,
    }


def build_structured_user_message(fields: dict[str, str]) -> str:
    lines = [
        f"Recipient: {fields['recipient']}",
        f"Relationship: {fields['relationship']}",
        f"What happened: {fields['what_happened']}",
        f"What I want to take responsibility for: {fields['responsibility']}",
        f"Tone: {fields['tone']}",
        f"Format: {fields['format']}",
    ]
    if fields.get("reparation"):
        lines.append(f"How I'd like to make it right: {fields['reparation']}")
    return "\n".join(lines)


def render_apology(mode_label: str, apology: str) -> None:
    console.print()
    console.print(
        Panel(
            apology,
            title=f"[bold]Apology[/bold] [dim]({mode_label})[/dim]",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def run_freedump(client: OpenAI, conn: sqlite3.Connection) -> None:
    paragraph = ask_freedump_input()
    if not paragraph.strip():
        console.print("[red]Empty input. Aborting.[/red]")
        return

    system_prompt = load_prompt(PROMPT_FREEDUMP)
    console.print(f"\n[dim]Calling {MODEL}...[/dim]")
    try:
        apology = call_model(client, system_prompt, paragraph)
    except Exception as e:
        console.print(f"[red]API call failed: {e}[/red]")
        return

    run_id = save_run(conn, "freedump", {"paragraph": paragraph}, apology)
    render_apology("free dump", apology)
    console.print(f"\n[dim]Saved as run #{run_id} in {DB_PATH.name}[/dim]")


def run_structured(client: OpenAI, conn: sqlite3.Connection) -> None:
    fields = ask_structured_input()
    if not fields["recipient"].strip() or not fields["what_happened"].strip():
        console.print("[red]Need at least recipient and what-happened. Aborting.[/red]")
        return

    system_prompt = load_prompt(PROMPT_STRUCTURED)
    user_message = build_structured_user_message(fields)
    console.print(f"\n[dim]Calling {MODEL}...[/dim]")
    try:
        apology = call_model(client, system_prompt, user_message)
    except Exception as e:
        console.print(f"[red]API call failed: {e}[/red]")
        return

    run_id = save_run(conn, "structured", fields, apology)
    render_apology("structured", apology)
    console.print(f"\n[dim]Saved as run #{run_id} in {DB_PATH.name}[/dim]")


def run_eval(client: OpenAI, conn: sqlite3.Connection) -> None:
    if not TEST_FILE.exists():
        console.print(f"[red]{TEST_FILE.name} not found.[/red]")
        return

    paragraphs = [
        line.strip()
        for line in TEST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not paragraphs:
        console.print(f"[red]{TEST_FILE.name} is empty.[/red]")
        return

    system_prompt = load_prompt(PROMPT_FREEDUMP)
    console.print(f"[bold]Eval mode (free-dump, {MODEL}):[/bold] {len(paragraphs)} cases\n")

    failures: list[tuple[int, str, str]] = []
    successes = 0
    for i, paragraph in enumerate(paragraphs, start=1):
        console.rule(f"[bold]{i}/{len(paragraphs)}[/bold]")
        console.print(
            Panel(paragraph, title="[dim]Input[/dim]", border_style="dim", box=box.ROUNDED)
        )
        try:
            apology = call_model(client, system_prompt, paragraph)
            run_id = save_run(conn, "eval", {"paragraph": paragraph}, apology)
            render_apology("free dump", apology)
            console.print(f"[dim]Saved as run #{run_id}[/dim]")
            successes += 1
        except Exception as e:
            failures.append((i, paragraph, str(e)))
            console.print(f"[red]Failed on #{i}: {e}[/red]")

    console.rule()
    console.print(
        f"\n[bold green]Eval complete:[/bold green] {successes}/{len(paragraphs)} runs saved to {DB_PATH.name}"
    )
    if failures:
        console.print("[bold red]Failures:[/bold red]")
        for i, p, err in failures:
            console.print(f"  #{i}: {p[:60]}... -> {err}")


def pick_mode_interactively() -> str:
    console.print()
    console.print(
        Panel(
            "[bold]Sincerely[/bold] — write a sincere apology you can actually send.\n\n"
            "[bold cyan][1] Free dump[/bold cyan] — paste one messy paragraph; the model figures it out\n"
            "[bold magenta][2] Structured[/bold magenta] — answer 7 quick questions for tighter control",
            border_style="white",
            box=box.ROUNDED,
        )
    )
    choice = Prompt.ask("Pick a mode", choices=["1", "2"], default="1")
    return "freedump" if choice == "1" else "structured"


def main() -> None:
    parser = argparse.ArgumentParser(description="Sincerely — sincere-apology text generator")
    parser.add_argument(
        "--mode",
        choices=["freedump", "structured"],
        default=None,
        help="Skip the interactive picker and go straight into a mode.",
    )
    parser.add_argument(
        "--eval",
        action="store_true",
        help=f"Batch mode: free-dump against all cases in {TEST_FILE.name}",
    )
    args = parser.parse_args()

    load_dotenv(dotenv_path=HERE / ".env")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        console.print(
            "[red]GEMINI_API_KEY not set.[/red] Either set it as a Windows user env var "
            "([dim]setx GEMINI_API_KEY \"<key>\"[/dim], then open a new terminal), "
            "or copy [dim].env.example[/dim] to [dim].env[/dim] and fill it in."
        )
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL)
    conn = init_db()

    try:
        if args.eval:
            run_eval(client, conn)
        else:
            mode = args.mode or pick_mode_interactively()
            if mode == "freedump":
                run_freedump(client, conn)
            else:
                run_structured(client, conn)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(130)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
