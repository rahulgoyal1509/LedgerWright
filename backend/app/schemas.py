"""
Shared data schema for LedgerWright.

Every ingestion source (CSV, Excel, PDF, QuickBooks/Tally/Zoho export) gets
normalized into this single Transaction shape before it ever reaches the
matching engine. This is what makes the Scan stage source-agnostic.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Source(str, Enum):
    BANK = "bank"
    LEDGER = "ledger"


class Transaction(BaseModel):
    """A single normalized transaction, from either side of the reconciliation."""

    source: Source
    source_id: str = Field(..., description="Original row ID from the raw file, e.g. 'B001' or 'L001'")
    date: date
    description: str
    amount: float = Field(..., description="Always positive; direction is implied by `source` + description")
    reference: str = Field(default="", description="Invoice / UPI / NEFT / PO reference string, used for fuzzy matching")

    class Config:
        use_enum_values = True


class MatchStatus(str, Enum):
    AUTO_MATCHED = "auto_matched"
    NEEDS_REVIEW = "needs_review"
    UNMATCHED = "unmatched"


class MatchCategory(str, Enum):
    EXACT = "exact_match"
    TIMING_LAG = "timing_lag"
    ROUNDING = "rounding_difference"
    DUPLICATE = "duplicate_entry"
    MISSING_ENTRY = "missing_entry"
    GENUINE_ERROR = "genuine_error"
    UNKNOWN = "unknown"


class MatchResult(BaseModel):
    """Output of the Triage stage for a single ledger<->bank pair (or unmatched singleton)."""

    ledger_txn: Optional[Transaction] = None
    bank_txn: Optional[Transaction] = None
    status: MatchStatus
    category: MatchCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    explanation: str = Field(..., description="Plain-English reason, shown to the user")
