"""
CFO Context Builder — constructs structured, token-efficient context for Claude.
Claude never receives raw API data — only computed, structured facts.
"""
from __future__ import annotations
from decimal import Decimal
from typing import Optional

from core.family.family_unit import FamilyUnit, FamilyMember
from core.models import AssetClass, TaxConstants
from core.tax.equity_tax import EquityTaxEngine
from core.tax.crypto_tax import CryptoTaxEngine
from core.tax.tlh_scanner import TLHScanner
from core.tax.tax_calendar import TaxCalendar


class CFOContextBuilder:
    """
    Builds comprehensive, structured context payloads for Claude CFO reasoning.
    Keeps context token-efficient by using computed summaries, not raw data.
    """

    def __init__(self):
        self.equity_engine = EquityTaxEngine()
        self.crypto_engine = CryptoTaxEngine()
        self.tlh_scanner = TLHScanner()
        self.tax_calendar = TaxCalendar()

    def build_portfolio_context(self, family: FamilyUnit) -> dict:
        """Full family portfolio context for comprehensive Claude analysis."""
        all_lots = family.all_lots
        total_nw = family.total_net_worth

        # Asset breakdown
        asset_breakdown = {}
        for cls, data in family.asset_class_breakdown().items():
            asset_breakdown[cls] = data

        # Tax flags
        tax_flags = []

        # LTCG unlock events (next 30 days)
        unlock_events = self.tax_calendar.ltcg_unlock_events(all_lots, look_ahead_days=30)
        for event in unlock_events[:5]:  # Top 5 most urgent
            tax_flags.append({
                "type": "LTCG_UNLOCK_IMMINENT",
                "symbol": event["symbol"],
                "member_id": event["member_id"],
                "days_remaining": event["days_remaining"],
                "unlock_date": event["unlock_date"],
                "current_gain_inr": event["unrealized_gain_inr"],
                "tax_saving_if_waited_inr": event["potential_saving_inr"],
            })

        # TLH opportunities
        tlh_report = self.tlh_scanner.generate_report(all_lots)
        tlh_opps = tlh_report["opportunities"][:3]  # Top 3

        # Crypto unrealized gains
        crypto_lots = [l for l in all_lots if l.asset_class == AssetClass.CRYPTO]
        crypto_summary = self.crypto_engine.unrealized_gain_summary(crypto_lots)

        # Family tax summary
        family_tax = family.ytd_tax_summary()

        # Concentration risks
        risks = family.concentration_risks()

        # Per-member summaries
        member_contexts = []
        for member in family.members:
            if member.portfolio is None:
                continue
            member_lots = member.portfolio.lots
            equity_lots = [l for l in member_lots if l.asset_class in (AssetClass.EQUITY, AssetClass.MUTUAL_FUND)]
            equity_value = sum(l.current_value for l in equity_lots)
            equity_gain = sum(l.unrealized_gain for l in equity_lots)

            member_contexts.append({
                "member_id": member.member_id,
                "name": member.name,
                "relationship": member.relationship,
                "net_worth_inr": float(member.net_worth),
                "pct_of_family_wealth": float(
                    (member.net_worth / total_nw * 100).quantize(Decimal("0.01"))
                ) if total_nw else 0.0,
                "equity_value_inr": float(equity_value),
                "equity_unrealized_gain_inr": float(equity_gain),
                "ltcg_exemption_remaining_inr": float(member.ltcg_exemption_remaining),
                "ytd_realized_ltcg_inr": float(member.ytd_realized_ltcg),
                "ytd_realized_stcg_inr": float(member.ytd_realized_stcg),
                "ytd_realized_crypto_gain_inr": float(member.ytd_realized_crypto),
            })

        return {
            "family_name": family.family_name,
            "as_of_date": __import__("datetime").date.today().isoformat(),
            "summary": {
                "total_net_worth_inr": float(total_nw),
                "member_count": len(family.members),
                "asset_class_breakdown": asset_breakdown,
                "ytd_estimated_tax_inr": family_tax.get("estimated_total_tax_inr", 0),
            },
            "tax_flags": tax_flags,
            "tlh_opportunities": tlh_opps,
            "concentration_risks": risks[:5],
            "crypto_summary": {
                "total_crypto_value_inr": crypto_summary.get("total_crypto_value_inr"),
                "total_unrealized_gain_inr": crypto_summary.get("total_unrealized_gain_inr"),
                "tax_if_liquidated_inr": crypto_summary.get("tax_if_fully_liquidated", {}).get("total_tax_inr"),
            },
            "family_members": member_contexts,
            "important_constraints": [
                "LTCG exemption of ₹1.25L is per individual per FY — not shared across family.",
                "Crypto gains taxed at 30% flat — no exemption, no loss offset (Section 115BBH).",
                "Debt MF gains (post Apr 2023) taxed at slab rate — no LTCG benefit.",
                "All Claude output is advisory only — verify with a qualified CA.",
            ],
        }

    def build_tax_advice_context(
        self,
        family: FamilyUnit,
        specific_query: Optional[str] = None,
    ) -> dict:
        """Focused tax optimization context."""
        all_lots = family.all_lots

        # LTCG calendar (90 days)
        unlock_events = self.tax_calendar.ltcg_unlock_events(all_lots, look_ahead_days=90)

        # TLH full report
        ytd_ltcg = sum(m.ytd_realized_ltcg for m in family.members)
        ytd_stcg = sum(m.ytd_realized_stcg for m in family.members)
        tlh = self.tlh_scanner.generate_report(all_lots, ytd_ltcg, ytd_stcg)

        # Advance tax (estimate)
        family_tax = family.ytd_tax_summary()
        estimated_tax = Decimal(str(family_tax.get("estimated_total_tax_inr", 0)))
        advance_tax = self.tax_calendar.advance_tax_dates(estimated_tax)

        # Key dates
        key_dates = self.tax_calendar.key_dates_this_fy()
        upcoming_dates = [d for d in key_dates if d["status"] == "UPCOMING"][:4]

        return {
            "query": specific_query,
            "ltcg_unlock_calendar_90d": unlock_events,
            "tlh_report": {
                "opportunities_count": tlh["summary"]["opportunities_found"],
                "total_potential_saving_inr": tlh["summary"]["total_potential_saving_inr"],
                "top_opportunities": tlh["opportunities"][:5],
                "crypto_loss_warnings": tlh["crypto_loss_warnings"],
            },
            "advance_tax_schedule": advance_tax,
            "upcoming_key_dates": upcoming_dates,
            "family_tax_position": family_tax,
        }

    def build_scenario_context(
        self,
        family: FamilyUnit,
        query: str,
        additional_data: Optional[dict] = None,
    ) -> dict:
        """Scenario analysis context — includes full portfolio for free-form queries."""
        base = self.build_portfolio_context(family)
        base["scenario_query"] = query
        if additional_data:
            base["additional_context"] = additional_data
        return base

    def build_daily_digest_context(self, family: FamilyUnit) -> dict:
        """Compact context for daily digest generation."""
        all_lots = family.all_lots
        total_nw = family.total_net_worth

        # Biggest movers (by unrealized gain change — proxy: highest gain %)
        movers = sorted(
            [l for l in all_lots if l.current_price > 0],
            key=lambda l: abs(float(l.unrealized_gain_pct)),
            reverse=True
        )[:5]

        unlock_events = self.tax_calendar.ltcg_unlock_events(all_lots, look_ahead_days=7)
        tlh = self.tlh_scanner.generate_report(all_lots)

        return {
            "date": __import__("datetime").date.today().isoformat(),
            "family_name": family.family_name,
            "total_net_worth_inr": float(total_nw),
            "asset_class_summary": family.asset_class_breakdown(),
            "top_movers": [
                {
                    "symbol": l.symbol,
                    "unrealized_gain_pct": float(l.unrealized_gain_pct),
                    "unrealized_gain_inr": float(l.unrealized_gain),
                    "current_value_inr": float(l.current_value),
                }
                for l in movers
            ],
            "ltcg_unlocks_this_week": unlock_events,
            "tlh_opportunities_count": tlh["summary"]["opportunities_found"],
            "tlh_total_saving_inr": tlh["summary"]["total_potential_saving_inr"],
            "family_ytd_tax": family.ytd_tax_summary(),
        }
