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


def test_zerodha_aggregator_resolves_trade_acquisition_date(monkeypatch):
    from datetime import date
    from core.aggregator.zerodha import ZerodhaAggregator

    aggregator = ZerodhaAggregator(api_key="mock_key", access_token="mock_token")

    class MockKite:
        def holdings(self):
            return [{
                "tradingsymbol": "INFY",
                "quantity": 100,
                "average_price": 1400.0,
                "last_price": 1600.0,
                "exchange": "NSE",
            }]

        def trades(self):
            return [{
                "tradingsymbol": "INFY",
                "fill_timestamp": "2022-03-15T10:30:00Z",
            }]

    aggregator._kite = MockKite()
    lots = aggregator.get_holdings("father")

    assert len(lots) == 1
    assert lots[0].symbol == "INFY.NS"
    assert lots[0].acquisition_date == date(2022, 3, 15)


def test_binance_aggregator_computes_cost_basis_and_trade_date(monkeypatch):
    from datetime import date
    from decimal import Decimal
    from core.aggregator.binance import BinanceAggregator

    aggregator = BinanceAggregator(api_key="mock_key", api_secret="mock_secret")

    class MockBinanceClient:
        def get_account(self):
            return {"balances": [{"asset": "BTC", "free": "0.5", "locked": "0.0"}]}

        def get_symbol_ticker(self, symbol):
            return {"symbol": "BTCUSDT", "price": "60000.00"}

        def get_my_trades(self, symbol):
            return [
                {
                    "qty": "0.5",
                    "price": "40000.00",
                    "time": 1640995200000,  # 2022-01-01 00:00:00 UTC
                    "isBuyer": True,
                }
            ]

    aggregator._client = MockBinanceClient()
    lots = aggregator.get_holdings("father")

    assert len(lots) == 1
    assert lots[0].symbol == "BTC"
    # 40,000 USD * 83.50 = 3,340,000 INR
    assert lots[0].cost_basis_per_unit == Decimal("3340000.00")
    assert lots[0].acquisition_date == date(2022, 1, 1)

