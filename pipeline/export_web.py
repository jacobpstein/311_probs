"""Fit the winning config (P5a) on all matured data and export the web payload.

Outputs into web/data/:
  tracts.geojson  — simplified tract polygons (geoid, ntaname, boro) for the map join
  probs.json      — compact per tract x type posterior summaries
  meta.json       — types, bin labels/edges, citywide + borough reference profiles,
                    model provenance, per-type flags
"""

import json
import os

import numpy as np
import pandas as pd
from scipy.stats import beta
from shapely.geometry import mapping, shape

import model as M

ROOT = os.path.join(os.path.dirname(__file__), "..")
WEB_DATA = os.path.join(ROOT, "web", "data")
N_TYPES = 20
HALF_LIFE = 90.0
SIMPLIFY_TOL = 0.00015  # ~15 m; keeps borough coastlines crisp, ~halves file size

BIN_LABELS = ["≤3 hrs", "3–24 hrs", "1–2 days", "2–3 days", "3–7 days",
              "1–2 weeks", "2–3 weeks", "3–4 weeks", "1 month+"]
CUM_LABELS = ["3 hours", "24 hours", "2 days", "3 days", "1 week",
              "2 weeks", "3 weeks", "1 month"]


def r3(x):
    return round(float(x), 3)


def main() -> None:
    os.makedirs(WEB_DATA, exist_ok=True)
    df = pd.read_parquet(os.path.join(ROOT, "data", "prepared.parquet"))
    geo_lookup = json.load(open(os.path.join(ROOT, "data", "geo_lookup.json")))
    df["created_date"] = pd.to_datetime(df["created_date"])
    for c in ["geoid", "nta", "boro", "complaint_type"]:
        df[c] = df[c].astype(str)
    geo = M.GeoIndex(geo_lookup)

    top_types = df["complaint_type"].value_counts().nlargest(N_TYPES).index.tolist()
    types = top_types + ["Other"]
    df["ctype"] = M.collapse_types(df["complaint_type"], top_types)
    t_ref = df["created_date"].max()

    cfg = M.Config("P5a", kappa_mode="per_type_level", half_life_days=HALF_LIFE)
    print("fitting P5a on all matured data...", flush=True)
    fm = M.fit(df, geo, types, cfg, t_ref)
    T = len(types)                      # named types; slot T = ALL
    ship_types = ["ALL"] + types        # UI order: All complaints first

    # per-type flags (§6.5, §6.8, §5)
    dur_note = df.groupby("ctype", observed=True)["bin"].agg(
        open_share=lambda s: float((s == M.K - 1).mean()))
    flags = {}
    for t in types:
        os_ = float(dur_note.loc[t, "open_share"]) if t in dur_note.index else 0.0
        flags[t] = {"high_open_share": os_ > 0.20}
    flags["ALL"] = {"high_open_share": bool(df["bin"].eq(M.K - 1).mean() > 0.20)}

    # --- posterior summaries at tract level ---
    a = fm.a_tract                       # (n_tract, T+1, K)
    A = a.sum(-1)                        # (n_tract, T+1)
    bp = a / A[..., None]                # posterior mean per bin
    cum = bp.cumsum(-1)[..., :-1]        # (n_tract, T+1, 8)
    n_obs = fm.R_tract.sum(-1)           # raw counts (n_tract, T+1)
    shrink = fm.shrinkage()             # (n_tract, T+1)

    # 90% CIs on each of the 8 cumulative cuts
    Ac = a.cumsum(-1)[..., :-1]          # (n_tract, T+1, 8)
    Arest = A[..., None] - Ac
    lo = beta.ppf(0.05, Ac, Arest)
    hi = beta.ppf(0.95, Ac, Arest)

    def type_slot(name):
        return T if name == "ALL" else types.index(name)

    data = {}
    for gi, geoid in enumerate(geo.tracts):
        cell = {}
        for st in ship_types:
            ti = type_slot(st)
            cell[st] = {
                "bp": [r3(x) for x in bp[gi, ti]],
                "lo": [r3(x) for x in lo[gi, ti]],
                "hi": [r3(x) for x in hi[gi, ti]],
                "n": int(n_obs[gi, ti]),
                "sw": r3(shrink[gi, ti]),
            }
        data[geoid] = cell
    print(f"built {len(data)} tract records x {len(ship_types)} types", flush=True)

    # reference profiles (borough + citywide) for the "compare to" affordance
    def summarize(a_vec):
        av = a_vec / a_vec.sum(-1, keepdims=True)
        return [r3(x) for x in av.cumsum(-1)[..., :-1]]
    refs = {"city": {}, "boro": {}}
    for st in ship_types:
        ti = type_slot(st)
        refs["city"][st] = summarize(fm.a_city[0, ti])
        for bi, bname in enumerate(geo.boros):
            refs["boro"].setdefault(bname, {})[st] = summarize(fm.a_boro[bi, ti])

    # --- geometry ---
    gj = json.load(open(os.path.join(ROOT, "data", "tracts2020.geojson")))
    feats = []
    for f in gj["features"]:
        p = f["properties"]
        if p["geoid"] not in data:
            continue
        g = shape(f["geometry"]).simplify(SIMPLIFY_TOL, preserve_topology=True)
        if g.is_empty:
            continue
        feats.append({
            "type": "Feature",
            "geometry": mapping(g),
            "properties": {"geoid": p["geoid"], "nta": p["ntaname"], "boro": p["boroname"]},
        })
    out_geo = {"type": "FeatureCollection", "features": feats}

    json.dump(out_geo, open(os.path.join(WEB_DATA, "tracts.geojson"), "w"))
    json.dump(data, open(os.path.join(WEB_DATA, "probs.json"), "w"), separators=(",", ":"))
    meta = {
        "types": ship_types,
        "bin_labels": BIN_LABELS,
        "cum_labels": CUM_LABELS,
        "edges_h": [3, 24, 48, 72, 168, 336, 480, 744],
        "refs": refs,
        "flags": flags,
        "model": {
            "config": "P5a (hierarchical Dirichlet-Multinomial, EB κ, 90-day decay)",
            "data_through": str(t_ref.date()),
            "n_requests": int(len(df)),
            "n_tracts": len(data),
            "updated_at": str(pd.Timestamp.now().date()),
        },
    }
    json.dump(meta, open(os.path.join(WEB_DATA, "meta.json"), "w"))

    for fn in ["tracts.geojson", "probs.json", "meta.json"]:
        sz = os.path.getsize(os.path.join(WEB_DATA, fn)) / 1e6
        print(f"  {fn}: {sz:.2f} MB", flush=True)


if __name__ == "__main__":
    main()
