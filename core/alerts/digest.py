"""
Digest dispatcher — sends daily portfolio digest via Telegram or email.
"""
from __future__ import annotations
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class DigestDispatcher:
    """Sends formatted digests via Telegram bot or email."""

    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
    ):
        self.telegram_token = telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    def send_telegram(self, message: str, chat_id: Optional[str] = None) -> bool:
        """Send message via Telegram Bot API."""
        try:
            import requests
            token = self.telegram_token
            cid = chat_id or self.telegram_chat_id
            if not token or not cid:
                logger.warning("Telegram credentials not configured.")
                return False

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            resp = requests.post(url, json={
                "chat_id": cid,
                "text": message,
                "parse_mode": "Markdown",
            }, timeout=10)
            resp.raise_for_status()
            logger.info("Telegram digest sent successfully.")
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def send_email(
        self,
        subject: str,
        body: str,
        to_email: str,
        from_email: Optional[str] = None,
    ) -> bool:
        """Send digest via email using SMTP."""
        try:
            import smtplib
            from email.mime.text import MIMEText
            smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
            smtp_port = int(os.environ.get("SMTP_PORT", "587"))
            smtp_user = os.environ.get("SMTP_USER", "")
            smtp_pass = os.environ.get("SMTP_PASS", "")

            msg = MIMEText(body, "plain")
            msg["Subject"] = subject
            msg["From"] = from_email or smtp_user
            msg["To"] = to_email

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

            logger.info(f"Email digest sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False
