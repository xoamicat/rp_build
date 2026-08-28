import streamlit as st
from ui.helpers import inject_css, load_runs, split_by_agent, fmt

def render():
    inject_css()
    st.title("🛡️ Sakshi — The Witness Layer")
    st.markdown("##### Where Sakshi fits in Razorpay's Agent Studio")

    # ── Agent Studio context ─────────────────────────────────
    st.markdown("""
    <div style="margin-bottom:1.2rem;">
        <p style="margin-bottom:0.5rem;"><strong>Existing Agent Studio agents:</strong></p>
        <span class="chip chip-green">🛒 Cart Recovery</span>
        <span class="chip chip-green">💳 Dispute Responder</span>
        <span class="chip chip-green">📊 Cash Flow Forecaster</span>
        <span class="chip chip-green">🔄 Subscription Recovery</span>
        <span class="chip chip-green">📦 Inventory Agent</span>
        <span class="chip chip-green">🎯 Growth Agent</span>
        <p style="margin:0.8rem 0 0.5rem 0;"><strong>What's missing — no one guards the payment moment:</strong></p>
        <span class="chip chip-red">❌ Intent Verification</span>
        <span class="chip chip-red">❌ Cross-Border Settlement Audit</span>
        <span class="chip chip-red">❌ Dark Pattern Guard (India 2023)</span>
        <p style="margin:0.8rem 0 0.5rem 0;"><strong>The solution:</strong></p>
        <span class="chip chip-blue">🛡️ Sakshi fills all three gaps</span>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Before vs After ──────────────────────────────────────
    st.markdown("##### Before vs After (per 1,000 conversations)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Leakage · Naive", "₹70,422", delta=None)
    c2.metric("Leakage · Guarded", "₹4,565", delta="-93.5%")
    c3.metric("Dark Patterns · Naive", "500/1K")
    c4.metric("Dark Patterns · Guarded", "0/1K", delta="-100%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Dispute Refunds (Naive)", "₹3,050")
    c6.metric("Dispute Refunds (Guarded)", "₹0", delta="-100%")
    c7.metric("Gate Accuracy", "100%")
    c8.metric("False Blocks", "0%")

    c9, c10, c11 = st.columns(3)
    c9.metric("Judge F1 (family)", "91%")
    c10.metric("Cohen's κ", "1.00")
    c11.metric("Corrections Learned", "10")

    st.divider()

    # ── Leakage split ────────────────────────────────────────
    st.markdown("##### Where the Money Leaks")
    import pandas as pd
    df = pd.DataFrame([
        {"Stage": "🚦 Cart (Stage 1)", "Naive": "₹862", "Guarded": "₹0",
         "What Sakshi Does": "Gate blocks unrequested items, price drift, discount breaches"},
        {"Stage": "📋 Promise vs Charge", "Naive": "₹60", "Guarded": "₹0",
         "What Sakshi Does": "Checks agent's stated total against the Razorpay order"},
        {"Stage": "🏦 Settlement (Stage 2)", "Naive": "₹64", "Guarded": "₹64",
         "What Sakshi Does": "Discovers FX markup, fee overcharge, refund burn"},
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Pipeline ─────────────────────────────────────────────
    st.markdown("##### How Sakshi Works")
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.markdown("📋\n\n**1. Capture**\n\nRecord intent receipt")
    p2.markdown("🚦\n\n**2. Gate**\n\nBefore payment")
    p3.markdown("🔍\n\n**3. Reconcile**\n\nAfter payment")
    p4.markdown("⚖️\n\n**4. Dispute**\n\nEvidence + ruling")
    p5.markdown("🧠\n\n**5. Learn**\n\nCorrections loop")
