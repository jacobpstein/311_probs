# Cutwise vs nine-bin pooling

_Generated 2026-09-19 on data 2024-08-19..2026-08-18; 11 monthly refits (2025-09..2026-07). Each row scores the binary event "resolved within the threshold" on the same held-out requests. Δ = cutwise − nine-bin (negative = cutwise better); ± is the bootstrap SE over tract × type cells._


| threshold | nine-bin log-loss | Δ log-loss | ±SE | nine-bin Brier | Δ Brier | ±SE |
|---|---|---|---|---|---|---|
| 3 hours | 0.37395 | -0.00119 | 0.00011 | 0.11911 | -0.00045 | 0.00004 |
| 24 hours | 0.31273 | -0.00076 | 0.00008 | 0.10265 | -0.00026 | 0.00003 |
| 2 days | 0.35350 | -0.00059 | 0.00008 | 0.12192 | -0.00019 | 0.00003 |
| 3 days | 0.35299 | -0.00022 | 0.00007 | 0.12025 | -0.00013 | 0.00002 |
| 1 week | 0.31465 | -0.00098 | 0.00006 | 0.10476 | -0.00007 | 0.00002 |
| 2 weeks | 0.27533 | -0.00041 | 0.00005 | 0.09086 | -0.00013 | 0.00002 |
| 3 weeks | 0.25674 | -0.00038 | 0.00005 | 0.08275 | -0.00013 | 0.00002 |
| 1 month | 0.22906 | -0.00036 | 0.00005 | 0.07102 | -0.00012 | 0.00001 |

## Scored from each tract's all-complaints distribution (what the default map shows)

| threshold | nine-bin log-loss | Δ log-loss | ±SE | Δ Brier | ±SE |
|---|---|---|---|---|---|
| 3 hours | 0.62671 | -0.00039 | 0.00017 | -0.00018 | 0.00007 |
| 24 hours | 0.64492 | -0.00038 | 0.00017 | -0.00018 | 0.00007 |
| 2 days | 0.61321 | -0.00021 | 0.00012 | -0.00010 | 0.00005 |
| 3 days | 0.57330 | -0.00011 | 0.00010 | -0.00005 | 0.00004 |
| 1 week | 0.47183 | -0.00002 | 0.00006 | -0.00001 | 0.00002 |
| 2 weeks | 0.38843 | +0.00001 | 0.00004 | +0.00000 | 0.00001 |
| 3 weeks | 0.34736 | +0.00002 | 0.00003 | +0.00000 | 0.00001 |
| 1 month | 0.29872 | +0.00002 | 0.00002 | +0.00000 | 0.00001 |

## By complaint type, 24 hours threshold (log-loss)

| type | requests | nine-bin | Δ cutwise | ±SE |
|---|---|---|---|---|
| Noise | 54,444 | 0.5228 | -0.00383 | 0.00102 |
| Other | 953,390 | 0.5786 | -0.00140 | 0.00023 |
| Noise - Street/Sidewalk | 149,231 | 0.0238 | -0.00127 | 0.00033 |
| Encampment | 43,381 | 0.4686 | -0.00111 | 0.00021 |
| Dirty Condition | 60,904 | 0.6704 | -0.00107 | 0.00037 |
| HEAT/HOT WATER | 346,064 | 0.5626 | -0.00097 | 0.00022 |
| Street Condition | 92,497 | 0.6232 | -0.00088 | 0.00035 |
| Water System | 57,627 | 0.6502 | -0.00070 | 0.00052 |
| Noise - Residential | 360,687 | 0.0221 | -0.00066 | 0.00011 |
| Noise - Vehicle | 44,415 | 0.0149 | -0.00034 | 0.00030 |
| Blocked Driveway | 178,752 | 0.0279 | -0.00026 | 0.00004 |
| Illegal Parking | 559,594 | 0.0243 | -0.00024 | 0.00005 |
| Abandoned Vehicle | 63,569 | 0.0615 | -0.00022 | 0.00008 |
| Noise - Commercial | 55,309 | 0.0099 | -0.00021 | 0.00025 |
| Traffic Signal Condition | 46,214 | 0.4996 | -0.00008 | 0.00015 |
| DOOR/WINDOW | 45,142 | 0.0820 | +0.00002 | 0.00003 |
| WATER LEAK | 40,897 | 0.1053 | +0.00004 | 0.00003 |
| PAINT/PLASTER | 53,366 | 0.1511 | +0.00007 | 0.00004 |
| UNSANITARY CONDITION | 103,343 | 0.0848 | +0.00009 | 0.00008 |
| PLUMBING | 71,297 | 0.2280 | +0.00072 | 0.00046 |
| Snow or Ice | 63,863 | 0.7305 | +0.00107 | 0.00028 |

## By complaint type, 1 week threshold (log-loss)

| type | requests | nine-bin | Δ cutwise | ±SE |
|---|---|---|---|---|
| Snow or Ice | 63,863 | 0.7047 | -0.02751 | 0.00213 |
| Dirty Condition | 60,904 | 0.1912 | -0.00439 | 0.00097 |
| Noise - Street/Sidewalk | 149,231 | 0.0095 | -0.00132 | 0.00032 |
| WATER LEAK | 40,897 | 0.6454 | -0.00095 | 0.00026 |
| Noise | 54,444 | 0.5081 | -0.00092 | 0.00044 |
| PAINT/PLASTER | 53,366 | 0.6852 | -0.00084 | 0.00025 |
| Abandoned Vehicle | 63,569 | 0.0066 | -0.00079 | 0.00023 |
| PLUMBING | 71,297 | 0.6859 | -0.00071 | 0.00045 |
| Blocked Driveway | 178,752 | 0.0042 | -0.00059 | 0.00010 |
| Noise - Residential | 360,687 | 0.0037 | -0.00052 | 0.00011 |
| HEAT/HOT WATER | 346,064 | 0.1587 | -0.00051 | 0.00010 |
| UNSANITARY CONDITION | 103,343 | 0.6362 | -0.00050 | 0.00043 |
| DOOR/WINDOW | 45,142 | 0.6218 | -0.00031 | 0.00014 |
| Other | 953,390 | 0.6539 | -0.00030 | 0.00011 |
| Illegal Parking | 559,594 | 0.0029 | -0.00026 | 0.00004 |
| Water System | 57,627 | 0.4514 | -0.00023 | 0.00017 |
| Noise - Vehicle | 44,415 | 0.0053 | -0.00020 | 0.00008 |
| Encampment | 43,381 | 0.3641 | -0.00008 | 0.00019 |
| Noise - Commercial | 55,309 | 0.0022 | -0.00007 | 0.00005 |
| Traffic Signal Condition | 46,214 | 0.2324 | +0.00011 | 0.00005 |
| Street Condition | 92,497 | 0.6143 | +0.00086 | 0.00028 |

## Tract-level κ in the last refit: nine-bin vs cutwise

| threshold | type | nine-bin κ | cutwise κ |
|---|---|---|---|
| 24 hours | HEAT/HOT WATER | 819 | 128 |
| 24 hours | Street Condition | 5000 | 1144 |
| 24 hours | Water System | 5000 | 183 |
| 24 hours | Illegal Parking | 376 | 5000 |
| 24 hours | ALL | 149 | 28 |
| 1 week | HEAT/HOT WATER | 819 | 682 |
| 1 week | Street Condition | 5000 | 5000 |
| 1 week | Water System | 5000 | 5000 |
| 1 week | Illegal Parking | 376 | 5000 |
| 1 week | ALL | 149 | 60 |
