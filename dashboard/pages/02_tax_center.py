"""
Tax Center Page — LTCG/STCG liability, TLH scanner, sale simulator.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from decimal import Decimal

st.set_page_config(page_title="Tax Center — WealthMap", page_icon="🧾", layout="wide")
st.title("🧾 Tax Center")
st.caption("FY 2025-26 | LTCG: 12.5% above ₹1.25L | STCG: 20% | Crypto: 30% flat")

if "initialized" not in st.session_state:
    st.warning("Please start from the main app page.")
    st.stop()

family = st.session_state.family
tracker = st.session_state.tracker
from core.tax.tax_calendar import TaxCalendar
from core.tax.tlh_scanner import TLHScanner
from core.models import TaxConstants

calendar = TaxCalendar()
tlh = TLHScanner()

# ── YTD Tax Summary ───────────────────────────────────────────────────────────
st.subheader("📋 YTD Tax Position")
tax_summary = family.ytd_tax_summary()
members_tax = tax_summary.get("members", [])

cols = st.columns(len(members_tax) + 1)
for i, m in enumerate(members_tax):
    with cols[i]:
        st.metric(
            m["name"],
            f"₹{m['estimated_tax_inr']/100000:.2f}L est. tax",
            delta=f"₹{m['ltcg_exemption_remaining_inr']/1000:.0f}K LTCG exemption left",
        )
with cols[-1]:
    st.metric(
        "Family Total",
        f"₹{tax_summary['estimated_total_tax_inr']/100000:.2f}L",
        delta=None,
    )

st.info("ℹ️ LTCG exemption of ₹1,25,000 is **per individual per FY** — not shared across family members.")

st.divider()

# ── Member Tax Details ────────────────────────────────────────────────────────
st.subheader("Per-Member Tax Breakdown")
df_tax = pd.DataFrame(members_tax)
df_tax = df_tax.rename(columns={
    "name": "Member", "ytd_realized_ltcg_inr": "Realized LTCG (₹)",
    "ytd_realized_stcg_inr": "Realized STCG (₹)",
    "estimated_tax_inr": "Est. Tax (₹)",
    "ltcg_exemption_remaining_inr": "LTCG Exemption Left (₹)",
})
st.dataframe(df_tax[["Member", "Realized LTCG (₹)", "Realized STCG (₹)", "Est. Tax (₹)", "LTCG Exemption Left (₹)"]], 
             use_container_width=True, hide_index=True)

st.divider()

# ── Sale Simulator ────────────────────────────────────────────────────────────
st.subheader("🔬 Sale Tax Simulator")
st.caption("Simulate selling shares and see the exact tax impact before transacting.")

all_lots = family.all_lots
equity_symbols = list({l.symbol for l in all_lots if l.asset_class.value in ("EQUITY", "MUTUAL_FUND")})
equity_symbols.sort()

col_s1, col_s2, col_s3 = st.columns(3)
with col_s1:
    member_sel = st.selectbox("Member", [m.member_id for m in family.members], key="sim_member")
with col_s2:
    sym_sel = st.selectbox("Symbol", equity_symbols, key="sim_symbol")
with col_s3:
    # Get max quantity
    lots_for_sim = tracker.get_lots(member_sel, sym_sel)
    max_qty = float(sum(l.quantity for l in lots_for_sim)) if lots_for_sim else 0
    qty_sel = st.number_input("Quantity", min_value=1.0, max_value=max(max_qty, 1.0), value=min(10.0, max_qty or 10.0), step=1.0)

if st.button("🧮 Simulate Sale", type="primary"):
    lots = tracker.get_lots(member_sel, sym_sel)
    if not lots:
        st.error(f"No lots found for {sym_sel}")
    else:
        member = family.get_member(member_sel)
        current_price = lots[0].current_price
        try:
            result = tracker.simulate_sale(
                member_id=member_sel,
                symbol=sym_sel,
                quantity=Decimal(str(qty_sel)),
                sale_price=current_price,
                ytd_realized_ltcg=member.ytd_realized_ltcg,
            )

            # Display results
            sale_sum = result["sale_summary"]
            tax_sum = result["tax_summary"]
            advisory = result["advisory"]

            col_r1, col_r2, col_r3 = st.columns(3)
            col_r1.metric("Total Proceeds", f"₹{sale_sum['total_proceeds_inr']:,.0f}")
            col_r2.metric("Total Tax", f"₹{tax_sum['total_tax_inr']:,.0f}")
            col_r3.metric("Net Proceeds", f"₹{sale_sum['net_proceeds_after_tax_inr']:,.0f}")

            # Lot breakdown
            st.markdown("**Lot-by-Lot Breakdown:**")
            df_lots_sim = pd.DataFrame(result["lot_breakdown"])
            if not df_lots_sim.empty:
                st.dataframe(df_lots_sim[[
                    "lot_id", "quantity", "acquisition_date", "holding_days",
                    "classification", "gain_inr", "tax_rate", "total_tax_inr"
                ]], use_container_width=True, hide_index=True)

            # Advisory
            if advisory.get("wait_recommendation"):
                st.warning(f"⏳ **Wait Recommended**: {advisory['reason']}\n\n"
                           f"Potential saving: ₹{advisory.get('potential_saving_inr', 0):,.0f}")
            else:
                st.success(f"✅ {advisory['reason']}")

        except ValueError as e:
            st.error(str(e))

st.divider()

# ── TLH Scanner ───────────────────────────────────────────────────────────────
st.subheader("🔍 Tax Loss Harvesting Opportunities")
ytd_ltcg = sum(m.ytd_realized_ltcg for m in family.members)
ytd_stcg = sum(m.ytd_realized_stcg for m in family.members)
tlh_report = tlh.generate_report(all_lots, ytd_ltcg, ytd_stcg)

tlh_summary = tlh_report["summary"]
col_t1, col_t2, col_t3 = st.columns(3)
col_t1.metric("Opportunities Found", tlh_summary["opportunities_found"])
col_t2.metric("Total Potential Saving", f"₹{tlh_summary['total_potential_saving_inr']:,.0f}")
col_t3.metric("Harvestable Losses", f"₹{tlh_summary['total_harvestable_loss_inr']:,.0f}")

if tlh_report["opportunities"]:
    st.markdown("**Top TLH Opportunities:**")
    for opp in tlh_report["opportunities"][:5]:
        with st.expander(f"📉 {opp['loss_symbol']} — Save ₹{opp['net_tax_saving_inr']:,.0f}"):
            st.write(f"**Unrealized Loss:** ₹{opp['unrealized_loss_inr']:,.0f}")
            st.write(f"**Can offset gains in:** {', '.join(opp['can_offset_symbols'])}")
            for note in opp.get("risk_notes", []):
                st.caption(f"⚠️ {note}")

if tlh_report["crypto_loss_warnings"]:
    st.error("🚫 **Crypto Loss Warnings (Section 115BBH)**")
    for w in tlh_report["crypto_loss_warnings"]:
        st.warning(f"**{w['symbol']}**: Unrealized loss of ₹{w['unrealized_loss_inr']:,.0f} — {w['warning']}")

for note in tlh_report["important_notes"]:
    st.caption(f"📌 {note}")

st.divider()

# ── Advance Tax Calendar ──────────────────────────────────────────────────────
st.subheader("📅 Advance Tax Schedule")
est_tax = Decimal(str(tax_summary.get("estimated_total_tax_inr", 0)))
ytd_paid = sum(m.ytd_tax_paid for m in family.members)
schedule = calendar.advance_tax_dates(est_tax, ytd_paid)

if isinstance(schedule, list) and schedule and "note" not in schedule[0]:
    df_adv = pd.DataFrame(schedule)
    for _, row in df_adv.iterrows():
        status = row.get("status", "UPCOMING")
        icon = "🔴" if status == "OVERDUE" else ("🟡" if status == "DUE_SOON" else "🟢")
        st.write(f"{icon} **{row['installment']}** — Due: {row['due_date']} | "
                 f"Amount: ₹{row['installment_amount_inr']:,.0f} | "
                 f"Days: {row['days_until_due']}")
else:
    st.info("Advance tax not applicable — estimated liability ≤ ₹10,000.")
