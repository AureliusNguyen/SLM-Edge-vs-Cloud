# RQ1 results

## Quality by task

Each cell: score (questions, format errors, median seconds per question). Format errors count as 0.

| task | metric | llama | qwen_nothink | qwen_think | cloud |
|---|---|---|---|---|---|
| yesno | accuracy | 0.780 (n=100, 0 fmt err, 4.0s) | 0.780 (n=100, 0 fmt err, 0.5s) | 0.850 (n=100, 0 fmt err, 4.6s) | 0.940 (n=100, 0 fmt err, 0.5s) |
| classify | accuracy | 0.550 (n=100, 0 fmt err, 1.8s) | 0.360 (n=100, 1 fmt err, 0.3s) | 0.780 (n=100, 0 fmt err, 5.7s) | 0.750 (n=100, 0 fmt err, 0.4s) |
| extract | mean F1 | 0.832 (n=100, 0 fmt err, 1.8s) | 0.555 (n=100, 0 fmt err, 0.5s) | 0.444 (n=100, 0 fmt err, 4.2s) | 0.876 (n=100, 0 fmt err, 0.5s) |
| math | accuracy | 0.730 (n=100, 5 fmt err, 18.4s) | 0.220 (n=100, 66 fmt err, 3.5s) | 0.650 (n=100, 29 fmt err, 22.5s) | 0.970 (n=100, 0 fmt err, 0.7s) |

## Confidence signal and cascade

### llama

| task | AUROC | threshold | kept local | local acc. on kept | cascade score | always-local | always-cloud |
|---|---|---|---|---|---|---|---|
| yesno | 0.72 | -0.018 | 52% | 0.923 | 0.920 | 0.780 | 0.940 |
| classify | 0.66 | -0.062 | 40% | 0.700 | 0.730 | 0.550 | 0.750 |
| extract | 0.54 | -0.056 | 30% | 0.869 | 0.862 | 0.832 | 0.876 |
| math | 0.83 | -0.115 | 45% | 0.956 | 0.950 | 0.730 | 0.970 |

### qwen_nothink

| task | AUROC | threshold | kept local | local acc. on kept | cascade score | always-local | always-cloud |
|---|---|---|---|---|---|---|---|
| yesno | 0.55 | -0.015 | 36% | 0.833 | 0.920 | 0.780 | 0.940 |
| classify | 0.70 | always cloud | 0% | - | 0.750 | 0.360 | 0.750 |
| extract | 0.57 | always cloud | 0% | - | 0.876 | 0.555 | 0.876 |
| math | 0.59 | -0.011 | 3% | 0.333 | 0.950 | 0.220 | 0.970 |

### qwen_think

| task | AUROC | threshold | kept local | local acc. on kept | cascade score | always-local | always-cloud |
|---|---|---|---|---|---|---|---|
| yesno | 0.63 | -0.066 | 44% | 0.909 | 0.920 | 0.850 | 0.940 |
| classify | 0.66 | -0.150 | 100% | 0.780 | 0.780 | 0.780 | 0.750 |
| extract | 0.38 | -0.013 | 3% | 0.295 | 0.860 | 0.444 | 0.876 |
| math | 0.58 | -0.036 | 16% | 0.812 | 0.950 | 0.650 | 0.970 |

Threshold rule: the lowest log-prob threshold (keeping the most requests local) whose cascade score stays within 0.02 of always-cloud. AUROC 0.5 means the confidence says nothing about correctness, 1.0 means it separates right from wrong perfectly. For extract, F1 >= 0.5 counts as right.
