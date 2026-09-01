# LedgerWright — Project Summary

**FinTech & Financial Inclusion · Problem Statement `Omni_FinTech_5` — Automated Account Reconciliation for Small Businesses**

---

## The Problem

Small businesses reconcile a bank statement against an internal ledger by hand — exporting both and eyeballing rows in a spreadsheet. It's repetitive and error-prone, and it gets harder every month.

- **2–8 hrs/month** spent on manual reconciliation by a typical small business
- **90%+** of transactions are routine, exact matches — yet all checked by hand anyway
- **<5%** are genuine exceptions that actually need a human decision

Beyond time lost, messy books quietly lock small businesses out of loans, investor trust, and tax compliance — the paperwork larger businesses take for granted.

## The Solution

LedgerWright is an AI reconciliation agent that ingests a bank statement and a ledger, matches transactions automatically, explains every discrepancy in plain language, and only asks for human input where it's genuinely needed.

**Core idea:** cheap deterministic rules handle the routine ~90% instantly and for free. An LLM (Google Gemini) is only invoked on the small, genuinely ambiguous remainder — keeping the system fast, explainable, and cheap to run at scale.

## Architecture at a Glance

```
SCAN → PREMATCH → TRIAGE → VERIFY → SHIP
```

| Stage | What it does |
|---|---|
| **Scan** | Parse bank statement + ledger (CSV/Excel/PDF) into one common schema |
| **Prematch** | Rule-based fuzzy matching — clears exact matches, timing lags, rounding differences. Zero LLM cost. |
| **Triage** | Gemini classifies whatever's left — duplicate, missing entry, or genuine error — with a plain-English reason |
| **Verify** | Re-checks every auto-match against its category's tolerance. Never forces a match — anything that fails goes back to human review |
| **Ship** | Downloadable Excel report + live dashboard |

## What's Actually Built (not just planned)

Every item below has been tested end-to-end — not just written, run and verified:

- Multi-format ingestion: CSV, Excel, digital PDF, and OCR for scanned PDFs
- Rule-based matching engine with configurable thresholds
- Live Gemini-powered triage with real API integration
- Balance verification + a completeness audit (nothing silently dropped)
- Downloadable Excel reconciliation report
- A working Next.js dashboard, connected to the live backend

## Result on Test Data

On a 202-transaction test dataset: **91% auto-resolved**, 0 forced matches, every transaction accounted for.

## Tech Stack

FastAPI · pandas · RapidFuzz · Google Gemini (`gemini-3.6-flash`) · pdfplumber · Tesseract OCR · Next.js 14 · TypeScript · Tailwind CSS

## Links

| | |
|---|---|
| Live Deployment | `<ADD URL>` |
| GitHub Repository | `<ADD URL>` |

---

*See `README.md` for full setup instructions, `ARCHITECTURE.md` for pipeline internals, `API.md` for endpoint reference, and `TESTING.md` for the testing approach and bugs found along the way.*
