export interface Transaction {
  source: "bank" | "ledger";
  source_id: string;
  date: string;
  description: string;
  amount: number;
  reference: string;
}

export interface MatchResult {
  ledger_txn: Transaction | null;
  bank_txn: Transaction | null;
  status: "auto_matched" | "needs_review" | "unmatched";
  category:
    | "exact_match"
    | "timing_lag"
    | "rounding_difference"
    | "duplicate_entry"
    | "missing_entry"
    | "genuine_error"
    | "unknown";
  confidence: number;
  explanation: string;
}

export interface ReconcileSummary {
  ledger_rows: number;
  bank_rows: number;
  auto_matched_pairs: number;
  flagged_for_review: number;
  by_category: Record<string, number>;
}

export interface ReconcileHealth {
  complete: boolean;
  missing_ledger_ids: string[];
  missing_bank_ids: string[];
  ledger_total: number;
  bank_total: number;
  matched_ledger_total: number;
  matched_bank_total: number;
  matched_pair_balance_diff: number;
  flagged_ledger_total: number;
  flagged_bank_total: number;
  downgraded_on_verify: number;
}

export interface ReconcileResponse {
  summary: ReconcileSummary;
  health: ReconcileHealth;
  results: MatchResult[];
}