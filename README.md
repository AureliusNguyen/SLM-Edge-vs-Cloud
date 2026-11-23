# SLM Edge vs Cloud

CSCI8980 project (Leo, Shuyuan, Faishal). For each request, decide whether a small model on the device (edge SLM) or a large cloud model should answer, based on answer quality, energy, and carbon.

## Current state

A working demo of the routing idea:

- Local: Llama 3.2 3B in Ollama (Docker)
- Cloud: Groq, `openai/gpt-oss-120b`
- Yes/no and extract questions may run locally; classify and math go to the cloud (from the RQ1 results). Among the allowed tiers that are up, the carbon-aware strategy picks the lowest-carbon one.
- Carbon numbers in `gateway/route.go` come from the RQ2 measurements (local) and a published estimate (cloud).

Results so far:

- RQ1, answer quality (`shuyuan_rq1/`): Llama 3.2 3B, Qwen3 1.7B (thinking off and on) and the cloud on 100 questions each of yes/no, classify, extract and math, plus LLM judges for extract and a confidence-based cascade. Phi-3.5 mini and Gemma 2 2B were added later on the same 400 questions to check that the conclusions hold beyond Llama (`rq3/results_extra/EXTRA_MODELS_SUMMARY.md`).
- RQ2, latency, energy and carbon (`rq2/`): measured on a Windows laptop across native GPU, native CPU and two Docker profiles, and for the cloud over Wi-Fi and a phone hotspot.
- RQ3, routing policies (`rq3/`): always-local, always-cloud, the task rule, a per-model task rule (fit-rule), a confidence cascade, rule+cascade and an oracle, replayed on all RQ1 questions with the RQ2 costs and checked with a live run of the router on 100 mixed questions.

The gateway can also run the cascades (`-policy rule+cascade` or `-policy cascade` with `-thresholds rq3/results/thresholds_llama.json`), logs an energy and carbon estimate for every request (`energy_wh_est`, `gco2e_est`, summed over every tier the request used), and can add a fixed delay to every cloud call (`-cloud-delay 300ms`) to emulate a slower network. Device energy is still measured outside the gateway, with `rq2/rq2_measure.py`.

## Files

```
Load-Balancer/   Go load balancer with 11 strategies, incl. strategy/carbon_aware.go
                 (forked from Distributed-Systems-Components)
gateway/         the router: route.go decides, main.go serves HTTP
demo/demo.py     interactive client
shuyuan_rq1/     RQ1: answer quality, local vs cloud
rq2/             RQ2: latency, device energy and carbon per request
rq3/             RQ3: routing policies, offline replay and live check
load/            open-loop load test: traces, runner, deadline-miss plot
setup.sh         one-time setup: Docker + local model
```

## Run the demo

Needs Docker, Go 1.22.5+, Python 3, and a Groq API key.

```sh
echo 'GROQ_API_KEY=your-key' > .env
./setup.sh

cd gateway && env $(cat ../.env) go run .   # leave running; add -addr :8081 if 8080 is taken
# cascade inside the gateway:
#   env $(cat ../.env) go run . -policy rule+cascade -thresholds ../rq3/results/thresholds_llama.json

python3 demo/demo.py                        # in another terminal, from the repo root
```

Pick 1-6 for a seeded question (BoolQ yes/no, GSM8K math) or type your own. Each answer shows where it went, why, and whether it was right.

```sh
python3 demo/demo.py all           # run all seeded questions, print a score
python3 demo/demo.py local         # always local (or cloud)
```

Notes:

- The first local answer can take about 30 s while the model loads on CPU.
- Temperature is 0, so answers are deterministic: a wrong answer stays wrong on reruns.
- Requests are logged to `gateway/requests.jsonl`.

## Load test

Sends requests through the gateway on a fixed schedule, without waiting for earlier answers, at 0.2, 0.5, 1 and 2 requests/s. With the gateway running:

```sh
load/sweep.sh                  # task-rule, Poisson arrivals, uniform task mix
load/sweep.sh always-cloud     # also always-local; then fixed|uniform|bursty, then uniform|zipf
```

The plot is `load/results/miss_rate.png`. Deadlines: 2 s, 10 s for math. Groq's free tier (8k tokens/min, 1,000 requests/day) limits cloud-heavy runs; its 429s count as misses.

Tests: `go test ./...` in `Load-Balancer/` and in `gateway/`, and `python3 load/test_run.py`.
