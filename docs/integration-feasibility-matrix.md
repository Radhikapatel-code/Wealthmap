# WealthMap Integration Feasibility Matrix

**Last Updated:** 2026-09-18  
**Purpose:** Honest engineering assessment of financial data integration feasibility for Indian HNI portfolios

## Executive Summary

This matrix provides a transparent, technically rigorous assessment of financial data integration options for WealthMap. Each provider is classified based on:
- **Technical Feasibility:** Can the integration be built with available APIs?
- **Retail Access:** Can individual investors obtain the necessary credentials?
- **Data Completeness:** Does the API provide the data WealthMap needs?
- **Regulatory/Legal Constraints:** Are there terms, compliance, or partnership requirements?

**Classification Standards:**
- **IMPLEMENTABLE NOW:** API exists, retail credentials available, data sufficient, no partnership needed
- **IMPLEMENTABLE WITH USER CREDENTIALS:** API exists but requires user to obtain specific credentials/approval
- **REQUIRES PARTNERSHIP / INSTITUTIONAL ACCESS:** API restricted to approved partners or requires commercial agreement
- **NOT PRACTICALLY INTEGRATABLE:** No suitable API, terms prohibit access, or technical barriers
- **BETTER HANDLED THROUGH CSV/STATEMENT IMPORT:** API unavailable but statement import is viable

---

## Indian Equity Brokers

| Provider | Asset Type | API Available? | Retail Access? | OAuth? | API Keys? | Holdings | Transactions | Dividends | Historical Data | Difficulty | Status | Notes |
|----------|------------|----------------|----------------|--------|-----------|----------|--------------|-----------|----------------|------------|--------|-------|
| **Zerodha (Kite Connect)** | Equity & F&O | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes | ❌ Limited | ✅ Yes (Paid) | Medium | **IMPLEMENTABLE NOW** | Paid developer portal (₹2000/mo). Access token expires daily at 6:00 AM IST via TOTP. Holdings endpoint returns positions with average cost. Trade history available. Historical data requires separate add-on. |
| **Upstox (UpLink API v2)** | Equity & F&O | ✅ Yes | ✅ Yes | ✅ Yes (OAuth 2.0) | ✅ Yes | ✅ Yes | ✅ Yes | ❌ Limited | ✅ Yes | Medium | **IMPLEMENTABLE WITH USER CREDENTIALS** | Free developer portal. OAuth 2.0 flow with daily token expiration. Sandbox environment available. Holdings and trade history endpoints well-documented. 90-day zero brokerage for new API users (as of Aug 2024). |
| **Angel One (SmartAPI)** | Equity & F&O | ✅ Yes | ✅ Yes | ⚠️ Hybrid (TOTP + API Key) | ✅ Yes | ✅ Yes | ✅ Yes | ❌ Limited | ✅ Yes | Medium | **IMPLEMENTABLE WITH USER CREDENTIALS** | Completely free API. Authentication requires client code, PIN, and TOTP. Session valid till midnight. Token refresh available. Holdings and order history endpoints available. Strong community documentation. |
| **ICICI Direct (Breeze API)** | Equity & F&O | ✅ Yes | ✅ Yes | ✅ Yes (OAuth 2.0) | ✅ Yes | ✅ Yes | ✅ Yes | ❌ Limited | ✅ Yes (3 years) | Medium | **IMPLEMENTABLE WITH USER CREDENTIALS** | Free API access for all ICICI Direct customers. OAuth 2.0 authentication. Static IP registration required (can be updated once/week). Market orders not permitted via API. 10 orders/second rate limit. Excellent historical data (3 years LTP). |
| **HDFC Securities (Sky API)** | Equity & F&O | ✅ Yes | ✅ Yes | ✅ Yes (OAuth 2.0) | ✅ Yes | ✅ Yes | ✅ Yes | ❌ Limited | ✅ Yes | Medium | **IMPLEMENTABLE WITH USER CREDENTIALS** | Free API access via InvestRight developer portal. OAuth 2.0 authentication. Real-time WebSocket market data. Portfolio and transaction endpoints available. Static IP whitelisting required. |
| **5paisa (Xstream API)** | Equity & F&O | ✅ Yes | ✅ Yes | ✅ Yes (Bearer Token) | ✅ Yes | ✅ Yes | ✅ Yes | ❌ Limited | ✅ Yes | Medium | **IMPLEMENTABLE WITH USER CREDENTIALS** | REST API with Bearer token authentication. Holdings, order book, and trade book endpoints available. WebSocket for real-time order updates. Vendor-based integration available. |
| **Motilal Oswal (MO API)** | Equity & F&O | ✅ Yes | ✅ Yes | ✅ Yes (API Key + Auth Token) | ✅ Yes | ✅ Yes | ✅ Yes | ❌ Limited | ✅ Yes | Medium | **IMPLEMENTABLE WITH USER CREDENTIALS** | Free API access. API key generation via portal. Auth token valid for 24 hours or until 6:00 AM daily reset. UAT testing mandatory for vendor integration. Retail auto-activation available. Symphony XTS platform for shared brokers. |
| **Groww** | Equity & MF | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | N/A | **BETTER HANDLED THROUGH CSV IMPORT** | No public retail API. Scraping violates TOS and requires SMS OTP interception. Holdings and transaction data available via CSV export from web interface. Good CSV format for statement import. |
| **Kotak Securities** | Equity & F&O | ✅ Yes | ✅ Yes | ✅ Yes (API Key) | ✅ Yes | ✅ Yes | ✅ Yes | ❌ Limited | ✅ Yes | Medium | **IMPLEMENTABLE WITH USER CREDENTIALS** | API access available for retail customers. Requires API key registration. Holdings and transaction history endpoints available. Rate limits apply. Documentation available on developer portal. |
| **SBI Securities** | Equity & F&O | ⚠️ Limited | ⚠️ Limited | ❌ No | ✅ Yes | ⚠️ Limited | ⚠️ Limited | ❌ No | ⚠️ Limited | High | **NOT PRACTICALLY INTEGRATABLE** | Limited API access primarily for institutional partners. Retail access restricted. Documentation sparse. Better handled through statement import. |

---

## Mutual Funds

| Provider | Asset Type | API Available? | Retail Access? | OAuth? | API Keys? | Holdings | Transactions | Dividends | Historical Data | Difficulty | Status | Notes |
|----------|------------|----------------|----------------|--------|-----------|----------|--------------|-----------|----------------|------------|--------|-------|
| **AMFI (Public NAV Feed)** | Mutual Funds | ✅ Yes | ✅ Yes (Public) | ❌ No | ❌ No | ❌ No (NAV only) | ❌ No | ❌ No | ✅ Yes (Daily NAV) | Low | **IMPLEMENTABLE NOW** | Free public API via MFAPI.in. Provides daily NAVs for all AMFI-registered schemes. No user holdings data - pricing/directory service only. Ideal for current valuation of manually entered holdings. |
| **MF Central** | Mutual Funds | ✅ Yes | ❌ No (B2B Only) | ✅ Yes (OTP-based) | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | High | **REQUIRES PARTNERSHIP / INSTITUTIONAL ACCESS** | Joint CAMS/KFintech platform. APIs for Consolidated Account Statement (CAS) commercially offered to Mutual Fund Distributors / RIAs only. Requires SEBI/AMFI RIA accreditation and commercial contract. Retail investors can use web/mobile app but no direct API access. |
| **CAMS / KFintech** | Mutual Funds | ❌ No (Direct) | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | N/A | **BETTER HANDLED THROUGH CSV/PDF IMPORT** | No direct retail REST API. Industry standard is e-CAS PDF/Excel delivered via email or downloadable from MF Central. CSV parsing is the practical integration path. Third-party aggregators (MfAPIs.in) offer API access via partnership. |
| **MfAPIs.in** | Mutual Funds | ✅ Yes | ⚠️ Via Partnership | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | Medium | **REQUIRES PARTNERSHIP / INSTITUTIONAL ACCESS** | Third-party aggregator offering MF Central OTP sync, BSE StarMF integration, and CAS parsing. Requires commercial partnership. Normalizes data across AMCs. Practical if partnership can be established. |
| **Groww Mutual Funds** | Mutual Funds | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | N/A | **BETTER HANDLED THROUGH CSV IMPORT** | Holdings available via Groww web interface. CSV export functionality provides transaction history. No direct API access. Integration through CSV statement import is recommended. |

---

## Crypto Exchanges

| Provider | Asset Type | API Available? | Retail Access? | OAuth? | API Keys? | Holdings | Transactions | Dividends | Historical Data | Difficulty | Status | Notes |
|----------|------------|----------------|----------------|--------|-----------|----------|--------------|-----------|----------------|------------|--------|-------|
| **Binance** | Crypto | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes (Read-Only) | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes | Low | **IMPLEMENTABLE NOW** | Comprehensive REST API. Read-only API keys with IP whitelisting. Full trade history, holdings, and market data. Python-binance library well-maintained. Supports USDT-margined and spot trading. |
| **CoinDCX** | Crypto (INR) | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes (HMAC-SHA256) | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes | Low | **IMPLEMENTABLE NOW** | Native Indian exchange with public signed balance/trade endpoints. HMAC-SHA256 authentication. INR pair support. Good documentation. Portfolio and trade history available. |
| **WazirX** | Crypto | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes (HMAC-SHA256) | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes | Low | **IMPLEMENTABLE NOW** | REST API with public and private endpoints. HMAC-SHA256 signature authentication. Holdings, trade history, and market data available. Indian exchange with INR pairs. Well-documented. |
| **CoinSwitch PRO** | Crypto | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes (Ed25519) | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes | Medium | **IMPLEMENTABLE WITH USER CREDENTIALS** | Advanced trading platform with separate APIs for Spot, Futures, HFT, and Options. Ed25519 signature authentication. Portfolio and TDS tracking endpoints available. Requires PRO account. Documentation excellent but more complex than other exchanges. |

---

## US/Global Investments

| Provider | Asset Type | API Available? | Retail Access? | OAuth? | API Keys? | Holdings | Transactions | Dividends | Historical Data | Difficulty | Status | Notes |
|----------|------------|----------------|----------------|--------|-----------|----------|--------------|-----------|----------------|------------|--------|-------|
| **Interactive Brokers** | Global Equity | ✅ Yes | ✅ Yes | ✅ Yes (OAuth 2.0, Flex Query) | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | Medium | **IMPLEMENTABLE WITH USER CREDENTIALS** | Multiple authentication methods: Client Portal Gateway (username/password), OAuth 2.0 (beta), Flex Query Web Token for XML/CSV statements. Retail users with funded IBKR Pro accounts can access Web API immediately. Full portfolio, transaction, and corporate action data. Rate limits apply. Ideal for Indian HNIs investing via RBI LRS. |
| **Alpaca** | US Equity | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes (API Key ID + Secret) | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | Low | **IMPLEMENTABLE NOW** | Commission-free US equities API. Simple API Key ID + Secret authentication. Holdings, positions, trade history, and activities API available. WebSocket for real-time data. Good for US exposure via LRS. |
| **Vested** | US Equity | ⚠️ Limited | ⚠️ Limited | ✅ Yes | ✅ Yes | ⚠️ Limited | ⚠️ Limited | ⚠️ Limited | ⚠️ Limited | High | **NOT PRACTICALLY INTEGRATABLE** | Primarily UI-focused platform. Limited API access for retail investors. Better handled through CSV statement import or manual entry. |
| **IndMoney** | US Equity | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | N/A | **BETTER HANDLED THROUGH CSV IMPORT** | No public API. Holdings available via web interface. CSV export functionality available. Integration through statement import recommended. |

---

## Banks & Fixed Deposits

| Provider | Asset Type | API Available? | Retail Access? | OAuth? | API Keys? | Holdings | Transactions | Dividends | Historical Data | Difficulty | Status | Notes |
|----------|------------|----------------|----------------|--------|-----------|----------|--------------|-----------|----------------|------------|--------|-------|
| **RBI Account Aggregator (AA) Ecosystem** | Bank Accounts / FDs | ✅ Yes | ❌ No (FIU License Required) | ✅ Yes (Consent-Based) | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | Very High | **REQUIRES PARTNERSHIP / INSTITUTIONAL ACCESS** | RBI-regulated framework for consent-based data sharing. Requires NBFC-AA license or partnership with licensed AA. FIU (Financial Information User) license from RBI/SEBI/IRDAI/PFRDA required. Technical specifications published by ReBIT. Setu, Sahamati ecosystem participants offer integration services. NOT available to individual developers without regulatory approval. |
| **Indian Retail Banks (HDFC, ICICI, SBI, etc.)** | Bank Accounts / FDs | ❌ No (Direct) | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | N/A | **BETTER HANDLED THROUGH CSV/STATEMENT IMPORT** | Direct scraping prohibited by RBI guidelines and bank TOS. No public retail APIs for account aggregation. AA framework is the only legal path for automated access. Practical integration via CSV statement import or manual entry. |
| **Bank Statement APIs** | Bank Accounts / FDs | ⚠️ Limited | ⚠️ Limited | ✅ Yes | ✅ Yes | ⚠️ Limited | ⚠️ Limited | ❌ No | ⚠️ Limited | High | **REQUIRES PARTNERSHIP / INSTITUTIONAL ACCESS** | Some banks offer limited APIs for business customers via partnerships. Not available for retail HNI customers. AA framework is the correct architecture for bank data aggregation. |

---

## Government / Official Data Sources

| Provider | Asset Type | API Available? | Retail Access? | OAuth? | API Keys? | Holdings | Transactions | Dividends | Historical Data | Difficulty | Status | Notes |
|----------|------------|----------------|----------------|--------|-----------|----------|--------------|-----------|----------------|------------|--------|-------|
| **AMFI India** | Mutual Fund NAV | ✅ Yes | ✅ Yes (Public) | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ✅ Yes (Daily) | Low | **IMPLEMENTABLE NOW** | Free public API for daily NAVs of all registered schemes. No authentication required. Ideal for valuation of manually entered mutual fund holdings. |
| **NSE / BSE Official Data** | Equity Prices | ✅ Yes | ✅ Yes (Public) | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ✅ Yes (EOD) | Low | **IMPLEMENTABLE NOW** | End-of-day price data available via official exchange APIs. No intraday data without subscription. Good for valuation but not real-time trading. |
| **RBI Reference Rate** | FX Rates | ✅ Yes | ✅ Yes (Public) | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ✅ Yes (Daily) | Low | **IMPLEMENTABLE NOW** | Official daily FX reference rates published by RBI. Public access. Good for USD/INR conversion in portfolio valuation. |
| **GST Network** | Tax Data | ⚠️ Limited | ❌ No (B2B Only) | ✅ Yes | ✅ Yes | ❌ No | ⚠️ Limited | ❌ No | ⚠️ Limited | Very High | **REQUIRES PARTNERSHIP / INSTITUTIONAL ACCESS** | GST data available via AA framework for authorized FIUs. Not directly accessible to retail applications. |

---

## Summary Statistics

### By Status Classification:
- **IMPLEMENTABLE NOW:** 8 providers (Zerodha, Binance, CoinDCX, WazirX, Alpaca, AMFI, NSE/BSE, RBI FX)
- **IMPLEMENTABLE WITH USER CREDENTIALS:** 7 providers (Upstox, Angel One, ICICI Direct, HDFC Securities, 5paisa, Motilal Oswal, Kotak, CoinSwitch PRO)
- **REQUIRES PARTNERSHIP / INSTITUTIONAL ACCESS:** 4 providers (MF Central, MfAPIs.in, RBI AA Ecosystem, Bank Statement APIs)
- **NOT PRACTICALLY INTEGRATABLE:** 3 providers (SBI Securities, Vested, IndMoney)
- **BETTER HANDLED THROUGH CSV/STATEMENT IMPORT:** 5 providers (Groww, CAMS/KFintech, Indian Retail Banks, Kotak Limited API)

### By Asset Class:
- **Indian Equity:** 8 providers with varying feasibility
- **US/Global Equity:** 3 providers (2 implementable, 1 CSV import)
- **Mutual Funds:** 5 providers (1 pricing, 1 partnership, 3 CSV import)
- **Crypto:** 4 providers (all implementable)
- **Bank/FD:** 2 providers (1 requires partnership, 1 CSV import)

---

## Key Technical Constraints

### 1. Authentication Complexity
- **Daily Token Expiration:** Most Indian brokers (Zerodha, Upstox, Angel One, Motilal Oswal) require daily token regeneration via TOTP or manual login
- **Static IP Requirements:** ICICI Direct, HDFC Securities require static IP whitelisting
- **TOTP Dependency:** Angel One, Motilal Oswal require TOTP for authentication
- **OAuth Variations:** Upstox (OAuth 2.0), ICICI Direct (OAuth 2.0), HDFC Securities (OAuth 2.0) vs others (API Key)

### 2. Rate Limiting
- **Order Placement:** Typically 10 orders/second across Indian brokers
- **Market Data:** WebSocket limits (1500 instruments/connection for HDFC)
- **Historical Data:** Separate rate limits (Zerodha: 3 requests/second for historical data)
- **API Calls:** Varies by broker, typically 10-100 requests/minute

### 3. Data Limitations
- **Dividend Data:** Limited availability across broker APIs (better via corporate action data)
- **Historical Depth:** Varies significantly (ICICI Direct: 3 years, others: limited)
- **Cost Basis:** Average cost available, but lot-level FIFO history may require trade book reconstruction
- **Grandfathering:** Pre-2018 FMV data rarely available via API (requires manual entry or CSV import)

### 4. Regulatory Constraints
- **SEBI Algo Framework:** New rules effective April 2026 affecting order types (market orders prohibited via API)
- **AA Framework:** Bank/FD aggregation requires FIU license - not available to individual developers
- **Data Privacy:** Consent-based data sharing only via AA framework for financial data
- **Partnership Requirements:** MF Central, CAMS/KFintech APIs restricted to registered RIAs/distributors

---

## Implementation Recommendations

### Phase 1: High-Value, Low-Complexity (Immediate)
1. **Upstox Connector** - Expand beyond Zerodha, OAuth 2.0 flow
2. **Angel One Connector** - Free API, strong community
3. **WazirX Connector** - Additional crypto option for Indian users
4. **ICICI Direct Connector** - Premium broker, excellent historical data

### Phase 2: Medium-Complexity (Short-term)
1. **HDFC Securities Connector** - Another premium option
2. **5paisa Connector** - Expand broker coverage
3. **Motilal Oswal Connector** - Diversify broker options
4. **CoinSwitch PRO Connector** - Advanced crypto features

### Phase 3: Partnership-Dependent (Long-term)
1. **MF Central Partnership** - For comprehensive mutual fund data
2. **RBI AA Framework Integration** - For bank/FD aggregation (requires FIU license)
3. **MfAPIs.in Partnership** - Alternative mutual fund aggregation

### Phase 4: Statement Import Enhancement
1. **Enhanced CSV Parser** - Support Groww, CAMS/KFintech formats
2. **PDF Statement Parser** - For e-CAS and broker statements
3. **Bank Statement Import** - Manual bank/FD entry with validation

---

## Security Considerations

### Credential Management
- **Never store plaintext credentials** in database or logs
- **Use environment variables** for local development
- **Implement encryption at rest** for credential storage (if persistent storage needed)
- **Prefer read-only API keys** wherever available
- **Support OAuth flows** where available to avoid credential storage

### Data Privacy
- **Never send credentials to AI layer** (Gemini receives only structured portfolio context)
- **Mask identifiers in UI** (show only last 4 characters)
- **Implement consent-based access** for any future AA integration
- **Comply with Indian data protection regulations**

### API Security
- **Implement rate limiting** to respect provider constraints
- **Handle token expiration** gracefully with user prompts
- **Validate API responses** to prevent injection attacks
- **Use HTTPS exclusively** for all API communications

---

## Conclusion

WealthMap has a solid foundation with 6 already-implemented connectors (Zerodha, Binance, CoinDCX, Alpaca, AMFI, CSV Statement). The integration feasibility matrix identifies **15 additional providers** that can be realistically integrated:

- **8 can be implemented immediately** with user credentials
- **4 require partnership/institutional access** (long-term strategic consideration)
- **3 are better handled through CSV import** (alternative path)

The architecture is well-designed to support additional connectors through the BaseConnector interface. Priority should be given to brokers with OAuth 2.0 authentication (Upstox, ICICI Direct, HDFC Securities) to reduce credential management complexity.

**Critical Principle:** Do not attempt to integrate providers without suitable public APIs or where integration would violate terms of service. CSV/PDF statement import is the honest and practical alternative for such cases.