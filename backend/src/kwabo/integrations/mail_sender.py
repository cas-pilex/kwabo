"""Mail sender: SMTP / Microsoft Graph / log-only.

Protocol-based so the graph node doesn't care about the transport.
Config: MAIL_MODE=log|smtp|graph (default 'log').
"""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path
from typing import Protocol

import httpx

from kwabo.config import settings
from kwabo.utils.logging import log

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "ontvangstbevestiging.txt"


class MailSender(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class LogMailSender:
    async def send(self, to: str, subject: str, body: str) -> None:
        log.info("mail_sent_log", to=to, subject=subject, body_len=len(body))


class SmtpMailSender:
    def __init__(self) -> None:
        self.host = os.getenv("SMTP_HOST", "localhost")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("SMTP_USER", "")
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.from_addr = os.getenv("SMTP_FROM", "noreply@kwabo.nl")
        self.use_tls = os.getenv("SMTP_TLS", "true").lower() != "false"

    async def send(self, to: str, subject: str, body: str) -> None:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = to
        with smtplib.SMTP(self.host, self.port) as server:
            if self.use_tls:
                server.starttls()
            if self.user:
                server.login(self.user, self.password)
            server.send_message(msg)
        log.info("mail_sent_smtp", to=to, subject=subject)


class GraphMailSender:
    def __init__(self) -> None:
        self.tenant_id = os.getenv("GRAPH_TENANT_ID", "")
        self.client_id = os.getenv("GRAPH_CLIENT_ID", "")
        self.client_secret = os.getenv("GRAPH_CLIENT_SECRET", "")
        self.from_user = os.getenv("GRAPH_FROM_USER", "info@kwabo.nl")

    async def _get_token(self) -> str:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
            )
            r.raise_for_status()
            return r.json()["access_token"]

    async def send(self, to: str, subject: str, body: str) -> None:
        token = await self._get_token()
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            "saveToSentItems": True,
        }
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"https://graph.microsoft.com/v1.0/users/{self.from_user}/sendMail",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
        log.info("mail_sent_graph", to=to, subject=subject)


def get_mail_sender() -> MailSender:
    mode = getattr(settings, "mail_mode", None) or os.getenv("MAIL_MODE", "log")
    if mode == "smtp":
        return SmtpMailSender()
    if mode == "graph":
        return GraphMailSender()
    return LogMailSender()


def render_confirmation(
    klant_naam: str,
    bestelnr_klant: str | None,
    navision_order_nr: str | None,
    opmerkingen: str | None = None,
) -> tuple[str, str]:
    """Render the confirmation template. Returns (subject, body)."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8") if TEMPLATE_PATH.exists() else (
        "Geachte {klant_naam},\n\n"
        "Wij bevestigen de ontvangst van uw bestelling {bestelnr_klant}.\n"
        "Ons Navision-ordernummer: {navision_order_nr}.\n\n"
        "Met vriendelijke groet,\nKwabo Techniek B.V."
    )
    body = template.format(
        klant_naam=klant_naam or "klant",
        bestelnr_klant=bestelnr_klant or "(onbekend)",
        navision_order_nr=navision_order_nr or "(nog niet toegekend)",
        opmerkingen=opmerkingen or "",
    )
    subject = f"Ontvangstbevestiging bestelling {bestelnr_klant or navision_order_nr or ''} — Kwabo Techniek"
    return subject, body
