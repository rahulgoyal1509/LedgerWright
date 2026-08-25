"""
Phase 2 smoke test: run the full Scan -> Prematch -> Triage pipeline on the
sample data and print the same kind of summary table shown in the
submission PDF's "Proposed Solution" section.

Run: python test_matching.py
"""

from pathlib import Path

from app.ingestion.csv_parser import parse_csv
from app.ingestion.normalize import normalize_bank, normalize_ledger
from app.matching.pipeline import run_matching, summarize
from app.schemas import MatchStatus

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"


def main() -> None:
    ledger = normalize_ledger(parse_csv(str(SAMPLES / "ledger.csv")))
    bank = normalize_bank(parse_csv(str(SAMPLES / "bank_statement.csv")))

    results = run_matching(ledger, bank)
    summary = summarize(results, len(ledger), len(bank))

    print("=== SUMMARY ===")
    for k, v in summary.items():
        print(f"{k}: {v}")

    print("\n=== AUTO-MATCHED (sample) ===")
    auto = [r for r in results if r.status == MatchStatus.AUTO_MATCHED]
    for r in auto[:5]:
        l = r.ledger_txn.description if r.ledger_txn else "-"
        b = r.bank_txn.description if r.bank_txn else "-"
        print(f"[{r.category}] {l!r} <-> {b!r}  ({r.explanation})")
    print(f"... and {len(auto) - 5} more auto-matched pairs" if len(auto) > 5 else "")

    print("\n=== FLAGGED FOR REVIEW ===")
    review = [r for r in results if r.status == MatchStatus.NEEDS_REVIEW]
    for r in review:
        txn = r.ledger_txn or r.bank_txn
        print(f"[{r.category}] ({txn.source}) {txn.description!r} — {r.explanation}")

    total_flagged_pct = round(100 * len(review) / (len(ledger) + len(bank)), 1)
    print(f"\n{len(review)} genuine exceptions flagged out of {len(ledger) + len(bank)} "
          f"total line items ({total_flagged_pct}%) — the rest auto-resolved.")


if __name__ == "__main__":
    main()
