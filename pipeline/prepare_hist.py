"""Clean the historical 311 pulls (2010-2024) with the same hygiene as prepare.py,
processing one year at a time to bound memory (~3M rows/year vs 38M total).

Output: data/prepared_hist/year=YYYY.parquet  (same columns as prepared.parquet)
        data/funnel_hist.json                 (per-year cleaning funnels)

All historical requests matured years ago, so the §5 censoring rule reduces to:
closed -> duration bin, never-closed -> bin 9.
"""

import glob
import json
import os
import re
from collections import defaultdict

import numpy as np
import pandas as pd

import prepare as P

ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW_DIR = os.path.join(ROOT, "data", "raw_hist")
OUT_DIR = os.path.join(ROOT, "data", "prepared_hist")


def year_files(include_max_year: bool) -> dict[int, list[str]]:
    """Group quarter files by year. The downloader works chronologically, so the
    max year present may still be mid-download; skip it unless --all is passed."""
    by_year = defaultdict(list)
    for p in sorted(glob.glob(os.path.join(RAW_DIR, "sr_*Q*_p*.csv"))):
        year = int(re.search(r"sr_(\d{4})Q", os.path.basename(p)).group(1))
        by_year[year].append(p)
    if by_year and not include_max_year:
        by_year.pop(max(by_year))
    return dict(by_year)


def prepare_year(year: int, files: list[str]) -> dict:
    dfs = [pd.read_csv(
        p,
        dtype={"unique_key": "int64", "complaint_type": "string", "descriptor": "string",
               "agency": "string", "status": "string", "borough": "string",
               "latitude": "float64", "longitude": "float64"},
        parse_dates=["created_date", "closed_date"], date_format="ISO8601",
    ) for p in files]
    df = pd.concat(dfs, ignore_index=True)
    # read_csv's parse_dates falls back to object dtype silently when a column
    # contains unparseable values (the 2010-2019 archive has some); coerce hard.
    for c in ["created_date", "closed_date"]:
        if df[c].dtype == object:
            df[c] = pd.to_datetime(df[c], format="ISO8601", errors="coerce")
    funnel = {"raw": len(df)}

    df = df.drop_duplicates("unique_key")
    df["complaint_type"] = df["complaint_type"].str.strip().str.replace(r"\s+", " ", regex=True)
    df = P.collapse_double_submissions(df)
    funnel["after_double_submission"] = len(df)

    df = df[df["created_date"].notna()]
    closed_null = (df["status"] == "Closed") & df["closed_date"].isna()
    funnel["closed_null_dropped"] = int(closed_null.sum())
    df = df[~closed_null]

    dur_h = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600.0
    df = df[~(dur_h < 0)]
    dur_h = dur_h.loc[df.index]
    zero = dur_h == 0
    funnel["zero_duration_dropped"] = int(zero.sum())
    df = df[~zero]
    funnel["after_duration_filters"] = len(df)

    df["batch_closed"] = P.flag_batch_closures(df)
    funnel["batch_flagged"] = int(df["batch_closed"].sum())

    df["geoid"], lookup = P.assign_tracts(df)
    df["boro_field"] = df["borough"].str.upper().map(P.BORO_NORM)
    has_geo = df["geoid"].notna()
    funnel["tract_share"] = round(float(has_geo.mean()), 4)
    df = df[has_geo | df["boro_field"].notna()]
    funnel["after_geography"] = len(df)

    dur_h = (df["closed_date"] - df["created_date"]).dt.total_seconds() / 3600.0
    df["bin"] = np.where(dur_h.isna(), P.K - 1,
                         np.searchsorted(P.EDGES_H, dur_h.fillna(0), side="left")).astype("int8")

    tract_meta = pd.DataFrame.from_dict(lookup, orient="index")
    df["nta"] = df["geoid"].map(tract_meta["nta"])
    df["boro"] = df["geoid"].map(tract_meta["boro"]).fillna(df["boro_field"])

    out = df[["created_date", "bin", "complaint_type", "agency",
              "geoid", "nta", "boro", "batch_closed"]].copy()
    for c in ["complaint_type", "agency", "geoid", "nta", "boro"]:
        out[c] = out[c].astype("category")
    out.to_parquet(os.path.join(OUT_DIR, f"year={year}.parquet"), index=False)
    return funnel


def main() -> None:
    import sys
    include_all = "--all" in sys.argv
    os.makedirs(OUT_DIR, exist_ok=True)
    funnels = {}
    fpath = os.path.join(ROOT, "data", "funnel_hist.json")
    if os.path.exists(fpath):
        funnels = json.load(open(fpath))
    for year, files in year_files(include_all).items():
        if str(year) in funnels and os.path.exists(os.path.join(OUT_DIR, f"year={year}.parquet")):
            print(f"{year}: already prepared, skipping", flush=True)
            continue
        f = prepare_year(year, files)
        funnels[str(year)] = f
        json.dump(funnels, open(fpath, "w"), indent=2)
        print(f"{year}: {f['raw']:,} raw -> {f['after_geography']:,} kept "
              f"(tract share {f['tract_share']})", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
