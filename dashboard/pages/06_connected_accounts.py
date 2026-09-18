"""
Connected Accounts & Integrations Page — WealthMap.
Allows HNI families to connect, monitor, synchronize, and manage multi-platform accounts.
"""
import sys
sys.path.insert(0, ".")

import streamlit as st
import pandas as pd
from datetime import datetime
from decimal import Decimal

from core.connectors.models import SyncStatus
from core.connectors.providers.zerodha import ZerodhaConnector
from core.connectors.providers.binance import BinanceConnector
from core.connectors.providers.coindcx import CoinDCXConnector
from core.connectors.providers.alpaca import AlpacaConnector
from core.connectors.providers.csv_statement import CSVStatementConnector
from core.connectors.providers.upstox import UpstoxConnector
from core.connectors.providers.angel_one import AngelOneConnector
from core.connectors.providers.wazirx import WazirXConnector
from core.connectors.providers.upstox import UpstoxConnector
from core.connectors.providers.angel_one import AngelOneConnector
from core.connectors.providers.wazirx import WazirXConnector

st.set_page_config(page_title="Connected Accounts — WealthMap", page_icon="🔗", layout="wide")
st.title("🔗 Connected Accounts & Integrations")
st.caption("Live portfolio feeds and statement aggregation for all family members. Read-only permissions enforced.")

if "initialized" not in st.session_state:
    st.warning("Please launch from the main app page.")
    st.stop()

family = st.session_state.family
tracker = st.session_state.tracker
settings = st.session_state.settings

# Initialize or retrieve state manager's sync engine
from core.state_manager import get_state_manager
state_mgr = get_state_manager()
sync_engine = state_mgr.get_sync_engine("default")

# ── Summary Metrics Bar ────────────────────────────────────────────────────────
accounts = sync_engine.list_accounts()
connected_count = sum(1 for a in accounts if a.status == SyncStatus.CONNECTED)
total_accounts = len(accounts)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Connected Feeds", f"{connected_count} Active", delta=f"{total_accounts} Configured")
col2.metric("Family Members Covered", f"{len({a.family_member_id for a in accounts if a.family_member_id})} Members")
col3.metric("Supported Connectors", "7 Providers")
col4.metric("Security Level", "AES-256 / Read-Only", delta="No Trading Scope")

st.divider()

# ── Provider Status Cards ──────────────────────────────────────────────────────
st.subheader("Configured Financial Accounts")

tabs = st.tabs(["Active & Available Accounts", "➕ Connect New Platform", "📄 Import Statement (CSV / CAS)", "ℹ️ Integration Feasibility Guide"])

with tabs[0]:
    # Provider metadata registry
    providers_catalog = [
        {
            "id": "zerodha",
            "name": "Zerodha Kite Connect",
            "asset_type": "Indian Equity & F&O",
            "icon": "📈",
            "default_member": "father",
            "configured": bool(settings.kite_api_key and settings.kite_access_token),
            "auth_type": "Daily Access Token (TOTP)",
        },
        {
            "id": "binance",
            "name": "Binance Global",
            "asset_type": "Crypto & Stablecoins",
            "icon": "🪙",
            "default_member": "father",
            "configured": bool(settings.binance_api_key and settings.binance_api_secret),
            "auth_type": "HMAC-SHA256 API Key",
        },
        {
            "id": "coindcx",
            "name": "CoinDCX",
            "asset_type": "Indian Crypto (INR Pairs)",
            "icon": "🇮🇳",
            "default_member": "son",
            "configured": bool(settings.coindcx_api_key and settings.coindcx_api_secret),
            "auth_type": "HMAC-SHA256 API Key",
        },
        {
            "id": "upstox",
            "name": "Upstox UpLink API",
            "asset_type": "Indian Equity & F&O",
            "icon": "⬆️",
            "default_member": "father",
            "configured": bool(settings.upstox_api_key and settings.upstox_api_secret and settings.upstox_redirect_uri),
            "auth_type": "OAuth 2.0",
        },
        {
            "id": "angel_one",
            "name": "Angel One SmartAPI",
            "asset_type": "Indian Equity & F&O",
            "icon": "👼",
            "default_member": "mother",
            "configured": bool(settings.angel_one_api_key and settings.angel_one_client_code and settings.angel_one_password),
            "auth_type": "API Key + TOTP",
        },
        {
            "id": "wazirx",
            "name": "WazirX",
            "asset_type": "Indian Crypto (INR Pairs)",
            "icon": "🇮🇳",
            "default_member": "son",
            "configured": bool(settings.wazirx_api_key and settings.wazirx_api_secret),
            "auth_type": "HMAC-SHA256 API Key",
        },
        {
            "id": "alpaca",
            "name": "Alpaca Markets",
            "asset_type": "US Equities & ETFs (LRS)",
            "icon": "🗽",
            "default_member": "father",
            "configured": False,
            "auth_type": "APCA Key ID + Secret",
        },
        {
            "id": "groww",
            "name": "Groww Statements",
            "asset_type": "Indian Equity & Mutual Funds",
            "icon": "🌱",
            "default_member": "mother",
            "configured": True,
            "auth_type": "P&L / Holdings CSV Import",
        },
        {
            "id": "amfi",
            "name": "AMFI Official NAV Feed",
            "asset_type": "Mutual Fund Valuation Data",
            "icon": "🏛️",
            "default_member": "all",
            "configured": True,
            "auth_type": "Public Open Data (Free)",
        },
    ]

    cols = st.columns(3)
    for idx, p in enumerate(providers_catalog):
        with cols[idx % 3]:
            with st.container(border=True):
                # Header
                st.markdown(f"### {p['icon']} {p['name']}")
                st.caption(f"**Asset Class**: {p['asset_type']}")
                st.caption(f"**Auth Type**: {p['auth_type']}")

                # Find registered connector
                matching_conn_id = next(
                    (cid for cid, c in sync_engine.list_connectors().items() if c.provider_id == p["id"]),
                    None
                )
                conn = sync_engine.list_connectors().get(matching_conn_id) if matching_conn_id else None

                if conn:
                    status = conn.status
                    if status == SyncStatus.CONNECTED:
                        st.success("● Connected ✓", icon="🟢")
                    elif status == SyncStatus.AUTH_EXPIRED:
                        st.warning("● Token Expired", icon="🟠")
                    elif status == SyncStatus.RATE_LIMITED:
                        st.warning("● Rate Limited", icon="🟡")
                    elif status == SyncStatus.SYNC_FAILED:
                        st.error("● Sync Failed", icon="🔴")
                    else:
                        st.info(f"● {status.value}", icon="⚪")

                    accs = conn.get_accounts()
                    acc = accs[0] if accs else None
                    if acc:
                        st.markdown(f"**Account**: `{acc.masked_identifier or 'Linked'}`")
                        st.markdown(f"**Assigned To**: {acc.family_member_id.title()}")

                    last_sync = conn.last_synced_at.strftime('%d-%b %H:%M') if conn.last_synced_at else "Not yet synced"
                    st.caption(f"Last sync: {last_sync}")

                    if conn.last_error:
                        st.error(f"⚠️ {conn.last_error}")

                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("🔄 Sync Now", key=f"sync_{p['id']}", use_container_width=True):
                            with st.spinner(f"Synchronizing {p['name']}..."):
                                res = sync_engine.sync_connector(matching_conn_id)
                                if res.status == SyncStatus.SYNC_SUCCESS:
                                    st.toast(f"Synced {res.holdings_count} holdings from {p['name']}!")
                                    st.rerun()
                                else:
                                    st.error(res.error_message or "Sync failed.")
                    with btn_col2:
                        if st.button("🔌 Disconnect", key=f"disc_{p['id']}", use_container_width=True):
                            sync_engine.unregister_connector(matching_conn_id)
                            st.toast(f"Disconnected {p['name']}")
                            st.rerun()
                else:
                    st.info("● Not Configured", icon="⚪")
                    st.caption("No active API credentials found.")
                    st.markdown(f"**Default Member**: {p['default_member'].title()}")
                    st.button("⚙️ Connect Feed", key=f"setup_{p['id']}", use_container_width=True, disabled=False)

with tabs[1]:
    st.subheader("Connect an External Broker or Exchange")
    st.caption("All credentials are saved locally or in memory and never transmitted to third parties or AI.")

    with st.form("connect_platform_form"):
        f_provider = st.selectbox(
            "Select Provider",
            ["Zerodha Kite Connect", "Binance Global", "CoinDCX", "Upstox UpLink API", "Angel One SmartAPI", "WazirX", "Alpaca US Equities"],
        )
        f_member = st.selectbox(
            "Assign to Family Member",
            [m.member_id for m in family.members],
            format_func=lambda mid: f"{next(m.name for m in family.members if m.member_id == mid)} ({mid.title()})",
        )

        if "Zerodha" in f_provider:
            st.info("Requires Kite Connect Developer credentials. Token expires daily at 6:00 AM IST.")
            api_key = st.text_input("Kite API Key", type="password")
            access_token = st.text_input("Kite Daily Access Token", type="password")
            client_id = st.text_input("Zerodha Client Code (e.g. RA1234)", placeholder="RA1234")
            api_secret = ""
        elif "Binance" in f_provider:
            st.info("Generate a READ-ONLY API key in Binance API Management. Enable IP restriction for security.")
            api_key = st.text_input("Binance API Key", type="password")
            api_secret = st.text_input("Binance API Secret", type="password")
            access_token = ""
            client_id = ""
        elif "CoinDCX" in f_provider:
            st.info("Generate API Key in CoinDCX Profile > Security. Ensure Read permission is enabled.")
            api_key = st.text_input("CoinDCX API Key", type="password")
            api_secret = st.text_input("CoinDCX Secret Key", type="password")
            access_token = ""
            client_id = ""
        elif "Alpaca" in f_provider:
            st.info("Generate an API Key ID and Secret in your Alpaca Dashboard.")
            api_key = st.text_input("Alpaca API Key ID", type="password")
            api_secret = st.text_input("Alpaca Secret Key", type="password")
            access_token = ""
            client_id = ""
        elif "Upstox" in f_provider:
            st.info("Create an UpLink app for free at upstox.com/developer. OAuth 2.0 flow with 24-hour token validity.")
            api_key = st.text_input("Upstox API Key", type="password")
            api_secret = st.text_input("Upstox API Secret", type="password")
            redirect_uri = st.text_input("Redirect URI (e.g., http://localhost:8501)")
            access_token = st.text_input("Access Token (if already obtained)", type="password")
            client_id = ""
        elif "Angel One" in f_provider:
            st.info("SmartAPI is completely free. Requires Client Code, PIN, and TOTP for authentication.")
            api_key = st.text_input("Angel One API Key", type="password")
            client_id = st.text_input("Angel One Client Code")
            api_secret = st.text_input("Angel One Password (PIN)", type="password")
            redirect_uri = st.text_input("TOTP Secret (optional, for auto-generation)", type="password")
            access_token = ""
        elif "WazirX" in f_provider:
            st.info("Generate HMAC-SHA256 API keys in WazirX dashboard. Indian exchange with INR pairs.")
            api_key = st.text_input("WazirX API Key", type="password")
            api_secret = st.text_input("WazirX API Secret", type="password")
            access_token = ""
            client_id = ""
            redirect_uri = ""

        submitted = st.form_submit_button("Test & Connect Account", use_container_width=True)
        if submitted:
            if not api_key:
                st.error("Please provide the required API key.")
            else:
                with st.spinner("Validating credentials with remote provider..."):
                    try:
                        if "Zerodha" in f_provider:
                            conn = ZerodhaConnector(api_key, access_token, member_id=f_member, client_id=client_id)
                            cid = f"zerodha_{f_member}"
                        elif "Binance" in f_provider:
                            conn = BinanceConnector(api_key, api_secret, member_id=f_member)
                            cid = f"binance_{f_member}"
                        elif "CoinDCX" in f_provider:
                            conn = CoinDCXConnector(api_key, api_secret, member_id=f_member)
                            cid = f"coindcx_{f_member}"
                        elif "Alpaca" in f_provider:
                            conn = AlpacaConnector(api_key, api_secret, member_id=f_member)
                            cid = f"alpaca_{f_member}"
                        elif "Upstox" in f_provider:
                            conn = UpstoxConnector(api_key, api_secret, redirect_uri, member_id=f_member, access_token=access_token)
                            cid = f"upstox_{f_member}"
                        elif "Angel One" in f_provider:
                            conn = AngelOneConnector(api_key, client_id, api_secret, redirect_uri, member_id=f_member)
                            cid = f"angel_one_{f_member}"
                        elif "WazirX" in f_provider:
                            conn = WazirXConnector(api_key, api_secret, member_id=f_member)
                            cid = f"wazirx_{f_member}"

                        auth_ok = conn.authenticate()
                        if auth_ok:
                            sync_engine.register_connector(cid, conn)
                            st.success(f"Successfully connected to {f_provider} for {f_member.title()}!")
                            st.rerun()
                        else:
                            st.error(conn.last_error or "Authentication failed. Check your API credentials.")
                    except Exception as exc:
                        st.error(f"Connection test error: {exc}")

with tabs[2]:
    st.subheader("Statement Ingestion (CSV / CAS)")
    st.markdown("""
    For platforms without public retail APIs (e.g. **Groww**, **CAMS / KFintech CAS**, or broker tradebooks),
    upload your statement file to import holdings with lot-level purchase dates and cost basis.
    """)

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        stmt_provider = st.selectbox(
            "Statement Source",
            ["Groww Stocks / Mutual Funds", "CAMS / KFintech Consolidated Account Statement (CAS)", "Zerodha Console Tradebook", "Generic Portfolio CSV"],
        )
    with col_s2:
        stmt_member = st.selectbox(
            "Assign Holdings To",
            [m.member_id for m in family.members],
            format_func=lambda mid: f"{next(m.name for m in family.members if m.member_id == mid)} ({mid.title()})",
            key="stmt_member_select",
        )

    uploaded_file = st.file_uploader("Upload CSV Statement", type=["csv", "txt"])

    sample_csv_text = """Symbol,ISIN,Quantity,Average Cost,Current Price,Asset Class,Buy Date
INFY.NS,INE009A01021,150,1420.00,1680.00,EQUITY,2023-04-10
HDFCBANK.NS,INE040A01034,100,1550.00,1720.00,EQUITY,2022-11-15
HDFC_INDEX_NIFTY50,INF179K01BE2,1200,42.50,58.20,MUTUAL_FUND,2023-01-10
PHYSICAL_GOLD,,50,5200.00,6900.00,GOLD,2021-08-20"""

    st.caption("CSV header format supported: `Symbol`, `ISIN`, `Quantity`, `Average Cost`, `Current Price`, `Asset Class`, `Buy Date`")
    with st.expander("Show Sample CSV Template"):
        st.code(sample_csv_text, language="csv")

    if uploaded_file is not None:
        try:
            content = uploaded_file.getvalue().decode("utf-8")
            st.success(f"Loaded file: {uploaded_file.name} ({len(content)} bytes)")

            if st.button("Parse and Ingest Statement", type="primary"):
                with st.spinner("Parsing statement and generating tax lots..."):
                    prov_key = "groww" if "Groww" in stmt_provider else "cams" if "CAMS" in stmt_provider else "custom"
                    conn = CSVStatementConnector(provider_name=prov_key, member_id=stmt_member)
                    holdings = conn.parse_holdings_csv(content)
                    sync_engine.register_connector(f"{prov_key}_{stmt_member}", conn)

                    member = family.get_member(stmt_member)
                    if member and member.portfolio:
                        for h in holdings:
                            lot = sync_engine.canonical_to_asset_lot(h, stmt_member)
                            member.portfolio.lots.append(lot)
                            tracker.add_lot(lot)

                    st.success(f"Successfully ingested {len(holdings)} holdings into {stmt_member.title()}'s portfolio!")
                    st.rerun()
        except Exception as err:
            st.error(f"Failed to parse statement: {err}")

with tabs[3]:
    st.subheader("Integration Feasibility Matrix & Engineering Analysis")
    st.markdown("""
    WealthMap maintains strict engineering standards: **no fake APIs, no credential scraping, and full compliance with Indian regulatory frameworks.**
    Below is our audited classification of retail financial data sources:
    """)

    matrix_data = [
        {"Provider": "Zerodha (Kite Connect)", "Asset Class": "Equity & F&O", "Retail API": "Yes", "Auth Mechanism": "API Key + Daily TOTP", "Status": "IMPLEMENTABLE NOW", "Notes": "Paid developer portal (₹2000/mo). Access token expires daily."},
        {"Provider": "Binance", "Asset Class": "Crypto", "Retail API": "Yes", "Auth Mechanism": "HMAC-SHA256 API Key", "Status": "IMPLEMENTABLE NOW", "Notes": "Read-only keys with IP whitelisting. Full trade history."},
        {"Provider": "CoinDCX", "Asset Class": "Crypto (INR)", "Retail API": "Yes", "Auth Mechanism": "HMAC-SHA256 Signed REST", "Status": "IMPLEMENTABLE NOW", "Notes": "Native Indian exchange with public signed balance/trade endpoints."},
        {"Provider": "Alpaca", "Asset Class": "US Equity", "Retail API": "Yes", "Auth Mechanism": "API Key ID + Secret Key", "Status": "IMPLEMENTABLE NOW", "Notes": "Enables automated sync for Indian HNIs investing via RBI LRS."},
        {"Provider": "AMFI India", "Asset Class": "Mutual Funds", "Retail API": "Yes", "Auth Mechanism": "Public Open Data", "Status": "IMPLEMENTABLE NOW", "Notes": "Free official daily NAVs for all registered Indian mutual fund schemes."},
        {"Provider": "Upstox (UpLink)", "Asset Class": "Equity & F&O", "Retail API": "Yes", "Auth Mechanism": "OAuth 2.0 Auth Code", "Status": "IMPLEMENTABLE WITH USER CREDENTIALS", "Notes": "Open retail developer portal. Token valid for 24 hours."},
        {"Provider": "Angel One (SmartAPI)", "Asset Class": "Equity & F&O", "Retail API": "Yes", "Auth Mechanism": "API Key + MPIN + TOTP", "Status": "IMPLEMENTABLE WITH USER CREDENTIALS", "Notes": "Free developer portal. Can automate session generation via TOTP."},
        {"Provider": "Interactive Brokers", "Asset Class": "Global Equity", "Retail API": "Yes", "Auth Mechanism": "Flex Query Web Token", "Status": "IMPLEMENTABLE WITH USER CREDENTIALS", "Notes": "Retail users generate Flex Query Tokens to download XML/CSV account statements."},
        {"Provider": "Groww", "Asset Class": "Equity & MF", "Retail API": "No", "Auth Mechanism": "None (No Public API)", "Status": "BETTER HANDLED THROUGH CSV IMPORT", "Notes": "No retail developer API. Scraping violates TOS and requires SMS OTP interception."},
        {"Provider": "CAMS / KFintech", "Asset Class": "Mutual Funds", "Retail API": "No", "Auth Mechanism": "B2B Only", "Status": "BETTER HANDLED THROUGH CSV IMPORT", "Notes": "No retail REST API. Industry standard is e-CAS PDF/Excel delivered via email."},
        {"Provider": "MF Central", "Asset Class": "Mutual Funds", "Retail API": "Yes", "Auth Mechanism": "Institutional B2B Agreement", "Status": "REQUIRES PARTNERSHIP / INSTITUTIONAL ACCESS", "Notes": "Joint CAMS/KFintech platform requires SEBI/AMFI RIA accreditation and commercial contract."},
        {"Provider": "Indian Retail Banks", "Asset Class": "Bank Accounts / FDs", "Retail API": "No", "Auth Mechanism": "RBI Account Aggregator (AA)", "Status": "REQUIRES PARTNERSHIP / INSTITUTIONAL ACCESS", "Notes": "Direct scraping is prohibited. RBI AA ecosystem (Setu/Sahamati) requires certified FIU license."},
    ]

    df_matrix = pd.DataFrame(matrix_data)
    st.dataframe(df_matrix, use_container_width=True, hide_index=True)
