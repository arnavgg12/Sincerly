"""Sincerely — Streamlit web UI.

Browser front-end for the apology generator. Reuses the same Gemini-backed
call and the same two prompt files as the CLI (sincerely.py).

Run locally:
    streamlit run streamlit_app.py

Deploy to Streamlit Cloud:
    1. Push the repo to GitHub.
    2. Connect at https://streamlit.io/cloud and pick streamlit_app.py.
    3. In app settings → Secrets, set: GEMINI_API_KEY = "your-key"
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from sincerely import (
    GEMINI_BASE_URL,
    MAX_TOKENS,
    MODEL,
    PROMPT_FREEDUMP,
    PROMPT_STRUCTURED,
    TEMPERATURE,
    build_structured_user_message,
    load_prompt,
)


def get_api_key() -> str | None:
    """Resolve the API key from env var (local dev) or Streamlit secrets (deployed)."""
    load_dotenv(dotenv_path=Path(__file__).parent / ".env")
    key = os.getenv("GEMINI_API_KEY")
    if key:
        return key
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return None


@st.cache_resource
def get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL)


def call_apology(system_prompt: str, user_message: str) -> str:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = get_client(api_key)
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def render_output(apology: str) -> None:
    st.divider()
    st.subheader("Your apology")
    st.text_area(
        "apology_output",
        value=apology,
        height=280,
        label_visibility="collapsed",
    )
    st.caption("Edit if you want, then copy and send. AI-assisted — the recipient doesn't need to know.")


# ----- Page -----

st.set_page_config(page_title="Sincerely", page_icon="✉️", layout="centered")

st.title("Sincerely")
st.caption("Write a sincere apology you can actually send.")

if not get_api_key():
    st.error(
        "`GEMINI_API_KEY` is not configured. Set it as an environment variable "
        "(`setx GEMINI_API_KEY \"<key>\"` on Windows, then reopen the terminal) "
        "or, when deployed, add it to Streamlit Cloud secrets."
    )
    st.stop()

mode = st.radio(
    "Mode",
    ["Quick — one paragraph", "Detailed — 7 fields"],
    horizontal=True,
    label_visibility="collapsed",
)

st.divider()

if mode.startswith("Quick"):
    paragraph = st.text_area(
        "What happened?",
        height=180,
        placeholder="Tell me — who, what you did, what they're upset about. Just write it out, however messy.",
    )
    if st.button(
        "Write the apology",
        type="primary",
        disabled=not paragraph.strip(),
        use_container_width=True,
    ):
        with st.spinner("Writing..."):
            try:
                system_prompt = load_prompt(PROMPT_FREEDUMP)
                apology = call_apology(system_prompt, paragraph)
            except Exception as e:
                st.error(f"Couldn't generate the apology: {e}")
                st.stop()
        render_output(apology)

else:
    col_a, col_b = st.columns(2)
    with col_a:
        recipient = st.text_input("Recipient *", placeholder="e.g. mom, Sarah")
        relationship = st.text_input("Your relationship", placeholder="e.g. close friend, my mom")
        what_happened = st.text_area(
            "What happened *",
            height=120,
            placeholder="What you did, what they're upset about",
        )
    with col_b:
        responsibility = st.text_area(
            "What you take responsibility for",
            height=120,
            placeholder="Be specific — the part that was actually yours",
        )
        tone = st.selectbox("Tone", ["heartfelt", "casual", "formal", "brief", "quiet"])
        fmt = st.selectbox("Format", ["text", "email", "letter", "in-person"])
    reparation = st.text_input("How you'd like to make it right (optional)")

    submit_disabled = not (recipient.strip() and what_happened.strip())
    if st.button(
        "Write the apology",
        type="primary",
        disabled=submit_disabled,
        use_container_width=True,
    ):
        with st.spinner("Writing..."):
            try:
                fields = {
                    "recipient": recipient,
                    "relationship": relationship,
                    "what_happened": what_happened,
                    "responsibility": responsibility,
                    "tone": tone,
                    "format": fmt,
                    "reparation": reparation,
                }
                user_msg = build_structured_user_message(fields)
                system_prompt = load_prompt(PROMPT_STRUCTURED)
                apology = call_apology(system_prompt, user_msg)
            except Exception as e:
                st.error(f"Couldn't generate the apology: {e}")
                st.stop()
        render_output(apology)
