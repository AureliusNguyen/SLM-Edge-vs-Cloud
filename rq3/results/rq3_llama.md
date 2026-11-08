# RQ3 results: routing policies (llama)

Offline replay of the RQ1 answers (100 questions per task, 400 total, equal mix) with the RQ2 per-request costs. Thresholds come from 2-fold cross-validation repeated 50 times; numbers are means over the held-out halves. Extract counts as correct when the gpt-oss-20b judge says CORRECT. Latency is the median per-request time from RQ2 (busy device), so a cascade that escalates pays local + cloud time and energy.

Assumptions: edge grid 420 g/kWh, data-center grid 350 g/kWh, cloud energy 0.24 Wh/request (low) or 83.1 Wh per 1k output tokens (upper), Groq price $0.15/$0.6 per 1M input/output tokens, cascade tolerance 0.02.

## Headline: GPU laptop, Wi-Fi, low cloud-energy estimate

| policy | accuracy (±sd) | kept local | cloud calls/req | latency s | total Wh/req | gCO2e/req | $ per 1k req | Wh per correct | tCDP g·s |
|---|---|---|---|---|---|---|---|---|---|
| always-local | 0.748 (±0.022) | 100% | 0.00 | 0.437 | 0.0139 | 0.00584 | 0.000 | 0.0186 | 0.00255 |
| always-cloud | 0.915 (±0.012) | 0% | 1.00 | 0.5 | 0.241 | 0.0846 | 0.117 | 0.264 | 0.0423 |
| task-rule | 0.858 (±0.018) | 50% | 0.50 | 0.358 | 0.121 | 0.0425 | 0.070 | 0.141 | 0.0152 |
| cascade | 0.878 (±0.026) | 48% | 0.52 | 0.696 | 0.138 | 0.0494 | 0.060 | 0.157 | 0.0347 |
| rule+cascade | 0.895 (±0.020) | 27% | 0.73 | 0.451 | 0.177 | 0.062 | 0.092 | 0.197 | 0.0281 |
| oracle | 0.917 (±0.012) | 75% | 0.25 | 0.451 | 0.0711 | 0.0256 | 0.029 | 0.0776 | 0.0116 |

Per-task accuracy:

| policy | yesno | classify | extract | math |
|---|---|---|---|---|
| always-local | 0.780 | 0.550 | 0.930 | 0.730 |
| always-cloud | 0.940 | 0.750 | 1.000 | 0.970 |
| task-rule | 0.780 | 0.750 | 0.930 | 0.970 |
| cascade | 0.898 | 0.719 | 0.963 | 0.931 |
| rule+cascade | 0.898 | 0.750 | 0.963 | 0.970 |
| oracle | 0.950 | 0.750 | 1.000 | 0.970 |

Cascade thresholds (mean token log-prob) fit on all 100 questions, for the gateway; 'cloud' means no threshold met the tolerance, so the task always goes to the cloud. 'never local' is how often that happened across the cross-validation folds.

| task | threshold | never local in CV |
|---|---|---|
| yesno | -0.0184 | 0% |
| classify | -0.0624 | 0% |
| extract | -0.0783 | 0% |
| math | -0.1147 | 0% |

## All scenarios

accuracy / gCO2e per request / latency s, per policy. Accuracy does not depend on the scenario (same answers), only the cost does.

| profile | network | cloud energy | always-local | always-cloud | task-rule | cascade | rule+cascade | oracle |
|---|---|---|---|---|---|---|---|---|
| gpu | wifi | low | 0.75 / 0.0058 / 0.44 | 0.92 / 0.085 / 0.5 | 0.86 / 0.042 / 0.36 | 0.88 / 0.049 / 0.7 | 0.90 / 0.062 / 0.45 | 0.92 / 0.026 / 0.45 |
| gpu | wifi | upper | 0.75 / 0.0058 / 0.44 | 0.92 / 4.3 / 0.5 | 0.86 / 2.8 / 0.36 | 0.88 / 2.2 / 0.7 | 0.90 / 3.5 / 0.45 | 0.92 / 1.1 / 0.45 |
| gpu | hotspot | low | 0.75 / 0.0058 / 0.44 | 0.92 / 0.084 / 0.75 | 0.86 / 0.042 / 0.47 | 0.88 / 0.049 / 0.82 | 0.90 / 0.062 / 0.63 | 0.92 / 0.026 / 0.51 |
| gpu | hotspot | upper | 0.75 / 0.0058 / 0.44 | 0.92 / 4.5 / 0.75 | 0.86 / 3 / 0.47 | 0.88 / 2.3 / 0.82 | 0.90 / 3.7 / 0.63 | 0.92 / 1.1 / 0.51 |
| cpu | wifi | low | 0.75 / 0.015 / 1.9 | 0.92 / 0.085 / 0.5 | 0.86 / 0.046 / 0.72 | 0.88 / 0.059 / 2.2 | 0.90 / 0.066 / 0.81 | 0.92 / 0.033 / 1.6 |
| cpu | wifi | upper | 0.75 / 0.015 / 1.9 | 0.92 / 4.3 / 0.5 | 0.86 / 2.8 / 0.72 | 0.88 / 2.2 / 2.2 | 0.90 / 3.5 / 0.81 | 0.92 / 1.1 / 1.6 |
| cpu | hotspot | low | 0.75 / 0.015 / 1.9 | 0.92 / 0.084 / 0.75 | 0.86 / 0.046 / 0.83 | 0.88 / 0.058 / 2.3 | 0.90 / 0.065 / 0.99 | 0.92 / 0.032 / 1.6 |
| cpu | hotspot | upper | 0.75 / 0.015 / 1.9 | 0.92 / 4.5 / 0.75 | 0.86 / 3 / 0.83 | 0.88 / 2.3 / 2.3 | 0.90 / 3.7 / 0.99 | 0.92 / 1.1 / 1.6 |
| docker-full | wifi | low | 0.75 / 0.018 / 2.2 | 0.92 / 0.085 / 0.5 | 0.86 / 0.047 / 0.81 | 0.88 / 0.061 / 2.5 | 0.90 / 0.066 / 0.9 | 0.92 / 0.035 / 1.8 |
| docker-full | wifi | upper | 0.75 / 0.018 / 2.2 | 0.92 / 4.3 / 0.5 | 0.86 / 2.9 / 0.81 | 0.88 / 2.2 / 2.5 | 0.90 / 3.5 / 0.9 | 0.92 / 1.1 / 1.8 |
| docker-full | hotspot | low | 0.75 / 0.018 / 2.2 | 0.92 / 0.084 / 0.75 | 0.86 / 0.047 / 0.92 | 0.88 / 0.061 / 2.6 | 0.90 / 0.066 / 1.1 | 0.92 / 0.035 / 1.8 |
| docker-full | hotspot | upper | 0.75 / 0.018 / 2.2 | 0.92 / 4.5 / 0.75 | 0.86 / 3 / 0.92 | 0.88 / 2.4 / 2.6 | 0.90 / 3.7 / 1.1 | 0.92 / 1.2 / 1.8 |
| docker-2cpu | wifi | low | 0.75 / 0.029 / 4.8 | 0.92 / 0.085 / 0.5 | 0.86 / 0.049 / 1.8 | 0.88 / 0.072 / 5.1 | 0.90 / 0.068 / 1.9 | 0.92 / 0.043 / 3.8 |
| docker-2cpu | wifi | upper | 0.75 / 0.029 / 4.8 | 0.92 / 4.3 / 0.5 | 0.86 / 2.9 / 1.8 | 0.88 / 2.2 / 5.1 | 0.90 / 3.5 / 1.9 | 0.92 / 1.1 / 3.8 |
| docker-2cpu | hotspot | low | 0.75 / 0.029 / 4.8 | 0.92 / 0.084 / 0.75 | 0.86 / 0.049 / 1.9 | 0.88 / 0.072 / 5.2 | 0.90 / 0.068 / 2 | 0.92 / 0.043 / 3.8 |
| docker-2cpu | hotspot | upper | 0.75 / 0.029 / 4.8 | 0.92 / 4.5 / 0.75 | 0.86 / 3 / 1.9 | 0.88 / 2.4 / 5.2 | 0.90 / 3.7 / 2 | 0.92 / 1.2 / 3.8 |

## Low battery (20% of requests forced to the cloud)

Expected value: (1 - share) x policy + share x always-cloud, GPU / Wi-Fi / low estimate.

| policy | accuracy | kept local | latency s | gCO2e/req | $ per 1k req |
|---|---|---|---|---|---|
| always-local | 0.781 | 80% | 0.45 | 0.0216 | 0.023 |
| always-cloud | 0.915 | 0% | 0.5 | 0.0846 | 0.117 |
| task-rule | 0.869 | 40% | 0.386 | 0.0509 | 0.079 |
| cascade | 0.885 | 39% | 0.657 | 0.0565 | 0.072 |
| rule+cascade | 0.899 | 22% | 0.461 | 0.0665 | 0.097 |
| oracle | 0.917 | 60% | 0.461 | 0.0374 | 0.047 |

## Edge-grid sensitivity (GPU / Wi-Fi / low estimate)

gCO2e per request when the device sits on a different grid. 420 = eGRID MROW (ours), 364 = Minnesota state average and 163 = a solar-rich western state (both from Kopczyk & Chandra).

| policy | 163 | 364 | 420 |
|---|---|---|---|
| always-local | 0.00226 | 0.00506 | 0.00584 |
| always-cloud | 0.0842 | 0.0845 | 0.0846 |
| task-rule | 0.0422 | 0.0424 | 0.0425 |
| cascade | 0.0488 | 0.0518 | 0.0526 |
| rule+cascade | 0.0645 | 0.0649 | 0.065 |
| oracle | 0.0229 | 0.025 | 0.0256 |

## When energy-best and carbon-best disagree

For one request, local wins on energy when local Wh < cloud Wh, and on carbon when local Wh x 420 < cloud Wh x 350. With the low estimate (0.24 Wh) the two disagree only when local energy is between 0.200 and 0.24 Wh.

| model | profile | task | local Wh | energy-best | carbon-best |
|---|---|---|---|---|---|
| llama | gpu | yesno | 0.000811 | local | local |
| llama | gpu | classify | 0.000675 | local | local |
| llama | gpu | extract | 0.00214 | local | local |
| llama | gpu | math | 0.052 | local | local |
| llama | cpu | yesno | 0.018 | local | local |
| llama | cpu | classify | 0.00804 | local | local |
| llama | cpu | extract | 0.0197 | local | local |
| llama | cpu | math | 0.0966 | local | local |
| llama | docker-full | yesno | 0.0233 | local | local |
| llama | docker-full | classify | 0.00964 | local | local |
| llama | docker-full | extract | 0.0211 | local | local |
| llama | docker-full | math | 0.115 | local | local |
| llama | docker-2cpu | yesno | 0.0338 | local | local |
| llama | docker-2cpu | classify | 0.013 | local | local |
| llama | docker-2cpu | extract | 0.0294 | local | local |
| llama | docker-2cpu | math | 0.197 | local | local |
