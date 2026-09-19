# Simulation check of the cascade

_8 replicates per scenario; real geography (2325 tracts) and real per-tract volumes for one complaint type. KL = mean KL(truth ‖ estimate) over tracts (lower is better); coverage = share of tracts whose true P(resolved ≤24h) lies inside the nominal 90% interval._


## high heterogeneity: true κ (borough, NTA, tract) = (150, 40, 100)

| method | κ̂ NTA | κ̂ tract | KL | KL, <30 requests | 90% coverage, tract only | + parent uncertainty | + parent, <30 requests |
|---|---|---|---|---|---|---|---|
| cascade | 38 | 145 | 0.03381 | 0.04425 | 0.807 | 0.854 | 0.844 |
| cascade, true kappa | given | given | 0.03338 | 0.04382 | 0.868 | 0.896 | 0.893 |
| sibling-only | 36 | 76 | 0.03371 | 0.04427 | 0.901 | 0.921 | 0.926 |
| sibling-only, true kappa | given | given | 0.03405 | 0.04461 | 0.865 | 0.896 | 0.894 |

## moderate: true κ (borough, NTA, tract) = (150, 100, 300)

| method | κ̂ NTA | κ̂ tract | KL | KL, <30 requests | 90% coverage, tract only | + parent uncertainty | + parent, <30 requests |
|---|---|---|---|---|---|---|---|
| cascade | 97 | 705 | 0.01807 | 0.02142 | 0.625 | 0.797 | 0.803 |
| cascade, true kappa | given | given | 0.01768 | 0.02120 | 0.814 | 0.889 | 0.889 |
| sibling-only | 92 | 186 | 0.01784 | 0.02136 | 0.893 | 0.933 | 0.935 |
| sibling-only, true kappa | given | given | 0.01820 | 0.02159 | 0.807 | 0.889 | 0.891 |

## low heterogeneity: true κ (borough, NTA, tract) = (150, 300, 1500)

| method | κ̂ NTA | κ̂ tract | KL | KL, <30 requests | 90% coverage, tract only | + parent uncertainty | + parent, <30 requests |
|---|---|---|---|---|---|---|---|
| cascade | 301 | 5000 | 0.00736 | 0.00834 | 0.428 | 0.841 | 0.851 |
| cascade, true kappa | given | given | 0.00732 | 0.00832 | 0.686 | 0.896 | 0.904 |
| sibling-only | 278 | 533 | 0.00736 | 0.00836 | 0.889 | 0.961 | 0.964 |
| sibling-only, true kappa | given | given | 0.00759 | 0.00846 | 0.676 | 0.896 | 0.907 |
