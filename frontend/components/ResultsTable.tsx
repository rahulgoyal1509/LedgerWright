import { MatchResult } from "@/lib/types";

const CATEGORY_STYLES: Record<string, string> = {
  exact_match: "bg-emerald-100 text-emerald-700",
  timing_lag: "bg-sky-100 text-sky-700",
  rounding_difference: "bg-violet-100 text-violet-700",
  duplicate_entry: "bg-amber-100 text-amber-700",
  missing_entry: "bg-orange-100 text-orange-700",
  genuine_error: "bg-rose-100 text-rose-700",
  unknown: "bg-slate-100 text-slate-700",
};

function CategoryBadge({ category }: { category: string }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${CATEGORY_STYLES[category] ?? "bg-slate-100 text-slate-700"}`}>
      {category.replace(/_/g, " ")}
    </span>
  );
}

function fmtAmount(n: number | undefined | null) {
  if (n === undefined || n === null) return "—";
  return `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

export function AutoMatchedTable({ results }: { results: MatchResult[] }) {
  const rows = results.filter((r) => r.status === "auto_matched");
  if (rows.length === 0) return <p className="text-sm text-slate-500">No auto-matched pairs.</p>;

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            <th className="px-4 py-2 text-left font-medium text-slate-600">Category</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600">Ledger</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600">Bank</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600">Explanation</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => (
            <tr key={i}>
              <td className="px-4 py-2"><CategoryBadge category={r.category} /></td>
              <td className="px-4 py-2 text-slate-700">
                {r.ledger_txn?.description} <span className="text-slate-400">({fmtAmount(r.ledger_txn?.amount)})</span>
              </td>
              <td className="px-4 py-2 text-slate-700">
                {r.bank_txn?.description} <span className="text-slate-400">({fmtAmount(r.bank_txn?.amount)})</span>
              </td>
              <td className="px-4 py-2 text-slate-500">{r.explanation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FlaggedTable({ results }: { results: MatchResult[] }) {
  const rows = results.filter((r) => r.status === "needs_review");
  if (rows.length === 0) return <p className="text-sm text-slate-500">Nothing flagged — everything auto-resolved.</p>;

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            <th className="px-4 py-2 text-left font-medium text-slate-600">Category</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600">Source</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600">Transaction</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600">Confidence</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600">Why it's flagged</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => {
            const txn = r.ledger_txn ?? r.bank_txn;
            return (
              <tr key={i}>
                <td className="px-4 py-2"><CategoryBadge category={r.category} /></td>
                <td className="px-4 py-2 capitalize text-slate-600">{txn?.source}</td>
                <td className="px-4 py-2 text-slate-700">
                  {txn?.description} <span className="text-slate-400">({fmtAmount(txn?.amount)})</span>
                </td>
                <td className="px-4 py-2 text-slate-600">{Math.round(r.confidence * 100)}%</td>
                <td className="px-4 py-2 text-slate-500">{r.explanation}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}