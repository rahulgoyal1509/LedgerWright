import { ReconcileResponse } from "./types";

// Point this at your running FastAPI backend (see backend/README.md).
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://ledgerwright.onrender.com";

/**
 * Render free tier spins down after ~15 min of inactivity.
 * First request can take 30-60s to wake up. We ping /health
 * repeatedly until it responds before sending the real payload.
 */
async function wakeServer(
  onWaking?: () => void,
  timeoutMs = 60_000,
  intervalMs = 3_000
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let notified = false;

  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${API_BASE}/health`, { method: "GET" });
      if (res.ok) return; // server is up
    } catch {
      // still sleeping — keep trying
    }
    if (!notified) {
      onWaking?.();
      notified = true;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(
    `Backend at ${API_BASE} did not respond within ${timeoutMs / 1000}s. ` +
    `It may still be starting up — please try again in a moment.`
  );
}

export async function reconcile(
  ledgerFile: File,
  bankFile: File,
  onWaking?: () => void
): Promise<ReconcileResponse> {
  // Wake the server first (no-op if already running)
  await wakeServer(onWaking);

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
  return `${API_BASE}/reconcile/report`;
}

export { API_BASE };