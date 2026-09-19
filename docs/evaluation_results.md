# Prior Comparison Results

_Generated 2026-09-19. Train 2024-08-19–2025-08-19 (3,332,157 requests), test 2025-08-19–2026-08-18 (3,748,130 requests)._


**Complaint types modeled (21):** Illegal Parking, Noise - Residential, HEAT/HOT WATER, Blocked Driveway, Noise - Street/Sidewalk, UNSANITARY CONDITION, Street Condition, PLUMBING, Abandoned Vehicle, Water System, Dirty Condition, Noise - Commercial, Noise, PAINT/PLASTER, Snow or Ice, Traffic Signal Condition, DOOR/WINDOW, Encampment, Noise - Vehicle, WATER LEAK, Other


## Selection


**Lowest RPS on this single 12-month split: `P5b P4 + decay h=180d`.** The shipped configuration is `P5a P4 + decay h=90d`: it is chosen with the rolling-origin evaluation ([rolling_evaluation.md](rolling_evaluation.md)), which refits at each month start and predicts only the next month, as the deployed map does. A single split trains once and predicts up to 12 months ahead, which favors long memory (see the notes below).


## Results table


| config | RPS all | ±SE | ΔRPS vs best | ±SE | LL all | LL n=0 | LL n<30 | LL n≥30 | RPS n<30 | ECE₂₄ₕ | ECE₇d | cov₉₀ | z² sparse | z² dense |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P5b P4 + decay h=180d | 0.10290 | 0.00149 | +0.00000 | 0.00000 | 1.3392 | 1.7621 | 1.5001 | 1.3052 | 0.10271 | 0.0157 | 0.0157 | 0.909 | 1.14 | 0.80 |
| P5c P4 + decay h=365d | 0.10297 | 0.00149 | +0.00007 | 0.00002 | 1.3422 | 1.7884 | 1.5092 | 1.3073 | 0.10290 | 0.0143 | 0.0156 | 0.909 | 1.18 | 0.83 |
| P6a P5a + sibling-only prior | 0.10300 | 0.00149 | +0.00010 | 0.00003 | 1.3385 | 1.7325 | 1.4944 | 1.3054 | 0.10272 | 0.0179 | 0.0163 | 0.910 | 1.18 | 0.83 |
| P5a P4 + decay h=90d | 0.10302 | 0.00149 | +0.00012 | 0.00003 | 1.3383 | 1.7326 | 1.4941 | 1.3052 | 0.10271 | 0.0180 | 0.0165 | 0.908 | 1.14 | 0.78 |
| P3 hierarchy, EB k per type | 0.10316 | 0.00149 | +0.00026 | 0.00004 | 1.3485 | 1.8568 | 1.5344 | 1.3109 | 0.10325 | 0.0145 | 0.0146 | 0.910 | 1.01 | 0.79 |
| P4 hierarchy, EB k per (type,level) | 0.10318 | 0.00149 | +0.00028 | 0.00004 | 1.3492 | 1.8239 | 1.5305 | 1.3123 | 0.10332 | 0.0143 | 0.0147 | 0.909 | 1.15 | 0.87 |
| P2 hierarchy, fixed k=15 | 0.10365 | 0.00149 | +0.00075 | 0.00005 | 1.3671 | 1.8802 | 1.5906 | 1.3248 | 0.10471 | 0.0160 | 0.0143 | 0.912 | 1.12 | 0.93 |
| P1 Jeffreys, no pooling | 0.10548 | 0.00147 | +0.00258 | 0.00009 | 1.3843 | 2.1972 | 1.7054 | 1.3285 | 0.11692 | 0.0238 | 0.0076 | 0.369 | 1.81 | 3.03 |
| P0 uniform, no pooling | 0.10685 | 0.00146 | +0.00395 | 0.00014 | 1.3921 | 2.1972 | 1.7239 | 1.3351 | 0.12584 | 0.0329 | 0.0165 | 0.304 | 2.65 | 3.78 |

## Cleaning funnel (§6)


| step | rows |
|---|---|
| raw rows | 7,522,477 |
| after unique_key dedupe | 7,522,477 |
| after double-submission collapse | 7,236,222 |
| after created_date parse | 7,236,222 |
| closed_status_null_closed_date_dropped | 17,403 |
| after closed-but-no-closed_date drop | 7,218,819 |
| after negative-duration drop | 7,217,251 |
| exact_zero_duration_dropped | 131,287 |
| after zero-duration drop | 7,085,964 |
| batch_closed_flagged | 114,252 |
| tract_assigned | 6,969,876 |
| after geography filter | 7,080,287 |

## Estimated concentration κ (shipped configuration, by level & type)


```json
{
  "boro": {
    "Illegal Parking": 107.43,
    "Noise - Residential": 107.43,
    "HEAT/HOT WATER": 107.43,
    "Blocked Driveway": 107.43,
    "Noise - Street/Sidewalk": 107.43,
    "UNSANITARY CONDITION": 107.43,
    "Street Condition": 107.43,
    "PLUMBING": 107.43,
    "Abandoned Vehicle": 107.43,
    "Water System": 107.43,
    "Dirty Condition": 107.43,
    "Noise - Commercial": 107.43,
    "Noise": 107.43,
    "PAINT/PLASTER": 107.43,
    "Snow or Ice": 107.43,
    "Traffic Signal Condition": 107.43,
    "DOOR/WINDOW": 107.43,
    "Encampment": 107.43,
    "Noise - Vehicle": 107.43,
    "WATER LEAK": 107.43,
    "Other": 107.43,
    "ALL": 107.43
  },
  "boro_pooled": 107.43,
  "nta": {
    "Illegal Parking": 13.22,
    "Noise - Residential": 14.24,
    "HEAT/HOT WATER": 2451.31,
    "Blocked Driveway": 12.55,
    "Noise - Street/Sidewalk": 18.43,
    "UNSANITARY CONDITION": 299.31,
    "Street Condition": 363.02,
    "PLUMBING": 231.5,
    "Abandoned Vehicle": 8.83,
    "Water System": 176.94,
    "Dirty Condition": 53.71,
    "Noise - Commercial": 16.45,
    "Noise": 280.29,
    "PAINT/PLASTER": 3032.25,
    "Snow or Ice": 4999.75,
    "Traffic Signal Condition": 4999.77,
    "DOOR/WINDOW": 4999.77,
    "Encampment": 121.11,
    "Noise - Vehicle": 15.13,
    "WATER LEAK": 4999.77,
    "Other": 66.33,
    "ALL": 76.23
  },
  "nta_pooled": 58.74,
  "tract": {
    "Illegal Parking": 315.16,
    "Noise - Residential": 204.35,
    "HEAT/HOT WATER": 4999.68,
    "Blocked Driveway": 4999.69,
    "Noise - Street/Sidewalk": 333.54,
    "UNSANITARY CONDITION": 4999.77,
    "Street Condition": 4999.78,
    "PLUMBING": 4999.67,
    "Abandoned Vehicle": 4999.82,
    "Water System": 4999.73,
    "Dirty Condition": 4999.74,
    "Noise - Commercial": 4999.77,
    "Noise": 2706.96,
    "PAINT/PLASTER": 4999.76,
    "Snow or Ice": 4999.81,
    "Traffic Signal Condition": 4999.82,
    "DOOR/WINDOW": 4999.83,
    "Encampment": 4999.72,
    "Noise - Vehicle": 4999.74,
    "WATER LEAK": 4999.81,
    "Other": 117.91,
    "ALL": 135.43
  },
  "tract_pooled": 214.05
}
```


## Interpretation & caveats

_Written against the results above: data window 2024-08-19 – 2026-08-18; train on the first
12 months, test on the next 12; pinned complaint-type list (`pipeline/types.json`); requests
without a tract handled as missing (see `statistical_review.md` §7). Earlier versions of this
file used a different window and a loader that mishandled missing tracts, so their numbers are
not comparable._

- **Pooling across the hierarchy is essential.** The no-pooling baselines (P0, P1) are
  +0.0040 and +0.0026 RPS behind the best configuration, and on unseen tract×type cells they
  predict the bare prior, scoring exactly log(9) = 2.197 in log-loss against 1.73–1.88 for the
  hierarchical configurations. Their intervals are also badly wrong (90% coverage 0.30–0.37; squared standardized
  residual 1.8–3.8 against a target of 1).
- **This single split does not choose the decay setting.** Its lowest RPS is P5b (180-day
  half-life), ahead of the shipped P5a (90 days) by 0.00012 (paired SE 0.00003); log-loss
  points the other way (P5a 1.3383 vs P5b 1.3392). More importantly, the protocol trains once
  and predicts up to 12 months ahead, which penalizes short memory on the later months. The map
  is refit every week and only ever predicts the near future, so the decay setting is chosen
  with the rolling-origin evaluation instead ([rolling_evaluation.md](rolling_evaluation.md):
  refit at each month start, score that month, 11 months).
- **Rolling-origin result: keep the 90-day half-life.** Half-lives from 45 to 180 days are
  statistically tied with it (RPS differences 0.00000 to +0.00004, each within about 1.3
  paired SEs of zero). A 365-day half-life is worse by 0.00014 ± 0.00005 and no decay at all by
  0.00040 ± 0.00008. Decay matters; the exact value between 45 and 180 days does not.
- **Same-season-last-year blending: small, inconsistent, not adopted.** With two years of
  history the best variant (β = 0.5) improves RPS by 0.00013 ± 0.00004 and log-loss by
  0.00176 ± 0.00038, but it wins in only 5 of the 11 months (clear gains in
  December–February, small ones in May–June, losses in September–November, March–April and July), and β = 1.0 is worse on log-loss.
  Re-run `pipeline/eval_rolling.py` as more history accumulates.
- **Sibling-only prior: no measurable gain on real data.** Excluding a unit's own counts from
  its parent mean removes a double count and changes RPS by −0.00004 ± 0.00001 and log-loss by
  +0.00016 ± 0.00007, i.e. nothing that matters. It is available as `Config.loo_parent` and
  examined in `simulation_check.md`.
- **Concentration estimation.** κ is maximized directly on the exact Dirichlet–Multinomial
  marginal likelihood (`statistical_review.md` §2). The simulation check shows both this
  estimator and the sibling-only variant are biased for the tract-level κ (too high by 45% or
  more for the plain cascade; too low by 24–65% for sibling-only), yet tract-level accuracy is
  the same either way, so the pinned-at-cap values in the table below should not be read as
  "no local signal".
- **Interval calibration.** Intervals combine Dirichlet variance, the uncertainty of the
  neighborhood mean a tract borrows (needed for correct coverage when the model is exactly
  true: 43–81% without it in simulation), and a per-type regime variance fitted on rolling
  training holdouts. Shipped configuration: 90% coverage 0.908 on cells with at least 50 test
  requests; on sparse cells (under 30 training requests, at least 10 test requests) the squared
  standardized residual is 1.14 and 90.2% of cells fall inside their interval. In dense cells
  the intervals are slightly wide (0.78; 94% coverage). On real data the regime term (median
  0.09 across types, range 0.00–0.31) is far larger than the parent term (median SD 0.008 in
  sparse cells, 90th percentile 0.03; under 1% of the variance at the median regime term), so for
  most types the parent term barely changes what users see (median change in the 24-hour
  interval width +0.001; 99th percentile +0.031). It matters where the regime term is near
  zero: the largest changes, up to +0.145, are 1,575 Noise - Commercial cells in sparse
  neighborhoods, whose old intervals were about ±0.007 even for cells with 2–15 requests
  because they ignored the uncertainty of the neighborhood mean. Calibration for the six
  types with almost no regime variance (the three noise types, Illegal Parking, Unsanitary
  Condition, Blocked Driveway) has not been checked separately.

**Shipped configuration: P5a** — hierarchical Dirichlet–Multinomial cascade
(tract→NTA→borough→city per complaint type, city×type rooted in city×ALL, global root
Jeffreys ½), κ per (type, level) by bounded MLE on the DM marginal likelihood, 90-day
exponential decay, regime-calibrated 90% intervals with the parent-uncertainty term.
