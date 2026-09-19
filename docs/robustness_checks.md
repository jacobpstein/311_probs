# Follow-up robustness checks

_Generated 2026-09-19 on data 2024-08-19..2026-08-18; shipped model P7a (cutwise, 90-day decay)._

## A. Interval calibration by complaint type (24-hour threshold)

_Shipped model on the evaluate.py split (train first 12 months, test the next 12). z² is the mean squared standardized residual (target 1; tract × type cells with ≥10 test requests); coverage is the share of cells with ≥50 test requests whose observed rate falls in the 90% interval (target 0.90)._

| type | σ (24h) | sparse z² | sparse cells | dense z² | dense coverage | dense cells |
|---|---|---|---|---|---|---|
| Noise - Commercial ◂ | 0.003 | 0.97 | 432 | 0.59 | 0.93 | 500 |
| Noise - Street/Sidewalk ◂ | 0.006 | 1.82 | 669 | 1.78 | 0.86 | 1086 |
| UNSANITARY CONDITION ◂ | 0.018 | 1.38 | 715 | 0.55 | 0.96 | 909 |
| Noise - Residential ◂ | 0.020 | 0.41 | 353 | 0.62 | 0.91 | 1816 |
| Illegal Parking ◂ | 0.026 | 0.19 | 116 | 0.67 | 0.92 | 2164 |
| Blocked Driveway ◂ | 0.041 | 0.11 | 458 | 0.40 | 0.92 | 1546 |
| Encampment | 0.063 | 0.73 | 321 | 0.61 | 0.95 | 224 |
| Street Condition | 0.087 | 1.72 | 1365 | 1.64 | 0.69 | 535 |
| PLUMBING | 0.087 | 0.48 | 763 | 0.45 | 0.96 | 591 |
| Abandoned Vehicle | 0.087 | 0.17 | 917 | 0.47 | 0.88 | 675 |
| Water System | 0.087 | 1.29 | 1121 | 1.11 | 0.84 | 706 |
| Dirty Condition | 0.087 | 1.46 | 1106 | 1.61 | 0.67 | 653 |
| Noise | 0.087 | 0.99 | 911 | 0.83 | 0.91 | 496 |
| PAINT/PLASTER | 0.087 | 0.28 | 662 | 0.10 | 1.00 | 489 |
| Snow or Ice | 0.087 | 2.41 | 1745 | nan | nan | 7 |
| Traffic Signal Condition | 0.087 | 0.98 | 1003 | 0.67 | 0.97 | 413 |
| DOOR/WINDOW | 0.087 | 0.16 | 666 | 0.04 | 1.00 | 426 |
| Noise - Vehicle | 0.087 | 0.04 | 672 | 0.03 | 1.00 | 323 |
| WATER LEAK | 0.087 | 0.16 | 646 | 0.05 | 1.00 | 387 |
| Other | 0.089 | 0.77 | 23 | 0.59 | 0.96 | 2285 |
| HEAT/HOT WATER | 0.098 | 0.90 | 514 | 0.63 | 0.97 | 1332 |

◂ = the six types flagged as having almost no regime variance.

## B. Do correlated outcomes within cells explain the dense-cell shortfall?

### B1. Day-to-day clustering of outcomes inside a tract × type cell

_Pearson dispersion of the daily counts of “resolved within 24 hours” within tract × type cells (cells with ≥50 requests in the last 365 days, ≥10 active days, rate between 2% and 98%). 1.0 means requests behave like independent draws; above 1 means outcomes cluster by day (for a cell averaging m requests a day, the variance of its yearly rate is inflated by roughly this factor)._

Pooled over cells: all requests **1.29** (6,787 cells); batch closures removed **1.29** (6,745 cells).

| type | dispersion, all | dispersion, batch removed |
|---|---|---|
| Snow or Ice | 3.25 | 3.25 |
| Noise - Street/Sidewalk | 1.74 | 1.74 |
| HEAT/HOT WATER | 1.55 | 1.55 |
| Noise - Commercial | 1.42 | 1.42 |
| Noise - Residential | 1.39 | 1.39 |
| Traffic Signal Condition | 1.37 | 1.37 |
| Illegal Parking | 1.35 | 1.35 |
| Water System | 1.28 | 1.28 |
| Abandoned Vehicle | 1.27 | 1.27 |
| Blocked Driveway | 1.25 | 1.25 |
| PAINT/PLASTER | 1.25 | 1.25 |
| UNSANITARY CONDITION | 1.24 | 1.25 |
| Other | 1.23 | 1.22 |
| DOOR/WINDOW | 1.22 | 1.18 |
| Dirty Condition | 1.18 | 1.18 |
| PLUMBING | 1.18 | 1.20 |
| Noise | 1.18 | 1.18 |
| Street Condition | 1.14 | 1.14 |
| WATER LEAK | 1.09 | 1.09 |
| Noise - Vehicle | 1.05 | 1.05 |
| Encampment | 0.72 | 0.72 |

### B2. Even/odd-day split: coverage of the 90% interval (cells with ≥50 requests on the held-out half)

_Train on even days, score odd days; both halves span the same dates, so drift cannot explain a shortfall. No decay, no regime term: this isolates the sampling intervals. “Latent” compares the held-out rate with the interval for the true rate (the earlier convention); “predictive” also adds the held-out half's binomial noise. “Inflated” multiplies the sampling variance by the dispersion measured on the training half only._

| data | interval | coverage (latent) | coverage (predictive) | coverage (inflated, predictive) | cells |
|---|---|---|---|---|---|
| all requests | sampling only | 0.690 | 0.888 | 0.903 | 8,773 |
| batch closures removed | sampling only | 0.694 | 0.889 | 0.902 | 8,628 |

## C. Batch-closure sensitivity

_Rolling-origin (11 monthly refits). “Excluded” models are trained without batch-closed requests. Δ = excluded − full (negative = excluding batch closures predicts better); ± bootstrap SE over tract × type cells._

| scored on | metric | full-trained | excluded-trained | Δ | ±SE |
|---|---|---|---|---|---|
| requests not flagged as batch closures | RPS | 0.09929 | 0.09924 | -0.00005 | 0.00001 |
| requests not flagged as batch closures | log-loss | 1.30071 | 1.30034 | -0.00037 | 0.00006 |
| all requests | RPS | 0.10148 | 0.10171 | +0.00023 | 0.00001 |
| all requests | log-loss | 1.31747 | 1.31884 | +0.00137 | 0.00007 |

### Where batch-closed requests concentrate

Share flagged by borough: Bronx 2.10%, Manhattan 1.91%, Brooklyn 1.55%, Queens 1.16%, Staten Island 0.93%; overall 1.61%.

| type | share flagged | requests flagged |
|---|---|---|
| WATER LEAK | 9.87% | 8,173 |
| DOOR/WINDOW | 9.41% | 8,589 |
| PLUMBING | 8.98% | 12,580 |
| UNSANITARY CONDITION | 7.24% | 15,613 |
| PAINT/PLASTER | 7.00% | 7,772 |
| Other | 2.89% | 59,935 |
| Water System | 1.25% | 1,525 |
| HEAT/HOT WATER | 0.01% | 50 |

Agencies with the most flagged requests: HPD (77,063, 5.0%), DOB (35,097, 18.4%), DEP (1,529, 0.4%), DSNY (551, 0.1%), DCWP (0, 0.0%).

### Change in displayed P(resolved within 24 hours) when batch closures are excluded from the fit

| type | city, full | city, excluded | largest borough change (points) | borough ranking preserved |
|---|---|---|---|---|
| Illegal Parking | 0.994 | 0.994 | 0.0 | yes |
| Noise - Residential | 0.995 | 0.995 | 0.0 | yes |
| HEAT/HOT WATER | 0.256 | 0.256 | 0.0 | yes |
| Blocked Driveway | 0.994 | 0.994 | 0.0 | yes |
| Noise - Street/Sidewalk | 0.995 | 0.995 | 0.0 | yes |
| UNSANITARY CONDITION | 0.014 | 0.015 | 0.2 | yes |
| Street Condition | 0.309 | 0.309 | 0.0 | yes |
| PLUMBING | 0.055 | 0.062 | 0.9 | yes |
| Abandoned Vehicle | 0.986 | 0.986 | 0.0 | yes |
| Water System | 0.617 | 0.624 | 2.1 | yes |
| Dirty Condition | 0.388 | 0.388 | 0.0 | yes |
| Noise - Commercial | 0.998 | 0.998 | 0.0 | yes |
| Noise | 0.230 | 0.230 | 0.0 | yes |
| PAINT/PLASTER | 0.030 | 0.032 | 0.5 | yes |
| Snow or Ice | 0.362 | 0.362 | 0.0 | yes |
| Traffic Signal Condition | 0.813 | 0.813 | 0.0 | yes |
| DOOR/WINDOW | 0.013 | 0.015 | 0.3 | no |
| Encampment | 0.824 | 0.824 | 0.0 | yes |
| Noise - Vehicle | 0.997 | 0.997 | 0.0 | yes |
| WATER LEAK | 0.018 | 0.020 | 0.4 | no |
| Other | 0.306 | 0.315 | 1.3 | yes |
| ALL | 0.586 | 0.599 | 1.6 | yes |

All-complaints tract map: mean absolute change 1.06 points, 99th percentile 3.1, max 12.7; rank correlation of tracts 0.9975.

