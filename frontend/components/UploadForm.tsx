"use client";

import { useState } from "react";
import { reportDownloadUrl } from "@/lib/api";

export default function UploadForm({
  onReconcile,
  loading,
}: {
  onReconcile: (ledger: File, bank: File) => void;
  loading: boolean;
}) {
  const [ledgerFile, setLedgerFile] = useState<File | null>(null);
  const [bankFile, setBankFile] = useState<File | null>(null);
  const [downloading, setDownloading] = useState(false);

  const canSubmit = ledgerFile && bankFile && !loading;

  async function handleDownloadReport() {
    if (!ledgerFile || !bankFile) return;
    setDownloading(true);
    try {
      const form = new FormData();
      form.append("ledger_file", ledgerFile);
      form.append("bank_file", bankFile);
      const res = await fetch(reportDownloadUrl(), { method: "POST", body: form });
      if (!res.ok) throw new Error(await res.text());

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "LedgerWright_Reconciliation_Report.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(`Report download failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6">
      <div className="grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Ledger export (CSV/Excel)</span>
          <input
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={(e) => setLedgerFile(e.target.files?.[0] ?? null)}
            className="mt-1 block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-brand-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-brand-700 hover:file:bg-brand-100"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Bank statement (CSV/Excel/PDF)</span>
          <input
            type="file"
            accept=".csv,.xlsx,.xls,.pdf"
            onChange={(e) => setBankFile(e.target.files?.[0] ?? null)}
            className="mt-1 block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-brand-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-brand-700 hover:file:bg-brand-100"
          />
        </label>
      </div>

      <div className="mt-4 flex gap-3">
        <button
          disabled={!canSubmit}
          onClick={() => ledgerFile && bankFile && onReconcile(ledgerFile, bankFile)}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Reconciling…" : "Reconcile"}
        </button>
        <button
          disabled={!ledgerFile || !bankFile || downloading}
          onClick={handleDownloadReport}
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {downloading ? "Preparing…" : "Download Excel Report"}
        </button>
      </div>
    </div>
  );
}