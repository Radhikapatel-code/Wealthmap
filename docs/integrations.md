# WealthMap Integrations Documentation

**Last Updated:** 2026-09-18  
**Purpose:** Comprehensive guide for connecting external financial accounts to WealthMap

## Overview

WealthMap provides a standardized connector architecture for integrating with multiple financial platforms. This documentation covers:

- Supported integrations and their feasibility
- Connection setup instructions
- Authentication mechanisms
- Data synchronization capabilities
- Security considerations
- Troubleshooting guide

## Supported Integrations

### Currently Implemented Connectors

| Provider | Asset Type | Status | Authentication | Documentation |
|----------|------------|--------|----------------|---------------|
| **Zerodha** | Indian Equity & F&O | ✅ Production | API Key + Daily TOTP Token | [Kite Connect](https://kite.trade/docs/connect/) |
| **Binance** | Crypto (Global) | ✅ Production | HMAC-SHA256 API Key | [Binance API](https://binance-docs.github.io/) |
| **CoinDCX** | Crypto (INR) | ✅ Production | HMAC-SHA256 API Key | [CoinDCX API](https://docs.coindcx.com/) |
| **Alpaca** | US Equity | ✅ Production | API Key ID + Secret | [Alpaca Docs](https://alpaca.markets/docs/) |
| **AMFI** | Mutual Fund NAV | ✅ Production | Public (No Auth) | [AMFI India](https://www.amfiindia.com/) |
| **CSV Statement** | All Asset Types | ✅ Production | CSV Upload | - |

### Newly Added Connectors (This Release)

| Provider | Asset Type | Status | Authentication | Documentation |
|----------|------------|--------|----------------|---------------|
| **Upstox** | Indian Equity & F&O | ✅ New | OAuth 2.0 | [Upstox API](https://upstox.com/developer/api-documentation/) |
| **Angel One** | Indian Equity & F&O | ✅ New | API Key + TOTP | [SmartAPI](https://smartapi.angelone.in/docs) |
| **WazirX** | Crypto (INR) | ✅ New | HMAC-SHA256 API Key | [WazirX API](https://docs.wazirx.com/) |

## Connection Setup Guide

### Zerodha (Kite Connect)

**Prerequisites:**
- Kite Connect Developer Account (₹2000/month)
- API Key from Kite Connect Dashboard
- Daily Access Token (expires at 6:00 AM IST)

**Setup Steps:**
1. Navigate to [Kite Connect Developer Dashboard](https://developers.kite.trade/)
2. Generate API Key
3. Use TOTP authenticator app to generate daily access token
4. Configure in `.env`:
   ```
   KITE_API_KEY=your_api_key
   KITE_ACCESS_TOKEN=your_daily_token
   ```

**Data Synchronized:**
- Holdings with average cost
- Trade history
- Cash balances
- Real-time market data

**Limitations:**
- Access token expires daily - requires manual regeneration
- Historical data requires separate paid add-on
- Market orders not permitted via API

---

### Upstox (UpLink API v2)

**Prerequisites:**
- Upstox Trading Account
- UpLink Developer Account (Free)
- OAuth 2.0 Redirect URI

**Setup Steps:**
1. Create an account at [Upstox Developer Portal](https://upstox.com/developer/api-documentation/)
2. Create a new app to get API Key and Secret
3. Set redirect URI (e.g., `http://localhost:8501`)
4. Complete OAuth 2.0 flow to get access token
5. Configure in `.env`:
   ```
   UPSTOX_API_KEY=your_api_key
   UPSTOX_API_SECRET=your_api_secret
   UPSTOX_REDIRECT_URI=http://localhost:8501
   UPSTOX_ACCESS_TOKEN=your_access_token
   ```

**Data Synchronized:**
- Holdings with acquisition dates
- Trade history
- Portfolio positions
- Cash balances

**Advantages:**
- Free API access
- OAuth 2.0 flow (no daily token regeneration)
- Sandbox environment for testing
- 90-day zero brokerage for new API users

**Limitations:**
- Access token expires after 24 hours
- Static IP registration may be required for production

---

### Angel One (SmartAPI)

**Prerequisites:**
- Angel One Trading Account
- SmartAPI Developer Account (Free)
- TOTP Authenticator App

**Setup Steps:**
1. Sign up at [SmartAPI Portal](https://smartapi.angelone.in/docs)
2. Create an app to get API Key
3. Note your Client Code, PIN, and TOTP Secret
4. Configure in `.env`:
   ```
   ANGEL_ONE_API_KEY=your_api_key
   ANGEL_ONE_CLIENT_CODE=your_client_code
   ANGEL_ONE_PASSWORD=your_pin
   ANGEL_ONE_TOTP_SECRET=your_totp_secret
   ```

**Data Synchronized:**
- Holdings with cost basis
- Trade book
- Order history
- Margin and positions

**Advantages:**
- Completely free API access
- Strong community documentation
- Session valid till midnight
- Token refresh available

**Limitations:**
- Requires TOTP for authentication
- Session expires at 6:00 AM daily
- Market orders not permitted via API (SEBI regulation)

---

### Binance

**Prerequisites:**
- Binance Account
- Read-Only API Key (Recommended)

**Setup Steps:**
1. Navigate to Binance API Management
2. Create API Key with Read-Only permissions
3. Enable IP restriction for security
4. Configure in `.env`:
   ```
   BINANCE_API_KEY=your_api_key
   BINANCE_API_SECRET=your_api_secret
   ```

**Data Synchronized:**
- Crypto holdings with cost basis
- Trade history
- Withdrawal/deposit history
- Real-time market data

**Security Note:**
- Always use Read-Only API keys
- Enable IP whitelisting
- Never share API secrets

---

### CoinDCX

**Prerequisites:**
- CoinDCX Account
- API Key with Read permissions

**Setup Steps:**
1. Navigate to CoinDCX Profile > Security
2. Generate API Key
3. Configure in `.env`:
   ```
   COINDCX_API_KEY=your_api_key
   COINDCX_API_SECRET=your_api_secret
   ```

**Data Synchronized:**
- Crypto holdings (INR pairs)
- Trade history
- Cash balances

**Advantages:**
- Native Indian exchange
- INR trading pairs
- Simple HMAC-SHA256 authentication

---

### WazirX

**Prerequisites:**
- WazirX Account
- API Key with trading permissions

**Setup Steps:**
1. Navigate to WazirX API Management
2. Generate API Key
3. Configure in `.env`:
   ```
   WAZIRX_API_KEY=your_api_key
   WazirX_API_SECRET=your_api_secret
   ```

**Data Synchronized:**
- Crypto holdings (INR pairs)
- Trade history
- Deposit/withdrawal history

**Advantages:**
- Indian exchange with INR pairs
- Well-documented API
- Supports major cryptocurrencies

---

### Alpaca (US Equity)

**Prerequisites:**
- Alpaca Trading Account (LRS-enabled for Indian users)
- API Key ID and Secret

**Setup Steps:**
1. Create Alpaca account or use existing account
2. Generate API Key in Alpaca Dashboard
3. Configure in `.env`:
   ```
   APCA_API_KEY_ID=your_key_id
   APCA_API_SECRET=your_secret
   ```

**Data Synchronized:**
- US equity holdings
- Trade history
- Corporate actions (dividends)
- Cash balances

**Note:**
- Requires RBI LRS compliance for Indian residents
- Good for diversification into US markets

---

### AMFI (Mutual Fund NAV)

**Prerequisites:**
- None (Public Data)

**Setup:**
- No configuration required - automatically enabled

**Data Synchronized:**
- Daily NAVs for all AMFI-registered mutual funds
- Scheme master data
- Historical NAV data

**Note:**
- Provides pricing data only, not user holdings
- Used for valuation of manually entered mutual fund positions

---

### CSV Statement Import

**Supported Formats:**
- Groww Equity/Mutual Fund statements
- Zerodha Console tradebook
- Generic portfolio CSV
- CAS (Consolidated Account Statement) formats

**CSV Format:**
```
Symbol,ISIN,Quantity,Average Cost,Current Price,Asset Class,Buy Date
INFY.NS,INE009A01021,150,1420.00,1680.00,EQUITY,2023-04-10
HDFCBANK.NS,INE040A01034,100,1550.00,1720.00,EQUITY,2022-11-15
```

**Setup:**
1. Export statement from broker platform
2. Upload via WealthMap Connected Accounts page
3. Assign to family member
4. Data is normalized and imported

---

## Connector Architecture

### BaseConnector Interface

All connectors implement the `BaseConnector` interface with the following methods:

```python
class BaseConnector(ABC):
    def authenticate() -> bool
    def health_check() -> ConnectionHealth
    def get_accounts() -> List[CanonicalAccount]
    def get_holdings(account_id: str) -> List[CanonicalHolding]
    def get_transactions(account_id: str, since: Optional[datetime]) -> List[CanonicalTransaction]
    def get_cash_balances(account_id: str) -> List[CanonicalCashBalance]
    def disconnect() -> bool
```

### Canonical Data Models

WealthMap normalizes all provider-specific data into canonical models:

- **CanonicalAccount**: Account metadata and status
- **CanonicalAsset**: Standardized asset information
- **CanonicalHolding**: Current positions with cost basis
- **CanonicalTransaction**: Transaction history
- **CanonicalCashBalance**: Cash and margin positions

### Sync Engine

The `SyncEngine` orchestrates:

- Connector registration and management
- Incremental synchronization (fetch only new data since last sync)
- Deduplication across accounts
- Transfer detection (prevents false taxable events)
- Conversion to core portfolio models

## Security Guidelines

### Credential Management

✅ **DO:**
- Store credentials in environment variables only
- Use read-only API keys where available
- Enable IP whitelisting for additional security
- Use OAuth flows where available (Upstox, ICICI Direct)
- Mask identifiers in UI display

❌ **DO NOT:**
- Store credentials in database
- Commit credentials to version control
- Print credentials in logs
- Share credentials via chat/email
- Use admin/broker passwords for API access

### Data Privacy

- Credentials are never sent to the AI layer (Gemini)
- Only structured portfolio data is sent to AI for analysis
- User consent is required for any data sharing
- All API calls use HTTPS encryption

### Rate Limiting

Each provider has different rate limits. The sync engine respects these by:

- Implementing appropriate delays between requests
- Providing smart sync scheduling based on data freshness requirements
- Handling rate limit errors gracefully with retry logic

## Troubleshooting

### Common Issues

**"Access Token Expired"**
- Zerodha: Regenerate daily token via TOTP
- Upstox: Complete OAuth 2.0 flow again
- Angel One: Re-authenticate with PIN + TOTP

**"Invalid API Key"**
- Verify API key is correct
- Check IP whitelisting requirements
- Ensure API key has required permissions

**"Rate Limit Exceeded"**
- Wait before retrying
- Check if you're making too many requests
- Reduce sync frequency

**"Connection Failed"**
- Check internet connectivity
- Verify provider API status
- Check firewall/proxy settings

### Debug Mode

Enable debug logging by setting:
```bash
DEBUG=true
```

This will show detailed API logs in the console output.

## Integration Feasibility Matrix

For a comprehensive assessment of all possible integrations, see [Integration Feasibility Matrix](./integration-feasibility-matrix.md).

## API Status Monitoring

The Connected Accounts page shows real-time status for each provider:

- **🟢 Connected**: Successfully authenticated and syncing
- **🟠 Token Expired**: Requires re-authentication
- **🟡 Rate Limited**: Temporary rate limit, retry later
- **🔴 Sync Failed**: Error occurred, check error message
- **⚪ Not Connected**: Not configured

## Future Integrations

### High Priority (Planned)
- ICICI Direct Breeze API
- HDFC Securities Sky API
- 5paisa Xstream API
- Motilal Oswal MO API

### Partnership Required
- MF Central (requires RIA accreditation)
- RBI Account Aggregator (requires FIU license)
- MfAPIs.in (commercial partnership)

### Statement Import Only
- Groww (no public API)
- CAMS/KFintech (CSV/PDF import)
- SBI Securities (limited API)

## Support

For integration issues:
1. Check the provider's official documentation
2. Review the Integration Feasibility Matrix
3. Enable debug logging
4. Check the troubleshooting section above

For general WealthMap support:
- GitHub Issues: [https://github.com/Radhikapatel-code/Wealthmap/issues]
- Documentation: [README.md](../README.md)