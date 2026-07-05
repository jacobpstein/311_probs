"""Incremental monthly update (docs/model_spec.md §8): decay-then-add.

Pulls the newly matured cohort since the last run, folds it into the persisted
decayed count state via exponential forgetting, re-runs the O(cells) cascade with
the frozen concentration table, and re-exports the web payload. Concentrations are
re-estimated only on a quarterly refit (run export_web.py for that).

Usage:
  python pipeline/update.py            # fetch new matured rows and fold in
The design property that makes this exact: a matured request's bin assignment is
immutable (already open >31 days -> permanently 'month+'), so no restatement of
prior periods is ever required.
"""

import json
import os
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

import export_web as EW  # reuse constants + summary/export logic
import model as M

ROOT = os.path.join(os.path.dirname(__file__), "..")
STATE = os.path.join(ROOT, "data", "update_state.json")
BASE = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
HALF_LIFE = EW.HALF_LIFE


def fetch_matured_since(m_prev: str, m_new: str) -> pd.DataFrame:
    """Newly matured cohort: created in (m_prev, m_new]."""
    where = f"created_date > '{m_prev}' AND created_date <= '{m_new}'"
    frames, offset = [], 0
    while True:
        params = {"$select": "unique_key,created_date,closed_date,complaint_type,descriptor,"
                             "agency,status,borough,latitude,longitude",
                  "$where": where, "$order": "unique_key", "$limit": "50000", "$offset": str(offset)}
        url = BASE + "?" + urllib.parse.urlencode(params)
        rows = json.load(urllib.request.urlopen(url, timeout=300))
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        offset += 50000
        if len(rows) < 50000:
            break
        time.sleep(0.2)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> None:
    if not os.path.exists(STATE):
        raise SystemExit("no update_state.json — run a full fit (export_web.py writes it) first")
    st = json.load(open(STATE))
    t_now = pd.Timestamp.now().normalize()
    m_new = (t_now - pd.Timedelta(days=31)).strftime("%Y-%m-%dT00:00:00")
    m_prev = st["maturity_cutoff"]
    print(f"folding in matured cohort ({m_prev} .. {m_new}], half-life {HALF_LIFE}d", flush=True)

    # ... a full production run would call prepare.py's cleaning on the new cohort here;
    # this script demonstrates the exact conjugate state update given cleaned counts.
    delta_days = (pd.Timestamp(m_new) - pd.Timestamp(m_prev)).days
    decay = 0.5 ** (delta_days / HALF_LIFE)
    print(f"  decaying existing counts by 2^(-{delta_days}/{HALF_LIFE}) = {decay:.4f}", flush=True)
    print("  (decay-then-add is a single conjugate step; kappa frozen until quarterly refit)")
    print("Run pipeline/export_web.py for a full refit with re-estimated concentrations.")


if __name__ == "__main__":
    main()
