"""
Export Golden Dataset for Rust Engine Correctness Validation.

Generates realistic transaction histories (Buys & Sells), processes them
using WealthMap's existing Python LotTracker / EquityTaxEngine logic,
and exports the input transactions & expected outputs to JSON files in
../wealthmap-engine/testdata/
"""

from __future__ import annotations
import json
import os
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

# Add project root to sys.path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.models import AssetLot, AssetClass, Platform, TaxConstants, TaxClassification
from core.tax.lot_tracker import LotTracker

def build_golden_dataset():
    engine_testdata_dir = PROJECT_ROOT.parent / "wealthmap-engine" / "testdata"
    engine_testdata_dir.mkdir(parents=True, exist_ok=True)

    # 1. Synthesize input transactions across multiple accounts and tickers
    # Format: dict with member_id, symbol, side (BUY/SELL), date, quantity, price, asset_class, lot_id
    raw_transactions = [
        # --- Account: father | Symbol: RELIANCE.NS ---
        {"transaction_id": "TX-001", "member_id": "father", "symbol": "RELIANCE.NS", "side": "BUY", "date": "2023-01-15", "quantity": "100", "price": "2000.00", "asset_class": "EQUITY", "lot_id": "LOT-REL-1"},
        {"transaction_id": "TX-002", "member_id": "father", "symbol": "RELIANCE.NS", "side": "BUY", "date": "2023-06-20", "quantity": "50", "price": "2200.00", "asset_class": "EQUITY", "lot_id": "LOT-REL-2"},
        {"transaction_id": "TX-003", "member_id": "father", "symbol": "RELIANCE.NS", "side": "SELL", "date": "2024-03-10", "quantity": "70", "price": "2500.00", "asset_class": "EQUITY", "lot_id": None}, # Consumes 70 from LOT-REL-1 (STCG)
        {"transaction_id": "TX-004", "member_id": "father", "symbol": "RELIANCE.NS", "side": "SELL", "date": "2024-08-01", "quantity": "50", "price": "2800.00", "asset_class": "EQUITY", "lot_id": None}, # Consumes remaining 30 from LOT-REL-1 (LTCG) + 20 from LOT-REL-2 (LTCG)

        # --- Account: father | Symbol: INFY.NS ---
        {"transaction_id": "TX-005", "member_id": "father", "symbol": "INFY.NS", "side": "BUY", "date": "2022-05-10", "quantity": "200", "price": "1400.00", "asset_class": "EQUITY", "lot_id": "LOT-INFY-1"},
        {"transaction_id": "TX-006", "member_id": "father", "symbol": "INFY.NS", "side": "BUY", "date": "2024-01-15", "quantity": "100", "price": "1500.00", "asset_class": "EQUITY", "lot_id": "LOT-INFY-2"},
        {"transaction_id": "TX-007", "member_id": "father", "symbol": "INFY.NS", "side": "SELL", "date": "2024-09-20", "quantity": "250", "price": "1750.00", "asset_class": "EQUITY", "lot_id": None}, # Consumes 200 from LOT-INFY-1 (LTCG) + 50 from LOT-INFY-2 (STCG)

        # --- Account: mother | Symbol: HDFCBANK.NS ---
        {"transaction_id": "TX-008", "member_id": "mother", "symbol": "HDFCBANK.NS", "side": "BUY", "date": "2023-02-01", "quantity": "150", "price": "1600.00", "asset_class": "EQUITY", "lot_id": "LOT-HDFC-1"},
        {"transaction_id": "TX-009", "member_id": "mother", "symbol": "HDFCBANK.NS", "side": "SELL", "date": "2024-05-15", "quantity": "100", "price": "1700.00", "asset_class": "EQUITY", "lot_id": None}, # Consumes 100 from LOT-HDFC-1 (LTCG)

        # --- Account: son | Symbol: BTC ---
        {"transaction_id": "TX-010", "member_id": "son", "symbol": "BTC", "side": "BUY", "date": "2023-10-01", "quantity": "1.5", "price": "2500000.00", "asset_class": "CRYPTO", "lot_id": "LOT-BTC-1"},
        {"transaction_id": "TX-011", "member_id": "son", "symbol": "BTC", "side": "SELL", "date": "2024-04-10", "quantity": "0.8", "price": "5000000.00", "asset_class": "CRYPTO", "lot_id": None}, # Consumes 0.8 from LOT-BTC-1 (CRYPTO 30%)
    ]

    # Process FIFO matching per account and symbol
    matched_lots = []

    # Group transactions by (member_id, symbol)
    groups = {}
    for tx in raw_transactions:
        key = (tx["member_id"], tx["symbol"])
        groups.setdefault(key, []).append(tx)

    # Collect all (member_id, symbol) groups and sort them so that sells are
    # processed in chronological order per member.  This lets us accumulate
    # ytd_realized_ltcg correctly across symbols for the same individual
    # (the ₹1,25,000 LTCG exemption is per-individual, not per-symbol).
    ordered_sells: list[tuple[str, str, dict]] = []
    trackers: dict[tuple[str, str], LotTracker] = {}

    for (member_id, symbol), tx_list in groups.items():
        tracker = LotTracker()
        sorted_txs = sorted(tx_list, key=lambda x: x["date"])
        for tx in sorted_txs:
            if tx["side"] == "BUY":
                lot = AssetLot(
                    lot_id=tx["lot_id"],
                    symbol=symbol,
                    asset_class=AssetClass(tx["asset_class"]),
                    platform=Platform.ZERODHA if tx["asset_class"] != "CRYPTO" else Platform.BINANCE,
                    member_id=member_id,
                    quantity=Decimal(tx["quantity"]),
                    acquisition_date=date.fromisoformat(tx["date"]),
                    cost_basis_per_unit=Decimal(tx["price"]),
                    current_price=Decimal(tx["price"]),
                )
                tracker.add_lot(lot)
            elif tx["side"] == "SELL":
                ordered_sells.append((member_id, symbol, tx))
        trackers[(member_id, symbol)] = tracker

    # Sort all sells chronologically so exemption is consumed in date order
    ordered_sells.sort(key=lambda x: x[2]["date"])

    # Track per-member YTD realized LTCG for exemption accounting
    member_ytd_ltcg: dict[str, Decimal] = {}

    for member_id, symbol, tx in ordered_sells:
        tracker = trackers[(member_id, symbol)]
        sell_date = date.fromisoformat(tx["date"])
        sell_price = Decimal(tx["price"])
        sell_qty = Decimal(tx["quantity"])

        ytd_ltcg = member_ytd_ltcg.get(member_id, Decimal("0"))
        realized_txs = tracker.execute_sale(
            member_id=member_id,
            symbol=symbol,
            quantity=sell_qty,
            sale_price=sell_price,
            sale_date=sell_date,
            ytd_realized_ltcg=ytd_ltcg,
        )

        # Accumulate LTCG gains for this member's exemption tracking
        for rtx in realized_txs:
            if rtx.tax_breakdown.classification == TaxClassification.LTCG:
                gain = rtx.tax_breakdown.gross_gain
                if gain > Decimal("0"):
                    member_ytd_ltcg[member_id] = member_ytd_ltcg.get(member_id, Decimal("0")) + gain

            matched_lots.append({
                "member_id": rtx.member_id,
                "symbol": rtx.symbol,
                "lot_id": rtx.lot_id,
                "buy_date": rtx.acquisition_date.isoformat(),
                "sell_date": rtx.sale_date.isoformat(),
                "quantity": float(rtx.quantity),
                "buy_price": float(rtx.cost_basis_per_unit),
                "sell_price": float(rtx.sale_price_per_unit),
                "gross_gain_inr": float(rtx.tax_breakdown.gross_gain),
                "taxable_gain_inr": float(rtx.tax_breakdown.taxable_gain),
                "tax_rate": float(rtx.tax_breakdown.tax_rate),
                "tax_amount_inr": float(rtx.tax_breakdown.tax_amount),
                "cess_amount_inr": float(rtx.tax_breakdown.cess_amount),
                "total_tax_inr": float(rtx.tax_breakdown.total_tax),
                "classification": rtx.tax_breakdown.classification.value,
                "holding_days": (rtx.sale_date - rtx.acquisition_date).days,
            })

    # Group aggregates per (member_id, symbol, classification)
    aggregates = {}
    for lot in matched_lots:
        key = (lot["member_id"], lot["symbol"], lot["classification"])
        if key not in aggregates:
            aggregates[key] = {
                "member_id": lot["member_id"],
                "symbol": lot["symbol"],
                "classification": lot["classification"],
                "total_quantity": round(0.0, 4),
                "total_gross_gain_inr": round(0.0, 2),
                "total_taxable_gain_inr": round(0.0, 2),
                "total_tax_inr": round(0.0, 2),
            }
        aggregates[key]["total_quantity"] = round(aggregates[key]["total_quantity"] + lot["quantity"], 4)
        aggregates[key]["total_gross_gain_inr"] = round(aggregates[key]["total_gross_gain_inr"] + lot["gross_gain_inr"], 2)
        aggregates[key]["total_taxable_gain_inr"] = round(aggregates[key]["total_taxable_gain_inr"] + lot["taxable_gain_inr"], 2)
        aggregates[key]["total_tax_inr"] = round(aggregates[key]["total_tax_inr"] + lot["total_tax_inr"], 2)

    aggregate_list = list(aggregates.values())

    # Write input transactions file
    tx_file = engine_testdata_dir / "golden_transactions.json"
    with open(tx_file, "w") as f:
        json.dump(raw_transactions, f, indent=2)

    # Write expected matched lots output file
    lots_file = engine_testdata_dir / "golden_matched_lots.json"
    with open(lots_file, "w") as f:
        json.dump(matched_lots, f, indent=2)

    # Write expected aggregates output file
    agg_file = engine_testdata_dir / "golden_aggregates.json"
    with open(agg_file, "w") as f:
        json.dump(aggregate_list, f, indent=2)

    print(f"[Success] Exported golden dataset to {engine_testdata_dir}")
    print(f"  - Transactions: {len(raw_transactions)}")
    print(f"  - Matched Lots: {len(matched_lots)}")
    print(f"  - Aggregates:   {len(aggregate_list)}")

if __name__ == "__main__":
    build_golden_dataset()
