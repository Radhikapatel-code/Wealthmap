from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from core.models import AssetClass, AssetLot
from core.tax.tlh_scanner import TaxLossHarvestScanner


def test_tlh_scanner_finds_equity_loss_against_gain_pool():
    scanner = TaxLossHarvestScanner()
    gain_lot = AssetLot(
        asset_id="gain-1",
        symbol="TCS.NS",
        asset_class=AssetClass.EQUITY,
        platform="zerodha",
        member_id="father",
        quantity=Decimal("10"),
        acquisition_date=date.today() - timedelta(days=400),
        cost_basis_per_unit=Decimal("100"),
        current_price=Decimal("160"),
    )
    loss_lot = AssetLot(
        asset_id="loss-1",
        symbol="PAYTM.NS",
        asset_class=AssetClass.EQUITY,
        platform="zerodha",
        member_id="child",
        quantity=Decimal("10"),
        acquisition_date=date.today() - timedelta(days=100),
        cost_basis_per_unit=Decimal("100"),
        current_price=Decimal("70"),
    )

    results = scanner.scan([gain_lot, loss_lot])

    assert len(results) == 1
    assert results[0]["symbol"] == "PAYTM.NS"
    assert results[0]["estimated_post_tax_benefit_inr"] > 0


def test_tlh_scanner_uses_ytd_realized_gains():
    scanner = TaxLossHarvestScanner()
    loss_lot = AssetLot(
        asset_id="loss-stcg",
        symbol="ZOMATO.NS",
        asset_class=AssetClass.EQUITY,
        platform="zerodha",
        member_id="father",
        quantity=Decimal("100"),
        acquisition_date=date.today() - timedelta(days=50),
        cost_basis_per_unit=Decimal("200"),
        current_price=Decimal("150"),  # unrealized loss = 5,000 STCG loss
    )

    # 1) Scan without realized gains or unrealized gains -> 0 tax saving
    res_no_gains = scanner.scan([loss_lot], ytd_realized_stcg=Decimal("0"))
    assert len(res_no_gains) == 1
    assert res_no_gains[0].net_tax_saving == Decimal("0")

    # 2) Scan with YTD realized STCG = ₹10,000 -> 5,000 STCG loss offsets ₹5,000 realized STCG @ 20% = ₹1,000 saving
    res_stcg = scanner.scan([loss_lot], ytd_realized_stcg=Decimal("10000"))
    assert len(res_stcg) == 1
    assert res_stcg[0].net_tax_saving == Decimal("1000.00")
    assert any("YTD realized STCG" in note for note in res_stcg[0].risk_notes)

