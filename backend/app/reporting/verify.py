"""
VERIFY stage — the safety net between Patch and Ship.

Two checks, both required before any result is allowed to Ship as "resolved":

1. Balance-integrity check: recompute the ledger/bank amount difference for
   every auto-matched pair. If it doesn't actually satisfy the tolerance its
   own category claims (e.g. a "rounding" match where the amounts differ by
   more than a rounding-sized gap), the match is rejected and sent back to
   NEEDS_REVIEW rather than shipped as resolved. This is what "never force a
   match — a match is only accepted once both running balances verify" means
   in code.

2. Completeness audit: confirm every single ledger and bank transaction
   ended up SOMEWHERE in the results (auto-matched or flagged) — nothing
   silently dropped. This is what makes the report trustworthy for a loan
   application or an audit.
"""

from app.config import MatchingConfig, get_matching_config
from app.schemas import MatchCategory, MatchResult, MatchStatus, Transaction


def _expected_tolerance(category: MatchCategory, base_amount: float, config: MatchingConfig) -> float | None:
    """Max amount-diff (₹) this category is allowed to have. None = not an auto-match category."""
    if category in (MatchCategory.EXACT, MatchCategory.TIMING_LAG):
        return 0.0
    if category == MatchCategory.ROUNDING:
        return max(config.rounding_abs_tolerance, base_amount * config.rounding_pct_tolerance)
    return None


def verify_balances(
    results: list[MatchResult], config: MatchingConfig | None = None
) -> tuple[list[MatchResult], int]:
    """Re-check every AUTO_MATCHED pair; downgrade any that don't actually verify."""
    config = config or get_matching_config()
    verified: list[MatchResult] = []
    downgraded = 0

    for r in results:
        if r.status == MatchStatus.AUTO_MATCHED and r.ledger_txn and r.bank_txn:
            diff = round(abs(r.ledger_txn.amount - r.bank_txn.amount), 2)
            tolerance = _expected_tolerance(r.category, max(r.ledger_txn.amount, r.bank_txn.amount), config)
            if tolerance is not None and diff > tolerance:
                downgraded += 1
                verified.append(
                    r.model_copy(
                        update={
                            "status": MatchStatus.NEEDS_REVIEW,
                            "category": MatchCategory.GENUINE_ERROR,
                            "explanation": (
                                f"Verification failed: a {r.category} match should differ by at most "
                                f"₹{tolerance:.2f}, but this pair differs by ₹{diff:.2f}. Sent back for "
                                "human review instead of being force-matched."
                            ),
                        }
                    )
                )
                continue
        verified.append(r)

    return verified, downgraded

def completeness_audit(
    results: list[MatchResult], ledger: list[Transaction], bank: list[Transaction]
) -> dict:
    """Confirm every transaction is accounted for, and totals reconcile within tolerance."""

    def ids(side_attr: str, status: MatchStatus) -> set[str]:
        return {
            getattr(r, side_attr).source_id
            for r in results
            if getattr(r, side_attr) and r.status == status
        }

    matched_ledger_ids = ids("ledger_txn", MatchStatus.AUTO_MATCHED)
    matched_bank_ids = ids("bank_txn", MatchStatus.AUTO_MATCHED)
    flagged_ledger_ids = ids("ledger_txn", MatchStatus.NEEDS_REVIEW)
    flagged_bank_ids = ids("bank_txn", MatchStatus.NEEDS_REVIEW)

    all_ledger_ids = {t.source_id for t in ledger}
    all_bank_ids = {t.source_id for t in bank}
    missing_ledger = sorted(all_ledger_ids - matched_ledger_ids - flagged_ledger_ids)
    missing_bank = sorted(all_bank_ids - matched_bank_ids - flagged_bank_ids)

    matched_ledger_total = sum(t.amount for t in ledger if t.source_id in matched_ledger_ids)
    matched_bank_total = sum(t.amount for t in bank if t.source_id in matched_bank_ids)

    return {
        "complete": not missing_ledger and not missing_bank,
        "missing_ledger_ids": missing_ledger,
        "missing_bank_ids": missing_bank,
        "ledger_total": round(sum(t.amount for t in ledger), 2),
        "bank_total": round(sum(t.amount for t in bank), 2),
        "matched_ledger_total": round(matched_ledger_total, 2),
        "matched_bank_total": round(matched_bank_total, 2),
        "matched_pair_balance_diff": round(abs(matched_ledger_total - matched_bank_total), 2),
        "flagged_ledger_total": round(
            sum(t.amount for t in ledger if t.source_id in flagged_ledger_ids), 2
        ),
        "flagged_bank_total": round(
            sum(t.amount for t in bank if t.source_id in flagged_bank_ids), 2
        ),
    }
