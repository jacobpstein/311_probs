# Interval calibration under the deployed protocol

_Generated 2026-09-19; 11 monthly refits (2025-09..2026-07); sigma re-estimated before every month from four rolling holdouts, exactly as the weekly export does. Cells: tract × type with ≥50 requests in the scored month; interval for P(resolved within 24 h). “Holdout cell threshold” is the minimum requests a holdout cell needs to contribute to sigma._

| holdout cell threshold | cells | coverage (target 0.90) | mean z² (target ≈1) |
|---|---|---|---|
| 20 | 11,865 | 0.874 | 8.80 |
| 50 | 11,865 | 0.874 | 4.55 |

## Coverage by complaint type

| type | cells | coverage @50 | coverage @20 | mean σ @50 | mean σ @20 |
|---|---|---|---|---|---|
| Street Condition | 2 | 0.00 | 0.00 | 0.086 | 0.171 |
| Snow or Ice | 119 | 0.11 | 0.11 | 0.081 | 0.076 |
| Water System | 18 | 0.33 | 0.67 | 0.082 | 0.171 |
| Traffic Signal Condition | 7 | 0.43 | 0.57 | 0.084 | 0.090 |
| PLUMBING | 24 | 0.71 | 0.58 | 0.112 | 0.074 |
| Dirty Condition | 11 | 0.73 | 0.91 | 0.083 | 0.155 |
| Noise | 23 | 0.74 | 0.87 | 0.084 | 0.142 |
| UNSANITARY CONDITION | 35 | 0.77 | 0.83 | 0.015 | 0.018 |
| Noise - Street/Sidewalk | 451 | 0.84 | 0.80 | 0.002 | 0.001 |
| Other | 5,684 | 0.86 | 0.88 | 0.085 | 0.090 |
| Encampment | 164 | 0.87 | 0.90 | 0.068 | 0.072 |
| Noise - Residential | 1,009 | 0.89 | 0.81 | 0.010 | 0.006 |
| HEAT/HOT WATER | 1,895 | 0.90 | 0.92 | 0.115 | 0.126 |
| Illegal Parking | 2,197 | 0.92 | 0.90 | 0.018 | 0.015 |
| Blocked Driveway | 56 | 0.98 | 0.96 | 0.028 | 0.024 |
| Noise - Commercial | 73 | 1.00 | 1.00 | 0.000 | 0.000 |
| Noise - Vehicle | 79 | 1.00 | 0.99 | 0.084 | 0.000 |
| PAINT/PLASTER | 1 | 1.00 | 1.00 | 0.082 | 0.033 |
| Abandoned Vehicle | 17 | 1.00 | 0.94 | 0.085 | 0.068 |

At threshold 50: 9 types below 0.85, 5 above 0.97; mean |coverage − 0.90| = 0.212.

At threshold 20: 8 types below 0.85, 3 above 0.97; mean |coverage − 0.90| = 0.174.
