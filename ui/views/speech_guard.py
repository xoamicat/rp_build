import streamlit as st
from ui.helpers import inject_css
from sakshi.speech import SpeechGuard, scan_message, PATTERN_DEFINITIONS

def render():
    inject_css()
    st.title("🗣️ Speech Guard")
    st.caption("Scans every agent message for India's Dark Pattern Guidelines (2023). Catches and rewrites blatant violations before they reach the customer.")

    # ── Interactive scanner ───────────────────────────────────
    st.markdown("##### Try It Live")
    text = st.text_area("Type an agent message:",
                        placeholder="e.g. Hurry, only 3 left! This deal ends in 5 minutes!",
                        height=80)
    after_refusal = st.checkbox("Customer previously refused? (enables nagging detection)")

    if st.button("🔍 Scan Message", type="primary"):
        if text.strip():
            guard = SpeechGuard()
            replacement, findings = guard.filter(text, after_refusal=after_refusal)

            if findings:
                for f in findings:
                    st.error(f"**{f.pattern}** — matched: \"{f.snippet}\"")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**❌ Original (would be blocked):**")
                    st.code(text, language=None)
                with col2:
                    st.markdown("**✅ Replacement (what gets sent):**")
                    st.code(replacement, language=None)
            else:
                st.success("✅ No dark patterns detected. Message is clean.")
        else:
            st.warning("Enter a message to scan.")

    st.divider()

    # ── Examples ─────────────────────────────────────────────
    st.markdown("##### Examples from Kasauti Runs")

    examples = [
        ("false_urgency", "Only 2 left and this price ends in 10 minutes!",
         "Take your time. The price is the same tomorrow."),
        ("confirm_shaming + nagging", "Are you sure? Most customers add it, and it is only ₹190 today.",
         "That's completely fine."),
        ("misrepresentation", "Of course, full refund anytime, no questions asked.",
         "Let me check the exact policy before I promise anything."),
    ]

    for pattern, original, replacement in examples:
        with st.expander(f"**{pattern}** — \"{original[:50]}...\"" if len(original) > 50 else f"**{pattern}** — \"{original}\""):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("❌ **Original:**")
                st.error(original)
            with col2:
                st.markdown("✅ **Replacement:**")
                st.success(replacement)

    st.divider()

    # ── Pattern reference ────────────────────────────────────
    with st.expander("📖 All 9 Pattern Definitions"):
        import pandas as pd
        df = pd.DataFrame([{"Pattern": k, "Definition": v} for k, v in PATTERN_DEFINITIONS.items()])
        st.dataframe(df, use_container_width=True, hide_index=True)
