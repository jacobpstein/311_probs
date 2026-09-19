"""Does estimating a separate pooling strength per cumulative threshold predict better?

The production model pools all nine duration bins with one concentration per
(type, level). If tract-to-tract variation is large for "resolved within 24h" but
small for the other bins, that shared strength is dominated by the quiet bins and
over-pools the quantity the map displays. The cutwise alternative fits one
two-category hierarchy per threshold (bins <= c vs later; a Dirichlet merged over
categories is a Dirichlet with summed parameters, so the structure is unchanged),
each with its own empirical-Bayes concentrations.

Rolling-origin protocol as in eval_rolling.py: refit at each month start on all
earlier data (90-day decay), score that month. Metric: log-loss and Brier score of
the binary event "resolved within threshold c", paired across the two models on the
same requests; SEs by bootstrap over tract x type cells.

Writes docs/cutwise_evaluation.md.
"""

import json
import os
import sys

import numpy as np
import pandas as pd

import model as M

ROOT = os.path.join(os.path.dirname(__file__), "..")
CUTS = list(range(M.K - 1))
CUT_LABELS = ["3 hours", "24 hours", "2 days", "3 days", "1 week", "2 weeks", "3 weeks", "1 month"]
MIN_TRAIN_DAYS = 365
CFG = M.Config("cutwise", half_life_days=90.0)


def load():
    df = pd.read_parquet(os.path.join(ROOT, "data", "prepared.parquet"))
    df["created_date"] = pd.to_datetime(df["created_date"])
    for c in ["geoid", "nta", "boro", "complaint_type"]:
        df[c] = df[c].astype("object")
    geo = M.GeoIndex(json.load(open(os.path.join(ROOT, "data", "geo_lookup.json"))))
    types = json.load(open(os.path.join(ROOT, "pipeline", "types.json")))["types"]
    df["ctype"] = M.collapse_types(df["complaint_type"], types)
    return df, geo, types + ["Other"]


def cum_predictions(a_tract, a_boro, sub, geo, tix, first_only=False, all_slot=False):
    """Predicted P(<= cut) for every request in `sub`; (n, K-1) for the 9-bin model or (n,) for a merged one.
    all_slot=True predicts from the tract's ALL-complaints distribution (what the default map shows)."""
    ti = np.full(len(sub), a_tract.shape[1] - 1) if all_slot else sub["ctype"].map(tix).to_numpy()
    gi = sub["geoid"].map(geo.tract_ix)
    ok = gi.notna().to_numpy()
    gi = gi.fillna(0).astype(int).to_numpy()
    bi = sub["boro"].map(geo.boro_ix).fillna(0).astype(int).to_numpy()
    a = np.where(ok[:, None], a_tract[gi, ti], a_boro[bi, ti])
    p = a / a.sum(1, keepdims=True)
    return p[:, 0] if first_only else np.cumsum(p, 1)[:, :-1]


def binary_losses(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p)), (y - p) ** 2


def main() -> None:
    df, geo, types = load()
    tix = {t: i for i, t in enumerate(types)}
    d0, end = df["created_date"].min(), df["created_date"].max()
    months = [m for m in pd.date_range(d0.normalize().replace(day=1) + pd.offsets.MonthBegin(1), end, freq="MS")
              if (m - d0).days >= MIN_TRAIN_DAYS and m + pd.offsets.MonthBegin(1) <= end + pd.Timedelta(days=1)]
    print(f"scoring {len(months)} months {months[0].strftime('%Y-%m')}..{months[-1].strftime('%Y-%m')}", flush=True)

    keys, tyidx = [], []
    dLL, dBS, LLp, BSp = ([[] for _ in CUTS] for _ in range(4))
    dLL_all, dBS_all, LLp_all = ([[] for _ in CUTS] for _ in range(3))
    kappa_note = {}
    for m in months:
        train = df[df["created_date"] < m]
        test = df[(df["created_date"] >= m) & (df["created_date"] < m + pd.offsets.MonthBegin(1))]
        C = M.count_tensors(train, geo, types, m, CFG.half_life_days)
        prod = M.fit_from_counts(*C, geo, types, CFG)
        cp = cum_predictions(prod.a_tract, prod.a_boro, test, geo, tix)
        cp_all = cum_predictions(prod.a_tract, prod.a_boro, test, geo, tix, all_slot=True)
        tyidx.append(test["ctype"].map(tix).to_numpy())
        keys.append((test["geoid"].fillna("NA").astype(str) + "|" + test["ctype"]).to_numpy())
        bins = test["bin"].to_numpy()
        for c in CUTS:
            merged = [M.merge_at_cut(x, c) for x in C]
            fm2 = M.fit_from_counts(*merged, geo, types, CFG)
            p2 = cum_predictions(fm2.a_tract, fm2.a_boro, test, geo, tix, first_only=True)
            y = (bins <= c).astype(float)
            ll1, bs1 = binary_losses(y, cp[:, c])
            ll2, bs2 = binary_losses(y, p2)
            p2a = cum_predictions(fm2.a_tract, fm2.a_boro, test, geo, tix, first_only=True, all_slot=True)
            lla1, bsa1 = binary_losses(y, cp_all[:, c]); lla2, bsa2 = binary_losses(y, p2a)
            dLL_all[c].append((lla2 - lla1).astype(np.float32)); dBS_all[c].append((bsa2 - bsa1).astype(np.float32))
            LLp_all[c].append(lla1.astype(np.float32))
            dLL[c].append((ll2 - ll1).astype(np.float32)); dBS[c].append((bs2 - bs1).astype(np.float32))
            LLp[c].append(ll1.astype(np.float32)); BSp[c].append(bs1.astype(np.float32))
            if m == months[-1] and c in (1, 4):
                kappa_note[c] = {t: (round(prod.kappa_table["tract"][t]), round(fm2.kappa_table["tract"][t]))
                                 for t in ["HEAT/HOT WATER", "Street Condition", "Water System", "Illegal Parking", "ALL"]}
        print(f"  scored {m.strftime('%Y-%m')} ({len(test):,} requests)", flush=True)

    codes, _ = pd.factorize(np.concatenate(keys))
    ncell = codes.max() + 1
    cnt = np.bincount(codes, minlength=ncell).astype(float)
    rng = np.random.default_rng(0)
    picks = [rng.integers(0, ncell, ncell) for _ in range(400)]

    def boot(x):
        s = np.bincount(codes, weights=np.concatenate(x), minlength=ncell)
        return float(np.concatenate(x).mean()), float(np.std([s[p].sum() / cnt[p].sum() for p in picks]))

    lines = ["# Cutwise vs nine-bin pooling\n",
             f"_Generated {pd.Timestamp.now().date()} on data {d0.date()}..{end.date()}; {len(months)} monthly refits "
             f"({months[0].strftime('%Y-%m')}..{months[-1].strftime('%Y-%m')}). Each row scores the binary event "
             f"\"resolved within the threshold\" on the same held-out requests. Δ = cutwise − nine-bin (negative = cutwise "
             f"better); ± is the bootstrap SE over tract × type cells._\n",
             "\n| threshold | nine-bin log-loss | Δ log-loss | ±SE | nine-bin Brier | Δ Brier | ±SE |", "|---|---|---|---|---|---|---|"]
    for c in CUTS:
        ll, _ = boot(LLp[c]); bs, _ = boot(BSp[c])
        dl, sl = boot(dLL[c]); db, sb = boot(dBS[c])
        lines.append(f"| {CUT_LABELS[c]} | {ll:.5f} | {dl:+.5f} | {sl:.5f} | {bs:.5f} | {db:+.5f} | {sb:.5f} |")
        print(lines[-1], flush=True)
    lines += ["\n## Scored from each tract's all-complaints distribution (what the default map shows)\n",
              "| threshold | nine-bin log-loss | Δ log-loss | ±SE | Δ Brier | ±SE |", "|---|---|---|---|---|---|"]
    for c in CUTS:
        ll, _ = boot(LLp_all[c]); dl, sl = boot(dLL_all[c]); db, sb = boot(dBS_all[c])
        lines.append(f"| {CUT_LABELS[c]} | {ll:.5f} | {dl:+.5f} | {sl:.5f} | {db:+.5f} | {sb:.5f} |")
        print("ALL-slot " + lines[-1], flush=True)

    ty = np.concatenate(tyidx)
    for c in (1, 4):
        d = np.concatenate(dLL[c]); base = np.concatenate(LLp[c])
        lines += [f"\n## By complaint type, {CUT_LABELS[c]} threshold (log-loss)\n",
                  "| type | requests | nine-bin | Δ cutwise | ±SE |", "|---|---|---|---|---|"]
        rows = []
        for t, i in tix.items():
            mk = ty == i
            if mk.sum() < 20000: continue
            cs, _ = pd.factorize(codes[mk]); nc = cs.max() + 1
            cn = np.bincount(cs, minlength=nc).astype(float); sm = np.bincount(cs, weights=d[mk], minlength=nc)
            r2 = np.random.default_rng(1); pk = [r2.integers(0, nc, nc) for _ in range(300)]
            se = float(np.std([sm[q].sum() / cn[q].sum() for q in pk]))
            rows.append((d[mk].mean(), t, int(mk.sum()), float(base[mk].mean()), se))
        for dm, t, n, b, se in sorted(rows):
            lines.append(f"| {t} | {n:,} | {b:.4f} | {dm:+.5f} | {se:.5f} |")

    lines += ["\n## Tract-level κ in the last refit: nine-bin vs cutwise\n", "| threshold | type | nine-bin κ | cutwise κ |", "|---|---|---|---|"]
    for c, d in kappa_note.items():
        for t, (a, b) in d.items():
            lines.append(f"| {CUT_LABELS[c]} | {t} | {a} | {b} |")
    open(os.path.join(ROOT, "docs", "cutwise_evaluation.md"), "w").write("\n".join(lines) + "\n")
    print("wrote docs/cutwise_evaluation.md", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
