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
| fit-rule | per-model task rule: the 2 tasks with the smallest local-vs-cloud gap on the training half run locally (same 50% local share) |
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
  rises from about 0.08 g to 4.3 g for always-cloud and the gaps grow. The order changes for
  Llama: cascade (2.2 g) beats task-rule (2.8 g), because it keeps about half of the long math
  answers local while task-rule sends all math to the cloud.

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

## More models (Phi-3.5 mini, Gemma 2 2B)

Same 400 questions, judges and replay, on the GPU and native CPU profiles; Gemma also got a
live check (`results/live_gemma2_gpu.md`). The conclusions above hold for all three SLMs: same
policy ranking, the cascade-oracle gap stays, carbon follows the cloud-call share, and the CPU
makes local-first policies slower than the cloud. The fixed task rule is not best for every model
(Gemma does better with classify + extract local, 0.890 vs 0.875). Details:
`results_extra/EXTRA_MODELS_SUMMARY.md`; tables `results_extra/rq3_{llama,phi35,gemma2}.md`
(these also include fit-rule and a network-delay sensitivity table).

## Run

```
python rq3/rq3_sim.py                       # Llama, writes results/rq3_llama.{md,csv} and thresholds
python rq3/rq3_sim.py --model qwen_nothink
python rq3/rq3_sim.py --model gemma2 --out rq3/results_extra   # also llama, phi35
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

## Hourly grid, full comparison, embodied and network carbon

```
python rq3/get_hourly_ci.py          # EIA-930 MISO 2024 -> results/miso_hourly_ci_2024.csv
python rq3/rq3_hourly.py --model llama [--upper]
python rq3/rq3_compare.py            # all policies x both SLMs -> results/rq3_compare.{md,csv,png}
```

`rq3_compare.py` adds three policies (carbon-aware with the fixed grid, carbon-aware with the
hourly grid, and rule+cascade that also moves SLM-bound requests to the cloud in hours when the
cloud is lower-carbon), prices edge energy with the hourly MISO grid, and adds embodied carbon
(laptop and cloud server) and network carbon with low / mid / high assumptions.
`results/rq3_summary.md` has the numbers and assumptions written up for the report.
Main points: the MISO 2024 mean is 445 g/kWh (we used 420); the hourly grid changes yearly
carbon by at most 1% for any policy that calls the cloud and flips no routing decision on the GPU;
a carbon-only router collapses to always-local; embodied carbon adds about 9% to a cloud request
and 42% to a local one; network carbon is under 1%.
