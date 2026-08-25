"""Excel (.xlsx/.xls) ingestion for bank statements and ledger exports."""

from __future__ import annotations

import pandas as pd

from .csv_parser import REQUIRED_COLUMNS


def parse_excel(path: str, sheet_name: str | int = 0) -> pd.DataFrame:
    """
    Read a bank statement or ledger Excel export into a raw DataFrame.

    Same column contract as parse_csv: date, description, amount required.
    Most QuickBooks / Tally / Zoho Books exports land here.
    """
    df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    df.columns = [str(c).strip().lower() for c in df.columns]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Excel file at {path} is missing required column(s): {sorted(missing)}. "
            f"Found columns: {list(df.columns)}"
        )

    return df
