"""Download NYC 311 service requests from NYC Open Data (Socrata) into data/raw/.

Fetches one calendar month at a time and pages *within* each month. This keeps
every $offset small — Socrata degrades badly on deep global offsets (a full
two-year pull paginated by global offset can take hours), but bounded per-month
queries stay fast and reliable, which is what makes the scheduled refresh
(.github/workflows/refresh-data.yml) practical.

Window: [START, END). END is set ~31 days before the run date so every kept
request has its full 31-day resolution window observable (docs/model_spec.md §5).
Both dates can be overridden with the SR_START / SR_END environment variables
(by default the window is rolling: two years ending 31 days ago).
"""

import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASE = "https://data.cityofnewyork.us/resource/erm2-nwe9.csv"
FIELDS = ("unique_key,created_date,closed_date,complaint_type,descriptor,"
          "agency,status,borough,latitude,longitude")
# Default window: rolling two years ending 31 days ago (full maturity for every row).
_END_DEFAULT = (datetime.now() - timedelta(days=31)).replace(hour=0, minute=0, second=0, microsecond=0)
END = os.environ.get("SR_END", _END_DEFAULT.isoformat())
START = os.environ.get("SR_START", (datetime.fromisoformat(END) - timedelta(days=730)).isoformat())
PAGE = 50_000
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
APP_TOKEN = os.environ.get("SOCRATA_APP_TOKEN")  # optional; raises rate limits


def month_windows(start: str, end: str):
    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)
    cur = s.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while cur < e:
        nxt = (cur.replace(day=28) + timedelta(days=7)).replace(day=1)
        yield max(cur, s), min(nxt, e)
        cur = nxt


def fetch(where: str, offset: int, dest: str, retries: int = 6) -> int:
    params = {
        "$select": FIELDS, "$where": where, "$order": "created_date,unique_key",
        "$limit": str(PAGE), "$offset": str(offset),
    }
    if APP_TOKEN:
        params["$$app_token"] = APP_TOKEN
    url = BASE + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/csv"})
            with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as f:
                while chunk := resp.read(1 << 20):
                    f.write(chunk)
            with open(dest) as f:
                return sum(1 for _ in f) - 1  # minus header
        except Exception as e:  # noqa: BLE001
            wait = 2 ** (attempt + 1)
            print(f"  {os.path.basename(dest)} attempt {attempt + 1} failed: {e}; "
                  f"retry in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"{dest} failed after {retries} attempts")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"window {START} .. {END}  (app_token: {'yes' if APP_TOKEN else 'no'})", flush=True)
    total = 0
    for w0, w1 in month_windows(START, END):
        tag = w0.strftime("%Y_%m")
        where = f"created_date >= '{w0.isoformat()}' AND created_date < '{w1.isoformat()}'"
        page = 0
        while True:
            dest = os.path.join(OUT_DIR, f"sr_{tag}_{page:02d}.csv")
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                with open(dest) as f:
                    n = sum(1 for _ in f) - 1
            else:
                t0 = time.time()
                n = fetch(where, page * PAGE, dest)
                print(f"{tag} p{page}: {n:,} rows in {time.time() - t0:.0f}s", flush=True)
            total += n
            if n < PAGE:
                break
            page += 1
    print(f"DONE: {total:,} rows across {START[:7]}..{END[:7]}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    main()
