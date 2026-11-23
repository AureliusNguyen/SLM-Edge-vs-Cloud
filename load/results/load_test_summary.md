# Load test results (open-loop, Poisson arrivals, uniform task mix)

Setup: `load/sweep.sh` on commit c12370c, 200 requests per rate, seed 1. Deadlines 2 s (yesno, classify, extract) and 10 s (math). Local tier: Llama 3.2 3B in native Ollama on the Windows laptop. Cloud tier: Groq `openai/gpt-oss-120b`, free tier. Gateway ran on port 8081 (8080 was taken); the runner was otherwise unchanged. Max dispatch lag stayed under 20 ms in every run, so all runs were truly open-loop.

| Rate (req/s) | always-local miss | always-local p50 / p95 (s) | task-rule miss | task-rule p50 / p95 (s) |
|---|---|---|---|---|
| 0.2 | 1.5% (3/200) | 0.31 / 2.30 | 0% (0/200) | 0.39 / 1.04 |
| 0.5 | 22% (44/200) | 1.09 / 31.8 | 0% (0/200) | 0.36 / 1.03 |
| 1   | 3% (6/200)   | 0.61 / 2.39 | 6% (12/200) | 0.29 / 0.97 |
| 2   | 76% (152/200) | 5.60 / 46.1 | 29% (58/200) | 0.09 / 0.89 |

Quality (task-rule vs always-local): classify 0.83 vs 0.64, math 1.00 vs 0.72-0.79; yesno 0.76 and extract 0.73 are identical because both policies run them locally.

Notes:
- Every task-rule miss is a Groq HTTP 429 (free-tier rate limit, 8k tokens/min) on classify or math. The local half of task-rule (yesno + extract, about 1 req/s at the top rate) never missed a deadline at any rate.
- always-local is not monotonic at 0.5 req/s. The 44 misses are one contiguous block (requests 101-145, t = 206-320 s): a single math request generated for 44 s and Ollama serves one request at a time, so everything behind it queued. At 2 req/s the queue never drains (p95 46 s).
- always-cloud was not run: at 1-2 req/s it would exceed Groq's free-tier limits, which the task-rule rows already show.
