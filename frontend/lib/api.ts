import { ReconcileResponse } from "./types";

// Point this at your running FastAPI backend (see backend/README.md).
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ledgerwright.onrender.com";

export async function reconcile(ledgerFile: File, bankFile: File): Promise<ReconcileResponse> {
  const form = new FormData();
  form.append("ledger_file", ledgerFile);
  form.append("bank_file", bankFile);

  const res = await fetch(`${API_BASE}/reconcile`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Reconcile failed (${res.status}): ${detail}`);
  }

  return res.json();
}

export function reportDownloadUrl(): string {
  // The actual download happens via a form POST from UploadForm,
  // since /reconcile/report needs the same two files re-sent as multipart.
  return `${API_BASE}/reconcile/report`;
}

export { API_BASE };