"""Tekst-extractie voor klantkaart-documenten (PDF, DOCX, Excel, CSV)."""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile

from kwabo.integrations.pdf_parser import extract_pdf_text


def _extract_excel_text(xlsx_bytes: bytes) -> str:
    try:
        import openpyxl
    except ImportError:
        return "[openpyxl niet beschikbaar]"
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    out: list[str] = []
    for sheet in wb.worksheets:
        out.append(f"=== Sheet: {sheet.title} ===")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(cells):
                out.append(" | ".join(cells))
    return "\n".join(out)


def _extract_docx_text(docx_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
            xml_bytes = z.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as e:
        return f"[DOCX leesfout: {e}]"
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = ET.fromstring(xml_bytes)
    lines: list[str] = []
    for p in root.iter(f"{ns}p"):
        text = "".join(t.text or "" for t in p.iter(f"{ns}t"))
        if text.strip():
            lines.append(text)
    return "\n".join(lines)


def classify_by_filename(filename: str) -> str:
    lower = (filename or "").lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith((".xlsx", ".xls")):
        return "excel"
    if lower.endswith(".docx"):
        return "docx"
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".txt"):
        return "txt"
    return "other"


def extract_text(filename: str, content: bytes) -> tuple[str, str]:
    """Return (doc_type, extracted_text). On failure: ('other', '[fout: ...]')."""
    doc_type = classify_by_filename(filename)
    try:
        if doc_type == "pdf":
            return doc_type, extract_pdf_text(content)
        if doc_type == "excel":
            return doc_type, _extract_excel_text(content)
        if doc_type == "docx":
            return doc_type, _extract_docx_text(content)
        if doc_type == "csv":
            return doc_type, content.decode("utf-8", errors="replace")
        if doc_type == "txt":
            return doc_type, content.decode("utf-8", errors="replace")
        return doc_type, "[geen text-extractor beschikbaar voor dit bestandstype]"
    except Exception as e:  # noqa: BLE001
        return doc_type, f"[extractie-fout: {e}]"
