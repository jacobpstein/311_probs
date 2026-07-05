"""Rolling-monthly test of same-season-last-year blending.

RESULT (run 2026-07, one prior year of history): no adoption. Overall paired RPS
difference vs the shipped P5a was -0.00001 +/- 0.00008 (null) for the best variant,
and slightly negative for heavier blends; gains on strongly seasonal types were
~0.3% relative and inconsistent across months. With a single prior year, the
same-season kernel adds one noisy replicate that also carries that year's
idiosyncrasies, and the 90-day recency window already captures mid-season behavior.
Revisit once 2+ full years of matured history exist (kernel is available via
Config.seasonal_beta / seasonal_bw_days).

For each 2026 test month m: fit on all matured data created before m (t_ref = m start,
exactly as the deployed monthly refresh would), predict month m's requests. Compare
P5a (recency only) against seasonal blends. Report RPS/LL overall, per month, and for
strongly seasonal types; paired cell-block bootstrap SE on the overall RPS difference.
"""
import os
import sys, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import model as M

ROOT = os.path.join(os.path.dirname(__file__), "..")
df = pd.read_parquet(f"{ROOT}/data/prepared.parquet")
df["created_date"] = pd.to_datetime(df["created_date"])
for c in ["geoid", "nta", "boro", "complaint_type"]:
    df[c] = df[c].astype(str)
df.loc[df["geoid"].isin(["nan", "None"]), "geoid"] = np.nan
geo = M.GeoIndex(json.load(open(f"{ROOT}/data/geo_lookup.json")))

# frozen type list from the pre-2026 period (consistent across months/configs)
top = df[df["created_date"] < "2026-01-01"]["complaint_type"].value_counts().nlargest(20).index.tolist()
types = top + ["Other"]
tix = {t: i for i, t in enumerate(types)}
df["ctype"] = M.collapse_types(df["complaint_type"], top)

SEASONAL_TYPES = ["HEAT/HOT WATER", "Snow or Ice", "PLUMBING", "Water System"]

CFGS = [
    M.Config("P5a  recency only (shipped)", half_life_days=90.0),
    M.Config("P6a  + seasonal b=0.5 bw=45d", half_life_days=90.0, seasonal_beta=0.5),
    M.Config("P6b  + seasonal b=1.0 bw=45d", half_life_days=90.0, seasonal_beta=1.0),
    M.Config("P6c  + seasonal b=0.5 bw=90d", half_life_days=90.0, seasonal_beta=0.5, seasonal_bw_days=90.0),
]

months = pd.date_range("2026-01-01", "2026-06-01", freq="MS")

def score(fm, sub):
    ti = sub["ctype"].map(tix).to_numpy()
    gi = sub["geoid"].map(geo.tract_ix)
    ok = gi.notna().to_numpy()
    gi = gi.fillna(0).astype(int).to_numpy()
    a = np.empty((len(sub), M.K))
    a[ok] = fm.a_tract[gi[ok], ti[ok]]
    bi = sub["boro"].map(geo.boro_ix).fillna(0).astype(int).to_numpy()
    a[~ok] = fm.a_boro[bi[~ok], ti[~ok]]
    p = a / a.sum(1, keepdims=True)
    P = p.cumsum(1)
    y = sub["bin"].to_numpy()
    ind = (np.arange(M.K)[None, :] >= y[:, None])
    rps = ((P[:, :-1] - ind[:, :-1]) ** 2).sum(1) / (M.K - 1)
    ll = -np.log(np.clip(p[np.arange(len(y)), y], 1e-12, None))
    return rps, ll

rows = []            # per (config, month) means
req = {}             # per config: concatenated per-request rps + keys for bootstrap
for cfg in CFGS:
    all_rps, all_ll, all_keys, all_seas = [], [], [], []
    for m in months:
        m_end = m + pd.offsets.MonthBegin(1)
        train = df[df["created_date"] < m]
        test = df[(df["created_date"] >= m) & (df["created_date"] < m_end)]
        fm = M.fit(train.copy(), geo, types, cfg, m)
        rps, ll = score(fm, test)
        seas = test["ctype"].isin(SEASONAL_TYPES).to_numpy()
        rows.append((cfg.name, str(m.date())[:7], rps.mean(), ll.mean(),
                     rps[seas].mean(), len(test)))
        all_rps.append(rps); all_ll.append(ll); all_seas.append(seas)
        all_keys.append((test["geoid"].fillna("NA") + "|" + test["ctype"]).to_numpy())
    req[cfg.name] = (np.concatenate(all_rps), np.concatenate(all_ll),
                     np.concatenate(all_seas), np.concatenate(all_keys))
    r = req[cfg.name]
    print(f"{cfg.name:<32} RPS={r[0].mean():.5f}  LL={r[1].mean():.4f}  "
          f"RPS(seasonal types)={r[0][r[2]].mean():.5f}", flush=True)

# paired cell bootstrap of overall RPS diff vs P5a
base = CFGS[0].name
keys = pd.Series(req[base][3])
groups = list(keys.groupby(keys).indices.values())
rng = np.random.default_rng(0)
print("\npaired bootstrap (500 draws over tract x type cells), RPS diff vs shipped P5a:")
for cfg in CFGS[1:]:
    diffs = []
    d_req = req[cfg.name][0] - req[base][0]
    for _ in range(500):
        pick = rng.integers(0, len(groups), len(groups))
        idx = np.concatenate([groups[i] for i in pick])
        diffs.append(d_req[idx].mean())
    print(f"  {cfg.name:<32} d={d_req.mean():+.5f}  SE={np.std(diffs):.5f}")

print("\nper-month RPS by config:")
tab = pd.DataFrame(rows, columns=["cfg", "month", "rps", "ll", "rps_seas", "n"])
print(tab.pivot(index="month", columns="cfg", values="rps").round(5).to_string())
print("\nper-month RPS on seasonal types only:")
print(tab.pivot(index="month", columns="cfg", values="rps_seas").round(5).to_string())
