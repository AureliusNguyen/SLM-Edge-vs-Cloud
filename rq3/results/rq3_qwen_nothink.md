# RQ3 results: routing policies (qwen_nothink)

Offline replay of the RQ1 answers (100 questions per task, 400 total, equal mix) with the RQ2 per-request costs. Thresholds come from 2-fold cross-validation repeated 50 times; numbers are means over the held-out halves. Extract counts as correct when the gpt-oss-20b judge says CORRECT. Latency is the median per-request time from RQ2 (busy device), so a cascade that escalates pays local + cloud time and energy.

Assumptions: edge grid 420 g/kWh, data-center grid 350 g/kWh, cloud energy 0.24 Wh/request (low) or 83.1 Wh per 1k output tokens (upper), Groq price $0.15/$0.6 per 1M input/output tokens, cascade tolerance 0.02.

## Headline: GPU laptop, Wi-Fi, low cloud-energy estimate

| policy | accuracy (±sd) | kept local | cloud calls/req | latency s | total Wh/req | gCO2e/req | $ per 1k req | Wh per correct | tCDP g·s |
|---|---|---|---|---|---|---|---|---|---|
| always-local | 0.578 (±0.021) | 100% | 0.00 | 0.304 | 0.00939 | 0.00394 | 0.000 | 0.0163 | 0.0012 |
| always-cloud | 0.915 (±0.012) | 0% | 1.00 | 0.5 | 0.241 | 0.0846 | 0.117 | 0.264 | 0.0423 |
| task-rule | 0.863 (±0.015) | 50% | 0.50 | 0.346 | 0.121 | 0.0425 | 0.070 | 0.141 | 0.0147 |
| cascade | 0.883 (±0.023) | 31% | 0.69 | 0.666 | 0.175 | 0.0621 | 0.087 | 0.199 | 0.0415 |
| rule+cascade | 0.897 (±0.016) | 28% | 0.72 | 0.435 | 0.173 | 0.0608 | 0.090 | 0.193 | 0.0265 |
| oracle | 0.922 (±0.012) | 58% | 0.42 | 0.348 | 0.105 | 0.0368 | 0.058 | 0.113 | 0.0128 |

Per-task accuracy:

| policy | yesno | classify | extract | math |
|---|---|---|---|---|
| always-local | 0.780 | 0.360 | 0.950 | 0.220 |
| always-cloud | 0.940 | 0.750 | 1.000 | 0.970 |
| task-rule | 0.780 | 0.750 | 0.950 | 0.970 |
| cascade | 0.901 | 0.718 | 0.965 | 0.945 |
| rule+cascade | 0.901 | 0.750 | 0.965 | 0.970 |
| oracle | 0.960 | 0.760 | 1.000 | 0.970 |

Cascade thresholds (mean token log-prob) fit on all 100 questions, for the gateway; 'cloud' means no threshold met the tolerance, so the task always goes to the cloud. 'never local' is how often that happened across the cross-validation folds.

| task | threshold | never local in CV |
|---|---|---|
| yesno | -0.0147 | 0% |
| classify | cloud | 50% |
| extract | -0.0237 | 0% |
| math | -0.0105 | 0% |

## All scenarios

accuracy / gCO2e per request / latency s, per policy. Accuracy does not depend on the scenario (same answers), only the cost does.

| profile | network | cloud energy | always-local | always-cloud | task-rule | cascade | rule+cascade | oracle |
|---|---|---|---|---|---|---|---|---|
| gpu | wifi | low | 0.58 / 0.0039 / 0.3 | 0.92 / 0.085 / 0.5 | 0.86 / 0.043 / 0.35 | 0.88 / 0.062 / 0.67 | 0.90 / 0.061 / 0.43 | 0.92 / 0.037 / 0.35 |
| gpu | wifi | upper | 0.58 / 0.0039 / 0.3 | 0.92 / 4.3 / 0.5 | 0.86 / 2.8 / 0.35 | 0.88 / 3.3 / 0.67 | 0.90 / 3.5 / 0.43 | 0.92 / 2.3 / 0.35 |
| gpu | hotspot | low | 0.58 / 0.0039 / 0.3 | 0.92 / 0.084 / 0.75 | 0.86 / 0.042 / 0.46 | 0.88 / 0.062 / 0.83 | 0.90 / 0.061 / 0.61 | 0.92 / 0.037 / 0.45 |
| gpu | hotspot | upper | 0.58 / 0.0039 / 0.3 | 0.92 / 4.5 / 0.75 | 0.86 / 3 / 0.46 | 0.88 / 3.6 / 0.83 | 0.90 / 3.7 / 0.61 | 0.92 / 2.5 / 0.45 |
| cpu | wifi | low | 0.58 / 0.01 / 1.2 | 0.92 / 0.085 / 0.5 | 0.86 / 0.045 / 0.57 | 0.88 / 0.068 / 1.6 | 0.90 / 0.064 / 0.66 | 0.92 / 0.04 / 0.7 |
| cpu | wifi | upper | 0.58 / 0.01 / 1.2 | 0.92 / 4.3 / 0.5 | 0.86 / 2.8 / 0.57 | 0.88 / 3.3 / 1.6 | 0.90 / 3.5 / 0.66 | 0.92 / 2.3 / 0.7 |
| cpu | hotspot | low | 0.58 / 0.01 / 1.2 | 0.92 / 0.084 / 0.75 | 0.86 / 0.045 / 0.68 | 0.88 / 0.068 / 1.7 | 0.90 / 0.063 / 0.83 | 0.92 / 0.04 / 0.8 |
| cpu | hotspot | upper | 0.58 / 0.01 / 1.2 | 0.92 / 4.5 / 0.75 | 0.86 / 3 / 0.68 | 0.88 / 3.6 / 1.7 | 0.90 / 3.7 / 0.83 | 0.92 / 2.5 / 0.8 |
| docker-full | wifi | low | 0.58 / 0.011 / 1.4 | 0.92 / 0.085 / 0.5 | 0.86 / 0.046 / 0.63 | 0.88 / 0.069 / 1.7 | 0.90 / 0.064 / 0.72 | 0.92 / 0.041 / 0.78 |
| docker-full | wifi | upper | 0.58 / 0.011 / 1.4 | 0.92 / 4.3 / 0.5 | 0.86 / 2.8 / 0.63 | 0.88 / 3.3 / 1.7 | 0.90 / 3.5 / 0.72 | 0.92 / 2.3 / 0.78 |
| docker-full | hotspot | low | 0.58 / 0.011 / 1.4 | 0.92 / 0.084 / 0.75 | 0.86 / 0.046 / 0.74 | 0.88 / 0.068 / 1.9 | 0.90 / 0.064 / 0.89 | 0.92 / 0.04 / 0.87 |
| docker-full | hotspot | upper | 0.58 / 0.011 / 1.4 | 0.92 / 4.5 / 0.75 | 0.86 / 3 / 0.74 | 0.88 / 3.6 / 1.9 | 0.90 / 3.7 / 0.89 | 0.92 / 2.5 / 0.87 |
| docker-2cpu | wifi | low | 0.58 / 0.017 / 2.5 | 0.92 / 0.085 / 0.5 | 0.86 / 0.047 / 1.2 | 0.88 / 0.074 / 2.8 | 0.90 / 0.066 / 1.3 | 0.92 / 0.043 / 1.4 |
| docker-2cpu | wifi | upper | 0.58 / 0.017 / 2.5 | 0.92 / 4.3 / 0.5 | 0.86 / 2.9 / 1.2 | 0.88 / 3.4 / 2.8 | 0.90 / 3.5 / 1.3 | 0.92 / 2.3 / 1.4 |
| docker-2cpu | hotspot | low | 0.58 / 0.017 / 2.5 | 0.92 / 0.084 / 0.75 | 0.86 / 0.047 / 1.3 | 0.88 / 0.074 / 3 | 0.90 / 0.065 / 1.5 | 0.92 / 0.043 / 1.5 |
| docker-2cpu | hotspot | upper | 0.58 / 0.017 / 2.5 | 0.92 / 4.5 / 0.75 | 0.86 / 3 / 1.3 | 0.88 / 3.6 / 3 | 0.90 / 3.7 / 1.5 | 0.92 / 2.5 / 1.5 |

## Low battery (20% of requests forced to the cloud)

Expected value: (1 - share) x policy + share x always-cloud, GPU / Wi-Fi / low estimate.

| policy | accuracy | kept local | latency s | gCO2e/req | $ per 1k req |
|---|---|---|---|---|---|
| always-local | 0.645 | 80% | 0.343 | 0.0201 | 0.023 |
| always-cloud | 0.915 | 0% | 0.5 | 0.0846 | 0.117 |
| task-rule | 0.873 | 40% | 0.377 | 0.0509 | 0.079 |
| cascade | 0.889 | 25% | 0.633 | 0.0666 | 0.093 |
| rule+cascade | 0.900 | 23% | 0.448 | 0.0656 | 0.095 |
| oracle | 0.921 | 46% | 0.378 | 0.0464 | 0.070 |

## Edge-grid sensitivity (GPU / Wi-Fi / low estimate)

gCO2e per request when the device sits on a different grid. 420 = eGRID MROW (ours), 364 = Minnesota state average and 163 = a solar-rich western state (both from Kopczyk & Chandra).

| policy | 163 | 364 | 420 |
|---|---|---|---|
| always-local | 0.00153 | 0.00342 | 0.00394 |
| always-cloud | 0.0842 | 0.0845 | 0.0846 |
| task-rule | 0.0422 | 0.0425 | 0.0425 |
| cascade | 0.0625 | 0.0646 | 0.0651 |
| rule+cascade | 0.0618 | 0.0622 | 0.0623 |
| oracle | 0.036 | 0.0366 | 0.0368 |

## When energy-best and carbon-best disagree

For one request, local wins on energy when local Wh < cloud Wh, and on carbon when local Wh x 420 < cloud Wh x 350. With the low estimate (0.24 Wh) the two disagree only when local energy is between 0.200 and 0.24 Wh.

| model | profile | task | local Wh | energy-best | carbon-best |
|---|---|---|---|---|---|
| qwen_nothink | gpu | yesno | 0.000701 | local | local |
| qwen_nothink | gpu | classify | 0.000755 | local | local |
| qwen_nothink | gpu | extract | 0.00282 | local | local |
| qwen_nothink | gpu | math | 0.0333 | local | local |
| qwen_nothink | cpu | yesno | 0.012 | local | local |
| qwen_nothink | cpu | classify | 0.00549 | local | local |
| qwen_nothink | cpu | extract | 0.0179 | local | local |
| qwen_nothink | cpu | math | 0.0637 | local | local |
| qwen_nothink | docker-full | yesno | 0.0144 | local | local |
| qwen_nothink | docker-full | classify | 0.00734 | local | local |
| qwen_nothink | docker-full | extract | 0.0196 | local | local |
| qwen_nothink | docker-full | math | 0.0629 | local | local |
| qwen_nothink | docker-2cpu | yesno | 0.0224 | local | local |
| qwen_nothink | docker-2cpu | classify | 0.00905 | local | local |
| qwen_nothink | docker-2cpu | extract | 0.0256 | local | local |
| qwen_nothink | docker-2cpu | math | 0.102 | local | local |
