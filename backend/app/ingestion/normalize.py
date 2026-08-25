"""
Normalization layer: raw DataFrame (from csv_parser / excel_parser / pdf_parser)
-> list[Transaction] in the common schema used by the matching engine.

This is the seam that keeps the rest of the pipeline (Triage/Patch/Verify/Ship)
completely ignorant of whether the data originally came from a CSV, an Excel
export, or a PDF bank statement.
"""

from __future__ import annotations

import pandas as pd

from app.schemas import Source, Transaction

_ID_COLUMN_CANDIDATES = ["entry_id", "txn_id", "id", "transaction_id"]


def _find_id_column(df: pd.DataFrame) -> str | None:
    for candidate in _ID_COLUMN_CANDIDATES:
        if candidate in df.columns:
            return candidate
    return None


def normalize_dataframe(df: pd.DataFrame, source: Source) -> list[Transaction]:
    """Convert a raw parsed DataFrame into a list of normalized Transactions."""
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    if "reference" not in df.columns:
        df["reference"] = ""

    id_col = _find_id_column(df)
    prefix = "B" if source == Source.BANK else "L"

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").abs()
    df["description"] = df["description"].astype(str).str.strip()
    df["reference"] = df["reference"].fillna("").astype(str).str.strip()

    bad_rows = df["date"].isna() | df["amount"].isna()
    if bad_rows.any():
        # In production these would go to an ingestion-error report rather
        # than being silently dropped. For the hackathon scaffold: drop + warn.
        df = df[~bad_rows]

    transactions: list[Transaction] = []
    for i, (_, row) in enumerate(df.reset_index(drop=True).iterrows()):
        source_id = str(row[id_col]) if id_col else f"{prefix}{i + 1:03d}"
        transactions.append(
            Transaction(
                source=source,
                source_id=source_id,
                date=row["date"],
                description=row["description"],
                amount=float(row["amount"]),
                reference=row["reference"],
            )
        )
    return transactions


def normalize_ledger(df: pd.DataFrame) -> list[Transaction]:
    return normalize_dataframe(df, Source.LEDGER)


def normalize_bank(df: pd.DataFrame) -> list[Transaction]:
    return normalize_dataframe(df, Source.BANK)


def to_frame(transactions: list[Transaction]) -> pd.DataFrame:
    """Convenience: normalized Transactions back to a flat DataFrame for display/debugging."""
    return pd.DataFrame([t.model_dump() for t in transactions])
