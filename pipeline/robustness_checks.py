"""Three follow-up checks on the shipped (cutwise) model. Writes docs/robustness_checks.md.

A. Per-type calibration of the 90% intervals, split by how much training data a cell has, with
   the shipped model on the single train/test split of evaluate.py. Focus: the types whose
   estimated regime variance is close to zero.
B. Do correlated outcomes within cells explain the dense-cell interval shortfall? Even/odd
   day-of-year split of the last 12 months (drift cannot matter: both halves span the same
   dates). Measures the day-clustering of outcomes directly (Pearson dispersion of daily
   counts within tract x type cells), then re-scores coverage with the sampling variance
   inflated by the dispersion measured on the training half, with and without batch closures.
C. Batch-closure sensitivity: rolling-origin scores with batch-closed requests removed from
   training and/or scoring, and the change in borough and city P(<=24h) by type.
"""
import json, os, sys
import numpy as np
import pandas as pd
import model as M
from eval_rolling import load as load_all, MIN_TRAIN_DAYS
import evaluate as E

ROOT = os.path.join(os.path.dirname(__file__), "..")
SHIP = M.Config("P7a", kappa_mode="per_type_level", half_life_days=90.0, cutwise=True)
LOW_SIGMA = ["Noise - Commercial", "Noise - Street/Sidewalk", "Noise - Residential", "Illegal Parking",
             "UNSANITARY CONDITION", "Blocked Driveway"]
out = []


def section_a(df, geo, types):
    print("A. per-type calibration", flush=True)
    tix = {t: i for i, t in enumerate(types)}
    d0 = df["created_date"].min(); split = d0 + pd.Timedelta(days=E.TRAIN_DAYS)
    train = df[df["created_date"] < split]; test = df[df["created_date"] >= split]
    origins = [str((split - pd.Timedelta(days=d)).date()) for d in (270, 210, 150, 90)]
    sig = M.estimate_regime_sigma(train, geo, types, origins, cfg=SHIP)
    fm = M.fit(train, geo, types, SHIP, split)
    p, var24 = E.predictions_for(fm, geo, tix, test)
    mid = p[:, :2].sum(1); hit = (test["bin"].to_numpy() <= 1).astype(float)
    ntr = train.groupby(["geoid", "ctype"], observed=True).size().to_dict()
    g = pd.DataFrame({"geoid": test["geoid"].to_numpy(), "ctype": test["ctype"].to_numpy(), "hit": hit, "mid": mid, "v": var24})
    g = g[g["geoid"].notna()]
    sg = np.array([sig["per_type"][t][1] for t in g["ctype"]])
    cell = g.assign(sg=sg).groupby(["geoid", "ctype"], observed=True).agg(
        n=("hit", "size"), obs=("hit", "mean"), mid=("mid", "first"), v=("v", "first"), sg=("sg", "first")).reset_index()
    cell["ntr"] = [ntr.get((a, b), 0) for a, b in zip(cell["geoid"], cell["ctype"])]
    cell = cell[cell["n"] >= 10]
    rows = []
    for t in types:
        c = cell[cell["ctype"] == t]
        r = {"type": t, "sigma": sig["per_type"][t][1]}
        for name, m in (("sparse", c["ntr"] < 30), ("dense", c["ntr"] >= 30)):
            cc = c[m]
            if len(cc) < 20:
                r[name] = (np.nan, np.nan, len(cc)); continue
            z = (cc["obs"] - cc["mid"]) / np.sqrt(cc["v"] + cc["sg"] ** 2 + cc["mid"] * (1 - cc["mid"]) / cc["n"])
            # coverage of the interval itself for cells with >= 50 test obs
            big = cc[cc["n"] >= 50]
            hw = 1.645 * np.sqrt(big["v"] + big["sg"] ** 2)
            cov = float(((big["obs"] >= big["mid"] - hw) & (big["obs"] <= big["mid"] + hw)).mean()) if len(big) else np.nan
            r[name] = (float((z ** 2).mean()), cov, len(cc))
        rows.append(r)
    out.append("## A. Interval calibration by complaint type (24-hour threshold)\n")
    out.append("_Shipped model on the evaluate.py split (train first 12 months, test the next 12). z² is the mean squared "
               "standardized residual (target 1; tract × type cells with ≥10 test requests); coverage is the share of cells with "
               "≥50 test requests whose observed rate falls in the 90% interval (target 0.90)._\n")
    out.append("| type | σ (24h) | sparse z² | sparse cells | dense z² | dense coverage | dense cells |\n|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: r["sigma"]):
        s, d = r["sparse"], r["dense"]
        out.append(f"| {r['type']}{' ◂' if r['type'] in LOW_SIGMA else ''} | {r['sigma']:.3f} | {s[0]:.2f} | {s[2]} | {d[0]:.2f} | {d[1]:.2f} | {d[2]} |")
    out.append("\n◂ = the six types flagged as having almost no regime variance.\n")
    return rows, sig


def pearson_dispersion(sub, ctype_col="ctype"):
    """Pearson dispersion of daily 24h-hit counts within tract x type cells, pooled per type.
    phi = sum_cells,days (y - n*p)^2 / (n*p*(1-p))  /  (cell-days - cells)."""
    s = sub[sub["geoid"].notna()].copy()
    s["hit"] = (s["bin"] <= 1).astype(float); s["day"] = s["created_date"].dt.normalize()
    cd = s.groupby(["geoid", ctype_col, "day"], observed=True)["hit"].agg(["sum", "size"]).reset_index()
    cp = cd.groupby(["geoid", ctype_col], observed=True).agg(y=("sum", "sum"), n=("size", "sum"), D=("day", "size")).reset_index()
    cd = cd.merge(cp[["geoid", ctype_col, "y", "n", "D"]], on=["geoid", ctype_col])
    cd["p"] = cd["y"] / cd["n"]
    keep = (cd["p"] > 0.02) & (cd["p"] < 0.98) & (cd["n"] >= 50) & (cd["D"] >= 10)
    cd = cd[keep]
    cd["chi"] = (cd["sum"] - cd["size"] * cd["p"]) ** 2 / (cd["size"] * cd["p"] * (1 - cd["p"]))
    cells = cd.groupby(["geoid", ctype_col], observed=True).agg(chi=("chi", "sum"), D=("day", "size")).reset_index()
    per = cells.groupby(ctype_col, observed=True).apply(lambda g: g["chi"].sum() / (g["D"].sum() - len(g)), include_groups=False)
    return per, float(cells["chi"].sum() / (cells["D"].sum() - len(cells))), len(cells)


def section_b(df, geo, types):
    print("B. overdispersion and even/odd coverage", flush=True)
    tix = {t: i for i, t in enumerate(types)}
    end = df["created_date"].max(); win = df[df["created_date"] > end - pd.Timedelta(days=365)]
    out.append("## B. Do correlated outcomes within cells explain the dense-cell shortfall?\n")
    rows = {}
    for label, d in (("all requests", win), ("batch closures removed", win[~win["batch_closed"]])):
        per, pooled, ncell = pearson_dispersion(d)
        rows[label] = (per, pooled, ncell)
    out.append("### B1. Day-to-day clustering of outcomes inside a tract × type cell\n")
    out.append("_Pearson dispersion of the daily counts of “resolved within 24 hours” within tract × type cells (cells with ≥50 requests "
               "in the last 365 days, ≥10 active days, rate between 2% and 98%). 1.0 means requests behave like independent draws; "
               "above 1 means outcomes cluster by day (for a cell averaging m requests a day, the variance of its yearly rate is "
               "inflated by roughly this factor)._\n")
    out.append(f"Pooled over cells: all requests **{rows['all requests'][1]:.2f}** ({rows['all requests'][2]:,} cells); "
               f"batch closures removed **{rows['batch closures removed'][1]:.2f}** ({rows['batch closures removed'][2]:,} cells).\n")
    out.append("| type | dispersion, all | dispersion, batch removed |\n|---|---|---|")
    pa, pb = rows["all requests"][0], rows["batch closures removed"][0]
    for t in pa.sort_values(ascending=False).index:
        out.append(f"| {t} | {pa[t]:.2f} | {pb.get(t, np.nan):.2f} |")

    # even / odd day-of-year split
    doy = win["created_date"].dt.dayofyear + win["created_date"].dt.year * 366
    res = {}
    out.append("\n### B2. Even/odd-day split: coverage of the 90% interval (cells with ≥50 requests on the held-out half)\n")
    out.append("_Train on even days, score odd days; both halves span the same dates, so drift cannot explain a shortfall. "
               "No decay, no regime term: this isolates the sampling intervals. “Latent” compares the held-out rate with the interval for the "
               "true rate (the earlier convention); “predictive” also adds the held-out half's binomial noise. “Inflated” multiplies the "
               "sampling variance by the dispersion measured on the training half only._\n")
    out.append("| data | interval | coverage (latent) | coverage (predictive) | coverage (inflated, predictive) | cells |\n|---|---|---|---|---|---|")
    for label, d in (("all requests", win), ("batch closures removed", win[~win["batch_closed"]])):
        even = d[(doy.loc[d.index] % 2) == 0]; odd = d[(doy.loc[d.index] % 2) == 1]
        cfg = M.Config("eo", half_life_days=None, cutwise=True)
        fm = M.fit(even, geo, types, cfg, end)
        per_tr, pooled_tr, _ = pearson_dispersion(even)
        mid = fm.cum_mean()[..., 1]; var = fm.cum_variance()[..., 1]
        o = odd[odd["geoid"].notna()]
        g = o.assign(hit=(o["bin"] <= 1).astype(float)).groupby(["geoid", "ctype"], observed=True)["hit"].agg(["mean", "size"]).reset_index()
        g = g[g["size"] >= 50]
        gi = g["geoid"].map(geo.tract_ix).to_numpy(); ti = g["ctype"].map(tix).to_numpy()
        m_, v_ = mid[gi, ti], var[gi, ti]
        phi = np.array([per_tr.get(t, pooled_tr) for t in g["ctype"]]); phi = np.where(np.isnan(phi), pooled_tr, phi)
        noise = m_ * (1 - m_) / g["size"].to_numpy()
        def cov(vv): return float((np.abs(g["mean"].to_numpy() - m_) <= 1.645 * np.sqrt(vv)).mean())
        out.append(f"| {label} | sampling only | {cov(v_):.3f} | {cov(v_ + noise):.3f} | {cov(v_ * phi + noise):.3f} | {len(g):,} |")
        res[label] = (cov(v_), cov(v_ + noise), cov(v_ * phi + noise))
        print(f"  {label}: latent {res[label][0]:.3f} predictive {res[label][1]:.3f} inflated {res[label][2]:.3f} (n={len(g)})", flush=True)
    return rows, res


def rolling_batch(df, geo, types):
    print("C. batch-closure sensitivity", flush=True)
    tix = {t: i for i, t in enumerate(types)}
    from eval_rolling import score
    d0, end = df["created_date"].min(), df["created_date"].max()
    months = [m for m in pd.date_range(d0.normalize().replace(day=1) + pd.offsets.MonthBegin(1), end, freq="MS")
              if (m - d0).days >= MIN_TRAIN_DAYS and m + pd.offsets.MonthBegin(1) <= end + pd.Timedelta(days=1)]
    R = {k: [] for k in ("full_on_nb", "excl_on_nb", "full_on_all", "excl_on_all")}
    keys = []
    for m in months:
        train = df[df["created_date"] < m]
        test = df[(df["created_date"] >= m) & (df["created_date"] < m + pd.offsets.MonthBegin(1))]
        tnb = test[~test["batch_closed"]]
        f_full = M.fit(train, geo, types, SHIP, m)
        f_excl = M.fit(train[~train["batch_closed"]], geo, types, SHIP, m)
        R["full_on_nb"].append(score(f_full, tnb, geo, tix)); R["excl_on_nb"].append(score(f_excl, tnb, geo, tix))
        R["full_on_all"].append(score(f_full, test, geo, tix)); R["excl_on_all"].append(score(f_excl, test, geo, tix))
        keys.append(((tnb["geoid"].fillna("NA").astype(str) + "|" + tnb["ctype"]).to_numpy(),
                     (test["geoid"].fillna("NA").astype(str) + "|" + test["ctype"]).to_numpy()))
        print("  scored", m.strftime("%Y-%m"), flush=True)
    def cat(name, j): return np.concatenate([r[j] for r in R[name]])
    def boot(a, b, k):
        codes, _ = pd.factorize(k); nc = codes.max() + 1; cnt = np.bincount(codes, minlength=nc).astype(float)
        d = a - b; s = np.bincount(codes, weights=d, minlength=nc)
        rng = np.random.default_rng(0); pk = [rng.integers(0, nc, nc) for _ in range(300)]
        return d.mean(), np.std([s[p].sum() / cnt[p].sum() for p in pk])
    knb = np.concatenate([k[0] for k in keys]); kall = np.concatenate([k[1] for k in keys])
    out.append("\n## C. Batch-closure sensitivity\n")
    out.append("_Rolling-origin (11 monthly refits). “Excluded” models are trained without batch-closed requests. Δ = excluded − full "
               "(negative = excluding batch closures predicts better); ± bootstrap SE over tract × type cells._\n")
    out.append("| scored on | metric | full-trained | excluded-trained | Δ | ±SE |\n|---|---|---|---|---|---|")
    for label, fk, ek, k in (("requests not flagged as batch closures", "full_on_nb", "excl_on_nb", knb), ("all requests", "full_on_all", "excl_on_all", kall)):
        for j, nm in ((0, "RPS"), (1, "log-loss")):
            a, b = cat(ek, j), cat(fk, j); mu, se = boot(a, b, k)
            out.append(f"| {label} | {nm} | {b.mean():.5f} | {a.mean():.5f} | {mu:+.5f} | {se:.5f} |")
    # where do flags concentrate, and how much do displayed probabilities move
    out.append("\n### Where batch-closed requests concentrate\n")
    sh = df.groupby("boro", observed=True)["batch_closed"].mean().sort_values(ascending=False)
    out.append("Share flagged by borough: " + ", ".join(f"{b} {v:.2%}" for b, v in sh.items()) + f"; overall {df['batch_closed'].mean():.2%}.\n")
    ty = df.groupby("ctype", observed=True)["batch_closed"].agg(["mean", "sum"]).sort_values("mean", ascending=False)
    out.append("| type | share flagged | requests flagged |\n|---|---|---|")
    for t, r in ty.head(8).iterrows():
        out.append(f"| {t} | {r['mean']:.2%} | {int(r['sum']):,} |")
    ag = df.groupby("agency", observed=True)["batch_closed"].agg(["mean", "sum"]).sort_values("sum", ascending=False).head(5)
    out.append("\nAgencies with the most flagged requests: " + ", ".join(f"{a} ({int(r['sum']):,}, {r['mean']:.1%})" for a, r in ag.iterrows()) + ".\n")

    t_ref = end
    f_full = M.fit(df, geo, types, SHIP, t_ref); f_excl = M.fit(df[~df["batch_closed"]], geo, types, SHIP, t_ref)
    bc_f, bc_e, cc_f, cc_e = f_full.boro_cum()[..., 1], f_excl.boro_cum()[..., 1], f_full.city_cum()[..., 1], f_excl.city_cum()[..., 1]
    out.append("### Change in displayed P(resolved within 24 hours) when batch closures are excluded from the fit\n")
    out.append("| type | city, full | city, excluded | largest borough change (points) | borough ranking preserved |\n|---|---|---|---|---|")
    allt = types + ["ALL"]
    for ti, t in enumerate(allt):
        rk = (np.argsort(np.argsort(bc_f[:, ti])) == np.argsort(np.argsort(bc_e[:, ti]))).all()
        out.append(f"| {t} | {cc_f[ti]:.3f} | {cc_e[ti]:.3f} | {100 * np.abs(bc_e[:, ti] - bc_f[:, ti]).max():.1f} | {'yes' if rk else 'no'} |")
    tr_f, tr_e = f_full.cum_mean()[..., 1], f_excl.cum_mean()[..., 1]
    d = np.abs(tr_e[:, -1] - tr_f[:, -1])
    out.append(f"\nAll-complaints tract map: mean absolute change {100 * d.mean():.2f} points, 99th percentile {100 * np.percentile(d, 99):.1f}, "
               f"max {100 * d.max():.1f}; rank correlation of tracts {pd.Series(tr_f[:, -1]).corr(pd.Series(tr_e[:, -1]), method='spearman'):.4f}.\n")


def main():
    df, geo, types = load_all()
    rowsA, sig = section_a(df, geo, types)
    section_b(df, geo, types)
    rolling_batch(df, geo, types)
    head = [f"# Follow-up robustness checks\n", f"_Generated {pd.Timestamp.now().date()} on data {df['created_date'].min().date()}..{df['created_date'].max().date()}; shipped model P7a (cutwise, 90-day decay)._\n"]
    open(os.path.join(ROOT, "docs", "robustness_checks.md"), "w").write("\n".join(head + out) + "\n")
    print("\n".join(out), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True); main()
