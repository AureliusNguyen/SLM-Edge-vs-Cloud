# SLM Edge vs Cloud

CSCI8980 project (Leo, Shuyuan, Faishal). For each request, decide whether a small model on the device (edge SLM) or a large cloud model should answer, based on answer quality, energy, and carbon.

## Current state

A working demo of the routing idea:

- Local: Llama 3.2 3B in Ollama (Docker)
- Cloud: Groq, `openai/gpt-oss-120b`
- Yes/no and extract questions may run locally; classify and math go to the cloud (from the RQ1 results). Among the allowed tiers that are up, the carbon-aware strategy picks the lowest-carbon one.
- Carbon numbers in `gateway/route.go` come from the RQ2 measurements (local) and a published estimate (cloud).

Results so far:

- RQ1, answer quality (`shuyuan_rq1/`): Llama 3.2 3B, Qwen3 1.7B (thinking off and on) and the cloud on 100 questions each of yes/no, classify, extract and math, plus LLM judges for extract and a confidence-based cascade.
- RQ2, latency, energy and carbon (`rq2/`): measured on a Windows laptop across native GPU, native CPU and two Docker profiles, and for the cloud over Wi-Fi and a phone hotspot.
- RQ3, routing policies (`rq3/`): always-local, always-cloud, the task rule, a confidence cascade, rule+cascade and an oracle, replayed on all RQ1 questions with the RQ2 costs and checked with a live run of the router on 100 mixed questions.

Not done yet: the cascade inside the Go gateway (`rq3/rq3_live.py` implements it in Python), energy logging in the gateway itself (still null in `requests.jsonl`), and an injected-delay network test.

## Files

```
Load-Balancer/   Go load balancer with 11 strategies, incl. strategy/carbon_aware.go
                 (forked from Distributed-Systems-Components)
gateway/         the router: route.go decides, main.go serves HTTP
demo/demo.py     interactive client
shuyuan_rq1/     RQ1: answer quality, local vs cloud
rq2/             RQ2: latency, device energy and carbon per request
rq3/             RQ3: routing policies, offline replay and live check
setup.sh         one-time setup: Docker + local model
```

## Run the demo

Needs Docker, Go 1.22.5+, Python 3, and a Groq API key.

```sh
echo 'GROQ_API_KEY=your-key' > .env
./setup.sh

cd gateway && env $(cat ../.env) go run .   # leave running

python3 demo/demo.py                        # in another terminal, from the repo root
```

Pick 1-6 for a seeded question (BoolQ yes/no, GSM8K math) or type your own. Each answer shows where it went, why, and whether it was right.

```sh
python3 demo/demo.py --all           # run all seeded questions, print a score
python3 demo/demo.py --force local   # always local (or --force cloud)
```

Notes:

- The first local answer can take about 30 s while the model loads on CPU.
- Temperature is 0, so answers are deterministic: a wrong answer stays wrong on reruns.
- Requests are logged to `gateway/requests.jsonl`.

Tests: `go test ./...` in `Load-Balancer/` and in `gateway/`.
