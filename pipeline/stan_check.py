"""Full-Bayes check of the production cascade with Stan (CmdStan via cmdstanpy).

For one borough and several complaint types, fits pipeline/stan/hier_dm.stan - a
hierarchical Dirichlet-Multinomial in which both concentrations and the
neighborhood distributions are sampled (nothing plugged in) - and compares its
tract-level P(resolved within 24h) with the production cascade fitted on the same
counts. Workflow (stan-testing skill): 1) parameter recovery on data simulated from
the Stan program's own generative process, 2) real-data fit with sampler
diagnostics, 3) comparison with the cascade.

    python pipeline/stan_check.py [Borough]     # default Brooklyn
Writes docs/stan_validation.md. Uses the last 365 days, no decay, so both models see
identical integer counts.
"""

import json
import os
import sys

import numpy as np
import pandas as pd
from cmdstanpy import CmdStanModel, cmdstan_version

import model as M

ROOT = os.path.join(os.path.dirname(__file__), "..")
TYPES_TO_CHECK = ["HEAT/HOT WATER", "Street Condition", "Water System"]   # substantial mass on both sides of 24h
PRIOR = dict(mu_log_k2=5.0, sd_log_k2=2.0, mu_log_k3=5.0, sd_log_k3=2.0)   # k median ~150, 95% range ~3-8000
SIM_TRUTH = (120.0, 350.0)


def split_rhat(x):        # x: (chains, draws)
    n = x.shape[1] // 2
    ch = np.concatenate([x[:, :n], x[:, n:2 * n]], axis=0)
    w = ch.var(axis=1, ddof=1).mean()
    b = n * ch.mean(axis=1).var(ddof=1)
    return float(np.sqrt(((n - 1) / n * w + b / n) / w))


def ess(x):               # bulk-style ESS from pooled autocorrelation (Geyer initial positive sequence)
    c, n = x.shape
    xc = x - x.mean(axis=1, keepdims=True)
    f = np.fft.rfft(xc, n=2 * n, axis=1)
    acov = np.fft.irfft(f * np.conj(f), axis=1)[:, :n] / n
    rho = acov.mean(axis=0) / acov.mean(axis=0)[0]
    s = 0.0
    for t in range(1, n - 1, 2):
        pair = rho[t] + rho[t + 1]
        if pair < 0:
            break
        s += pair
    return float(c * n / (1 + 2 * s))


def diagnostics(fit, names):
    rows = []
    for nm in names:
        d = fit.stan_variable(nm)
        arr = d.reshape(fit.chains, -1) if d.ndim == 1 else None
        rows.append((nm, split_rhat(arr), ess(arr), float(np.median(d)), *np.percentile(d, [5, 95])))
    return rows


def sampler_health(fit):
    mv = fit.method_variables()
    div = int(mv["divergent__"].sum())
    depth = int((mv["treedepth__"] >= 10).sum())
    en = mv["energy__"]                                    # (draws, chains)
    bfmi = [float(np.sum(np.diff(en[:, c]) ** 2) / np.sum((en[:, c] - en[:, c].mean()) ** 2)) for c in range(en.shape[1])]
    return div, depth, min(bfmi)


def merge(counts):        # 9 duration bins -> (within 24h, later)
    return np.stack([counts[..., :2].sum(-1), counts[..., 2:].sum(-1)], axis=-1)


def build_data(fm, geo, lookup, boro, ti, y_counts=None):
    tr = [g for g in geo.tracts if lookup[g]["boro"] == boro]
    ntas = sorted({lookup[g]["nta"] for g in tr}); nix = {a: i + 1 for i, a in enumerate(ntas)}
    gi = np.array([geo.tract_ix[g] for g in tr])
    y = merge(fm.R_tract[gi, ti, :].round().astype(int)) if y_counts is None else y_counts
    m_b = merge(fm.a_boro[geo.boros.index(boro), ti]); m_b = m_b / m_b.sum()
    return dict(K=2, n_first=1, A=len(ntas), G=len(tr), nta=[nix[lookup[g]["nta"]] for g in tr],
                y=y.tolist(), m_b=m_b.tolist(), **PRIOR), gi, tr


def plugin_cascade(data):
    """The production estimator's logic (empirical-Bayes kappa per level, top-down conjugate
    update, parent-uncertainty term) applied to the same merged counts."""
    y = np.array(data["y"], float); nta = np.array(data["nta"]) - 1; A_ = data["A"]
    C_a = np.zeros((A_, 2)); np.add.at(C_a, nta, y)
    m_b = np.array(data["m_b"])
    k2 = M.fit_kappa(C_a, np.repeat(m_b[None], A_, 0)) or 50.0
    a_a = k2 * m_b[None] + C_a; m_a = a_a / a_a.sum(1, keepdims=True)
    pm_t = m_a[nta]
    k3 = M.fit_kappa(y, pm_t) or 50.0
    a_t = k3 * pm_t + y; At = a_t.sum(1)
    mean = a_t[:, 0] / At
    var_dir = mean * (1 - mean) / (At + 1)
    Ap = a_a.sum(1)[nta]
    var_par = pm_t[:, 0] * (1 - pm_t[:, 0]) / (Ap + 1)
    var_tot = var_dir + (k3 / At) ** 2 * var_par
    return k2, k3, mean, np.sqrt(var_dir), np.sqrt(var_tot)


def main() -> None:
    boro = sys.argv[1] if len(sys.argv) > 1 else "Brooklyn"
    lookup = json.load(open(os.path.join(ROOT, "data", "geo_lookup.json")))
    geo = M.GeoIndex(lookup)
    df = pd.read_parquet(os.path.join(ROOT, "data", "prepared.parquet"))
    df["created_date"] = pd.to_datetime(df["created_date"])
    for c in ["geoid", "nta", "boro", "complaint_type"]:
        df[c] = df[c].astype("object")
    t_end = df["created_date"].max()
    df = df[df["created_date"] > t_end - pd.Timedelta(days=365)]
    named = json.load(open(os.path.join(ROOT, "pipeline", "types.json")))["types"]
    types = named + ["Other"]
    df["ctype"] = M.collapse_types(df["complaint_type"], named)
    fm = M.fit(df, geo, types, M.Config("stan-check", half_life_days=None), t_end)
    model = CmdStanModel(stan_file=os.path.join(ROOT, "pipeline", "stan", "hier_dm.stan"))
    kw = dict(chains=4, parallel_chains=4, iter_warmup=1000, iter_sampling=1000, seed=20260919,
              adapt_delta=0.9, show_progress=False, show_console=False)
    out = [f"# Full-Bayes check of the cascade (Stan)\n",
           f"_{boro}, last 365 days to {t_end.date()}, no decay; CmdStan {'.'.join(map(str, cmdstan_version()))}. "
           f"Priors: log κ ~ Normal({PRIOR['mu_log_k2']:g}, {PRIOR['sd_log_k2']:g}) for both levels "
           f"(κ median ≈ 150, 95% range ≈ 3–8,000). Four chains × 1,000 draws, adapt_delta 0.9._\n"]

    # ---- 1. parameter recovery on simulated data (checks the Stan program itself) ----
    ti0 = types.index("HEAT/HOT WATER")
    data, gi, tr = build_data(fm, geo, lookup, boro, ti0)
    rng = np.random.default_rng(7)
    k2t, k3t = SIM_TRUTH
    m_b = np.array(data["m_b"]); A_ = data["A"]
    p_nta = rng.dirichlet(k2t * m_b, size=A_)
    N = np.array(data["y"]).sum(1)
    p_g = np.stack([rng.dirichlet(k3t * p_nta[a - 1]) for a in data["nta"]])
    y_sim = np.stack([rng.multinomial(int(n), p) for n, p in zip(N, p_g)])
    sim = dict(data, y=y_sim.tolist())
    fit = model.sample(data=sim, **kw)
    d = diagnostics(fit, ["k2", "k3"])
    div, depth, bfmi = sampler_health(fit)
    cum = fit.stan_variable("cum24")
    lo, hi = np.percentile(cum, [5, 95], axis=0)
    true_cum = p_g[:, 0]
    cover = float(((lo <= true_cum) & (true_cum <= hi)).mean())
    k2d, k3d = fit.stan_variable("k2"), fit.stan_variable("k3")
    inside = lambda draws, truth: bool(np.percentile(draws, 0.5) <= truth <= np.percentile(draws, 99.5))
    out += ["\n## 1. Recovery on simulated data (checks the program, not the data)\n",
            f"Data simulated from the program's own generative process with true κ = ({k2t:g}, {k3t:g}) for the "
            f"real {boro} geography and request volumes ({int(N.sum()):,} requests).\n",
            "| parameter | truth | posterior median | 90% interval | truth in 99% interval | R̂ | ESS |", "|---|---|---|---|---|---|---|",
            f"| κ neighborhood | {k2t:g} | {np.median(k2d):.0f} | {np.percentile(k2d, 5):.0f}–{np.percentile(k2d, 95):.0f} | {'yes' if inside(k2d, k2t) else 'NO'} | {d[0][1]:.3f} | {d[0][2]:.0f} |",
            f"| κ tract | {k3t:g} | {np.median(k3d):.0f} | {np.percentile(k3d, 5):.0f}–{np.percentile(k3d, 95):.0f} | {'yes' if inside(k3d, k3t) else 'NO'} | {d[1][1]:.3f} | {d[1][2]:.0f} |",
            f"\nTract-level P(≤24h): {cover:.1%} of {len(tr)} tracts have their true value inside the 90% posterior interval "
            f"(target 90%). Divergences {div}, treedepth-10 hits {depth}, min E-BFMI {bfmi:.2f}.\n"]
    print(out[-1], flush=True)

    # ---- 2/3. real data ----
    for t in TYPES_TO_CHECK:
        ti = types.index(t)
        data, gi, tr = build_data(fm, geo, lookup, boro, ti)
        fit = model.sample(data=data, **kw)
        div, depth, bfmi = sampler_health(fit)
        d = diagnostics(fit, ["k2", "k3"])
        k2d, k3d = fit.stan_variable("k2"), fit.stan_variable("k3")
        cum = fit.stan_variable("cum24"); mean24 = fit.stan_variable("mean24")
        s_mean, s_sd = mean24.mean(0), cum.std(0)
        c_k2, c_k3, c_mean, c_sd_dir, c_sd_tot = plugin_cascade(data)
        c9 = fm.a_tract[gi, ti, :2].sum(-1) / fm.a_tract[gi, ti, :].sum(-1)      # production 9-bin cascade
        n = np.array(data["y"]).sum(1)
        sparse, dense = (n > 0) & (n < 30), n >= 100
        out += [f"\n## {t}\n",
                f"- **Sampler:** divergences {div}, treedepth-10 hits {depth}, min E-BFMI {bfmi:.2f}; "
                f"κ R̂ {d[0][1]:.3f}/{d[1][1]:.3f}, ESS {d[0][2]:.0f}/{d[1][2]:.0f} (neighborhood/tract).",
                f"- **Pooling strengths:** Stan κ neighborhood {np.median(k2d):.0f} (90% {np.percentile(k2d, 5):.0f}–{np.percentile(k2d, 95):.0f}), "
                f"κ tract {np.median(k3d):.0f} (90% {np.percentile(k3d, 5):.0f}–{np.percentile(k3d, 95):.0f}); "
                f"matching plug-in cascade estimates {c_k2:.0f} and {c_k3:.0f}.",
                f"- **Tract posterior means, Stan vs plug-in cascade on the same counts** ({len(tr)} tracts): mean |difference| "
                f"{np.abs(s_mean - c_mean).mean():.4f}, 99th percentile {np.percentile(np.abs(s_mean - c_mean), 99):.4f}, "
                f"max {np.abs(s_mean - c_mean).max():.4f} (on the 0–1 probability scale).",
                f"  (production 9-bin cascade vs Stan: mean |difference| {np.abs(s_mean - c9).mean():.4f}, max {np.abs(s_mean - c9).max():.4f}.)",
                f"- **Uncertainty (SD of P(≤24h)), Stan ÷ plug-in cascade** — median ratio; sparse tracts (<30 requests) / dense (≥100):",
                f"  Dirichlet-only cascade SD: {np.median(s_sd[sparse] / c_sd_dir[sparse]):.2f} / {np.median(s_sd[dense] / c_sd_dir[dense]):.2f}; "
                f"cascade SD with the parent-uncertainty term: {np.median(s_sd[sparse] / c_sd_tot[sparse]):.2f} / {np.median(s_sd[dense] / c_sd_tot[dense]):.2f}."]
        print(out[-1], flush=True)
    text = "\n".join(out) + "\n"
    open(os.path.join(ROOT, "docs", "stan_validation.md"), "w").write(text)
    print("wrote docs/stan_validation.md", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
