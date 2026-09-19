"""End-to-end audit of the shipped map data against the raw 311 files.

Independent of the production estimator: its own count accumulation (pandas
groupby, not np.add.at), its own concentration search (dense grid + refinement,
not scipy's bounded optimizer), its own per-threshold hierarchy and monotone/floor
rules, and the Dirichlet-Multinomial likelihood checked against scipy.stats.dirichlet_multinomial. Every tract x type cell is compared,
not a sample.

    python pipeline/audit.py

Requires data/raw, data/prepared.parquet, data/funnel.json (from the pipeline)
and the export in web/data. Exits non-zero if any check fails.
"""

import glob
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.special import gammaln
from scipy.stats import dirichlet_multinomial

ROOT = os.path.join(os.path.dirname(__file__), "..")
K = 9
EDGES_H = [3, 24, 48, 72, 168, 336, 480, 744]
failures = []


def check(ok: bool, msg: str) -> None:
    print(("PASS  " if ok else "FAIL  ") + msg, flush=True)
    if not ok:
        failures.append(msg)


def info(msg: str) -> None:
    print("INFO  " + msg, flush=True)


# ---------------------------------------------------------------- 1. conservation
def conservation(prep, probs, meta, types_named, lookup):
    print("\n[1] Row and count conservation", flush=True)
    funnel = json.load(open(os.path.join(ROOT, "data", "funnel.json")))
    raw_rows = 0
    for f in glob.glob(os.path.join(ROOT, "data", "raw", "sr_*.csv")):
        with open(f, "rb") as fh:
            raw_rows += sum(1 for _ in fh) - 1
    check(raw_rows == funnel["raw rows"], f"raw CSV rows {raw_rows:,} == funnel raw {funnel['raw rows']:,}")
    check(len(prep) == funnel["after geography filter"],
          f"prepared rows {len(prep):,} == funnel after geography filter {funnel['after geography filter']:,}")
    check(int(prep["geoid"].notna().sum()) == funnel["tract_assigned"],
          f"tract-assigned rows {int(prep['geoid'].notna().sum()):,} == funnel {funnel['tract_assigned']:,}")
    check(len(prep) == meta["model"]["n_requests"], "export n_requests == prepared rows")

    ct = prep["complaint_type"].where(prep["complaint_type"].isin(types_named), "Other")
    sub = prep[prep["geoid"].notna()]
    cnt = sub.groupby([sub["geoid"], ct[sub.index]]).size()
    bad = 0
    cells = len(probs) * len(next(iter(probs.values())))
    # expected counts per tract x type, from the prepared rows
    exp = cnt.unstack(fill_value=0)
    for g, cell in probs.items():
        row = exp.loc[g] if g in exp.index else None
        tot = 0
        for t, c in cell.items():
            if t == "ALL":
                continue
            e = int(row[t]) if (row is not None and t in row.index) else 0
            tot += e
            bad += (c["n"] != e)
        bad += (cell["ALL"]["n"] != tot)
    check(bad == 0, f"raw counts n match independent tallies in all {cells:,} cells (mismatches: {bad})")


# ---------------------------------------------------------------- 2. binning
def binning():
    print("\n[2] Duration binning at the boundaries", flush=True)
    edges = np.array(EDGES_H, dtype=float)
    prod = lambda d: np.searchsorted(edges, d, side="left")           # expression used in prepare.py
    indep = lambda d: (d[:, None] > edges[None, :]).sum(1)            # bin = number of edges strictly exceeded
    d = np.concatenate([np.array(EDGES_H, float), np.array(EDGES_H, float) + 1e-9,
                        np.array(EDGES_H, float) - 1e-9, [1e-6, 1e6, 1 / 3600],
                        np.random.default_rng(0).uniform(0, 1000, 1_000_000)])
    check(np.array_equal(prod(d), indep(d)), f"searchsorted binning == 'edges exceeded' on {len(d):,} durations incl. exact edges")
    check(prod(np.array([3.0]))[0] == 0 and prod(np.array([24.0]))[0] == 1 and prod(np.array([744.0]))[0] == 7
          and prod(np.array([744.0001]))[0] == 8, "exactly 3h -> bin 1, 24h -> bin 2, 31d -> bin 8, just over 31d -> bin 9")


# ---------------------------------------------------------------- 3. likelihood formula
def likelihood_formula():
    print("\n[3] Dirichlet-Multinomial likelihood used for pooling strength", flush=True)
    rng = np.random.default_rng(1)
    n = rng.integers(0, 40, size=(30, K)); m = rng.dirichlet(np.ones(K), size=30)

    def ll(k):  # production formula (constant multinomial coefficient omitted)
        km = k * m
        return (gammaln(k) - gammaln(n.sum(1) + k) + (gammaln(n + km) - gammaln(km)).sum(1)).sum()

    def ref(k):
        return sum(dirichlet_multinomial.logpmf(n[i], k * m[i], int(n[i].sum())) for i in range(len(n)))

    diffs = [ll(k) - ref(k) for k in (0.7, 5.0, 60.0, 900.0)]
    check(np.ptp(diffs) < 1e-8, f"formula differs from scipy's logpmf by a constant in kappa (spread {np.ptp(diffs):.1e})")


# ---------------------------------------------------------------- 4. independent cascade
def fit_kappa_grid(n, m):
    keep = n.sum(1) >= 1
    n, m = n[keep], m[keep]
    if (n.sum(1) >= 5).sum() < 8:
        return None
    nj = n.sum(1)
    grid = np.exp(np.linspace(np.log(0.5), np.log(5000.0), 240))
    ll = np.array([(gammaln(k) - gammaln(nj + k) + (gammaln(n + np.clip(k * m, 1e-12, None)) - gammaln(np.clip(k * m, 1e-12, None))).sum(1)).sum() for k in grid])
    i = int(np.argmax(ll))
    lo, hi = grid[max(i - 1, 0)], grid[min(i + 1, len(grid) - 1)]
    fine = np.exp(np.linspace(np.log(lo), np.log(hi), 200))
    llf = np.array([(gammaln(k) - gammaln(nj + k) + (gammaln(n + np.clip(k * m, 1e-12, None)) - gammaln(np.clip(k * m, 1e-12, None))).sum(1)).sum() for k in fine])
    return float(fine[int(np.argmax(llf))])


def cascade(prep, probs, meta, types_named, lookup, half_life=90.0):
    print("\n[4] Independent re-implementation of the per-threshold hierarchies (all cells)", flush=True)
    types = types_named + ["Other"]; T = len(types)
    tracts = sorted(lookup); tix = {g: i for i, g in enumerate(tracts)}
    ntas = sorted({v["nta"] for v in lookup.values()}); nix = {a: i for i, a in enumerate(ntas)}
    boros = sorted({v["boro"] for v in lookup.values()}); bix = {b: i for i, b in enumerate(boros)}
    t_nta = np.array([nix[lookup[g]["nta"]] for g in tracts])
    n_boro = np.zeros(len(ntas), int)
    for g in tracts:
        n_boro[nix[lookup[g]["nta"]]] = bix[lookup[g]["boro"]]

    ct = prep["complaint_type"].where(prep["complaint_type"].isin(types_named), "Other")
    tcode = ct.map({t: i for i, t in enumerate(types)}).to_numpy()
    t_ref = prep["created_date"].max()
    w = np.exp2(-((t_ref - prep["created_date"]).dt.total_seconds().to_numpy() / 86400.0) / half_life)
    b = prep["bin"].to_numpy().astype(int)
    has = prep["geoid"].notna().to_numpy()

    def dense(index_codes, n_nodes, mask):
        df = pd.DataFrame({"i": index_codes[mask], "t": tcode[mask], "b": b[mask], "w": w[mask]})
        g = df.groupby(["i", "t", "b"], sort=False)["w"].sum()
        out = np.zeros((n_nodes, T + 1, K))
        idx = g.index.to_frame(index=False).to_numpy()
        out[idx[:, 0], idx[:, 1], idx[:, 2]] = g.to_numpy()
        out[:, T, :] = out[:, :T, :].sum(1)
        return out

    g_code = prep["geoid"].map(tix).to_numpy(dtype=float)
    g_code = np.where(has, g_code, 0).astype(int)
    C_t = dense(g_code, len(tracts), has)
    C_a = dense(t_nta[g_code], len(ntas), has)
    boro_code = prep["boro"].map(bix).to_numpy(dtype=float)
    hasb = ~np.isnan(boro_code)
    C_b = dense(np.where(hasb, boro_code, 0).astype(int), len(boros), hasb)
    C_c = dense(np.zeros(len(prep), int), 1, np.ones(len(prep), bool))

    norm = lambda x: x / x.sum(-1, keepdims=True)

    def merge(C, c):                       # two categories: bins <= c vs later
        return np.stack([C[..., :c + 1].sum(-1), C[..., c + 1:].sum(-1)], -1)

    def kappas(C, pm):
        Kc = C.shape[-1]
        ks = np.array([fit_kappa_grid(C[:, ti, :], pm[:, ti, :]) or np.nan for ti in range(T + 1)])
        pooled = fit_kappa_grid(C[:, :T, :].reshape(-1, Kc), pm[:, :T, :].reshape(-1, Kc)) or 50.0
        return np.where(np.isnan(ks), pooled, ks)

    cum_t = np.zeros((len(tracts), T + 1, K - 1)); cum_c = np.zeros((T + 1, K - 1)); k3_by_cut = []
    for c in range(K - 1):                 # one independent hierarchy per threshold
        Ct, Ca, Cb, Cc = (merge(x, c) for x in (C_t, C_a, C_b, C_c))
        a_city = np.zeros((T + 1, 2)); a_city[T] = 0.5 + Cc[0, T]
        a_city[:T] = 5.0 * norm(a_city[T]) + Cc[0, :T]; m_city = norm(a_city)
        pm_b = np.repeat(m_city[None], len(boros), 0)
        k1 = kappas(Cb, pm_b); m_b = norm(k1[None, :, None] * pm_b + Cb)
        pm_a = m_b[n_boro]; k2 = kappas(Ca, pm_a); m_a = norm(k2[None, :, None] * pm_a + Ca)
        pm_t = m_a[t_nta]; k3 = kappas(Ct, pm_t)
        cum_t[..., c] = norm(k3[None, :, None] * pm_t + Ct)[..., 0]
        cum_c[:, c] = m_city[:, 0]; k3_by_cut.append(k3)
    mono = lambda x: np.maximum.accumulate(np.clip(x, 0, 1), axis=-1)   # thresholds must not decrease
    cum_t, cum_c = mono(cum_t), mono(cum_c)

    def to_bins(cum):                       # difference the cumulative curve; floor so no bin is exactly zero
        bp = np.diff(np.concatenate([np.zeros(cum.shape[:-1] + (1,)), cum, np.ones(cum.shape[:-1] + (1,))], -1), axis=-1)
        bp = np.maximum(bp, 1e-6)
        return bp / bp.sum(-1, keepdims=True)
    bp = to_bins(cum_t)
    k3 = k3_by_cut[1]                       # shrinkage weight is reported at the 24-hour threshold

    ship_types = meta["types"]                                       # 'ALL' first
    slot = {t: (T if t == "ALL" else types.index(t)) for t in ship_types}
    worst = (0.0, None, None); nbad = 0
    for i, g in enumerate(tracts):
        for t in ship_types:
            e = np.abs(np.array(probs[g][t]["bp"]) - bp[i, slot[t]]).max()
            nbad += e > 0.0015
            if e > worst[0]:
                worst = (e, g, t)
    check(nbad == 0, f"posterior bin probabilities match in all {len(tracts) * len(ship_types):,} cells "
                     f"(max |diff| {worst[0]:.4f} at {worst[1]} / {worst[2]}; tolerance 0.0015 = export rounding)")
    # shrinkage weight
    n_dec = C_t.sum(-1); sw = n_dec / (n_dec + k3[None, :])
    dsw = max(abs(probs[g][t]["sw"] - sw[i, slot[t]]) for i, g in enumerate(tracts) for t in ship_types)
    check(dsw < 0.0015, f"shrinkage weights match (max |diff| {dsw:.4f})")
    # reference profiles
    dref = max(np.abs(np.array(meta["refs"]["city"][t]) - cum_c[slot[t]]).max() for t in ship_types)
    check(dref < 0.0015, f"citywide reference profiles match (max |diff| {dref:.4f})")
    info("independent kappa (tract level) for a few types: " +
         ", ".join(f"{t}={k3[slot[t]]:.0f}" for t in ["ALL", "HEAT/HOT WATER", "Illegal Parking"]))
    return k3


# ---------------------------------------------------------------- 5. raw cross-check of one month
def raw_month(prep, month="2026-03"):
    """Recompute one month's citywide P(<=24h) from the raw CSVs with independent duration
    handling; the only production step reused is the duplicate collapse (its own row-level
    rule), so agreement to 0.1 point validates binning, censoring and the funnel end to end."""
    import prepare as P
    print(f"\n[5] Independent recomputation from raw CSV, {month}", flush=True)
    frames = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "raw", f"sr_{month.replace('-', '_')}_*.csv"))):
        frames.append(pd.read_csv(
            f, dtype={"unique_key": "int64", "complaint_type": "string", "descriptor": "string", "agency": "string",
                      "status": "string", "borough": "string", "latitude": "float64", "longitude": "float64"},
            parse_dates=["created_date", "closed_date"], date_format="ISO8601"))
    raw = pd.concat(frames)

    def p24(d):
        dur = (d["closed_date"] - d["created_date"]).dt.total_seconds() / 3600
        ok = ~(dur < 0) & ~(dur == 0) & ~((d["status"] == "Closed") & d["closed_date"].isna())
        bins = np.where(dur[ok].isna(), 8, (dur[ok].fillna(0).to_numpy()[:, None] > np.array(EDGES_H)[None, :]).sum(1))
        return float((bins <= 1).mean()), int(ok.sum())

    p_rules, n_rules = p24(raw)
    raw["complaint_type"] = raw["complaint_type"].str.strip().str.replace(r"\s+", " ", regex=True)
    p_dedup, n_dedup = p24(P.collapse_double_submissions(raw.drop_duplicates("unique_key").copy()))
    pm = prep[(prep["created_date"] >= f"{month}-01") &
              (prep["created_date"] < (pd.Timestamp(f"{month}-01") + pd.offsets.MonthBegin(1)))]
    p_prep = float((pm["bin"] <= 1).mean())
    info(f"{month}: raw {len(raw):,} rows | duration rules only P24={p_rules:.4f} ({n_rules:,}) | "
         f"+ duplicate handling P24={p_dedup:.4f} ({n_dedup:,}) | prepared P24={p_prep:.4f} ({len(pm):,})")
    check(abs(p_dedup - p_prep) < 0.001,
          f"independent P(<=24h) {p_dedup:.4f} vs prepared {p_prep:.4f} agree to 0.1 point "
          f"(duplicate handling alone moves the raw figure by {p_dedup - p_rules:+.4f})")
    ct = pd.crosstab(raw["status"], raw["closed_date"].isna())
    ct.columns = ["has closed_date", "no closed_date"]
    print(ct.to_string(), flush=True)
    info("statuses without a closed_date are treated as still open (month+); a closed_date is used whenever present, "
         "even if the status was not updated")


def main() -> None:
    lookup = json.load(open(os.path.join(ROOT, "data", "geo_lookup.json")))
    meta = json.load(open(os.path.join(ROOT, "web", "data", "meta.json")))
    probs = json.load(open(os.path.join(ROOT, "web", "data", "probs.json")))
    types_named = json.load(open(os.path.join(ROOT, "pipeline", "types.json")))["types"]
    prep = pd.read_parquet(os.path.join(ROOT, "data", "prepared.parquet"))
    prep["created_date"] = pd.to_datetime(prep["created_date"])
    for c in ["geoid", "nta", "boro", "complaint_type"]:
        prep[c] = prep[c].astype("object")
    conservation(prep, probs, meta, types_named, lookup)
    binning()
    likelihood_formula()
    cascade(prep, probs, meta, types_named, lookup)
    raw_month(prep)
    print(f"\n{'FAILED: ' + str(len(failures)) + ' check(s)' if failures else 'ALL AUDIT CHECKS PASSED'}", flush=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
