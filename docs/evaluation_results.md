# Prior Comparison Results

_Generated 2026-07-05. Train 2025-01-01–2026-01-01 (3,422,381 requests), test 2026-01-01–2026-06-03 (1,619,581 requests)._


**Complaint types modeled (21):** Illegal Parking, Noise - Residential, HEAT/HOT WATER, Blocked Driveway, Noise - Street/Sidewalk, UNSANITARY CONDITION, Abandoned Vehicle, Street Condition, PLUMBING, Noise - Commercial, Dirty Condition, Water System, Noise, PAINT/PLASTER, Encampment, Traffic Signal Condition, Missed Collection, DOOR/WINDOW, Derelict Vehicles, Noise - Vehicle, Other


## Selection


**Winner (lowest overall RPS, guardrails in §7.4): `P5a P4 + decay h=90d`**


## Results table


| config | RPS all | ±SE | ΔRPS vs best | ±SE | LL all | LL n=0 | LL n<30 | LL n≥30 | RPS n<30 | ECE₂₄ₕ | ECE₇d | cov₉₀ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P5a P4 + decay h=90d | 0.10645 | 0.00184 | +0.00000 | 0.00000 | 1.3788 | 1.4420 | 1.4757 | 1.3676 | 0.10628 | 0.0135 | 0.0230 | 0.918 |
| P5b P4 + decay h=180d | 0.10668 | 0.00185 | +0.00023 | 0.00003 | 1.3787 | 1.4416 | 1.4795 | 1.3671 | 0.10667 | 0.0162 | 0.0230 | 0.913 |
| P5c P4 + decay h=365d | 0.10682 | 0.00187 | +0.00037 | 0.00005 | 1.3803 | 1.4420 | 1.4824 | 1.3686 | 0.10684 | 0.0169 | 0.0231 | 0.905 |
| P3 hierarchy, EB k per type | 0.10698 | 0.00189 | +0.00054 | 0.00008 | 1.3838 | 1.4484 | 1.4869 | 1.3719 | 0.10696 | 0.0181 | 0.0213 | 0.899 |
| P4 hierarchy, EB k per (type,level) | 0.10701 | 0.00189 | +0.00056 | 0.00008 | 1.3847 | 1.4435 | 1.4886 | 1.3728 | 0.10700 | 0.0181 | 0.0216 | 0.898 |
| P2 hierarchy, fixed k=15 | 0.10739 | 0.00189 | +0.00095 | 0.00008 | 1.4056 | 1.4684 | 1.5487 | 1.3891 | 0.10818 | 0.0184 | 0.0199 | 0.899 |
| P1 Jeffreys, no pooling | 0.10858 | 0.00187 | +0.00213 | 0.00008 | 1.4163 | 2.1972 | 1.6636 | 1.3871 | 0.11787 | 0.0226 | 0.0086 | 0.245 |
| P0 uniform, no pooling | 0.10958 | 0.00186 | +0.00313 | 0.00008 | 1.4220 | 2.1972 | 1.6862 | 1.3908 | 0.12577 | 0.0285 | 0.0123 | 0.223 |

## Cleaning funnel (§6)


| step | rows |
|---|---|
| raw rows | 5,338,189 |
| after unique_key dedupe | 5,338,189 |
| after double-submission collapse | 5,150,145 |
| after created_date parse | 5,150,145 |
| closed_status_null_closed_date_dropped | 6,028 |
| after closed-but-no-closed_date drop | 5,144,117 |
| after negative-duration drop | 5,143,159 |
| exact_zero_duration_dropped | 97,352 |
| after zero-duration drop | 5,045,807 |
| batch_closed_flagged | 84,563 |
| tract_assigned | 4,960,076 |
| after geography filter | 5,041,962 |

## Estimated concentration κ (winner, by level & type)


```json
{
  "boro": {
    "Illegal Parking": 145.6,
    "Noise - Residential": 145.6,
    "HEAT/HOT WATER": 145.6,
    "Blocked Driveway": 145.6,
    "Noise - Street/Sidewalk": 145.6,
    "UNSANITARY CONDITION": 145.6,
    "Abandoned Vehicle": 145.6,
    "Street Condition": 145.6,
    "PLUMBING": 145.6,
    "Noise - Commercial": 145.6,
    "Dirty Condition": 145.6,
    "Water System": 145.6,
    "Noise": 145.6,
    "PAINT/PLASTER": 145.6,
    "Encampment": 145.6,
    "Traffic Signal Condition": 145.6,
    "Missed Collection": 145.6,
    "DOOR/WINDOW": 145.6,
    "Derelict Vehicles": 145.6,
    "Noise - Vehicle": 145.6,
    "Other": 145.6,
    "ALL": 145.6
  },
  "boro_pooled": 145.6,
  "nta": {
    "Illegal Parking": 16.88,
    "Noise - Residential": 15.15,
    "HEAT/HOT WATER": 426.21,
    "Blocked Driveway": 18.27,
    "Noise - Street/Sidewalk": 20.16,
    "UNSANITARY CONDITION": 277.61,
    "Abandoned Vehicle": 11.93,
    "Street Condition": 157.13,
    "PLUMBING": 357.85,
    "Noise - Commercial": 15.67,
    "Dirty Condition": 71.49,
    "Water System": 519.05,
    "Noise": 240.27,
    "PAINT/PLASTER": 543.57,
    "Encampment": 155.95,
    "Traffic Signal Condition": 4999.75,
    "Missed Collection": 66.9,
    "DOOR/WINDOW": 841.84,
    "Derelict Vehicles": 101.79,
    "Noise - Vehicle": 17.05,
    "Other": 76.73,
    "ALL": 77.61
  },
  "nta_pooled": 69.32,
  "tract": {
    "Illegal Parking": 342.86,
    "Noise - Residential": 266.88,
    "HEAT/HOT WATER": 438.58,
    "Blocked Driveway": 4999.75,
    "Noise - Street/Sidewalk": 1005.52,
    "UNSANITARY CONDITION": 1694.42,
    "Abandoned Vehicle": 4999.67,
    "Street Condition": 4999.7,
    "PLUMBING": 747.26,
    "Noise - Commercial": 4999.71,
    "Dirty Condition": 4999.71,
    "Water System": 4999.73,
    "Noise": 3387.53,
    "PAINT/PLASTER": 4999.72,
    "Encampment": 4999.7,
    "Traffic Signal Condition": 4999.79,
    "Missed Collection": 4999.83,
    "DOOR/WINDOW": 4999.75,
    "Derelict Vehicles": 4999.73,
    "Noise - Vehicle": 4999.83,
    "Other": 125.26,
    "ALL": 126.96
  },
  "tract_pooled": 234.02
}
```

## Interpretation & caveats

- **Hierarchy is essential.** P0/P1 (no pooling) hit log-loss 2.197 = log(9) on the
  `n=0` stratum — literally a uniform guess, because an unseen tract×type cell has no
  data and no parent to borrow from. Partial pooling drops this to ~1.44 (the
  neighborhood/borough estimate). This is the core value of the hierarchical design.
- **Decay wins, shortest half-life wins.** P5a (h=90d) beats no-decay P4 and both longer
  half-lives on RPS, with the advantage concentrated in the first 2–3 test months —
  the signature of a model tracking a drifting process. Since the deployed pipeline
  refreshes monthly (always predicting the near term), P5a is the right choice.
- **Concentration estimation.** κ is maximized directly on the exact Dirichlet-
  Multinomial marginal likelihood by bounded scalar optimization. An earlier version
  used Minka's fixed-point iteration, which on these flat likelihood surfaces stopped
  far short of the optimum (verified against a likelihood grid: e.g. tract-level
  Heat/Hot Water stopped at κ≈230 where the optimum is ≈800) and systematically
  under-pooled. Predictive metrics moved only marginally after the fix (the surface is
  flat), but the shipped estimator is now the actual MLE.
- **Interval calibration.** Raw Dirichlet posterior intervals describe sampling
  uncertainty about the current decay-weighted rate only. Verified on both an
  even/odd-day split (~0.51 coverage at nominal 90%, no drift possible) and rolling
  next-60-day holdouts (~0.25 on dense cells), they badly understate the variability
  of realized near-future rates, which is dominated by regime movement (seasonality,
  agency policy/backlog changes, correlated batch closures). The shipped intervals
  therefore add a per-type, per-cut **regime variance** estimated from rolling
  temporal holdouts inside the training window (see model.estimate_regime_sigma):
  halfwidth = 1.645·√(Var_Dirichlet + σ²_type,cut). With this calibration the cov₉₀
  column above lands at 0.90–0.92 for the hierarchical configs, and an out-of-sample
  next-60-day check (fit through 2026-01, scored on Jan–Feb 2026 dense cells) gives
  0.87 — slightly under target because early 2026 shifted more than any window in the
  calibration year. Residual regime-shift risk beyond history is irreducible; the
  monthly update cycle re-centers the model continuously.
- **"Month+" composition.** 8.8% of matured requests land in the top bin; 71.5% of
  those did eventually close after 31+ days, 28.5% remained open at pull. For
  Heat/Hot Water and Homeless Person Assistance, >99% of month+ cases were still open
  (effectively never administratively closed) — truthful as "not resolved within a
  month," and flagged via the high-open-share metadata where the type-level share
  exceeds 20%.

**Shipped configuration: P5a** — hierarchical Dirichlet–Multinomial cascade
(tract→NTA→borough→city per complaint type, city×type rooted in city×ALL, global root
Jeffreys ½), κ per (type, level) by bounded MLE on the DM marginal likelihood,
90-day exponential decay, regime-calibrated 90% intervals. Fit on all matured data
through 2026-06-03.
- **Seasonal blending tested, not adopted.** A same-season-last-year kernel
  (row weight = recency + β·2^(−|age−1yr|/bw); conjugate, available via
  `Config.seasonal_beta`) was evaluated with a rolling-monthly protocol that mirrors
  the deployed refresh: refit at each 2026 month start, predict that month. Overall
  paired RPS difference vs P5a: −0.00001 ± 0.00008 (β=0.5, bw=45d) — a statistical
  zero — with heavier blends slightly worse (+0.00014 ± 0.00013 at β=1.0), and gains
  on strongly seasonal types (Heat/Hot Water, Snow or Ice, Plumbing, Water System)
  of only ~0.3% relative and inconsistent by month. With one prior year of history,
  "last season" is a single noisy replicate carrying that year's idiosyncrasies,
  while the 90-day recency window already captures mid-season behavior. Re-test with
  ≥2 years of history (`pipeline/eval_seasonal.py`).
