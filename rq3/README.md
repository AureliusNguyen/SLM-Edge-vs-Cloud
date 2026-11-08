# RQ3: does a routing policy save energy and carbon while keeping quality?

Two parts:

1. **Offline replay** (`rq3_sim.py`). Uses the per-question answers from RQ1 and the
   per-request costs from RQ2, so it needs no new runs. Every policy is scored on the same
   400 questions (100 each of yesno, classify, extract and math) under every device profile,
   both networks, and both cloud-energy estimates.
2. **Live check** (`rq3_live.py`). Runs the router for real on 100 mixed questions with
   power measured, to confirm the replay matches what happens on the machine.

## Policies

| policy | what it does |
|---|---|
| always-local | every request on the SLM |
| always-cloud | every request on gpt-oss-120b (Groq) |
| task-rule | the gateway rule: yesno and extract local, classify and math cloud |
| cascade | the SLM answers first; if its mean token log-prob is below the task's threshold, the request is sent to the cloud as well (pays for both) |
| rule+cascade | task-rule, but the local tasks fall back to the cloud when the SLM is unsure |
| oracle | local when the SLM is right, otherwise cloud. No real router can do this; it is the upper bound |

Each cascade threshold is the lowest one that keeps accuracy within 0.02 of always-cloud.
To avoid tuning on the questions we score, thresholds are picked on one half of the
questions and scored on the other half. This 2-fold split is repeated 50 times, and the
tables report the means. `results/thresholds_<model>.json` holds the thresholds fit on all
100 questions, and those are what the live check uses.

## Headline (Llama 3.2 3B on the GPU laptop, Wi-Fi, 0.24 Wh per cloud request)

| policy | accuracy | kept local | latency s | gCO2e/req | $ per 1k req |
|---|---|---|---|---|---|
| always-local | 0.748 | 100% | 0.44 | 0.0058 | 0 |
| always-cloud | 0.915 | 0% | 0.50 | 0.085 | 0.117 |
| task-rule | 0.858 | 50% | 0.36 | 0.043 | 0.070 |
| cascade | 0.878 | 48% | 0.70 | 0.049 | 0.060 |
| rule+cascade | 0.895 | 27% | 0.45 | 0.062 | 0.092 |
| oracle | 0.917 | 75% | 0.45 | 0.026 | 0.029 |

What this shows:

- **task-rule** halves cloud calls and carbon compared with always-cloud. It is also the
  fastest policy, because it sends each task to whichever side is quicker for it: the GPU
  for short yes/no and extract answers, and the cloud for long math answers. It loses
  about 6 points of accuracy, almost all on yes/no (0.78 vs 0.94).
- **rule+cascade** recovers most of that (0.895), at 0.73 cloud calls per request.
- **cascade on every task** is the slowest policy. An escalated request pays for the
  local answer and then the cloud answer.
- The oracle keeps 75% of requests local at cloud-level accuracy. The confidence signal
  is the bottleneck: its AUROC is only 0.54–0.83 depending on the task (see RQ1).
- On the CPU or the 2-CPU Docker profile, the local side is slow (1.9–4.8 s on average),
  so the policies that run locally first lose their latency advantage. Carbon is still
  lower than always-cloud.
- With the upper cloud-energy estimate (83.1 Wh per 1k output tokens), carbon per request
  rises from about 0.08 g to 4.3 g for always-cloud. The ranking of the policies stays the
  same, but the gap grows.

All scenarios, per-task accuracy, low-battery mixes, edge-grid sensitivity, and when the
energy-best and carbon-best choices disagree are in `results/rq3_llama.md` and
`results/rq3_qwen_nothink.md`. The figure is `results/rq3_llama.png`.

## Live check result (Llama 3.2 3B, GPU laptop, Wi-Fi, 100 shuffled questions)

`results/live_llama_gpu.md` has the full table. The router ran for real, with Ollama and Groq,
and device power was measured with LibreHardwareMonitor and nvidia-smi.

| policy | live score | replay score, same questions | answered locally (live / replay) | same route as replay | median s | device Wh/req | gCO2e/req |
|---|---|---|---|---|---|---|---|
| task-rule | 0.856 | 0.856 | 50% / 50% | 100% | 0.30 | 0.0018 | 0.043 |
| rule+cascade | 0.923 | 0.913 | 20% / 20% | 96% | 0.46 | 0.0033 | 0.069 |
| cascade | 0.913 | 0.913 | 38% / 38% | 94% | 0.62 | 0.0164 | 0.059 |

Scores here use F1 for extract on both sides, because the judge was not re-run live.

- The live router matches the offline replay closely. The task rule chose the same route
  for every request. The cascades chose the same route for 94–96% of requests; the rest
  sit right at the threshold. On the GPU the mean log-prob differs from the RQ1 run by a
  median of 0.005.
- Local answers were scored the same as in RQ1 for 98% of the questions. The replay is
  therefore a fair stand-in for the full grid of scenarios, which would take hours to run
  live.
- Groq's free tier rate-limited the first attempts (HTTP 429). The script now waits and
  retries, does not count the waiting time as latency, and resumes a partial run.

## Run

```
python rq3/rq3_sim.py                       # Llama, writes results/rq3_llama.{md,csv} and thresholds
python rq3/rq3_sim.py --model qwen_nothink
python rq3/rq3_plot.py llama
```

Live check on Windows: start Ollama and the LibreHardwareMonitor web server, then in cmd
from the repo root:

```
set GROQ_API_KEY=your-key
rq3\run_live.bat
```

It runs task-rule, rule+cascade and cascade on the same 100 shuffled questions (25 per task,
the first 25 of each RQ1 set) and writes `results/live_llama_gpu.csv` and `.md`.

## Limits

- Latency and energy per request come from the RQ2 medians and means for each task, not
  from each individual question.
- Extract counts as correct when the gpt-oss-20b judge says CORRECT. The live check uses
  F1 instead, because it does not re-run the judge.
- Cloud price is Groq's list price for gpt-oss-120b ($0.15 per 1M input tokens and $0.60
  per 1M output tokens). Check it before quoting it.
- The low-battery case is simulated by forcing a share of requests to the cloud, as the
  proposal describes. It is not a measured battery.
