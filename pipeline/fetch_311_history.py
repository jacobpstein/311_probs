"""Download historical NYC 311 service requests (2010 - 2024) for era analysis.

Sources (schemas verified identical):
  76ig-c548  311 Service Requests from 2010 to 2019 (static archive)
  erm2-nwe9  311 Service Requests from 2020 to Present

Pulls quarterly windows into data/raw_hist/, one or more 500k-row pages per
quarter, resumable per page (existing non-empty files are skipped). The current
pipeline's window (2025-01+) is already in data/raw/ and is not re-downloaded.
"""

import os
import sys
import time
import urllib.parse
import urllib.request

FIELDS = ("unique_key,created_date,closed_date,complaint_type,descriptor,"
          "agency,status,borough,latitude,longitude")
PAGE = 500_000
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw_hist")

def dataset_for(year: int) -> str:
    return "76ig-c548" if year < 2020 else "erm2-nwe9"

def quarters():
    for year in range(2010, 2025):
        for q, (m0, m1) in enumerate([(1, 4), (4, 7), (7, 10), (10, 13)], 1):
            start = f"{year}-{m0:02d}-01T00:00:00"
            end = f"{year + 1}-01-01T00:00:00" if m1 == 13 else f"{year}-{m1:02d}-01T00:00:00"
            yield year, q, start, end

def fetch_page(dataset: str, start: str, end: str, offset: int, dest: str,
               retries: int = 6) -> int:
    params = {
        "$select": FIELDS,
        "$where": f"created_date >= '{start}' AND created_date < '{end}'",
        "$order": "unique_key",
        "$limit": str(PAGE),
        "$offset": str(offset),
    }
    url = f"https://data.cityofnewyork.us/resource/{dataset}.csv?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/csv"})
            with urllib.request.urlopen(req, timeout=900) as resp, open(dest, "wb") as f:
                while chunk := resp.read(1 << 20):
                    f.write(chunk)
            with open(dest) as f:
                return sum(1 for _ in f) - 1
        except Exception as e:  # noqa: BLE001
            wait = 2 ** (attempt + 2)
            print(f"  {os.path.basename(dest)} attempt {attempt + 1} failed: {e}; retry in {wait}s",
                  flush=True)
            time.sleep(wait)
    raise RuntimeError(f"{dest} failed after {retries} attempts")

def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    total = 0
    for year, q, start, end in quarters():
        ds = dataset_for(year)
        part = 0
        while True:
            dest = os.path.join(OUT_DIR, f"sr_{year}Q{q}_p{part:02d}.csv")
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                with open(dest) as f:
                    n = sum(1 for _ in f) - 1
                print(f"{year}Q{q} p{part}: exists ({n:,})", flush=True)
            else:
                t0 = time.time()
                n = fetch_page(ds, start, end, part * PAGE, dest)
                print(f"{year}Q{q} p{part}: {n:,} rows in {time.time() - t0:.0f}s", flush=True)
            total += n
            if n < PAGE:
                break
            part += 1
    print(f"DONE: {total:,} historical rows", flush=True)

if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
