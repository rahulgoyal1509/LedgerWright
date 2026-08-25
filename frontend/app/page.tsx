"use client";

import { useState } from "react";
import UploadForm from "@/components/UploadForm";
import SummaryCards from "@/components/SummaryCards";
import { AutoMatchedTable, FlaggedTable } from "@/components/ResultsTable";
import { reconcile } from "@/lib/api";
import { ReconcileResponse } from "@/lib/types";

export default function DashboardPage() {
  const [data, setData] = useState<ReconcileResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"auto" | "flagged">("flagged");

  async function handleReconcile(ledgerFile: File, bankFile: File) {
    setLoading(true);
    setError(null);
    try {
      const result = await reconcile(ledgerFile, bankFile);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <header className="mb-8">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white">✓</div>
          <h1 className="text-2xl font-semibold text-slate-900">LedgerWright</h1>
        </div>
        <p className="mt-1 text-slate-500">
          Upload a bank statement and a ledger export to reconcile them automatically.
        </p>
      </header>

      <UploadForm onReconcile={handleReconcile} loading={loading} />

      {error && (
        <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error} — is the backend running at{" "}
          <code>NEXT_PUBLIC_API_BASE</code> (default <code>http://127.0.0.1:8000</code>)?
        </div>
      )}

      {data && (
        <div className="mt-8 space-y-6">
          <SummaryCards summary={data.summary} health={data.health} />

          <div>
            <div className="mb-3 flex gap-2">
              <button
                onClick={() => setTab("flagged")}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                  tab === "flagged" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"
                }`}
              >
                Flagged for Review ({data.summary.flagged_for_review})
              </button>
              <button
                onClick={() => setTab("auto")}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                  tab === "auto" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"
                }`}
              >
                Auto-Matched ({data.summary.auto_matched_pairs})
              </button>
            </div>

            {tab === "flagged" ? <FlaggedTable results={data.results} /> : <AutoMatchedTable results={data.results} />}
          </div>
        </div>
      )}
    </main>
  );
}