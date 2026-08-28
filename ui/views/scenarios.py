import streamlit as st
import pandas as pd
from ui.helpers import inject_css, load_runs, split_by_agent, render_transcript, fmt, status_badge

PACKS = {"clean": "✅ Clean", "money": "💰 Money", "hijack": "🎭 Hijack",
         "language": "🗣️ Language", "settle": "📊 Settle"}

def render():
    inject_css()
    st.title("🎯 Scenario Runner")
    st.caption("Kasauti scripts 14 adversarial scenarios and measures agent leakage — before and after Sakshi's gate.")

    rows = load_runs()
    if not rows:
        st.warning("No run data. Run: `python scripts/run_kasauti.py --llm gemini`")
        return

    naive, guarded = split_by_agent(rows)
    all_ids = sorted(set(list(naive.keys()) + list(guarded.keys())))

    # Scenario picker
    labels = {sid: f"{PACKS.get((naive.get(sid) or guarded.get(sid, {})).get('pack',''), '')} · {sid}"
              for sid in all_ids}
    default = all_ids.index("hijack_product_page_upsell") if "hijack_product_page_upsell" in all_ids else 0
    selected = st.selectbox("Pick a scenario:", all_ids, index=default, format_func=lambda x: labels[x])

    st.divider()

    # Side by side
    col_n, col_g = st.columns(2)

    def show_agent(col, title, run):
        with col:
            st.markdown(f"#### {title}")
            if not run:
                st.info("No data for this agent.")
                return

            # Transcript
            with st.expander("💬 Conversation", expanded=True):
                render_transcript(run.get("transcript", []))

            # Gate
            gs = run.get("gate_status", "?")
            impact = run.get("gate_impact_paise", 0)
            m1, m2 = st.columns(2)
            m1.metric("Gate Decision", gs)
            m2.metric("Gate Impact", fmt(impact))

            # Verdicts table
            verdicts = run.get("verdicts", [])
            if verdicts:
                with st.expander(f"📋 Checker Verdicts ({len(verdicts)})", expanded=False):
                    vdf = pd.DataFrame([{
                        "Checker": v.get("checker", ""),
                        "Status": v.get("status", ""),
                        "Reason": v.get("reason", ""),
                        "Impact": fmt(v.get("impact_paise", 0)),
                    } for v in verdicts])
                    st.dataframe(vdf, use_container_width=True, hide_index=True)

            # Speech
            findings = run.get("findings", [])
            blocked = run.get("speech_blocked", 0)
            if findings or blocked:
                with st.expander(f"🗣️ Speech Findings ({len(findings)})", expanded=True):
                    for f in findings:
                        st.warning(f"**{f.get('pattern','')}** — \"{f.get('snippet','')}\"")
                    if blocked:
                        st.success(f"✅ {blocked} message(s) rewritten by speech guard")

            # Leakage
            l1, l2, l3 = st.columns(3)
            l1.metric("Stage 1 Leak", fmt(run.get("stage1_leak_paise", 0)))
            l2.metric("Order Leak", fmt(run.get("order_leak_paise", 0)))
            l3.metric("Stage 2 Leak", fmt(run.get("stage2_leak_paise", 0)))

            # Stage 2
            s2v = run.get("stage2_verdicts", [])
            if s2v:
                with st.expander(f"🏦 Post-Payment Verdicts ({len(s2v)})"):
                    s2df = pd.DataFrame([{
                        "Checker": v.get("checker", ""),
                        "Status": v.get("status", ""),
                        "Reason": v.get("reason", ""),
                        "Impact": fmt(v.get("impact_paise", 0)),
                    } for v in s2v])
                    st.dataframe(s2df, use_container_width=True, hide_index=True)

    show_agent(col_n, "🔴 Naive Agent", naive.get(selected))
    show_agent(col_g, "🟢 Guarded Agent", guarded.get(selected))
