# How Fast Does New York Fix It?

**Live map → https://jacobpstein.github.io/311_probs/**  ·  **Historical analysis → https://jacobpstein.github.io/311_probs/analysis/**

Data: [NYC Open Data — 311 Service Requests from 2010 to Present](https://data.cityofnewyork.us/resource/erm2-nwe9) (dataset `erm2-nwe9`, City of New York, retrieved through the Socrata API). Not affiliated with the City of New York.

Interactive census-tract map of the probability a NYC 311 request is resolved within
different time windows, powered by a Bayesian hierarchical model fit on a rolling
two-year window of real service requests, refreshed weekly. Tap any of ~2,300 census tracts and any
complaint type to see the odds it gets resolved in hours, days, or a month. A companion
reproducible report (`docs/historical_analysis.qmd`) extends the same model back to 2010
to compare resolution odds across mayoral administrations, from Bloomberg to the current
Mamdani administration.

## Layout
- `pipeline/` — data + model
  - `fetch_311.py`          Download a rolling two-year 311 window from NYC Open Data (Socrata), month by month
  - `fetch_311_history.py`  Download the 2010–2024 archive for the historical analysis
  - `prepare.py`            Cleaning, tract point-in-polygon, censoring, 9-bin durations
  - `prepare_hist.py`       Same cleaning applied year-by-year to the historical pulls
  - `model.py`              Hierarchical cascade (one pooling strength per threshold), EB concentration, interval calibration
  - `types.json`            Pinned complaint-type list (everything else is grouped as "Other")
  - `export_web.py`         Fit the shipped model, export the web/data payload and geometry
  - `validate_export.py`    Sanity gate on the export (freshness, volume, tract counts, invariants); blocks publishing on failure
  - `audit.py`              Independent end-to-end audit: raw files → export, every cell, with its own re-implementation of the per-threshold hierarchies
  - `evaluate.py`           Single-split prior comparison (P0–P7a)
  - `eval_rolling.py`       Rolling-origin comparison (refit monthly, score the next month): decay half-life, seasonal blending
  - `eval_cutwise.py`       Per-threshold pooling vs the nine-bin model (the evidence for the shipped design)
  - `eval_kappa_source.py`  Whether pooling strengths should be fitted on decay-weighted or raw counts (decay-weighted kept)
  - `eval_intervals_rolling.py`  Interval coverage under the deployed protocol
  - `robustness_checks.py`  Per-type calibration, day-clustering of outcomes, batch-closure sensitivity
  - `sim_check.py`          Simulation of the cascade against known truth: accuracy and interval coverage
  - `stan_check.py`         Full-Bayes check of the cascade in Stan (needs CmdStan and `cmdstanpy`); program in `stan/hier_dm.stan`
- `web/`  — static MapLibre single-page app (open via any static server)
- `docs/`
  - `METHODS.md`               Layered plain-language + technical methods writeup
  - `model_spec.md`            Full model specification
  - `design_spec.md`           UI/UX specification
  - `evaluation_results.md`    Single-split results, generated, with interpretation from `evaluation_notes.md`
  - `rolling_evaluation.md`    Rolling-origin results (generated)
  - `simulation_check.md`      Simulation results (generated)
  - `stan_validation.md`       Stan comparison results (generated)
  - `cutwise_evaluation.md`    Cutwise-vs-nine-bin results (generated)
  - `kappa_source_evaluation.md`  Decayed vs raw counts for pooling strengths (generated)
  - `interval_calibration_rolling.md`  Interval coverage by type under the deployed protocol (generated)
  - `robustness_checks.md`     Per-type calibration, outcome clustering, batch-closure sensitivity (generated)
  - `statistical_review.md`    Adversarial audits and the corrections they led to
  - `historical_analysis.qmd`  Reproducible Quarto writeup: resolution odds across administrations (renders to `.html`)

## Run the pipeline
```
python3 pipeline/fetch_311.py      # rolling two-year window into data/raw/
python3 pipeline/prepare.py        # -> data/prepared.parquet
python3 pipeline/evaluate.py       # -> docs/evaluation_results.md (prior comparison)
python3 pipeline/export_web.py     # -> web/data/{tracts.geojson,probs.json,meta.json}
```

## Automated data refresh

`.github/workflows/refresh-data.yml` keeps the live map current without manual work. Every
Monday (and on demand from the Actions tab) it:

1. pulls a rolling two-year window of 311 data ending 31 days ago (the maturity cutoff),
2. cleans it, refits the model, and exports the map payload,
3. runs `pipeline/validate_export.py` — the run stops here, publishing nothing, if the
   data is stale, the pull looks truncated, or any posterior violates basic invariants,
4. commits the refreshed `web/data/` and redeploys GitHub Pages.

The complaint-type list is pinned in `pipeline/types.json` (grouping everything else into
"Other") so a refresh can't silently add or drop a chip when a borderline or seasonal type
crosses the top-20 line; each run prints how the pinned list has drifted from current
volume, for a deliberate review.

The map shows its own data window ("Requests Aug 2024 – Aug 2026 · refreshed …") so
freshness is always visible. An optional `SOCRATA_APP_TOKEN` repository secret raises
Socrata's rate limits.

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
city. Concretely, the probability of being resolved within each of eight thresholds (3 hours
to 31 days) is modeled by its own **hierarchical Beta-Binomial** (a two-category Dirichlet),
each with its own pooling strength, pooled *within complaint type across geography*
(tract → NTA → borough → citywide), because resolution time is driven far more by
complaint type / responsible agency than by geography. Each estimate's shrinkage weight
`w = n / (n + κ)` is set by how much local data the cell has relative to a fitted
concentration κ — not a hand-picked constant. Every published estimate ships with a
**data-strength indicator** and uncertainty bands, so the map is honest about how much of
an estimate is the block's own record versus a borrowed neighborhood estimate.

### Shipped config: P7a (per-threshold pooling)
Eight independent two-category hierarchies (bins ≤ c versus later), each with empirical-Bayes
concentrations per (type, level) by bounded MLE on the exact marginal likelihood, exponential
time decay (90-day half-life), a running maximum across thresholds so the curve never
decreases, and 90% intervals calibrated with a per-type regime-variance component estimated
from rolling temporal holdouts. It replaced the earlier single-strength nine-bin model (P5a)
because one strength shared across all bins is dominated by the quiet bins and over-pools the
rates the map shows: within-borough spread of P(≤24h) across tracts roughly doubles to triples
for heat, water, encampment and street-condition complaints, and rolling-origin log-loss
improves at every threshold (`docs/cutwise_evaluation.md`, `docs/rolling_evaluation.md`).

### Validation
The estimator survived an adversarial audit (`docs/statistical_review.md`) that
re-implemented the core math independently and re-checked all 51,150 published estimates.
It found and fixed defects and limitations, including: (1) the pooling routine used Minka's fixed-point iteration,
which converged well short of the true optimum on this data and under-pooled small blocks —
replaced with direct optimization of the marginal likelihood over κ; and (2) the credible
intervals were overconfident — an even/odd calendar-day split (no possible time trend
between halves) showed nominal 90% intervals covering reality only ~50% of the time, so an
additive **regime-variance** term for month-to-month drift was added, which brings coverage
close to nominal on the evaluation split. A later follow-up (`docs/robustness_checks.md`)
showed most of that even/odd shortfall was a comparison artifact (the held-out half is itself
a finite sample) plus day-to-day clustering of outcomes, and that batch closures are not the
cause. Other findings from the audits: requests with no tract had been counted in one tract
(fixed and guarded by export checks); the intervals originally ignored the uncertainty of the
neighborhood mean a tract borrows (fixed); and one pooling strength shared across all bins
over-smoothed the 24-hour rate (fixed by the per-threshold model above). A same-season-last-year
blending kernel, a sibling-only prior, pooling strengths fitted on raw counts and a lower
holdout threshold for the interval calibration were tested and *not* adopted.

**Known limitation.** Under the deployed protocol (regime variance re-estimated before each
of 11 months, next month scored) the nominal 90% intervals cover about 87% of tract × type
cells; Snow or Ice and Noise - Street/Sidewalk are the weakest types
(`docs/interval_calibration_rolling.md`).

### What the historical analysis found
Refitting the model to 2010–2026 ([live report](https://jacobpstein.github.io/311_probs/analysis/), source `docs/historical_analysis.qmd`) surfaces three findings
that survive the composition and artifact controls: (1) most of the apparent citywide
speed-up is **composition** — the complaint mix shifting toward fast-closing categories
(noise), not agencies getting faster; (2) trajectories are **agency-shaped, not
administration-shaped** — HPD housing types climbed across every era while infrastructure
types slipped, none of it starting or stopping at an inauguration; and (3) COVID was a
**composition shock**, not a slowdown, and is quarantined from any administration's record.

See `docs/METHODS.md` and `docs/model_spec.md` for full methodology.
