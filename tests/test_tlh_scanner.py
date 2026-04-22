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
