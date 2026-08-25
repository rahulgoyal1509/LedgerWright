import { ReconcileHealth, ReconcileSummary } from "@/lib/types";

const CATEGORY_LABELS: Record<string, string> = {
  exact_match: "Exact Match",
  timing_lag: "Timing Lag",
  rounding_difference: "Rounding",
  duplicate_entry: "Duplicate",
  missing_entry: "Missing Entry",
  genuine_error: "Needs Review",
  unknown: "Unknown",
};

function Card({ label, value, tone = "default" }: { label: string; value: string | number; tone?: "default" | "good" | "warn" }) {
  const toneClasses = {
    default: "bg-white border-slate-200",
    good: "bg-emerald-50 border-emerald-200",
    warn: "bg-amber-50 border-amber-200",
  }[tone];

  return (
    <div className={`rounded-xl border p-4 ${toneClasses}`}>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
    </div>
  );
}

export default function SummaryCards({
  summary,
  health,
}: {
  summary: ReconcileSummary;
  health: ReconcileHealth;
}) {
  const totalRows = summary.ledger_rows + summary.bank_rows;
  const autoPct = Math.round((100 * (summary.auto_matched_pairs * 2)) / totalRows);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card label="Ledger Rows" value={summary.ledger_rows} />
        <Card label="Bank Rows" value={summary.bank_rows} />
        <Card label="Auto-Matched Pairs" value={summary.auto_matched_pairs} tone="good" />
        <Card label="Flagged for Review" value={summary.flagged_for_review} tone={summary.flagged_for_review > 0 ? "warn" : "good"} />
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card label="Auto-Resolved" value={`${autoPct}%`} tone="good" />
        <Card label="Balance Diff (matched)" value={`₹${health.matched_pair_balance_diff.toFixed(2)}`} />
        <Card
          label="Every Row Accounted For"
          value={health.complete ? "Yes ✅" : "No ⚠️"}
          tone={health.complete ? "good" : "warn"}
        />
        <Card
          label="Forced Matches Rejected"
          value={health.downgraded_on_verify}
          tone={health.downgraded_on_verify === 0 ? "good" : "warn"}
        />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
          By Category
        </div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(summary.by_category).map(([category, count]) => (
            <span key={category} className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700">
              {CATEGORY_LABELS[category] ?? category}: <strong>{count}</strong>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}