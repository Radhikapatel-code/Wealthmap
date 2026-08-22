# WealthMap 🗺️
![CI](https://img.shields.io/badge/ci-pass-brightgreen)
![Python](https://img.shields.io/badge/python-3.11-blue)
![Rust](https://img.shields.io/badge/rust-stable-orange)
![License](https://img.shields.io/badge/Wealthmap-MIT-yellow)
  [![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)]([https://wealthmap-dashboard.onrender.com/])
### AI-Powered Portfolio Intelligence for High-Net-Worth Indian Families

WealthMap is a cross-asset portfolio intelligence engine built specifically for Indian HNI families — aggregating equity, crypto, and mutual fund data, computing real Indian tax liability at the lot level, and surfacing Gemini-powered CFO-grade reasoning across the entire family's wealth picture.

---
Live : https://wealthmap-dashboard.onrender.com/

## 🚀 Quick Start

```bash
git clone https://github.com/Radhikapatel-code/Wealthmap.git
cd Wealthmap
python -m venv venv && source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# (Optional) Build high-performance native Rust engine extension
make build-engine

# Run dashboard
streamlit run dashboard/app.py

# Run API backend
uvicorn api.main:app --reload --port 8000
```

Dashboard → http://localhost:8501  
API Docs  → http://localhost:8000/docs

---

## 🐳 Docker

```bash
cp config/.env.example .env
docker-compose up --build
```

---

## 🔑 Configuration

Copy `config/.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Optional (for AI) | Google Gemini API key ([get free key](https://aistudio.google.com/app/apikey)) |
| `API_KEY` | Optional | Bearer / `X-API-Key` token to protect API endpoints |
| `CORS_ALLOWED_ORIGINS` | Optional | Allowed frontend origins (default: localhost 8501, 3000, 8000) |
| `USD_INR_RATE` | Optional | Fallback USD/INR rate (live FX fetched automatically with TTL caching) |
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
│  │ Zerodha API  │───▶│ Portfolio    │───▶│ Gemini       │  │
│  │ Binance API  │    │ Normalizer   │    │ CFO Engine   │  │
│  │ CoinDCX API  │    │              │    │              │  │
│  │ Yahoo Finance│    │ Tax Engine   │    │ Structured   │  │
│  │ Live FX Feed │    │ (FIFO lots)  │    │ Context      │  │
│  │ Manual Input │    │ TLH Scanner  │    │ Builder      │  │
│  └──────────────┘    │ Tax Calendar │    └──────────────┘  │
│                      │ State Manager│            │          │
│                      └──────────────┘            ▼          │
│                                          ┌──────────────┐  │
│                                          │  FastAPI     │  │
│                                          │  Backend     │  │
│                                          │  (Auth+CORS) │  │
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

## ⚡ High-Performance Columnar Engine (`wealthmap-engine`)

WealthMap includes a native Rust engine [`wealthmap-engine`](./wealthmap-engine/) powering stateful FIFO tax-lot matching, portfolio aggregation, and SQL queries over Arrow memory batches.

- **Columnar Pipeline Execution**: Built using `arrow-rs` vector operators (`Scan -> Filter -> Sort -> FIFOMatch -> GroupAggregate`).
- **Parallel Multi-Portfolio Execution**: Work-stealing Rayon thread pool for multi-portfolio scalability (**22.95 ms** across portfolios).
- **Python / PyO3 Interop**: Zero-overhead in-process C-extension bindings (`RustEngineBridge`).
- **SQL Parser**: Standard SQL query parsing (`sqlparser-rs`) for dynamic analytical queries over tax lot streams.

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
| US Equity | Manual JSON (with live FX conversion) | ✅ |

### 2. Indian Tax Engine (FY 2025-26)
- **FIFO lot tracking** — every purchase is a separate lot with its own acquisition date and cost basis
- **LTCG/STCG classification** — to-the-day holding period accuracy  
- **₹1,25,000 LTCG exemption** — tracked per individual per FY (resets April 1) across all equity trades
- **Section 112A Grandfathering** — pre-Jan 31 2018 holdings use `max(actual_cost, min(Jan31_price, sale_price))`
- **Crypto: 30% flat** — no exemption, no loss offset (Section 115BBH)
- **FD: TDS tracking** — threshold alerts at ₹40,000
- **LTCG Unlock Calendar** — alerts 7 days before positions cross 12-month mark
- **Tax Loss Harvesting** — scans for offset opportunities with risk warnings

### 3. Gemini AI CFO Layer
The AI engine (Google Gemini) receives structured, pre-computed context — never raw numbers:
- Full family asset breakdown
- Tax status per position (STCG/LTCG, holding days, unrealized gain)
- YTD realized gains and tax paid
- LTCG unlock events
- TLH opportunities

The AI never calculates tax — Python does. Gemini explains, contextualizes, and recommends.

### 4. Family Office View
- Multiple member profiles (Father, Mother, Adult Child, HUF)
- Consolidated net worth dashboard
- Per-member tax liability with individual LTCG exemptions
- Gift tax tracking (>₹50,000 intra-family transfers)

### 5. Security & State Concurrency
- Configurable API Key Authentication (`X-API-Key` or `Authorization: Bearer <key>`)
- Origin-restricted CORS policies
- Thread-safe state synchronization across concurrent requests

---

## 🧪 Testing

```bash
# Full test suite (55+ tests)
pytest tests/ -v

# Run Rust engine tests
cargo test --release --manifest-path wealthmap-engine/Cargo.toml
```

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

### AI (Gemini)
```
POST /ai/portfolio-health           Full portfolio assessment
POST /ai/tax-advice                 Tax optimization advice
POST /ai/scenario                   Free-form scenario analysis
POST /ai/chat                       Multi-turn CFO chat
GET  /ai/daily-digest               Daily digest
```

---

## ⚠️ Disclaimer

WealthMap is a personal project for educational and informational purposes. It is **not** a SEBI-registered investment advisor or tax consultant. Tax laws change — always verify computations with a qualified CA before making financial decisions.
