"""Rolling-origin evaluation that mirrors how the deployed map is used.

At the start of each test month the model is refit on everything before that
month (decay anchored at the month start, exactly like a refresh) and scored on
that month's requests only. This measures near-term prediction - the deployed
setting - unlike the single 12-month-ahead split in evaluate.py, which penalizes
short-memory (fast-decay) configurations on the later test months.

Compares the shipped cutwise model with the nine-bin cascade, decay half-lives and same-season-last-year blending, reports overall and
per-month RPS / log-loss, and a paired block bootstrap (over tract x type cells)
of each config's RPS difference from the shipped reference.

Writes docs/rolling_evaluation.md.
"""

import json
import os
import sys

import numpy as np
import pandas as pd

import model as M

ROOT = os.path.join(os.path.dirname(__file__), "..")
REFERENCE = "cutwise h=90d (shipped)"
MIN_TRAIN_DAYS = 365          # only score months with at least this much history

CONFIGS = [
    M.Config("h=45d", half_life_days=45.0),
    M.Config("h=60d", half_life_days=60.0),
    M.Config("h=90d", half_life_days=90.0),
    M.Config(REFERENCE, half_life_days=90.0, cutwise=True),
    M.Config("cutwise h=180d", half_life_days=180.0, cutwise=True),
    M.Config("cutwise h=45d", half_life_days=45.0, cutwise=True),
    M.Config("h=120d", half_life_days=120.0),
    M.Config("h=180d", half_life_days=180.0),
    M.Config("h=365d", half_life_days=365.0),
    M.Config("no decay", half_life_days=None),
    M.Config("h=90d + season b=0.5", half_life_days=90.0, seasonal_beta=0.5),
    M.Config("h=90d + season b=1.0", half_life_days=90.0, seasonal_beta=1.0),
    M.Config("h=180d + season b=0.5", half_life_days=180.0, seasonal_beta=0.5),
    M.Config("h=90d + sibling-only prior", half_life_days=90.0, loo_parent=True),
]


def load():
    df = pd.read_parquet(os.path.join(ROOT, "data", "prepared.parquet"))
    df["created_date"] = pd.to_datetime(df["created_date"])
    for c in ["geoid", "nta", "boro", "complaint_type"]:
        df[c] = df[c].astype("object")   # keep missing tract IDs missing (see statistical_review.md s.7)
    geo = M.GeoIndex(json.load(open(os.path.join(ROOT, "data", "geo_lookup.json"))))
    types = json.load(open(os.path.join(ROOT, "pipeline", "types.json")))["types"]
    df["ctype"] = M.collapse_types(df["complaint_type"], types)
    return df, geo, types + ["Other"]


def score(fm, sub, geo, tix):
    ti = sub["ctype"].map(tix).to_numpy()
    gi = sub["geoid"].map(geo.tract_ix)
    ok = gi.notna().to_numpy()
    gi = gi.fillna(0).astype(int).to_numpy()
    a = np.empty((len(sub), M.K))
    a[ok] = fm.bin_probs_tract()[gi[ok], ti[ok]]
    bi = sub["boro"].map(geo.boro_ix).fillna(0).astype(int).to_numpy()
    a[~ok] = fm.bin_probs_boro()[bi[~ok], ti[~ok]]
    p = a / a.sum(1, keepdims=True)
    P = p.cumsum(1)
    y = sub["bin"].to_numpy()
    ind = np.arange(M.K)[None, :] >= y[:, None]
    rps = ((P[:, :-1] - ind[:, :-1]) ** 2).sum(1) / (M.K - 1)
    ll = -np.log(np.clip(p[np.arange(len(y)), y], 1e-12, None))
    return rps, ll


def main() -> None:
    df, geo, types = load()
    tix = {t: i for i, t in enumerate(types)}
    d0 = df["created_date"].min()
    end = df["created_date"].max()
    months = [m for m in pd.date_range(d0.normalize().replace(day=1) + pd.offsets.MonthBegin(1),
                                       end, freq="MS")
              if (m - d0).days >= MIN_TRAIN_DAYS and m + pd.offsets.MonthBegin(1) <= end + pd.Timedelta(days=1)]
    print(f"window {d0.date()}..{end.date()} | scoring {len(months)} months: "
          f"{months[0].strftime('%Y-%m')}..{months[-1].strftime('%Y-%m')}", flush=True)

    per = {c.name: {"rps": [], "ll": [], "keys": []} for c in CONFIGS}
    month_rows = []
    for m in months:
        m_end = m + pd.offsets.MonthBegin(1)
        train = df[df["created_date"] < m]
        test = df[(df["created_date"] >= m) & (df["created_date"] < m_end)]
        keys = (test["geoid"].fillna("NA").astype(str) + "|" + test["ctype"]).to_numpy()
        for cfg in CONFIGS:
            fm = M.fit(train, geo, types, cfg, m)
            rps, ll = score(fm, test, geo, tix)
            per[cfg.name]["rps"].append(rps); per[cfg.name]["ll"].append(ll)
            per[cfg.name]["keys"].append(keys)
            month_rows.append((cfg.name, m.strftime("%Y-%m"), rps.mean(), ll.mean(), len(test)))
        print(f"  scored {m.strftime('%Y-%m')} ({len(test):,} requests)", flush=True)

    cat = {n: {k: np.concatenate(v[k]) for k in v} for n, v in per.items()}
    base = cat[REFERENCE]
    groups = list(pd.Series(base["keys"]).groupby(pd.Series(base["keys"])).indices.values())
    rng = np.random.default_rng(0)
    picks = [np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
             for _ in range(300)]
    rows = []
    for c in CONFIGS:
        d_rps = cat[c.name]["rps"] - base["rps"]
        d_ll = cat[c.name]["ll"] - base["ll"]
        se_rps = float(np.std([d_rps[ix].mean() for ix in picks]))
        se_ll = float(np.std([d_ll[ix].mean() for ix in picks]))
        rows.append((c.name, cat[c.name]["rps"].mean(), d_rps.mean(), se_rps,
                     cat[c.name]["ll"].mean(), d_ll.mean(), se_ll))
        print(f"{c.name:<26} RPS={rows[-1][1]:.5f}  Δ={rows[-1][2]:+.5f}±{se_rps:.5f}   "
              f"LL={rows[-1][4]:.4f}  Δ={rows[-1][5]:+.5f}±{se_ll:.5f}", flush=True)

    mt = pd.DataFrame(month_rows, columns=["config", "month", "rps", "ll", "n"])
    piv = mt.pivot(index="month", columns="config", values="rps")[[c.name for c in CONFIGS]]
    lines = ["# Rolling-origin evaluation\n",
             f"_Generated {pd.Timestamp.now().date()} on data {d0.date()}..{end.date()}. "
             f"Each month is scored by a model refit on all earlier data ({len(months)} months: "
             f"{months[0].strftime('%Y-%m')}..{months[-1].strftime('%Y-%m')}). "
             f"Differences are versus `{REFERENCE}`; lower is better; ± is the paired "
             f"block-bootstrap SE over tract × type cells._\n",
             "\n| config | RPS | ΔRPS | ±SE | log-loss | ΔLL | ±SE |", "|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r[1]):
        lines.append(f"| {r[0]} | {r[1]:.5f} | {r[2]:+.5f} | {r[3]:.5f} | {r[4]:.4f} | {r[5]:+.5f} | {r[6]:.5f} |")
    lines += ["\n## RPS by month\n", "| month | " + " | ".join(piv.columns) + " |",
              "|---|" + "---|" * len(piv.columns)]
    for mon, row in piv.iterrows():
        lines.append(f"| {mon} | " + " | ".join(f"{v:.5f}" for v in row) + " |")
    open(os.path.join(ROOT, "docs", "rolling_evaluation.md"), "w").write("\n".join(lines) + "\n")
    print("wrote docs/rolling_evaluation.md", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
