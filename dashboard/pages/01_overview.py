"""
Portfolio Overview Page — Family net worth, allocations, top holdings.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from decimal import Decimal

st.set_page_config(page_title="Portfolio Overview — WealthMap", page_icon="📊", layout="wide")
st.title("📊 Portfolio Overview")

if "initialized" not in st.session_state:
    st.warning("Please start from the main app page.")
    st.stop()

family = st.session_state.family

# ── Key Metrics ───────────────────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)

total_nw = family.total_net_worth
all_lots = family.all_lots
total_gain = sum(l.unrealized_gain for l in all_lots)
total_cost = sum(l.total_cost_basis for l in all_lots)
gain_pct = (total_gain / total_cost * 100) if total_cost else Decimal("0")

col1.metric("Total Net Worth", f"₹{float(total_nw/10000000):.2f}Cr")
col2.metric("Total Cost Basis", f"₹{float(total_cost/10000000):.2f}Cr")
col3.metric("Unrealized Gain", f"₹{float(total_gain/100000):.1f}L",
            delta=f"{float(gain_pct):.1f}%")
col4.metric("Family Members", len(family.members))
col5.metric("Total Lots", len(all_lots))

st.divider()

# ── Asset Allocation ──────────────────────────────────────────────────────────
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("Asset Class Allocation")
    breakdown = family.asset_class_breakdown()
    df_alloc = pd.DataFrame([
        {
            "Asset Class": k.replace("_", " ").title(),
            "Value (₹L)": round(v["value_inr"] / 100000, 2),
            "% of Portfolio": v["pct_of_portfolio"],
        }
        for k, v in breakdown.items() if v["value_inr"] > 0
    ]).sort_values("Value (₹L)", ascending=False)

    fig_pie = px.pie(
        df_alloc, values="Value (₹L)", names="Asset Class",
        color_discrete_sequence=px.colors.qualitative.Set3,
        hole=0.4,
    )
    fig_pie.update_layout(height=350, margin=dict(t=20, b=0))
    st.plotly_chart(fig_pie, use_container_width=True)

with col_right:
    st.subheader("Allocation by Member")
    member_data = []
    for m in family.members:
        if m.portfolio:
            member_data.append({
                "Member": m.name,
                "Net Worth (₹L)": float(m.net_worth / 100000),
                "% of Family": float((m.net_worth / total_nw * 100).quantize(Decimal("0.01"))) if total_nw else 0,
            })
    df_members = pd.DataFrame(member_data)
    fig_bar = px.bar(
        df_members, x="Member", y="Net Worth (₹L)",
        color="Member", text="% of Family",
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig_bar.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_bar.update_layout(height=350, showlegend=False, margin=dict(t=20, b=0))
    st.plotly_chart(fig_bar, use_container_width=True)

# ── Allocation Table ──────────────────────────────────────────────────────────
st.subheader("Allocation Details")
st.dataframe(df_alloc, use_container_width=True, hide_index=True)

st.divider()

# ── Holdings Table ────────────────────────────────────────────────────────────
st.subheader("All Holdings")

lots_data = []
for lot in all_lots:
    lots_data.append({
        "Symbol": lot.symbol,
        "Asset Class": lot.asset_class.value.replace("_", " "),
        "Member": lot.member_id.title(),
        "Platform": lot.platform.value.title(),
        "Quantity": float(lot.quantity),
        "Cost (₹)": float(lot.cost_basis_per_unit),
        "Current (₹)": float(lot.current_price),
        "Value (₹L)": round(float(lot.current_value / 100000), 2),
        "P&L (₹)": round(float(lot.unrealized_gain), 0),
        "P&L %": float(lot.unrealized_gain_pct),
        "Holding Days": lot.holding_days,
        "Status": "LTCG ✅" if lot.is_long_term else f"STCG ⏳ ({lot.days_to_long_term}d)",
    })

df_lots = pd.DataFrame(lots_data)

# Color P&L column
def color_pnl(val):
    color = "green" if val > 0 else ("red" if val < 0 else "gray")
    return f"color: {color}"

# Filter controls
col_f1, col_f2 = st.columns(2)
with col_f1:
    member_filter = st.selectbox("Filter by Member", ["All"] + [m.member_id.title() for m in family.members])
with col_f2:
    class_filter = st.selectbox("Filter by Asset Class", ["All", "Equity", "Crypto", "Mutual Fund", "Fixed Deposit", "Gold"])

filtered = df_lots.copy()
if member_filter != "All":
    filtered = filtered[filtered["Member"] == member_filter]
if class_filter != "All":
    filtered = filtered[filtered["Asset Class"].str.contains(class_filter, case=False)]

st.dataframe(
    filtered.style.applymap(color_pnl, subset=["P&L %"]),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# ── Concentration Risks ───────────────────────────────────────────────────────
st.subheader("⚠️ Concentration Risks")
risks = family.concentration_risks()
if risks:
    for risk in risks:
        level = risk["risk_level"]
        icon = "🔴" if level == "HIGH" else "🟡"
        st.warning(f"{icon} **{risk['symbol']}**: {risk['portfolio_pct']:.1f}% of portfolio "
                   f"(₹{risk['value_inr']/100000:.1f}L) — {risk['recommendation']}")
else:
    st.success("✅ No single position exceeds the 15% concentration threshold.")
