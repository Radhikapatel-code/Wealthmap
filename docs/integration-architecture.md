# WealthMap Integration Architecture

**Last Updated:** 2026-09-18  
**Version:** 2.0  
**Purpose:** Technical architecture documentation for WealthMap's connector system

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     WealthMap Platform                          │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              User Interface Layer                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │  │
│  │  │ Streamlit     │  │  FastAPI      │  │  Mobile       │ │  │
│  │  │ Dashboard    │  │  Backend      │  │  App (Future) │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
│                          ↕                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Business Logic Layer                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │  │
│  │  │ State        │  │ Wealth       │  │ AI Context   │ │  │
│  │  │ Manager      │  │ Service      │  │ Builder      │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
│                          ↕                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Connector Layer                           │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │  │
│  │  │ Sync Engine  │  │ Connector    │  │ Canonical    │ │  │
│  │  │              │  │ Registry     │  │ Models       │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘ │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │ Provider-Specific Connectors                    │  │  │
│  │  │ ┌─────────┐ ┌─────────┐ ┌─────────┐      │  │  │
│  │  │ │Zerodha │ │ Binance │ │CoinDCX  │      │  │  │
│  │  │ │Upstox  │ │Angel 1 │ │WazirX  │      │  │  │
│  │  │ │Alpaca  │ │AMFI    │ │CSV Imp │      │  │  │
│  │  │ └─────────┘ └─────────┘ └─────────┘      │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                          ↕                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              External Data Sources                      │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │  │
│  │  │Zerodha  │ │Binance │ │CoinDCX  │ │Upstox  │  │  │
│  │  │API      │ │API     │ │API     │ │API     │  │  │
│  │  │Angel 1  │ │WazirX  │ │Alpaca  │ │AMFI    │  │  │
│  │  │SmartAPI │ │API     │ │API     │ │Feed    │  │  │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. BaseConnector Interface

**Location:** `core/connectors/base.py`

The `BaseConnector` abstract class defines the contract that all external provider connectors must implement:

```python
class BaseConnector(ABC):
    @abstractmethod
    def authenticate(self) -> bool:
        """Validate credentials and establish connection."""
        
    @abstractmethod
    def health_check(self) -> ConnectionHealth:
        """Verify API connectivity and latency."""
        
    @abstractmethod
    def get_accounts(self) -> List[CanonicalAccount]:
        """Discover accounts linked to credentials."""
        
    @abstractmethod
    def get_holdings(self, account_id: str) -> List[CanonicalHolding]:
        """Fetch current positions with cost basis."""
        
    @abstractmethod
    def get_transactions(self, account_id: str, since: Optional[datetime]) -> List[CanonicalTransaction]:
        """Fetch transaction history incrementally."""
        
    @abstractmethod
    def get_cash_balances(self, account_id: str) -> List[CanonicalCashBalance]:
        """Fetch available and locked cash balances."""
        
    @abstractmethod
    def disconnect(self) -> bool:
        """Invalidate session and clean up resources."""
```

**Key Design Principles:**
- Provider-specific implementations NEVER leak raw response structures outside the adapter
- All monetary values use `Decimal` for financial precision
- Errors are caught and mapped to `SyncStatus` states
- Credentials are never logged or exposed

### 2. Canonical Data Models

**Location:** `core/connectors/models.py`

Canonical models provide the unified representation that all connectors must normalize to:

#### CanonicalAccount
```python
@dataclass
class CanonicalAccount:
    provider: str                      # "zerodha", "binance", etc.
    provider_account_id: str             # Provider's internal ID
    family_member_id: str              # Family member assignment
    account_type: str                   # "EQUITY_TRADING", "CRYPTO_WALLET", etc.
    currency: str                       # "INR", "USD", etc.
    masked_identifier: str              # User-facing masked ID
    status: SyncStatus                  # Connection state
    last_synced_at: Optional[datetime]   # Last successful sync
    error_message: Optional[str]         # Last error if any
```

#### CanonicalAsset
```python
@dataclass
class CanonicalAsset:
    symbol: str                       # Normalized symbol (e.g., "RELIANCE.NS")
    name: str                          # Human-readable name
    asset_type: AssetType               # Standardized asset class
    currency: str                      # Base currency
    isin: Optional[str]                # ISIN where available
    exchange: Optional[str]            # Exchange identifier
    provider_asset_id: Optional[str]     # Provider's internal ID
    metadata: Dict[str, Any]            # Additional provider-specific data
```

#### CanonicalHolding
```python
@dataclass
class CanonicalHolding:
    holding_id: str                    # Unique holding identifier
    account_id: str                   # Associated account
    asset: CanonicalAsset              # Asset details
    quantity: Decimal                  # Current quantity
    average_cost: Decimal               # Weighted average cost
    cost_basis: Decimal                 # Total cost basis
    current_price: Decimal              # Current market price
    market_value: Decimal               # Total market value
    currency: str                      # Base currency
    as_of: datetime                    # Price timestamp
    acquisition_date: Optional[date]     # Purchase date
    grandfathered_cost: Optional[Decimal] # FMV for pre-2018 holdings
    metadata: Dict[str, Any]            # Additional data
```

#### CanonicalTransaction
```python
@dataclass
class CanonicalTransaction:
    transaction_id: str               # Unique transaction ID
    account_id: str                   # Associated account
    asset: CanonicalAsset              # Asset details
    transaction_type: TransactionType   # BUY, SELL, DIVIDEND, etc.
    quantity: Decimal                  # Quantity traded
    price: Decimal                      # Price per unit
    timestamp: datetime                # Execution timestamp
    currency: str                      # Base currency
    fees: Decimal                       # Trading fees
    taxes: Decimal                      # Withheld taxes
    settlement_date: Optional[date]     # Settlement date
    provider_transaction_id: Optional[str]  # Provider's transaction ID
    notes: Optional[str]                 # Additional notes
    is_internal_transfer: bool         # Marked if this is an internal transfer
    metadata: Dict[str, Any]            # Additional data
```

### 3. Sync Engine

**Location:** `core/connectors/sync_engine.py`

The `SyncEngine` orchestrates all connectors and manages the synchronization lifecycle:

#### Key Responsibilities

1. **Connector Registration**
   - Register connector instances with unique IDs
   - Discover accounts from each connector
   - Maintain connector lifecycle

2. **Synchronization**
   - Execute sync operations on-demand or scheduled
   - Support incremental sync using `since` parameter
   - Support forced full sync when needed
   - Implement smart sync scheduling based on provider requirements

3. **Deduplication**
   - Merge duplicate holdings within same account
   - Preserve holdings across different accounts (different members)
   - Handle weighted average cost basis correctly

4. **Transfer Detection**
   - Identify matching withdrawal/deposit pairs across accounts
   - Mark internal transfers to prevent false taxable events
   - Use 48-hour window and 2% quantity tolerance

5. **Data Conversion**
   - Convert canonical models to core `AssetLot` format
   - Map asset types to internal `AssetClass` enum
   - Preserve tax lot information

#### Smart Sync Scheduling

Different providers have different optimal sync intervals:

| Provider | Sync Interval | Rationale |
|----------|---------------|-----------|
| Zerodha | 15 minutes | Daily token expiry |
| Binance | 5 minutes | Real-time crypto |
| CoinDCX | 5 minutes | Real-time crypto |
| WazirX | 5 minutes | Real-time crypto |
| Upstox | 10 minutes | 24-hour token |
| Angel One | 15 minutes | Till midnight expiry |
| Alpaca | 10 minutes | US market hours |
| AMFI | 60 minutes | Daily NAV updates |

### 4. Data Flow Pipeline

```
External API
    ↓
Provider-Specific Connector
    ├─ authenticate()
    ├─ get_accounts()
    ├─ get_holdings()
    ├─ get_transactions(since=last_sync)
    └─ get_cash_balances()
    ↓
Normalization Layer
    ├─ Provider response → Canonical Model
    ├─ Symbol normalization (e.g., "RELIANCE" → "RELIANCE.NS")
    ├─ Asset type mapping
    └─ Currency conversion
    ↓
Sync Engine
    ├─ Register connector
    ├─ Detect transfers
    ├─ Deduplicate holdings
    └─ Smart sync scheduling
    ↓
Core Conversion
    ├─ Canonical → AssetLot
    ├─ AssetType → AssetClass
    └─ Platform → Platform enum
    ↓
Portfolio Engine
    ├─ LotTracker (FIFO tax lots)
    ├─ Tax Engine (Indian tax rules)
    └─ Wealth Service
    ↓
AI Context Builder
    ├─ Build structured context
    ├─ Compute tax implications
    └─ Generate CFO insights
    ↓
User Interface
    ├─ Portfolio dashboard
    ├─ Tax center
    └─ Connected accounts
```

## Provider-Specific Implementations

### Authentication Mechanisms

#### 1. API Key + Secret (Simple)
- **Providers:** Binance, CoinDCX, WazirX, Alpaca
- **Method:** HMAC-SHA256 signature
- **Token Lifetime:** Until revoked
- **Pros:** Simple, widely supported
- **Cons:** Key rotation required for security

#### 2. API Key + Daily Token (TOTP)
- **Providers:** Zerodha
- **Method:** TOTP-generated access token
- **Token Lifetime:** Daily (expires 6:00 AM IST)
- **Pros:** Enhanced security
- **Cons:** Manual token regeneration required

#### 3. OAuth 2.0
- **Providers:** Upstox, ICICI Direct, HDFC Securities
- **Method:** Standard OAuth 2.0 flow
- **Token Lifetime:** 24 hours (varies by provider)
- **Pros:** Standard, no credential storage needed
- **Cons:** Requires redirect URI setup

#### 4. API Key + TOTP
- **Providers:** Angel One
- **Method:** Client code + PIN + TOTP
- **Token Lifetime:** Till midnight
- **Pros:** Enhanced security, free API
- **Cons:** TOTP dependency

#### 5. Public Data (No Auth)
- **Providers:** AMFI
- **Method:** Direct HTTP requests
- **Token Lifetime:** N/A
- **Pros:** No credentials needed
- **Cons:** Pricing data only, no user holdings

### Error Handling Strategy

All connectors implement a consistent error handling pattern:

```python
try:
    # API call
    response = self._session.get(url, headers=headers, timeout=10)
    
    if response.status_code == 200:
        self._status = SyncStatus.CONNECTED
        return process_response(response)
    elif response.status_code == 401:
        self._status = SyncStatus.AUTH_EXPIRED
        self._last_error = "Authentication failed"
    elif response.status_code == 429:
        self._status = SyncStatus.RATE_LIMITED
        self._last_error = "Rate limit exceeded"
    else:
        self._status = SyncStatus.PROVIDER_UNAVAILABLE
        self._last_error = f"API error: {response.status_code}"
        
except Exception as e:
    self._status = SyncStatus.SYNC_FAILED
    self._last_error = str(e)
    logger.error(f"{self.provider_id} error: {e}")
```

### Incremental Synchronization

The sync engine supports incremental sync to avoid downloading full history on every sync:

1. **Last Synced Timestamp:** Each account stores `last_synced_at`
2. **Since Parameter:** Transactions are fetched with `since=last_synced_at`
3. **Full Sync Option:** Can force full sync when needed
4. **Provider Support:** Some providers don't support incremental fetch

**Example:**
```python
# Incremental sync (default)
txs = connector.get_transactions(account_id, since=account.last_synced_at)

# Full sync (forced)
txs = connector.get_transactions(account_id, since=None)
```

### Currency Conversion

All monetary values are normalized to INR for consistency:

- **Crypto:** USDT → INR using live FX rate
- **US Equity:** USD → INR using live FX rate
- **Indian Platforms:** Already in INR (no conversion needed)

FX rates are cached with TTL to avoid excessive API calls.

## Security Architecture

### Credential Storage

**Current Implementation:**
- Credentials stored in environment variables only
- No persistent credential storage in database
- Credentials loaded at application startup
- Each connector holds credentials in memory only

**Future Enhancements:**
- Encrypted credential storage (if persistent storage needed)
- Hardware security module (HSM) integration
- OAuth token refresh without user intervention

### Credential Exposure Prevention

**✅ What We Do:**
- Never log credentials
- Never send credentials to AI layer
- Mask identifiers in UI display
- Use read-only API keys where available
- Validate credentials before use

**❌ What We Don't Do:**
- Store credentials in database
- Commit credentials to version control
- Display full credentials in UI
- Share credentials via unencrypted channels
- Use admin/broker passwords for API access

### AI Layer Isolation

The AI context builder (`core/ai/context_builder.py`) receives only:

- Structured portfolio data
- Computed tax implications
- Asset allocations
- Risk metrics
- Summarized financial metrics

The AI layer NEVER receives:
- API keys
- Access tokens
- Refresh tokens
- Raw API responses
- Passwords
- Authentication headers

## Family Account Model

### Multi-Member Support

WealthMap is designed around family units where each member can have:

- Multiple accounts across different providers
- Individual tax calculations with per-member LTCG exemption
- Gift tax tracking for intra-family transfers
- Consolidated family dashboard

### Account Assignment

Each connector must be assigned to a specific family member:

```python
connector = ZerodhaConnector(
    api_key="key",
    access_token="token",
    member_id="father"  # Required
)
```

### Tax Implications

Indian tax calculations are individual/entity-specific:

- **LTCG Exemption:** ₹1.25L per individual per FY
- **Gift Tax:** Applicable for gifts >₹50,000
- **Tax Filing:** Each member files separate returns

The system maintains individual tax states for each family member.

## Performance Considerations

### Rate Limiting

Each provider has different rate limits. The sync engine:

- Implements delays between requests
- Respects provider-specific limits
- Handles rate limit errors gracefully
- Provides exponential backoff for retries

### Caching Strategy

- **FX Rates:** Cached with 1-hour TTL
- **NAV Data:** Cached with 24-hour TTL (AMFI)
- **Market Data:** Fetched on-demand with short cache
- **Portfolio Data:** Refreshed on sync or user request

### Concurrency

- Thread-safe state management
- Connector instances are not thread-safe by default
- Sync engine coordinates concurrent access
- Each family member has isolated state

## Extensibility

### Adding a New Connector

To add a new provider:

1. **Create Connector Class**
   - Inherit from `BaseConnector`
   - Implement all abstract methods
   - Follow existing patterns for error handling

2. **Add Configuration**
   - Add environment variables to settings
   - Update `.env.example`

3. **Register in State Manager**
   - Add to `_init_connectors_for_session()`
   - Handle credential loading

4. **Update UI**
   - Add to provider catalog in connected accounts page
   - Add connection form fields
   - Add to API endpoint for registration

5. **Add Tests**
   - Create test class in `tests/test_connectors.py`
   - Test authentication, normalization, error handling
   - Test deduplication and transfer detection

### Adding a New Asset Type

To support a new asset type:

1. **Add to AssetType enum** in `core/connectors/models.py`
2. **Add mapping** in `SyncEngine.map_asset_type_to_class()`
3. **Update tax engine** to handle the new asset type
4. **Add test coverage** for the new asset type

## Testing Strategy

### Unit Tests

Each connector has comprehensive unit tests covering:

- **Authentication Tests:** Valid and invalid credentials
- **Normalization Tests:** Provider data → canonical models
- **Incremental Sync Tests:** Since parameter handling
- **Error Handling Tests:** API failures, rate limits, timeouts
- **Deduplication Tests:** Cross-account and within-account
- **Transfer Detection Tests:** Matching withdrawal/deposit pairs

### Integration Tests

The sync engine is tested for:

- **Connector Registration:** Multiple providers
- **Concurrent Sync:** Multiple connectors syncing simultaneously
- **Smart Scheduling:** Provider-specific intervals
- **Data Conversion:** Canonical → Core models
- **Error Recovery:** Partial sync scenarios

### Mocking Strategy

All external API calls are mocked in tests to:

- Avoid dependency on real credentials
- Test error scenarios reliably
- Ensure tests run consistently
- Avoid rate limit issues

## Monitoring and Observability

### Sync Statistics

The sync engine provides:

- Total syncs count
- Success/failure rates
- Holdings/transactions synced
- Per-provider statistics
- Sync history tracking

### Health Checks

Each connector provides:

- API latency measurement
- Connection status
- Last successful sync time
- Rate limit remaining (where available)

### Error Logging

All errors are logged with context:

- Provider and operation
- Error type and message
- Timestamp
- Account ID (masked)

## Future Enhancements

### Planned Improvements

1. **OAuth Token Refresh**
   - Automatic token refresh for OAuth providers
   - Background token validity monitoring

2. **Advanced Deduplication**
   - Machine learning-based duplicate detection
   - Fuzzy matching for similar transactions

3. **Enhanced Transfer Detection**
   - Multi-step transfer patterns
   - Cross-broker transfer support
   - Tax lot preservation during transfers

4. **Real-time Streaming**
   - WebSocket support for real-time updates
   - Push notifications for large movements
   - Live tax impact calculation

5. **Account Aggregator Integration**
   - RBI AA framework integration (requires FIU license)
   - Bank/FD direct aggregation
   - Consent-based data sharing

### Scalability Considerations

- **Multi-Instance Deployment:** Stateless sync engine design
- **Database Storage:** Future credential persistence with encryption
- **API Gateway:** Potential for centralized credential management
- **Monitoring:** Integration with observability platforms

## Conclusion

The WealthMap connector architecture is designed to be:

- **Modular:** Easy to add new providers without modifying core logic
- **Secure:** Credentials are isolated and never exposed
- **Scalable:** Supports multiple providers, accounts, and family members
- **Reliable:** Comprehensive error handling and retry logic
- **Extensible:** Clean abstractions for future enhancements

The architecture separates concerns appropriately:

- **Connectors:** Provider-specific implementations
- **Sync Engine:** Orchestration and deduplication
- **Canonical Models:** Unified data representation
- **Core Engine:** Business logic and tax calculations
- **UI Layer:** User interaction and display

This design ensures that WealthMap can continue to expand its integration capabilities while maintaining code quality and security standards.