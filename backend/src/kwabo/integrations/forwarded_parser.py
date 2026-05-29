"""Detect forwarded emails and extract original sender.

Forwarded mails from Kwabo-medewerkers (Ivar, Mark, Nico, ... @ kwabo.nl) hide
the real customer. We scan the body for the standard forward headers and return
the original sender when detected.

Patterns we support:
  Outlook (NL):
    Van: Naam <adres@x.nl>
    Verzonden: donderdag 13 maart 2026 08:59
    Aan: ...
    Onderwerp: ...
  Outlook (EN):
    From: Name <addr@x.nl>
    Sent: ...
    To: ...
    Subject: ...
  Outlook (DE):
    Von: Name <addr@x.de>
    Gesendet: ...
    An: ...
    Betreff: ...
  Gmail / generic:
    ---------- Forwarded message ----------
    From: Name <addr@x.nl>
    Date: ...
    Subject: ...
    To: ...
  Inline quoted (less reliable):
    > From: Name <addr@x.nl>
"""
from __future__ import annotations

import re
from dataclasses import dataclass

KWABO_DOMAIN = "kwabo.nl"

EMAIL_RE = re.compile(r"[\w\.\-\+]+@[\w\.\-]+\.[A-Za-z]{2,}")

# "Van: Foo <a@b.nl>" / "From: Foo <a@b.nl>" / "Von: ..." (NL/EN/DE)
FROM_LINE = re.compile(
    r"^\s*>?\s*(?:Van|From|Von|De)\s*:\s*(?P<name>.*?)\s*(?:<(?P<email>[\w\.\-\+]+@[\w\.\-]+\.[A-Za-z]{2,})>|(?P<bare>[\w\.\-\+]+@[\w\.\-]+\.[A-Za-z]{2,}))",
    re.IGNORECASE | re.MULTILINE,
)

FORWARD_MARKERS = re.compile(
    r"(-{2,}\s*(?:Forwarded message|Doorgestuurd bericht|Weitergeleitete Nachricht|Oorspronkelijk bericht|Original Message)\s*-{2,}|Begin forwarded message:)",
    re.IGNORECASE,
)

SUBJECT_PREFIX = re.compile(r"^\s*(fw|fwd|wg|rv|re|aw|doorg\.)\s*:", re.IGNORECASE)


def _as_text(value) -> str:
    """Coerce naar str zodat een per ongeluk bytes-veld (zie email_client
    `_as_text` / de prod-crash 29-05-2026) nooit een str-regex laat crashen."""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value or "")


@dataclass
class ForwardInfo:
    is_forwarded: bool
    original_from_email: str | None = None
    original_from_name: str | None = None
    reason: str = ""


def detect_forward(
    email_from: str,
    email_subject: str,
    email_body: str,
    bijlagen_content: str = "",
) -> ForwardInfo:
    """Return (is_forwarded, original_from_email) if the mail is a forward.

    We consider a mail forwarded if:
      (a) the outer From is a Kwabo-medewerker (kwabo.nl domain) AND body contains a From-line,
      (b) OR the subject starts with Fw:/Fwd:/Wg:/Doorg.: AND body contains a From-line,
      (c) OR the body contains an explicit "Forwarded message" marker.
    """
    # Defensief: nooit een str-regex op bytes draaien (prod-crash 29-05-2026).
    email_from = _as_text(email_from)
    email_subject = _as_text(email_subject)
    email_body = _as_text(email_body)
    bijlagen_content = _as_text(bijlagen_content)

    outer_email_match = EMAIL_RE.search(email_from or "")
    outer_email = outer_email_match.group(0).lower() if outer_email_match else ""
    outer_is_kwabo = outer_email.endswith(f"@{KWABO_DOMAIN}")

    subject_is_fwd = bool(SUBJECT_PREFIX.match(email_subject or ""))
    # Skip plain "Re:" — that's a reply, not a forward
    if subject_is_fwd and re.match(r"^\s*re\s*:", (email_subject or ""), re.IGNORECASE):
        subject_is_fwd = False

    body_has_marker = bool(FORWARD_MARKERS.search(email_body or ""))

    # Find candidate From-lines in the email body (inner forward header)
    search_pool = (email_body or "") + "\n" + (bijlagen_content or "")
    candidates: list[tuple[str, str | None]] = []
    for m in FROM_LINE.finditer(search_pool):
        email_addr = (m.group("email") or m.group("bare") or "").lower()
        name = (m.group("name") or "").strip().strip('"').strip()
        if not email_addr:
            continue
        # Skip if it's just the Kwabo-medewerker themselves in the body (they were TO, not FROM)
        if email_addr.endswith(f"@{KWABO_DOMAIN}"):
            continue
        candidates.append((email_addr, name or None))

    if not candidates:
        if outer_is_kwabo:
            return ForwardInfo(is_forwarded=False, reason="Kwabo-afzender maar geen From-lijn in body")
        return ForwardInfo(is_forwarded=False, reason="Geen forward-signaal")

    original = candidates[0]

    if outer_is_kwabo or body_has_marker or subject_is_fwd:
        reasons = []
        if outer_is_kwabo:
            reasons.append("outer-from @kwabo.nl")
        if body_has_marker:
            reasons.append("forward-marker in body")
        if subject_is_fwd:
            reasons.append("subject-prefix")
        return ForwardInfo(
            is_forwarded=True,
            original_from_email=original[0],
            original_from_name=original[1],
            reason=", ".join(reasons),
        )

    return ForwardInfo(is_forwarded=False, reason="Geen trigger gevonden")
