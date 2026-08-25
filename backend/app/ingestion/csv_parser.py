"""CSV ingestion for bank statements and ledger exports."""

from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = {"date", "description", "amount"}


def parse_csv(path: str) -> pd.DataFrame:
    """
    Read a bank statement or ledger CSV export into a raw DataFrame.

    Expects at minimum: date, description, amount (reference/id columns optional,
    filled in by the normalize step). Column names are matched case-insensitively.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV at {path} is missing required column(s): {sorted(missing)}. "
            f"Found columns: {list(df.columns)}"
        )

    return df
