# Methods — How Fast Does New York Fix It?

The whole method in one paragraph:

> We took roughly five million 311 service requests, measured how long each one took to
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

**Window.** All requests created between **2025-01-01 and 2026-06-03** — about
**5.34 million** requests. The end date is deliberately ~31 days before the data pull; §4
explains why.

**Geography.** Each request's latitude/longitude is assigned to a 2020 census tract by
point-in-polygon test against the city's official tract boundaries. Tracts roll up into
**Neighborhood Tabulation Areas** (NTAs, ~260 of them), which roll up into **boroughs** (5),
which roll up into the **city** (1). This four-level hierarchy is the backbone of the model
(§5). 98.3% of requests carry usable coordinates; the rest are kept only at the borough/city
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
   them is the honest choice: the recorded closure is what the requester experienced.

For this run the funnel was: **5.34M → 5.04M** kept, with ~188k double-submissions, ~97k
exact-zero durations, and ~85k batch-closure flags. The full table is in
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

We use a **hierarchical Dirichlet–Multinomial** model. Each request in a cell (tract × type)
is a draw from a 9-category distribution `p` (the probabilities of the nine bins). The
category counts are therefore **Multinomial**; the natural, conjugate prior for `p` is a
**Dirichlet**. "Hierarchical" means each cell's Dirichlet prior is centered on its parent's
estimated distribution.

Why this class and not something fancier (a survival model, a neural net)? Three reasons:
(1) the deliverable *is* the binned distribution, so modeling continuous time buys nothing we
show; (2) conjugacy gives **closed-form** answers — no MCMC — so the whole city fits in
seconds on a laptop and updates cheaply; (3) every quantity the interface needs (means,
uncertainty intervals, a shrinkage indicator) falls out analytically. Alternatives are
discussed and rejected in [model_spec.md §1](model_spec.md).

### 4.2 The generative story

For a fixed complaint type, with concentration parameters κ at each level:

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

We use the standard top-down **conjugate cascade**: each node's posterior is a Dirichlet
whose parameters are its parent's posterior *mean* (scaled by κ) plus the node's own counts.

```
a_tract = κ₃ · (parent NTA mean) + (this tract's bin counts)
```

Everything the app shows is then closed-form from `a_tract` (with `A = Σ a`):

- **Posterior mean** for each bin: `aₖ / A` — the probabilities on the ladder.
- **Cumulative** "within X": partial sums of those means — the map metric.
- **Uncertainty**: the soft "faded bar ends" in the panel are 90% intervals built from two
  variance components: the Dirichlet posterior's **sampling variance** (a standard closed
  form), plus a per-type **regime variance** estimated from rolling temporal holdouts —
  because a cell's realized near-future rate moves with seasonality and agency behavior,
  not just sampling noise (§6.1 shows why this second component is essential, not optional).
  Half-width = 1.645·√(sampling + regime²).
- **Shrinkage weight** `λ = n / (n + κ₃)` ∈ [0, 1]: the share of the estimate that comes
  from *this tract's own data* versus the borrowed neighborhood pattern.

> That last number, λ, is what powers the "data strength" dots in the
> app. λ near 1 ("Strong local data," ●●●) means the estimate is essentially this tract's own
> record. λ near 0 ("Limited"/"No local data," ○○○, shown with a "~" and a wider faded range)
> means you're mostly looking at the neighborhood, honestly labeled as such.

### 4.4 How much to blend: learning κ from the data

The concentration parameters κ decide *how strongly* a child is pulled toward its parent — in
plain terms, "how many requests' worth of belief" the parent's pattern is worth before local
data takes over. Rather than guess them, we **learn them from the data** by empirical Bayes:
for each (type, level) we maximize the exact Dirichlet–Multinomial marginal likelihood by
**bounded scalar optimization over log κ** (about thirty likelihood evaluations per
parameter). Types with fewer than 8 well-populated children fall back to a pooled per-level
estimate. An implementation note for practitioners: the commonly used Minka fixed-point
iteration was tried first and quietly converged far short of the optimum on these flat
likelihood surfaces (checked against a direct likelihood grid), systematically
under-pooling — direct bounded maximization is just as cheap here and exact.

The learned κ's are interpretable and vary sensibly by complaint type: strong pooling where
resolution speed is uniform within a neighborhood, weaker where there is genuine
block-to-block variation, and very large κ for spatially smooth types — the model correctly
saying "there is essentially no tract-level signal here beyond the neighborhood." The full
κ table is in [evaluation_results.md](evaluation_results.md).

### 4.5 An honest note on the approximation

The cascade plugs in each parent's *mean* rather than propagating full parent uncertainty
downward. This is the standard, defensible trade for tractability: parent nodes aggregate
thousands to millions of requests, so their means are pinned down tightly, and the uncertainty
that actually matters — the spread at a thin tract cell — is retained exactly. A 200-draw
refinement that propagates parent uncertainty is specified and available if calibration
diagnostics ever demand it (§6 shows they didn't warrant it here).

---

## 5. Keeping estimates fresh — time decay and updating

> The city changes: agencies get faster or slower, policies shift,
> seasons turn. So we let recent requests count for more than old ones — a request from last
> month carries more weight than one from a year ago. And when a new month of data arrives,
> we don't refit from scratch; we gently "age" the existing counts and add the new ones. Today's
> answer becomes tomorrow's starting point.

**Time decay.** Each request contributes a weight `2^(−age / h)` with **half-life h = 90 days**
(a request 90 days old counts half as much as a brand-new one). This value was chosen
empirically (§6), not by hand.

**Incremental update.** Because matured requests never change bins (§2.2), updating
is a single conjugate step — "decay-then-add":

```
ñ ← ñ · 2^(−Δ/h)  +  (decay-weighted counts of the newly matured cohort)
```

then re-run the O(cells) cascade with the stored κ table. Concentrations are re-estimated only
on a quarterly full refit. This is formally an exponential-forgetting / power-prior filter — we
label it as such rather than overselling it as exact dynamic Bayes. The recipe lives in
[`pipeline/update.py`](../pipeline/update.py) and [model_spec.md §8](model_spec.md).

---

## 6. How we know it works — testing the priors

> We didn't just pick a method and hope. We built eight versions —
> from a dumb baseline that ignores the neighborhood entirely, up to the full model with
> learned blending and time decay — and staged a fair contest: train each on the first year
> of data, then see which best predicts what *actually* happened in the following five months,
> on requests it had never seen. The full model won, decisively, and the time-decay versions
> won among those. We report the whole scoreboard, including where the model is weakest.

**Protocol.** Train on requests created in the first 12 months; test on the ~5 months after.
All settings (the κ's, the complaint-type list, the cleaning thresholds) are learned on the
training period only — the test period is untouched until scoring.

**Scoring.** The headline metric is the **Ranked Probability Score (RPS)**, which is the right
metric here because the bins are *ordered*: predicting "2–3 days" when the truth was "1 week"
should be penalized less than predicting "3 hours." We also report multinomial **log-loss**,
**calibration error** on the two headline claims ("within 24h" and "within 7d"), and
**credible-interval coverage** — all broken out by how much training data each cell had
(`n = 0`, `n < 30`, `n ≥ 30`), because the sparse cells are exactly where methods differ.
Uncertainty on the comparison comes from a **block bootstrap over cells**.

**Result (lower RPS is better):**

| Configuration | RPS | vs. best |
|---|---|---|
| No pooling, uniform prior (baseline) | 0.1096 | +0.0032 |
| No pooling, Jeffreys prior | 0.1086 | +0.0022 |
| Hierarchy, fixed blending | 0.1074 | +0.0010 |
| Hierarchy, learned κ per type | 0.1070 | +0.0006 |
| Hierarchy, learned κ per type & level | 0.1070 | +0.0006 |
| **+ time decay, 90-day half-life (shipped)** | **0.1064** | **best** |
| + time decay, 180-day half-life | 0.1067 | +0.0003 |
| + time decay, 365-day half-life | 0.1068 | +0.0004 |

> The two things that mattered most: (1) letting thin blocks borrow
> from their neighborhood — the no-pooling baselines are visibly worse, and on blocks the
> model had never seen they collapse to a useless "all outcomes equally likely" guess, while
> the hierarchy still gives a sensible neighborhood-based answer; (2) weighting recent data
> more. The winner does both.

The clearest illustration is the sparse stratum: on cells with **no** training data, the
no-pooling baselines score a log-loss of 2.197 — which is exactly `log(9)`, the score of a
shrug that says every bin is equally likely — while the hierarchy scores ~1.44 by falling
back to the neighborhood. That gap is the entire value proposition of the method.

### 6.1 The uncertainty story: what the intervals had to learn the hard way

> A plain-vanilla version of this model produces very tight "plausible ranges" on busy
> blocks — thousands of past requests, so the math says it knows the rate precisely. But
> when we tested those ranges against what actually happened next, they were wrong far too
> often. The reason isn't randomness; it's that city services *change* — with the seasons,
> with agency staffing and backlogs, with policy. So the shipped ranges include a second
> ingredient, measured from history: how much each complaint type's rates typically move
> over a couple of months. Busy blocks now get honest ranges instead of falsely precise
> ones, and quiet blocks are barely affected (their ranges were already wide).

Technically, the raw Dirichlet intervals badly under-covered on dense cells, and stress
tests showed drift alone doesn't explain it: coverage was ~0.44 on the cross-year backtest,
still only ~0.51 on an **even/odd-day split** where drift is impossible by construction, and
~0.25 against rolling next-60-day holdouts. The failures concentrate where sampling variance
is tiny, so any systematic regime movement (seasonality, batch closures, policy shifts)
lands outside the interval. The fix is a per-type, per-threshold **additive regime variance**
σ estimated from rolling temporal holdouts inside the training window: interval half-width
= 1.645·√(sampling variance + σ²). Additive rather than multiplicative, so sparse cells —
whose intervals are dominated by sampling uncertainty — are only modestly widened. With this
calibration, backtest coverage lands at 0.90–0.92 (in the guardrail), and a fully
out-of-sample next-60-day check gives 0.87 — slightly under target because early 2026 moved
more than anything in the calibration year. That residual is irreducible regime-shift risk;
the monthly update cycle re-centers the model continuously. The 7-day calibration error
(~0.02, marginally above the 0.02 guardrail) shares the same drift cause and the same
mitigation. We report these numbers rather than tuning them away.

A second honest caveat, unchanged: for several complaint types the model finds no meaningful
block-to-block difference and shows the neighborhood pattern everywhere — the correct answer
when the signal isn't there (§7.1).

---

## 7. What the app shows, mapped to the math

| In the app | Is this quantity |
|---|---|
| Tract color | Posterior-mean cumulative probability "resolved within X" for the selected type |
| Big headline % | The same number for the selected tract, tracking the time scrubber |
| Resolution-ladder bar length | Posterior-mean cumulative probability at each of the 8 thresholds |
| Brighter cap on each bar | That bin's individual probability (the increment) |
| Faded bar end | 90% interval: Dirichlet sampling variance + calibrated regime variance (§6.1) |
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
types the tract-to-tract spread in the *raw* data is tiny — e.g., the middle 50% of Brooklyn
tracts differ in their "resolved within 24h" rate for illegal parking by well under one
percentage point — and the model faithfully reports that near-uniformity rather than
inventing variation. The empirical-Bayes concentration for such types is correspondingly
large (strong pooling), which the evaluation confirms is the right call. Types with genuine
local structure (Heat/Hot Water, Dirty Condition) keep a visibly wider spread.

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
python3 pipeline/fetch_311.py     # download the raw 311 pulls (one-time, large)
python3 pipeline/prepare.py       # clean, assign tracts, bin durations
python3 pipeline/evaluate.py      # run the eight-way prior contest (§6)
python3 pipeline/export_web.py    # fit the winner, write the app's data
python3 -m http.server 8011 --directory web   # open http://localhost:8011
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
