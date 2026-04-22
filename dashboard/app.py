"""
WealthMap Streamlit Dashboard — main entry point.
Run: streamlit run dashboard/app.py
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
from decimal import Decimal

st.set_page_config(
    page_title="WealthMap 🗺️",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Shared State Init ─────────────────────────────────────────────────────────

@st.cache_resource
def init_app():
    """Initialize family data once and cache it."""
    from config.settings import get_settings
    from core.aggregator.normalizer import PortfolioNormalizer
    from core.family.family_unit import FamilyUnit, FamilyMember
    from core.ai.cfo_engine import CFOEngine
    from core.ai.context_builder import CFOContextBuilder
    from core.tax.lot_tracker import LotTracker

    settings = get_settings()
    normalizer = PortfolioNormalizer(settings)
    cfo = CFOEngine(api_key=settings.gemini_api_key)
    context_builder = CFOContextBuilder()
    tracker = LotTracker()

    family = FamilyUnit(family_name="Demo Family")
    member_configs = [
        ("father", "Rajesh Sharma", "SELF", Decimal("0.30"), Decimal("87000"), Decimal("23000"), Decimal("120000"), Decimal("52000")),
        ("mother", "Priya Sharma", "SPOUSE", Decimal("0.30"), Decimal("15000"), Decimal("5000"), Decimal("0"), Decimal("6000")),
        ("son", "Arjun Sharma", "CHILD", Decimal("0.20"), Decimal("8000"), Decimal("2000"), Decimal("0"), Decimal("2000")),
    ]

    for mid, name, rel, slab, ltcg, stcg, crypto, tax_paid in member_configs:
        snapshot = normalizer.build_demo_snapshot(mid)
        member = FamilyMember(
            member_id=mid, name=name, relationship=rel,
            tax_slab_rate=slab, portfolio=snapshot,
            ytd_realized_ltcg=ltcg, ytd_realized_stcg=stcg,
            ytd_realized_crypto=crypto, ytd_tax_paid=tax_paid,
        )
        family.add_member(member)
        for lot in snapshot.lots:
            tracker.add_lot(lot)

    return family, cfo, context_builder, tracker, settings

# Store in session state
if "initialized" not in st.session_state:
    with st.spinner("Initializing WealthMap..."):
        family, cfo, ctx_builder, tracker, settings = init_app()
        st.session_state.family = family
        st.session_state.cfo = cfo
        st.session_state.ctx_builder = ctx_builder
        st.session_state.tracker = tracker
        st.session_state.settings = settings
        st.session_state.initialized = True

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🗺️ WealthMap")
    st.caption("AI-Powered Portfolio Intelligence")
    st.divider()

    family = st.session_state.family
    total_nw = family.total_net_worth
    st.metric("Family Net Worth", f"₹{float(total_nw/10000000):.2f} Cr")

    st.divider()
    st.caption("Navigate using the pages in the sidebar ↑")
    st.divider()

    # Quick alerts
    from core.alerts.ltcg_watcher import LTCGWatcher
    watcher = LTCGWatcher()
    alerts = watcher.generate_alerts(family.all_lots)
    if alerts:
        st.error(f"⚡ {len(alerts)} Active Alert{'s' if len(alerts) > 1 else ''}")
        for a in alerts[:2]:
            st.warning(a["message"][:100] + "...")
    else:
        st.success("✅ No urgent alerts")

    st.divider()
    st.caption("⚠️ Advisory only. Not SEBI-registered.")
    st.caption("Verify with CA before transacting.")

# ── Home Page ─────────────────────────────────────────────────────────────────

st.title("🗺️ WealthMap — Family Portfolio Intelligence")
st.markdown("""
Welcome to **WealthMap** — your family's AI-powered CFO.

Navigate using the sidebar:
- 📊 **Portfolio Overview** — Net worth, allocation, concentration risks
- 🧾 **Tax Center** — LTCG/STCG, TLH, advance tax calendar
- 🤖 **CFO Chat** — Ask Claude anything about your portfolio
- 📅 **LTCG Calendar** — Upcoming unlock events and tax savings
- 👨‍👩‍👦 **Family View** — Per-member breakdown and comparison
""")

# Quick stats
col1, col2, col3, col4 = st.columns(4)
family = st.session_state.family

with col1:
    st.metric("Total Net Worth", f"₹{float(family.total_net_worth/10000000):.2f}Cr")

with col2:
    breakdown = family.asset_class_breakdown()
    equity_val = breakdown.get("EQUITY", {}).get("value_inr", 0)
    st.metric("Equity Holdings", f"₹{equity_val/100000:.1f}L")

with col3:
    crypto_val = breakdown.get("CRYPTO", {}).get("value_inr", 0)
    st.metric("Crypto Holdings", f"₹{crypto_val/100000:.1f}L")

with col4:
    tax_summary = family.ytd_tax_summary()
    est_tax = tax_summary.get("estimated_total_tax_inr", 0)
    st.metric("Est. FY Tax", f"₹{est_tax/100000:.1f}L")

st.divider()

# Asset allocation pie
st.subheader("Asset Allocation")
try:
    import plotly.express as px
    import pandas as pd
    breakdown = family.asset_class_breakdown()
    df = pd.DataFrame([
        {"Asset Class": k, "Value (₹L)": v["value_inr"] / 100000}
        for k, v in breakdown.items() if v["value_inr"] > 0
    ])
    if not df.empty:
        fig = px.pie(df, values="Value (₹L)", names="Asset Class",
                     color_discrete_sequence=px.colors.qualitative.Set3)
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=350)
        st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.warning(f"Chart unavailable: {e}")
