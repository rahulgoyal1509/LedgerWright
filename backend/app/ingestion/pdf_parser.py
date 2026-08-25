"""
PDF bank statement ingestion.

Most Indian SME bank statements are exported as PDF. Strategy:
  1. Try pdfplumber's table extraction first (works for digitally-generated
     statements, which is the large majority).
  2. If no tables are found (i.e. the PDF is a scanned image), fall back to
     OCR via pytesseract on rasterized pages.

The OCR fallback needs the system `tesseract` binary installed on the host —
it's guarded so the rest of the app still imports cleanly if it isn't.
"""

from __future__ import annotations

import io
import re

import pandas as pd
import pdfplumber

from .csv_parser import REQUIRED_COLUMNS

# Loose header aliases seen across common Indian bank statement exports
_COLUMN_ALIASES = {
    "date": {"date", "txn date", "transaction date", "value date"},
    "description": {"description", "narration", "particulars", "details"},
    "amount": {"amount", "debit", "credit", "amount (inr)", "transaction amount"},
    "reference": {"reference", "ref no", "ref no.", "chq/ref no", "cheque no"},
}


def _map_columns(raw_columns: list[str]) -> dict[str, str]:
    """Map a statement's raw header row onto our normalized column names."""
    mapping: dict[str, str] = {}
    for raw in raw_columns:
        key = str(raw).strip().lower()
        for target, aliases in _COLUMN_ALIASES.items():
            if key in aliases and target not in mapping.values():
                mapping[raw] = target
                break
    return mapping


def _tables_to_dataframe(tables: list[list[list[str]]]) -> pd.DataFrame | None:
    for table in tables:
        if not table or len(table) < 2:
            continue
        header, *rows = table
        col_map = _map_columns(header)
        if not {"date", "description", "amount"}.issubset(col_map.values()):
            continue  # not the transactions table (could be a summary/fees table)

        df = pd.DataFrame(rows, columns=header)
        df = df.rename(columns=col_map)
        df = df[[c for c in df.columns if c in REQUIRED_COLUMNS | {"reference"}]]
        return df
    return None


def parse_pdf(path: str) -> pd.DataFrame:
    """Extract the transactions table from a PDF bank statement."""
    with pdfplumber.open(path) as pdf:
        all_tables = []
        for page in pdf.pages:
            all_tables.extend(page.extract_tables())

    df = _tables_to_dataframe(all_tables)
    if df is not None and not df.empty:
        return _clean_amounts(df)

    # Fall back to OCR for scanned statements
    df = _parse_pdf_via_ocr(path)
    if df is None or df.empty:
        raise ValueError(
            f"Could not extract a transactions table from {path} — "
            "no digital table found and OCR fallback returned nothing."
        )
    return _clean_amounts(df)


def _clean_amounts(df: pd.DataFrame) -> pd.DataFrame:
    df["amount"] = (
        df["amount"]
        .astype(str)
        .str.replace(r"[₹,]", "", regex=True)
        .str.replace(r"^\((.*)\)$", r"-\1", regex=True)  # (150.00) -> -150.00
        .str.strip()
    )
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    return df.dropna(subset=["amount"])


def _parse_pdf_via_ocr(path: str) -> pd.DataFrame | None:
    """
    Best-effort OCR fallback for scanned bank statements.

    Requires: pytesseract + pdf2image (and the system `tesseract` + `poppler`
    binaries). This is a scaffold — wire up real row parsing once we have a
    sample scanned statement to test against.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        return None

    try:
        pages = convert_from_path(path)
    except Exception:
        return None

    rows = []
    line_pattern = re.compile(
        r"(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(?P<description>.+?)\s+"
        r"(?P<amount>[\d,]+\.\d{2})\s*$"
    )
    for page in pages:
        text = pytesseract.image_to_string(page)
        for line in text.splitlines():
            match = line_pattern.search(line.strip())
            if match:
                rows.append(match.groupdict())

    if not rows:
        return None
    return pd.DataFrame(rows)
