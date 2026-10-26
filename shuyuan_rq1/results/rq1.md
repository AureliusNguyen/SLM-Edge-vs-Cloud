# RQ1 results

## Quality by task

Each cell: score (questions, format errors, median seconds per question). Format errors count as 0.

| task | metric | llama | qwen | cloud |
|---|---|---|---|---|
| yesno | accuracy | 0.780 (n=100, 0 fmt err, 4.0s) | 0.767 (n=30, 0 fmt err, 18.2s) | 0.940 (n=100, 0 fmt err, 0.5s) |
| classify | accuracy | 0.550 (n=100, 0 fmt err, 1.8s) | 0.867 (n=30, 0 fmt err, 15.8s) | 0.750 (n=100, 0 fmt err, 0.4s) |
| extract | mean F1 | 0.832 (n=100, 0 fmt err, 1.8s) | 0.505 (n=30, 0 fmt err, 13.2s) | 0.876 (n=100, 0 fmt err, 0.5s) |
| math | accuracy | 0.730 (n=100, 5 fmt err, 18.4s) | 0.600 (n=5, 2 fmt err, 69.6s) | 0.970 (n=100, 0 fmt err, 0.7s) |

## Confidence signal and cascade

### llama

| task | AUROC | threshold | kept local | local acc. on kept | cascade score | always-local | always-cloud |
|---|---|---|---|---|---|---|---|
| yesno | 0.72 | -0.018 | 52% | 0.923 | 0.920 | 0.780 | 0.940 |
| classify | 0.66 | -0.062 | 40% | 0.700 | 0.730 | 0.550 | 0.750 |
| extract | 0.54 | -0.056 | 30% | 0.869 | 0.862 | 0.832 | 0.876 |
| math | 0.83 | -0.115 | 45% | 0.956 | 0.950 | 0.730 | 0.970 |

### qwen

| task | AUROC | threshold | kept local | local acc. on kept | cascade score | always-local | always-cloud |
|---|---|---|---|---|---|---|---|
| yesno | 0.81 | -0.048 | 20% | 1.000 | 0.967 | 0.767 | 0.967 |
| classify | 0.55 | -0.157 | 100% | 0.867 | 0.867 | 0.867 | 0.833 |
| extract | 0.37 | -0.002 | 3% | 0.800 | 0.888 | 0.505 | 0.895 |
| math | 0.00 | always cloud | 0% | - | 1.000 | 0.600 | 1.000 |

Threshold rule: the lowest log-prob threshold (keeping the most requests local) whose cascade score stays within 0.02 of always-cloud. AUROC 0.5 means the confidence says nothing about correctness, 1.0 means it separates right from wrong perfectly. For extract, F1 >= 0.5 counts as right.
