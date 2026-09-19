"""Simulation check of the cascade against known truth.

Generates data from the hierarchical Dirichlet-Multinomial the model assumes
(city -> borough -> NTA -> tract, real geography and real per-tract request
volumes for one complaint type) with KNOWN concentration parameters, fits the
production cascade and the sibling-only (loo_parent) variant, and compares:

  * recovery of the NTA->tract and borough->NTA concentrations,
  * accuracy of tract-level estimates (mean KL from the truth),
  * coverage of the 90% Dirichlet-Beta intervals for the true P(<=24h),

each also with the TRUE concentrations supplied, which separates
concentration-estimation error from structural error in the cascade.

    python pipeline/sim_check.py
"""

import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import beta

import model as M

ROOT = os.path.join(os.path.dirname(__file__), "..")
N_REPS = 8
SCENARIOS = {                       # true (kappa1, kappa2, kappa3)
    "high heterogeneity": (150.0, 40.0, 100.0),
    "moderate":           (150.0, 100.0, 300.0),
    "low heterogeneity":  (150.0, 300.0, 1500.0),
}
TYPE = "X"


def main() -> None:
    lookup = json.load(open(os.path.join(ROOT, "data", "geo_lookup.json")))
    geo = M.GeoIndex(lookup)
    prep = pd.read_parquet(os.path.join(ROOT, "data", "prepared.parquet"),
                           columns=["geoid", "complaint_type", "bin"])
    prep["geoid"] = prep["geoid"].astype("object"); prep["complaint_type"] = prep["complaint_type"].astype("object")
    n_g = (prep[prep["complaint_type"] == "Street Condition"]["geoid"].dropna()
           .value_counts().reindex(geo.tracts, fill_value=0).to_numpy())
    m0 = np.bincount(prep["bin"], minlength=M.K) / len(prep)          # realistic city profile
    tract_boro = np.array([geo.boros.index(lookup[g]["boro"]) for g in geo.tracts])
    boro_names = np.array(geo.boros)[tract_boro]
    t_ref = pd.Timestamp("2026-01-01")
    print(f"{len(geo.tracts)} tracts | {int(n_g.sum()):,} requests/replicate | "
          f"{(n_g == 0).mean():.0%} empty, {(n_g < 30).mean():.0%} under 30 requests", flush=True)

    out = []
    for scen, (k1, k2, k3) in SCENARIOS.items():
        for rep in range(N_REPS):
            rng = np.random.default_rng(1000 * (list(SCENARIOS).index(scen) + 1) + rep)
            p_b = rng.dirichlet(k1 * m0, size=len(geo.boros))
            p_a = np.stack([rng.dirichlet(k2 * p_b[geo.nta_parent[a]]) for a in range(len(geo.ntas))])
            p_g = np.stack([rng.dirichlet(k3 * p_a[geo.tract_parent[g]]) for g in range(len(geo.tracts))])
            counts = np.stack([rng.multinomial(int(n), p) for n, p in zip(n_g, p_g)])      # (tracts, K)
            gi = np.repeat(np.arange(len(geo.tracts)), counts.sum(1))
            bins = np.concatenate([np.repeat(np.arange(M.K), c) for c in counts])
            df = pd.DataFrame({"ctype": TYPE, "bin": bins.astype("int8"), "created_date": t_ref,
                               "geoid": np.array(geo.tracts, dtype=object)[gi],
                               "boro": boro_names[gi]})
            true_cum = p_g[:, :2].sum(1)
            for label, loo, frozen in [("cascade", False, False), ("cascade, true kappa", False, True),
                                       ("sibling-only", True, False), ("sibling-only, true kappa", True, True)]:
                cfg = M.Config("sim", kappa_mode="per_type_level", half_life_days=None, loo_parent=loo)
                fk = {"boro": np.full(2, k1), "nta": np.full(2, k2), "tract": np.full(2, k3)} if frozen else None
                fm = M.fit(df, geo, [TYPE], cfg, t_ref, frozen_kappa=fk)
                a = fm.a_tract[:, 0, :]
                post = a / a.sum(1, keepdims=True)
                kl = (p_g * (np.log(p_g + 1e-12) - np.log(post))).sum(1)
                A = a.sum(1); Ac = a[:, :2].sum(1)
                lo, hi = beta.ppf(0.05, Ac, A - Ac), beta.ppf(0.95, Ac, A - Ac)
                cov = (lo <= true_cum) & (true_cum <= hi)
                sd = np.sqrt(fm.cum_variance()[:, 0, 1])
                mid = Ac / A
                cov_adj = (np.abs(true_cum - mid) <= 1.645 * sd)
                small = n_g < 30
                out.append(dict(scenario=scen, method=label, rep=rep,
                                k2_hat=(fm.kappa_table.get("nta", {}).get(TYPE, np.nan) if not frozen else np.nan),
                                k3_hat=(fm.kappa_table.get("tract", {}).get(TYPE, np.nan) if not frozen else np.nan),
                                kl=kl.mean(), kl_small=kl[small].mean(),
                                cov=cov.mean(), cov_small=cov[small].mean(),
                                cov_adj=cov_adj.mean(), cov_adj_small=cov_adj[small].mean()))
        print(f"  finished {scen}", flush=True)

    r = pd.DataFrame(out)
    lines = ["# Simulation check of the cascade\n",
             f"_{N_REPS} replicates per scenario; real geography ({len(geo.tracts)} tracts) and real "
             f"per-tract volumes for one complaint type. KL = mean KL(truth ‖ estimate) over tracts "
             f"(lower is better); coverage = share of tracts whose true P(resolved ≤24h) lies inside "
             f"the nominal 90% interval._\n"]
    for scen, (k1, k2, k3) in SCENARIOS.items():
        s = r[r["scenario"] == scen]
        lines += [f"\n## {scen}: true κ (borough, NTA, tract) = ({k1:g}, {k2:g}, {k3:g})\n",
                  "| method | κ̂ NTA | κ̂ tract | KL | KL, <30 requests | 90% coverage, tract only | + parent uncertainty | + parent, <30 requests |",
                  "|---|---|---|---|---|---|---|---|"]
        for label in ["cascade", "cascade, true kappa", "sibling-only", "sibling-only, true kappa"]:
            g = s[s["method"] == label]
            kk = "given" if g["k2_hat"].isna().all() else f"{g['k2_hat'].median():.0f}"
            k3s = "given" if g["k3_hat"].isna().all() else f"{g['k3_hat'].median():.0f}"
            lines.append(f"| {label} | {kk} | {k3s} | {g['kl'].mean():.5f} | {g['kl_small'].mean():.5f} | "
                         f"{g['cov'].mean():.3f} | {g['cov_adj'].mean():.3f} | {g['cov_adj_small'].mean():.3f} |")
    text = "\n".join(lines) + "\n"
    open(os.path.join(ROOT, "docs", "simulation_check.md"), "w").write(text)
    print(text)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
