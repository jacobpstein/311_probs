# How Fast Does New York Fix It?

Interactive census-tract map of the probability a NYC 311 request is resolved within
different time windows, powered by a Bayesian hierarchical model fit on 5.3M real
service requests (Jan 2025 – Jun 2026).

## Layout
- `pipeline/` — data + model
  - `fetch_311.py`   Download 311 CSV pulls from NYC Open Data (Socrata)
  - `prepare.py`     Cleaning, tract point-in-polygon, censoring, 9-bin durations
  - `model.py`       Hierarchical Dirichlet-Multinomial cascade + EB concentration
  - `evaluate.py`    Prior comparison (P0–P5c) with temporal holdout
  - `export_web.py`  Fit winning config, export web/data payload + geometry
  - `update.py`      Incremental monthly decay-then-add update
- `web/`  — static MapLibre single-page app (open via any static server)
- `docs/` — design_spec.md, model_spec.md, evaluation_results.md

## Run the pipeline
```
python3 pipeline/fetch_311.py      # ~5.3M rows into data/raw/ (one-time)
python3 pipeline/prepare.py        # -> data/prepared.parquet
python3 pipeline/evaluate.py       # -> docs/evaluation_results.md (prior comparison)
python3 pipeline/export_web.py     # -> web/data/{tracts.geojson,probs.json,meta.json}
```

## Run the app
```
python3 -m http.server 8011 --directory web
# open http://localhost:8011
```

## Model
Hierarchical Dirichlet-Multinomial over 9 ordered resolution-time bins with partial
pooling tract → NTA → borough → citywide, per complaint type. Winning config **P5a**:
empirical-Bayes concentration per (type, level) via Minka's fixed point, exponential
time decay (90-day half-life). Selected by lowest ranked probability score on a
12-month-train / 5-month-test temporal holdout. See docs/ for full methodology.
