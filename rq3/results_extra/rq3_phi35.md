# RQ3 results: routing policies (phi35)

Offline replay of the RQ1 answers (100 questions per task, 400 total, equal mix) with the RQ2 per-request costs. Thresholds come from 2-fold cross-validation repeated 50 times; numbers are means over the held-out halves. Extract counts as correct when the gpt-oss-20b judge says CORRECT. Latency is the median per-request time from RQ2 (busy device), so a cascade that escalates pays local + cloud time and energy.

Assumptions: edge grid 420 g/kWh, data-center grid 350 g/kWh, cloud energy 0.24 Wh/request (low) or 83.1 Wh per 1k output tokens (upper), Groq price $0.15/$0.6 per 1M input/output tokens, cascade tolerance 0.02.

## Headline: GPU laptop, Wi-Fi, low cloud-energy estimate

| policy | accuracy (±sd) | kept local | cloud calls/req | latency s | total Wh/req | gCO2e/req | $ per 1k req | Wh per correct | tCDP g·s |
|---|---|---|---|---|---|---|---|---|---|
| always-local | 0.780 (±0.019) | 100% | 0.00 | 0.58 | 0.0231 | 0.00971 | 0.000 | 0.0297 | 0.00563 |
| always-cloud | 0.915 (±0.012) | 0% | 1.00 | 0.5 | 0.241 | 0.0846 | 0.117 | 0.264 | 0.0423 |
| task-rule | 0.877 (±0.017) | 50% | 0.50 | 0.366 | 0.123 | 0.0432 | 0.070 | 0.14 | 0.0158 |
| fit-rule | 0.870 (±0.019) | 50% | 0.50 | 0.468 | 0.127 | 0.045 | 0.062 | 0.146 | 0.0215 |
| cascade | 0.875 (±0.021) | 53% | 0.47 | 0.809 | 0.137 | 0.0498 | 0.051 | 0.157 | 0.0406 |
| rule+cascade | 0.894 (±0.017) | 32% | 0.68 | 0.439 | 0.166 | 0.0584 | 0.087 | 0.186 | 0.0258 |
| oracle | 0.927 (±0.011) | 78% | 0.22 | 0.597 | 0.0712 | 0.0262 | 0.022 | 0.0768 | 0.0157 |

Per-task accuracy:

| policy | yesno | classify | extract | math |
|---|---|---|---|---|
| always-local | 0.860 | 0.470 | 0.930 | 0.860 |
| always-cloud | 0.940 | 0.750 | 1.000 | 0.970 |
| task-rule | 0.860 | 0.750 | 0.930 | 0.970 |
| fit-rule | 0.865 | 0.750 | 0.936 | 0.930 |
| cascade | 0.895 | 0.712 | 0.960 | 0.931 |
| rule+cascade | 0.895 | 0.750 | 0.960 | 0.970 |
| oracle | 0.950 | 0.780 | 1.000 | 0.980 |

fit-rule keeps local the 2 tasks with the smallest SLM-vs-cloud accuracy gap on the training half (same 50% local share as task-rule). Fit on all questions: **yesno + extract** local. Chosen across the CV folds: yesno+extract 72%, yesno+math 15%, extract+math 13%.

Cascade thresholds (mean token log-prob) fit on all 100 questions, for the gateway; 'cloud' means no threshold met the tolerance, so the task always goes to the cloud. 'never local' is how often that happened across the cross-validation folds.

| task | threshold | never local in CV |
|---|---|---|
| yesno | -0.2057 | 0% |
| classify | -0.0037 | 0% |
| extract | -0.1052 | 0% |
| math | -0.1081 | 0% |

## All scenarios

accuracy / gCO2e per request / latency s, per policy. Accuracy does not depend on the scenario (same answers), only the cost does.

| profile | network | cloud energy | always-local | always-cloud | task-rule | fit-rule | cascade | rule+cascade | oracle |
|---|---|---|---|---|---|---|---|---|---|
| gpu | wifi | low | 0.78 / 0.0097 / 0.58 | 0.92 / 0.085 / 0.5 | 0.88 / 0.043 / 0.37 | 0.87 / 0.045 / 0.47 | 0.87 / 0.05 / 0.81 | 0.89 / 0.058 / 0.44 | 0.93 / 0.026 / 0.6 |
| gpu | wifi | upper | 0.78 / 0.0097 / 0.58 | 0.92 / 4.3 / 0.5 | 0.88 / 2.8 / 0.37 | 0.87 / 2.4 / 0.47 | 0.87 / 1.9 / 0.81 | 0.89 / 3.4 / 0.44 | 0.93 / 0.78 / 0.6 |
| gpu | hotspot | low | 0.78 / 0.0097 / 0.58 | 0.92 / 0.084 / 0.75 | 0.88 / 0.043 / 0.48 | 0.87 / 0.045 / 0.58 | 0.87 / 0.05 / 0.92 | 0.89 / 0.058 / 0.6 | 0.93 / 0.026 / 0.65 |
| gpu | hotspot | upper | 0.78 / 0.0097 / 0.58 | 0.92 / 4.5 / 0.75 | 0.88 / 3 / 0.48 | 0.87 / 2.6 / 0.58 | 0.87 / 1.9 / 0.92 | 0.89 / 3.6 / 0.6 | 0.93 / 0.81 / 0.65 |
| cpu | wifi | low | 0.78 / 0.013 / 3 | 0.92 / 0.085 / 0.5 | 0.88 / 0.047 / 1.2 | 0.87 / 0.049 / 1.6 | 0.87 / 0.053 / 3.2 | 0.89 / 0.062 / 1.3 | 0.93 / 0.03 / 2.6 |
| cpu | wifi | upper | 0.78 / 0.013 / 3 | 0.92 / 4.3 / 0.5 | 0.88 / 2.9 / 1.2 | 0.87 / 2.4 / 1.6 | 0.87 / 1.9 / 3.2 | 0.89 / 3.4 / 1.3 | 0.93 / 0.78 / 2.6 |
| cpu | hotspot | low | 0.78 / 0.013 / 3 | 0.92 / 0.084 / 0.75 | 0.88 / 0.047 / 1.3 | 0.87 / 0.048 / 1.7 | 0.87 / 0.053 / 3.3 | 0.89 / 0.062 / 1.5 | 0.93 / 0.03 / 2.7 |
| cpu | hotspot | upper | 0.78 / 0.013 / 3 | 0.92 / 4.5 / 0.75 | 0.88 / 3 / 1.3 | 0.87 / 2.6 / 1.7 | 0.87 / 2 / 3.3 | 0.89 / 3.6 / 1.5 | 0.93 / 0.82 / 2.7 |
| docker-full | wifi | low | 0.78 / 0.011 / 3.5 | 0.92 / 0.085 / 0.5 | 0.88 / 0.047 / 1.4 | 0.87 / 0.048 / 1.8 | 0.87 / 0.051 / 3.7 | 0.89 / 0.062 / 1.4 | 0.93 / 0.028 / 3 |
| docker-full | wifi | upper | 0.78 / 0.011 / 3.5 | 0.92 / 4.3 / 0.5 | 0.88 / 2.9 / 1.4 | 0.87 / 2.4 / 1.8 | 0.87 / 1.9 / 3.7 | 0.89 / 3.4 / 1.4 | 0.93 / 0.78 / 3 |
| docker-full | hotspot | low | 0.78 / 0.011 / 3.5 | 0.92 / 0.084 / 0.75 | 0.88 / 0.047 / 1.5 | 0.87 / 0.047 / 1.9 | 0.87 / 0.051 / 3.8 | 0.89 / 0.062 / 1.6 | 0.93 / 0.027 / 3.1 |
| docker-full | hotspot | upper | 0.78 / 0.011 / 3.5 | 0.92 / 4.5 / 0.75 | 0.88 / 3 / 1.5 | 0.87 / 2.6 / 1.9 | 0.87 / 1.9 / 3.8 | 0.89 / 3.6 / 1.6 | 0.93 / 0.81 / 3.1 |
| docker-2cpu | wifi | low | 0.78 / 0.031 / 7.8 | 0.92 / 0.085 / 0.5 | 0.88 / 0.05 / 3.2 | 0.87 / 0.054 / 4 | 0.87 / 0.071 / 8.1 | 0.89 / 0.066 / 3.3 | 0.93 / 0.043 / 6.8 |
| docker-2cpu | wifi | upper | 0.78 / 0.031 / 7.8 | 0.92 / 4.3 / 0.5 | 0.88 / 2.9 / 3.2 | 0.87 / 2.4 / 4 | 0.87 / 1.9 / 8.1 | 0.89 / 3.4 / 3.3 | 0.93 / 0.79 / 6.8 |
| docker-2cpu | hotspot | low | 0.78 / 0.031 / 7.8 | 0.92 / 0.084 / 0.75 | 0.88 / 0.05 / 3.3 | 0.87 / 0.054 / 4.1 | 0.87 / 0.071 / 8.2 | 0.89 / 0.065 / 3.4 | 0.93 / 0.043 / 6.8 |
| docker-2cpu | hotspot | upper | 0.78 / 0.031 / 7.8 | 0.92 / 4.5 / 0.75 | 0.88 / 3 / 3.3 | 0.87 / 2.6 / 4.1 | 0.87 / 2 / 8.2 | 0.89 / 3.6 / 3.4 | 0.93 / 0.83 / 6.8 |

## Low battery (20% of requests forced to the cloud)

Expected value: (1 - share) x policy + share x always-cloud, GPU / Wi-Fi / low estimate.

| policy | accuracy | kept local | latency s | gCO2e/req | $ per 1k req |
|---|---|---|---|---|---|
| always-local | 0.807 | 80% | 0.564 | 0.0247 | 0.023 |
| always-cloud | 0.915 | 0% | 0.5 | 0.0846 | 0.117 |
| task-rule | 0.885 | 40% | 0.393 | 0.0515 | 0.079 |
| fit-rule | 0.879 | 40% | 0.474 | 0.0529 | 0.073 |
| cascade | 0.883 | 42% | 0.747 | 0.0567 | 0.064 |
| rule+cascade | 0.898 | 26% | 0.451 | 0.0637 | 0.093 |
| oracle | 0.925 | 62% | 0.578 | 0.0379 | 0.041 |

## Edge-grid sensitivity (GPU / Wi-Fi / low estimate)

gCO2e per request when the device sits on a different grid. 420 = eGRID MROW (ours), 364 = Minnesota state average and 163 = a solar-rich western state (both from Kopczyk & Chandra).

| policy | 163 | 364 | 420 |
|---|---|---|---|
| always-local | 0.00377 | 0.00842 | 0.00971 |
| always-cloud | 0.0842 | 0.0845 | 0.0846 |
| task-rule | 0.0425 | 0.0431 | 0.0432 |
| fit-rule | 0.0425 | 0.0431 | 0.0432 |
| cascade | 0.045 | 0.0498 | 0.0511 |
| rule+cascade | 0.0572 | 0.0579 | 0.0581 |
| oracle | 0.0215 | 0.0252 | 0.0262 |

## Network delay sensitivity (GPU / Wi-Fi / low estimate)

Mean latency per request (s) when every cloud call takes this much longer. Accuracy and carbon do not change. Cascade thresholds fit on all questions.

| policy | +0 s | +0.1 s | +0.3 s | +1 s |
|---|---|---|---|---|
| always-local | 0.58 | 0.58 | 0.58 | 0.58 |
| always-cloud | 0.5 | 0.6 | 0.8 | 1.5 |
| task-rule | 0.366 | 0.416 | 0.516 | 0.866 |
| fit-rule | 0.366 | 0.416 | 0.516 | 0.866 |
| cascade | 0.82 | 0.869 | 0.967 | 1.31 |
| rule+cascade | 0.438 | 0.505 | 0.64 | 1.11 |
| oracle | 0.597 | 0.619 | 0.663 | 0.817 |
| fastest (no oracle) | task-rule | task-rule | task-rule | always-local |

## When energy-best and carbon-best disagree

For one request, local wins on energy when local Wh < cloud Wh, and on carbon when local Wh x 420 < cloud Wh x 350. With the low estimate (0.24 Wh) the two disagree only when local energy is between 0.200 and 0.24 Wh.

| model | profile | task | local Wh | energy-best | carbon-best |
|---|---|---|---|---|---|
| phi35 | gpu | yesno | 0.00502 | local | local |
| phi35 | gpu | classify | 0.0182 | local | local |
| phi35 | gpu | extract | 0.00527 | local | local |
| phi35 | gpu | math | 0.064 | local | local |
| phi35 | cpu | yesno | 0.0332 | local | local |
| phi35 | cpu | classify | 0.00959 | local | local |
| phi35 | cpu | extract | 0.0147 | local | local |
| phi35 | cpu | math | 0.0681 | local | local |
| phi35 | docker-full | yesno | 0.03 | local | local |
| phi35 | docker-full | classify | 0.0147 | local | local |
| phi35 | docker-full | extract | 0.0147 | local | local |
| phi35 | docker-full | math | 0.045 | local | local |
| phi35 | docker-2cpu | yesno | 0.0434 | local | local |
| phi35 | docker-2cpu | classify | 0.0534 | local | local |
| phi35 | docker-2cpu | extract | 0.0347 | local | local |
| phi35 | docker-2cpu | math | 0.164 | local | local |
