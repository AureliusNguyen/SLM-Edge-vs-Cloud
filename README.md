# SLM Edge vs Cloud

CSCI8980 project (Leo, Shuyuan, Faishal). For each request, decide whether a small model on the device (edge SLM) or a large cloud model should answer, based on answer quality, energy, and carbon.

## Current state

A working demo of the routing idea:

- Local: Llama 3.2 3B in Ollama (Docker)
- Cloud: Groq, `openai/gpt-oss-120b`
- Yes/no questions may run locally, math goes to the cloud. Among the allowed tiers that are up, the carbon-aware strategy picks the lowest-carbon one.

Not done yet: energy measurement (logged as null), real carbon numbers (placeholders in `gateway/route.go`), bigger dataset runs, and the cascade (answer locally first, escalate to the cloud when unsure).

## Files

```
Load-Balancer/   Go load balancer with 11 strategies, incl. strategy/carbon_aware.go
                 (forked from Distributed-Systems-Components)
gateway/         the router: route.go decides, main.go serves HTTP
demo/demo.py     interactive client
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
