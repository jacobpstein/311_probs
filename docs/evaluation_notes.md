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
  half-life), ahead of the shipped P7a (90 days, per-threshold pooling) by 0.00007 (paired SE 0.00003); log-loss
  points the other way (P7a 1.3403 vs P5b 1.3392 here, and P5a 1.3383). More importantly, the protocol trains once
  and predicts up to 12 months ahead, which penalizes short memory on the later months. The map
  is refit every week and only ever predicts the near future, so the decay setting is chosen
  with the rolling-origin evaluation instead ([rolling_evaluation.md](rolling_evaluation.md):
  refit at each month start, score that month, 11 months).
- **Rolling-origin result: per-threshold pooling and a 90-day half-life.** The per-threshold
  model (P7a) beats the nine-bin model with the same decay by 0.00019 ± 0.00002 in RPS and
  0.00084 ± 0.00016 in log-loss. Among nine-bin models, half-lives from 45 to 180 days are
  statistically tied; for the per-threshold model 45 days is slightly better in RPS (−0.00010 ±
  0.00003) but worse in log-loss (+0.0026 ± 0.0004) and 180 days is worse in both, so 90 days is kept.
  A 365-day half-life (+0.00033 ± 0.00005 in the nine-bin model) and no decay (+0.00058 ± 0.00007) are worse.
  Decay matters; the exact value between 45 and 180 days does not.
- **Same-season-last-year blending: small, inconsistent, not adopted.** With two years of
  history the best variant (β = 0.5) improves the nine-bin model's RPS by 0.00013 ± 0.00004 and log-loss by
  0.00176 ± 0.00038 (measured against the nine-bin reference; against the shipped per-threshold model it is
  RPS +0.00005 ± 0.00004, log-loss −0.0009 ± 0.0004), but it wins in only 5 of the 11 months (clear gains in
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
  training holdouts. Shipped configuration: 90% coverage 0.911 on cells with at least 50 test
  requests; on sparse cells (under 30 training requests, at least 10 test requests) the squared
  standardized residual is 1.05 and 90.7% of cells fall inside their interval. In dense cells
  the intervals are slightly wide (0.70; 94% coverage). Follow-up checks
  ([robustness_checks.md](robustness_checks.md), [interval_calibration_rolling.md](interval_calibration_rolling.md)):
  by type, the six low-regime-variance types are fine except Noise - Street/Sidewalk (dense coverage 0.86);
  types that fall back to the pooled regime variance (Street Condition, Dirty Condition, Water System) are
  under-covered in this split (0.67–0.84), and a lower holdout threshold did not help under the deployed
  protocol; under that protocol overall coverage is 0.874.
  Other configurations' calibration columns changed slightly from earlier runs because the
  regime variance is now estimated with the model's own structure.

**Shipped configuration: P7a** — per-threshold hierarchical Dirichlet–Multinomial (eight
two-category hierarchies tract→NTA→borough→city per complaint type, city×type rooted in
city×ALL, global root Jeffreys ½), κ per (threshold, type, level) by bounded MLE, running maximum
across thresholds, 90-day exponential decay, regime-calibrated 90% intervals with the
parent-uncertainty term.
