# LedgerWright — Architecture

This document goes deeper into the 5-stage pipeline than the main README — how each stage actually works internally, why it's designed this way, and where the boundaries between stages are.

## Design Principle

The pipeline is ordered from **cheapest/most-certain** to **most-expensive/least-certain**:

```
Rules (free, instant, deterministic)
   ↓
Cheap heuristics (free, instant, still deterministic)
   ↓
LLM reasoning (costs money, takes time, used only when necessary)
```

This ordering is deliberate. On a typical dataset, ~90% of transactions are resolved before an LLM is ever called. The LLM is reserved for the genuinely ambiguous remainder — the cases that actually need judgment, not pattern-matching.

## The Five Stages

### 1. Scan — Ingestion & Normalization

```
Bank Statement (CSV/Excel/PDF)  ─┐
                                   ├──▶  Normalize  ──▶  list[Transaction]
Ledger Export  (CSV/Excel)      ─┘
```

Three format-specific parsers (`csv_parser.py`, `excel_parser.py`, `pdf_parser.py`) each produce a raw `DataFrame` with loosely-matched column names (handling aliases like "Narration" vs "Description", "Ref No" vs "Reference"). `normalize.py` is the seam that converts any of these into the single shared `Transaction` schema:

```python
class Transaction(BaseModel):
    source: Source          # "bank" or "ledger"
    source_id: str
    date: date
    description: str
    amount: float            # always positive
    reference: str
```

Everything downstream of this point is completely ignorant of whether the data originally came from a CSV, an Excel export, or a PDF bank statement.

**PDF-specific handling:** `pdf_parser.py` tries `pdfplumber`'s digital table extraction first. If that returns nothing (a scanned/image-only PDF), it falls back to OCR — see the [OCR Fallback](#ocr-fallback-detail) section below.

**Date parsing:** a two-pass strategy — try strict ISO (`YYYY-MM-DD`) first, since that's unambiguous, then fall back to `dayfirst=True` (the Indian bank-statement standard, `DD/MM/YYYY`) only for whatever didn't match ISO. A single `dayfirst=True` pass on everything was tried and rejected — see `TESTING.md` for why.

### 2. Prematch — Rule-Based Matching

`fuzzy_matcher.py` pairs ledger and bank transactions using three rules, in order of strictness:

| Category | Rule |
|---|---|
| **Exact** | Same amount, dates ≤1 day apart |
| **Timing Lag** | Same amount, dates within `max_timing_lag_days` (default 10) |
| **Rounding** | Amount differs by ≤ `max(rounding_abs_tolerance, amount × rounding_pct_tolerance)`, dates ≤2 days apart |

**Candidate generation and greedy assignment:** every possible ledger↔bank pair within the date window is scored, then sorted by (smallest amount difference, smallest date difference, highest text similarity) and assigned greedily. This ordering is what makes duplicate detection work "for free" — if a ledger entry was accidentally logged twice, the *better-fitting* duplicate wins the real bank transaction, and the leftover duplicate naturally falls through to the next stage unmatched.

RapidFuzz's `token_set_ratio` on the combined reference+description text is used as a tie-breaker signal, not a hard gate.

All thresholds are configurable — see `config.py` and the **Configuration** section in `README.md`.

### 3. Triage — AI-Powered Classification

Only transactions that didn't clear Prematch reach this stage — typically 10–15% of the total. Two layers, cheapest first:

**Layer 1 — free duplicate check.** If an unmatched transaction's `(amount, reference)` already appears among the auto-matched set on the same side, it's flagged as a likely duplicate without ever calling an LLM.

**Layer 2 — Gemini triage.** Whatever's still unexplained is sent to Google Gemini (`gemini-3.6-flash` via the `google-genai` SDK) in a single batched call, with a structured JSON response schema constraining output to exactly four categories:

```python
response_schema = types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(
        type=types.Type.OBJECT,
        required=["id", "category", "confidence", "explanation"],
        properties={
            "category": types.Schema(
                type=types.Type.STRING,
                enum=["duplicate_entry", "missing_entry", "genuine_error", "unknown"],
            ),
            ...
        },
    ),
)
```

**Fallback without an API key:** if `GEMINI_API_KEY` isn't set, `triage.py` uses a deterministic heuristic classifier (keyword matching for bank fees, generic "no counterpart found" for everything else) so the pipeline still runs end-to-end. This was essential during development and is a reasonable degraded mode if the key is ever unavailable.

### 4. Verify — Balance Integrity

This is the safety net between Patch and Ship, and the mechanism behind "never force a match":

```python
def _expected_tolerance(category, base_amount, config):
    if category in (EXACT, TIMING_LAG):
        return 0.0
    if category == ROUNDING:
        return max(config.rounding_abs_tolerance, base_amount * config.rounding_pct_tolerance)
```

Every auto-matched pair is re-checked against what its *own category* claims to allow. If a pair labeled `ROUNDING` actually differs by more than its tolerance permits, it's downgraded back to `NEEDS_REVIEW` with an explanation — rather than shipped as a resolved match. This uses the exact same tolerance logic as Prematch (`config.py` is the single source of truth for both — see `TESTING.md` for why that matters).

**Completeness audit:** separately confirms every single ledger and bank transaction ended up *somewhere* in the results — matched or flagged — with no silent drops. This produces the `health` object returned by `/reconcile`:

```json
{
  "complete": true,
  "matched_pair_balance_diff": 0.35,
  "downgraded_on_verify": 0,
  ...
}
```

### 5. Ship — Report & Dashboard

Two outputs from the same pipeline result:

- **Excel report** (`report.py`) — three sheets (Summary, Auto-Matched, Flagged for Review), generated via `openpyxl`.
- **Live dashboard** (Next.js) — calls `/reconcile` directly from the browser, renders summary cards, category breakdown, and a tabbed matched/flagged table.

## OCR Fallback (Detail)

Scanned/image-only PDFs have no extractable text layer, so `pdfplumber` finds nothing. The OCR path (`_parse_pdf_via_ocr`) doesn't just run Tesseract and hope for structured output — plain OCR text has no column boundaries, and a naive "the last number on the line is the amount" approach actually picks up the running **Balance** column instead of the transaction amount (see `TESTING.md`).

Instead:
1. Preprocess the image (grayscale, autocontrast, sharpen) — real scans are rarely as clean as a fresh render.
2. Run `pytesseract.image_to_data` to get **word-level bounding boxes**, not just flat text.
3. Group words into physical lines by `(block_num, par_num, line_num)`.
4. Find the header row by matching known column keywords (`date`, `narration`, `debit`, `credit`, etc.), and record each header word's x-position as that column's anchor.
5. For every subsequent line, assign each word to whichever column anchor is horizontally closest.
6. Feed the reconstructed table into the *same* `_tables_to_dataframe` function used for digital PDFs — no duplicated column-mapping logic.

This is what correctly tells "Debit" and "Balance" apart even though both are just numbers to the OCR engine.

## Configuration System

`config.py` is the single source of truth for matching tolerances — previously these were duplicated separately in `fuzzy_matcher.py` and `verify.py`, which is exactly the kind of thing that quietly drifts out of sync. Now both stages read from one `MatchingConfig`:

```
Environment variables (.env)  ──▶  MatchingConfig defaults
                                          │
Per-request API form fields  ───────────▶│  (override, if provided)
                                          ▼
                                  Used by BOTH Prematch and Verify
```

One subtlety worth noting: the candidate-generation date window in Prematch is `max(max_timing_lag_days, 2)`, not just `max_timing_lag_days` directly — because EXACT and ROUNDING have their own fixed day-windows independent of the timing-lag setting. Using the raw config value directly here was tried and found to incorrectly suppress EXACT/ROUNDING matches when `max_timing_lag_days` was configured low — see `TESTING.md`.
