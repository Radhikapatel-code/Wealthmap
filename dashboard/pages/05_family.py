"""
Family View Page — Per-member portfolio breakdown and comparison.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from decimal import Decimal

st.set_page_config(page_title="Family View — WealthMap", page_icon="👨‍👩‍👦", layout="wide")
st.title("👨‍👩‍👦 Family View")
st.caption("Wealth, tax, and portfolio breakdown per family member. LTCG exemption is per individual.")

if "initialized" not in st.session_state:
    st.warning("Please start from the main app page.")
    st.stop()

family = st.session_state.family

# ── Family Summary ────────────────────────────────────────────────────────────
total_nw = family.total_net_worth
st.metric("Total Family Net Worth", f"₹{float(total_nw / 10000000):.2f}Cr")

# ── Member Cards ──────────────────────────────────────────────────────────────
st.subheader("Member Profiles")
cols = st.columns(len(family.members))

for i, member in enumerate(family.members):
    with cols[i]:
        nw = float(member.net_worth / 100000)
        pct = float(member.net_worth / total_nw * 100) if total_nw else 0
        ltcg_left = float(member.ltcg_exemption_remaining / 1000)

        with st.container(border=True):
            st.markdown(f"### {member.name}")
            st.caption(f"{member.relationship} | Slab: {int(member.tax_slab_rate * 100)}%")
            st.metric("Net Worth", f"₹{nw:.1f}L", delta=f"{pct:.1f}% of family")
            st.metric("LTCG Exemption Left", f"₹{ltcg_left:.0f}K")
            st.metric("YTD Realized LTCG", f"₹{float(member.ytd_realized_ltcg/1000):.1f}K")
            st.metric("YTD Realized STCG", f"₹{float(member.ytd_realized_stcg/1000):.1f}K")
            est_tax = (
                max(member.ytd_realized_ltcg - Decimal("125000"), Decimal("0")) * Decimal("0.125")
                + member.ytd_realized_stcg * Decimal("0.20")
                + member.ytd_realized_crypto * Decimal("0.30")
            )
            st.metric("Est. Tax This FY", f"₹{float(est_tax/1000):.1f}K")

st.divider()

# ── Member Selector ───────────────────────────────────────────────────────────
selected_member_id = st.selectbox(
    "Select Member for Detailed View",
    [m.member_id for m in family.members],
    format_func=lambda mid: next(m.name for m in family.members if m.member_id == mid)
)

member = family.get_member(selected_member_id)
if not member or not member.portfolio:
    st.error("No portfolio data.")
    st.stop()

portfolio = member.portfolio
lots = portfolio.lots

st.subheader(f"📊 {member.name}'s Portfolio")

# ── Asset Allocation ──────────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    asset_vals = portfolio.asset_class_values()
    df_alloc = pd.DataFrame([
        {"Asset": k.replace("_", " ").title(), "Value (₹L)": float(v / 100000)}
        for k, v in asset_vals.items() if v > 0
    ])
    if not df_alloc.empty:
        fig = px.pie(df_alloc, values="Value (₹L)", names="Asset", hole=0.35,
                     color_discrete_sequence=px.colors.qualitative.Pastel)
        fig.update_layout(height=300, margin=dict(t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)

with col_right:
    # Long-term vs short-term
    from core.models import AssetClass
    lt_value = sum(l.current_value for l in lots if l.is_long_term and l.asset_class != AssetClass.CRYPTO)
    st_value = sum(l.current_value for l in lots if not l.is_long_term and l.asset_class != AssetClass.CRYPTO)
    crypto_value = sum(l.current_value for l in lots if l.asset_class == AssetClass.CRYPTO)

    fig2 = go.Figure(go.Bar(
        x=["Long-Term Equity", "Short-Term Equity", "Crypto"],
        y=[float(lt_value / 100000), float(st_value / 100000), float(crypto_value / 100000)],
        marker_color=["#2ecc71", "#e67e22", "#9b59b6"],
        text=[f"₹{float(lt_value/100000):.1f}L", f"₹{float(st_value/100000):.1f}L", f"₹{float(crypto_value/100000):.1f}L"],
        textposition="outside",
    ))
    fig2.update_layout(
        title="LTCG vs STCG vs Crypto Classification",
        height=300, margin=dict(t=40, b=0),
        yaxis_title="Value (₹L)",
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Holdings Table ────────────────────────────────────────────────────────────
st.subheader("Holdings")
lots_data = [{
    "Symbol": l.symbol,
    "Type": l.asset_class.value.replace("_", " "),
    "Platform": l.platform.value.title(),
    "Qty": float(l.quantity),
    "Cost/unit (₹)": float(l.cost_basis_per_unit),
    "Current (₹)": float(l.current_price),
    "Value (₹L)": round(float(l.current_value / 100000), 2),
    "P&L (₹)": round(float(l.unrealized_gain), 0),
    "P&L %": float(l.unrealized_gain_pct),
    "Days Held": l.holding_days,
    "Tax Status": "LTCG ✅" if l.is_long_term else f"STCG ({l.days_to_long_term}d to LTCG)",
} for l in lots]

df_lots = pd.DataFrame(lots_data)
st.dataframe(df_lots, use_container_width=True, hide_index=True)

st.divider()

# ── Comparison Chart ──────────────────────────────────────────────────────────
st.subheader("📊 Family Wealth Comparison")
comparison_data = []
for m in family.members:
    if not m.portfolio:
        continue
    av = m.portfolio.asset_class_values()
    for cls, val in av.items():
        if val > 0:
            comparison_data.append({
                "Member": m.name,
                "Asset Class": cls.replace("_", " ").title(),
                "Value (₹L)": float(val / 100000),
            })

df_comp = pd.DataFrame(comparison_data)
if not df_comp.empty:
    fig3 = px.bar(
        df_comp, x="Member", y="Value (₹L)", color="Asset Class",
        barmode="stack",
        color_discrete_sequence=px.colors.qualitative.Set3,
    )
    fig3.update_layout(height=400, margin=dict(t=10, b=0))
    st.plotly_chart(fig3, use_container_width=True)

st.divider()
st.caption("⚠️ Advisory only. Not SEBI-registered. Consult a CA before transacting.")
