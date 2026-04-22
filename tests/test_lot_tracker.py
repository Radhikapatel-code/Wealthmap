from __future__ import annotations

from datetime import date
from decimal import Decimal

from hypothesis import given, strategies as st

from core.models import AssetClass, AssetLot
from core.tax.lot_tracker import FIFOLotTracker


def make_lot(asset_id: str, quantity: str, acquired: str) -> AssetLot:
    return AssetLot(
        asset_id=asset_id,
        symbol="RELIANCE.NS",
        asset_class=AssetClass.EQUITY,
        platform="zerodha",
        member_id="father",
        quantity=Decimal(quantity),
        acquisition_date=date.fromisoformat(acquired),
        cost_basis_per_unit=Decimal("100"),
        current_price=Decimal("120"),
    )


def test_fifo_consumes_oldest_lots_first():
    tracker = FIFOLotTracker()
    lots = [
        make_lot("lot-2", "5", "2024-02-01"),
        make_lot("lot-1", "10", "2024-01-01"),
    ]

    sale_slices = tracker.build_sale_slices(lots, 12)

    assert [slice_.lot.asset_id for slice_ in sale_slices] == ["lot-1", "lot-2"]
    assert [slice_.quantity for slice_ in sale_slices] == [Decimal("10"), Decimal("2")]


@given(quantity=st.integers(min_value=1, max_value=20))
def test_fifo_slice_quantities_sum_to_requested_amount(quantity: int):
    tracker = FIFOLotTracker()
    lots = [
        make_lot("lot-1", "10", "2024-01-01"),
        make_lot("lot-2", "10", "2024-02-01"),
    ]

    sale_slices = tracker.build_sale_slices(lots, quantity)

    assert sum(slice_.quantity for slice_ in sale_slices) == Decimal(str(quantity))
