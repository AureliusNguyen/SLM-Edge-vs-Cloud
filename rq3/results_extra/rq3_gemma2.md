# RQ3 results: routing policies (gemma2)

Offline replay of the RQ1 answers (100 questions per task, 400 total, equal mix) with the RQ2 per-request costs. Thresholds come from 2-fold cross-validation repeated 50 times; numbers are means over the held-out halves. Extract counts as correct when the gpt-oss-20b judge says CORRECT. Latency is the median per-request time from RQ2 (busy device), so a cascade that escalates pays local + cloud time and energy.

Assumptions: edge grid 420 g/kWh, data-center grid 350 g/kWh, cloud energy 0.24 Wh/request (low) or 83.1 Wh per 1k output tokens (upper), Groq price $0.15/$0.6 per 1M input/output tokens, cascade tolerance 0.02.

## Headline: GPU laptop, Wi-Fi, low cloud-energy estimate

| policy | accuracy (±sd) | kept local | cloud calls/req | latency s | total Wh/req | gCO2e/req | $ per 1k req | Wh per correct | tCDP g·s |
|---|---|---|---|---|---|---|---|---|---|
| always-local | 0.760 (±0.020) | 100% | 0.00 | 0.379 | 0.0113 | 0.00473 | 0.000 | 0.0148 | 0.00179 |
| always-cloud | 0.915 (±0.012) | 0% | 1.00 | 0.5 | 0.241 | 0.0846 | 0.117 | 0.264 | 0.0423 |
| task-rule | 0.875 (±0.015) | 50% | 0.50 | 0.358 | 0.122 | 0.0427 | 0.070 | 0.139 | 0.0153 |
| fit-rule | 0.890 (±0.016) | 50% | 0.50 | 0.356 | 0.122 | 0.0429 | 0.075 | 0.137 | 0.0153 |
| cascade | 0.885 (±0.020) | 56% | 0.44 | 0.642 | 0.118 | 0.042 | 0.067 | 0.133 | 0.0271 |
| rule+cascade | 0.899 (±0.015) | 30% | 0.70 | 0.441 | 0.17 | 0.0596 | 0.088 | 0.189 | 0.0264 |
| oracle | 0.927 (±0.012) | 76% | 0.24 | 0.377 | 0.0648 | 0.0232 | 0.033 | 0.0699 | 0.00874 |

Per-task accuracy:

| policy | yesno | classify | extract | math |
|---|---|---|---|---|
| always-local | 0.810 | 0.690 | 0.970 | 0.570 |
| always-cloud | 0.940 | 0.750 | 1.000 | 0.970 |
| task-rule | 0.810 | 0.750 | 0.970 | 0.970 |
| fit-rule | 0.927 | 0.692 | 0.970 | 0.970 |
| cascade | 0.895 | 0.724 | 0.980 | 0.941 |
| rule+cascade | 0.895 | 0.750 | 0.980 | 0.970 |
| oracle | 0.970 | 0.770 | 1.000 | 0.970 |

fit-rule keeps local the 2 tasks with the smallest SLM-vs-cloud accuracy gap on the training half (same 50% local share as task-rule). Fit on all questions: **classify + extract** local. Chosen across the CV folds: classify+extract 93%, yesno+extract 7%.

Cascade thresholds (mean token log-prob) fit on all 100 questions, for the gateway; 'cloud' means no threshold met the tolerance, so the task always goes to the cloud. 'never local' is how often that happened across the cross-validation folds.

| task | threshold | never local in CV |
|---|---|---|
| yesno | -0.0119 | 0% |
| classify | -0.1343 | 0% |
| extract | -0.2130 | 0% |
| math | -0.0311 | 0% |

## All scenarios

accuracy / gCO2e per request / latency s, per policy. Accuracy does not depend on the scenario (same answers), only the cost does.

| profile | network | cloud energy | always-local | always-cloud | task-rule | fit-rule | cascade | rule+cascade | oracle |
|---|---|---|---|---|---|---|---|---|---|
| gpu | wifi | low | 0.76 / 0.0047 / 0.38 | 0.92 / 0.085 / 0.5 | 0.88 / 0.043 / 0.36 | 0.89 / 0.043 / 0.36 | 0.88 / 0.042 / 0.64 | 0.90 / 0.06 / 0.44 | 0.93 / 0.023 / 0.38 |
| gpu | wifi | upper | 0.76 / 0.0047 / 0.38 | 0.92 / 4.3 / 0.5 | 0.88 / 2.8 / 0.36 | 0.89 / 3 / 0.36 | 0.88 / 2.6 / 0.64 | 0.90 / 3.4 / 0.44 | 0.93 / 1.3 / 0.38 |
| gpu | hotspot | low | 0.76 / 0.0047 / 0.38 | 0.92 / 0.084 / 0.75 | 0.88 / 0.043 / 0.47 | 0.89 / 0.043 / 0.48 | 0.88 / 0.042 / 0.75 | 0.90 / 0.059 / 0.61 | 0.93 / 0.023 / 0.43 |
| gpu | hotspot | upper | 0.76 / 0.0047 / 0.38 | 0.92 / 4.5 / 0.75 | 0.88 / 3 / 0.47 | 0.89 / 3.2 / 0.48 | 0.88 / 2.8 / 0.75 | 0.90 / 3.6 / 0.61 | 0.93 / 1.4 / 0.43 |
| cpu | wifi | low | 0.76 / 0.011 / 1.8 | 0.92 / 0.085 / 0.5 | 0.88 / 0.046 / 0.85 | 0.89 / 0.045 / 0.78 | 0.88 / 0.048 / 2 | 0.90 / 0.063 / 0.94 | 0.93 / 0.028 / 1.3 |
| cpu | wifi | upper | 0.76 / 0.011 / 1.8 | 0.92 / 4.3 / 0.5 | 0.88 / 2.8 / 0.85 | 0.89 / 3 / 0.78 | 0.88 / 2.7 / 2 | 0.90 / 3.4 / 0.94 | 0.93 / 1.3 / 1.3 |
| cpu | hotspot | low | 0.76 / 0.011 / 1.8 | 0.92 / 0.084 / 0.75 | 0.88 / 0.045 / 0.97 | 0.89 / 0.045 / 0.91 | 0.88 / 0.048 / 2.1 | 0.90 / 0.062 / 1.1 | 0.93 / 0.028 / 1.4 |
| cpu | hotspot | upper | 0.76 / 0.011 / 1.8 | 0.92 / 4.5 / 0.75 | 0.88 / 3 / 0.97 | 0.89 / 3.2 / 0.91 | 0.88 / 2.8 / 2.1 | 0.90 / 3.6 / 1.1 | 0.93 / 1.4 / 1.4 |
| docker-full | wifi | low | 0.76 / 0.004 / 2.3 | 0.92 / 0.085 / 0.5 | 0.88 / 0.044 / 1 | 0.89 / 0.043 / 0.94 | 0.88 / 0.041 / 2.6 | 0.90 / 0.061 / 1.1 | 0.93 / 0.023 / 1.7 |
| docker-full | wifi | upper | 0.76 / 0.004 / 2.3 | 0.92 / 4.3 / 0.5 | 0.88 / 2.8 / 1 | 0.89 / 3 / 0.94 | 0.88 / 2.6 / 2.6 | 0.90 / 3.4 / 1.1 | 0.93 / 1.3 / 1.7 |
| docker-full | hotspot | low | 0.76 / 0.004 / 2.3 | 0.92 / 0.084 / 0.75 | 0.88 / 0.044 / 1.1 | 0.89 / 0.043 / 1.1 | 0.88 / 0.041 / 2.7 | 0.90 / 0.06 / 1.3 | 0.93 / 0.023 / 1.8 |
| docker-full | hotspot | upper | 0.76 / 0.004 / 2.3 | 0.92 / 4.5 / 0.75 | 0.88 / 3 / 1.1 | 0.89 / 3.2 / 1.1 | 0.88 / 2.8 / 2.7 | 0.90 / 3.6 / 1.3 | 0.93 / 1.4 / 1.8 |
| docker-2cpu | wifi | low | 0.76 / 0.0094 / 4.7 | 0.92 / 0.085 / 0.5 | 0.88 / 0.044 / 2.1 | 0.89 / 0.044 / 1.8 | 0.88 / 0.047 / 5 | 0.90 / 0.061 / 2.2 | 0.93 / 0.026 / 3.5 |
| docker-2cpu | wifi | upper | 0.76 / 0.0094 / 4.7 | 0.92 / 4.3 / 0.5 | 0.88 / 2.8 / 2.1 | 0.89 / 3 / 1.8 | 0.88 / 2.6 / 5 | 0.90 / 3.4 / 2.2 | 0.93 / 1.3 / 3.5 |
| docker-2cpu | hotspot | low | 0.76 / 0.0094 / 4.7 | 0.92 / 0.084 / 0.75 | 0.88 / 0.044 / 2.2 | 0.89 / 0.044 / 1.9 | 0.88 / 0.046 / 5.1 | 0.90 / 0.061 / 2.3 | 0.93 / 0.026 / 3.5 |
| docker-2cpu | hotspot | upper | 0.76 / 0.0094 / 4.7 | 0.92 / 4.5 / 0.75 | 0.88 / 3 / 2.2 | 0.89 / 3.2 / 1.9 | 0.88 / 2.8 / 5.1 | 0.90 / 3.6 / 2.3 | 0.93 / 1.4 / 3.5 |

## Low battery (20% of requests forced to the cloud)

Expected value: (1 - share) x policy + share x always-cloud, GPU / Wi-Fi / low estimate.

| policy | accuracy | kept local | latency s | gCO2e/req | $ per 1k req |
|---|---|---|---|---|---|
| always-local | 0.791 | 80% | 0.403 | 0.0207 | 0.023 |
| always-cloud | 0.915 | 0% | 0.5 | 0.0846 | 0.117 |
| task-rule | 0.883 | 40% | 0.387 | 0.0511 | 0.079 |
| fit-rule | 0.895 | 40% | 0.385 | 0.0513 | 0.084 |
| cascade | 0.891 | 45% | 0.614 | 0.0505 | 0.077 |
| rule+cascade | 0.902 | 24% | 0.453 | 0.0646 | 0.094 |
| oracle | 0.925 | 61% | 0.401 | 0.0355 | 0.050 |

## Edge-grid sensitivity (GPU / Wi-Fi / low estimate)

gCO2e per request when the device sits on a different grid. 420 = eGRID MROW (ours), 364 = Minnesota state average and 163 = a solar-rich western state (both from Kopczyk & Chandra).

| policy | 163 | 364 | 420 |
|---|---|---|---|
| always-local | 0.00184 | 0.0041 | 0.00473 |
| always-cloud | 0.0842 | 0.0845 | 0.0846 |
| task-rule | 0.0423 | 0.0426 | 0.0427 |
| fit-rule | 0.0424 | 0.0428 | 0.0429 |
| cascade | 0.0414 | 0.0439 | 0.0445 |
| rule+cascade | 0.0606 | 0.0611 | 0.0612 |
| oracle | 0.0213 | 0.0228 | 0.0232 |

## Network delay sensitivity (GPU / Wi-Fi / low estimate)

Mean latency per request (s) when every cloud call takes this much longer. Accuracy and carbon do not change. Cascade thresholds fit on all questions.

| policy | +0 s | +0.1 s | +0.3 s | +1 s |
|---|---|---|---|---|
| always-local | 0.379 | 0.379 | 0.379 | 0.379 |
| always-cloud | 0.5 | 0.6 | 0.8 | 1.5 |
| task-rule | 0.358 | 0.408 | 0.508 | 0.858 |
| fit-rule | 0.356 | 0.406 | 0.506 | 0.856 |
| cascade | 0.661 | 0.708 | 0.802 | 1.13 |
| rule+cascade | 0.449 | 0.521 | 0.664 | 1.17 |
| oracle | 0.377 | 0.401 | 0.449 | 0.617 |
| fastest (no oracle) | fit-rule | always-local | always-local | always-local |

## When energy-best and carbon-best disagree

For one request, local wins on energy when local Wh < cloud Wh, and on carbon when local Wh x 420 < cloud Wh x 350. With the low estimate (0.24 Wh) the two disagree only when local energy is between 0.200 and 0.24 Wh.

| model | profile | task | local Wh | energy-best | carbon-best |
|---|---|---|---|---|---|
| gemma2 | gpu | yesno | 0.00133 | local | local |
| gemma2 | gpu | classify | 0.00133 | local | local |
| gemma2 | gpu | extract | 0.00392 | local | local |
| gemma2 | gpu | math | 0.0385 | local | local |
| gemma2 | cpu | yesno | 0.0161 | local | local |
| gemma2 | cpu | classify | 0.00915 | local | local |
| gemma2 | cpu | extract | 0.0165 | local | local |
| gemma2 | cpu | math | 0.0614 | local | local |
| gemma2 | docker-full | yesno | 0.00961 | local | local |
| gemma2 | docker-full | classify | 0.00306 | local | local |
| gemma2 | docker-full | extract | 0.00558 | local | local |
| gemma2 | docker-full | math | 0.0196 | local | local |
| gemma2 | docker-2cpu | yesno | 0.0101 | local | local |
| gemma2 | docker-2cpu | classify | 0.00496 | local | local |
| gemma2 | docker-2cpu | extract | 0.0115 | local | local |
| gemma2 | docker-2cpu | math | 0.0626 | local | local |
