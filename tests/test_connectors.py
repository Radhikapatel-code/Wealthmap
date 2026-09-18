"""
Comprehensive tests for WealthMap connectors.
Tests authentication, normalization, deduplication, and error handling.
"""
from __future__ import annotations

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from core.connectors.providers.zerodha import ZerodhaConnector
from core.connectors.providers.binance import BinanceConnector
from core.connectors.providers.coindcx import CoinDCXConnector
from core.connectors.providers.upstox import UpstoxConnector
from core.connectors.providers.angel_one import AngelOneConnector
from core.connectors.providers.wazirx import WazirXConnector
from core.connectors.providers.alpaca import AlpacaConnector
from core.connectors.models import (
    CanonicalAccount,
    CanonicalAsset,
    CanonicalHolding,
    CanonicalTransaction,
    SyncStatus,
    AssetType,
    TransactionType,
)


class TestZerodhaConnector:
    """Test suite for Zerodha Kite Connect connector."""

    def test_initialization(self):
        """Test Zerodha connector initialization."""
        connector = ZerodhaConnector("test_key", "test_token", member_id="father")
        assert connector.provider_id == "zerodha"
        assert connector.member_id == "father"
        assert connector.api_key == "test_key"
        assert connector.access_token == "test_token"

    def test_authenticate_success(self):
        """Test successful authentication."""
        connector = ZerodhaConnector("test_key", "test_token", member_id="father")
        
        with patch.object(connector, '_kite') as mock_kite:
            mock_kite.profile.return_value = {"user_id": "TEST123", "user_name": "Test User"}
            assert connector.authenticate() is True
            assert connector.status == SyncStatus.CONNECTED
            assert connector._last_error is None

    def test_authenticate_missing_credentials(self):
        """Test authentication with missing credentials."""
        connector = ZerodhaConnector("", "", member_id="father")
        assert connector.authenticate() is False
        assert connector.status == SyncStatus.NOT_CONNECTED
        assert "Missing" in connector._last_error

    def test_authenticate_token_expired(self):
        """Test authentication with expired token."""
        connector = ZerodhaConnector("test_key", "test_token", member_id="father")
        
        with patch.object(connector, '_kite') as mock_kite:
            mock_kite.profile.side_effect = Exception("TokenException")
            assert connector.authenticate() is False
            assert connector.status == SyncStatus.AUTH_EXPIRED
            assert "expired" in connector._last_error.lower()

    def test_get_holdings_normalization(self):
        """Test that holdings are properly normalized to canonical format."""
        connector = ZerodhaConnector("test_key", "test_token", member_id="father")
        
        mock_holdings = [
            {
                "tradingsymbol": "RELIANCE",
                "isin": "INE002A01032",
                "exchange": "NSE",
                "quantity": 100,
                "average_price": 2340.00,
                "last_price": 2847.50,
                "instrument_token": "123456",
            }
        ]
        
        with patch.object(connector, '_kite') as mock_kite:
            mock_kite.holdings.return_value = mock_holdings
            mock_kite.trades.return_value = []
            
            holdings = connector.get_holdings("test_account")
            
            assert len(holdings) == 1
            assert holdings[0].asset.symbol == "RELIANCE.NS"
            assert holdings[0].asset.asset_type == AssetType.INDIAN_EQUITY
            assert holdings[0].asset.isin == "INE002A01032"
            assert holdings[0].quantity == Decimal("100")
            assert holdings[0].average_cost == Decimal("2340.00")
            assert holdings[0].currency == "INR"

    def test_get_transactions_incremental(self):
        """Test incremental transaction fetching with since parameter."""
        connector = ZerodhaConnector("test_key", "test_token", member_id="father")
        
        since_time = datetime.utcnow() - timedelta(days=1)
        old_trade = {
            "trade_id": "old_123",
            "tradingsymbol": "INFY",
            "transaction_type": "BUY",
            "quantity": 50,
            "average_price": 1420.00,
            "fill_timestamp": since_time - timedelta(days=2),
        }
        new_trade = {
            "trade_id": "new_456",
            "tradingsymbol": "INFY",
            "transaction_type": "BUY",
            "quantity": 25,
            "average_price": 1680.00,
            "fill_timestamp": since_time + timedelta(hours=1),
        }
        
        with patch.object(connector, '_kite') as mock_kite:
            mock_kite.trades.return_value = [old_trade, new_trade]
            
            transactions = connector.get_transactions("test_account", since=since_time)
            
            # Should only return transactions since the specified time
            assert len(transactions) == 1
            assert transactions[0].provider_transaction_id == "new_456"

    def test_health_check(self):
        """Test health check functionality."""
        connector = ZerodhaConnector("test_key", "test_token", member_id="father")
        
        with patch.object(connector, '_kite') as mock_kite:
            mock_kite.profile.return_value = {"user_id": "TEST123"}
            
            health = connector.health_check()
            
            assert health.is_healthy is True
            assert health.status == SyncStatus.CONNECTED
            assert health.latency_ms is not None


class TestBinanceConnector:
    """Test suite for Binance connector."""

    def test_initialization(self):
        """Test Binance connector initialization."""
        connector = BinanceConnector("test_key", "test_secret", member_id="father")
        assert connector.provider_id == "binance"
        assert connector.api_key == "test_key"
        assert connector.api_secret == "test_secret"

    def test_authenticate_success(self):
        """Test successful Binance authentication."""
        connector = BinanceConnector("test_key", "test_secret", member_id="father")
        
        with patch.object(connector, '_client') as mock_client:
            mock_client.get_account_status.return_value = {"status": "NORMAL"}
            assert connector.authenticate() is True
            assert connector.status == SyncStatus.CONNECTED

    def test_get_holdings_crypto_normalization(self):
        """Test crypto holdings normalization."""
        connector = BinanceConnector("test_key", "test_secret", member_id="father")
        
        mock_account = {
            "balances": [
                {"asset": "BTC", "free": "0.18", "locked": "0.00"},
                {"asset": "ETH", "free": "2.5", "locked": "0.00"},
            ]
        }
        
        with patch.object(connector, '_client') as mock_client:
            mock_client.get_account.return_value = mock_account
            mock_client.get_symbol_ticker.return_value = {"price": "95000.00"}
            mock_client.get_my_trades.return_value = []
            
            holdings = connector.get_holdings("test_account")
            
            assert len(holdings) == 2
            assert holdings[0].asset.symbol == "BTC"
            assert holdings[0].asset.asset_type == AssetType.CRYPTO
            assert holdings[0].quantity == Decimal("0.18")
            assert holdings[0].currency == "INR"

    def test_cost_basis_from_trade_history(self):
        """Test cost basis resolution from trade history."""
        connector = BinanceConnector("test_key", "test_secret", member_id="father")
        
        mock_account = {"balances": [{"asset": "BTC", "free": "0.18", "locked": "0.00"}]}
        mock_trades = [
            {
                "id": "12345",
                "isBuyer": True,
                "qty": "0.10",
                "price": "1800000",
                "time": 1728000000000,  # Oct 6, 2024
            }
        ]
        
        with patch.object(connector, '_client') as mock_client:
            mock_client.get_account.return_value = mock_account
            mock_client.get_symbol_ticker.return_value = {"price": "95000.00"}
            mock_client.get_my_trades.return_value = mock_trades
            
            holdings = connector.get_holdings("test_account")
            
            # Cost basis should be derived from trade history
            assert holdings[0].average_cost > 0
            assert holdings[0].acquisition_date == date(2024, 10, 6)


class TestUpstoxConnector:
    """Test suite for Upstox connector."""

    def test_initialization(self):
        """Test Upstox connector initialization."""
        connector = UpstoxConnector(
            "test_key", "test_secret", "http://localhost:8501", member_id="father"
        )
        assert connector.provider_id == "upstox"
        assert connector.redirect_uri == "http://localhost:8501"

    def test_oauth_authentication(self):
        """Test OAuth 2.0 authentication flow."""
        connector = UpstoxConnector(
            "test_key", "test_secret", "http://localhost:8501", 
            member_id="father", access_token="test_token"
        )
        
        with patch.object(connector, '_session') as mock_session:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": {"client_id": "UPSTOX123"}}
            mock_session.get.return_value = mock_response
            
            assert connector.authenticate() is True
            assert connector.status == SyncStatus.CONNECTED

    def test_get_holdings_oauth_token_required(self):
        """Test that holdings fetch requires OAuth token."""
        connector = UpstoxConnector(
            "test_key", "test_secret", "http://localhost:8501", member_id="father"
        )
        
        with pytest.raises(RuntimeError, match="access token"):
            connector.get_holdings("test_account")


class TestAngelOneConnector:
    """Test suite for Angel One connector."""

    def test_initialization(self):
        """Test Angel One connector initialization."""
        connector = AngelOneConnector(
            "test_key", "CLIENT123", "123456", member_id="mother"
        )
        assert connector.provider_id == "angel_one"
        assert connector.client_code == "CLIENT123"

    def test_totp_authentication(self):
        """Test TOTP-based authentication."""
        connector = AngelOneConnector(
            "test_key", "CLIENT123", "123456", 
            totp_secret="JBSWY3DPEHPK3PXP", member_id="mother"
        )
        
        with patch.object(connector, '_session') as mock_session:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": {"jwtToken": "test_jwt_token"}}
            mock_session.post.return_value = mock_response
            
            with patch.object(connector, '_generate_totp', return_value="123456"):
                assert connector.authenticate() is True
                assert connector.jwt_token == "test_jwt_token"

    def test_jwt_token_validation(self):
        """Test JWT token validation without re-authentication."""
        connector = AngelOneConnector(
            "test_key", "CLIENT123", "123456", 
            member_id="mother", jwt_token="test_jwt_token"
        )
        
        with patch.object(connector, '_session') as mock_session:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": {"clientcode": "CLIENT123"}}
            mock_session.get.return_value = mock_response
            
            assert connector.authenticate() is True
            assert connector.status == SyncStatus.CONNECTED


class TestWazirXConnector:
    """Test suite for WazirX connector."""

    def test_initialization(self):
        """Test WazirX connector initialization."""
        connector = WazirXConnector("test_key", "test_secret", member_id="son")
        assert connector.provider_id == "wazirx"
        assert connector.api_key == "test_key"

    def test_hmac_signature_generation(self):
        """Test HMAC-SHA256 signature generation."""
        connector = WazirXConnector("test_key", "test_secret", member_id="son")
        
        query_string = "timestamp=1234567890"
        signature = connector._generate_signature(query_string)
        
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 produces 64-character hex string

    def test_get_holdings_inr_pairs(self):
        """Test holdings fetch for INR trading pairs."""
        connector = WazirXConnector("test_key", "test_secret", member_id="son")
        
        mock_account = {"balances": [{"asset": "BTC", "free": "0.15", "locked": "0.00"}]}
        
        with patch.object(connector, '_session') as mock_session:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_account
            mock_session.get.return_value = mock_response
            
            # Mock INR ticker
            inr_ticker = Mock()
            inr_ticker.status_code = 200
            inr_ticker.json.return_value = {"price": "8500000.00"}
            
            with patch.object(connector, '_session') as mock_session_ticker:
                mock_session_ticker.get.return_value = inr_ticker
                
                holdings = connector.get_holdings("test_account")
                
                assert len(holdings) == 1
                assert holdings[0].asset.symbol == "BTC"
                assert holdings[0].asset.asset_type == AssetType.CRYPTO
                assert holdings[0].currency == "INR"


class TestConnectorNormalization:
    """Test suite for cross-connector normalization consistency."""

    def test_symbol_normalization_consistency(self):
        """Test that different connectors normalize symbols consistently."""
        # Test NSE symbol normalization
        nse_symbol = "RELIANCE"
        expected_normalized = "RELIANCE.NS"
        
        # Test with Zerodha
        zerodha_asset = CanonicalAsset(
            symbol=nse_symbol,
            name="Reliance Industries",
            asset_type=AssetType.INDIAN_EQUITY,
            currency="INR",
            exchange="NSE",
        )
        
        # Test with Angel One
        angel_asset = CanonicalAsset(
            symbol=nse_symbol,
            name="Reliance Industries",
            asset_type=AssetType.INDIAN_EQUITY,
            currency="INR",
            exchange="NSE",
        )
        
        # Both should normalize to same format
        assert zerodha_asset.symbol == expected_normalized

    def test_decimal_precision_consistency(self):
        """Test that monetary values use consistent decimal precision."""
        test_values = [
            Decimal("100.123456789"),
            Decimal("2340.50"),
            Decimal("8500000.99"),
        ]
        
        # All should be quantized to 2 decimal places
        quantized = [v.quantize(Decimal("0.01")) for v in test_values]
        
        assert all(v == quantized[i] for i, v in enumerate(test_values))


class TestSyncEngineIntegration:
    """Test suite for sync engine integration with connectors."""

    def test_connector_registration(self):
        """Test connector registration and discovery."""
        from core.connectors.sync_engine import SyncEngine
        
        engine = SyncEngine()
        mock_connector = Mock(spec=BaseConnector)
        mock_connector.provider_id = "test_provider"
        mock_connector.get_accounts.return_value = [
            CanonicalAccount(
                provider="test_provider",
                provider_account_id="test_account",
                family_member_id="father",
                account_type="TEST",
                currency="INR",
            )
        ]
        
        engine.register_connector("test_connector", mock_connector)
        
        accounts = engine.list_accounts()
        assert len(accounts) == 1
        assert accounts[0].provider == "test_provider"

    def test_incremental_sync(self):
        """Test incremental sync with since parameter."""
        from core.connectors.sync_engine import SyncEngine
        
        engine = SyncEngine()
        mock_connector = Mock(spec=BaseConnector)
        mock_connector.provider_id = "test_provider"
        
        # Mock account with last_synced_at
        account = CanonicalAccount(
            provider="test_provider",
            provider_account_id="test_account",
            family_member_id="father",
            account_type="TEST",
            currency="INR",
            last_synced_at=datetime.utcnow() - timedelta(hours=1),
        )
        mock_connector.get_accounts.return_value = [account]
        
        mock_connector.get_holdings.return_value = []
        mock_connector.get_transactions.return_value = []
        mock_connector.get_cash_balances.return_value = []
        
        engine.register_connector("test_connector", mock_connector)
        
        # Sync should use incremental timestamp
        result = engine.sync_connector("test_connector")
        
        # Verify transactions were called with since parameter
        mock_connector.get_transactions.assert_called_once()
        call_args = mock_connector.get_transactions.call_args
        assert call_args[1]["since"] is not None
        assert call_args[1]["since"] >= account.last_synced_at

    def test_force_full_sync(self):
        """Test force full sync bypassing incremental logic."""
        from core.connectors.sync_engine import SyncEngine
        
        engine = SyncEngine()
        mock_connector = Mock(spec=BaseConnector)
        mock_connector.provider_id = "test_provider"
        
        account = CanonicalAccount(
            provider="test_provider",
            provider_account_id="test_account",
            family_member_id="father",
            account_type="TEST",
            currency="INR",
            last_synced_at=datetime.utcnow() - timedelta(hours=1),
        )
        mock_connector.get_accounts.return_value = [account]
        mock_connector.get_holdings.return_value = []
        mock_connector.get_transactions.return_value = []
        mock_connector.get_cash_balances.return_value = []
        
        engine.register_connector("test_connector", mock_connector)
        
        # Force full sync
        result = engine.sync_connector("test_connector", force_full_sync=True)
        
        # Verify transactions were called without since parameter
        mock_connector.get_transactions.assert_called_once()
        call_args = mock_connector.get_transactions.call_args
        assert call_args[1]["since"] is None


class TestDeduplication:
    """Test suite for duplicate prevention across accounts."""

    def test_cross_account_deduplication(self):
        """Test deduplication of same asset across different accounts."""
        from core.connectors.sync_engine import SyncEngine
        
        engine = SyncEngine()
        
        # Create holdings for same asset in different accounts
        holding1 = CanonicalHolding(
            holding_id="hold1",
            account_id="account1",
            asset=CanonicalAsset(
                symbol="RELIANCE.NS",
                name="Reliance",
                asset_type=AssetType.INDIAN_EQUITY,
                currency="INR",
                isin="INE002A01032",
            ),
            quantity=Decimal("100"),
            average_cost=Decimal("2400.00"),
            cost_basis=Decimal("240000.00"),
            current_price=Decimal("2800.00"),
            market_value=Decimal("280000.00"),
            currency="INR",
        )
        
        holding2 = CanonicalHolding(
            holding_id="hold2",
            account_id="account2",
            asset=CanonicalAsset(
                symbol="RELIANCE.NS",
                name="Reliance",
                asset_type=AssetType.INDIAN_EQUITY,
                currency="INR",
                isin="INE002A01032",
            ),
            quantity=Decimal("50"),
            average_cost=Decimal("2200.00"),
            cost_basis=Decimal("110000.00"),
            current_price=Decimal("2800.00"),
            market_value=Decimal("140000.00"),
            currency="INR",
        )
        
        # Deduplicate
        deduped = engine.deduplicate_holdings([holding1, holding2])
        
        # Should merge by account, not across accounts
        assert len(deduped) == 2

    def test_same_account_deduplication(self):
        """Test deduplication of same asset within same account."""
        from core.connectors.sync_engine import SyncEngine
        
        engine = SyncEngine()
        
        # Create holdings for same asset in same account
        holding1 = CanonicalHolding(
            holding_id="hold1",
            account_id="account1",
            asset=CanonicalAsset(
                symbol="RELIANCE.NS",
                name="Reliance",
                asset_type=AssetType.INDIAN_EQUITY,
                currency="INR",
                isin="INE002A01032",
            ),
            quantity=Decimal("100"),
            average_cost=Decimal("2400.00"),
            cost_basis=Decimal("240000.00"),
            current_price=Decimal("2800.00"),
            market_value=Decimal("280000.00"),
            currency="INR",
        )
        
        holding2 = CanonicalHolding(
            holding_id="hold2",
            account_id="account1",
            asset=CanonicalAsset(
                symbol="RELIANCE.NS",
                name="Reliance",
                asset_type=AssetType.INDIAN_EQUITY,
                currency="INR",
                isin="INE002A01032",
            ),
            quantity=Decimal("50"),
            average_cost=Decimal("2200.00"),
            cost_basis=Decimal("110000.00"),
            current_price=Decimal("2800.00"),
            market_value=Decimal("140000.00"),
            currency="INR",
        )
        
        # Deduplicate
        deduped = engine.deduplicate_holdings([holding1, holding2])
        
        # Should merge within same account
        assert len(deduped) == 1
        assert deduped[0].quantity == Decimal("150")  # 100 + 50
        # Weighted average cost: (240000 + 110000) / 150 = 2333.33
        assert abs(deduped[0].average_cost - Decimal("2333.33")) < Decimal("0.01")


class TestTransferDetection:
    """Test suite for transfer detection to prevent false taxable events."""

    def test_internal_transfer_detection(self):
        """Test detection of internal transfers between accounts."""
        from core.connectors.sync_engine import SyncEngine
        
        engine = SyncEngine()
        
        # Create matching withdrawal and deposit
        withdrawal = CanonicalTransaction(
            transaction_id="tx1",
            account_id="account1",
            asset=CanonicalAsset(
                symbol="BTC",
                name="Bitcoin",
                asset_type=AssetType.CRYPTO,
                currency="INR",
            ),
            transaction_type=TransactionType.WITHDRAWAL,
            quantity=Decimal("0.5"),
            price=Decimal("4500000"),
            timestamp=datetime.utcnow() - timedelta(hours=1),
            currency="INR",
        )
        
        deposit = CanonicalTransaction(
            transaction_id="tx2",
            account_id="account2",
            asset=CanonicalAsset(
                symbol="BTC",
                name="Bitcoin",
                asset_type=AssetType.CRYPTO,
                currency="INR",
            ),
            transaction_type=TransactionType.DEPOSIT,
            quantity=Decimal("0.5"),
            price=Decimal("4500000"),
            timestamp=datetime.utcnow() - timedelta(minutes=30),
            currency="INR",
        )
        
        transactions = [withdrawal, deposit]
        detected = engine.detect_transfers(transactions)
        
        # Both should be marked as internal transfers
        assert all(tx.is_internal_transfer for tx in detected)
        assert "internal transfer" in withdrawal.notes.lower()
        assert "internal transfer" in deposit.notes.lower()

    def test_non_transfer_transactions(self):
        """Test that normal buy/sell transactions are not marked as transfers."""
        from core.connectors.sync_engine import SyncEngine
        
        engine = SyncEngine()
        
        buy = CanonicalTransaction(
            transaction_id="tx1",
            account_id="account1",
            asset=CanonicalAsset(
                symbol="RELIANCE.NS",
                name="Reliance",
                asset_type=AssetType.INDIAN_EQUITY,
                currency="INR",
            ),
            transaction_type=TransactionType.BUY,
            quantity=Decimal("100"),
            price=Decimal("2400"),
            timestamp=datetime.utcnow(),
            currency="INR",
        )
        
        sell = CanonicalTransaction(
            transaction_id="tx2",
            account_id="account1",
            asset=CanonicalAsset(
                symbol="INFY.NS",
                name="Infosys",
                asset_type=AssetType.INDIAN_EQUITY,
                currency="INR",
            ),
            transaction_type=TransactionType.SELL,
            quantity=Decimal("50"),
            price=Decimal("1600"),
            timestamp=datetime.utcnow(),
            currency="INR",
        )
        
        transactions = [buy, sell]
        detected = engine.detect_transfers(transactions)
        
        # Neither should be marked as internal transfer
        assert not any(tx.is_internal_transfer for tx in detected)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])