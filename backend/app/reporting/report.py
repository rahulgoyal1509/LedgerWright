"""
SHIP stage — turns verified MatchResults into the deliverable: a formatted
Excel reconciliation report with a Summary sheet, an Auto-Matched sheet,
and a Flagged-for-Review sheet. This is the artifact a small business owner
hands to their accountant, or attaches to a loan application.
"""

from __future__ import annotations

import pandas as pd

from app.schemas import MatchResult, MatchStatus


def _results_to_rows(results: list[MatchResult]) -> list[dict]:
    rows = []
    for r in results:
        rows.append(
            {
                "Status": r.status.value if hasattr(r.status, "value") else r.status,
                "Category": r.category.value if hasattr(r.category, "value") else r.category,
                "Confidence": r.confidence,
                "Ledger Date": r.ledger_txn.date if r.ledger_txn else None,
                "Ledger Description": r.ledger_txn.description if r.ledger_txn else None,
                "Ledger Amount": r.ledger_txn.amount if r.ledger_txn else None,
                "Bank Date": r.bank_txn.date if r.bank_txn else None,
                "Bank Description": r.bank_txn.description if r.bank_txn else None,
                "Bank Amount": r.bank_txn.amount if r.bank_txn else None,
                "Explanation": r.explanation,
            }
        )
    return rows


def build_excel_report(results: list[MatchResult], summary: dict, health: dict, output_path: str) -> str:
    df = pd.DataFrame(_results_to_rows(results))
    auto_df = df[df["Status"] == MatchStatus.AUTO_MATCHED.value].drop(columns=["Status"])
    review_df = df[df["Status"] == MatchStatus.NEEDS_REVIEW.value].drop(columns=["Status"])

    summary_rows = [{"Metric": k.replace("_", " ").title(), "Value": v} for k, v in summary.items()]
    summary_rows += [
        {"Metric": "—", "Value": "—"},
        {"Metric": "Verification", "Value": "—"},
    ]
    summary_rows += [
        {"Metric": k.replace("_", " ").title(), "Value": v}
        for k, v in health.items()
        if k not in ("missing_ledger_ids", "missing_bank_ids")
    ]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)
        auto_df.to_excel(writer, sheet_name="Auto-Matched", index=False)
        review_df.to_excel(writer, sheet_name="Flagged for Review", index=False)

        for sheet_name, frame in (
            ("Summary", pd.DataFrame(summary_rows)),
            ("Auto-Matched", auto_df),
            ("Flagged for Review", review_df),
        ):
            ws = writer.sheets[sheet_name]
            for col_idx, col in enumerate(frame.columns, start=1):
                if frame.empty:
                    width = 14
                else:
                    max_len = frame[col].astype(str).str.len().max()
                    width = max(12, min(40, int(max_len if pd.notna(max_len) else 10) + 2))
                ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = width

    return output_path
