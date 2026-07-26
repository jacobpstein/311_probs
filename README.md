# How Fast Does New York Fix It?

**Live map → https://jacobpstein.github.io/311_probs/**

Interactive census-tract map of the probability a NYC 311 request is resolved within
different time windows, powered by a Bayesian hierarchical model fit on ~5.0M real
service requests (Jan 2025 – Jun 2026). Tap any of ~2,300 census tracts and any
complaint type to see the odds it gets resolved in hours, days, or a month. A companion
reproducible report (`docs/historical_analysis.qmd`) extends the same model back to 2010
to compare resolution odds across mayoral administrations, from Bloomberg to the current
Mamdani administration.

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
python3 pipeline/fetch_311.py      # ~5.0M rows into data/raw/ (one-time)
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

### The problem: small blocks
Some census tracts log thousands of requests; others log three. A busy block that closed
1,800 of 2,000 requests same-day gives a solid "90%." A quiet block that closed 2 of 3
gives "67%" — a coin flip dressed up as a statistic, where one different outcome swings it
to 33%. Mapping raw per-tract proportions draws a lie in bright colors.

### The approach: let small blocks borrow from their neighborhood
The fix is **partial pooling** (shrinkage): a tract with lots of data speaks for itself; a
tract with little data leans on its surrounding neighborhood, then its borough, then the
city. Concretely, resolution outcomes are modeled as a **hierarchical Dirichlet-Multinomial
over 9 ordered resolution-time bins**, pooled *within complaint type across geography*
(tract → NTA → borough → citywide), because resolution time is driven far more by
complaint type / responsible agency than by geography. Each estimate's shrinkage weight
`w = n / (n + κ)` is set by how much local data the cell has relative to a fitted
concentration κ — not a hand-picked constant. Every published estimate ships with a
**data-strength indicator** and uncertainty bands, so the map is honest about how much of
an estimate is the block's own record versus a borrowed neighborhood estimate.

### Winning config: P5a
Empirical-Bayes concentration per (type, level) by bounded MLE on the exact
Dirichlet-Multinomial marginal likelihood, exponential time decay (90-day half-life), and
90% intervals calibrated with a per-type regime-variance component estimated from rolling
temporal holdouts. Selected by lowest ranked probability score (RPS) on a 12-month-train /
5-month-test temporal holdout, over candidates P0–P5c (`docs/evaluation_results.md`).

### Validation
The estimator survived an adversarial audit (`docs/statistical_review.md`) that
re-implemented the core math independently and re-checked all 51,150 published estimates.
It found and fixed two defects: (1) the pooling routine used Minka's fixed-point iteration,
which converged well short of the true optimum on this data and under-pooled small blocks —
replaced with direct optimization of the marginal likelihood over κ; and (2) the credible
intervals were overconfident — an even/odd calendar-day split (no possible time trend
between halves) showed nominal 90% intervals covering reality only ~50% of the time, so an
additive **regime-variance** term for month-to-month drift was added, restoring coverage.
A same-season-last-year blending kernel was tested and *not* adopted (a statistical dead
heat on the holdout).

### What the historical analysis found
Refitting the model to 2010–2026 (`docs/historical_analysis.qmd`) surfaces three findings
that survive the composition and artifact controls: (1) most of the apparent citywide
speed-up is **composition** — the complaint mix shifting toward fast-closing categories
(noise), not agencies getting faster; (2) trajectories are **agency-shaped, not
administration-shaped** — HPD housing types climbed across every era while infrastructure
types slipped, none of it starting or stopping at an inauguration; and (3) COVID was a
**composition shock**, not a slowdown, and is quarantined from any administration's record.

See `docs/METHODS.md` and `docs/model_spec.md` for full methodology.
