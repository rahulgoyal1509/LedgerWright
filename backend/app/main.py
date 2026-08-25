"""
LedgerWright backend — Phase 1 scaffold.

Currently wires up: SCAN stage only (ingestion + normalization).
Matching (Triage/Patch), Verify, and Ship land in later phases.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.ingestion.csv_parser import parse_csv
from app.ingestion.excel_parser import parse_excel
from app.ingestion.pdf_parser import parse_pdf
from app.ingestion.normalize import normalize_bank, normalize_ledger, to_frame
from app.matching.pipeline import run_full_pipeline, summarize
from app.reporting.report import build_excel_report
from app.schemas import Source
from fastapi.responses import FileResponse

app = FastAPI(title="LedgerWright API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before production
    allow_methods=["*"],
    allow_headers=["*"],
)

_PARSERS = {
    ".csv": parse_csv,
    ".xlsx": parse_excel,
    ".xls": parse_excel,
    ".pdf": parse_pdf,
}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


async def _parse_and_normalize(source: Source, file: UploadFile):
    suffix = Path(file.filename or "").suffix.lower()
    parser = _PARSERS.get(suffix)
    if parser is None:
        raise HTTPException(400, f"Unsupported file type '{suffix}'. Use CSV, XLSX, or PDF.")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        raw_df = parser(tmp_path)
    except Exception as exc:
        raise HTTPException(422, f"Failed to parse {file.filename}: {exc}") from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    normalize_fn = normalize_bank if source == Source.BANK else normalize_ledger
    return normalize_fn(raw_df)


@app.post("/ingest/{source}")
async def ingest(source: Source, file: UploadFile) -> dict:
    """SCAN stage: accept a bank statement or ledger export, parse + normalize it."""
    transactions = await _parse_and_normalize(source, file)
    return {
        "source": source,
        "filename": file.filename,
        "row_count": len(transactions),
        "transactions": [t.model_dump(mode="json") for t in transactions],
    }


@app.post("/reconcile")
async def reconcile(ledger_file: UploadFile, bank_file: UploadFile) -> dict:
    """
    Full pipeline: Scan -> Prematch -> Triage -> Verify -> completeness audit.
    Returns every matched pair, every flagged item, and a health report
    confirming every transaction was accounted for and balances reconcile.
    """
    ledger_txns = await _parse_and_normalize(Source.LEDGER, ledger_file)
    bank_txns = await _parse_and_normalize(Source.BANK, bank_file)

    results, health = run_full_pipeline(ledger_txns, bank_txns)
    summary = summarize(results, len(ledger_txns), len(bank_txns))

    return {
        "summary": summary,
        "health": health,
        "results": [r.model_dump(mode="json") for r in results],
    }


@app.post("/reconcile/report")
async def reconcile_report(ledger_file: UploadFile, bank_file: UploadFile) -> FileResponse:
    """SHIP stage: same pipeline as /reconcile, but returns a downloadable .xlsx report."""
    ledger_txns = await _parse_and_normalize(Source.LEDGER, ledger_file)
    bank_txns = await _parse_and_normalize(Source.BANK, bank_file)

    results, health = run_full_pipeline(ledger_txns, bank_txns)
    summary = summarize(results, len(ledger_txns), len(bank_txns))

    output_path = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False).name
    build_excel_report(results, summary, health, output_path)

    return FileResponse(
        output_path,
        filename="LedgerWright_Reconciliation_Report.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
