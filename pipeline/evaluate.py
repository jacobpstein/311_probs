"""Prior comparison via temporal holdout (docs/model_spec.md §7).

Train on the first 12 months, test on the remainder. Score every config in
model.CONFIGS with mean log-loss, RPS (primary, ordered bins), ECE on the two
headline cumulatives, and 90% CI coverage, all stratified by training-cell count.
Paired block bootstrap over tract x type cells gives SEs. Writes a results table
and the winning config id to docs/evaluation_results.md.
"""

import json
import os
import time

import numpy as np
import pandas as pd
from scipy.stats import beta

import model as M

ROOT = os.path.join(os.path.dirname(__file__), "..")
N_TYPES = 20
TRAIN_DAYS = 365


def load() -> tuple[pd.DataFrame, M.GeoIndex]:
    df = pd.read_parquet(os.path.join(ROOT, "data", "prepared.parquet"))
    geo_lookup = json.load(open(os.path.join(ROOT, "data", "geo_lookup.json")))
    df["created_date"] = pd.to_datetime(df["created_date"])
    for c in ["geoid", "nta", "boro", "complaint_type"]:
        df[c] = df[c].astype(str)
    return df, M.GeoIndex(geo_lookup)


def cumulative_A(a: np.ndarray, upto: int) -> np.ndarray:
    return a[..., :upto].sum(-1)


def predictions_for(fm: M.FittedModel, geo: M.GeoIndex, type_ix: dict,
                    test: pd.DataFrame) -> np.ndarray:
    """Per-test-request Dirichlet params from its tract x type cell (n_test, K)."""
    ti = test["ctype"].map(type_ix).to_numpy()
    gi = test["geoid"].map(geo.tract_ix)
    # tract-assigned rows -> tract posterior; unmapped -> borough posterior
    has_tract = gi.notna().to_numpy()
    gi_f = gi.fillna(0).astype(int).to_numpy()
    a = np.empty((len(test), M.K))
    a[has_tract] = fm.a_tract[gi_f[has_tract], ti[has_tract]]
    bi = test["boro"].map(geo.boro_ix).fillna(0).astype(int).to_numpy()
    a[~has_tract] = fm.a_boro[bi[~has_tract], ti[~has_tract]]
    return a


def score(a: np.ndarray, y: np.ndarray) -> dict:
    p = a / a.sum(1, keepdims=True)
    ll = -np.log(np.clip(p[np.arange(len(y)), y], 1e-12, None))
    P = p.cumsum(1)
    # RPS over cumulative up to K-1 cuts: sum_c (CDF_pred(c) - 1{y<=c})^2 / (K-1)
    ind_le = (np.arange(M.K)[None, :] >= y[:, None])  # 1{c >= y} == 1{y <= c}
    rps = ((P[:, :-1] - ind_le[:, :-1]) ** 2).sum(1) / (M.K - 1)
    return {"ll": ll, "rps": rps}


def ece(pred_cum: np.ndarray, hit: np.ndarray, nbins: int = 20) -> float:
    order = np.argsort(pred_cum)
    n = len(pred_cum)
    edges = np.linspace(0, n, nbins + 1).astype(int)
    e = 0.0
    for i in range(nbins):
        sl = order[edges[i]:edges[i + 1]]
        if len(sl) == 0:
            continue
        e += len(sl) / n * abs(pred_cum[sl].mean() - hit[sl].mean())
    return e


def evaluate_config(cfg: M.Config, train: pd.DataFrame, test: pd.DataFrame,
                    geo: M.GeoIndex, types: list[str], type_ix: dict,
                    t_ref: pd.Timestamp, train_cell_n: pd.Series):
    fm = M.fit(train, geo, types, cfg, t_ref)
    a = predictions_for(fm, geo, type_ix, test)
    y = test["bin"].to_numpy()
    s = score(a, y)

    # cumulative predictions for calibration
    p = a / a.sum(1, keepdims=True)
    P = p.cumsum(1)
    pred_24 = P[:, 1]   # P(<=24h) = bins 0,1
    pred_7d = P[:, 4]   # P(<=7d)  = bins 0..4
    hit_24 = (y <= 1).astype(float)
    hit_7d = (y <= 4).astype(float)

    # stratify by training-cell raw count
    cell_key = list(zip(test["geoid"], test["ctype"]))
    n_train = np.array([train_cell_n.get(k, 0) for k in cell_key])
    strata = {
        "all": np.ones(len(y), bool),
        "n=0": n_train == 0,
        "n<30": (n_train > 0) & (n_train < 30),
        "n>=30": n_train >= 30,
    }
    res = {"name": cfg.name, "kappa_table": fm.kappa_table}
    for sn, mask in strata.items():
        if mask.sum() == 0:
            continue
        res[f"ll_{sn}"] = float(s["ll"][mask].mean())
        res[f"rps_{sn}"] = float(s["rps"][mask].mean())
    res["ece_24"] = float(ece(pred_24, hit_24))
    res["ece_7d"] = float(ece(pred_7d, hit_7d))

    # 90% CI coverage on P(<=24h) for cells with >=50 test obs
    A = a.sum(1)
    Ac = cumulative_A(a, 2)
    lo = beta.ppf(0.05, Ac, A - Ac)
    hi = beta.ppf(0.95, Ac, A - Ac)
    tdf = pd.DataFrame({"key": cell_key, "hit24": hit_24, "lo": lo, "hi": hi})
    cov_rows = []
    for _, g in tdf.groupby("key"):
        if len(g) >= 50:
            emp = g["hit24"].mean()
            cov_rows.append(g["lo"].iloc[0] <= emp <= g["hi"].iloc[0])
    res["cov90"] = float(np.mean(cov_rows)) if cov_rows else float("nan")

    # per-request rps for bootstrap, keyed by cell (as flat string keys)
    key_str = np.array([f"{g}|{c}" for g, c in cell_key], dtype=object)
    return res, s["rps"], key_str


def paired_bootstrap(rps_by_cfg: dict, cell_keys: np.ndarray, best: str, B: int = 500):
    """Block bootstrap over cells; SE of each config's RPS and its diff vs best."""
    keys = pd.Series(cell_keys)
    groups = keys.groupby(keys).indices
    cell_list = list(groups.values())
    rng = np.random.default_rng(0)
    n = len(cell_keys)
    means = {c: [] for c in rps_by_cfg}
    diffs = {c: [] for c in rps_by_cfg}
    for _ in range(B):
        pick = rng.integers(0, len(cell_list), len(cell_list))
        idx = np.concatenate([cell_list[i] for i in pick])
        for c, r in rps_by_cfg.items():
            means[c].append(r[idx].mean())
        base = rps_by_cfg[best][idx].mean()
        for c, r in rps_by_cfg.items():
            diffs[c].append(r[idx].mean() - base)
    se = {c: float(np.std(means[c])) for c in means}
    dse = {c: float(np.std(diffs[c])) for c in diffs}
    return se, dse


def main() -> None:
    df, geo = load()
    d0 = df["created_date"].min()
    split = d0 + pd.Timedelta(days=TRAIN_DAYS)
    train = df[df["created_date"] < split].copy()
    test = df[df["created_date"] >= split].copy()
    print(f"train {len(train):,} ({d0.date()}..{split.date()}) | test {len(test):,}", flush=True)

    top_types = train["complaint_type"].value_counts().nlargest(N_TYPES).index.tolist()
    types = top_types + ["Other"]
    type_ix = {t: i for i, t in enumerate(types)}
    train["ctype"] = M.collapse_types(train["complaint_type"], top_types)
    test["ctype"] = M.collapse_types(test["complaint_type"], top_types)
    t_ref = split

    train_cell_n = train.groupby([train["geoid"], train["ctype"]], observed=True).size()
    train_cell_n.index = [tuple(k) for k in train_cell_n.index]
    train_cell_n = train_cell_n.to_dict()
    from collections import defaultdict
    tcn = defaultdict(int, train_cell_n)

    results, rps_by_cfg, cell_keys = [], {}, None
    for cfg in M.CONFIGS:
        t0 = time.time()
        r, rps, keys = evaluate_config(cfg, train, test, geo, types, type_ix, t_ref, tcn)
        results.append(r)
        rps_by_cfg[cfg.name] = rps
        cell_keys = keys
        print(f"{cfg.name:.<40} RPS={r['rps_all']:.5f} LL={r['ll_all']:.4f} "
              f"ECE24={r['ece_24']:.4f} cov={r['cov90']:.3f} ({time.time()-t0:.0f}s)", flush=True)

    best = min(results, key=lambda r: r["rps_all"])["name"]
    se, dse = paired_bootstrap(rps_by_cfg, cell_keys, best)

    write_report(results, se, dse, best, train, test, d0, split, types)
    json.dump({"best": best, "types": types},
              open(os.path.join(ROOT, "data", "winner.json"), "w"), indent=2)
    print(f"\nWINNER (lowest RPS): {best}", flush=True)


def write_report(results, se, dse, best, train, test, d0, split, types):
    funnel = json.load(open(os.path.join(ROOT, "data", "funnel.json")))
    lines = ["# Prior Comparison Results\n",
             f"_Generated {pd.Timestamp.now().date()}. "
             f"Train {d0.date()}–{split.date()} ({len(train):,} requests), "
             f"test {split.date()}–{test['created_date'].max().date()} "
             f"({len(test):,} requests)._\n",
             f"\n**Complaint types modeled ({len(types)}):** "
             + ", ".join(types) + "\n",
             "\n## Selection\n",
             f"\n**Winner (lowest overall RPS, guardrails in §7.4): `{best}`**\n",
             "\n## Results table\n",
             "\n| config | RPS all | ±SE | ΔRPS vs best | ±SE | LL all | LL n=0 | LL n<30 | LL n≥30 | RPS n<30 | ECE₂₄ₕ | ECE₇d | cov₉₀ |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda x: x["rps_all"]):
        n = r["name"]
        lines.append(
            f"| {n} | {r['rps_all']:.5f} | {se[n]:.5f} | "
            f"{r['rps_all']-min(x['rps_all'] for x in results):+.5f} | {dse[n]:.5f} | "
            f"{r['ll_all']:.4f} | {r.get('ll_n=0',float('nan')):.4f} | "
            f"{r.get('ll_n<30',float('nan')):.4f} | {r.get('ll_n>=30',float('nan')):.4f} | "
            f"{r.get('rps_n<30',float('nan')):.5f} | {r['ece_24']:.4f} | "
            f"{r['ece_7d']:.4f} | {r['cov90']:.3f} |")
    lines += ["\n## Cleaning funnel (§6)\n", "\n| step | rows |", "|---|---|"]
    for k, v in funnel.items():
        if isinstance(v, int):
            lines.append(f"| {k} | {v:,} |")
    # kappa table for the winner
    wtab = next(r["kappa_table"] for r in results if r["name"] == best)
    lines.append("\n## Estimated concentration κ (winner, by level & type)\n")
    lines.append("\n```json\n" + json.dumps(wtab, indent=2) + "\n```\n")
    open(os.path.join(ROOT, "docs", "evaluation_results.md"), "w").write("\n".join(lines))


if __name__ == "__main__":
    main()
