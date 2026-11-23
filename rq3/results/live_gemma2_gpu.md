# RQ3 live run (gemma2, gpu, wifi, 25 questions per task)

Measured: accuracy (extract = F1 here, the judge is not re-run), share answered locally, latency, device energy above idle. Carbon adds the cloud estimate (0.24 Wh per cloud call, 350 g/kWh) to device energy at 420 g/kWh.

| policy | n | score | answered locally | escalated | median s | mean s | device Wh/req | cloud calls/req | gCO2e/req |
|---|---|---|---|---|---|---|---|---|---|
| task-rule | 100 | 0.872 | 50% | 0% | 0.39 | 0.44 | 0.0014 | 0.50 | 0.0426 |
| rule+cascade | 100 | 0.922 | 25% | 25% | 0.52 | 0.58 | 0.0011 | 0.75 | 0.0635 |
| cascade | 100 | 0.902 | 49% | 51% | 0.55 | 0.87 | 0.0102 | 0.51 | 0.0471 |
