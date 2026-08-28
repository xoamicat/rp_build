import streamlit as st
from ui.helpers import inject_css, load_runs, split_by_agent, render_transcript, fmt, status_badge

def render():
    inject_css()
    st.title("⚖️ Dispute Resolution")
    st.caption("When a customer disputes a charge, Sakshi builds a 9-point evidence pack and recommends: CONTEST, REFUND, PARTIAL_REFUND, or ESCALATE.")

    rows = load_runs()
    if not rows:
        st.warning("No run data.")
        return

    dispute_rows = [r for r in rows if r.get("dispute_type")]
    if not dispute_rows:
        st.info("No disputes in current run data.")
        return

    naive, guarded = split_by_agent(dispute_rows)
    all_ids = sorted(set(list(naive.keys()) + list(guarded.keys())))
    selected = st.selectbox("Pick a dispute scenario:", all_ids)

    st.divider()

    col_n, col_g = st.columns(2)

    def show_dispute(col, title, run):
        with col:
            st.markdown(f"#### {title}")
            if not run:
                st.info("No dispute for this agent.")
                return

            # Claim
            dtype = run.get("dispute_type", "?").replace("_", " ").title()
            st.info(f"**Claim type:** {dtype}")

            # Recommendation
            rec = run.get("dispute_recommendation", "?")
            st.markdown(f"### {status_badge(rec)}")

            # Financials
            m1, m2 = st.columns(2)
            refund = run.get("dispute_refund_paise", 0)
            cost = run.get("dispute_cost_total_paise", 0)
            m1.metric("Refund Amount", fmt(refund))
            m2.metric("Total Cost (inc fees)", fmt(cost))

            # Flags
            f1, f2 = st.columns(2)
            req = run.get("dispute_requires_human", False)
            match = run.get("dispute_match", False)
            if req:
                f1.error("🟣 Requires Human Review")
            else:
                f1.success("🟢 Auto-Resolved")
            if match:
                f2.success("✓ Matched Expected")
            else:
                f2.warning("✗ Mismatch")

            # Transcript
            with st.expander("💬 View Conversation"):
                render_transcript(run.get("transcript", []))

    show_dispute(col_n, "🔴 Naive Agent", naive.get(selected))
    show_dispute(col_g, "🟢 Guarded Agent", guarded.get(selected))
