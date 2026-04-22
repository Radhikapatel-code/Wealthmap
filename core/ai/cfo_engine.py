"""
Gemini CFO Engine — manages Google Gemini API calls with structured context.
Gemini reasons over pre-computed structured data, never raw numbers.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from typing import Optional, AsyncGenerator

import google.generativeai as genai

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
MODEL = "gemini-2.0-flash"
MAX_TOKENS = 2048


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    if path.exists():
        return path.read_text()
    return ""


class CFOEngine:
    """
    Wrapper around Google Gemini API for portfolio intelligence.
    All interactions are structured: system prompt + JSON context + user query.
    """

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            logger.warning("No Gemini API key provided. AI features will be unavailable.")
        genai.configure(api_key=key)
        self.model = genai.GenerativeModel(MODEL)

    # ── Synchronous Calls ────────────────────────────────────────────────────

    def portfolio_health(self, context: dict) -> str:
        """Full portfolio health assessment."""
        system = _load_prompt("portfolio_health") or self._default_system_prompt()
        user_msg = (
            "Provide a comprehensive CFO-grade portfolio health assessment based on the following data:\n\n"
            f"```json\n{json.dumps(context, indent=2)}\n```\n\n"
            "Structure your response with:\n"
            "1. Executive Summary (2-3 sentences)\n"
            "2. Concentration Risk Analysis\n"
            "3. Tax Efficiency Assessment\n"
            "4. Actionable Recommendations (numbered, specific)\n"
            "5. Watch Items (upcoming events to monitor)"
        )
        return self._call(system, user_msg)

    def tax_advice(self, context: dict) -> str:
        """Tax optimization advice."""
        system = _load_prompt("tax_advice") or self._default_system_prompt()
        user_msg = (
            "Provide specific, actionable Indian tax optimization advice based on this portfolio data:\n\n"
            f"```json\n{json.dumps(context, indent=2)}\n```\n\n"
            "Focus on:\n"
            "- Immediate actions (next 30 days)\n"
            "- LTCG unlock opportunities\n"
            "- Tax loss harvesting\n"
            "- Advance tax planning\n"
            "Always cite specific INR amounts and dates."
        )
        return self._call(system, user_msg)

    def scenario_analysis(self, context: dict, query: str) -> str:
        """Free-form scenario analysis."""
        system = _load_prompt("scenario_analysis") or self._default_system_prompt()
        user_msg = (
            f"User Query: {query}\n\n"
            "Portfolio Context:\n"
            f"```json\n{json.dumps(context, indent=2)}\n```\n\n"
            "Provide specific, quantified analysis. Always show INR impact of recommendations."
        )
        return self._call(system, user_msg)

    def daily_digest(self, context: dict) -> str:
        """Concise daily portfolio digest."""
        system = _load_prompt("daily_digest") or self._default_system_prompt()
        user_msg = (
            "Generate a concise daily portfolio digest (under 300 words) for this family:\n\n"
            f"```json\n{json.dumps(context, indent=2)}\n```\n\n"
            "Format: net worth snapshot → biggest movers → tax alerts → 1 action item."
        )
        return self._call(system, user_msg)

    def chat(self, context: dict, user_message: str, conversation_history: list[dict]) -> str:
        """Multi-turn CFO chat with persistent context."""
        system = self._default_system_prompt() + (
            "\n\nCurrent portfolio context:\n"
            f"```json\n{json.dumps(context, indent=2)}\n```"
        )

        messages = conversation_history + [{"role": "user", "content": user_message}]
        return self._call(system, messages=messages)

    # ── Streaming ────────────────────────────────────────────────────────────

    def stream_response(self, system: str, user_msg: str):
        """Yield text chunks from streaming API call."""
        full_message = f"{system}\n\nUser: {user_msg}"
        response = self.model.generate_content(full_message, stream=True)
        for chunk in response:
            if chunk.text:
                yield chunk.text

    # ── Internal ─────────────────────────────────────────────────────────────

    def _call(
        self,
        system: str,
        user_msg: Optional[str] = None,
        messages: Optional[list[dict]] = None,
    ) -> str:
        try:
            if messages is None and user_msg:
                full_message = f"{system}\n\nUser: {user_msg}"
            else:
                # For multi-turn conversations, reconstruct from history
                message_text = "\n".join(
                    [f"{msg['role'].capitalize()}: {msg['content']}" for msg in (messages or [])]
                )
                full_message = f"{system}\n\n{message_text}"

            response = self.model.generate_content(full_message)
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return f"Error communicating with Gemini API: {str(e)}"

    @staticmethod
    def _default_system_prompt() -> str:
        return """You are WealthMap CFO — an AI portfolio intelligence engine powered by Google Gemini for Indian High-Net-Worth families.

Your role:
- Provide CFO-grade reasoning over pre-computed, structured portfolio data
- Apply deep knowledge of Indian tax law (IT Act, Section 115BBH, LTCG/STCG rules)
- Give specific, actionable advice with exact INR amounts and dates
- Always distinguish between STCG (20%) and LTCG (12.5% above ₹1.25L exemption)
- Flag crypto tax implications clearly (30% flat, no offset under 115BBH)
- Consider family as a unit but remember tax slabs and LTCG exemptions are per individual

Rules:
- Never compute tax yourself — use the numbers already computed and provided in context
- Always add: "Verify with a qualified CA before acting"
- For scenario questions, show the math step by step
- Be direct and concise. Use ₹ and commas for Indian numbering (₹1,25,000 not ₹125000)
- Indian FY runs April 1 – March 31
- Do not recommend specific stocks to buy/sell for investment purposes (only for tax reasons)

You are NOT:
- A SEBI-registered advisor
- A tax consultant
- A replacement for professional advice"""
