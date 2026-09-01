"""
TRIAGE stage — handles whatever the rule-based pre-filter couldn't explain.

Two layers, cheapest first:
  1. A free duplicate check: if an unmatched row's amount+reference exactly
     matches a row that was ALREADY auto-matched on its own side, it's very
     likely a duplicate entry — no LLM call needed.
  2. Everything still unexplained goes to Gemini, one small batched call,
     asking for category + confidence + a plain-English explanation per item.

If GEMINI_API_KEY isn't set (e.g. running this scaffold without a key yet),
we fall back to a deterministic heuristic so the pipeline still runs
end-to-end for testing/demo purposes. Swap in a real key and it uses Gemini.
"""

from __future__ import annotations

import json
import os
from collections import Counter

from app.schemas import MatchCategory, MatchResult, MatchStatus, Source, Transaction

_FEE_KEYWORDS = ("charge", "fee", "interest", "penalty", "maintenance")


def _find_duplicates(
    unmatched: list[Transaction], auto_matched_same_side: list[Transaction]
) -> tuple[list[MatchResult], list[Transaction]]:
    """Flag unmatched rows whose (amount, reference) already appears among auto-matched rows."""
    matched_keys = Counter((t.amount, t.reference) for t in auto_matched_same_side)

    duplicates: list[MatchResult] = []
    remaining: list[Transaction] = []
    for txn in unmatched:
        key = (txn.amount, txn.reference)
        if matched_keys.get(key, 0) > 0:
            side_field = "ledger_txn" if txn.source == Source.LEDGER else "bank_txn"
            duplicates.append(
                MatchResult(
                    **{side_field: txn},
                    status=MatchStatus.NEEDS_REVIEW,
                    category=MatchCategory.DUPLICATE,
                    confidence=0.85,
                    explanation=(
                        f"'{txn.description}' (₹{txn.amount:,.2f}, ref {txn.reference}) looks like a "
                        "duplicate — another entry with the same amount and reference was already "
                        "matched. Recommend verifying and removing this row."
                    ),
                )
            )
        else:
            remaining.append(txn)
    return duplicates, remaining


def _heuristic_triage(txn: Transaction) -> MatchResult:
    """Fallback classifier used when no Gemini API key is configured."""
    side_field = "ledger_txn" if txn.source == Source.LEDGER else "bank_txn"
    desc_lower = txn.description.lower()

    if txn.source == Source.BANK and any(kw in desc_lower for kw in _FEE_KEYWORDS):
        return MatchResult(
            **{side_field: txn},
            status=MatchStatus.NEEDS_REVIEW,
            category=MatchCategory.MISSING_ENTRY,
            confidence=0.7,
            explanation=(
                f"'{txn.description}' (₹{txn.amount:,.2f}) appears on the bank statement but has no "
                "matching ledger entry — likely a bank-initiated charge or credit never logged internally. "
                "Recommend adding this entry to the ledger."
            ),
        )

    return MatchResult(
        **{side_field: txn},
        status=MatchStatus.NEEDS_REVIEW,
        category=MatchCategory.GENUINE_ERROR,
        confidence=0.5,
        explanation=(
            f"'{txn.description}' (₹{txn.amount:,.2f}, {txn.date}) has no corresponding entry on the "
            f"other side within the statement period. No rule-based explanation fits — needs a human look."
        ),
    )


def _gemini_triage(items: list[Transaction]) -> list[MatchResult]:
    """Real LLM triage via Gemini. Requires GEMINI_API_KEY and `pip install google-genai`."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    payload = [
        {
            "id": i,
            "source": t.source,
            "date": str(t.date),
            "description": t.description,
            "amount": t.amount,
            "reference": t.reference,
        }
        for i, t in enumerate(items)
    ]

    prompt = f"""You are an accounting reconciliation assistant. Each item below is a transaction
from either a bank statement or an internal ledger that had NO matching entry on the other side
after exact/timing-lag/rounding checks already ran.

For each item, decide the most likely category:
- "duplicate_entry": likely a duplicate record
- "missing_entry": a real transaction (e.g. a bank fee) that was simply never logged on the other side
- "genuine_error": looks like a real discrepancy needing human judgement (data entry error, fraud risk, or a transaction with no counterpart at all)
- "unknown": not enough information to tell

Items:
{json.dumps(payload, indent=2)}
"""

    response_schema = types.Schema(
        type=types.Type.ARRAY,
        items=types.Schema(
            type=types.Type.OBJECT,
            required=["id", "category", "confidence", "explanation"],
            properties={
                "id": types.Schema(type=types.Type.INTEGER),
                "category": types.Schema(
                    type=types.Type.STRING,
                    enum=["duplicate_entry", "missing_entry", "genuine_error", "unknown"],
                ),
                "confidence": types.Schema(type=types.Type.NUMBER),
                "explanation": types.Schema(type=types.Type.STRING),
            },
        ),
    )

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
        ),
    )
    verdicts = json.loads(response.text)

    results = []
    for v in verdicts:
        txn = items[v["id"]]
        side_field = "ledger_txn" if txn.source == Source.LEDGER else "bank_txn"
        category = MatchCategory(v["category"])
        results.append(
            MatchResult(
                **{side_field: txn},
                status=MatchStatus.NEEDS_REVIEW,
                category=category,
                confidence=float(v["confidence"]),
                explanation=v["explanation"],
            )
        )
    return results


def triage(
    unmatched_ledger: list[Transaction],
    unmatched_bank: list[Transaction],
    auto_matched: list[MatchResult],
) -> list[MatchResult]:
    """Run the full triage stage on whatever the rule-based pre-filter left unexplained."""
    auto_matched_ledger = [r.ledger_txn for r in auto_matched if r.ledger_txn]
    auto_matched_bank = [r.bank_txn for r in auto_matched if r.bank_txn]

    ledger_dupes, ledger_remaining = _find_duplicates(unmatched_ledger, auto_matched_ledger)
    bank_dupes, bank_remaining = _find_duplicates(unmatched_bank, auto_matched_bank)

    still_ambiguous = ledger_remaining + bank_remaining
    results = ledger_dupes + bank_dupes

    if not still_ambiguous:
        return results

    if os.environ.get("GEMINI_API_KEY"):
        results += _gemini_triage(still_ambiguous)
    else:
        results += [_heuristic_triage(t) for t in still_ambiguous]

    return results
