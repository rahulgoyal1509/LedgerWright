"""
SCAN's output -> rule-based pre-matching.

This is deliberately NOT an LLM call. It's cheap, deterministic, and clears
the large majority of transactions (exact matches, timing lags, rounding
differences) using amount + date-window + reference/description similarity.
Only what's left after this stage goes to the (expensive) LLM triage step.

This mirrors the "rule-based + fuzzy pre-filter before invoking the LLM"
design principle from the submission.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from app.config import MatchingConfig, get_matching_config
from app.schemas import MatchCategory, MatchResult, MatchStatus, Transaction

TEXT_SIMILARITY_FLOOR = 30        # rapidfuzz score (0-100); just a tie-breaker, not a hard gate

# EXACT and ROUNDING have their own fixed day-windows (see _classify) that
# are independent of the configurable timing-lag threshold. The candidate-
# generation filter below must stay at least this wide even if someone
# configures a very small (or zero) max_timing_lag_days — otherwise a
# strict timing-lag setting would incorrectly also block EXACT/ROUNDING
# matches that should still be found.
_ROUNDING_DATE_WINDOW = 2


@dataclass
class _Candidate:
    ledger_idx: int
    bank_idx: int
    amount_diff: float
    date_diff: int
    text_score: float
    category: MatchCategory


def _text_score(a: Transaction, b: Transaction) -> float:
    left = f"{a.reference} {a.description}".strip().lower()
    right = f"{b.reference} {b.description}".strip().lower()
    return fuzz.token_set_ratio(left, right)


def _classify(amount_diff: float, date_diff: int, base_amount: float, config: MatchingConfig) -> MatchCategory | None:
    if amount_diff == 0 and date_diff <= 1:
        return MatchCategory.EXACT
    if amount_diff == 0 and date_diff <= config.max_timing_lag_days:
        return MatchCategory.TIMING_LAG
    tolerance = max(config.rounding_abs_tolerance, base_amount * config.rounding_pct_tolerance)
    if 0 < amount_diff <= tolerance and date_diff <= _ROUNDING_DATE_WINDOW:
        return MatchCategory.ROUNDING
    return None


def prematch(
    ledger: list[Transaction], bank: list[Transaction], config: MatchingConfig | None = None
) -> tuple[list[MatchResult], list[Transaction], list[Transaction]]:
    """
    Greedily pair ledger <-> bank transactions on exact/near-exact rules.

    Returns:
        (auto_matched_results, unmatched_ledger, unmatched_bank)
    """
    config = config or get_matching_config()
    candidate_window = max(config.max_timing_lag_days, _ROUNDING_DATE_WINDOW)
    candidates: list[_Candidate] = []
    for li, l in enumerate(ledger):
        for bi, b in enumerate(bank):
            date_diff = abs((l.date - b.date).days)
            if date_diff > candidate_window:
                continue
            amount_diff = round(abs(l.amount - b.amount), 2)
            category = _classify(amount_diff, date_diff, max(l.amount, b.amount), config)
            if category is None:
                continue
            candidates.append(
                _Candidate(
                    ledger_idx=li,
                    bank_idx=bi,
                    amount_diff=amount_diff,
                    date_diff=date_diff,
                    text_score=_text_score(l, b),
                    category=category,
                )
            )

    # Best candidates first: smallest amount diff, then smallest date diff,
    # then highest text similarity. This is what makes greedy assignment safe
    # for duplicate ledger entries — the "real" match wins the bank txn, and
    # any leftover duplicate ledger row is naturally excluded below.
    candidates.sort(key=lambda c: (c.amount_diff, c.date_diff, -c.text_score))

    used_ledger: set[int] = set()
    used_bank: set[int] = set()
    results: list[MatchResult] = []

    _EXPLANATIONS = {
        MatchCategory.EXACT: "Amount and date match exactly between ledger and bank statement.",
        MatchCategory.TIMING_LAG: "Same amount, but the bank cleared it {days} day(s) after it was logged — a normal clearing delay.",
        MatchCategory.ROUNDING: "Amounts differ by only ₹{diff:.2f} — a rounding or minor fee difference, dates align.",
    }

    for c in candidates:
        if c.ledger_idx in used_ledger or c.bank_idx in used_bank:
            continue
        used_ledger.add(c.ledger_idx)
        used_bank.add(c.bank_idx)

        explanation = _EXPLANATIONS[c.category].format(days=c.date_diff, diff=c.amount_diff)
        results.append(
            MatchResult(
                ledger_txn=ledger[c.ledger_idx],
                bank_txn=bank[c.bank_idx],
                status=MatchStatus.AUTO_MATCHED,
                category=c.category,
                confidence=1.0 if c.category == MatchCategory.EXACT else 0.9,
                explanation=explanation,
            )
        )

    unmatched_ledger = [l for i, l in enumerate(ledger) if i not in used_ledger]
    unmatched_bank = [b for i, b in enumerate(bank) if i not in used_bank]
    return results, unmatched_ledger, unmatched_bank