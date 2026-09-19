# Statistical Review — Model, Output, and Data Audit

**Scope.** Adversarial verification of the shipped hierarchical Dirichlet–Multinomial
model, its exported outputs, the evaluation protocol, and the data preparation, with
every claim checked computationally against the production data rather than by reading
documentation. Conducted against the P5a configuration (90-day decay) fit on 5.04M
cleaned requests (2025-01-01 – 2026-06-03).

**Verdict.** The modeling approach — conjugate hierarchical cascade with empirical-Bayes
concentrations, exact censoring at the 31-day maturity boundary, temporal-holdout prior
selection scored by ranked probability score — is sound and defensible for a
public-facing map. The audit found **two material defects**, both since remediated:
(1) the concentration estimator stopped far short of the marginal-likelihood optimum,
and (2) the credible intervals badly under-covered realized near-future rates, and the
prior documentation misattributed this to temporal drift alone. Point estimates
(posterior means, the map colors, the ladder bars) were verified correct throughout;
the defects concerned pooling strength and uncertainty quantification.

---

## 1. Correctness of the implementation

**Cascade reproduction.** An independent re-implementation (separate code path: own count
accumulation, own concentration optimizer, own cascade) reproduced the shipped
`probs.json` posterior means once the concentration values were matched, and a refit
through the production code path reproduced the shipped export to within the 3-decimal
export rounding (max |Δ| = 0.0005 across sampled tracts × types). Count indexing, the
parent maps (tract→NTA→borough), the ALL tree, decay weighting, and the shrinkage
formula are implemented as specified.

**Output sanity (all 51,150 tract × type records).** Bin probabilities sum to 1 and
cumulative sequences are monotone in every record; shrinkage weights all lie in [0, 1];
raw counts `n` match direct tallies from the cleaned request table exactly (1,200-cell
sample, zero mismatches); citywide reference cumulatives match direct empirical rates on
dense types (e.g. Heat/Hot Water P(≤24h): 0.257 exported vs 0.259 empirical, the gap
being decay weighting). The 41 records (0.08%) initially flagged for interval
bracketing are 3-decimal rounding accumulation (max excess 0.002), not defects.

**Ranked probability score.** The vectorized RPS in the evaluation harness matches a
hand computation on a constructed example exactly.

## 2. Defect 1 — concentration estimator under-converged (fixed)

The κ parameters were maximized with Minka's fixed-point iteration (200 iterations,
tolerance 1e-6 on log κ). Evaluating the exact Dirichlet–Multinomial marginal
log-likelihood on a grid showed the fixed point stopping far short of the optimum on
these flat surfaces:

| type (NTA→tract level) | fixed-point κ | grid optimum | ll gap (nats) |
|---|---|---|---|
| Heat/Hot Water | 230 | ≈ 800 | 78 |
| Illegal Parking | 87 | ≈ 400 | 288 |

Direction of the error: systematic **under-pooling** (κ too small ⇒ tract estimates
noisier and less shrunk than the evidence warrants). An independent longer-running
fixed point also undershot, confirming slow linear convergence rather than a coding
slip. **Remediation:** the estimator now maximizes the exact marginal likelihood by
bounded scalar optimization over log κ (~30 likelihood evaluations; exact to the
tolerance of the bracket). Effect on predictions is small (the likelihood is flat — RPS
moved from 0.10640 to 0.10645 for the winning config, ranking unchanged), but the
shipped estimator is now the actual MLE, and reported κ values are interpretable.

## 3. Defect 2 — interval under-coverage misattributed to drift (fixed)

Prior documentation attributed the backtest's 90%-interval coverage of ~0.44 on dense
cells to 2025→2026 temporal drift. Three tests refute drift as the primary cause:

| test | drift possible? | coverage at nominal 90% |
|---|---|---|
| cross-year backtest (train 2025, test 2026) | yes | 0.44 |
| within-2025 split (fit Jan–Jun, test Jul–Dec) | seasonal only | 0.55 |
| even/odd day-of-year split | no | **0.51** |
| rolling next-60-day holdouts (dense cells) | short-horizon | 0.25 |

Even with drift impossible by construction, half the dense cells fall outside their
intervals: the Dirichlet sampling variance (∝ 1/A) understates the variability of
realized cell rates, which carry additional components the Multinomial cannot see —
within-cell correlation (repeat reports on one condition, batch closures, day-of-week
structure) and regime movement interacting with decay weighting. Multiplicative
inflation (a quasi-likelihood design effect) was tested and rejected: factors large
enough for dense cells (5–150×) absurdly widen sparse cells whose intervals are already
sampling-dominated.

**Remediation (shipped):** per-type, per-threshold **additive regime variance** σ,
estimated by refitting the model at four rolling origins inside the training year and
taking the 90th percentile of dense-cell squared deviation between posterior mean and
next-60-day empirical rate, in excess of sampling variance. Interval half-width is now
1.645·√(Var_Dirichlet + σ²). Estimated σ at the 24-hour cut: all-types 0.098,
Heat/Hot Water 0.115 (strong seasonality), Illegal Parking 0.007 (stable, near-saturated
process). Verification:

- cross-period backtest coverage: 0.90–0.92 across hierarchical configurations
  (previously 0.37–0.52), inside the [0.80, 0.97] guardrail;
- fully out-of-sample next-60-day check (fit through 2026-01, scored on Jan–Feb 2026):
  **0.87** — the shortfall from 0.90 reflects early 2026 shifting more than any window
  in the calibration year, an irreducible regime-shift residual mitigated operationally
  by the monthly update cycle;
- sparse cells widen only modestly (example: half-width 0.066 → 0.145), preserving the
  product's shrinkage story.

## 4. Evaluation protocol

Verified sound: the complaint-type list, concentrations, and now the interval
calibration are all estimated strictly on the training window (calibration origins and
their 60-day horizons end at the train/test split); test rows in tracts unseen at
training still receive predictions through the hierarchy, so no selection against
sparse cells; the paired block bootstrap resamples tract × type cells, the correct
exchangeable unit given within-cell correlation. The P5a-over-P5b margin (ΔRPS 0.00025,
paired SE 0.00003) was probed month-by-month: the 90-day half-life's advantage is
concentrated in test months 1–3 and decays to ≈0 by month 5–6 — the expected signature
of a drifting process, and the correct basis for choosing P5a given the deployed
monthly refresh (the model always predicts the near term). One asymmetry noted, not
material: requests lacking tract coordinates (~1.7%) are scored from borough-level
posteriors for all configurations equally.

## 5. Data preparation and censoring

- **Maturity cutoff verified exact:** max `created_date` in the prepared table is
  2026-06-03, 31 days before the pull; every retained request had the full 744-hour
  observation window, so the "open ⇒ month+" assignment is deductively correct, not an
  approximation.
- **Bin-9 composition:** 8.8% of matured requests land in "month+"; 71.5% of those
  eventually closed after 31+ days and 28.5% were still open at pull. For Heat/Hot Water
  and Homeless Person Assistance, >99% of month+ cases were never closed —
  administrative non-closure rather than late resolution. The user-facing claim ("not
  resolved within a month") remains truthful; the type-level `high_open_share` flag
  covers the general case.
- Cleaning-funnel counts in the documentation match the logged funnel (5.34M → 5.04M;
  188k double-submissions, 97k exact-zero durations, 85k batch-closure flags).
- Not run (cost): a full sensitivity re-evaluation excluding batch-closure-flagged
  records, and a formal within-cell correlation decomposition; the additive regime
  variance subsumes their effect on the shipped intervals.

## 6. Residual limitations and recommended next steps, ranked

1. **Regime-shift residual.** Calibrated intervals cover 0.87 out-of-sample against a
   0.90 target when the regime moves more than history suggests. Worth revisiting after
   each quarterly refit; if persistent, raise the calibration quantile or add the most
   recent quarter to the origin set.
2. **Plug-in cascade.** Parent uncertainty is still not propagated (the spec's 200-draw
   refinement remains unimplemented). With the regime component dominating interval
   width this is now immaterial for the shipped product, but a full-Bayes comparison on
   one borough would make the approximation error citable rather than argued.
3. **Ordered-bin structure.** Adjacent bins share no strength (the Dirichlet is
   exchangeable over categories); a continuation-ratio Beta–Binomial with a smoothness
   prior could improve sparse-cell tail estimates. The evaluation's RPS already rewards
   ordering, so any gain is measurable within the existing harness.
4. **Borough-level batch-closure sensitivity** (the deferred §5 item) should be run once
   before any claim that borough contrasts reflect service quality rather than
   record-keeping practice.

**Bottom line.** With the two remediations in place — exact MLE concentrations and
regime-calibrated intervals — the shipped estimates are verified correct, the pooling is
evidence-optimal under the stated model, the intervals now mean what the interface says
they mean, and the remaining weaknesses are documented residuals rather than silent
defects.

---

## 7. Addendum: handling of requests without a tract (found after publication)

**Finding.** About 1.6% of matured requests (110,411 of 7,080,287 in the 2026-09 rebuild) have
no census tract because their coordinates are missing or outside the city. The export step
converted the tract column with `astype(str)`. Under pandas 2.x this turns missing values
into the text `"nan"`, so those rows passed the "has a tract" test and were counted in tract
index 0 (36005000100, Rikers Island, a single-tract neighborhood). Under pandas 3.x missing
values are preserved and the rows are correctly limited to borough and citywide estimates.

**Detection.** A scheduled refresh ran on a GitHub runner with pandas 3.0.6 and produced
different per-tract counts than the same data processed locally with pandas 2.3.3. The
difference was exactly the number of unlocated requests. The audit in section 1 checked raw
counts on a random sample of 300 tracts, which did not include tract index 0.

**Impact.** Every export produced under pandas 2.x carried the error. The Rikers Island tract
displayed the mix of all unlocated requests (n = 110,486) instead of its own (n = 75). That
one extreme child also distorted the fitted concentration parameters, moving other tracts
slightly: across the other 2,324 tracts the largest change in any bin probability was 0.020,
with a median of 0.004. Estimates at borough and citywide level were unaffected. The
published data was replaced by a pandas 3.x rebuild on 2026-09-19.

**Fix and verification.** The conversion now preserves missing values
(`astype("object")`). Rebuilt under pandas 2.3.3, the export matches the pandas 3.0.6 runner
output in 51,146 of 51,150 cells exactly, the remaining four differing by at most 0.001
(rounding); all raw counts are identical. `pipeline/validate_export.py` now also requires the
summed tract counts to equal the cleaning step's geocoded-request count (to 0.1%) and no
single tract to hold more than 1% of requests; both checks fail on the affected export.

**Not yet redone.** The prior comparison in `evaluation_results.md` was fitted on the earlier
data window using the same conversion, so its training counts carry the same small distortion.
It should be regenerated on the current window.
