"""Tax engine tests — deterministic unit tests for all tax computation paths."""
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
from core.aggregator.fx import FXRateService, get_fx_service
from core.aggregator.manual_import import ManualAssetImporter
from core.aggregator.binance import BinanceAggregator
from core.state_manager import PortfolioStateManager
from config.settings import Settings
from api.main import get_session_id


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


class TestSection112AGrandfathering:

    def test_grandfathering_capped_at_sale_price(self):
        lot = AssetLot(
            lot_id="GF-1",
            symbol="TCS.NS",
            asset_class=AssetClass.EQUITY,
            platform=Platform.ZERODHA,
            member_id="test",
            quantity=Decimal("10"),
            acquisition_date=date(2017, 6, 1),
            cost_basis_per_unit=Decimal("1000"),
            current_price=Decimal("1800"),
            grandfathered_cost=Decimal("2000"),
        )
        assert lot.effective_cost_basis_at(Decimal("1800")) == Decimal("1800")
        assert lot.effective_cost_basis_at(Decimal("2500")) == Decimal("2000")
        assert lot.effective_cost_basis_at(Decimal("800")) == Decimal("1000")


class TestEquityTaxEngine:
    engine = EquityTaxEngine()

    def test_stcg_tax_computation(self):
        lot = make_equity_lot(days_held=200, qty=100, cost=1000, current=1500)
        result = self.engine.compute_tax_if_sold_today([lot])
        assert result["total_stcg_inr"] == 50000.0
        assert result["stcg_tax_inr"] == 10000.0
        assert result["cess_inr"] == pytest.approx(400.0, abs=1)

    def test_ltcg_within_exemption_no_tax(self):
        lot = make_equity_lot(days_held=400, qty=100, cost=1000, current=1800)
        result = self.engine.compute_tax_if_sold_today([lot], ytd_realized_ltcg=Decimal("0"))
        assert result["total_ltcg_inr"] == 80000.0
        assert result["taxable_ltcg_inr"] == 0.0
        assert result["ltcg_tax_inr"] == 0.0

    def test_ltcg_above_exemption_taxed(self):
        lot = make_equity_lot(days_held=400, qty=100, cost=1000, current=3000)
        result = self.engine.compute_tax_if_sold_today([lot], ytd_realized_ltcg=Decimal("0"))
        assert result["taxable_ltcg_inr"] == 75000.0
        assert result["ltcg_tax_inr"] == pytest.approx(9375.0, abs=1)

    def test_ltcg_exemption_partially_used(self):
        lot = make_equity_lot(days_held=400, qty=100, cost=1000, current=2000)
        result = self.engine.compute_tax_if_sold_today(
            [lot], ytd_realized_ltcg=Decimal("100000")
        )
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
        assert summary.tds_liability_inr == Decimal("2000.00")
        assert summary.tds_deducted_inr == Decimal("2000")

    def test_effective_rate_with_cess(self):
        result = self.engine.compute_tax_on_gain(Decimal("1000000"))
        assert result["effective_rate_pct"] == pytest.approx(31.2, abs=0.1)


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
        result = self.engine.compute_tax_and_tds(Decimal("100000"), Decimal("0.30"))
        assert result["actual_tax_liability_inr"] == pytest.approx(31200.0, abs=1)

    def test_tds_credited_against_tax(self):
        result = self.engine.compute_tax_and_tds(
            Decimal("100000"), Decimal("0.30"), tds_already_deducted=Decimal("10000")
        )
        assert result["balance_tax_payable_inr"] == pytest.approx(21200.0, abs=1)


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

    def test_execute_sale_ltcg_exemption_applied(self):
        tracker = LotTracker()
        lot = make_equity_lot("RELIANCE.NS", days_held=400, qty=100, cost=1000, current=1350)
        tracker.add_lot(lot)

        realized = tracker.execute_sale(
            "test", "RELIANCE.NS", Decimal("100"), Decimal("1350"),
            ytd_realized_ltcg=Decimal("0"),
        )
        assert len(realized) == 1
        tb = realized[0].tax_breakdown
        assert tb.classification.value == "LTCG"
        assert tb.gross_gain == Decimal("35000.00")
        assert tb.taxable_gain == Decimal("0")
        assert tb.tax_amount == Decimal("0")
        assert tb.total_tax == Decimal("0")

    def test_execute_sale_ltcg_exemption_partially_used(self):
        tracker = LotTracker()
        lot = make_equity_lot("WIPRO.NS", days_held=400, qty=100, cost=1000, current=3000)
        tracker.add_lot(lot)

        realized = tracker.execute_sale(
            "test", "WIPRO.NS", Decimal("100"), Decimal("3000"),
            ytd_realized_ltcg=Decimal("100000"),
        )
        assert len(realized) == 1
        tb = realized[0].tax_breakdown
        assert tb.classification.value == "LTCG"
        assert tb.gross_gain == Decimal("200000.00")
        assert tb.taxable_gain == Decimal("175000")
        expected_tax = Decimal("175000") * Decimal("0.125")
        assert tb.tax_amount == expected_tax.quantize(Decimal("0.01"))

    def test_execute_sale_ltcg_exemption_exhausted(self):
        tracker = LotTracker()
        lot = make_equity_lot("INFY.NS", days_held=400, qty=100, cost=1000, current=2000)
        tracker.add_lot(lot)

        realized = tracker.execute_sale(
            "test", "INFY.NS", Decimal("100"), Decimal("2000"),
            ytd_realized_ltcg=Decimal("150000"),
        )
        assert len(realized) == 1
        tb = realized[0].tax_breakdown
        assert tb.taxable_gain == Decimal("100000")
        expected_tax = Decimal("100000") * Decimal("0.125")
        assert tb.tax_amount == expected_tax.quantize(Decimal("0.01"))

    def test_execute_sale_stcg_unchanged(self):
        tracker = LotTracker()
        lot = make_equity_lot("TCS.NS", days_held=100, qty=100, cost=1000, current=1500)
        tracker.add_lot(lot)

        realized = tracker.execute_sale(
            "test", "TCS.NS", Decimal("100"), Decimal("1500"),
            ytd_realized_ltcg=Decimal("0"),
        )
        assert len(realized) == 1
        tb = realized[0].tax_breakdown
        assert tb.classification.value == "STCG"
        assert tb.taxable_gain == Decimal("50000")
        expected_tax = Decimal("50000") * Decimal("0.20")
        assert tb.tax_amount == expected_tax.quantize(Decimal("0.01"))

    def test_execute_sale_crypto_unchanged(self):
        tracker = LotTracker()
        lot = make_crypto_lot("BTC", qty="1", cost=2000000, current=3000000)
        tracker.add_lot(lot)

        realized = tracker.execute_sale(
            "test", "BTC", Decimal("1"), Decimal("3000000"),
            ytd_realized_ltcg=Decimal("0"),
        )
        assert len(realized) == 1
        tb = realized[0].tax_breakdown
        assert tb.classification.value == "CRYPTO"
        assert tb.taxable_gain == Decimal("1000000")
        expected_tax = Decimal("1000000") * Decimal("0.30")
        assert tb.tax_amount == expected_tax.quantize(Decimal("0.01"))


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
            for gain_lot in lt_opp.offsettable_gain_lots:
                assert gain_lot.is_long_term, "LTCG loss should only offset LTCG gains"


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


class TestOptimalSellAndCalendarFixes:

    def test_optimal_sell_recommendation_respects_ytd_realized_ltcg(self):
        engine = EquityTaxEngine()
        lot = make_equity_lot(days_held=200, qty=100, cost=1000, current=2000)

        rec_fresh = engine.optimal_sell_recommendation(lot, ytd_realized_ltcg=Decimal("0"))
        assert rec_fresh["remaining_exemption_inr"] == 125000.0
        assert rec_fresh["ltcg_tax_if_waited_inr"] == 0.0

        rec_part = engine.optimal_sell_recommendation(lot, ytd_realized_ltcg=Decimal("100000"))
        assert rec_part["remaining_exemption_inr"] == 25000.0
        assert rec_part["ltcg_tax_if_waited_inr"] == 9375.0

        rec_used = engine.optimal_sell_recommendation(lot, ytd_realized_ltcg=Decimal("150000"))
        assert rec_used["remaining_exemption_inr"] == 0.0
        assert rec_used["ltcg_tax_if_waited_inr"] == 12500.0

    def test_tax_calendar_ltcg_unlock_events_uses_equity_engine_and_ytd_ltcg(self):
        from core.tax.tax_calendar import TaxCalendar
        calendar = TaxCalendar()
        lot = make_equity_lot(days_held=300, qty=100, cost=1000, current=2000)

        events_fresh = calendar.ltcg_unlock_events([lot], look_ahead_days=90, ytd_realized_ltcg=Decimal("0"))
        assert len(events_fresh) == 1
        assert events_fresh[0]["ltcg_tax_after_unlock_inr"] == 0.0

        events_exhausted = calendar.ltcg_unlock_events([lot], look_ahead_days=90, ytd_realized_ltcg=Decimal("150000"))
        assert len(events_exhausted) == 1
        assert events_exhausted[0]["ltcg_tax_after_unlock_inr"] == 12500.0


class TestDebtMFTaxCutoffDate:

    def test_post_april_2023_debt_mf_always_slab_rate(self):
        from core.tax.mf_tax import MFTaxEngine
        engine = MFTaxEngine()
        lot = AssetLot(
            lot_id="DEBT-POST-2023",
            symbol="HDFC_DEBT",
            asset_class=AssetClass.MUTUAL_FUND,
            platform=Platform.ZERODHA,
            member_id="test",
            quantity=Decimal("100"),
            acquisition_date=date(2023, 5, 1),
            cost_basis_per_unit=Decimal("100"),
            current_price=Decimal("150"),
        )
        res = engine.compute_tax(lot, mf_type="DEBT", tax_slab_rate=Decimal("0.30"))
        assert res["treatment"] == "SLAB_RATE"
        assert res["tax_rate"] == 0.30
        assert "Apr 1 2023" in res["note"]

    def test_pre_april_2023_debt_mf_qualifies_for_ltcg_if_held_3_years(self):
        from core.tax.mf_tax import MFTaxEngine
        engine = MFTaxEngine()
        lot = AssetLot(
            lot_id="DEBT-PRE-2023-LT",
            symbol="ICICI_DEBT",
            asset_class=AssetClass.MUTUAL_FUND,
            platform=Platform.ZERODHA,
            member_id="test",
            quantity=Decimal("100"),
            acquisition_date=date(2020, 1, 1),
            cost_basis_per_unit=Decimal("100"),
            current_price=Decimal("150"),
        )
        res = engine.compute_tax(lot, mf_type="DEBT", tax_slab_rate=Decimal("0.30"))
        assert res["treatment"] == "LTCG"
        assert res["tax_rate"] == 0.20


class TestInfrastructureFeatures:

    def test_fx_service_fallback(self):
        svc = FXRateService(default_rate=83.5)
        rate = svc.get_usd_inr_rate()
        assert rate > Decimal("0")

    def test_state_manager_thread_safety(self):
        sm = PortfolioStateManager(settings=Settings())
        fam1 = sm.get_family("session_1")
        fam2 = sm.get_family("session_2")
        assert fam1 is not fam2
        assert len(fam1.members) > 0
        assert len(fam2.members) > 0

    def test_session_id_resolver(self):
        assert get_session_id(x_session_id="user_123") == "user_123"
        assert get_session_id(x_family_id="fam_456") == "fam_456"
        assert get_session_id(session_id="query_789") == "query_789"
        assert get_session_id() == "default"

    def test_manual_us_equity_uses_live_fx(self):
        importer = ManualAssetImporter()
        lot = importer.import_us_equity({
            "symbol": "AAPL",
            "quantity": 10,
            "acquisition_date": "2023-01-01",
            "cost_basis_usd": 150.0,
            "current_price_usd": 180.0,
        }, member_id="test")
        rate = get_fx_service().get_usd_inr_rate()
        expected_cost = Decimal("150.0") * rate
        assert lot.cost_basis_per_unit == expected_cost

    def test_binance_uses_live_fx(self):
        agg = BinanceAggregator(api_key="mock", api_secret="mock")
        assert agg.usd_inr_rate == get_fx_service().get_usd_inr_rate()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
