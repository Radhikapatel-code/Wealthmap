# WealthMap 🗺️
### AI-Powered Portfolio Intelligence for High-Net-Worth Indian Families

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python"/>
  <img src="https://img.shields.io/badge/Claude-claude--sonnet--4-8A2BE2?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/FastAPI-0.110+-green?style=for-the-badge&logo=fastapi"/>
  <img src="https://img.shields.io/badge/Status-Active_Development-orange?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge"/>
</p>

> **WealthMap** is not a chatbot over financial data. It is a cross-asset portfolio intelligence engine built specifically for Indian HNI families — aggregating equity, crypto, and mutual fund data, computing real Indian tax liability at the lot level, and surfacing Claude-powered CFO-grade reasoning across the entire family's wealth picture.

---

## The Problem

An HNI Indian family's wealth is structurally scattered:

| Asset | Platform | Tax Treatment |
|-------|----------|---------------|
| Equity | Zerodha, HDFC Securities | LTCG (>1Y): 12.5% above ₹1.25L, STCG: 20% |
| Crypto | CoinDCX, Binance | 30% flat + 1% TDS per transaction |
| Mutual Funds | Groww, Kuvera | Equity MF: same as equity; Debt MF: slab rate |
| Fixed Deposits | HDFC, SBI | Slab rate, TDS at 10% above ₹40,000 interest |
| US Equity | Vested, INDmoney | 25% flat (DTAA), reported under foreign assets |
| Physical Gold | Manual | LTCG (>3Y): 12.5% with indexation |

No single platform gives a unified, tax-aware view across all of these. No existing tool tells a family: *"If you sell this position today vs. 12 days from now, the tax difference is ₹23,000."* WealthMap does.

---

## What WealthMap Does

### 1. Multi-Asset Aggregation Engine
Connects to real Indian and global APIs to pull live portfolio data:
- **Zerodha Kite API** — equity holdings, P&L, order history
- **Binance & CoinDCX API** — crypto holdings, transaction history, cost basis
- **BSE/NSE via Yahoo Finance** — live equity prices, historical OHLCV
- **Groww / Kuvera (CSV import)** — mutual fund NAV, purchase history
- **Manual inputs** — FDs, physical gold, real estate, US equity (structured JSON schema)

Every asset is normalized into a unified internal schema with acquisition date, cost basis, current value, and unrealized P&L.

### 2. Indian Tax Computation Core
This is the mathematical backbone of WealthMap. No LLM guessing — hard computation.

**Equity & MF Tax Engine:**
- Tracks every lot independently (FIFO by default, configurable)
- Computes holding period per lot to the day
- Classifies each lot: STCG / LTCG with correct rates
- Aggregates LTCG across the financial year; applies ₹1.25L exemption
- Projects tax liability if user sells today vs. at a future date
- Surfaces LTCG unlock calendar: *"3 positions unlock LTCG status in the next 30 days"*

**Crypto Tax Engine:**
- 30% flat tax on every gain — no exemption, no offsetting losses
- 1% TDS tracking per transaction (Form 26AS reconciliation)
- Computes unrealized crypto gains for advance tax planning
- Flags: *"Your crypto gains this FY are ₹4.2L. Advance tax of ₹1.26L due by 15 Dec."*
- Accounts for carry-forward loss restrictions under Section 115BBH

**Tax Loss Harvesting Module:**
- Scans entire portfolio for unrealized losses
- Identifies which losses can offset which gains under Indian tax law
- Suggests specific sell-rebuy pairs with net post-tax benefit
- Computes wash-sale equivalent risk (India has no formal wash-sale rule — this is a risk flag)

### 3. Claude CFO Layer
Claude is not a chatbot here. It is a reasoning layer with access to the full, structured, computed portfolio state.

Every Claude interaction receives:
```
- Full asset breakdown (all classes, all platforms)
- Tax status per position (STCG/LTCG, holding days, unrealized gain)
- YTD realized gains and tax paid
- Upcoming LTCG unlock events
- Family member breakdown
- Macro context (optional: fetched news headlines)
```

Claude then produces:
- **Portfolio health assessment** — concentration risk, sector exposure, asset class balance
- **Tax-optimal action recommendations** — specific, numbered, actionable
- **Forward projections** — *"At current trajectory, your FY2026 tax liability is ₹6.8L"*
- **Scenario reasoning** — *"If BTC drops another 20%, your unrealized crypto loss of ₹3.1L can offset your equity STCG"*

Claude never has access to raw API keys or executes actions. It only reasons over structured context passed to it.

### 4. Family Office View
WealthMap models wealth at the **family unit** level, not just individual.

- Multiple member profiles (Father, Mother, Adult Child, HUF entity)
- Consolidated net worth dashboard across all members
- Per-member tax liability breakdown
- Gift tax tracking (intra-family transfers above ₹50,000)
- HUF-specific tax slab computation

### 5. Alerts & Digest Engine
- **LTCG Unlock Alerts** — notified 7 days before a position qualifies for long-term treatment
- **TDS Threshold Alerts** — FD interest approaching ₹40,000 TDS trigger
- **Crypto TDS Tracker** — aggregate TDS deducted vs. actual liability
- **Daily Digest** (optional Telegram/email) — net worth delta, biggest movers, upcoming tax events

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        WealthMap                            │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  Data Layer  │    │  Compute     │    │  AI Layer    │  │
│  │              │    │  Layer       │    │              │  │
│  │ Zerodha API  │───▶│ Portfolio    │───▶│ Claude       │  │
│  │ Binance API  │    │ Normalizer   │    │ CFO Engine   │  │
│  │ CoinDCX API  │    │              │    │              │  │
│  │ Yahoo Finance│    │ Tax Engine   │    │ Structured   │  │
│  │ Manual Input │    │ (FIFO lots)  │    │ Context      │  │
│  └──────────────┘    │              │    │ Builder      │  │
│                      │ TLH Scanner  │    └──────────────┘  │
│                      │              │            │          │
│                      │ Family       │            ▼          │
│                      │ Aggregator   │    ┌──────────────┐  │
│                      └──────────────┘    │  FastAPI     │  │
│                                          │  Backend     │  │
│                                          └──────┬───────┘  │
│                                                 │          │
│                              ┌──────────────────┘          │
│                              ▼                             │
│                    ┌──────────────────┐                    │
│                    │  Streamlit / Web │                    │
│                    │  Dashboard       │                    │
│                    └──────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
wealthmap/
│
├── core/
│   ├── aggregator/
│   │   ├── zerodha.py           # Kite Connect integration
│   │   ├── binance.py           # Binance API integration
│   │   ├── coindcx.py           # CoinDCX integration
│   │   ├── yahoo_finance.py     # Live price feeds
│   │   ├── manual_import.py     # JSON schema for manual assets
│   │   └── normalizer.py        # Unified asset schema
│   │
│   ├── tax/
│   │   ├── lot_tracker.py       # Per-lot FIFO tracking
│   │   ├── equity_tax.py        # LTCG/STCG engine
│   │   ├── crypto_tax.py        # 30% + TDS engine
│   │   ├── mf_tax.py            # Mutual fund tax engine
│   │   ├── fd_tax.py            # FD interest + TDS
│   │   ├── tlh_scanner.py       # Tax loss harvesting
│   │   └── tax_calendar.py      # Advance tax dates, LTCG unlock
│   │
│   ├── family/
│   │   ├── member.py            # Individual member model
│   │   ├── family_unit.py       # Family aggregation
│   │   └── huf.py               # HUF-specific logic
│   │
│   ├── ai/
│   │   ├── context_builder.py   # Builds structured context for Claude
│   │   ├── cfo_engine.py        # Claude API calls, prompt management
│   │   ├── prompts/
│   │   │   ├── portfolio_health.txt
│   │   │   ├── tax_advice.txt
│   │   │   ├── scenario_analysis.txt
│   │   │   └── daily_digest.txt
│   │   └── response_parser.py   # Parses Claude output to structured data
│   │
│   └── alerts/
│       ├── ltcg_watcher.py
│       ├── tds_tracker.py
│       └── digest.py            # Telegram / email digest
│
├── api/
│   ├── main.py                  # FastAPI app
│   ├── routes/
│   │   ├── portfolio.py
│   │   ├── tax.py
│   │   ├── family.py
│   │   └── ai.py
│   └── schemas/
│       ├── asset.py
│       ├── tax.py
│       └── family.py
│
├── dashboard/
│   ├── app.py                   # Streamlit entry point
│   ├── pages/
│   │   ├── 01_overview.py       # Family net worth overview
│   │   ├── 02_tax_center.py     # Tax liability + TLH
│   │   ├── 03_cfo_chat.py       # Claude CFO interface
│   │   ├── 04_ltcg_calendar.py  # LTCG unlock timeline
│   │   └── 05_family.py         # Per-member breakdown
│   └── components/
│       ├── charts.py            # Plotly charts
│       └── cards.py             # Metric cards
│
├── data/
│   ├── schemas/
│   │   └── manual_asset_schema.json
│   └── sample/
│       └── sample_portfolio.json  # Demo data for testing
│
├── tests/
│   ├── test_tax_engine.py       # Tax computation unit tests
│   ├── test_lot_tracker.py
│   ├── test_aggregator.py
│   └── test_tlh_scanner.py
│
├── config/
│   ├── settings.py              # Pydantic settings
│   └── .env.example
│
├── requirements.txt
├── docker-compose.yml
└── README.md
```

---

## Core Modules — Deep Dive

### Unified Asset Schema
Every asset, regardless of source, is normalized to:
```python
@dataclass
class AssetLot:
    asset_id: str               # Unique lot identifier
    symbol: str                 # RELIANCE.NS, BTC, HDFCMF001
    asset_class: AssetClass     # EQUITY | CRYPTO | MF | FD | GOLD | US_EQUITY
    platform: str               # zerodha | binance | coindcx | manual
    member_id: str              # Which family member holds this
    quantity: Decimal
    acquisition_date: date
    cost_basis_per_unit: Decimal  # In INR
    current_price: Decimal        # In INR (converted for crypto)
    
    # Computed fields
    @property
    def holding_days(self) -> int: ...
    
    @property
    def is_long_term(self) -> bool: ...
    
    @property
    def unrealized_gain(self) -> Decimal: ...
    
    @property
    def tax_on_sale_today(self) -> TaxBreakdown: ...
```

### Tax Engine — Equity LTCG Computation
```python
class EquityTaxEngine:
    """
    Implements Indian equity tax rules FY2025-26:
    - STCG (holding < 12 months): 20% flat
    - LTCG (holding >= 12 months): 12.5% above ₹1,25,000 annual exemption
    - LTCG exemption is per-individual, per-financial-year
    - Grandfathering: cost basis for pre-Jan-31-2018 holdings is max(actual, Jan31 price)
    """
    
    def compute_tax_if_sold(
        self, 
        lots: list[AssetLot], 
        ytd_realized_ltcg: Decimal,
        ytd_realized_stcg: Decimal
    ) -> TaxBreakdown:
        ...
    
    def ltcg_unlock_calendar(
        self, 
        lots: list[AssetLot]
    ) -> list[UnlockEvent]:
        """Returns sorted list of dates when lots cross 12-month threshold"""
        ...
    
    def optimal_sell_date(
        self, 
        lot: AssetLot
    ) -> SellRecommendation:
        """Computes tax delta between selling today vs. LTCG unlock date"""
        ...
```

### Claude Context Builder
```python
class CFOContextBuilder:
    """
    Builds a structured, token-efficient context payload for Claude.
    Claude never receives raw API data — only computed, structured facts.
    """
    
    def build_portfolio_context(self, family: FamilyUnit) -> dict:
        return {
            "summary": {
                "total_net_worth_inr": ...,
                "asset_class_breakdown": {...},
                "ytd_tax_paid": ...,
                "projected_fy_tax": ...,
            },
            "tax_flags": [
                {
                    "type": "LTCG_UNLOCK_IMMINENT",
                    "symbol": "RELIANCE",
                    "days_remaining": 7,
                    "tax_saving_if_waited": 18400
                },
                ...
            ],
            "concentration_risks": [...],
            "tlh_opportunities": [...],
            "family_members": [...],
        }
```

---

## Tech Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| Core language | Python 3.11+ | JD requirement, async support |
| API framework | FastAPI | Async, type-safe, production-grade |
| Dashboard | Streamlit | Fast UI iteration |
| AI reasoning | Claude claude-sonnet-4 via Anthropic SDK | JD explicitly mentions Claude |
| Equity data | Zerodha Kite Connect | Official Indian broker API |
| Crypto data | Binance + CoinDCX REST APIs | JD explicitly asks for exchange API experience |
| Price feeds | yfinance + BSE/NSE unofficial | Free, reliable for Indian equities |
| Data validation | Pydantic v2 | Schema enforcement across all asset types |
| Decimal math | Python `decimal.Decimal` | Mandatory for financial computation — no float |
| Charts | Plotly | Interactive portfolio visualizations |
| Testing | pytest + hypothesis | Property-based tests for tax engine edge cases |
| Containerization | Docker + docker-compose | One-command setup |
| Storage | SQLite (dev) → PostgreSQL (prod) | Lot history, realized gains tracking |

---

## Tax Computation Accuracy — Design Principles

Financial computation is unforgiving. WealthMap is built with these non-negotiables:

1. **No floats in tax math.** Every monetary value uses `decimal.Decimal` with explicit precision. `0.1 + 0.2 != 0.3` in float — unacceptable in a tax engine.

2. **FIFO lot tracking by default.** Each purchase creates a separate lot with its own acquisition date and cost basis. Selling always consumes the oldest lot first (FIFO), which is the standard for Indian tax computation.

3. **FY-aware aggregation.** Indian financial year runs April 1 – March 31. The ₹1.25L LTCG exemption resets every April 1. All aggregation respects this boundary.

4. **Grandfathering clause implementation.** For equity positions acquired before January 31, 2018, the cost basis is `max(actual_cost, closing_price_jan31_2018)` per CBDT guidelines.

5. **TDS tracking as a first-class concern.** Crypto TDS (1% per transaction) is tracked independently of tax liability. These are reconcilable against Form 26AS.

6. **Conservative estimates for Claude.** Claude's reasoning output is always marked as advisory. Tax computation numbers are computed deterministically in Python — Claude explains them, never calculates them.

---

## Setup & Installation

### Prerequisites
- Python 3.11+
- Zerodha Kite Connect API credentials
- Binance API credentials (read-only scope)
- Anthropic API key
- CoinDCX API credentials (optional)

### 1. Clone and install
```bash
git clone https://github.com/yourusername/wealthmap.git
cd wealthmap
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp config/.env.example .env
```

Edit `.env`:
```env
# Anthropic
ANTHROPIC_API_KEY=your_key_here

# Zerodha Kite Connect
KITE_API_KEY=your_key
KITE_API_SECRET=your_secret
KITE_ACCESS_TOKEN=your_token  # Generated via Kite auth flow

# Binance (read-only API key recommended)
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret

# CoinDCX (optional)
COINDCX_API_KEY=your_key
COINDCX_API_SECRET=your_secret

# App config
FY_START_MONTH=4  # April
DEFAULT_MEMBER_ID=primary
TELEGRAM_BOT_TOKEN=optional
```

### 3. Run with Docker (recommended)
```bash
docker-compose up --build
```

Dashboard available at `http://localhost:8501`
API docs at `http://localhost:8000/docs`

### 4. Run locally
```bash
# Start API
uvicorn api.main:app --reload --port 8000

# Start dashboard (separate terminal)
streamlit run dashboard/app.py
```

### 5. Load sample portfolio (no API keys needed)
```bash
python scripts/load_sample_data.py
```
This loads `data/sample/sample_portfolio.json` — a realistic fictional HNI portfolio for demo and development purposes.

---

## API Reference

### Portfolio Endpoints
```
GET  /portfolio/family                    → Full family portfolio snapshot
GET  /portfolio/member/{member_id}        → Individual member portfolio
GET  /portfolio/net-worth                 → Current net worth breakdown
POST /portfolio/manual-asset              → Add manual asset (gold, real estate, FD)
```

### Tax Endpoints
```
GET  /tax/liability                       → Current FY tax liability (all members)
GET  /tax/ltcg-calendar                   → Upcoming LTCG unlock events (30/60/90 days)
POST /tax/simulate-sale                   → "If I sell X units of Y today, what's my tax?"
GET  /tax/tlh-opportunities               → Tax loss harvesting candidates
GET  /tax/crypto-tds                      → YTD TDS deducted vs. liability
GET  /tax/advance-tax                     → Advance tax installments due
```

### AI Endpoints
```
POST /ai/portfolio-health                 → Claude portfolio assessment
POST /ai/tax-advice                       → Claude tax optimization advice
POST /ai/scenario                         → Claude scenario analysis (free-form query)
GET  /ai/daily-digest                     → Generate daily CFO digest
```

---

## Example: Tax Simulation API

**Request:**
```json
POST /tax/simulate-sale
{
  "member_id": "father",
  "symbol": "RELIANCE.NS",
  "quantity": 50,
  "method": "FIFO"
}
```

**Response:**
```json
{
  "sale_summary": {
    "symbol": "RELIANCE.NS",
    "quantity": 50,
    "current_price_inr": 2847.50,
    "total_proceeds_inr": 142375.00
  },
  "lot_breakdown": [
    {
      "lot_id": "REL-20230315-001",
      "quantity": 30,
      "acquisition_date": "2023-03-15",
      "cost_basis_per_unit": 2340.00,
      "holding_days": 709,
      "classification": "LTCG",
      "gain_inr": 15225.00,
      "tax_rate": 0.125,
      "tax_inr": 1903.12
    },
    {
      "lot_id": "REL-20240901-002",
      "quantity": 20,
      "acquisition_date": "2024-09-01",
      "cost_basis_per_unit": 2680.00,
      "holding_days": 233,
      "classification": "STCG",
      "gain_inr": 3350.00,
      "tax_rate": 0.20,
      "tax_inr": 670.00
    }
  ],
  "tax_summary": {
    "total_gain_inr": 18575.00,
    "ltcg_this_transaction": 15225.00,
    "ltcg_ytd_before_this": 87000.00,
    "ltcg_exemption_remaining": 38000.00,
    "effective_ltcg_taxable": 0.00,
    "stcg_taxable": 3350.00,
    "total_tax_inr": 670.00
  },
  "advisory": {
    "wait_recommendation": false,
    "reason": "All LTCG lots are already long-term. Proceed if needed.",
    "alternative": "The 20 STCG units will qualify for LTCG treatment on 2025-09-01 — waiting saves ₹462."
  }
}
```

---

## Example: Claude CFO Response

**User query:** *"Should I sell my Bitcoin position or wait? I need ₹5L for a property down payment."*

**Claude receives (structured context, not raw query):**
```json
{
  "query": "Should I sell BTC? Need ₹5L for property purchase.",
  "portfolio_context": {
    "btc_holding": {
      "quantity": 0.18,
      "cost_basis_inr": 3240000,
      "current_value_inr": 3890000,
      "unrealized_gain_inr": 650000,
      "tax_on_sale": 195000,
      "net_proceeds_after_tax": 3695000
    },
    "equity_unrealized_losses": [
      {"symbol": "ZOMATO.NS", "unrealized_loss_inr": 45000},
      {"symbol": "PAYTM.NS", "unrealized_loss_inr": 28000}
    ],
    "fd_maturity_schedule": [
      {"bank": "HDFC", "maturity_date": "2025-07-15", "amount_inr": 300000}
    ],
    "ytd_crypto_gains_realized": 120000
  }
}
```

**Claude's response:**
```
Before liquidating BTC, consider this sequencing:

1. Your HDFC FD matures July 15 — that's ₹3L in 73 days with no tax cost beyond 
   slab-rate interest. If the property timeline allows, this covers 60% of your need 
   without triggering crypto tax.

2. Selling BTC today generates ₹6.5L gain, taxed at 30% flat — that's ₹1.95L in tax.
   Your net proceeds on ₹5L target sale would require liquidating more than ₹5L worth 
   to account for tax drag.

3. You hold ₹73,000 in unrealized equity losses (Zomato + Paytm). Under Indian tax 
   law, these cannot offset your crypto gains (Section 115BBH). Selling them provides 
   no tax benefit against this transaction.

Recommendation: Partial FD premature withdrawal (usually 0.5-1% penalty) + partial 
BTC sale is likely cheaper than full BTC liquidation. Run the property closing date 
past a CA — if it's post-July 15, the FD-first strategy saves approximately ₹1.4L 
in tax.
```

---

## Testing

WealthMap's tax engine has deterministic outputs — every edge case must be tested.

```bash
# Run full test suite
pytest tests/ -v

# Run only tax engine tests
pytest tests/test_tax_engine.py -v

# Property-based tests (hypothesis generates edge cases automatically)
pytest tests/test_lot_tracker.py --hypothesis-show-statistics
```

Key test scenarios:
- Grandfathering clause (pre-2018 holdings)
- FY boundary (sale spanning March 31 / April 1)
- LTCG exemption exhaustion across multiple lots
- Crypto TDS reconciliation across 100+ transactions
- HUF vs. individual tax slab differences
- Family-level LTCG aggregation (exemption is per-individual, not per-family)

---

## Current Limitations & Roadmap

**Known limitations (honest):**
- Zerodha Kite requires daily re-authentication (token expires). Auto-refresh via TOTP planned.
- MF NAV data relies on AMFI daily file — intraday NAV not available by design.
- Real estate valuation is manual input only. Automated circle rate integration is a future milestone.
- This is not a SEBI-registered advisory platform. All Claude output is informational only.

**Roadmap:**
- [ ] US equity integration via Vested API
- [ ] Automated ITR-2 Schedule AL (foreign assets) pre-fill
- [ ] WhatsApp digest (in addition to Telegram)
- [ ] Multi-CA collaboration mode (read-only CA access to family portfolio)
- [ ] Advance tax reminder system with UPI deep-link to NSDL
- [ ] Backtesting module — *"If you had followed TLH suggestions last year, you would have saved ₹X"*

---

## Disclaimer

WealthMap is a personal project for educational and informational purposes. It is **not** a SEBI-registered investment advisor or tax consultant. Tax laws change — always verify computations with a qualified CA before making financial decisions. The developer assumes no liability for financial decisions made based on this tool's output.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built with Python, Claude, and a deep frustration with Indian wealth management fragmentation.
</p>
