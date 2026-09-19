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
