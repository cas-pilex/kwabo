"""Email client with a Protocol interface + FileDrop local implementation."""
from __future__ import annotations

import email
import email.policy
import email.utils
import hashlib
import io
import mimetypes
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from email.message import Message
from pathlib import Path
from typing import Protocol

from kwabo.config import settings
from kwabo.integrations.pdf_parser import extract_pdf_text


@dataclass
class Attachment:
    naam: str
    type: str  # pdf | excel | csv | image | other
    inhoud_tekst: str = ""
    raw: bytes | None = field(default=None, repr=False)


@dataclass
class RawEmail:
    email_id: str
    email_from: str
    email_subject: str
    email_date: str
    email_body: str
    bijlagen: list[Attachment]
    source_path: str | None = None
    # Raw RFC822 bytes — set by parse_eml_bytes so the intake layer can
    # persist the source under data/incoming_documents/{log_id}/ and pass
    # the path to push_navision as `state.incoming_document_path`. Without
    # this, Graph-ingested mails had no on-disk source-document at all.
    raw_eml: bytes | None = field(default=None, repr=False)


class EmailClient(Protocol):
    def list_new(self) -> list[RawEmail]: ...
    def mark_seen(self, email_id: str) -> None: ...


def _as_text(value) -> str:
    """Coerce wat `get_content()` ook teruggeeft naar str.

    `Message.get_content()` levert *bytes* bij een non-text content-type
    (kale PDF, application/octet-stream, …). Die bytes mogen nooit als
    `email_body` doorlekken: downstream regex-stappen (detect_forward,
    match_customer) draaien een str-pattern en crashen dan met
    "cannot use a string pattern on a bytes-like object" — de prod-crash
    van 29-05-2026 die élke mail in een poison-pill loop duwde."""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value or "")


def _plain_body(msg: Message) -> str:
    if msg.is_multipart():
        plain = []
        html = []
        for part in msg.walk():
            ctype = part.get_content_type()
            if part.get_filename():
                continue
            if ctype == "text/plain":
                try:
                    plain.append(_as_text(part.get_content()))
                except Exception:  # noqa: BLE001
                    payload = part.get_payload(decode=True)
                    if payload:
                        plain.append(payload.decode("utf-8", errors="replace"))
            elif ctype == "text/html":
                try:
                    html.append(_as_text(part.get_content()))
                except Exception:  # noqa: BLE001
                    payload = part.get_payload(decode=True)
                    if payload:
                        html.append(payload.decode("utf-8", errors="replace"))
        if plain:
            return "\n".join(plain)
        if html:
            return _strip_html(html[0])
        return ""
    try:
        body = _as_text(msg.get_content())
    except Exception:  # noqa: BLE001
        payload = msg.get_payload(decode=True)
        body = payload.decode("utf-8", errors="replace") if payload else ""
    return body if msg.get_content_type() != "text/html" else _strip_html(body)


def _strip_html(html: str) -> str:
    import re
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    import html as h
    return h.unescape(text).strip()


def parse_eml_file(path: str | Path) -> RawEmail:
    path = Path(path)
    raw = path.read_bytes()
    return parse_eml_bytes(raw, email_id=_hash(raw), source_path=str(path))


def parse_eml_bytes(raw: bytes, email_id: str | None = None, source_path: str | None = None) -> RawEmail:
    msg: Message = email.message_from_bytes(raw, policy=email.policy.default)
    bijlagen: list[Attachment] = []

    for part in msg.walk():
        filename = part.get_filename()
        if not filename:
            continue
        try:
            content = part.get_payload(decode=True)
        except Exception:  # noqa: BLE001
            content = None
        if not content:
            continue
        lower = filename.lower()
        if lower.endswith(".pdf"):
            try:
                tekst = extract_pdf_text(content)
            except Exception as e:  # noqa: BLE001
                tekst = f"[PDF parse error: {e}]"
            bijlagen.append(Attachment(naam=filename, type="pdf", inhoud_tekst=tekst, raw=content))
        elif lower.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for zname in zf.namelist():
                        if zname.lower().endswith(".pdf"):
                            pdf_bytes = zf.read(zname)
                            tekst = extract_pdf_text(pdf_bytes)
                            bijlagen.append(
                                Attachment(
                                    naam=f"{filename}:{zname}",
                                    type="pdf",
                                    inhoud_tekst=tekst,
                                    raw=pdf_bytes,
                                )
                            )
                        elif zname.lower().endswith((".xlsx", ".xls")):
                            bijlagen.append(
                                Attachment(
                                    naam=f"{filename}:{zname}",
                                    type="excel",
                                    inhoud_tekst=_extract_excel_text(zf.read(zname)),
                                )
                            )
                        elif zname.lower().endswith(".csv"):
                            bijlagen.append(
                                Attachment(
                                    naam=f"{filename}:{zname}",
                                    type="csv",
                                    inhoud_tekst=zf.read(zname).decode("utf-8", errors="replace"),
                                )
                            )
            except zipfile.BadZipFile:
                bijlagen.append(Attachment(naam=filename, type="other"))
        elif lower.endswith((".xlsx", ".xls")):
            bijlagen.append(
                Attachment(naam=filename, type="excel", inhoud_tekst=_extract_excel_text(content))
            )
        elif lower.endswith(".csv"):
            bijlagen.append(
                Attachment(
                    naam=filename,
                    type="csv",
                    inhoud_tekst=content.decode("utf-8", errors="replace"),
                )
            )
        elif lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp")):
            continue  # skip logos/signatures
        else:
            bijlagen.append(Attachment(naam=filename, type="other"))

    return RawEmail(
        email_id=email_id or _hash(raw),
        email_from=str(msg.get("from", "")),
        email_subject=str(msg.get("subject", "")),
        email_date=str(msg.get("date", "")),
        email_body=_plain_body(msg),
        bijlagen=bijlagen,
        source_path=source_path,
        raw_eml=raw,
    )


def _msg_to_mime_bytes(content: bytes) -> bytes:
    """Convert an Outlook `.msg` (OLE compound file) to RFC822 MIME bytes.

    Kwabo forwards orders as `.msg` files (both the source-document upload and
    the loose-mail upload button). The rest of the pipeline — extraction,
    storage, and the attachment-download MIME walker — speaks MIME, so we
    convert once here and reuse `parse_eml_bytes`. extract_msg is imported
    lazily so a missing dependency only breaks `.msg` handling, not app start.
    """
    import extract_msg  # lazy: optional dependency, .msg-only path

    with tempfile.NamedTemporaryFile(suffix=".msg", delete=False) as tf:
        tf.write(content)
        tmp = tf.name
    msg = None
    try:
        msg = extract_msg.openMsg(tmp)
        em = email.message.EmailMessage()
        if getattr(msg, "sender", None):
            em["From"] = str(msg.sender)
        if getattr(msg, "to", None):
            em["To"] = str(msg.to)
        em["Subject"] = str(getattr(msg, "subject", "") or "")
        try:
            d = getattr(msg, "date", None)
            if d:
                em["Date"] = d if isinstance(d, str) else email.utils.format_datetime(d)
        except Exception:  # noqa: BLE001
            pass
        em.set_content(str(getattr(msg, "body", "") or ""))

        for att in (getattr(msg, "attachments", None) or []):
            data = getattr(att, "data", None)
            # File attachments expose bytes; embedded .msg/other types don't.
            if not isinstance(data, (bytes, bytearray)):
                log_name = getattr(att, "longFilename", None) or getattr(att, "shortFilename", None)
                from kwabo.utils.logging import log as _log
                _log.warning("msg_attachment_skipped_non_bytes", filename=str(log_name))
                continue
            fname = (
                getattr(att, "longFilename", None)
                or getattr(att, "shortFilename", None)
                or "attachment"
            )
            ctype, _ = mimetypes.guess_type(fname)
            if ctype and "/" in ctype:
                maintype, subtype = ctype.split("/", 1)
            else:
                maintype, subtype = "application", "octet-stream"
            em.add_attachment(bytes(data), maintype=maintype, subtype=subtype, filename=fname)
        return em.as_bytes()
    finally:
        if msg is not None:
            try:
                msg.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            os.unlink(tmp)
        except OSError:
            pass


def parse_msg_bytes(content: bytes, email_id: str | None = None, source_path: str | None = None) -> RawEmail:
    """Parse an Outlook `.msg` by converting to MIME then reusing the .eml path.

    The returned RawEmail's `raw_eml` is the converted MIME — so persisting it
    and later re-extracting attachments works exactly like a native .eml."""
    mime = _msg_to_mime_bytes(content)
    return parse_eml_bytes(mime, email_id=email_id or _hash(content), source_path=source_path)


def _extract_excel_text(xlsx_bytes: bytes) -> str:
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
        out = []
        for sheet in wb.worksheets:
            out.append(f"=== Sheet: {sheet.title} ===")
            for row in sheet.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                if any(cells):
                    out.append(" | ".join(cells))
        return "\n".join(out)
    except Exception as e:  # noqa: BLE001
        return f"[excel parse error: {e}]"


def _hash(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


class FileDropEmailClient:
    """Reads .eml files from an inbox dir, moves them to processed after `mark_seen`."""

    def __init__(self, inbox: Path | None = None, processed: Path | None = None) -> None:
        self.inbox = inbox or settings.inbox_path
        self.processed = processed or settings.processed_path
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.processed.mkdir(parents=True, exist_ok=True)
        self._path_by_id: dict[str, Path] = {}

    def list_new(self) -> list[RawEmail]:
        out: list[RawEmail] = []
        for p in sorted(self.inbox.glob("*.eml")):
            em = parse_eml_file(p)
            self._path_by_id[em.email_id] = p
            out.append(em)
        return out

    def mark_seen(self, email_id: str) -> None:
        p = self._path_by_id.get(email_id)
        if p and p.exists():
            shutil.move(str(p), str(self.processed / p.name))


def get_email_client():
    """Factory: pick the email client implementation by `EMAIL_MODE`.

    Modes:
      * file_drop  — local .eml files in `inbox_path` (default; what the
                     test harness and dev loop use today).
      * graph      — Microsoft Graph mailbox; OAuth2 token stored by the
                     /api/mailbox/oauth/* flow.
      * imap       — not yet implemented; placeholder so the env var is
                     recognised and the operator gets a clear message.

    Mirrors `kwabo.integrations.navision_api.get_navision_client`. Switching
    to a real mailbox should be a config flip + credentials, not a code
    change."""
    mode = settings.email_mode
    if mode == "file_drop":
        return FileDropEmailClient()
    if mode == "graph":
        from kwabo.integrations.email_client_graph import GraphEmailClient
        return GraphEmailClient()
    if mode == "imap":
        raise NotImplementedError(
            "EMAIL_MODE=imap is not yet supported. Use file_drop or graph."
        )
    raise ValueError(f"Unknown EMAIL_MODE: {mode!r}")
