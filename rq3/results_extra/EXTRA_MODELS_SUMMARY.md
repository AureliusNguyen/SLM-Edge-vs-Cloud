# Extra local models: Phi-3.5 mini and Gemma 2 2B

Added to check whether the RQ1/RQ3 conclusions hold beyond Llama 3.2 3B. Run on 2026-11-22
on the RTX 4060 laptop.

## What was run

- RQ1: `rq1_direct.py` straight to Ollama (GPU, temperature 0), the same 400 questions
  (100 each of BoolQ yes/no, AG News classify, SQuAD extract, GSM8K math), prompts and scoring
  as Llama/Qwen. Ollama models `phi3.5` (3.8B) and `gemma2:2b`. Output: `shuyuan_rq1/results/phi35.csv`, `gemma2.csv`.
- Extract judged by the same judges as before: gpt-oss-20b (used by RQ3) and qwen3.8-27b
  (`results/judge/`). Earlier verdicts are reused unchanged (checked: 0 of 400 changed). The two judges agree on 98% (Phi, kappa 0.85) and 99% (Gemma, kappa 0.85) of the new extract replies; qwen3.8-27b gives Phi 0.93 and Gemma 0.96 (`judge_agree_extra.md`).
- RQ2 (cost for the replay): `rq2_measure.py`, GPU, busy mode, 20 per task, CPU package power from
  LibreHardwareMonitor + GPU power from nvidia-smi, the same method as the original RQ2
  (`rq2/results/extra/*_gpu_busy_lhm.csv`). Llama was re-measured in the same session as a check:
  its device energy matches the original RQ2 run (yes/no 0.0009 vs 0.0008 Wh, math 0.046 vs 0.052 Wh),
  even though idle power on this machine was higher (~30 W). RQ3 uses the original Llama RQ2 file.
- The native CPU profile (`--cpu-only`) was measured the same way for Phi and Gemma (`*_cpu_busy_lhm.csv`). No Docker profiles.
- RQ3: `rq3_sim.py` (now accepts `--model phi35|gemma2`, GPU and CPU profiles), same 50x 2-fold CV
  thresholds, tolerance 0.02. Re-running Llama with this code gives the identical headline table.

Phi-3.5 looped on one classify prompt at temperature 0 and Ollama aborted it ("token repeat limit");
that reply is counted as a format error (`rq1_direct.py` now records this instead of crashing).

## RQ1: quality (extract = gpt-oss-20b judge; F1 in brackets)

| task | Llama 3.2 3B | Qwen3 1.7B (think off) | Phi-3.5 mini | Gemma 2 2B | cloud gpt-oss-120b |
|---|---|---|---|---|---|
| yesno | 0.78 | 0.78 | 0.86 | 0.81 | 0.94 |
| classify | 0.55 | 0.36 | 0.47 | 0.69 | 0.75 |
| extract | 0.93 (0.83) | 0.95 (0.55) | 0.93 (0.84) | 0.97 (0.84) | 1.00 (0.88) |
| math | 0.73 | 0.22 | 0.86 | 0.57 | 0.97 |
| confidence AUROC (yesno/classify/extract-F1/math) | 0.72/0.66/0.54/0.83 | 0.55/0.70/0.57/0.59 | 0.54/0.71/0.71/0.76 | 0.61/0.52/0.58/0.69 | |

## RQ3 headline (GPU, Wi-Fi, 0.24 Wh per cloud request)

| policy | Llama acc. | Llama local | Phi acc. | Phi local | Gemma acc. | Gemma local | gCO2e/req (L / P / G) |
|---|---|---|---|---|---|---|---|
| always-local | 0.748 | 100% | 0.780 | 100% | 0.760 | 100% | 0.006 / 0.010 / 0.005 |
| always-cloud | 0.915 | 0% | 0.915 | 0% | 0.915 | 0% | 0.085 |
| task-rule | 0.858 | 50% | 0.877 | 50% | 0.875 | 50% | 0.043 / 0.043 / 0.043 |
| fit-rule (per model, CV) | 0.849 | 50% | 0.870 | 50% | 0.890 | 50% | 0.043 / 0.045 / 0.043 |
| cascade | 0.878 | 48% | 0.875 | 53% | 0.885 | 56% | 0.049 / 0.050 / 0.042 |
| rule+cascade | 0.895 | 27% | 0.894 | 32% | 0.899 | 30% | 0.062 / 0.058 / 0.060 |
| oracle | 0.917 | 75% | 0.927 | 78% | 0.927 | 76% | 0.026 / 0.026 / 0.023 |

Full tables (all scenarios, per-task accuracy, thresholds): `rq3/results_extra/rq3_{llama,phi35,gemma2}.md`.

## What carries over

- The ranking of policies is the same for all three models: task-rule halves cloud calls and
  carbon for 4-6 points of accuracy; rule+cascade gets within ~0.02 of always-cloud with ~30% local;
  the oracle keeps 75-78% local at cloud-level accuracy. The gap between cascade and oracle is
  there for every model, so the confidence signal stays the bottleneck (AUROC 0.52-0.83).
- Carbon per request is set by the share of cloud calls; local energy is too small to change it
  on the GPU (0.005-0.010 g for all-local vs 0.085 g for all-cloud).
- All SLMs trail the cloud on every task, but where they are weak differs: Phi is strong on math
  (0.86) and weak on classify (0.47); Gemma is the reverse (classify 0.69, math 0.57).
- **fit-rule** (new policy in `rq3_sim.py`): keep local the 2 tasks with the smallest SLM-vs-cloud
  gap on the training half, scored on the held-out half (same 50% local share and carbon as task-rule).
  - Gemma: picks classify + extract in 93% of folds and beats the fixed rule, 0.890 vs 0.875.
  - Llama and Phi: the full data picks yes/no + extract (the fixed rule), but with 50 questions per
    task the choice flips in 23-28% of folds, so held-out accuracy is slightly lower (0.849 vs 0.858,
    0.870 vs 0.877).
  - The fixed rule was itself chosen from Llama's RQ1 results, so its Llama score is in-sample and a
    little optimistic. Takeaway: the right rule depends on the model, and fitting it per model helps
    when one model's weak task differs clearly (Gemma); with small gaps, 100 questions per task is
    not enough to pick reliably.

## CPU profile (native CPU, Wi-Fi, low estimate): accuracy / gCO2e / latency s

| policy | Llama | Phi-3.5 | Gemma 2 |
|---|---|---|---|
| always-local | 0.75 / 0.015 / 1.9 | 0.78 / 0.013 / 3.0 | 0.76 / 0.011 / 1.8 |
| always-cloud | 0.92 / 0.085 / 0.5 | same | same |
| task-rule | 0.86 / 0.046 / 0.72 | 0.88 / 0.047 / 1.2 | 0.88 / 0.046 / 0.85 |
| cascade | 0.88 / 0.059 / 2.2 | 0.87 / 0.053 / 3.2 | 0.88 / 0.048 / 2.0 |
| rule+cascade | 0.90 / 0.066 / 0.81 | 0.89 / 0.062 / 1.3 | 0.90 / 0.063 / 0.94 |

The CPU result carries over too: on the CPU every policy that runs locally is slower than
always-cloud (0.5 s), and cascade is the slowest, while carbon stays about half of always-cloud
for task-rule. Phi (3.8B) is the slowest on the CPU.

## Live check with Gemma 2 2B (GPU, Wi-Fi, 25 questions per task, `rq3/results/live_gemma2_gpu.md`)

The router ran for real with Gemma's thresholds (`rq3/results/thresholds_gemma2.json`):

| policy | live score | replay score, same questions | answered locally | same route as replay | median s | gCO2e/req |
|---|---|---|---|---|---|---|
| task-rule | 0.872 | 0.872 | 50% | 100% | 0.39 | 0.043 |
| rule+cascade | 0.922 | 0.922 | 25% | 99% | 0.52 | 0.064 |
| cascade | 0.902 | 0.892 | 49% | 98% | 0.55 | 0.047 |

As with Llama, the live router takes the same route as the replay for 98-100% of requests, and
every local answer was scored the same as in RQ1 (extract uses F1 here on both sides).

## Network delay (offline, `rq3_sim.py` "Network delay sensitivity"; gateway flag `-cloud-delay`)

Adding a fixed delay to every cloud call changes only latency. On the GPU the point where
always-local becomes faster than task-rule depends on how fast the local model is: under +0.1 s
per cloud call for Gemma (0.38 s all-local), +0.1 to +0.3 s for Llama (0.44 s), and +0.3 to +1 s for Phi (0.58 s).
The cascades lose the most, because an escalated request pays the delay on top of the local answer.
Full tables in each `rq3_<model>.md`.

## Limits

- New models ran on the GPU; Llama's RQ1 seconds were on a CPU laptop, so RQ1 times are not comparable (quality is).
- Device energy is from 20 questions per task, back-to-back; short-request energy is noisy. Phi's
  classify mean is pulled up by one reply that looped until the 1024-token cap. Local energy is
  too small to change any carbon conclusion.
- New models have GPU and native CPU profiles only (no Docker profiles). Idle power during these runs was 30-44 W, higher than the original RQ2 session; a Llama re-run in the same session matched the original energy, so the extra-energy method is not thrown off by it.
