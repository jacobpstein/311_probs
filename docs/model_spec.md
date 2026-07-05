# Model Specification: Bayesian Resolution-Time Distributions for NYC 311

**Target:** posterior distribution over 9 ordered resolution-time bins for every
(census tract × complaint type) cell, plus an all-types distribution per tract.

**Status:** methodology specification (v1.0). No production code here; §9 gives the
implementable pseudocode.

**Revision note (post-audit).** Two changes relative to this spec are shipped, both
documented in [statistical_review.md](statistical_review.md): (1) κ is estimated by
bounded maximization of the exact DM marginal likelihood rather than the Minka fixed
point of §2.1, which under-converged on flat likelihood surfaces; (2) the exact Beta
credible intervals of §1.3 are widened by a per-(type, cut) additive regime variance
estimated from rolling temporal holdouts — the coverage diagnostic of §7.2 exposed
material under-coverage that parent-uncertainty propagation alone would not fix.
Everything else (hierarchy, censoring, hygiene, evaluation design) ships as specified.

---

## 0. Notation and setup

- Bins `k = 1..K`, `K = 9`, with upper edges in hours:
  `EDGES = [3, 24, 48, 72, 168, 336, 480, 744, ∞]`
  i.e. (0,3h], (3h,24h], (24h,48h], (48h,72h], (72h,7d], (7d,14d], (14d,20d], (20d,31d], (31d,∞).
  Note 31 days = 744 h is the "month+" boundary; this constant also drives the
  censoring rule in §5.
- Complaint types `t ∈ {1..T, "ALL"}` with `T ≈ 15–25` named types plus `Other`.
  `ALL` is a separate, independently fitted tree over the union of all requests
  (it is **not** derived by summing the per-type outputs, so it gets its own
  correctly-calibrated shrinkage).
- Geographic hierarchy, per type: level 0 = citywide (1 node), level 1 = borough (5),
  level 2 = NTA (~260), level 3 = tract (~2,300). `pa(v)` denotes the parent node of `v`.
- For node `v` and type `t`: raw counts `n_{v,t,k}` (number of matured requests in bin k),
  decayed counts `ñ_{v,t,k}` (§4, §8), totals `n_{v,t} = Σ_k n_{v,t,k}`.
  Node counts are computed **directly from request rows** assigned to that node's
  geography, not by summing children (this lets rows with missing tract but known
  borough still inform upper levels; see §6.7).
- `ψ(·)` is the digamma function (`scipy.special.digamma`).

---

## 1. The model

### 1.1 Choice of model class (confirmation and justification)

The hierarchical Dirichlet–Multinomial (DM) over the 9 bins with geographic partial
pooling **is the right choice**, and we adopt it. Alternatives considered and rejected:

1. **Continuous-time survival model** (log-normal/Weibull AFT, or discrete-time hazard
   with tract random effects). Strictly more informative, but: requires non-conjugate
   inference (MCMC/VI) at 3–7M rows × 2,300 tracts, violates the laptop + incremental
   constraints, and the deliverable is the binned distribution anyway. Rejected.
2. **Ordered stick-breaking / continuation-ratio Beta–Binomial** (model the K−1
   conditional continuation probabilities `P(bin > k | bin ≥ k)` with independent
   Beta–Binomial hierarchies). This is exactly as conjugate as the DM (the Dirichlet is
   the special case where the Beta parameters telescope) and does **not** actually
   smooth across bins — adjacent-bin smoothing would require a random-walk prior on
   logits, which breaks conjugacy. The ordering of bins is instead respected at
   **evaluation** time via the ranked probability score (§7). Rejected as pure
   complexity; noted as a future extension if adjacent-bin smoothing is ever needed.
3. **Full hierarchical Bayes with sampled concentration parameters** (HDP-style).
   Not tractable in closed form; PyMC/numpyro on a 2,300 × 25 × 9 crossed hierarchy is
   feasible but slow, fragile on a laptop, and destroys cheap incremental updates.
   Instead we use **empirical Bayes for the concentration parameters only** (§1.5, §3)
   and exact conjugate updates for everything else. With ~260 NTAs and ~2,300 tracts
   per type, the concentration parameters are estimated from hundreds/thousands of
   groups, so EB plug-in uncertainty in κ is negligible relative to cell-level
   uncertainty. This is the standard, defensible tractability trade.

### 1.2 Generative model (per complaint type)

For fixed type `t`, with concentration parameters `κ₀` (city root), `κ₁` (city→borough),
`κ₂` (borough→NTA), `κ₃` (NTA→tract):

```
p_city,ALL              ~ Dirichlet(α₀·1_K)                    # global root, α₀ = 1/2 (Jeffreys)
p_city,t | p_city,ALL   ~ Dirichlet(κ₀ · p_city,ALL)           # type root borrows from all-types
p_b,t    | p_city,t     ~ Dirichlet(κ₁ · p_city,t)             # borough b
p_a,t    | p_b(a),t     ~ Dirichlet(κ₂ · p_b(a),t)             # NTA a
p_g,t    | p_a(g),t     ~ Dirichlet(κ₃ · p_a(g),t)             # tract g
bin_i | cell(i)=(g,t)   ~ Categorical(p_g,t)                   # each matured request i
```

The `ALL` tree is generated identically with its own `(κ₁ᴬ, κ₂ᴬ, κ₃ᴬ)` and root prior
`Dirichlet(½·1_K)`, fitted on all requests pooled across types.

**Crossing with type.** Pooling is routed **within type across geography** (tract→NTA→
borough→city), because resolution time is dominated by complaint type / responsible
agency, not geography; a sparse tract×type cell should look like its neighborhood's
distribution *for that type*, not like the tract's all-types mix. The only cross-type
pooling is at the root (`p_city,t` shrinks toward `p_city,ALL`), where it is harmless
(city×type counts are large, so this prior is almost irrelevant except for very rare
types inside "Other"). A convex two-parent prior (NTA×type blended with tract×ALL) was
considered and rejected: it has no conjugate form, requires an extra mixing weight per
cell, and the empirical gain is speculative. If the sparse-cell diagnostics in §7 show
systematic tract-level residual structure, revisit.

### 1.3 Inference: the conjugate cascade (exact update equations)

The full joint posterior is not conjugate (parents and children are coupled). We use
the standard **top-down cascade / plug-in approximation**: compute each node's Dirichlet
posterior using its own counts and its parent's posterior *mean* as the prior base
measure. Proceeding top-down:

```
a_city,ALL,k = α₀ + ñ_city,ALL,k                                (K-vector)
m_city,ALL,k = a_city,ALL,k / Σ_j a_city,ALL,j

a_city,t,k   = κ₀ · m_city,ALL,k + ñ_city,t,k
m_city,t,k   = a_city,t,k / Σ_j a_city,t,j

a_b,t,k      = κ₁ · m_city,t,k   + ñ_b,t,k       ; m_b,t = normalize(a_b,t)
a_a,t,k      = κ₂ · m_b(a),t,k   + ñ_a,t,k       ; m_a,t = normalize(a_a,t)
a_g,t,k      = κ₃ · m_a(g),t,k   + ñ_g,t,k       # ← the deliverable cell posterior
```

Every node's posterior is an **exact Dirichlet** given the plug-in parent mean:
`p_g,t | data ≈ Dirichlet(a_g,t)`. All downstream quantities are closed-form:

- **Posterior mean:** `E[p_k] = a_k / A`, where `A = Σ_k a_k`.
- **Posterior SD per bin:** `SD[p_k] = sqrt( a_k (A − a_k) / (A² (A + 1)) )`.
- **Cumulative probabilities:** by the Dirichlet aggregation property, for cut `c`,
  `P(bin ≤ c) = Σ_{k≤c} p_k ~ Beta(A_c, A − A_c)` with `A_c = Σ_{k≤c} a_k`.
  Exact 90% credible interval: `beta.ppf([0.05, 0.95], A_c, A − A_c)`.
- **Effective sample size / shrinkage:** local decayed data mass `ñ_g,t = Σ_k ñ_g,t,k`,
  prior mass `κ₃`, shrinkage weight (share of the posterior mean owed to local data)
  `λ_g,t = ñ_g,t / (ñ_g,t + κ₃) ∈ [0,1]`.

**Why the plug-in is defensible.** (i) Information still flows upward: parent counts
are the aggregate of all requests in the parent's geography, so the parent mean is the
correctly pooled estimate. What the cascade cuts is only the *feedback of child-level
fit into parent uncertainty* and the *propagation of parent uncertainty downward*.
(ii) Parent nodes are data-rich (an NTA×type node aggregates ~10 tracts; borough and
city nodes have 10³–10⁶ counts), so their posterior SDs are tiny compared with κ-scale
prior mass; plugging in the mean loses almost nothing. (iii) Where uncertainty matters
— sparse tract cells — the dominant uncertainty is the tract-level Dirichlet spread,
which is retained exactly. **Optional refinement** (cheap, implement only if CI
coverage in §7 comes in under-dispersed): propagate parent uncertainty by drawing
`S = 200` parent means `m^(s) ~ Dirichlet(a_parent)`, forming `a^(s) = κ₃ m^(s) + ñ`,
and reporting mixture-of-Dirichlets summaries (means average exactly; CI via pooled
Beta draws).

### 1.4 What plays the role of "the prior" for a cell

For tract cell `(g,t)`: an **informative Dirichlet prior** `Dirichlet(κ₃ · m_{a(g),t})`
— i.e., "κ₃ pseudo-requests distributed like this NTA's posterior for this type."
A cell with `ñ = 0` reports exactly its NTA's distribution with `λ = 0`; a cell with
`ñ = 5,000` is data-dominated with `λ ≈ 1`. This is transparent, monotone, and easily
explained in a UI.

### 1.5 Concentration parameters

`κ₁, κ₂, κ₃` (and `κ₀`) control pooling strength and are the only free
hyperparameters. They are estimated by **empirical Bayes on the Dirichlet–Multinomial
marginal likelihood** (§3), per (type, level) with pooled fallbacks. Candidate simpler
settings are part of the prior comparison (§4). `κ₀` is set, not estimated: `κ₀ = 5`
(weak; the city×type counts overwhelm it for every top-N type — it only matters for
regularizing "Other" and any future rare type).

---

## 2. Concentration estimation (empirical Bayes)

For a fixed type `t` and level `ℓ` (children `j = 1..J` under their respective
parents, child count vectors `n_j·` — decayed counts are fine, digamma accepts
non-integers), the marginal likelihood of the children given plug-in parent means
`m_j` (each child's own parent's mean) is Dirichlet–Multinomial:

```
ℓℓ(κ) = Σ_j [ logΓ(κ) − logΓ(n_j + κ) + Σ_k ( logΓ(n_jk + κ m_jk) − logΓ(κ m_jk) ) ]
```

### 2.1 Minka fixed-point update (primary estimator)

Maximize `ℓℓ(κ)` with Minka's fixed point for a Dirichlet with fixed mean and free
concentration (Minka 2000, *Estimating a Dirichlet distribution*):

```
           Σ_j Σ_k  m_jk · [ ψ(n_jk + κ m_jk) − ψ(κ m_jk) ]
κ ← κ ·   ─────────────────────────────────────────────────────
           Σ_j       [ ψ(n_j + κ) − ψ(κ) ]
```

Iterate until `|Δlog κ| < 1e-6` or 200 iterations. Skip children with `n_j = 0`
(they contribute nothing). Guard rails: clamp `κ ∈ [0.5, 5000]`; if fewer than 8
children have `n_j ≥ 5`, fall back to the pooled estimate (§2.3).

### 2.2 Method-of-moments initializer

The DM implies intra-class correlation `ρ = 1/(1+κ)` for the bin-indicator variables.
One-way ANOVA moment estimator, computed per bin `k` and combined:

```
N   = Σ_j n_j ;  n̄_c = (N − Σ_j n_j²/N) / (J − 1)
MSB_k = Σ_j n_j (p̂_jk − m̄_k)² / (J − 1)          # p̂_jk = n_jk/n_j, m̄_k = Σ_j n_jk / N
MSW_k = Σ_j n_j p̂_jk (1 − p̂_jk) / (N − J)         # within-group binomial variance
ρ̂_k  = (MSB_k − MSW_k) / (MSB_k + (n̄_c − 1)·MSW_k)
ρ̂    = Σ_k w_k ρ̂_k / Σ_k w_k   with  w_k = m̄_k (1 − m̄_k)     # precision-ish weights
κ̂_init = clip( (1 − ρ̂)/ρ̂ , 0.5, 5000 )            # if ρ̂ ≤ 0 → κ̂_init = 5000
```

Use `κ̂_init` to start §2.1 (also useful as a sanity cross-check: MoM and MLE should
agree within a factor of ~2–3; log a warning otherwise).

### 2.3 Pooling and fallback schedule for κ

- Estimate `κ̂_ℓ,t` for each (level ℓ ∈ {1,2,3}, type t) — ≤ 3 × 26 estimates.
- **Fallback:** if type `t` at level ℓ has < 8 children with `n_j ≥ 5`, use the
  level-pooled `κ̂_ℓ` (fitted on all types' children jointly at that level, each child
  paired with its own parent mean).
- The `ALL` tree gets its own `κ̂ᴬ_ℓ` at each level.
- κ estimation is done **once per full refit** (initial fit; then quarterly, §8),
  never inside the incremental monthly update.

---

## 3. Full posterior-update summary (closed form)

Everything after κ estimation is a single top-down pass of vectorized additions:

```
level 0 (ALL):  a = ½ + ñ_city,ALL
level 0 (t):    a = κ₀ · m_city,ALL + ñ_city,t
level 1:        a = κ₁,t · m_parent + ñ_borough,t
level 2:        a = κ₂,t · m_parent + ñ_NTA,t
level 3:        a = κ₃,t · m_parent + ñ_tract,t
```

Cost: (2,300 + 260 + 5 + 1) nodes × 26 types × 9 bins ≈ 600K floats — milliseconds in
numpy. The entire fit (excluding I/O and κ iteration) is O(rows) for the groupby plus
O(cells) for the cascade.

---

## 4. Prior configurations to test empirically

Six configurations. P0–P1 are non-hierarchical baselines (they must lose; if they
don't, the hierarchy is buggy). P2–P5 are the real candidates.

| ID | Name | Tract-cell prior | Specification |
|----|------|------------------|---------------|
| P0 | Uniform, no pooling | `Dirichlet(1_K)` | `a_g,t = 1 + n_g,t·`. No hierarchy, no decay. |
| P1 | Jeffreys, no pooling | `Dirichlet(½·1_K)` | `a_g,t = ½ + n_g,t·`. No hierarchy, no decay. |
| P2 | Hierarchy, fixed κ | cascade §1.3 | `κ₁ = κ₂ = κ₃ = 15` for all types (a defensible hand-set value ≈ "15 pseudo-requests from the parent"). No decay. |
| P3 | Hierarchy, EB κ per type | cascade §1.3 | Single `κ̂_t` per type shared across levels 1–3, fitted by §2 on the level-3 (NTA→tract) children only. No decay. |
| P4 | Hierarchy, EB κ per (type, level) | cascade §1.3 | `κ̂_ℓ,t` per level and type per §2.3, with pooled fallback. No decay. **Expected winner.** |
| P5a/b/c | P4 + time decay | cascade §1.3 | Decayed counts `ñ` with exponential half-life `h ∈ {90d (P5a), 180d (P5b), 365d (P5c)}`: request `i` contributes weight `w_i = 2^{−(t_ref − created_i)/h}` to its cell's bin count, `t_ref` = end of training window. κ re-estimated on decayed counts. |

Notes:
- P0 vs P1 also isolates the effect of prior mass in empty cells (P0 predicts uniform
  over 9 bins in an empty cell — visibly absurd; useful pedagogically in the report).
- Decay (P5) trades bias (staleness) for variance: with only ~1.5 years of data,
  aggressive decay may lose. It is included because agency performance drifts
  (seasonality, policy changes, backlog purges) and because the incremental-update
  design (§8) wants a decay constant. If P5 ties P4 (within 1 SE), **prefer P5b**
  (h = 180d) for its operational freshness benefits.

---

## 5. Right-censoring

Let `T_pull` be the data-pull timestamp and `M = T_pull − 31 days` the **maturity
cutoff** (31 d = top-bin boundary = 744 h).

**Rule:** train and evaluate **only on requests with `created_date ≤ M`** ("matured"
requests). Among matured requests:
- closed with valid duration → assign to its bin;
- still open at `T_pull` → assign to bin 9 ("month+"). This is **exact, not an
  approximation**: a matured request still open at pull time has already been open
  > 31 days, so its final duration is certainly in (31d, ∞). No imputation, no
  Kaplan–Meier machinery needed — this is the payoff of making the top bin unbounded
  and keying the maturity window to its boundary.

**Residual biases, and why they're acceptable:**
1. *Never-closed / administratively abandoned records* inflate bin 9. They are real
   ("your request effectively won't be resolved within a month" is truthful user-facing
   information), but track the rate: report per type the share of matured requests
   still open at pull; if a type exceeds ~20%, annotate it in the output metadata
   (`high_open_share: true`) rather than "fixing" the data.
2. *Recency loss*: the freshest 31 days of requests are unused. Cost: ~6% of 1.5 years
   of data, uniformly across cells. Acceptable; the decay machinery (P5) governs
   recency emphasis among matured data.
3. *No interval censoring issues*: closed matured requests have fully observed
   durations; open matured requests are point-identified into bin 9. The only
   partially observed case — requests created within the last 31 days — is excluded
   entirely, which is unbiased (exclusion depends only on `created_date`, not on the
   outcome).

---

## 6. Data hygiene rules (NYC 311 specific)

Apply in order; log a row count after each step (the cleaning funnel is part of the
results report).

1. **Deduplicate on `unique_key`** (the Socrata primary key): keep first occurrence.
2. **Double-submission collapse:** among rows with identical
   (`complaint_type`, `descriptor`, `latitude`/`longitude` rounded to 5 decimals) and
   `created_date` within 60 s of each other, keep the earliest. (These are re-taps of
   the submit button / duplicate phone entries. Do **not** dedupe wider than this —
   genuinely repeated complaints about the same condition are real demand and their
   resolutions are real observations.)
3. **Timestamps:** parse as America/New_York naive-local (as published). Drop rows
   with unparseable `created_date`. Rows with `status = Closed` but null
   `closed_date` → drop from duration modeling (unknown duration; typically < 0.5%);
   report the count. Rows with open-like status and null `closed_date` → keep as
   open (censoring logic §5 decides).
4. **Negative durations:** drop rows with `closed_date < created_date` (a known NYC
   311 artifact from agency backfills; typically ~0.1–0.5%).
5. **Zero durations:** drop rows with `closed_date == created_date` exact to the
   second (system artifact / auto-void, not a real 3-hour-bin resolution). Rows with
   `0 < duration < 60 s` are **kept** (some agencies legitimately auto-respond;
   they land in bin 1) but counted and reported per type.
6. **Bulk/batch closures:** detect closure spikes: group closures by
   (`agency`, `closed_date` truncated to the minute); flag minutes containing
   > max(500, 20% of that agency's median daily closures). Requests closed inside
   flagged minutes get `batch_closed = true`. **Default: keep them** (the recorded
   closure is the administrative resolution the requester experiences, and dropping
   them would optimistically bias slow agencies), but run the §7 evaluation once with
   and once without them as a sensitivity check; report if any headline number moves
   by > 0.005 RPS. Known offenders: DSNY and DOT backlog purges, HPD season-end
   heat/hot-water mass closes.
7. **Geography:** map (lat, lon) → 2020 tract GEOID by point-in-polygon. Rows with
   missing/invalid coordinates (null, or the (0,0)/out-of-NYC junk points) but a valid
   `borough` field: **retain for city- and borough-level counts only** (they inform
   the pooling means; node counts are computed from rows, not child sums — §0). Rows
   with neither coordinates nor borough: drop. Report the unmappable share (expect
   2–5%).
8. **Auto-close complaint types:** compute per type median duration and
   `P̂(duration < 1h)`. Types with median < 5 min and `P̂(<1h) > 0.9` (classic
   examples live mostly in "Other": DOF/DHS literature requests, benefit-card
   replacements; among top types, DSNY "Request Large Bulky Item Collection"
   auto-closes on schedule) are **kept and modeled** — their fast closure is their
   true behavior — but flagged `auto_close_type: true` in the export metadata so the
   UI can annotate that "resolved" may mean "acknowledged/scheduled" for them.
9. **Duration cap:** none. Durations of years land in bin 9, which is unbounded;
   no winsorization needed. (Do log the max duration as a sanity check on parsing.)
10. **Type collapsing:** collapse `complaint_type` to the top `T` types by matured
    volume computed **on the training window only** (freeze the list; do not let it
    drift between train and test or between incremental updates until a quarterly
    refit). Everything else → "Other". Normalize known near-duplicate labels first
    (e.g., "Noise - Residential"/"Noise - Street/Sidewalk"/"Noise - Commercial" stay
    distinct; but unify casing/whitespace variants of identical labels).

---

## 7. Evaluation protocol

### 7.1 Temporal split

Let the data span `[D₀, T_pull]`, `T_pull − D₀ ≈ 548 d`, `M = T_pull − 31 d`.

- **Train:** matured requests with `created_date ∈ [D₀, D₀ + 365 d)`.
- **Test:** matured requests with `created_date ∈ [D₀ + 365 d, M)` (~4.5–5 months,
  several hundred thousand to ~1.5M requests).
- For decayed configs, `t_ref = D₀ + 365 d` (no leakage of test-period recency).
- All hyperparameters (κ, type list, hygiene thresholds) are fitted on train only.

**Secondary (realism) evaluation:** rolling monthly update — starting from the
train-only posterior, fold in test months one at a time via §8 and score each month
with the posterior available at its start. Run this **only for the winning config**,
to confirm the incremental-update path performs equivalently to a batch refit
(report both; they should differ only via κ staleness).

### 7.2 Metrics (per test request `i` with cell `c(i)` and observed bin `k(i)`)

Predictions `p̂ = a_{c(i)} / A_{c(i)}` come from the **tract×type** posterior;
requests in the test set whose tract×type cell never existed in training still get a
prediction (the cascade defines one for every cell — for P0/P1 baselines, empty cells
predict the bare prior).

1. **Mean multinomial log-loss (negative log predictive density):**
   `LL = −(1/N) Σ_i log p̂_{k(i)}`. No clipping needed (all p̂ > 0 by construction).
2. **Ranked probability score** (primary; respects bin ordering):
   `RPS_i = (1/(K−1)) Σ_{c=1}^{K−1} ( Σ_{k≤c} p̂_k − 1{k(i) ≤ c} )²`, report the mean.
3. **Calibration of the two headline cumulative claims,** `q_i = P̂(≤ 24h)` and
   `q_i = P̂(≤ 7d)`: sort test requests by `q_i`, split into **20 equal-count bins**,
   plot mean predicted vs. empirical frequency (reliability diagram), and report
   `ECE = Σ_b (N_b/N) · | mean_pred_b − emp_freq_b |`.
4. **Credible-interval coverage** (checks the uncertainty claims, not just the means):
   for every cell with test count ≥ 50, check whether the cell's held-out empirical
   `P̂_emp(≤24h)` falls in the cell's 90% CI. Report empirical coverage; target
   0.90 ± 0.05. (Under-coverage → implement the parent-uncertainty refinement of §1.3.)
5. **Sparse-cell stratification:** every metric above is reported for three strata by
   **training-cell raw count**: `n = 0`, `1 ≤ n < 30`, `n ≥ 30`. The sparse strata are
   where the configurations actually differ; dense cells will be nearly identical
   across P2–P5.

### 7.3 Uncertainty on metric comparisons

Paired **block bootstrap over tract×type cells** (resample cells with replacement,
keep each cell's test requests together; B = 1,000): report each config's metric with
its bootstrap SE, and the SE of each config's *difference from the best* (pairing
removes most of the variance). Cells, not requests, are the exchangeable unit —
request-level bootstrap would wildly understate uncertainty due to within-cell
correlation.

### 7.4 Selection rule (decisive)

1. **Primary criterion:** lowest overall mean **RPS**.
2. **Guardrails** (a config is disqualified if it violates any):
   - sparse-stratum (`n < 30`) mean log-loss worse than the best config's by more
     than 1 bootstrap SE of the paired difference;
   - `ECE(≤24h) > 0.02` or `ECE(≤7d) > 0.02`;
   - 90% CI coverage outside [0.80, 0.97].
3. **Tie-break** (within 1 SE on RPS): prefer, in order, (a) the config with decay
   (operational freshness, §4 note), (b) fewer estimated hyperparameters, (c) lower
   sparse-stratum RPS.

### 7.5 Results table format

One row per configuration:

| config | LL all | LL n=0 | LL n<30 | LL n≥30 | RPS all (±SE) | RPS n<30 | ECE₂₄ₕ | ECE₇d | cov₉₀ | ΔRPS vs best (±SE) |

plus the two reliability diagrams for the winner, the cleaning funnel table (§6), and
the per-(type, level) κ̂ table with MoM cross-checks (§2.2).

---

## 8. Incremental update procedure (posterior today = prior tomorrow)

State to persist per node×type: decayed count vector `ñ` (K floats), raw count `n_raw`
(int, for the UI/diagnostics — never decayed), `last_update_ts`, plus the global
κ table and type list.

**Monthly update recipe** (new pull at `T'`, previous state at `T`, half-life `h`;
`Δ = T' − T` in days):

1. Ingest rows with `created_date ∈ (M_prev, M']` where `M' = T' − 31 d`,
   `M_prev = T − 31 d` — i.e., the newly **matured** cohort. Apply all §6 hygiene with
   the frozen type list.
2. **Re-resolve the previous open tail:** requests created ≤ `M_prev` that were open
   at `T` were finalized as bin 9 — correctly and permanently (§5: they were already
   > 31 d old; later closure cannot move them out of bin 9). **No restatement is ever
   needed.** This is a key design property: bin assignments of matured requests are
   immutable.
3. **Decay-then-add** (exponential forgetting commutes into a single conjugate step):
   ```
   ñ ← ñ · 2^(−Δ/h)  +  Σ_{i ∈ new cohort} 2^(−(T' − created_i)/h) · e_{k(i)}
   n_raw ← n_raw + count(new cohort)
   ```
   With `h = ∞` (no decay) this is plain conjugate addition of the new counts.
4. Re-run the O(cells) cascade of §3 with the **existing κ table**. Re-export JSON.
5. **Quarterly refit:** re-estimate κ (§2) on current decayed counts, refresh the
   top-N type list, and rebuild. Between refits κ is frozen — κ drifts slowly and
   re-estimating it monthly buys nothing while breaking the "pure conjugate update"
   story.

**Honesty note on decay + Bayes:** exponential forgetting is not exact Bayesian
conditioning under a static model; it is the standard **power-prior / exponential-
forgetting filter** — equivalently, exact conjugate updating where the previous
posterior is downweighted to `(2^(−Δ/h))·ñ` pseudo-counts before conditioning on new
data. This is the principled discrete-time analogue of assuming the cell distribution
drifts slowly, and it preserves *posterior-today-is-prior-tomorrow* mechanically:
tomorrow's prior is today's posterior, tempered. State this in the report; do not
oversell it as exact dynamic Bayes.

---

## 9. Fitting-pipeline pseudocode

```python
# ---------- constants ----------
EDGES_H = [3, 24, 48, 72, 168, 336, 480, 744]     # bin upper edges (hours); bin 9 = (744, inf)
K = 9
MATURITY_DAYS = 31
ALPHA0 = 0.5                                       # Jeffreys at the global root
KAPPA0 = 5.0                                       # city ALL -> city type

# ---------- 1. load & clean (section 6) ----------
df = load_311(columns=[unique_key, created_date, closed_date, status,
                       complaint_type, descriptor, agency, lat, lon, borough])
df = df.drop_duplicates("unique_key")
df = collapse_double_submissions(df)               # §6.2: 60s / 5-decimal rule
df = df[df.created_date.notna()]
df = df[~((df.status == "Closed") & df.closed_date.isna())]
df["dur_h"] = (df.closed_date - df.created_date).dt.total_seconds() / 3600
df = df[~(df.dur_h < 0)]                           # negative durations (NaN dur = open, kept)
df = df[~(df.dur_h == 0)]                          # exact-zero artifact
df["batch_closed"] = flag_batch_closures(df)       # §6.6 (flag only)
df["geoid"] = point_in_polygon(df.lat, df.lon, tracts_2020)   # NaN if unmappable
df = df[df.geoid.notna() | df.borough.notna()]
df["nta"], df["boro"] = tract_to_nta(df.geoid), tract_to_borough(df.geoid, df.borough)

# ---------- 2. maturity & binning (section 5) ----------
M = T_PULL - timedelta(days=MATURITY_DAYS)
df = df[df.created_date <= M]                      # matured only
df["bin"] = np.where(df.dur_h.isna(), K - 1,       # open & matured -> bin 9 (index 8)
                     np.searchsorted(EDGES_H, df.dur_h, side="left"))  # dur<=3 -> 0, etc.
top_types = df.groupby("complaint_type").size().nlargest(N_TYPES).index   # freeze on train
df["ctype"] = np.where(df.complaint_type.isin(top_types), df.complaint_type, "Other")

# ---------- 3. decayed count tensors ----------
df["w"] = 0.5 ** ((t_ref - df.created_date).dt.days / HALF_LIFE_DAYS)   # w=1 if no decay
def counts(level_col, type_col_or_ALL):            # rows -> (node x K) decayed & raw counts
    return df.pivot_table(index=[level_col] + type_col_or_ALL, columns="bin",
                          values="w", aggfunc=["sum", "count"], fill_value=0)
# Build for every (level, tree): tract/nta/boro/city x (ctype, and pooled ALL).
# Rows with geoid NaN contribute only to boro/city tables (§6.7).

# ---------- 4. empirical-Bayes kappa (section 2), per (type, level) ----------
def fit_kappa(child_counts, parent_means):         # child_counts: (J,K); parent_means: (J,K)
    keep = child_counts.sum(1) >= 1
    n, m = child_counts[keep], parent_means[keep]
    if (n.sum(1) >= 5).sum() < 8: return None      # -> pooled fallback
    kappa = mom_icc_init(n, m)                     # §2.2
    for _ in range(200):
        num = (m * (digamma(n + kappa*m) - digamma(kappa*m))).sum()
        den = (digamma(n.sum(1) + kappa) - digamma(kappa)).sum()
        new = np.clip(kappa * num / den, 0.5, 5000.0)
        if abs(np.log(new) - np.log(kappa)) < 1e-6: break
        kappa = new
    return kappa
# Estimate in top-down order so parent_means exist: level1 uses city means, etc.
# kappa[level][type], with kappa_pooled[level] as fallback; same for the ALL tree.

# ---------- 5. cascade (section 3) ----------
a = {}                                              # posterior Dirichlet params per node
a["city","ALL"] = ALPHA0 + nt["city","ALL"]
for t in types:
    a["city",t] = KAPPA0 * normalize(a["city","ALL"]) + nt["city",t]
for level, kap in [("boro",k1), ("nta",k2), ("tract",k3)]:  # per-type kappa lookup inside
    for t in types + ["ALL"]:
        a[level,t] = kap[t] * normalize(a[parent_of(level),t])[parent_idx] + nt[level,t]
        # vectorized: parent_idx maps each child row to its parent's mean row

# ---------- 6. summaries & export (section 10) ----------
A  = a_tract.sum(-1, keepdims=True)                 # (n_tract, n_type, 1)
mean = a_tract / A
sd   = np.sqrt(a_tract * (A - a_tract) / (A**2 * (A + 1)))
cum  = mean.cumsum(-1)[..., :-1]                    # 8 cumulative probs
Ac_24, Ac_7d = a_tract[..., :2].sum(-1), a_tract[..., :5].sum(-1)
ci_24 = beta.ppf([0.05, 0.95], Ac_24[..., None], (A[...,0] - Ac_24)[..., None])
ci_7d = beta.ppf([0.05, 0.95], Ac_7d[..., None], (A[...,0] - Ac_7d)[..., None])
lam   = n_dec.sum(-1) / (n_dec.sum(-1) + kappa3_of_type)     # shrinkage weight
write_json_per_cell(...)                            # schema in §10

# ---------- 7. evaluation harness (section 7) ----------
# Re-run steps 2–6 with train-window data only (t_ref = train end), score test rows:
#   LL, RPS, ECE(24h), ECE(7d), coverage, stratified by train n; paired cell bootstrap.
# Loop over configs P0..P5c; emit results table §7.5; apply selection rule §7.4.
```

Memory/CPU envelope: the request-level table (≤7M rows × ~10 cols) is the only large
object (~1–2 GB in pandas with categoricals; chunk the CSV read if needed). Count
tensors are ≤ 2,300 × 26 × 9 floats. κ fitting is a few hundred digamma passes over
arrays of ≤ 2,300 × 9. Everything runs in minutes on a laptop.

---

## 10. Recommended default configuration and export schema

### 10.1 Default (to be confirmed by the §7 comparison)

**P5b**: hierarchical Dirichlet–Multinomial cascade (tract → NTA → borough → city,
per type, city×type rooted in city×ALL with κ₀ = 5, global root Jeffreys ½), with
empirical-Bayes κ per (type, level) via the Minka fixed point (MoM-initialized,
pooled-level fallback), and exponential time decay with **half-life 180 days**
(`t_ref` = latest maturity cutoff). Censoring per §5 (31-day maturity window,
open-and-matured → month+). If P5b fails the §7.4 guardrails against P4, ship **P4**
(same model, no decay) and revisit decay when > 2 years of history exist.

### 10.2 JSON export — one record per tract × type (including type = "ALL")

```json
{
  "geoid": "36061018900",
  "complaint_type": "HEAT/HOT WATER",
  "n_obs": 143,
  "n_eff": 96.4,
  "bin_probs":    [0.04, 0.22, 0.18, 0.11, 0.20, 0.12, 0.05, 0.04, 0.04],
  "bin_probs_sd": [0.008, 0.017, 0.016, 0.013, 0.017, 0.014, 0.009, 0.008, 0.008],
  "cum_probs":    [0.04, 0.26, 0.44, 0.55, 0.75, 0.87, 0.92, 0.96],
  "ci90_le_24h":  [0.221, 0.301],
  "ci90_le_7d":   [0.712, 0.786],
  "shrinkage_weight": 0.86,
  "posterior_total": 112.1,
  "prior_source": "NTA MN0603",
  "flags": {"auto_close_type": false, "high_open_share": false},
  "model_version": "p5b-2026-07",
  "data_through": "2026-06-03",
  "updated_at": "2026-07-04"
}
```

Field definitions:
- `n_obs` — raw matured request count in the cell (undecayed; show this to users).
- `n_eff` — decayed count mass `ñ` (drives the math).
- `bin_probs` — posterior mean `a_k/A` over the 9 bins (sums to 1).
- `bin_probs_sd` — exact Dirichlet posterior SD per bin (§1.3).
- `cum_probs` — `P(≤3h), P(≤24h), P(≤48h), P(≤72h), P(≤7d), P(≤14d), P(≤20d), P(≤31d)`.
- `ci90_le_24h`, `ci90_le_7d` — exact 90% credible intervals from the Beta marginals.
- `shrinkage_weight` — `λ = ñ/(ñ+κ₃)`: 0 = "showing you the neighborhood," 1 = "this
  tract's own data." Recommended UI mapping: λ < 0.3 → "low local data," 0.3–0.7 →
  "blended," > 0.7 → "tract-level evidence."
- `posterior_total` — `A = Σ a_k`, the cell's total effective evidence (prior + data);
  the generic ESS diagnostic.
- `prior_source` — the parent node supplying the prior mean (for UI provenance).
- `flags` — §6.8 auto-close annotation and §5 high-open-share annotation (per type).
