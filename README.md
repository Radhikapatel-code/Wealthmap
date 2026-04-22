# WealthMap 🗺️
### AI-Powered Portfolio Intelligence for High-Net-Worth Indian Families

WealthMap is a cross-asset portfolio intelligence engine built specifically for Indian HNI families — aggregating equity, crypto, and mutual fund data, computing real Indian tax liability at the lot level, and surfacing Claude-powered CFO-grade reasoning across the entire family's wealth picture.

---

## 🚀 Quick Start (Demo Mode — No API Keys Needed)

```bash
git clone https://github.com/yourusername/wealthmap.git
cd wealthmap
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Load demo data and verify setup
python scripts/load_sample_data.py

# Run dashboard
streamlit run dashboard/app.py

# Run API (separate terminal)
uvicorn api.main:app --reload --port 8000
```

Dashboard → http://localhost:8501  
API Docs  → http://localhost:8000/docs

---

## 🐳 Docker (Recommended)

```bash
cp config/.env.example .env
# Edit .env with your API keys

docker-compose up --build
```

---

## 🔑 Configuration

Copy `config/.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ For AI features | Claude API key |
| `KITE_API_KEY` + `KITE_ACCESS_TOKEN` | Optional | Zerodha equity data |
| `BINANCE_API_KEY` + `BINANCE_API_SECRET` | Optional | Binance crypto data |
| `COINDCX_API_KEY` | Optional | CoinDCX crypto data |
| `TELEGRAM_BOT_TOKEN` | Optional | Daily digest alerts |

Without exchange API keys, WealthMap runs with realistic mock/demo data.

---

## 📐 Architecture

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
│                      │ Tax Calendar │            │          │
│                      └──────────────┘            ▼          │
│                                          ┌──────────────┐  │
│                                          │  FastAPI     │  │
│                                          │  Backend     │  │
│                                          └──────┬───────┘  │
│                                                 │           │
│                                    ┌────────────┘           │
│                                    ▼                        │
│                          ┌──────────────────┐               │
│                          │  Streamlit       │               │
│                          │  Dashboard       │               │
│                          └──────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## 💡 Features

### 1. Multi-Asset Aggregation
| Asset | Source | Status |
|---|---|---|
| Indian Equity | Zerodha Kite API | ✅ |
| Crypto | Binance + CoinDCX | ✅ |
| Mutual Funds | CSV import / manual | ✅ |
| Fixed Deposits | Manual JSON | ✅ |
| Physical Gold | Manual JSON | ✅ |
| US Equity | Manual JSON | ✅ |

### 2. Indian Tax Engine
- **FIFO lot tracking** — every purchase is a separate lot with its own acquisition date and cost basis
- **LTCG/STCG classification** — to the day accuracy  
- **₹1,25,000 LTCG exemption** — tracked per individual per FY (resets April 1)
- **Grandfathering** — pre-Jan 31 2018 holdings use `max(actual_cost, Jan31_price)`
- **Crypto: 30% flat** — no exemption, no loss offset (Section 115BBH)
- **FD: TDS tracking** — threshold alerts at ₹40,000
- **LTCG Unlock Calendar** — alerts 7 days before positions cross 12-month mark
- **Tax Loss Harvesting** — scans for offset opportunities with risk warnings

### 3. Claude CFO Layer
Claude receives structured, pre-computed context — never raw numbers. It reasons over:
- Full family asset breakdown
- Tax status per position (STCG/LTCG, holding days, unrealized gain)
- YTD realized gains and tax paid
- LTCG unlock events
- TLH opportunities

Claude never calculates tax — Python does. Claude explains, contextualizes, and recommends.

### 4. Family Office View
- Multiple member profiles (Father, Mother, Adult Child, HUF)
- Consolidated net worth dashboard
- Per-member tax liability with individual LTCG exemptions
- Gift tax tracking (>₹50,000 intra-family transfers)

### 5. Alerts
- ⚡ LTCG unlock alerts (7 days before)
- 💰 Advance tax due date reminders
- 🚨 Crypto TDS reconciliation flags
- 📋 Daily digest (Telegram/email)

---

## 🧾 Tax Rules Implemented (FY 2025-26)

| Asset | Holding | Rate |
|---|---|---|
| Equity / Equity MF | < 12 months (STCG) | 20% flat |
| Equity / Equity MF | ≥ 12 months (LTCG) | 12.5% above ₹1,25,000 |
| Crypto | Any | 30% flat (Section 115BBH) |
| Crypto TDS | Per sale transaction | 1% (Section 194S) |
| Debt MF (post Apr 2023) | Any | Slab rate |
| FD Interest | Any | Slab rate (TDS at 10% above ₹40K) |
| Physical Gold | ≥ 2 years | 12.5% with indexation |
| US Equity | Any | 25% (DTAA) |

**Cess:** 4% health & education cess applies on all tax.

---

## 🛠️ Project Structure

```
wealthmap/
├── core/
│   ├── models.py               # AssetLot, TaxBreakdown, UnlockEvent
│   ├── aggregator/
│   │   ├── zerodha.py          # Kite Connect integration
│   │   ├── binance.py          # Binance + CoinDCX
│   │   ├── manual_import.py    # FD, gold, US equity
│   │   └── normalizer.py       # Unified aggregation entry point
│   ├── tax/
│   │   ├── lot_tracker.py      # FIFO lot management + sale simulation
│   │   ├── equity_tax.py       # LTCG/STCG engine
│   │   ├── crypto_tax.py       # 30% + TDS engine
│   │   ├── mf_tax.py           # Mutual fund tax
│   │   ├── fd_tax.py           # FD interest + TDS
│   │   ├── tlh_scanner.py      # Tax loss harvesting
│   │   └── tax_calendar.py     # Advance tax dates, LTCG unlock
│   ├── family/
│   │   ├── family_unit.py      # Family aggregation, gift tracking
│   │   └── huf.py              # HUF-specific tax logic
│   └── ai/
│       ├── context_builder.py  # Structured context for Claude
│       ├── cfo_engine.py       # Claude API calls
│       ├── response_parser.py  # Parse Claude output
│       └── prompts/            # System prompts
├── api/
│   ├── main.py                 # FastAPI app + all routes
│   └── schemas/asset.py        # Pydantic request/response models
├── dashboard/
│   ├── app.py                  # Streamlit entry point + sidebar
│   └── pages/
│       ├── 01_overview.py      # Portfolio overview
│       ├── 02_tax_center.py    # Tax + TLH + simulator
│       ├── 03_cfo_chat.py      # Claude CFO chat
│       ├── 04_ltcg_calendar.py # LTCG unlock timeline
│       └── 05_family.py        # Per-member breakdown
├── tests/
│   └── test_tax_engine.py      # 30+ unit tests
├── data/sample/sample_portfolio.json
├── config/settings.py
├── scripts/load_sample_data.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## 🧪 Testing

```bash
# Full test suite
pytest tests/ -v

# Tax engine only
pytest tests/test_tax_engine.py -v

# With coverage
pytest tests/ --cov=core --cov-report=term-missing

# Property-based tests (if hypothesis installed)
pytest tests/ --hypothesis-show-statistics
```

Key test scenarios covered:
- LTCG/STCG classification at exact 365-day boundary
- LTCG exemption application and partial use
- FIFO lot consumption and partial lot splits
- Crypto 30% flat tax and loss handling
- FD TDS threshold triggers
- TLH STCG vs LTCG offset rules
- FY boundary (April 1 reset)

---

## 📡 API Reference

### Portfolio
```
GET  /portfolio/family              Full family snapshot
GET  /portfolio/member/{id}         Individual member data
GET  /portfolio/net-worth           Net worth by class and member
POST /portfolio/manual-asset        Add FD / gold / US equity
```

### Tax
```
GET  /tax/liability                 YTD tax liability
GET  /tax/ltcg-calendar?days=90     LTCG unlock events
POST /tax/simulate-sale             Tax impact of proposed sale
GET  /tax/tlh-opportunities         TLH candidates
GET  /tax/advance-tax               Advance tax schedule
GET  /tax/key-dates                 All FY tax dates
```

### AI (Claude)
```
POST /ai/portfolio-health           Full portfolio assessment
POST /ai/tax-advice                 Tax optimization advice
POST /ai/scenario                   Free-form scenario analysis
POST /ai/chat                       Multi-turn CFO chat
GET  /ai/daily-digest               Daily digest
```

### Alerts
```
GET  /alerts                        All active alerts
```

---

## ⚠️ Disclaimer

WealthMap is a personal project for educational and informational purposes. It is **not** a SEBI-registered investment advisor or tax consultant. Tax laws change — always verify computations with a qualified CA before making financial decisions. The developer assumes no liability for financial decisions made based on this tool's output.

---

## 🗺️ Roadmap

- [ ] US equity integration via Vested API
- [ ] Automated ITR-2 Schedule AL pre-fill
- [ ] WhatsApp digest
- [ ] Multi-CA collaboration (read-only CA access)
- [ ] Advance tax UPI deep-link to NSDL
- [ ] Grandfathering data import from CDSL CAS
- [ ] Debt MF NAV from AMFI daily file
- [ ] Backtesting: "TLH savings last FY"
