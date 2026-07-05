"""Download NYC 311 service requests from NYC Open Data (Socrata) in paged CSV pulls.

Pulls only the fields the model needs, for requests created in [START, END).
END is set ~30 days before the pull date so every request's 31-day window is
observable (right-censoring rule in docs/model_spec.md §5).
"""

import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://data.cityofnewyork.us/resource/erm2-nwe9.csv"
FIELDS = "unique_key,created_date,closed_date,complaint_type,descriptor,agency,status,borough,latitude,longitude"
START = "2025-01-01T00:00:00"
END = "2026-06-03T00:00:00"
PAGE = 500_000
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def fetch_page(offset: int, dest: str, retries: int = 5) -> int:
    params = {
        "$select": FIELDS,
        "$where": f"created_date between '{START}' and '{END}'",
        "$order": "unique_key",
        "$limit": str(PAGE),
        "$offset": str(offset),
    }
    url = BASE + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/csv"})
            with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as f:
                while chunk := resp.read(1 << 20):
                    f.write(chunk)
            with open(dest) as f:
                n = sum(1 for _ in f) - 1  # minus header
            return n
        except Exception as e:  # noqa: BLE001
            wait = 2 ** (attempt + 2)
            print(f"  page offset={offset} attempt {attempt + 1} failed: {e}; retry in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"page at offset {offset} failed after {retries} attempts")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    offset = 0
    part = 0
    while True:
        dest = os.path.join(OUT_DIR, f"sr_{part:03d}.csv")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            with open(dest) as f:
                n = sum(1 for _ in f) - 1
            print(f"part {part}: exists with {n} rows, skipping", flush=True)
        else:
            t0 = time.time()
            n = fetch_page(offset, dest)
            print(f"part {part}: {n} rows in {time.time() - t0:.0f}s", flush=True)
        if n < PAGE:
            print(f"DONE: {offset + n} total rows across {part + 1} parts", flush=True)
            break
        offset += PAGE
        part += 1


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
