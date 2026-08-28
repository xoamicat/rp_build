"""Sakshi — Streamlit demo.  Run:  streamlit run ui/app.py"""
import streamlit as st
st.set_page_config(page_title="Sakshi · Witness Layer", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ui.helpers import inject_css

inject_css()

with st.sidebar:
    st.markdown("### 🛡️ Sakshi")
    st.caption("Witness Layer for Agent Payments")
    st.markdown("---")
    page = st.radio("Navigate", [
        "🏠 Dashboard",
        "🎯 Scenarios",
        "⚖️ Disputes",
        "🗣️ Speech Guard",
        "🧠 Memory",
        "📊 Report",
    ], label_visibility="collapsed")
    st.markdown("---")
    st.caption("Razorpay AI Buildathon 2026 · Track 5")

if "Dashboard" in page:
    from ui.views.dashboard import render
elif "Scenarios" in page:
    from ui.views.scenarios import render
elif "Disputes" in page:
    from ui.views.disputes import render
elif "Speech" in page:
    from ui.views.speech_guard import render
elif "Memory" in page:
    from ui.views.memory import render
else:
    from ui.views.report import render

render()
