"""
CFO Chat Page — Multi-turn Claude CFO interface.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st

st.set_page_config(page_title="CFO Chat — WealthMap", page_icon="🤖", layout="wide")
st.title("🤖 CFO Chat — Ask Claude")
st.caption("Your AI CFO with full context of the family portfolio and Indian tax rules.")

if "initialized" not in st.session_state:
    st.warning("Please start from the main app page.")
    st.stop()

family = st.session_state.family
cfo = st.session_state.cfo
ctx_builder = st.session_state.ctx_builder

# Initialize chat history
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "chat_context" not in st.session_state:
    st.session_state.chat_context = ctx_builder.build_portfolio_context(family)

# ── Suggested Questions ───────────────────────────────────────────────────────
if not st.session_state.chat_messages:
    st.subheader("💡 Suggested Questions")
    suggestions = [
        "What is my family's overall tax exposure this FY?",
        "Should I sell my Bitcoin now or wait? I need ₹5L for a property down payment.",
        "Which positions should I sell before March 31 to optimize my tax?",
        "How much LTCG exemption does each family member have left?",
        "What is the best tax-loss harvesting strategy for my portfolio right now?",
        "If BTC drops 20%, how does that affect my overall tax picture?",
    ]
    cols = st.columns(2)
    for i, q in enumerate(suggestions):
        with cols[i % 2]:
            if st.button(q, use_container_width=True, key=f"sugg_{i}"):
                st.session_state.chat_messages.append({"role": "user", "content": q})
                st.rerun()

# ── Chat History ──────────────────────────────────────────────────────────────
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])

# ── Chat Input ────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask your CFO anything about your portfolio..."):
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("CFO analyzing your portfolio..."):
            # Build conversation history for Claude
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.chat_messages[:-1]  # Exclude current
            ]
            response = cfo.chat(
                st.session_state.chat_context,
                prompt,
                history,
            )
        st.markdown(response)
        st.session_state.chat_messages.append({"role": "assistant", "content": response})

# ── Controls ──────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([1, 1, 4])
with col1:
    if st.button("🗑️ Clear Chat"):
        st.session_state.chat_messages = []
        st.rerun()
with col2:
    if st.button("🔄 Refresh Context"):
        st.session_state.chat_context = ctx_builder.build_portfolio_context(family)
        st.success("Context refreshed!")

st.divider()

# ── Quick Analysis Buttons ────────────────────────────────────────────────────
st.subheader("⚡ Quick Analysis")
col_q1, col_q2, col_q3 = st.columns(3)

with col_q1:
    if st.button("📊 Portfolio Health Report", use_container_width=True):
        with st.spinner("Generating portfolio health assessment..."):
            context = ctx_builder.build_portfolio_context(family)
            report = cfo.portfolio_health(context)
        with st.expander("Portfolio Health Report", expanded=True):
            st.markdown(report)

with col_q2:
    if st.button("🧾 Tax Optimization Report", use_container_width=True):
        with st.spinner("Generating tax advice..."):
            context = ctx_builder.build_tax_advice_context(family)
            advice = cfo.tax_advice(context)
        with st.expander("Tax Optimization Report", expanded=True):
            st.markdown(advice)

with col_q3:
    if st.button("📋 Daily Digest", use_container_width=True):
        with st.spinner("Generating daily digest..."):
            context = ctx_builder.build_daily_digest_context(family)
            digest = cfo.daily_digest(context)
        with st.expander("Daily Digest", expanded=True):
            st.markdown(digest)

st.divider()
st.caption("⚠️ All Claude output is advisory only. WealthMap is not a SEBI-registered advisor. "
           "Always verify with a qualified CA before making financial decisions.")
