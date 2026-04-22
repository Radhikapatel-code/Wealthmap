"""
Tax Loss Harvesting Scanner.
Scans portfolio for unrealized losses and identifies offset opportunities
under Indian tax law.

Key rules:
- STCG losses can offset STCG + LTCG gains
- LTCG losses can ONLY offset LTCG gains
- Crypto losses (Section 115BBH): CANNOT offset any other gains — cannot carry forward
- FD interest: cannot be offset by capital losses
- Loss can be carried forward for 8 years (equity/MF) — must file ITR-3
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from core.models import AssetLot, AssetClass, TaxConstants, TLHOpportunity


class TLHScanner:

    def scan(
        self,
        lots: list[AssetLot],
        ytd_realized_ltcg: Decimal = Decimal("0"),
        ytd_realized_stcg: Decimal = Decimal("0"),
    ) -> list[TLHOpportunity]:
        """
        Full portfolio scan for tax-loss harvesting opportunities.
        Returns ranked list of opportunities by net tax saving.
        """
        loss_lots = [l for l in lots if l.unrealized_gain < 0 and l.asset_class != AssetClass.CRYPTO]
        gain_lots = [l for l in lots if l.unrealized_gain > 0 and l.asset_class != AssetClass.CRYPTO]

        opportunities = []

        for loss_lot in loss_lots:
            loss_amount = abs(loss_lot.unrealized_gain)
            offsettable_gains = []
            net_saving = Decimal("0")
            risk_notes = []

            # LTCG loss: can only offset LTCG
            if loss_lot.is_long_term:
                offsettable = [g for g in gain_lots if g.is_long_term]
                for gain_lot in offsettable:
                    offset = min(loss_amount, gain_lot.unrealized_gain)
                    saving = (offset * TaxConstants.LTCG_RATE).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    net_saving += saving
                    offsettable_gains.append(gain_lot)
                risk_notes.append("LTCG loss: can only offset LTCG gains.")
            else:
                # STCG loss: can offset both STCG and LTCG
                offsettable = gain_lots  # All gains
                for gain_lot in offsettable:
                    offset = min(loss_amount, gain_lot.unrealized_gain)
                    rate = TaxConstants.LTCG_RATE if gain_lot.is_long_term else TaxConstants.STCG_RATE
                    saving = (offset * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    net_saving += saving
                    offsettable_gains.append(gain_lot)

            # India has no formal wash-sale rule but flag re-buy risk
            risk_notes.append(
                "No formal wash-sale rule in India, but immediate re-purchase may attract GAAR scrutiny."
            )

            # Only surface meaningful opportunities
            if net_saving >= Decimal("500"):
                opportunities.append(TLHOpportunity(
                    loss_lot=loss_lot,
                    offsettable_gain_lots=offsettable_gains,
                    net_tax_saving=net_saving,
                    loss_amount=loss_amount,
                    risk_notes=risk_notes,
                ))

        # Sort by saving descending
        opportunities.sort(key=lambda o: o.net_tax_saving, reverse=True)
        return opportunities

    def crypto_loss_warning(self, lots: list[AssetLot]) -> list[dict]:
        """
        Crypto losses under 115BBH CANNOT offset any other income or gains.
        Flag them with clear warnings.
        """
        crypto_loss_lots = [
            l for l in lots
            if l.asset_class == AssetClass.CRYPTO and l.unrealized_gain < 0
        ]
        warnings = []
        for lot in crypto_loss_lots:
            warnings.append({
                "symbol": lot.symbol,
                "lot_id": lot.lot_id,
                "unrealized_loss_inr": float(abs(lot.unrealized_gain)),
                "warning": (
                    "Section 115BBH: Crypto losses CANNOT be set off against any other income or gains. "
                    "Cannot be carried forward. This loss is a permanent tax write-off."
                ),
            })
        return warnings

    def carry_forward_summary(
        self,
        realized_transactions: list,
        member_id: str | None = None,
    ) -> dict:
        """
        Summarize realized losses eligible for carry-forward (8 FYs).
        Equity/MF STCG and LTCG losses can be carried forward.
        """
        stcg_loss_cf = Decimal("0")
        ltcg_loss_cf = Decimal("0")

        for tx in realized_transactions:
            if member_id and tx.member_id != member_id:
                continue
            if tx.asset_class not in (AssetClass.EQUITY, AssetClass.MUTUAL_FUND):
                continue
            gain = tx.tax_breakdown.gross_gain
            if gain >= 0:
                continue

            from core.models import TaxClassification
            if tx.tax_breakdown.classification == TaxClassification.STCG:
                stcg_loss_cf += abs(gain)
            elif tx.tax_breakdown.classification == TaxClassification.LTCG:
                ltcg_loss_cf += abs(gain)

        return {
            "stcg_loss_carry_forward_inr": float(stcg_loss_cf),
            "ltcg_loss_carry_forward_inr": float(ltcg_loss_cf),
            "note": (
                "Carry-forward requires filing ITR before due date. "
                "Valid for 8 assessment years. STCG loss offsets STCG+LTCG; LTCG loss offsets LTCG only."
            ),
        }

    def generate_report(
        self,
        lots: list[AssetLot],
        ytd_realized_ltcg: Decimal = Decimal("0"),
        ytd_realized_stcg: Decimal = Decimal("0"),
    ) -> dict:
        """Full TLH report for dashboard display."""
        opportunities = self.scan(lots, ytd_realized_ltcg, ytd_realized_stcg)
        crypto_warnings = self.crypto_loss_warning(lots)

        total_saving = sum(o.net_tax_saving for o in opportunities)
        total_losses_available = sum(o.loss_amount for o in opportunities)

        return {
            "summary": {
                "opportunities_found": len(opportunities),
                "total_potential_saving_inr": float(total_saving),
                "total_harvestable_loss_inr": float(total_losses_available),
            },
            "opportunities": [o.to_dict() for o in opportunities],
            "crypto_loss_warnings": crypto_warnings,
            "important_notes": [
                "India has no formal wash-sale rule. Immediate re-purchase is legally permissible but may attract GAAR scrutiny.",
                "Tax loss harvesting only beneficial if you intend to rebalance. Do not sell quality assets solely for tax benefit.",
                "Losses must be filed in ITR to be eligible for carry-forward.",
                "Consult a CA before executing any TLH strategy.",
            ],
        }
