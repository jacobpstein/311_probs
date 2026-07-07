# How Fast Does New York Fix It?

Interactive census-tract map of the probability a NYC 311 request is resolved within
different time windows, powered by a Bayesian hierarchical model fit on 5.3M real
service requests (Jan 2025 – Jun 2026). A companion reproducible report
(`docs/historical_analysis.qmd`) extends the same model back to 2010 to compare
resolution odds across mayoral administrations.

## Layout
- `pipeline/` — data + model
  - `fetch_311.py`          Download the recent (2025–) 311 window from NYC Open Data (Socrata)
  - `fetch_311_history.py`  Download the 2010–2024 archive for the historical analysis
  - `prepare.py`            Cleaning, tract point-in-polygon, censoring, 9-bin durations
  - `prepare_hist.py`       Same cleaning applied year-by-year to the historical pulls
  - `model.py`              Hierarchical Dirichlet-Multinomial cascade, EB concentration, interval calibration
  - `evaluate.py`           Prior comparison (P0–P5c) with temporal holdout
  - `eval_seasonal.py`      Rolling-monthly test of same-season-last-year blending (not adopted)
  - `export_web.py`         Fit winning config, export web/data payload + geometry + update state
  - `update.py`             Incremental monthly decay-then-add update
- `web/`  — static MapLibre single-page app (open via any static server)
- `docs/`
  - `METHODS.md`               Layered plain-language + technical methods writeup
  - `model_spec.md`            Full model specification
  - `design_spec.md`           UI/UX specification
  - `evaluation_results.md`    Prior comparison results and interpretation
  - `statistical_review.md`    Adversarial audit that motivated the estimator and interval fixes
  - `historical_analysis.qmd`  Reproducible Quarto writeup: resolution odds across administrations (renders to `.html`)

## Run the pipeline
```
python3 pipeline/fetch_311.py      # ~5.3M rows into data/raw/ (one-time)
python3 pipeline/prepare.py        # -> data/prepared.parquet
python3 pipeline/evaluate.py       # -> docs/evaluation_results.md (prior comparison)
python3 pipeline/export_web.py     # -> web/data/{tracts.geojson,probs.json,meta.json}
```

## Run the app
```
python3 -m http.server 8012 --directory web
# open http://localhost:8012
```

## Historical analysis (optional)
```
python3 pipeline/fetch_311_history.py         # ~38.6M rows into data/raw_hist/ (one-time)
python3 pipeline/prepare_hist.py --all        # -> data/prepared_hist/year=*.parquet
quarto render docs/historical_analysis.qmd    # -> docs/historical_analysis.html
```

## Model
Hierarchical Dirichlet-Multinomial over 9 ordered resolution-time bins with partial
pooling tract → NTA → borough → citywide, per complaint type. Winning config **P5a**:
empirical-Bayes concentration per (type, level) by bounded MLE on the exact
Dirichlet-Multinomial marginal likelihood, exponential time decay (90-day half-life),
and 90% intervals calibrated with a per-type regime-variance component estimated from
rolling temporal holdouts. Selected by lowest ranked probability score on a
12-month-train / 5-month-test temporal holdout. See docs/ for full methodology and
docs/statistical_review.md for the audit that motivated the calibration.
