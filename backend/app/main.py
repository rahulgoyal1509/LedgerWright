"""
LedgerWright backend — Phase 1 scaffold.

Currently wires up: SCAN stage only (ingestion + normalization).
Matching (Triage/Patch), Verify, and Ship land in later phases.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_matching_config
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
    allow_origins=[
        "https://ledger-wright.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
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
async def reconcile(
    ledger_file: UploadFile,
    bank_file: UploadFile,
    max_timing_lag_days: int | None = Form(None, description="Override: max days between ledger entry and bank clearing to still count as a timing-lag auto-match."),
    rounding_abs_tolerance: float | None = Form(None, description="Override: flat ₹ tolerance for a rounding-difference auto-match."),
    rounding_pct_tolerance: float | None = Form(None, description="Override: % of transaction amount tolerance for a rounding-difference auto-match."),
) -> dict:
    """
    Full pipeline: Scan -> Prematch -> Triage -> Verify -> completeness audit.
    Returns every matched pair, every flagged item, and a health report
    confirming every transaction was accounted for and balances reconcile.

    Matching thresholds default to whatever's set in .env, but can be
    overridden per-request with the three optional form fields above —
    handy for tuning how strict/lenient auto-matching is without a restart.
    """
    ledger_txns = await _parse_and_normalize(Source.LEDGER, ledger_file)
    bank_txns = await _parse_and_normalize(Source.BANK, bank_file)

    config = get_matching_config({
        "max_timing_lag_days": max_timing_lag_days,
        "rounding_abs_tolerance": rounding_abs_tolerance,
        "rounding_pct_tolerance": rounding_pct_tolerance,
    })

    # run_full_pipeline is synchronous (Gemini SDK blocks); offload to thread
    # pool so we don't hold the event loop during the LLM call.
    results, health = await asyncio.to_thread(run_full_pipeline, ledger_txns, bank_txns, config)
    summary = summarize(results, len(ledger_txns), len(bank_txns))

    return {
        "summary": summary,
        "health": health,
        "results": [r.model_dump(mode="json") for r in results],
    }


@app.post("/reconcile/report")
async def reconcile_report(
    ledger_file: UploadFile,
    bank_file: UploadFile,
    max_timing_lag_days: int | None = Form(None),
    rounding_abs_tolerance: float | None = Form(None),
    rounding_pct_tolerance: float | None = Form(None),
) -> FileResponse:
    """SHIP stage: same pipeline as /reconcile, but returns a downloadable .xlsx report."""
    ledger_txns = await _parse_and_normalize(Source.LEDGER, ledger_file)
    bank_txns = await _parse_and_normalize(Source.BANK, bank_file)

    config = get_matching_config({
        "max_timing_lag_days": max_timing_lag_days,
        "rounding_abs_tolerance": rounding_abs_tolerance,
        "rounding_pct_tolerance": rounding_pct_tolerance,
    })

    results, health = await asyncio.to_thread(run_full_pipeline, ledger_txns, bank_txns, config)
    summary = summarize(results, len(ledger_txns), len(bank_txns))

    output_path = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False).name
    build_excel_report(results, summary, health, output_path)

    return FileResponse(
        output_path,
        filename="LedgerWright_Reconciliation_Report.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )