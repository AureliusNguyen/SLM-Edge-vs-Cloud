# RQ3 live run (llama, gpu, wifi, 25 questions per task)

Measured: accuracy (extract = F1 here, the judge is not re-run), share answered locally, latency, device energy above idle. Carbon adds the cloud estimate (0.24 Wh per cloud call, 350 g/kWh) to device energy at 420 g/kWh.

| policy | n | score | answered locally | escalated | median s | mean s | device Wh/req | cloud calls/req | gCO2e/req |
|---|---|---|---|---|---|---|---|---|---|
| task-rule | 100 | 0.856 | 50% | 0% | 0.30 | 0.34 | 0.0018 | 0.50 | 0.0428 |
| rule+cascade | 100 | 0.923 | 20% | 30% | 0.46 | 0.52 | 0.0033 | 0.80 | 0.0686 |
| cascade | 100 | 0.913 | 38% | 62% | 0.62 | 0.87 | 0.0164 | 0.62 | 0.0590 |
