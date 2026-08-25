"""
Phase 3 smoke test: full pipeline (Scan -> Prematch -> Triage -> Verify ->
completeness audit) plus the Excel report export.

Run: python test_full_pipeline.py
"""

from pathlib import Path

from app.ingestion.csv_parser import parse_csv
from app.ingestion.normalize import normalize_bank, normalize_ledger
from app.matching.pipeline import run_full_pipeline, summarize
from app.reporting.report import build_excel_report

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"


def main() -> None:
    ledger = normalize_ledger(parse_csv(str(SAMPLES / "ledger.csv")))
    bank = normalize_bank(parse_csv(str(SAMPLES / "bank_statement.csv")))

    results, health = run_full_pipeline(ledger, bank)
    summary = summarize(results, len(ledger), len(bank))

    print("=== SUMMARY ===")
    for k, v in summary.items():
        print(f"{k}: {v}")

    print("\n=== VERIFY / COMPLETENESS AUDIT ===")
    for k, v in health.items():
        print(f"{k}: {v}")

    if health["complete"]:
        print("\n✅ Every ledger and bank transaction is accounted for — nothing dropped silently.")
    else:
        print("\n⚠️  Some transactions were not accounted for:", health["missing_ledger_ids"], health["missing_bank_ids"])

    if health["downgraded_on_verify"] == 0:
        print("✅ Every auto-matched pair verified — no forced matches.")
    else:
        print(f"⚠️  {health['downgraded_on_verify']} match(es) failed verification and were sent back for review.")

    out_path = Path(__file__).resolve().parent / "LedgerWright_Reconciliation_Report.xlsx"
    build_excel_report(results, summary, health, str(out_path))
    print(f"\n📄 Report written to: {out_path}")


if __name__ == "__main__":
    main()
