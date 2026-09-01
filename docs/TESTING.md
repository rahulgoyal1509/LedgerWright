# LedgerWright — Testing Approach & Bugs Found

This project was built and verified incrementally: each phase was tested end-to-end before moving to the next, and every "it works" claim in this repo is backed by an actual run, not an assumption. This document is the honest record of that — including the bugs that testing caught, because catching them is the point of testing, not something to hide.

## Testing Philosophy

1. **No claim of correctness without running it.** Code that "should work" gets run against real data before being called done.
2. **Test the untested path deliberately.** OCR fallback, PDF debit/credit columns, and date-format handling all had bugs that only surfaced when someone actually generated realistic test data and ran it through — not from reading the code.
3. **A passing test isn't the finish line if the output looks wrong.** Several bugs below were only caught by manually opening a generated file and checking the actual numbers, not just checking that the script exited without an error.
4. **Fix regressions immediately, don't assume a fix is safe.** More than once, a fix for one bug was re-tested against the *previously working* cases and found to have broken them — see the date-parsing bug below.

## Test Coverage Summary

| Component | How it was tested | Status |
|---|---|---|
| CSV ingestion | Sample datasets (49-row and 202-row), live API | ✅ Verified |
| Excel ingestion | Round-tripped CSV → Excel → parser | ✅ Verified |
| Digital PDF ingestion | Generated realistic Debit/Credit-column bank statement | ✅ Verified |
| OCR PDF ingestion | Generated a genuine image-only (zero text layer) scanned PDF | ✅ Verified |
| Rule-based matching | Both sample datasets, plus targeted threshold-override tests | ✅ Verified |
| Gemini triage | Mocked-response test (schema/parsing) + live API key test | ✅ Verified |
| Balance verification | Targeted tests forcing both stricter and looser tolerances | ✅ Verified |
| Completeness audit | Both sample datasets — confirmed `complete: true` | ✅ Verified |
| Excel report generation | Opened and inspected actual output file structure/row counts | ✅ Verified |
| Live API endpoints | curl + live server for every endpoint | ✅ Verified |
| Next.js dashboard | Built, ran dev server, live browser request against real backend | ✅ Verified |
| Configurable thresholds | Verified both directions (stricter and looser) change real output | ✅ Verified |

## Bugs Found During Development

### 1. PDF parser silently dropped every credit-side transaction

**How it was found:** generated a realistic bank statement PDF using separate Debit and Credit columns (the actual real-world format — most bank statements don't use a single signed "Amount" column). Ran it through the parser.

**What happened:** only 9 of 15 transactions survived. Every sales receipt and interest credit vanished with no error.

**Root cause:** the column-mapping logic only ever assigned one column to `amount`. Since "Debit" was processed first, "Credit" never got mapped to anything and was filtered out entirely.

**Fix:** added explicit `debit` and `credit` targets to the column-alias map, and a coalescing step that combines them into a single `amount` column (each row has exactly one of the two populated).

**Verification:** re-ran the same PDF — all 15 rows recovered, confirmed via the full pipeline and the live API.

---

### 2. Dates silently corrupted, not dropped — worse than an error

**How it was found:** immediately after fixing bug #1, normalizing the recovered rows.

**What happened:** `01/09/2025` (September 1st, the Indian `DD/MM/YYYY` standard) was being read as **January 9th**. 12 of 15 dates were silently wrong; the other 3 (day > 12) were dropped as unparseable, since there's no 13th month.

**Root cause:** `pd.to_datetime()` with no `dayfirst` argument defaults to interpreting ambiguous dates as US-style `MM/DD/YYYY`.

**First fix attempt — and the regression it caused:** adding `dayfirst=True` fixed the PDF dates, but re-running the *already-working* CSV test suite immediately afterward showed a regression: dates dropped from 25/24 rows to 11/10, because pandas' `dayfirst` flag also incorrectly reinterpreted the ISO-format dates (`2025-08-01`) already used correctly in the CSV samples — turning them into wrong dates too.

**Final fix:** a two-pass parser — try strict ISO (`%Y-%m-%d`) first, since that format is unambiguous, and only apply `dayfirst=True` to whatever didn't match ISO.

**Verification:** re-tested all three data sources in the same run — both CSV datasets (confirming no regression) and the PDF (confirming the original fix still held).

---

### 3. OCR fallback returned the wrong number, not just imperfect text

**How it was found:** built a genuinely realistic test — rendered the digital PDF to an image and re-embedded it into a new PDF with zero extractable text, simulating an actual scanned/photographed document. Ran the existing OCR fallback against it.

**What happened:** it "worked" — all 15 rows extracted, no errors — but the amount for the first row was `184500.00`. The real transaction was `32000.00`. `184500.00` was the **running account balance** for that row, not the transaction amount.

**Root cause:** the original OCR fallback used a single regex that grabbed "the last number on the line" as the amount. In a statement with Debit/Credit/Balance columns, the last number on a line is the balance, not the transaction.

**Fix:** rebuilt the OCR path to use Tesseract's word-level bounding box data (`image_to_data`) instead of flat text. The header row is located by keyword matching, each header word's x-position becomes a column anchor, and every subsequent word is assigned to its nearest anchor — reconstructing actual table columns instead of guessing from raw text.

**A secondary finding during this fix:** the first version of the realistic test PDF used a dark navy header with white text, which badly confused Tesseract (garbled to nonsense). This was a fair OCR limitation, but also revealed the test fixture wasn't representative — real bank statement exports are almost always plain black-on-white for legibility. Fixed the test data to be realistic rather than working around an unrealistic test case.

**Verification:** re-ran the corrected OCR path — correct amounts, correct dates, same 12/12 auto-match result as the digital-PDF version of the same statement, confirmed through normalization, the full pipeline, and the live API.

---

### 4. Config refactor could have silently changed matching behavior

**Context:** matching tolerances were originally hardcoded separately in `fuzzy_matcher.py` and `verify.py` — the same numbers, duplicated in two files, that had to be kept manually in sync.

**How it was found:** while centralizing these into `config.py` and adding support for per-request overrides, a deliberate test was run: setting `max_timing_lag_days=0` and checking the result.

**What happened:** auto-matched pairs dropped from 21 to 19 — one too many. The timing-lag case correctly disappeared, but so did the "unrelated" rounding-difference match that should have been unaffected by a timing-lag setting.

**Root cause:** the candidate-generation date filter (which rows are even considered as possible pairs) was reusing `max_timing_lag_days` directly as its ceiling. But EXACT (≤1 day) and ROUNDING (≤2 days) have their own fixed day-windows independent of the configurable timing-lag threshold. A very low `max_timing_lag_days` was incorrectly also excluding candidates those other categories should still have been able to see.

**Fix:** the candidate-generation window now uses `max(max_timing_lag_days, 2)` — always wide enough for EXACT/ROUNDING regardless of how strict the timing-lag setting is.

**Verification:** re-tested with `max_timing_lag_days=0` — exact matches (19) and rounding matches (1) both stayed exactly the same, only the timing-lag case moved to review, as intended. Also tested the reverse direction (loosening tolerances) and a targeted tightening test (setting rounding tolerance below the actual gap in the sample data) to confirm both directions of the config work correctly and independently.

---

### 5. Excel report showed raw Python object text instead of clean labels

**How it was found:** generated the report, then actually opened it and read the cells — not just checked that `openpyxl` didn't raise an exception.

**What happened:** the "By Category" summary row displayed `{<MatchCategory.EXACT: 'exact_match'>: 19, ...}` instead of `{'exact_match': 19, ...}`.

**Root cause:** `summarize()` was using the raw enum object as a dictionary key instead of its `.value`, and pandas stringified the enum's `repr()` when writing it to the sheet.

**Fix:** explicitly extract `.value` when building the `by_category` dictionary.

**Verification:** regenerated the report and read the actual cell contents to confirm clean text, not just re-running the script and trusting a lack of errors.

## What Hasn't Been Tested

In the interest of the same honesty this document is trying to model:

- **OCR fallback has not been tested on a real-world scanned document** (a genuine phone photo or physical scanner output) — only on a synthetically-flattened version of a clean digital render. Real scans have skew, noise, and lighting variation that weren't tested.
- **Load/scale testing** beyond the 202-transaction dataset hasn't been done. The greedy O(n×m) candidate matching in `fuzzy_matcher.py` would need attention at much larger transaction volumes.
- **Concurrent request handling** on the deployed backend hasn't been stress-tested.
