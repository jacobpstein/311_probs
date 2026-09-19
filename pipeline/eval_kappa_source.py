"""Which counts should set the pooling strengths: decay-weighted, raw, or raw scaled by the decay's mass ratio?

Rolling-origin protocol as in eval_rolling.py (monthly refit on earlier data, 90-day decay for the
posterior counts, score the next month). Each variant is scored on the binary events "resolved within
threshold c" for every request (log-loss, Brier) and for the tract's all-complaints slot (what the default
map shows); differences are paired against the decayed-count nine-bin model, with SEs by bootstrap over
tract x type cells. Writes docs/kappa_source_evaluation.md.
"""
import json, os, sys
import numpy as np
import pandas as pd
import model as M
from eval_cutwise import load, binary_losses, CUT_LABELS, MIN_TRAIN_DAYS

ROOT = os.path.join(os.path.dirname(__file__), "..")
CUTS = list(range(M.K - 1))
VARIANTS = {
    "nine-bin, decayed κ (previous production)": M.Config("a", half_life_days=90.0),
    "nine-bin, raw κ": M.Config("b", half_life_days=90.0, kappa_source="raw"),
    "cutwise, decayed κ": M.Config("c", half_life_days=90.0, cutwise=True),
    "cutwise, raw κ": M.Config("d", half_life_days=90.0, cutwise=True, kappa_source="raw"),
    "cutwise, raw κ scaled by decay mass": M.Config("e", half_life_days=90.0, cutwise=True, kappa_source="raw_scaled"),
}
BASE = "nine-bin, decayed κ (previous production)"


def cum_pred(fm, sub, geo, tix, all_slot):
    ti = np.full(len(sub), len(tix)) if all_slot else sub["ctype"].map(tix).to_numpy()
    gi = sub["geoid"].map(geo.tract_ix); ok = gi.notna().to_numpy(); gi = gi.fillna(0).astype(int).to_numpy()
    bi = sub["boro"].map(geo.boro_ix).fillna(0).astype(int).to_numpy()
    p = np.where(ok[:, None], fm.bin_probs_tract()[gi, ti], fm.bin_probs_boro()[bi, ti])
    return np.cumsum(p, 1)[:, :-1]


def main():
    df, geo, types = load(); tix = {t: i for i, t in enumerate(types)}
    d0, end = df["created_date"].min(), df["created_date"].max()
    months = [m for m in pd.date_range(d0.normalize().replace(day=1) + pd.offsets.MonthBegin(1), end, freq="MS")
              if (m - d0).days >= MIN_TRAIN_DAYS and m + pd.offsets.MonthBegin(1) <= end + pd.Timedelta(days=1)]
    LL = {v: {a: [[] for _ in CUTS] for a in (False, True)} for v in VARIANTS}
    keys = []
    for m in months:
        train = df[df["created_date"] < m]
        test = df[(df["created_date"] >= m) & (df["created_date"] < m + pd.offsets.MonthBegin(1))]
        keys.append((test["geoid"].fillna("NA").astype(str) + "|" + test["ctype"]).to_numpy())
        bins = test["bin"].to_numpy()
        for v, cfg in VARIANTS.items():
            fm = M.fit(train, geo, types, cfg, m)
            for a in (False, True):
                cp = cum_pred(fm, test, geo, tix, a)
                for c in CUTS:
                    LL[v][a][c].append(binary_losses((bins <= c).astype(float), cp[:, c])[0].astype(np.float32))
        print("scored", m.strftime("%Y-%m"), flush=True)
    codes, _ = pd.factorize(np.concatenate(keys)); nc = codes.max() + 1
    cnt = np.bincount(codes, minlength=nc).astype(float)
    rng = np.random.default_rng(0); picks = [rng.integers(0, nc, nc) for _ in range(300)]
    def boot(x):
        x = np.concatenate(x); s = np.bincount(codes, weights=x, minlength=nc)
        return x.mean(), np.std([s[p].sum() / cnt[p].sum() for p in picks])
    out = [f"# Which counts should set the pooling strengths?\n",
           f"_Generated {pd.Timestamp.now().date()}; {len(months)} monthly refits ({months[0]:%Y-%m}..{months[-1]:%Y-%m}). "
           f"Δ log-loss vs the previous production model (nine-bin, κ fitted on decay-weighted counts); negative = better; ± bootstrap SE._\n"]
    for a, title in ((False, "Every request, scored on its own complaint type"), (True, "Scored from each tract's all-complaints distribution (default map)")):
        out += [f"\n## {title}\n", "| variant | " + " | ".join(CUT_LABELS) + " |", "|---|" + "---|" * len(CUTS)]
        for v in VARIANTS:
            if v == BASE: continue
            cells = []
            for c in CUTS:
                d = [x - y for x, y in zip(LL[v][a][c], LL[BASE][a][c])]
                mu, se = boot(d); cells.append(f"{mu:+.5f} ± {se:.5f}")
            out.append(f"| {v} | " + " | ".join(cells) + " |")
    open(os.path.join(ROOT, "docs", "kappa_source_evaluation.md"), "w").write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True); main()
