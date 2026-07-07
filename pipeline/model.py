"""Hierarchical Dirichlet-Multinomial model for 311 resolution-time bins.

Implements docs/model_spec.md §1-3 (with the post-audit revisions in
docs/statistical_review.md): top-down conjugate cascade (tract -> NTA -> borough
-> city, per complaint type, city x type rooted in city x ALL), empirical-Bayes
concentration by bounded maximization of the exact Dirichlet-Multinomial marginal
likelihood with a pooled per-level fallback, optional exponential time decay of
counts, and a regime-variance estimator for credible-interval calibration.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln

K = 9
ALPHA0 = 0.5   # Jeffreys at the global root
KAPPA0 = 5.0   # city ALL -> city type
KAPPA_MIN, KAPPA_MAX = 0.5, 5000.0


@dataclass
class Config:
    name: str
    hierarchy: bool = True
    kappa_mode: str = "per_type_level"  # 'fixed' | 'per_type' | 'per_type_level'
    fixed_kappa: float = 15.0
    flat_alpha: float = 1.0             # used only when hierarchy=False
    half_life_days: float | None = None
    seasonal_beta: float = 0.0          # weight of same-season-last-year kernel
    seasonal_bw_days: float = 45.0      # kernel half-life around age = 1 year


CONFIGS = [
    Config("P0 uniform, no pooling", hierarchy=False, flat_alpha=1.0),
    Config("P1 Jeffreys, no pooling", hierarchy=False, flat_alpha=0.5),
    Config("P2 hierarchy, fixed k=15", kappa_mode="fixed", fixed_kappa=15.0),
    Config("P3 hierarchy, EB k per type", kappa_mode="per_type"),
    Config("P4 hierarchy, EB k per (type,level)", kappa_mode="per_type_level"),
    Config("P5a P4 + decay h=90d", half_life_days=90.0),
    Config("P5b P4 + decay h=180d", half_life_days=180.0),
    Config("P5c P4 + decay h=365d", half_life_days=365.0),
]


class GeoIndex:
    """Node indexing for the tract -> NTA -> borough hierarchy."""

    def __init__(self, geo_lookup: dict):
        self.tracts = sorted(geo_lookup)
        self.tract_ix = {g: i for i, g in enumerate(self.tracts)}
        self.ntas = sorted({v["nta"] for v in geo_lookup.values()})
        self.nta_ix = {a: i for i, a in enumerate(self.ntas)}
        self.boros = sorted({v["boro"] for v in geo_lookup.values()})
        self.boro_ix = {b: i for i, b in enumerate(self.boros)}
        self.tract_parent = np.array([self.nta_ix[geo_lookup[g]["nta"]] for g in self.tracts])
        self.nta_parent = np.zeros(len(self.ntas), dtype=int)
        for g in self.tracts:
            self.nta_parent[self.nta_ix[geo_lookup[g]["nta"]]] = self.boro_ix[geo_lookup[g]["boro"]]


def collapse_types(s: pd.Series, top_types: list[str]) -> pd.Series:
    return pd.Series(np.where(s.isin(top_types), s, "Other"), index=s.index)


def count_tensors(df: pd.DataFrame, geo: GeoIndex, types: list[str],
                  t_ref: pd.Timestamp, half_life_days: float | None,
                  seasonal_beta: float = 0.0, seasonal_bw_days: float = 45.0):
    """Decayed count tensors (nodes x T+1 x K) at each level; last type slot = ALL.

    Row weight = recency kernel 2^(-age/half_life) plus, when seasonal_beta > 0, a
    same-season kernel seasonal_beta * 2^(-|age - 365.25d| / seasonal_bw_days) that
    up-weights data from the matching season one year earlier (still one weighted
    count vector per row, so conjugacy is untouched).

    Rows without a tract (geoid NaN) contribute only to borough/city tensors
    (model_spec §6.7). Also returns raw (undecayed) tract counts for diagnostics.
    """
    T = len(types)
    type_ix = pd.Series(range(T), index=types)
    t = df["ctype"].map(type_ix).to_numpy()
    b = df["bin"].to_numpy()
    age_d = (t_ref - df["created_date"]).dt.total_seconds().to_numpy() / 86400.0
    if half_life_days is None:
        w = np.ones(len(df))
    else:
        w = np.exp2(-age_d / half_life_days)
    if seasonal_beta > 0:
        w = w + seasonal_beta * np.exp2(-np.abs(age_d - 365.25) / seasonal_bw_days)

    def accumulate(node_idx: np.ndarray, n_nodes: int, mask: np.ndarray, weights) -> np.ndarray:
        out = np.zeros((n_nodes, T + 1, K))
        flat = (node_idx[mask] * (T + 1) + t[mask]) * K + b[mask]
        np.add.at(out.reshape(-1), flat, weights[mask])
        out[:, T, :] = out[:, :T, :].sum(axis=1)  # ALL = pooled over types
        return out

    has_tract = df["geoid"].notna().to_numpy()
    tract_idx = df["geoid"].map(geo.tract_ix).to_numpy(dtype=float)
    tract_idx = np.nan_to_num(tract_idx, nan=0).astype(int)
    nta_idx = geo.tract_parent[tract_idx]
    boro_series = df["boro"].map(geo.boro_ix)
    has_boro = boro_series.notna().to_numpy()
    boro_idx = boro_series.fillna(0).to_numpy(dtype=int)

    C_tract = accumulate(tract_idx, len(geo.tracts), has_tract, w)
    C_nta = accumulate(nta_idx, len(geo.ntas), has_tract, w)
    C_boro = accumulate(boro_idx, len(geo.boros), has_boro, w)
    C_city = accumulate(np.zeros(len(df), dtype=int), 1, np.ones(len(df), bool), w)
    R_tract = accumulate(tract_idx, len(geo.tracts), has_tract, np.ones(len(df)))
    return C_tract, C_nta, C_boro, C_city, R_tract


def fit_kappa(child_counts: np.ndarray, parent_means: np.ndarray) -> float | None:
    """MLE of the DM concentration with fixed per-child means, by bracketed
    maximization of the exact marginal log-likelihood over log kappa.

    Replaces the Minka fixed-point iteration: on the flat likelihood surfaces
    typical here the fixed point converges too slowly and stops far short of the
    optimum (verified against a grid of the exact marginal likelihood), which
    systematically under-pools. Bounded scalar maximization is exact and cheap
    (~30 likelihood evaluations per (type, level)).

    child_counts: (J, K) decayed counts; parent_means: (J, K) each child's parent mean.
    Returns None if too few informative children (caller uses pooled fallback).
    """
    keep = child_counts.sum(1) >= 1
    n, m = child_counts[keep], parent_means[keep]
    if (n.sum(1) >= 5).sum() < 8:
        return None
    nj = n.sum(1)

    def negll(log_k: float) -> float:
        k = np.exp(log_k)
        km = np.clip(k * m, 1e-12, None)
        ll = (gammaln(k) - gammaln(nj + k) + (gammaln(n + km) - gammaln(km)).sum(1)).sum()
        return -float(ll)

    res = minimize_scalar(negll, bounds=(np.log(KAPPA_MIN), np.log(KAPPA_MAX)),
                          method="bounded", options={"xatol": 1e-4})
    return float(np.clip(np.exp(res.x), KAPPA_MIN, KAPPA_MAX))


def _normalize(a: np.ndarray) -> np.ndarray:
    return a / a.sum(-1, keepdims=True)


def estimate_regime_sigma(df: pd.DataFrame, geo: "GeoIndex", types: list[str],
                          origins: list[str], horizon_days: int = 60,
                          min_cell: int = 50, q: float = 0.90) -> dict:
    """Per-type additive regime-variance for credible-interval calibration.

    The Dirichlet posterior interval covers sampling uncertainty about the current
    decay-weighted rate, but a cell's realized near-future rate also moves with the
    service regime (seasonality, agency policy/backlog changes, correlated batch
    closures). On dense cells that regime variability dominates the (tiny) sampling
    term, so raw intervals badly under-cover (verified ~0.25 at nominal 90% against
    next-60-day empirical rates). Remedy: estimate, per complaint type and cumulative
    cut, an additive standard deviation sigma such that
        halfwidth = 1.645 * sqrt(Var_Dirichlet(cum) + sigma^2)
    covers ~q of near-future cell rates historically.

    Estimator: for several rolling origins inside the training window, fit the model
    on data before the origin and compare each dense cell's posterior cumulative mean
    with its empirical rate over the following horizon; sigma[type][cut] is the q-th
    percentile of squared deviation in excess of the sampling variance (model +
    horizon sample), pooled across origins, with a pooled-over-types fallback for
    thin types. Multiple origins spread across the year average over seasonal
    regimes. Additive (not multiplicative) so sparse cells - whose intervals are
    already wide - are only modestly widened.

    Returns {"per_type": {type: [sigma at 8 cuts]}, "pooled": [8 cuts]}.
    """
    cfg = Config("sigma-est", kappa_mode="per_type_level", half_life_days=90.0)
    named = [t for t in types if t != "Other"]
    rows = []  # (type, cut, excess squared deviation)
    for o in origins:
        fe = pd.Timestamp(o)
        tr = df[df["created_date"] < fe].copy()
        ho = df[(df["created_date"] >= fe) &
                (df["created_date"] < fe + pd.Timedelta(days=horizon_days))]
        ho = ho[ho["geoid"].notna()]
        if len(tr) == 0 or len(ho) == 0:
            continue
        tr["ctype"] = collapse_types(tr["complaint_type"], named)
        ho = ho.assign(ctype=collapse_types(ho["complaint_type"], named))
        fm = fit(tr, geo, types, cfg, fe)
        a = fm.a_tract
        A = a.sum(-1)
        tix = {t: i for i, t in enumerate(types)}

        # per-cell bin histogram -> empirical cumulative rates at all cuts at once
        ct = ho.groupby(["geoid", "ctype", "bin"], observed=True).size().unstack(
            "bin", fill_value=0).reindex(columns=range(K), fill_value=0)
        n_cell = ct.sum(1).to_numpy()
        keep = n_cell >= min_cell
        ct = ct[keep]
        n_cell = n_cell[keep]
        emp_cum = ct.to_numpy().cumsum(1)[:, :-1] / n_cell[:, None]   # (cells, 8)
        gi = np.array([geo.tract_ix.get(g, -1) for g in ct.index.get_level_values(0)])
        ti = np.array([tix.get(t, -1) for t in ct.index.get_level_values(1)])
        ok = (gi >= 0) & (ti >= 0)
        mid = a.cumsum(-1)[..., :-1] / A[..., None]                   # (tract, T+1, 8)
        m = mid[gi[ok], ti[ok]]                                       # (cells, 8)
        var0 = m * (1 - m) / (A[gi[ok], ti[ok], None] + 1)
        samp = var0 + m * (1 - m) / n_cell[ok, None]
        ex2 = np.maximum((emp_cum[ok] - m) ** 2 - samp, 0.0)
        tnames = ct.index.get_level_values(1).to_numpy()[ok]
        for cut in range(K - 1):
            rows.extend(zip(tnames, [cut] * ok.sum(), ex2[:, cut]))

        # the ALL (all-types pooled) tree, used by the UI's default view
        ct2 = ho.groupby(["geoid", "bin"], observed=True).size().unstack(
            "bin", fill_value=0).reindex(columns=range(K), fill_value=0)
        n2 = ct2.sum(1).to_numpy()
        ct2 = ct2[n2 >= min_cell]
        n2 = n2[n2 >= min_cell]
        emp2 = ct2.to_numpy().cumsum(1)[:, :-1] / n2[:, None]
        gi2 = np.array([geo.tract_ix.get(g, -1) for g in ct2.index])
        ok2 = gi2 >= 0
        T = len(types)
        m2 = mid[gi2[ok2], T]
        samp2 = m2 * (1 - m2) / (A[gi2[ok2], T, None] + 1) + m2 * (1 - m2) / n2[ok2, None]
        ex2b = np.maximum((emp2[ok2] - m2) ** 2 - samp2, 0.0)
        for cut in range(K - 1):
            rows.extend(zip(["ALL"] * int(ok2.sum()), [cut] * int(ok2.sum()), ex2b[:, cut]))
    z = pd.DataFrame(rows, columns=["t", "cut", "ex2"])
    pooled = [float(np.sqrt(z[z["cut"] == c]["ex2"].quantile(q)) / 1.645)
              for c in range(K - 1)]
    per_type = {}
    for t in types + ["ALL"]:
        zt = z[z["t"] == t]
        per_type[t] = [
            float(np.sqrt(zt[zt["cut"] == c]["ex2"].quantile(q)) / 1.645)
            if (zt["cut"] == c).sum() >= 60 else pooled[c]
            for c in range(K - 1)
        ]
    return {"per_type": per_type, "pooled": pooled}


class FittedModel:
    """Posterior Dirichlet parameters at every level, plus diagnostics."""

    def __init__(self, geo: GeoIndex, types: list[str], a_tract, a_nta, a_boro, a_city,
                 n_tract_dec, R_tract, kappa3, kappa_table):
        self.geo = geo
        self.types = types            # named types (+ 'Other'); index T = ALL
        self.a_tract = a_tract        # (n_tract, T+1, K)
        self.a_nta = a_nta
        self.a_boro = a_boro
        self.a_city = a_city
        self.n_tract_dec = n_tract_dec  # decayed local mass per cell (n_tract, T+1)
        self.R_tract = R_tract          # raw counts (n_tract, T+1, K)
        self.kappa3 = kappa3            # (T+1,) tract-level kappa per type
        self.kappa_table = kappa_table  # {level: {type: kappa}} for reporting

    def tract_probs(self) -> np.ndarray:
        return _normalize(self.a_tract)

    def shrinkage(self) -> np.ndarray:
        return self.n_tract_dec / (self.n_tract_dec + self.kappa3[None, :])


def fit(df: pd.DataFrame, geo: GeoIndex, types: list[str], cfg: Config,
        t_ref: pd.Timestamp, frozen_kappa: dict | None = None) -> FittedModel:
    """Fit one configuration. df must have columns ctype, bin, created_date, geoid, boro.

    frozen_kappa: optional {"boro"|"nta"|"tract": array (T+1,)} — skips EB estimation
    (the §8 incremental-update path re-runs the cascade with the stored kappa table).
    """
    C_tract, C_nta, C_boro, C_city, R_tract = count_tensors(
        df, geo, types, t_ref, cfg.half_life_days,
        cfg.seasonal_beta, cfg.seasonal_bw_days)
    T = len(types)

    if not cfg.hierarchy:
        a_tract = cfg.flat_alpha + C_tract
        # upper levels still get flat posteriors for completeness
        return FittedModel(geo, types, a_tract, cfg.flat_alpha + C_nta,
                           cfg.flat_alpha + C_boro, cfg.flat_alpha + C_city,
                           C_tract.sum(-1), R_tract,
                           np.full(T + 1, cfg.flat_alpha * K), {"mode": "none"})

    # --- top of cascade ---
    a_city = np.zeros_like(C_city)
    a_city[0, T] = ALPHA0 + C_city[0, T]
    m_city_all = _normalize(a_city[0, T])
    a_city[0, :T] = KAPPA0 * m_city_all + C_city[0, :T]
    m_city = _normalize(a_city[0])                      # (T+1, K)

    # --- kappa estimation (top-down so parent means exist) ---
    levels = [
        ("boro", C_boro, m_city[None, :, :].repeat(len(geo.boros), 0)),
        ("nta", None, None),   # filled after boro posterior
        ("tract", None, None),
    ]
    kap = {lvl: np.zeros(T + 1) for lvl, _, _ in levels}
    table = {}

    def estimate_level(lvl: str, C: np.ndarray, parent_mean: np.ndarray) -> np.ndarray:
        """C: (J, T+1, K); parent_mean: (J, T+1, K). Returns kappa per type (T+1,)."""
        if cfg.kappa_mode == "fixed":
            return np.full(T + 1, cfg.fixed_kappa)
        if frozen_kappa is not None:
            return np.asarray(frozen_kappa[lvl])
        ks = np.full(T + 1, np.nan)
        for ti in range(T + 1):
            ks[ti] = fit_kappa(C[:, ti, :], parent_mean[:, ti, :]) or np.nan
        # pooled fallback: all named-type children at this level jointly (§2.3)
        pooled = fit_kappa(C[:, :T, :].reshape(-1, K),
                           parent_mean[:, :T, :].reshape(-1, K)) or 50.0
        ks = np.where(np.isnan(ks), pooled, ks)
        table[lvl] = {types[ti] if ti < T else "ALL": round(float(ks[ti]), 2) for ti in range(T + 1)}
        table[lvl + "_pooled"] = round(float(pooled), 2)
        return ks

    # borough level
    pm_boro = m_city[None, :, :].repeat(len(geo.boros), 0)
    k1 = estimate_level("boro", C_boro, pm_boro)
    a_boro = k1[None, :, None] * pm_boro + C_boro
    m_boro = _normalize(a_boro)

    # NTA level
    pm_nta = m_boro[geo.nta_parent]
    k2 = estimate_level("nta", C_nta, pm_nta)
    a_nta = k2[None, :, None] * pm_nta + C_nta
    m_nta = _normalize(a_nta)

    # tract level
    pm_tract = m_nta[geo.tract_parent]
    k3 = estimate_level("tract", C_tract, pm_tract)
    a_tract = k3[None, :, None] * pm_tract + C_tract

    if cfg.kappa_mode == "per_type":
        # single kappa per type shared across levels, fitted on NTA->tract children
        k1, k2 = k3.copy(), k3.copy()
        a_boro = k1[None, :, None] * pm_boro + C_boro
        m_boro = _normalize(a_boro)
        pm_nta = m_boro[geo.nta_parent]
        a_nta = k2[None, :, None] * pm_nta + C_nta
        m_nta = _normalize(a_nta)
        pm_tract = m_nta[geo.tract_parent]
        a_tract = k3[None, :, None] * pm_tract + C_tract

    return FittedModel(geo, types, a_tract, a_nta, a_boro, a_city,
                       C_tract.sum(-1), R_tract, k3, table)
