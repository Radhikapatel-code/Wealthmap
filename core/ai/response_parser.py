"""
Response Parser — parses and structures Claude CFO output.
Extracts key insights, action items, and alerts from free-form Claude text.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedCFOResponse:
    raw_text: str
    summary: str = ""
    action_items: list[str] = field(default_factory=list)
    tax_alerts: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    disclaimer_present: bool = False


class ResponseParser:
    """
    Parses Claude CFO responses into structured components for dashboard display.
    """

    def parse(self, raw: str) -> ParsedCFOResponse:
        result = ParsedCFOResponse(raw_text=raw)

        # Check disclaimer
        result.disclaimer_present = any(kw in raw.lower() for kw in ["advisory", "consult a ca", "verify with"])

        # Extract numbered action items (lines starting with 1. 2. 3.)
        action_pattern = re.compile(r"^\s*\d+\.\s+(.+)$", re.MULTILINE)
        result.action_items = action_pattern.findall(raw)[:8]

        # Extract bullet points
        bullet_pattern = re.compile(r"^[\-•*]\s+(.+)$", re.MULTILINE)
        bullets = bullet_pattern.findall(raw)

        # Tax-related bullets
        tax_keywords = ["ltcg", "stcg", "tax", "tds", "harvest", "advance tax", "exemption"]
        result.tax_alerts = [
            b for b in bullets
            if any(kw in b.lower() for kw in tax_keywords)
        ][:5]

        # Risk-related bullets
        risk_keywords = ["risk", "concentration", "overweight", "high", "alert", "warning"]
        result.risk_flags = [
            b for b in bullets
            if any(kw in b.lower() for kw in risk_keywords)
        ][:5]

        # Summary: first non-empty paragraph
        paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]
        if paragraphs:
            result.summary = paragraphs[0][:400]

        return result

    def extract_inr_amounts(self, text: str) -> list[dict]:
        """Extract all ₹ amounts mentioned in a response."""
        pattern = re.compile(r"₹\s*([\d,]+(?:\.\d{1,2})?)\s*(L|Cr|lakh|crore|K)?", re.IGNORECASE)
        amounts = []
        for match in pattern.finditer(text):
            raw_amount = match.group(1).replace(",", "")
            unit = (match.group(2) or "").upper()
            try:
                value = float(raw_amount)
                if unit in ("L", "LAKH"):
                    value *= 100000
                elif unit in ("CR", "CRORE"):
                    value *= 10000000
                elif unit == "K":
                    value *= 1000
                amounts.append({
                    "raw": match.group(0),
                    "value_inr": value,
                    "context": text[max(0, match.start()-40):match.end()+40],
                })
            except ValueError:
                continue
        return amounts

    def to_telegram_markdown(self, parsed: ParsedCFOResponse) -> str:
        """Format parsed response for Telegram digest."""
        lines = ["*WealthMap CFO Daily Digest*", ""]

        if parsed.summary:
            lines.append(parsed.summary[:300])
            lines.append("")

        if parsed.tax_alerts:
            lines.append("⚠️ *Tax Alerts:*")
            for alert in parsed.tax_alerts[:3]:
                lines.append(f"• {alert}")
            lines.append("")

        if parsed.action_items:
            lines.append("✅ *Action Items:*")
            for i, item in enumerate(parsed.action_items[:3], 1):
                lines.append(f"{i}. {item}")
            lines.append("")

        if not parsed.disclaimer_present:
            lines.append("_Advisory only. Verify with your CA._")

        return "\n".join(lines)
