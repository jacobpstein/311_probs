"""Interval calibration under the deployed protocol.

For each of the 11 test months, the regime variance sigma is estimated from four rolling
holdouts inside the data before the month (as export_web.py does), the model is fitted on that
data, and the 90% interval for P(resolved within 24 h) of every tract x type cell is compared with
the rate observed in the month (cells with >= 50 requests that month). Compares the holdout-cell
threshold used to estimate sigma. Coverage is reported per complaint type (cells pooled across
months); the standardized residual z2 uses the interval variance plus the binomial noise of the
month's rate. Writes docs/interval_calibration_rolling.md.
"""
import os, sys
import numpy as np
import pandas as pd
import model as M
from eval_rolling import load, MIN_TRAIN_DAYS
ROOT = os.path.join(os.path.dirname(__file__), "..")
SHIP = M.Config("P7a", kappa_mode="per_type_level", half_life_days=90.0, cutwise=True)
SETTINGS = [50, 20]


def main():
    df, geo, types = load(); tix = {t: i for i, t in enumerate(types)}
    d0, end = df["created_date"].min(), df["created_date"].max()
    months = [m for m in pd.date_range(d0.normalize().replace(day=1) + pd.offsets.MonthBegin(1), end, freq="MS")
              if (m - d0).days >= MIN_TRAIN_DAYS and m + pd.offsets.MonthBegin(1) <= end + pd.Timedelta(days=1)]
    rec = []
    for m in months:
        train = df[df["created_date"] < m]
        test = df[(df["created_date"] >= m) & (df["created_date"] < m + pd.offsets.MonthBegin(1)) & df["geoid"].notna()]
        fm = M.fit(train, geo, types, SHIP, m)
        mid, var = fm.cum_mean()[..., 1], fm.cum_variance()[..., 1]
        g = test.assign(hit=(test["bin"] <= 1).astype(float)).groupby(["geoid", "ctype"], observed=True)["hit"].agg(["mean", "size"]).reset_index()
        g = g[g["size"] >= 50]
        gi, ti = g["geoid"].map(geo.tract_ix).to_numpy(), g["ctype"].map(tix).to_numpy()
        origins = [str((m - pd.Timedelta(days=d)).date()) for d in (270, 210, 150, 90)]
        for mc in SETTINGS:
            sig = M.estimate_regime_sigma(train, geo, types, origins, min_cell=mc, cfg=SHIP)
            sg = np.array([sig["per_type"][t][1] for t in g["ctype"]])
            tot = var[gi, ti] + sg ** 2
            rec.append(pd.DataFrame({"mc": mc, "month": m, "type": g["ctype"].to_numpy(), "n": g["size"].to_numpy(),
                                     "inside": (np.abs(g["mean"].to_numpy() - mid[gi, ti]) <= 1.645 * np.sqrt(tot)),
                                     "z2": (g["mean"].to_numpy() - mid[gi, ti]) ** 2 / (tot + mid[gi, ti] * (1 - mid[gi, ti]) / g["size"].to_numpy()),
                                     "sigma": sg}))
        print("scored", m.strftime("%Y-%m"), flush=True)
    R = pd.concat(rec)
    out = ["# Interval calibration under the deployed protocol\n",
           f"_Generated {pd.Timestamp.now().date()}; {len(months)} monthly refits ({months[0]:%Y-%m}..{months[-1]:%Y-%m}); sigma re-estimated before every month "
           "from four rolling holdouts, exactly as the weekly export does. Cells: tract × type with ≥50 requests in the scored month; interval for "
           "P(resolved within 24 h). “Holdout cell threshold” is the minimum requests a holdout cell needs to contribute to sigma._\n"]
    tot = R.groupby("mc").agg(cov=("inside", "mean"), z2=("z2", "mean"), cells=("inside", "size"))
    out += ["| holdout cell threshold | cells | coverage (target 0.90) | mean z² (target ≈1) |", "|---|---|---|---|"]
    for mc, r in tot.iterrows():
        out.append(f"| {mc} | {int(r['cells']):,} | {r['cov']:.3f} | {r['z2']:.2f} |")
    per = R.groupby(["type", "mc"]).agg(cov=("inside", "mean"), n=("inside", "size"), sigma=("sigma", "mean")).unstack("mc")
    out += ["\n## Coverage by complaint type\n", "| type | cells | " + " | ".join(f"coverage @{mc}" for mc in SETTINGS) + " | " + " | ".join(f"mean σ @{mc}" for mc in SETTINGS) + " |",
            "|---|---|" + "---|" * (2 * len(SETTINGS))]
    for t in per.sort_values(("cov", SETTINGS[0])).index:
        out.append(f"| {t} | {int(per.loc[t, ('n', SETTINGS[0])]):,} | " + " | ".join(f"{per.loc[t, ('cov', mc)]:.2f}" for mc in SETTINGS) + " | "
                   + " | ".join(f"{per.loc[t, ('sigma', mc)]:.3f}" for mc in SETTINGS) + " |")
    for mc in SETTINGS:
        c = per[("cov", mc)]
        out.append(f"\nAt threshold {mc}: {int((c < 0.85).sum())} types below 0.85, {int((c > 0.97).sum())} above 0.97; mean |coverage − 0.90| = {np.abs(c - 0.9).mean():.3f}.")
    open(os.path.join(ROOT, "docs", "interval_calibration_rolling.md"), "w").write("\n".join(out) + "\n")
    print("\n".join(out), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True); main()
