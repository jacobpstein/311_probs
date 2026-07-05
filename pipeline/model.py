"""Hierarchical Dirichlet-Multinomial model for 311 resolution-time bins.

Implements docs/model_spec.md §1-3: top-down conjugate cascade
(tract -> NTA -> borough -> city, per complaint type, city x type rooted in
city x ALL), empirical-Bayes concentration via Minka's fixed point with a
method-of-moments initializer and pooled per-level fallback, optional
exponential time decay of counts.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.special import digamma

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
                  t_ref: pd.Timestamp, half_life_days: float | None):
    """Decayed count tensors (nodes x T+1 x K) at each level; last type slot = ALL.

    Rows without a tract (geoid NaN) contribute only to borough/city tensors
    (model_spec §6.7). Also returns raw (undecayed) tract counts for diagnostics.
    """
    T = len(types)
    type_ix = pd.Series(range(T), index=types)
    t = df["ctype"].map(type_ix).to_numpy()
    b = df["bin"].to_numpy()
    if half_life_days is None:
        w = np.ones(len(df))
    else:
        age_d = (t_ref - df["created_date"]).dt.total_seconds().to_numpy() / 86400.0
        w = np.exp2(-age_d / half_life_days)

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


def mom_icc_init(n: np.ndarray, _m: np.ndarray) -> float:
    """§2.2 ANOVA/ICC method-of-moments initializer. n: (J, K) child counts."""
    J = n.shape[0]
    nj = n.sum(1)
    N = nj.sum()
    if J < 2 or N <= J:
        return 50.0
    nbar_c = (N - (nj ** 2).sum() / N) / (J - 1)
    phat = n / nj[:, None]
    mbar = n.sum(0) / N
    msb = (nj[:, None] * (phat - mbar) ** 2).sum(0) / (J - 1)
    msw = (nj[:, None] * phat * (1 - phat)).sum(0) / (N - J)
    denom = msb + (nbar_c - 1) * msw
    wk = mbar * (1 - mbar)
    ok = denom > 0
    if not ok.any() or wk[ok].sum() == 0:
        return 50.0
    rho = ((msb - msw)[ok] * wk[ok]).sum() / (denom[ok] * wk[ok]).sum()
    if rho <= 0:
        return KAPPA_MAX
    return float(np.clip((1 - rho) / rho, KAPPA_MIN, KAPPA_MAX))


def fit_kappa(child_counts: np.ndarray, parent_means: np.ndarray) -> float | None:
    """§2.1 Minka fixed point for DM concentration with fixed per-child means.

    child_counts: (J, K) decayed counts; parent_means: (J, K) each child's parent mean.
    Returns None if too few informative children (caller uses pooled fallback).
    """
    keep = child_counts.sum(1) >= 1
    n, m = child_counts[keep], parent_means[keep]
    if (n.sum(1) >= 5).sum() < 8:
        return None
    kappa = mom_icc_init(n, m)
    for _ in range(200):
        km = np.clip(kappa * m, 1e-12, None)
        num = (m * (digamma(n + km) - digamma(km))).sum()
        den = (digamma(n.sum(1) + kappa) - digamma(kappa)).sum()
        if den <= 0:
            break
        new = float(np.clip(kappa * num / den, KAPPA_MIN, KAPPA_MAX))
        if abs(np.log(new) - np.log(kappa)) < 1e-6:
            kappa = new
            break
        kappa = new
    return kappa


def _normalize(a: np.ndarray) -> np.ndarray:
    return a / a.sum(-1, keepdims=True)


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
        df, geo, types, t_ref, cfg.half_life_days)
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
