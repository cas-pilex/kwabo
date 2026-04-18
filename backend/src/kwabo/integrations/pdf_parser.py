"""PDF text extraction using pdfplumber with layout preservation."""
from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pdfplumber


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF. Prefers tables (layout-aware), falls back to raw text."""
    if not pdf_bytes:
        return ""
    out: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                out.append(f"--- PAGE {page_num} ---")
                tables = page.extract_tables() or []
                table_bboxes = []
                for tbl in tables:
                    rows = []
                    for row in tbl:
                        cells = [(c or "").strip() for c in row]
                        if any(cells):
                            rows.append(" | ".join(cells))
                    if rows:
                        out.append("\n".join(rows))
                text = page.extract_text() or ""
                if text.strip():
                    out.append(text)
    except Exception as e:  # noqa: BLE001
        out.append(f"[pdfplumber error: {e}]")
        out.append(_pdftotext_fallback(pdf_bytes))
    return "\n".join(out).strip()


def _pdftotext_fallback(pdf_bytes: bytes) -> str:
    try:
        p = subprocess.run(
            ["pdftotext", "-layout", "-", "-"],
            input=pdf_bytes,
            capture_output=True,
            timeout=30,
            check=False,
        )
        return p.stdout.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def extract_pdf_file(path: str | Path) -> str:
    return extract_pdf_text(Path(path).read_bytes())
