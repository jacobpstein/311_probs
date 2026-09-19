# Full-Bayes check of the cascade (Stan)

_Brooklyn, last 365 days to 2026-08-18, no decay; CmdStan 2.40. Priors: log κ ~ Normal(5, 2) for both levels (κ median ≈ 150, 95% range ≈ 3–8,000). Four chains × 1,000 draws, adapt_delta 0.9._


## 1. Recovery on simulated data (checks the program, not the data)

Data simulated from the program's own generative process with true κ = (120, 350) for the real Brooklyn geography and request volumes (96,430 requests).

| parameter | truth | posterior median | 90% interval | truth in 99% interval | R̂ | ESS |
|---|---|---|---|---|---|---|
| κ neighborhood | 120 | 119 | 80–169 | yes | 1.000 | 3114 |
| κ tract | 350 | 319 | 238–444 | yes | 1.000 | 4000 |

Tract-level P(≤24h): 88.7% of 804 tracts have their true value inside the 90% posterior interval (target 90%). Divergences 0, treedepth-10 hits 0, min E-BFMI 0.88.


## HEAT/HOT WATER

- **Sampler:** divergences 0, treedepth-10 hits 0, min E-BFMI 0.64; κ R̂ 1.005/1.000, ESS 819/4000 (neighborhood/tract).
- **Pooling strengths:** Stan κ neighborhood 214 (90% 127–395), κ tract 50 (90% 43–59); matching plug-in cascade estimates 150 and 52.
- **Tract posterior means, Stan vs plug-in cascade on the same counts** (804 tracts): mean |difference| 0.0067, 99th percentile 0.0457, max 0.0564 (on the 0–1 probability scale).
  (production 9-bin cascade vs Stan: mean |difference| 0.0155, max 0.0726.)
- **Uncertainty (SD of P(≤24h)), Stan ÷ plug-in cascade** — median ratio; sparse tracts (<30 requests) / dense (≥100):
  Dirichlet-only cascade SD: 1.05 / 1.01; cascade SD with the parent-uncertainty term: 1.03 / 1.01.

## Street Condition

- **Sampler:** divergences 0, treedepth-10 hits 0, min E-BFMI 0.44; κ R̂ 1.008/1.000, ESS 350/4000 (neighborhood/tract).
- **Pooling strengths:** Stan κ neighborhood 150 (90% 85–313), κ tract 29 (90% 24–35); matching plug-in cascade estimates 92 and 34.
- **Tract posterior means, Stan vs plug-in cascade on the same counts** (804 tracts): mean |difference| 0.0077, 99th percentile 0.0346, max 0.0634 (on the 0–1 probability scale).
  (production 9-bin cascade vs Stan: mean |difference| 0.0265, max 0.1433.)
- **Uncertainty (SD of P(≤24h)), Stan ÷ plug-in cascade** — median ratio; sparse tracts (<30 requests) / dense (≥100):
  Dirichlet-only cascade SD: 1.09 / 1.03; cascade SD with the parent-uncertainty term: 1.06 / 1.03.

## Water System

- **Sampler:** divergences 0, treedepth-10 hits 0, min E-BFMI 0.63; κ R̂ 1.005/1.000, ESS 1142/4000 (neighborhood/tract).
- **Pooling strengths:** Stan κ neighborhood 85 (90% 51–147), κ tract 25 (90% 20–30); matching plug-in cascade estimates 55 and 30.
- **Tract posterior means, Stan vs plug-in cascade on the same counts** (804 tracts): mean |difference| 0.0112, 99th percentile 0.0444, max 0.0605 (on the 0–1 probability scale).
  (production 9-bin cascade vs Stan: mean |difference| 0.0321, max 0.1282.)
- **Uncertainty (SD of P(≤24h)), Stan ÷ plug-in cascade** — median ratio; sparse tracts (<30 requests) / dense (≥100):
  Dirichlet-only cascade SD: 1.11 / 1.04; cascade SD with the parent-uncertainty term: 1.07 / 1.03.
