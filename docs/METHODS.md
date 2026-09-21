# Methods — How Fast Does New York Fix It?

The whole method in one paragraph:

> We took about seven million 311 service requests, measured how long each one took to
> close, and sorted those durations into nine buckets (under 3 hours, same day, next day,
> and so on out to "more than a month"). For every neighborhood and every kind of complaint,
> we estimated the chance a new request lands in each bucket. Because some blocks have
> thousands of requests and others only a handful, we used a method that lets thin data
> "borrow" from the surrounding neighborhood and borough, so every tract gets a fair,
> stable estimate instead of a noisy one — and the map is honest about which estimates are
> solid and which are mostly borrowed.

---

## 1. What question the map answers

> Pick a spot on the map and a type of problem — say, a noise
> complaint in your census tract. The map tells you: *if someone files this complaint here,
> what's the chance the city resolves it within 3 hours? Within a day? Within a week? A
> month?* It's a weather forecast for city services: not a promise, but the odds, based on
> what actually happened to millions of past requests.

Formally, for every **census tract** *g* and **complaint type** *t*, we estimate a
probability distribution over nine ordered **resolution-time bins**:

| # | Bin | Upper edge |
|---|-----|-----------|
| 1 | ≤ 3 hours | 3 h |
| 2 | 3–24 hours (same day) | 24 h |
| 3 | 1–2 days | 48 h |
| 4 | 2–3 days | 72 h |
| 5 | 3–7 days (within a week) | 168 h |
| 6 | 1–2 weeks | 336 h |
| 7 | 2–3 weeks | 480 h |
| 8 | 3–4 weeks | 744 h (31 days) |
| 9 | more than a month | ∞ |

The map always shows a **cumulative** probability — "resolved *within* X" — because that's
how people think ("will it be handled by tomorrow?") and because cumulative probabilities
only ever grow as you slide the time control forward, which makes the animation legible.
The side panel shows the full nine-bin picture.

Census tracts are the smallest standard geography the city publishes (roughly 1,200–8,000
residents each; there are 2,325 in NYC). That is the "smallest resolution possible" that
still leaves enough data per unit to say something meaningful.

---

## 2. The data

> We used the city's own public record of every 311 request —
> including when it was opened, when it was closed, what it was about, and where it was.
> We only kept requests old enough that we could actually see their full outcome, and we
> cleaned out obvious data-entry glitches (duplicates, negative durations, and so on).

**Source.** NYC Open Data, *311 Service Requests from 2010 to Present* (Socrata dataset
`erm2-nwe9`). We pull the fields `created_date`, `closed_date`, `complaint_type`,
`descriptor`, `agency`, `status`, `borough`, and `latitude`/`longitude`.

**Window.** A rolling two-year window of requests (currently created between **2024-08-19 and
2026-08-18**), about **7.5 million** before cleaning. The window ends 31 days before the data
pull, for the reason given in §2.2, and moves forward with every weekly refresh.

**Geography.** Each request's latitude/longitude is assigned to a 2020 census tract by
point-in-polygon test against the city's official tract boundaries. Tracts roll up into
**Neighborhood Tabulation Areas** (NTAs, ~260 of them), which roll up into **boroughs** (5),
which roll up into the **city** (1). This four-level hierarchy is the backbone of the model
(§5). about 98% of requests carry usable coordinates; the rest are kept only at the borough/city
level, where they still inform the estimates.

### 2.1 Cleaning ("data hygiene")

> Raw government data always has junk in it — the same request entered
> twice, a "closed" date that's somehow before the "opened" date, bulk closures where an
> agency shut thousands of cases in the same minute. We remove the clearly broken records
> and flag the suspicious-but-real ones, and we keep a running tally so anyone can see
> exactly how many rows each step removed.

Rules, applied in order (the row count after each is logged to `data/funnel.json`):

1. **De-duplicate** on the Socrata primary key `unique_key`.
2. **Collapse double-submissions**: rows with identical complaint type, descriptor, and
   coordinates (to 5 decimals) created within 60 seconds of each other are re-taps of the
   submit button; keep the earliest. (We do *not* merge genuinely repeated complaints about
   the same condition — those are real demand.)
3. Drop rows with an unparseable `created_date`, or marked `Closed` with no `closed_date`.
4. Drop **negative durations** (`closed_date < created_date`, a known agency-backfill artifact).
5. Drop **exact-zero durations** (`closed == created` to the second — a system void, not a
   real 3-hour resolution). Durations under a minute are *kept* (some agencies legitimately
   auto-acknowledge) but counted.
6. **Flag** — but keep — **batch closures**: minutes in which an agency closed an unusually
   large spike of cases (> max(500, 20% of that agency's median daily closures)). Keeping
   them is the honest choice: the recorded closure is what the requester experienced. A
   sensitivity check supports that: 1.6% of requests are flagged (HPD 77k, DOB 35k;
   9–10% of Water Leak, Door/Window and Plumbing requests), and dropping them from training
   moves the all-complaints citywide 24-hour figure from 58.6% to 59.9% (borough-by-type
   changes at most 2.1 points, tract map correlation 0.9975) while predicting the requests that
   were *not* flagged only negligibly better (log-loss −0.0004) and all requests worse
   (+0.0014) ([robustness_checks.md](robustness_checks.md)).

For the current window the funnel was: **7.52M → 7.08M** kept, with about 286k
double-submissions collapsed, 131k exact-zero durations dropped, and 114k batch-closure flags.
The full table is in
[evaluation_results.md](evaluation_results.md).

### 2.2 Right-censoring: only judging requests old enough to have an outcome

> If a request was filed three days ago, we can't yet know whether it
> will be resolved "within a month" — it simply hasn't had the chance. Counting recent,
> still-open requests would make the city look slower than it is. So we only use requests
> filed at least 31 days before we pulled the data. For those, if it's still open, we know
> for certain it took *more than a month* — no guessing required.

This is the one genuinely subtle statistical point, and it's handled exactly rather than
approximately. Let `M` = pull date − 31 days. We keep only requests with `created_date ≤ M`
("matured"). Among them:

- closed requests are assigned to their observed duration bin;
- still-open requests are assigned to **bin 9 ("more than a month")** — which is *exact*,
  because a matured request still open has already been open longer than 31 days, so its
  final duration is certainly in the top bin. No survival-analysis imputation is needed.

The one cost is that the freshest 31 days of data go unused (~6% of the window). The residual
bias — a small number of requests that are *never* administratively closed — is real and
truthful ("this effectively won't be resolved within a month is useful information"), and we
track it: any complaint type where more than 20% of matured requests are still open gets a
`high_open_share` flag in the export.

---

## 3. Turning counts into probabilities — the intuition

> The naïve way to estimate "chance a noise complaint here is resolved
> same-day" is to look at past noise complaints on that block and compute the fraction that
> were. That works great on a busy block with thousands of complaints. But on a quiet block
> with three complaints, "2 out of 3 = 67%" is basically noise — flip one case and it's 33%.
> Our model fixes this by blending each block's own history with the pattern of its
> surrounding neighborhood, then borough, then the whole city. Lots of local data → we mostly
> trust the block. Little local data → we mostly show the neighborhood. This blending is the
> heart of the method, and statisticians call it *partial pooling* or *shrinkage*.

The rest of §3–§6 makes that blending precise, defensible, and — crucially — **fast enough to
update as new data arrives**.

---

## 4. The model

> Think of it as a family tree. The whole city has an average pattern
> for, say, heat complaints. Each borough is a variation on the city's pattern; each
> neighborhood a variation on its borough's; each block a variation on its neighborhood's.
> A block with little data mostly inherits its neighborhood's pattern; a block with lots of
> data is allowed to look like itself. We compute this top-down, and every estimate comes
> with a built-in measure of how confident we are.

### 4.1 Model class

We use a **hierarchical Dirichlet–Multinomial** model, fitted **once per threshold**. Each
request in a cell (tract × type) falls into one of nine bins, so the bin counts are
**Multinomial** and the natural, conjugate prior is a **Dirichlet**. "Hierarchical" means each
cell's Dirichlet prior is centered on its parent's estimated distribution. The map shows
cumulative probabilities ("resolved within X"), and a Dirichlet merged over categories is
again a Dirichlet with summed parameters, so for each of the eight thresholds we merge the
nine bins into two ("within X" versus "later") and fit that two-category hierarchy with its
own pooling strengths. That matters because how much tracts genuinely differ depends on the
threshold: one strength shared across all nine bins is dominated by the quiet bins and
over-pools exactly the rates the map displays (§6.3, §7.1). The eight fits are independent, so
their cumulative curves can cross by tiny amounts; they are made non-decreasing with a running
maximum (measured: 21.5% of cells have some crossing, but the 99th-percentile drop is 0.00002
and the mean adjustment 0.00001), and bin probabilities are obtained by differencing, with a
floor of 10⁻⁶ so none is exactly zero.

Why this class and not something fancier (a survival model, a neural net)? Three reasons:
(1) the deliverable *is* the binned distribution, so modeling continuous time buys nothing we
show; (2) conjugacy gives **closed-form** answers — no MCMC — so the whole city fits in
seconds on a laptop and updates cheaply; (3) every quantity the interface needs (means,
uncertainty intervals, a shrinkage indicator) falls out analytically. Alternatives are
discussed and rejected in [model_spec.md §1](model_spec.md).

### 4.2 The generative story

For a fixed complaint type and threshold, with concentration parameters κ at each level (shown
for the full nine-bin distribution; each threshold uses the same structure on two categories):

```
p_city    ~ Dirichlet(½ · 1)                     # weak "Jeffreys" prior at the root
p_borough ~ Dirichlet(κ₁ · p_city)               # each borough centered on the city
p_NTA     ~ Dirichlet(κ₂ · p_borough)            # each neighborhood on its borough
p_tract   ~ Dirichlet(κ₃ · p_NTA)                # each tract on its neighborhood
bin_i     ~ Categorical(p_tract)                 # each matured request
```

Pooling flows **within a complaint type, across geography** — a sparse tract×"heat" cell is
shrunk toward its neighborhood's *heat* pattern, not toward its own all-complaints mix,
because resolution speed is driven far more by what the complaint is (which agency owns it,
what the legal response window is) than by where it is.

### 4.3 How an estimate is computed

We use the standard top-down **conjugate cascade**, run separately for each threshold: each
node's posterior is a Dirichlet whose parameters are its parent's posterior *mean* (scaled by
κ) plus the node's own counts.

```
a_tract = κ₃ · (parent NTA mean) + (this tract's bin counts)
```

Everything the app shows is then closed-form from `a_tract` (with `A = Σ a`):

- **Posterior mean** for each bin: `aₖ / A` — the probabilities on the ladder.
- **Cumulative** "within X": partial sums of those means — the map metric.
- **Uncertainty**: the soft "faded bar ends" in the panel are 90% intervals built from three
  variance components: the Dirichlet posterior's **sampling variance** (a standard closed
  form); the **uncertainty of the neighborhood mean** the tract borrows, weighted by how much
  of the estimate is borrowed, `(κ/A)² × Var(parent)`; and a per-type **regime variance**
  estimated from rolling temporal holdouts — because a cell's realized near-future rate moves
  with seasonality and agency behavior, not just sampling noise (§6.1 shows why this
  component is essential). Half-width = 1.645·√(sampling + (κ/A)²·parent + regime²).
- **Shrinkage weight** `λ = n / (n + κ₃)` ∈ [0, 1]: the share of the estimate that comes
  from *this tract's own data* versus the borrowed neighborhood pattern (reported with the
  24-hour threshold's κ).

> That last number, λ, is what powers the "data strength" dots in the
> app. λ near 1 ("Strong local data," ●●●) means the estimate is essentially this tract's own
> record. λ near 0 ("Limited"/"No local data," ○○○, shown with a "~" and a wider faded range)
> means you're mostly looking at the neighborhood, honestly labeled as such.

### 4.4 How much to blend: learning κ from the data

The concentration parameters κ decide *how strongly* a child is pulled toward its parent — in
plain terms, "how many requests' worth of belief" the parent's pattern is worth before local
data takes over. Rather than guess them, we **learn them from the data** by empirical Bayes:
for each (threshold, type, level) we maximize the exact Dirichlet–Multinomial marginal likelihood by
**bounded scalar optimization over log κ** (about thirty likelihood evaluations per
parameter). Types with fewer than 8 well-populated children fall back to a pooled per-level
estimate. An implementation note for practitioners: the commonly used Minka fixed-point
iteration was tried first and quietly converged far short of the optimum on these flat
likelihood surfaces (checked against a direct likelihood grid), systematically
under-pooling — direct bounded maximization is just as cheap here and exact.

The learned κ's vary by complaint type: strong pooling where resolution speed is uniform
within a neighborhood, weaker where there is genuine block-to-block variation. Very large
values (several types sit at the 5,000 ceiling at the tract level) should not be read as
proof of "no tract-level signal": in simulations with known truth this estimator overstates
the tract-level strength by 45% or more (§6.2). Fitting the strengths on undecayed rather than
decay-weighted counts (where they are far smaller for several types, e.g. Street Condition
57 against the 5,000 ceiling) predicted no better in the rolling test
([kappa_source_evaluation.md](kappa_source_evaluation.md)), so the decay-weighted fit stays. The full κ table is in
[evaluation_results.md](evaluation_results.md).

### 4.5 An honest note on the approximation

The cascade plugs in each parent's *mean* instead of sampling it. Two checks show how much
that matters. First, it ignores the uncertainty of the neighborhood mean a tract borrows,
which by itself makes the Dirichlet intervals too narrow when pooling is strong (43–81%
coverage for nominal 90% intervals in simulations that follow the model exactly), so the
interval variance includes the analytic term in §4.3. Second, against a fully Bayesian fit in
Stan that samples both concentrations and the neighborhood distributions, the plug-in tract
means differ by 0.7–1.1 points on average (§6.2). Neither moves a typical tract by more than
about a point.

---

## 5. Keeping estimates fresh — time decay and weekly refits

> The city changes: agencies get faster or slower, policies shift, seasons turn. So recent
> requests count for more than old ones — a request from last month carries more weight than
> one from a year ago. And the whole model is rebuilt from the latest data every week, so the
> map never drifts far from what has just happened.

**Time decay.** Each request contributes a weight `2^(−age / h)` with **half-life h = 90 days**
(a request 90 days old counts half as much as a brand-new one). The value was chosen
empirically (§6): the rolling-origin test finds half-lives from 45 to 180 days statistically
indistinguishable, and clearly worse results at 365 days and with no decay at all.

**Refresh.** A scheduled job (`.github/workflows/refresh-data.yml`) pulls a rolling two-year
window every week, refits the entire model — concentrations, interval calibration and
per-type regime variances included — validates the export
([`pipeline/validate_export.py`](../pipeline/validate_export.py)), and publishes only if every
check passes. A full refit takes minutes, so nothing is carried between runs and there is no
incremental state to go stale. The map lags real time by about 31 days because a request has
to be that old for its outcome to be known (§2.2). The complaint-type list is pinned in
[`pipeline/types.json`](../pipeline/types.json), so a refresh cannot silently add or drop a
type when a borderline or seasonal one crosses the top-20 line.

---

## 6. How we know it works

> We didn't just pick a method and hope. We built nine versions — from a baseline that ignores
> the neighborhood entirely, up to the full model with learned blending and time decay — and
> tested each on requests it had never seen. Letting thin blocks borrow from their neighborhood
> matters a great deal; giving recent data more weight helps, but the exact amount barely
> matters. Then we tried to break the model: with simulated data whose true answer we knew, and
> by re-fitting it in a fully Bayesian way. Point estimates held up; the checks exposed real
> problems with the theory behind the intervals and with how strongly the model pools, both
> described below.

**Protocol.** Two tests. A single split trains on the first 12 months of the window and tests
on the next 12. A rolling-origin test mirrors how the map is used: at the start of each of 11
months, refit on everything earlier and score only that month. All settings (the κ's, the
complaint-type list, the interval calibration) are learned on the training data only.

**Scoring.** The headline metric is the **Ranked Probability Score (RPS)**, the right metric
here because the bins are *ordered*: predicting "2–3 days" when the truth was "1 week" should
be penalized less than predicting "3 hours." We also report **log-loss**, **calibration
error** on the "within 24h" and "within 7d" claims, and interval calibration — all broken out
by how much training data each cell had (`n = 0`, `n < 30`, `n ≥ 30`), because the sparse
cells are where methods differ. Uncertainty on every comparison comes from a **block
bootstrap over tract × type cells**.

**Single split (lower RPS is better):**

| Configuration | RPS | vs. best |
|---|---|---|
| No pooling, uniform prior (baseline) | 0.10685 | +0.00395 |
| No pooling, Jeffreys prior | 0.10548 | +0.00258 |
| Hierarchy, fixed blending | 0.10365 | +0.00075 |
| Hierarchy, learned κ per type | 0.10316 | +0.00026 |
| Hierarchy, learned κ per type & level | 0.10318 | +0.00028 |
| + time decay, 90-day half-life (previous model) | 0.10302 | +0.00012 |
| + time decay, 180-day half-life | 0.10290 | best |
| + time decay, 365-day half-life | 0.10297 | +0.00007 |
| + time decay, 90-day, sibling-only prior | 0.10300 | +0.00010 |
| **+ time decay, 90-day, separate pooling per threshold (shipped)** | **0.10297** | +0.00007 |

> The biggest effect by far is letting thin blocks borrow from their neighborhood: the
> no-pooling baselines are clearly worse, and on blocks the model had never seen they collapse
> to a useless "all outcomes equally likely" guess, while the hierarchy still gives a sensible
> neighborhood-based answer.

The clearest illustration is the sparse stratum: on tract × type cells with **no** training
data, the no-pooling baselines score a log-loss of 2.197 — exactly `log(9)`, the score of a
shrug that says every bin is equally likely — against 1.73–1.88 for the hierarchical models,
which fall back to the neighborhood.

**Which decay?** The single split cannot decide, and its ranking (180 days ahead of 90) is
partly an artifact: it trains once and predicts up to a year ahead, which penalizes short
memory, whereas the deployed map is refit weekly and only ever predicts the near future. The
rolling-origin test is the one that matches deployment:

| Half-life (nine-bin model) | RPS vs. its 90-day version (± SE) |
|---|---|
| 45 days | +0.00003 ± 0.00004 |
| 60 days | +0.00001 ± 0.00002 |
| **90 days** | — |
| 120 days | +0.00000 ± 0.00001 |
| 180 days | +0.00004 ± 0.00003 |
| 365 days | +0.00014 ± 0.00005 |
| none | +0.00040 ± 0.00008 |

Decay matters; the value between 45 and 180 days does not. The same test on the shipped
per-threshold model gives 45 days −0.00010 ± 0.00003 in RPS but +0.0026 ± 0.0004 in log-loss
and 180 days +0.00014 ± 0.00003 in RPS, so 90 stays. Against the nine-bin model with the same
decay, the per-threshold model is better by 0.00019 ± 0.00002 in RPS
([rolling_evaluation.md](rolling_evaluation.md)).

### 6.1 The uncertainty story: what the intervals had to learn the hard way

> A plain-vanilla version of this model produces very tight "plausible ranges" on busy
> blocks — thousands of past requests, so the math says it knows the rate precisely. But
> when we tested those ranges against what actually happened next, they were wrong far too
> often. The reason isn't randomness; it's that city services *change* — with the seasons,
> with agency staffing and backlogs, with policy. So the shipped ranges include a second
> ingredient, measured from history: how much each complaint type's rates typically move
> over a couple of months. Busy blocks now get honest ranges instead of falsely precise
> ones, and quiet blocks are barely affected (their ranges were already wide).

Technically, the raw Dirichlet intervals badly under-covered on dense cells. In the original
audit, coverage of nominal 90% intervals was about 0.44 on a cross-year backtest, still only
about 0.51 on an **even/odd-day split** where drift is impossible by construction, and about
0.25 against rolling next-60-day holdouts. The failures concentrate where sampling variance
is tiny, so any systematic movement lands outside the interval. The fix is a per-type,
per-threshold **additive regime variance** σ estimated from rolling temporal holdouts inside
the training window: half-width = 1.645·√(sampling variance + σ²), additive rather than
multiplicative so sparse cells are only modestly widened. On the current data, cells with at
least 50 test requests are covered 91.1% of the time, and in sparse cells (fewer than 30
training requests, at least 10 test requests) the squared standardized residual is 1.05 with
90.7% of cells inside their interval, both close to the targets. The 7-day calibration error
is 0.016.

Three follow-up checks on the shipped model ([robustness_checks.md](robustness_checks.md),
[interval_calibration_rolling.md](interval_calibration_rolling.md)):

- **The even/odd-day shortfall is mostly a matter of what is compared.** Holding out odd days
  and comparing their observed rate with the interval for the *true* rate gives coverage 0.69
  in dense cells; the held-out half is itself a finite sample, and adding its binomial noise
  raises coverage to 0.89. Correlated outcomes account for the rest: outcomes cluster by day
  (Pearson dispersion of daily counts within cells 1.29 on average, 3.25 for Snow or Ice, 1.74
  for Noise - Street/Sidewalk), and inflating the sampling variance by the dispersion measured
  on the training half brings coverage to 0.903. Batch closures are not the cause: removing
  them leaves the pooled dispersion at 1.29 and moves coverage by 0.001. (The original 0.51 was
  measured on an earlier model and window and was not reproduced with the old code.)
- **Types with almost no regime variance.** Dense-cell coverage is 0.91–0.96 for Noise -
  Commercial, Noise - Residential, Illegal Parking, Blocked Driveway and Unsanitary Condition.
  Noise - Street/Sidewalk is under-covered (0.86; squared residual 1.8): its rate is about
  99.5%, where a Gaussian interval is a poor description, and its outcomes cluster by day.
  Inflating by the measured dispersion barely helps (0.88), so this is left as a known limit.
- **Thin types fall back to a pooled regime variance and are under-covered in the single
  split** (Street Condition 0.69, Dirty Condition 0.67, Water System 0.84 in dense cells).
  Lowering the holdout cell threshold from 50 to 20 requests fixes those three in the single
  split but breaks others, and under the deployed protocol (σ re-estimated before each of 11
  months, next month scored) the two settings have the same coverage, 0.874, with a worse mean
  squared residual at 20 (8.8 against 4.6), so 50 is kept. Honestly reported: under that
  protocol overall coverage of the nominal 90% intervals is 0.874, driven by a few types (Snow
  or Ice 0.11 on 119 cells, Other 0.86); it is lower than the 0.911 of the single split.

### 6.2 Checking the approximation: simulation and a fully Bayesian fit

> We generated fake data from the model itself, where the true answer is known, and checked
> whether the model finds it. It does, for the estimates. The intervals were too narrow when
> neighborhoods were tightly pooled, because they ignored how well the neighborhood's own
> pattern is known. We fixed that, and then re-fit a simplified version of the model in Stan, a
> tool that doesn't take any shortcuts, and confirmed the shortcut we use costs about a point.

Simulation (`pipeline/sim_check.py`, [simulation_check.md](simulation_check.md)): data drawn
from the hierarchical model with known concentrations, on the real geography and volumes.
Tract-level accuracy is identical for every variant. Nominal 90% intervals covered the true
tract value in only 81%, 63% and 43% of tracts in three scenarios of decreasing tract-level
heterogeneity; adding the parent-uncertainty term brings coverage to 89–90% when the true
concentrations are supplied, and 80–85% with estimated ones, because the estimator
overstates the tract-level pooling (true 100, 300, 1,500; estimated 145, 705, and the 5,000
ceiling). A sibling-only variant that removes the double-counting of a tract's own data in its
parent mean errs the other way (76, 186, 533) and gives conservative intervals (92–96%). On
real data the regime variance is much larger than the parent term for most types (median 0.09
against a median SD of 0.008 in sparse cells), so the correction changes the median interval
by about a tenth of a point; where the regime variance is zero (Noise - Commercial) it widened
the intervals of sparse-neighborhood cells by up to 0.145, from about ±0.007.

Stan (`pipeline/stan_check.py`, [stan_validation.md](stan_validation.md)): a hierarchical
model in which both concentrations and the neighborhood distributions are sampled, fitted to
Brooklyn's last 365 days for Heat/Hot Water, Street Condition and Water System on merged
"within 24 hours / later" counts (a Dirichlet merged over categories is a Dirichlet with
summed parameters). Recovery of known parameters from simulated data works (both
concentrations inside their 99% intervals; 88.7% of tract intervals cover the truth), and the
real-data fits are clean (no divergences, R̂ ≤ 1.008). Against a plug-in cascade on the same
counts, the tract means differ by 0.7–1.1 points on average and the uncertainty ratio is
1.01–1.11.

### 6.3 The per-threshold model, and options not adopted

- **A separate pooling strength per threshold — adopted** ([cutwise_evaluation.md](cutwise_evaluation.md),
  [rolling_evaluation.md](rolling_evaluation.md)). The Stan fits found much weaker pooling of
  the 24-hour rate than the single-strength model (Street Condition, Brooklyn: tract κ ≈ 29
  against the 5,000 ceiling), so the earlier model was over-smoothing the very rates the map
  shows. Fitting one two-category hierarchy per threshold improves held-out log-loss at all
  eight thresholds (by 0.06–0.32%, each at least 3 standard errors), and in the rolling-origin
  evaluation it beats the nine-bin model with the same decay by 0.00019 ± 0.00002 in RPS and
  0.00084 ± 0.00016 in log-loss. The gain for the all-complaints view is small (2 standard
  errors at 24 hours, gone beyond a week) and mixed by type (worse for Snow or Ice at 24 hours
  and Street Condition at one week; much better for Snow or Ice at one week). It is adopted
  because the maps should show the variation the data support: within a borough, the
  tract-to-tract standard deviation of P(≤24h) rose from 0.010 to 0.026 for Heat/Hot Water,
  0.014 to 0.036 for Water System, 0.018 to 0.035 for Encampment and 0.027 to 0.042 for Street
  Condition (tracts with at least 30 requests); it is unchanged where tracts genuinely do not
  differ (Illegal Parking, the noise types, all near 99%). A single-split evaluation is
  marginally worse in log-loss (1.3403 against 1.3383), since it favors long memory.
- **Same-season-last-year blending.** With two years of history the best variant improves RPS
  by 0.00013 and log-loss by 0.0018 but wins in only 5 of 11 months.
- **A sibling-only prior** (excluding a unit's own counts from its parent mean): no
  measurable predictive gain.

---

## 7. What the app shows, mapped to the math

| In the app | Is this quantity |
|---|---|
| Tract color | Posterior-mean cumulative probability "resolved within X" for the selected type |
| Big headline % | The same number for the selected tract, tracking the time scrubber |
| Resolution-ladder bar length | Posterior-mean cumulative probability at each of the 8 thresholds |
| Brighter cap on each bar | That bin's individual probability (the increment) |
| Faded bar end | 90% interval: sampling variance + uncertainty of the borrowed neighborhood mean + calibrated regime variance (§4.3, §6.1) |
| "1 month+" row | The tail probability — chance it takes longer than a month |
| Data-strength dots ●●● / ○○○ | Shrinkage weight λ = n/(n+κ): how much is local vs. borrowed |
| "~" prefix and wider fades | Low-data cells, flagged for honesty |
| "Compared to" strip | Tract vs. borough vs. citywide posterior means |

Every per-tract record exported to the browser
([`web/data/probs.json`](../web/data/probs.json)) carries the bin probabilities, the credible
interval bounds, the raw observation count, and the shrinkage weight, so nothing on screen is
computed in a way the data can't back up.

### 7.1 Why some maps look nearly uniform — and the two shading modes

> A lot of complaint types resolve at roughly the same speed everywhere in the city, so their
> maps look almost one color. That's usually real, not a glitch: things like illegal parking,
> missed collections, or traffic-signal repairs run on citywide agency schedules, so where you
> are barely matters. Other types — heat, sanitation — genuinely differ block to block. The
> "Absolute / Relative" switch lets you see both stories.

This is worth stating plainly because it's easy to misread. For high-volume, agency-scheduled
types the tract-to-tract spread in the *raw* data really is tiny — e.g., the middle 50% of
Brooklyn tracts differ in their "resolved within 24h" rate for illegal parking by well under
one percentage point — so a nearly uniform map is the honest picture there. For other types
there was a second effect, now fixed: the earlier model pooled all nine duration bins with a
single strength per type and level, and where the 24-hour rate varies a lot between tracts
while the other bins barely do, that shared strength over-pooled the 24-hour rate. The Stan
check put the tract-level pooling strength for Street Condition in Brooklyn near 29, against
the 5,000 ceiling in that model. The shipped model fits a separate strength per threshold
(§6.3), which roughly doubled to tripled the within-borough spread for heat, water,
encampment and street-condition complaints. Types with genuine local structure (Heat/Hot
Water, Dirty Condition) show a visibly wider spread; the near-uniform types stay uniform.

Two consequences for reading the map:

- **Absolute shading** (default) colors every tract on a fixed 0–100% scale. Colors mean the
  same thing across every complaint type and time threshold — essential for honest comparison
  and for the play-button animation — but a type whose values all sit in a narrow band (say
  96–100%) shows as one color.
- **Relative shading** stretches the color ramp across only the values currently in view (the
  focused borough, or the whole city). This surfaces the real-but-small variation that the
  absolute scale flattens — which tracts are the local outliers — while the legend always
  prints the actual numeric range (e.g., "96%–100%"), so a stretched-out 4-point spread can
  never be mistaken for a dramatic one. The underlying probabilities and the tract panel are
  identical in both modes; only the color mapping changes.

---

## 8. Reproducing this

```
python3 pipeline/fetch_311.py      # rolling two-year window of raw 311 data
python3 pipeline/prepare.py        # clean, assign tracts, bin durations
python3 pipeline/evaluate.py       # single-split prior comparison (§6)
python3 pipeline/eval_rolling.py   # rolling-origin comparison: decay, seasonality (§6)
python3 pipeline/export_web.py     # fit the shipped model, write the app's data
python3 pipeline/validate_export.py  # checks the export before it is published
python3 pipeline/audit.py          # independent end-to-end audit against the raw files
python3 -m http.server 8012 --directory web   # open http://localhost:8012
```

The design rationale for the interface is in [design_spec.md](design_spec.md); the full
statistical specification, including every equation and edge case summarized here, is in
[model_spec.md](model_spec.md); the complete results tables are in
[evaluation_results.md](evaluation_results.md).

---

*Data: NYC Open Data, 311 Service Requests. This is an independent analysis and is not
affiliated with or endorsed by the City of New York. Resolution times reflect when the city
recorded a request as closed, which for some complaint types means "acknowledged" or
"scheduled" rather than physically fixed.*
