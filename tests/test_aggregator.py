from __future__ import annotations

from core.aggregator.manual_import import load_manual_assets_from_payload


def test_manual_import_normalizes_assets():
    payload = {
        "assets": [
            {
                "asset_id": "gold-1",
                "symbol": "PHYSICAL_GOLD",
                "asset_class": "GOLD",
                "platform": "manual",
                "member_id": "mother",
                "quantity": 10,
                "acquisition_date": "2021-01-01",
                "cost_basis_per_unit": 5000,
                "current_price": 6500,
                "metadata": {"unit": "gram"},
            }
        ]
    }

    assets = load_manual_assets_from_payload(payload)

    assert len(assets) == 1
    assert assets[0].asset_class.value == "GOLD"
    assert assets[0].metadata["unit"] == "gram"
