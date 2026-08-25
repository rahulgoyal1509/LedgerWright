"""
Phase 1 smoke test: parse + normalize the sample bank statement and ledger,
and print the result so we can eyeball it before wiring up the matcher.

Run: python test_ingestion.py
"""

from pathlib import Path

from app.ingestion.csv_parser import parse_csv
from app.ingestion.normalize import normalize_bank, normalize_ledger, to_frame

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"


def main() -> None:
    ledger_raw = parse_csv(str(SAMPLES / "ledger.csv"))
    bank_raw = parse_csv(str(SAMPLES / "bank_statement.csv"))

    ledger_txns = normalize_ledger(ledger_raw)
    bank_txns = normalize_bank(bank_raw)

    print(f"Ledger: {len(ledger_txns)} transactions parsed & normalized")
    print(f"Bank:   {len(bank_txns)} transactions parsed & normalized\n")

    print("Sample normalized ledger rows:")
    print(to_frame(ledger_txns).head(5).to_string(index=False))
    print("\nSample normalized bank rows:")
    print(to_frame(bank_txns).head(5).to_string(index=False))

    ledger_total = sum(t.amount for t in ledger_txns)
    bank_total = sum(t.amount for t in bank_txns)
    print(f"\nLedger total: {ledger_total:,.2f}")
    print(f"Bank total:   {bank_total:,.2f}")
    print(f"Difference:   {abs(ledger_total - bank_total):,.2f}  "
          f"(expected — this is exactly what Triage will explain)")


if __name__ == "__main__":
    main()
