"""
Single source of truth for matching/verification tolerances.

Defaults come from environment variables (set in .env, same pattern as
GEMINI_API_KEY) so thresholds can be tuned without a code change. They can
also be overridden per-request via the /reconcile and /reconcile/report
API parameters, which take priority over the environment defaults.

Previously these tolerances were hardcoded separately in fuzzy_matcher.py
(the matching stage) and verify.py (the verification stage) — two places
that had to be kept manually in sync, which is exactly the kind of thing
that quietly drifts apart over time. Now both read from here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    return float(val) if val not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val not in (None, "") else default


@dataclass(frozen=True)
class MatchingConfig:
    # A same-amount pair is a TIMING_LAG match if the bank cleared it within
    # this many days of the ledger entry (0-1 days apart is EXACT instead).
    max_timing_lag_days: int = 10

    # A pair is a ROUNDING match if the amounts differ by no more than
    # max(rounding_abs_tolerance, rounding_pct_tolerance * amount).
    rounding_abs_tolerance: float = 1.0
    rounding_pct_tolerance: float = 0.005


def get_matching_config(overrides: dict | None = None) -> MatchingConfig:
    """
    Build the active config: environment defaults, with any explicitly
    provided overrides (e.g. from an API request) taking priority.
    """
    base = MatchingConfig(
        max_timing_lag_days=_env_int("MAX_TIMING_LAG_DAYS", 10),
        rounding_abs_tolerance=_env_float("ROUNDING_ABS_TOLERANCE", 1.0),
        rounding_pct_tolerance=_env_float("ROUNDING_PCT_TOLERANCE", 0.005),
    )
    if not overrides:
        return base

    clean = {k: v for k, v in overrides.items() if v is not None}
    return MatchingConfig(**{**base.__dict__, **clean})