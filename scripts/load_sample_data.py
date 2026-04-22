"""
Load sample portfolio data for demo/development.
Run: python scripts/load_sample_data.py
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, ".")

from core.models import AssetLot, AssetClass, Platform
from core.tax.lot_tracker import LotTracker
from core.family.family_unit import FamilyUnit, FamilyMember
from core.aggregator.normalizer import PortfolioNormalizer
from config.settings import get_settings
from datetime import datetime
from decimal import Decimal


def load_sample():
    sample_path = Path("data/sample/sample_portfolio.json")
    if not sample_path.exists():
        print("❌ Sample file not found at data/sample/sample_portfolio.json")
        return

    with open(sample_path) as f:
        data = json.load(f)

    settings = get_settings()
    normalizer = PortfolioNormalizer(settings)

    print(f"📂 Loading sample portfolio: {data['family_name']}")
    print("=" * 50)

    family = FamilyUnit(family_name=data["family_name"])
    tracker = LotTracker()

    for member_data in data["members"]:
        mid = member_data["member_id"]
        snapshot = normalizer.build_demo_snapshot(mid)
        member = FamilyMember(
            member_id=mid,
            name=member_data["name"],
            relationship=member_data["relationship"],
            tax_slab_rate=Decimal(str(member_data.get("tax_slab_rate", 0.30))),
            portfolio=snapshot,
            ytd_realized_ltcg=Decimal(str(member_data.get("ytd_realized_ltcg", 0))),
            ytd_realized_stcg=Decimal(str(member_data.get("ytd_realized_stcg", 0))),
            ytd_realized_crypto=Decimal(str(member_data.get("ytd_realized_crypto", 0))),
            ytd_tax_paid=Decimal(str(member_data.get("ytd_tax_paid", 0))),
        )
        family.add_member(member)
        for lot in snapshot.lots:
            tracker.add_lot(lot)

        print(f"  ✅ {member.name} ({mid}) — ₹{float(member.net_worth/100000):.1f}L net worth")

    print("=" * 50)
    print(f"  💰 Total Family Net Worth: ₹{float(family.total_net_worth/10000000):.2f}Cr")
    print(f"  📊 Asset classes: {list(family.asset_class_breakdown().keys())}")
    print(f"  👨‍👩‍👦 Members: {len(family.members)}")
    print(f"  📦 Total lots: {len(tracker.all_lots())}")
    print()

    tax = family.ytd_tax_summary()
    print("📋 YTD Tax Summary:")
    for m in tax.get("members", []):
        print(f"  {m['name']}: Est. tax ₹{m['estimated_tax_inr']:,.0f} | "
              f"LTCG exemption left ₹{m['ltcg_exemption_remaining_inr']:,.0f}")

    print()
    print("✅ Sample data loaded successfully.")
    print("   → Run dashboard: streamlit run dashboard/app.py")
    print("   → Run API:       uvicorn api.main:app --reload --port 8000")


if __name__ == "__main__":
    load_sample()
