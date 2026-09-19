"""Sanity-gate the exported web payload before it is published.

Exits non-zero (blocking the scheduled refresh from committing) if the export
looks wrong: stale data, a truncated pull, missing tracts, or posteriors that
violate basic invariants. Run after export_web.py:

    python pipeline/validate_export.py
"""

import json
import os
import sys
from datetime import date

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
WEB = os.path.join(ROOT, "web", "data")

MAX_AGE_DAYS = 50        # fetch END is today-31d, so data_through is ~31d old when fresh
MIN_REQUESTS = 3_000_000  # two years is ~7M; far below this means a truncated pull
N_TRACTS = 2325
TOL = 0.003              # exports are rounded to 3 decimals

failures: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("PASS  " if ok else "FAIL  ") + msg, flush=True)
    if not ok:
        failures.append(msg)


def main() -> None:
    meta = json.load(open(os.path.join(WEB, "meta.json")))
    probs = json.load(open(os.path.join(WEB, "probs.json")))
    m = meta["model"]

    age = (date.today() - date.fromisoformat(m["data_through"])).days
    check(age <= MAX_AGE_DAYS, f"data is fresh: through {m['data_through']} ({age} days old, max {MAX_AGE_DAYS})")
    check(m["n_requests"] >= MIN_REQUESTS, f"request volume plausible: {m['n_requests']:,} (min {MIN_REQUESTS:,})")
    check(len(probs) == N_TRACTS, f"all tracts present: {len(probs)} (expected {N_TRACTS})")
    check(len(meta["types"]) >= 15, f"complaint types present: {len(meta['types'])}")

    bad_sum = bad_mono = bad_ci = bad_sw = n = 0
    for cells in probs.values():
        for c in cells.values():
            n += 1
            bp, lo, hi = np.array(c["bp"]), np.array(c["lo"]), np.array(c["hi"])
            cum = bp.cumsum()[:-1]
            bad_sum += abs(bp.sum() - 1) > 0.006
            bad_mono += bool(np.any(np.diff(cum) < -1e-9))
            bad_ci += bool(np.any(lo > cum + TOL) or np.any(hi < cum - TOL))
            bad_sw += not (0 <= c["sw"] <= 1)
    check(bad_sum == 0, f"bin probabilities sum to 1 in all {n:,} cells")
    check(bad_mono == 0, "cumulative probabilities monotone in all cells")
    check(bad_ci == 0, "interval bounds bracket the posterior mean in all cells")
    check(bad_sw == 0, "shrinkage weights within [0, 1]")

    p24 = meta["refs"]["city"]["ALL"][1]
    check(0.30 <= p24 <= 0.80, f"citywide P(resolved within 24h) plausible: {p24:.3f}")

    print(f"\n{'FAILED: ' + str(len(failures)) + ' check(s)' if failures else 'ALL CHECKS PASSED'}", flush=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
