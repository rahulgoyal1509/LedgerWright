"""
Orchestrates SCAN's output through the full pipeline: rule-based pre-filter,
LLM triage on the leftovers, balance verification, and a completeness audit.
"""

from __future__ import annotations

from app.config import MatchingConfig, get_matching_config
from app.matching.fuzzy_matcher import prematch
from app.matching.triage import triage
from app.reporting.verify import completeness_audit, verify_balances
from app.schemas import MatchResult, MatchStatus, Transaction


def run_matching(
    ledger: list[Transaction], bank: list[Transaction], config: MatchingConfig | None = None
) -> list[MatchResult]:
    config = config or get_matching_config()
    auto_matched, unmatched_ledger, unmatched_bank = prematch(ledger, bank, config)
    triaged = triage(unmatched_ledger, unmatched_bank, auto_matched)
    return auto_matched + triaged


def run_full_pipeline(
    ledger: list[Transaction], bank: list[Transaction], config: MatchingConfig | None = None
) -> tuple[list[MatchResult], dict]:
    """Scan (already done by caller) -> Prematch -> Triage -> Verify -> completeness audit."""
    config = config or get_matching_config()
    results = run_matching(ledger, bank, config)
    results, downgraded = verify_balances(results, config)
    health = completeness_audit(results, ledger, bank)
    health["downgraded_on_verify"] = downgraded
    health["config"] = config.__dict__
    return results, health


def summarize(results: list[MatchResult], ledger_count: int, bank_count: int) -> dict:
    auto = [r for r in results if r.status == MatchStatus.AUTO_MATCHED]
    review = [r for r in results if r.status == MatchStatus.NEEDS_REVIEW]

    by_category: dict[str, int] = {}
    for r in results:
        key = r.category.value if hasattr(r.category, "value") else str(r.category)
        by_category[key] = by_category.get(key, 0) + 1

    return {
        "ledger_rows": ledger_count,
        "bank_rows": bank_count,
        "auto_matched_pairs": len(auto),
        "flagged_for_review": len(review),
        "by_category": by_category,
    }