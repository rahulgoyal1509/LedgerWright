import { ReconcileResponse } from "./types";

// Point this at your running FastAPI backend (see backend/README.md).
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ledgerwright.onrender.com";

/**
 * Render free tier spins down after ~15 min of inactivity.
 * We ping /health to wake it up before sending the heavy multipart request.
 * Uses no-cors mode so the browser doesn't block the preflight on a GET.
 */
async function wakeServer(onWaking?: () => void): Promise<void> {
  // Try a quick health check — if it responds fast, server is already up
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 4000);
    const res = await fetch(`${API_BASE}/health`, {
      method: "GET",
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    if (res.ok) return; // already up, no wait needed
  } catch {
    // Server sleeping — notify user and wait
  }

  onWaking?.();

  // Poll /health every 3s until it responds (up to 90s)
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 3000));
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 5000);
      const res = await fetch(`${API_BASE}/health`, {
        method: "GET",
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      if (res.ok) return;
    } catch {
      // still sleeping
    }
  }
  // Don't throw — just proceed and let the main request fail naturally
}

export async function reconcile(
  ledgerFile: File,
  bankFile: File,
  onWaking?: () => void
): Promise<ReconcileResponse> {
  await wakeServer(onWaking);

  const form = new FormData();
  form.append("ledger_file", ledgerFile);
  form.append("bank_file", bankFile);

  // Give the actual reconcile request 3 minutes — the pipeline can take a while
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 180_000);

  try {
    const res = await fetch(`${API_BASE}/reconcile`, {
      method: "POST",
      body: form,
      signal: ctrl.signal,
    });
    clearTimeout(timer);

    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`Reconcile failed (${res.status}): ${detail}`);
    }

    return res.json();
  } catch (err: unknown) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error(
        "Request timed out after 3 minutes. The server may be overloaded — please try again."
      );
    }
    throw err;
  }
}

export function reportDownloadUrl(): string {
  return `${API_BASE}/reconcile/report`;
}

export { API_BASE };