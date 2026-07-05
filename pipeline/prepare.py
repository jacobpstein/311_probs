"""Clean raw 311 pulls, assign census tracts, and bin resolution times.

Implements docs/model_spec.md §5 (censoring) and §6 (hygiene). Output:
  data/prepared.parquet  — one row per matured, cleaned request
  data/funnel.json       — row counts after each cleaning step
  data/geo_lookup.json   — tract geoid -> {nta, ntaname, boro}
"""

import glob
import json
import os

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from shapely.strtree import STRtree

ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW_GLOB = os.path.join(ROOT, "data", "raw", "sr_*.csv")
TRACTS = os.path.join(ROOT, "data", "tracts2020.geojson")

EDGES_H = np.array([3, 24, 48, 72, 168, 336, 480, 744], dtype=float)  # bin 9 = (744h, inf)
K = 9

# NYC bounding box for junk-coordinate rejection
LAT_RANGE = (40.45, 41.0)
LON_RANGE = (-74.3, -73.65)

BORO_NORM = {
    "MANHATTAN": "Manhattan", "BROOKLYN": "Brooklyn", "QUEENS": "Queens",
    "BRONX": "Bronx", "STATEN ISLAND": "Staten Island",
}

funnel = {}


def log_step(name: str, df: pd.DataFrame) -> None:
    funnel[name] = int(len(df))
    print(f"{name:.<46} {len(df):>9,}", flush=True)


def load_raw() -> pd.DataFrame:
    parts = sorted(glob.glob(RAW_GLOB))
    if not parts:
        raise SystemExit("no raw files found — run fetch_311.py first")
    dfs = []
    for p in parts:
        df = pd.read_csv(
            p,
            dtype={
                "unique_key": "int64", "complaint_type": "string", "descriptor": "string",
                "agency": "string", "status": "string", "borough": "string",
                "latitude": "float64", "longitude": "float64",
            },
            parse_dates=["created_date", "closed_date"],
            date_format="ISO8601",
        )
        dfs.append(df)
        print(f"loaded {os.path.basename(p)}: {len(df):,}", flush=True)
    return pd.concat(dfs, ignore_index=True)


def collapse_double_submissions(df: pd.DataFrame) -> pd.DataFrame:
    """§6.2: identical (type, descriptor, lat/lon@5dp) created within 60s -> keep earliest."""
    key = ["complaint_type", "descriptor", "lat5", "lon5"]
    df["lat5"] = df["latitude"].round(5)
    df["lon5"] = df["longitude"].round(5)
    df = df.sort_values(key + ["created_date"], kind="stable")
    same_key = (df[key] == df[key].shift()).all(axis=1) & df[key].notna().all(axis=1)
    gap = df["created_date"].diff().dt.total_seconds()
    dup = same_key & (gap <= 60)
    df = df[~dup].drop(columns=["lat5", "lon5"])
    return df.sort_index()  # restore original row order (dedup is order-independent)


def flag_batch_closures(df: pd.DataFrame) -> pd.Series:
    """§6.6: closures in (agency, minute) spikes exceeding max(500, 20% of agency median daily)."""
    closed = df[df["closed_date"].notna()]
    minute = closed["closed_date"].dt.floor("min")
    per_min = closed.groupby([closed["agency"], minute], observed=True).size()
    daily = closed.groupby([closed["agency"], closed["closed_date"].dt.floor("D")], observed=True).size()
    med_daily = daily.groupby(level=0, observed=True).median()
    thresh = np.maximum(500.0, 0.2 * med_daily)
    spike = per_min[per_min > thresh.reindex(per_min.index.get_level_values(0)).values]
    spike_set = set(spike.index)
    keys = list(zip(closed["agency"], minute))
    flagged = pd.Series(False, index=df.index)
    flagged.loc[closed.index] = [k in spike_set for k in keys]
    return flagged


def assign_tracts(df: pd.DataFrame) -> tuple[pd.Series, dict]:
    gj = json.load(open(TRACTS))
    geoms, geoid, lookup = [], [], {}
    for f in gj["features"]:
        p = f["properties"]
        geoms.append(shape(f["geometry"]))
        geoid.append(p["geoid"])
        lookup[p["geoid"]] = {"nta": p["nta2020"], "ntaname": p["ntaname"], "boro": p["boroname"]}
    tree = STRtree(geoms)
    geoid = np.array(geoid)

    ok = (
        df["latitude"].between(*LAT_RANGE) & df["longitude"].between(*LON_RANGE)
    ).to_numpy(dtype=bool)
    pts = shapely.points(df["longitude"].to_numpy()[ok], df["latitude"].to_numpy()[ok])
    pt_idx, poly_idx = tree.query(pts, predicate="intersects")
    # boundary points can match 2 tracts: keep the first match per point
    first = pd.Series(poly_idx).groupby(pt_idx).first()
    assigned = np.full(len(df), None, dtype=object)
    ok_positions = np.flatnonzero(ok)
    assigned[ok_positions[first.index.to_numpy()]] = geoid[first.to_numpy()]
    return pd.Series(assigned, index=df.index, dtype="string"), lookup


def main() -> None:
    df = load_raw()
    log_step("raw rows", df)

    df = df.drop_duplicates("unique_key")
    log_step("after unique_key dedupe", df)

    df["complaint_type"] = df["complaint_type"].str.strip().str.replace(r"\s+", " ", regex=True)

    df = collapse_double_submissions(df)
    log_step("after double-submission collapse", df)

    df = df[df["created_date"].notna()]
    log_step("after created_date parse", df)

    closed_null = (df["status"] == "Closed") & df["closed_date"].isna()
    funnel["closed_status_null_closed_date_dropped"] = int(closed_null.sum())
    df = df[~closed_null]
    log_step("after closed-but-no-closed_date drop", df)

    dur_h = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600.0
    df = df[~(dur_h < 0)]
    dur_h = dur_h.loc[df.index]
    log_step("after negative-duration drop", df)

    zero = dur_h == 0
    funnel["exact_zero_duration_dropped"] = int(zero.sum())
    df = df[~zero]
    dur_h = dur_h.loc[df.index]
    log_step("after zero-duration drop", df)

    sub_min = ((dur_h > 0) & (dur_h < 1 / 60)).groupby(df["complaint_type"], observed=True).sum()
    funnel["sub_minute_by_type_top"] = sub_min.nlargest(5).astype(int).to_dict()

    df["batch_closed"] = flag_batch_closures(df)
    funnel["batch_closed_flagged"] = int(df["batch_closed"].sum())
    print(f"batch-closure flagged: {df['batch_closed'].sum():,}", flush=True)

    df["geoid"], lookup = assign_tracts(df)
    df["boro_field"] = df["borough"].str.upper().map(BORO_NORM)
    has_geo = df["geoid"].notna()
    funnel["tract_assigned"] = int(has_geo.sum())
    df = df[has_geo | df["boro_field"].notna()]
    log_step("after geography filter", df)
    print(f"tract-assigned share: {has_geo.mean():.3f}", flush=True)

    # §5: all fetched rows were created >=31d before pull, so every row is matured.
    # closed -> duration bin; still open -> bin 9 (exactly, since already open >31d).
    dur_h = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600.0
    bins = np.where(dur_h.isna(), K - 1, np.searchsorted(EDGES_H, dur_h.fillna(0), side="left"))
    df["bin"] = bins.astype("int8")

    tract_meta = pd.DataFrame.from_dict(lookup, orient="index")
    df["nta"] = df["geoid"].map(tract_meta["nta"])
    df["boro"] = df["geoid"].map(tract_meta["boro"]).fillna(df["boro_field"])

    out = df[["created_date", "bin", "complaint_type", "agency", "geoid", "nta", "boro", "batch_closed"]].copy()
    for c in ["complaint_type", "agency", "geoid", "nta", "boro"]:
        out[c] = out[c].astype("category")
    out.to_parquet(os.path.join(ROOT, "data", "prepared.parquet"), index=False)
    json.dump(funnel, open(os.path.join(ROOT, "data", "funnel.json"), "w"), indent=2)
    json.dump(lookup, open(os.path.join(ROOT, "data", "geo_lookup.json"), "w"))
    print("wrote data/prepared.parquet", flush=True)

    open_share = (df["bin"] == K - 1).groupby(df["complaint_type"], observed=True).mean()
    print("\nbin distribution overall:", np.bincount(df["bin"], minlength=K) / len(df))
    print("month+ share top types:\n", open_share.nlargest(8))


if __name__ == "__main__":
    main()
