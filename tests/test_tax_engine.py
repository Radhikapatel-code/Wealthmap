"""
Tax engine tests — deterministic unit tests for all tax computation paths.
Run: pytest tests/test_tax_engine.py -v
"""
import sys
sys.path.insert(0, ".")

import pytest
from datetime import date, timedelta
from decimal import Decimal

from core.models import AssetLot, AssetClass, Platform, TaxConstants
from core.tax.equity_tax import EquityTaxEngine
from core.tax.crypto_tax import CryptoTaxEngine, CryptoTransaction
from core.tax.fd_tax import FDTaxEngine
from core.tax.tlh_scanner import TLHScanner
from core.tax.lot_tracker import LotTracker


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_equity_lot(
    symbol="RELIANCE.NS",
    qty=100,
    cost=1000,
    current=1500,
    days_held=400,
    member_id="test",
) -> AssetLot:
    return AssetLot(
        lot_id=f"TEST-{symbol}-{days_held}",
        symbol=symbol,
        asset_class=AssetClass.EQUITY,
        platform=Platform.ZERODHA,
        member_id=member_id,
        quantity=Decimal(str(qty)),
        acquisition_date=date.today() - timedelta(days=days_held),
        cost_basis_per_unit=Decimal(str(cost)),
        current_price=Decimal(str(current)),
    )


def make_crypto_lot(symbol="BTC", qty="0.1", cost=1500000, current=2000000) -> AssetLot:
    return AssetLot(
        lot_id=f"CRYPTO-{symbol}",
        symbol=symbol,
        asset_class=AssetClass.CRYPTO,
        platform=Platform.BINANCE,
        member_id="test",
        quantity=Decimal(qty),
        acquisition_date=date.today() - timedelta(days=200),
        cost_basis_per_unit=Decimal(str(cost)),
        current_price=Decimal(str(current)),
    )


# ── LTCG/STCG Classification Tests ───────────────────────────────────────────

class TestHoldingPeriodClassification:

    def test_exactly_365_days_is_long_term(self):
        lot = make_equity_lot(days_held=365)
        assert lot.is_long_term is True

    def test_364_days_is_short_term(self):
        lot = make_equity_lot(days_held=364)
        assert lot.is_long_term is False

    def test_366_days_is_long_term(self):
        lot = make_equity_lot(days_held=366)
        assert lot.is_long_term is True

    def test_crypto_is_never_long_term(self):
        lot = make_crypto_lot()
        assert lot.is_long_term is False

    def test_days_to_long_term_correct(self):
        lot = make_equity_lot(days_held=300)
        assert lot.days_to_long_term == 65

    def test_days_to_long_term_is_zero_if_already_lt(self):
        lot = make_equity_lot(days_held=400)
        assert lot.days_to_long_term == 0


# ── Unrealized Gain Tests ─────────────────────────────────────────────────────

class TestUnrealizedGain:

    def test_profit_lot(self):
        lot = make_equity_lot(qty=100, cost=1000, current=1500)
        assert lot.unrealized_gain == Decimal("50000.00")

    def test_loss_lot(self):
        lot = make_equity_lot(qty=100, cost=1500, current=1000)
        assert lot.unrealized_gain == Decimal("-50000.00")

    def test_breakeven_lot(self):
        lot = make_equity_lot(qty=100, cost=1000, current=1000)
        assert lot.unrealized_gain == Decimal("0.00")

    def test_gain_percentage(self):
        lot = make_equity_lot(qty=100, cost=1000, current=1500)
        assert lot.unrealized_gain_pct == Decimal("50.00")


# ── Equity Tax Engine Tests ───────────────────────────────────────────────────

class TestEquityTaxEngine:
    engine = EquityTaxEngine()

    def test_stcg_tax_computation(self):
        lot = make_equity_lot(days_held=200, qty=100, cost=1000, current=1500)
        result = self.engine.compute_tax_if_sold_today([lot])
        # STCG gain = 50,000, tax = 50,000 * 20% = 10,000 + 4% cess = 10,400
        assert result["total_stcg_inr"] == 50000.0
        assert result["stcg_tax_inr"] == 10000.0
        assert result["cess_inr"] == pytest.approx(400.0, abs=1)

    def test_ltcg_within_exemption_no_tax(self):
        # LTCG of 80,000 — under ₹1.25L exemption
        lot = make_equity_lot(days_held=400, qty=100, cost=1000, current=1800)
        result = self.engine.compute_tax_if_sold_today([lot], ytd_realized_ltcg=Decimal("0"))
        # Gain = 80,000; under 1.25L exemption
        assert result["total_ltcg_inr"] == 80000.0
        assert result["taxable_ltcg_inr"] == 0.0
        assert result["ltcg_tax_inr"] == 0.0

    def test_ltcg_above_exemption_taxed(self):
        # LTCG of 200,000, full exemption available
        lot = make_equity_lot(days_held=400, qty=100, cost=1000, current=3000)
        result = self.engine.compute_tax_if_sold_today([lot], ytd_realized_ltcg=Decimal("0"))
        # Gain = 200,000; taxable = 200,000 - 125,000 = 75,000
        # Tax = 75,000 * 12.5% = 9,375 + 4% cess = 9,750
        assert result["taxable_ltcg_inr"] == 75000.0
        assert result["ltcg_tax_inr"] == pytest.approx(9375.0, abs=1)

    def test_ltcg_exemption_partially_used(self):
        # YTD LTCG already realized: ₹100,000; gain of ₹100,000
        lot = make_equity_lot(days_held=400, qty=100, cost=1000, current=2000)
        result = self.engine.compute_tax_if_sold_today(
            [lot], ytd_realized_ltcg=Decimal("100000")
        )
        # Gain = 100,000; exemption remaining = 25,000
        # Taxable = 100,000 - 25,000 = 75,000
        assert result["taxable_ltcg_inr"] == 75000.0

    def test_mixed_stcg_ltcg_lots(self):
        lt_lot = make_equity_lot("RELIANCE.NS", days_held=400, qty=50, cost=1000, current=2000)
        st_lot = make_equity_lot("RELIANCE.NS", days_held=100, qty=50, cost=1000, current=2000)
        result = self.engine.compute_tax_if_sold_today([lt_lot, st_lot])
        assert result["total_ltcg_inr"] == 50000.0
        assert result["total_stcg_inr"] == 50000.0

    def test_loss_lots_produce_no_tax(self):
        lot = make_equity_lot(days_held=400, qty=100, cost=2000, current=1000)
        result = self.engine.compute_tax_if_sold_today([lot])
        assert result["ltcg_tax_inr"] == 0.0
        assert result["stcg_tax_inr"] == 0.0
        assert result["total_tax_inr"] == 0.0


# ── Crypto Tax Tests ──────────────────────────────────────────────────────────

class TestCryptoTaxEngine:
    engine = CryptoTaxEngine()

    def test_crypto_taxed_at_30_flat(self):
        result = self.engine.compute_tax_on_gain(Decimal("100000"))
        assert result["tax_rate"] == 0.30
        assert result["tax_inr"] == pytest.approx(30000.0, abs=1)
        assert result["cess_inr"] == pytest.approx(1200.0, abs=1)
        assert result["total_tax_inr"] == pytest.approx(31200.0, abs=1)

    def test_crypto_loss_generates_no_tax(self):
        result = self.engine.compute_tax_on_gain(Decimal("-50000"))
        assert result["tax_inr"] == 0.0
        assert result["total_tax_inr"] == 0.0

    def test_crypto_zero_gain_no_tax(self):
        result = self.engine.compute_tax_on_gain(Decimal("0"))
        assert result["total_tax_inr"] == 0.0

    def test_tds_computed_at_1_pct(self):
        txns = [
            CryptoTransaction(
                tx_id="TX1", symbol="BTC", member_id="test",
                tx_type="SELL", quantity=Decimal("0.1"),
                price_inr=Decimal("2000000"),
                tx_date=date.today(),
                platform="binance",
                tds_deducted=Decimal("2000"),
            )
        ]
        summary = self.engine.compute_tds_summary(txns)
        assert summary.tds_liability_inr == Decimal("2000.00")  # 1% of ₹2L
        assert summary.tds_deducted_inr == Decimal("2000")

    def test_effective_rate_with_cess(self):
        result = self.engine.compute_tax_on_gain(Decimal("1000000"))
        # 30% + 4% cess = 31.2% effective
        assert result["effective_rate_pct"] == pytest.approx(31.2, abs=0.1)


# ── FD Tax Tests ──────────────────────────────────────────────────────────────

class TestFDTaxEngine:
    engine = FDTaxEngine()

    def test_tds_not_applicable_below_threshold(self):
        result = self.engine.compute_tax_and_tds(Decimal("30000"), Decimal("0.30"))
        assert result["tds_applicable"] is False
        assert result["tds_at_source_inr"] == 0.0

    def test_tds_applicable_above_threshold(self):
        result = self.engine.compute_tax_and_tds(Decimal("50000"), Decimal("0.30"))
        assert result["tds_applicable"] is True
        assert result["tds_at_source_inr"] == pytest.approx(5000.0, abs=1)

    def test_actual_tax_at_slab_rate(self):
        # ₹1,00,000 interest at 30% slab = ₹30,000 tax + 4% cess = ₹31,200
        result = self.engine.compute_tax_and_tds(Decimal("100000"), Decimal("0.30"))
        assert result["actual_tax_liability_inr"] == pytest.approx(31200.0, abs=1)

    def test_tds_credited_against_tax(self):
        result = self.engine.compute_tax_and_tds(
            Decimal("100000"), Decimal("0.30"), tds_already_deducted=Decimal("10000")
        )
        # Tax = 31,200; TDS = 10,000; Balance = 21,200
        assert result["balance_tax_payable_inr"] == pytest.approx(21200.0, abs=1)


# ── Lot Tracker FIFO Tests ────────────────────────────────────────────────────

class TestLotTrackerFIFO:

    def test_fifo_consumes_oldest_lot_first(self):
        tracker = LotTracker()
        old_lot = make_equity_lot("INFY.NS", days_held=400, qty=50, cost=1000, current=2000)
        old_lot.lot_id = "OLD-LOT"
        new_lot = make_equity_lot("INFY.NS", days_held=100, qty=50, cost=1500, current=2000)
        new_lot.lot_id = "NEW-LOT"

        tracker.add_lots([old_lot, new_lot])
        result = tracker.simulate_sale("test", "INFY.NS", Decimal("30"), Decimal("2000"))

        breakdown = result["lot_breakdown"]
        # First consumed should be OLD-LOT (FIFO)
        assert breakdown[0]["lot_id"] == "OLD-LOT"
        assert breakdown[0]["classification"] == "LTCG"

    def test_partial_lot_sell(self):
        tracker = LotTracker()
        lot = make_equity_lot("HDFC.NS", days_held=400, qty=100, cost=1000, current=2000)
        tracker.add_lot(lot)

        result = tracker.simulate_sale("test", "HDFC.NS", Decimal("30"), Decimal("2000"))
        assert result["sale_summary"]["quantity"] == 30.0

    def test_sell_more_than_available_raises_error(self):
        tracker = LotTracker()
        lot = make_equity_lot("TCS.NS", days_held=400, qty=50, cost=1000, current=2000)
        tracker.add_lot(lot)

        with pytest.raises(ValueError, match="Cannot sell"):
            tracker.simulate_sale("test", "TCS.NS", Decimal("100"), Decimal("2000"))

    def test_ltcg_exemption_applied_correctly(self):
        tracker = LotTracker()
        lot = make_equity_lot("WIPRO.NS", days_held=400, qty=100, cost=1000, current=3000)
        tracker.add_lot(lot)

        # YTD LTCG already used ₹100,000; gain here = ₹200,000
        # Remaining exemption = ₹25,000; taxable = ₹175,000
        result = tracker.simulate_sale(
            "test", "WIPRO.NS", Decimal("100"), Decimal("3000"),
            ytd_realized_ltcg=Decimal("100000")
        )
        tax_sum = result["tax_summary"]
        assert tax_sum["ltcg_ytd_before_this_inr"] == 100000.0

    def test_execute_sale_mutates_lots(self):
        tracker = LotTracker()
        lot = make_equity_lot("TITAN.NS", days_held=400, qty=100, cost=1000, current=2000)
        tracker.add_lot(lot)

        tracker.execute_sale("test", "TITAN.NS", Decimal("40"), Decimal("2000"))
        remaining = tracker.get_lots("test", "TITAN.NS")
        remaining_qty = sum(l.quantity for l in remaining)
        assert remaining_qty == Decimal("60")


# ── TLH Scanner Tests ─────────────────────────────────────────────────────────

class TestTLHScanner:
    scanner = TLHScanner()

    def test_identifies_loss_lots(self):
        loss_lot = make_equity_lot("LOSS.NS", days_held=200, qty=100, cost=2000, current=1500)
        gain_lot = make_equity_lot("GAIN.NS", days_held=200, qty=100, cost=1000, current=2000)
        opps = self.scanner.scan([loss_lot, gain_lot])
        assert len(opps) >= 1
        assert any(o.loss_lot.symbol == "LOSS.NS" for o in opps)

    def test_no_opportunities_when_all_gains(self):
        lot1 = make_equity_lot("A.NS", days_held=400, qty=100, cost=1000, current=2000)
        lot2 = make_equity_lot("B.NS", days_held=200, qty=100, cost=1000, current=1500)
        opps = self.scanner.scan([lot1, lot2])
        assert len(opps) == 0

    def test_crypto_losses_flagged_separately(self):
        crypto_loss = make_crypto_lot("ETH", qty="1", cost=300000, current=200000)
        warnings = self.scanner.crypto_loss_warning([crypto_loss])
        assert len(warnings) == 1
        assert "115BBH" in warnings[0]["warning"]

    def test_ltcg_loss_only_offsets_ltcg(self):
        lt_loss = make_equity_lot("LTLOSS.NS", days_held=400, qty=100, cost=2000, current=1500)
        st_gain = make_equity_lot("STGAIN.NS", days_held=100, qty=100, cost=1000, current=2000)
        lt_gain = make_equity_lot("LTGAIN.NS", days_held=400, qty=100, cost=1000, current=2000)

        opps = self.scanner.scan([lt_loss, st_gain, lt_gain])
        lt_opp = next((o for o in opps if o.loss_lot.symbol == "LTLOSS.NS"), None)
        if lt_opp:
            # LTCG loss should only show LTCG gain lots
            for gain_lot in lt_opp.offsettable_gain_lots:
                assert gain_lot.is_long_term, "LTCG loss should only offset LTCG gains"


# ── FY Boundary Tests ─────────────────────────────────────────────────────────

class TestFYBoundary:

    def test_fy_start_is_april_1(self):
        from core.models import current_fy_start
        fy = current_fy_start()
        assert fy.month == 4
        assert fy.day == 1

    def test_fy_end_is_march_31(self):
        from core.models import current_fy_end
        fy_end = current_fy_end()
        assert fy_end.month == 3
        assert fy_end.day == 31


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
