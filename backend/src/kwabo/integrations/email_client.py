"""Email client with a Protocol interface + FileDrop local implementation."""
from __future__ import annotations

import email
import email.policy
import hashlib
import io
import shutil
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


class EmailClient(Protocol):
    def list_new(self) -> list[RawEmail]: ...
    def mark_seen(self, email_id: str) -> None: ...


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
                    plain.append(part.get_content())
                except Exception:  # noqa: BLE001
                    payload = part.get_payload(decode=True)
                    if payload:
                        plain.append(payload.decode("utf-8", errors="replace"))
            elif ctype == "text/html":
                try:
                    html.append(part.get_content())
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
        body = msg.get_content()
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
    )


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
