from __future__ import annotations

from core.models import AssetClass
from core.tax.fd_tax import FixedDepositTaxEngine


class TDSTracker:
    def __init__(self) -> None:
        self.fd_engine = FixedDepositTaxEngine()

    def fd_threshold_alerts(self, assets: list) -> list[dict]:
        fd_assets = [asset for asset in assets if asset.asset_class == AssetClass.FD]
        return self.fd_engine.threshold_alerts(fd_assets)
