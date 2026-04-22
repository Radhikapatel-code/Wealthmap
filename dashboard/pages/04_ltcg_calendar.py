"""
LTCG Calendar Page — Visual timeline of upcoming LTCG unlock events.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import date

st.set_page_config(page_title="LTCG Calendar — WealthMap", page_icon="📅", layout="wide")
st.title("📅 LTCG Unlock Calendar")
st.caption("Track positions approaching 12-month long-term status. LTCG rate: 12.5% vs STCG: 20%.")

if "initialized" not in st.session_state:
    st.warning("Please start from the main app page.")
    st.stop()

family = st.session_state.family
from core.tax.tax_calendar import TaxCalendar
calendar = TaxCalendar()

all_lots = family.all_lots

# ── Settings ──────────────────────────────────────────────────────────────────
look_ahead = st.slider("Look-ahead window (days)", min_value=7, max_value=365, value=90, step=7)

# ── LTCG Events ───────────────────────────────────────────────────────────────
events = calendar.ltcg_unlock_events(all_lots, look_ahead_days=look_ahead)

# Summary metrics
col1, col2, col3 = st.columns(3)
col1.metric("Unlocks in window", len(events))
col2.metric("Total Tax Saving", f"₹{sum(e['potential_saving_inr'] for e in events):,.0f}")
col3.metric("Worth waiting for", len([e for e in events if e['worth_waiting']]))

st.divider()

if not events:
    st.info(f"No LTCG unlock events in the next {look_ahead} days.")
else:
    # ── Timeline Chart ────────────────────────────────────────────────────────
    st.subheader("🗓️ Unlock Timeline")
    df_events = pd.DataFrame(events)
    df_events["unlock_date"] = pd.to_datetime(df_events["unlock_date"])
    df_events["Label"] = df_events.apply(
        lambda r: f"{r['symbol']} ({r['member_id']})", axis=1
    )

    fig = px.scatter(
        df_events,
        x="unlock_date",
        y="potential_saving_inr",
        size="unrealized_gain_inr",
        color="member_id",
        hover_name="symbol",
        hover_data=["days_remaining", "quantity", "potential_saving_inr"],
        labels={
            "unlock_date": "Unlock Date",
            "potential_saving_inr": "Tax Saving (₹)",
            "member_id": "Member",
        },
        title=f"LTCG Unlock Events — Next {look_ahead} Days",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.add_vline(x=date.today().isoformat(), line_dash="dash", line_color="red",
                  annotation_text="Today")
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

    # ── Detailed Table ────────────────────────────────────────────────────────
    st.subheader("📋 Unlock Details")
    df_display = df_events[[
        "symbol", "member_id", "days_remaining", "unlock_date",
        "quantity", "unrealized_gain_inr", "stcg_tax_if_sold_today_inr",
        "ltcg_tax_after_unlock_inr", "potential_saving_inr", "worth_waiting",
    ]].copy()
    df_display.columns = [
        "Symbol", "Member", "Days Left", "Unlock Date",
        "Qty", "Unrealized Gain (₹)", "STCG Tax Now (₹)",
        "LTCG Tax After (₹)", "Tax Saving (₹)", "Worth Waiting?",
    ]
    df_display["Worth Waiting?"] = df_display["Worth Waiting?"].apply(lambda x: "✅ Yes" if x else "❌ No")
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ── Urgent Alerts ─────────────────────────────────────────────────────────
    urgent = [e for e in events if e["days_remaining"] <= 7 and e["worth_waiting"]]
    if urgent:
        st.divider()
        st.subheader("⚡ Urgent — Unlock Within 7 Days")
        for e in urgent:
            st.error(
                f"🔴 **{e['symbol']}** ({e['member_id']}) unlocks in **{e['days_remaining']} days** "
                f"({e['unlock_date']}). Do NOT sell before then. "
                f"Tax saving: ₹{e['potential_saving_inr']:,.0f}"
            )

st.divider()

# ── Key Tax Dates ─────────────────────────────────────────────────────────────
st.subheader("📆 Key Tax Dates — FY 2025-26")
key_dates = calendar.key_dates_this_fy()

for d in key_dates:
    status = d.get("status")
    icon = "✅" if status == "PAST" else ("⏰" if status == "DUE_SOON" else "📅")
    color = "green" if status == "PAST" else "normal"
    category = d.get("category", "")
    cat_icon = {"ADVANCE_TAX": "💰", "FY_BOUNDARY": "📊", "ITR": "📝"}.get(category, "📌")

    col_d1, col_d2, col_d3 = st.columns([1, 2, 4])
    with col_d1:
        st.write(f"{icon} {d['date']}")
    with col_d2:
        st.write(f"{cat_icon} {d['event']}")
    with col_d3:
        st.caption(d["description"])
