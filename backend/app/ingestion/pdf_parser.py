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

import pandas as pd
import pdfplumber

from .csv_parser import REQUIRED_COLUMNS

# Loose header aliases seen across common Indian bank statement exports
_COLUMN_ALIASES = {
    "date": {"date", "txn date", "transaction date", "value date"},
    "description": {"description", "narration", "particulars", "details"},
    "amount": {"amount", "amount (inr)", "transaction amount"},
    "debit": {"debit", "debit amount", "withdrawal", "withdrawal amount", "dr"},
    "credit": {"credit", "credit amount", "deposit", "deposit amount", "cr"},
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


def _coalesce_debit_credit(df: pd.DataFrame) -> pd.DataFrame:
    """
    Most real bank statements split Debit and Credit into separate columns
    rather than one signed Amount column. A row has exactly one of the two
    populated — coalesce them into the single `amount` column the rest of
    the pipeline expects, rather than silently dropping whichever column
    didn't win the original "amount" mapping.
    """
    if "amount" in df.columns:
        return df  # already a single amount column, nothing to do

    has_debit = "debit" in df.columns
    has_credit = "credit" in df.columns
    if not (has_debit or has_credit):
        raise ValueError(
            "Could not find an 'amount' column, or a 'debit'/'credit' pair, "
            f"in the PDF table. Columns found: {list(df.columns)}"
        )

    debit = df["debit"] if has_debit else ""
    credit = df["credit"] if has_credit else ""
    # Whichever side is non-blank for a given row is that row's amount.
    df["amount"] = debit.where(debit.astype(str).str.strip().ne(""), credit)
    return df.drop(columns=[c for c in ("debit", "credit") if c in df.columns])


def _tables_to_dataframe(tables: list[list[list[str]]]) -> pd.DataFrame | None:
    for table in tables:
        if not table or len(table) < 2:
            continue
        header, *rows = table
        col_map = _map_columns(header)
        mapped_targets = set(col_map.values())
        has_amount_col = "amount" in mapped_targets
        has_debit_credit = {"debit", "credit"} & mapped_targets
        if "date" not in mapped_targets or "description" not in mapped_targets:
            continue  # not the transactions table (could be a summary/fees table)
        if not (has_amount_col or has_debit_credit):
            continue

        df = pd.DataFrame(rows, columns=header)
        df = df.rename(columns=col_map)
        keep = REQUIRED_COLUMNS | {"reference", "debit", "credit"}
        df = df[[c for c in df.columns if c in keep]]
        df = _coalesce_debit_credit(df)
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
    OCR fallback for scanned bank statements.

    Requires: pytesseract + pdf2image (and the system `tesseract` + `poppler`
    binaries). Uses word-level bounding boxes (not plain line-by-line text)
    to reconstruct actual table columns — a naive "grab the last number on
    the line" approach silently picks up the running Balance column instead
    of the transaction amount, which is wrong in a way that doesn't look
    wrong until you check the numbers.

    On Windows, tesseract.exe and poppler's binaries usually aren't on PATH
    by default. Rather than requiring a PATH edit (which needs a terminal
    restart and is a common source of "works on my machine" issues), both
    can be pointed at explicitly via environment variables in .env:
      TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
      POPPLER_PATH=C:\\poppler-24.08.0\\Library\\bin
    If unset, falls back to whatever's already on PATH (the Linux/Mac default).
    """
    import os

    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        return None

    tesseract_cmd = os.environ.get("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    poppler_path = os.environ.get("POPPLER_PATH")

    try:
        pages = convert_from_path(path, dpi=300, poppler_path=poppler_path or None)
    except Exception:
        return None

    for page in pages:
        table = _ocr_page_to_table(page)
        if table is not None:
            df = _tables_to_dataframe([table])
            if df is not None and not df.empty:
                return df
    return None


def _preprocess_for_ocr(image):
    """
    Grayscale + contrast/sharpness boost before OCR. Real scanned statements
    are frequently faint, slightly uneven, or low-contrast (phone photos,
    old scanners) — this materially improves Tesseract's word accuracy on
    anything other than a pristine digital render.
    """
    from PIL import ImageEnhance, ImageOps

    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Sharpness(gray).enhance(1.5)
    return gray


def _ocr_page_to_table(image) -> list[list[str]] | None:
    """
    Reconstruct a header+rows table from OCR'd word positions.

    Strategy: find the header row by matching known column-name keywords,
    record each header word's x-position as that column's anchor, then for
    every word on every subsequent line assign it to whichever column
    anchor is horizontally closest. This is what lets us tell "Debit" and
    "Balance" apart even though both are just numbers to the OCR engine.
    """
    import pytesseract
    from pytesseract import Output

    image = _preprocess_for_ocr(image)
    data = pytesseract.image_to_data(image, output_type=Output.DICT)
    n = len(data["text"])

    lines: dict[tuple, list[dict]] = {}
    for i in range(n):
        text = data["text"][i].strip()
        if not text:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(
            {"text": text, "x": data["left"][i] + data["width"][i] / 2}
        )
    ordered_lines = [sorted(words, key=lambda w: w["x"]) for words in lines.values()]

    anchors: dict[str, float] = {}
    header_idx = None
    for idx, words in enumerate(ordered_lines):
        found = {}
        for w in words:
            key = w["text"].lower().strip(":.")
            for col, kws in _OCR_HEADER_KEYWORDS.items():
                if key in kws and col not in found:
                    found[col] = w["x"]
        if len(found) >= 3 and "date" in found:
            anchors, header_idx = found, idx
            break

    if header_idx is None:
        return None  # no confident header row — don't guess at columns

    col_names = list(anchors.keys())
    col_x = list(anchors.values())

    def nearest_col(x: float) -> str:
        return col_names[min(range(len(col_x)), key=lambda i: abs(x - col_x[i]))]

    rows = []
    for words in ordered_lines[header_idx + 1 :]:
        row = {c: "" for c in col_names}
        for w in words:
            col = nearest_col(w["x"])
            row[col] = f"{row[col]} {w['text']}".strip()
        if row.get("date", "").strip():
            rows.append(row)

    if not rows:
        return None
    return [col_names] + [[row[c] for c in col_names] for row in rows]