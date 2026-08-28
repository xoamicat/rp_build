"""Shared helpers for Sakshi UI. Minimal CSS, mostly Streamlit-native components."""
from __future__ import annotations
import json, sys
from pathlib import Path
import streamlit as st
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Colours ─────────────────────────────────────────────────────────
NAVY = "#072654"
BLUE = "#528FF0"

STATUS_EMOJI = {
    "PASS": "🟢", "FLAG": "🟡", "ASK_HUMAN": "🟣", "BLOCK": "🔴", "SKIP": "⚪",
    "CONTEST": "🟢", "REFUND": "🔴", "PARTIAL_REFUND": "🟡", "ESCALATE": "🟣",
}


def inject_css():
    st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, .stApp { font-family: 'Inter', sans-serif; }
    section[data-testid="stSidebar"] { background: #072654 !important; }
    section[data-testid="stSidebar"] * { color: white !important; }
    section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
        background: rgba(255,255,255,0.08); border-radius: 8px; padding: 0.4rem 0.8rem;
        margin: 2px 0; transition: background 0.2s;
    }
    section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:hover {
        background: rgba(255,255,255,0.15);
    }
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1.5rem; max-width: 1100px; }
    div[data-testid="stMetric"] {
        background: white; border-radius: 10px; padding: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #edf1f7;
    }
    .chat-c { background: #E8F1FF; padding: 0.6rem 0.9rem; border-radius: 12px 12px 12px 4px;
              margin: 0.3rem 0; font-size: 0.88rem; }
    .chat-a { background: #f8f9fc; padding: 0.6rem 0.9rem; border-radius: 12px 12px 4px 12px;
              margin: 0.3rem 0; font-size: 0.88rem; border: 1px solid #edf1f7; }
    .chip { display:inline-block; padding:0.35rem 0.75rem; border-radius:8px; font-size:0.82rem;
            font-weight:500; margin:3px; }
    .chip-green { background:#e7f9f0; color:#0d6e4f; border:1px solid #1cb57e; }
    .chip-red { background:#fde8e9; color:#a3222a; border:1px solid #e2444d; }
    .chip-blue { background:#e8f1ff; color:#1a5dc8; border:1px solid #528ff0; font-weight:700; }
    </style>""", unsafe_allow_html=True)


def status_badge(status: str) -> str:
    return f"{STATUS_EMOJI.get(status, '⚪')} **{status}**"


def render_transcript(transcript: list[dict]):
    for t in transcript:
        if t["role"] == "customer":
            st.markdown(f'<div class="chat-c">👤 <strong>Customer:</strong> {t["text"]}</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-a">🤖 <strong>Agent:</strong> {t["text"]}</div>',
                        unsafe_allow_html=True)


def fmt(paise: int) -> str:
    r = paise / 100
    return f"₹{int(r):,}" if r == int(r) else f"₹{r:,.2f}"


@st.cache_data
def load_runs():
    rows = []
    for p in (ROOT / "data" / "runs").glob("*.jsonl"):
        with open(p, encoding="utf-8") as fh:
            rows.extend(json.loads(line) for line in fh if line.strip())
    return rows


@st.cache_data
def load_report():
    p = ROOT / "data" / "reports" / "report.md"
    return p.read_text(encoding="utf-8") if p.exists() else "*No report yet.*"


def split_by_agent(rows):
    naive, guarded = {}, {}
    for r in rows:
        (naive if r["agent"] == "rule-naive" else guarded)[r["scenario_id"]] = r
    return naive, guarded
