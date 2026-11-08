# RQ2: latency, energy and carbon of local vs cloud inference

How do the device and the network change the latency, energy and carbon of answering a request locally or in the cloud?

## Files

| File | What it does |
|---|---|
| `rq2_measure.py` | Runs the RQ1 questions (same datasets, prompts and scoring, imported from `../shuyuan_rq1/rq1_eval.py`) on one model, device profile and network. Logs time to first token, total time and extra device energy per request. |
| `rq2.py` | Reads the CSVs and writes `<out>.md` (tables + assumptions) and four charts (`_total_s`, `_ttft_s`, `_device_wh`, `_carbon_g`). |
| `check_power.py` | Lists the power sensors LibreHardwareMonitor reports. |
| `run_local.bat`, `run_docker.bat`, `run_cloud.bat` | The Windows runs behind the results below. |
| `results/rq2_all.md` | Final tables. `rq2_all_cloud_upper.md` is the same with an upper-bound cloud energy. |
| `results/raw/` | One CSV per run, one row per request. |
| `results/discarded/` | Runs we threw away and why (see below). |

Reproduce the tables: `python rq2.py "results/raw/*.csv" --out results/rq2_all`

## Setup

One Windows laptop: i9-14900HX, RTX 4060 Laptop GPU (8 GB), 32 GB RAM, Ollama, default 4-bit models. 20 questions per task (80 requests) per configuration, temperature 0.

- Local models: Llama 3.2 3B, Qwen3 1.7B with thinking off (`"think": false`; Ollama ignores `/no_think`).
- Cloud: gpt-oss-120b on Groq, streamed directly (not through the gateway) to get time to first token.
- Device profiles: `gpu` (native), `cpu` (native, `num_gpu=0`), `docker-full` (Ollama in Docker, CPU, no limits), `docker-2cpu` (`--cpus 2 --memory 4g`, `num_thread=2`) as a stand-in for a weaker device.
- Networks (cloud): home Wi-Fi and a phone hotspot.

## How energy is measured

A background thread samples power every 0.2 s: CPU package power from LibreHardwareMonitor (run as admin, Options > Remote Web Server on, port 8085) and GPU board power from `nvidia-smi -lms 200`. Before each run the script warms the model up, waits 20 s (60 s in Docker), and averages idle power over 30 s. Extra energy of a request = energy over the request minus idle power x its duration.

- Busy mode (`--gap 0`, shown as `/busy`): requests back to back, the marginal cost on an active device. All headline numbers use it.
- Isolated mode (`--gap 10`, `/isolated`): a 10 s pause after each request is counted too, because the GPU takes 5 to 8 s to wind down. This is the cost of a single request on an idle device.
- A run stops if idle power is above `--max-idle` (30 W; 40 W with Docker Desktop, whose VM adds a few watts).

Kepler (named in the proposal) needs Linux RAPL/eBPF and does not run on Windows or WSL2. `rq2_measure.py` also supports `rapl` (Linux), `powermetrics` (Mac), `battery` (Windows, unplugged) and `tegrastats` (Jetson).

## Results (busy mode)

| | Llama yes/no | Llama math | Qwen yes/no | Qwen math |
|---|---|---|---|---|
| Total time, native GPU | 0.10 s | 1.4 s | 0.07 s | 0.95 s |
| Total time, native CPU | 0.69 s | 5.6 s | 0.46 s | 3.6 s |
| Total time, Docker no limit | 0.86 s | 6.3 s | 0.59 s | 3.8 s |
| Total time, Docker 2 CPUs | 2.6 s | 12.1 s | 1.7 s | 5.7 s |
| Extra energy, native GPU | 0.0008 Wh | 0.052 Wh | 0.0007 Wh | 0.033 Wh |
| Extra energy, native CPU | 0.018 Wh | 0.097 Wh | 0.012 Wh | 0.064 Wh |
| Extra energy, Docker no limit | 0.023 Wh | 0.115 Wh | 0.014 Wh | 0.063 Wh |
| Extra energy, Docker 2 CPUs | 0.034 Wh | 0.197 Wh | 0.022 Wh | 0.102 Wh |

Cloud (gpt-oss-120b), total time: yes/no 0.42 s and math 0.78 s on Wi-Fi; 0.70 s and 1.01 s on the hotspot. Round-trip time 12 ms on Wi-Fi, 25 ms on the hotspot; time to first token 0.19-0.27 s vs 0.41-0.46 s.

- The GPU beats the cloud on latency for short tasks and uses the least energy.
- Docker without limits costs 10-25% more time and energy than native CPU.
- The 2-CPU container draws less power but runs 1.6-4x longer, so each request uses up to twice the energy of native CPU.
- Accuracy is the same within 0.05 across profiles.
- The hotspot adds 0.2-0.3 s to every cloud request, mostly before the first token.

## Carbon

C = E x CI (proposal, eq. 1). Local: measured extra device energy x the Minnesota grid. Cloud: estimated data-center energy x the U.S. average grid, plus the device's own energy while waiting (negligible).

| Assumption | Value | Flag |
|---|---|---|
| Edge grid | 420 gCO2e/kWh, EPA eGRID2023 rev. 2, MROW subregion (926.6 lb/MWh) | `--ci-edge` |
| Data-center grid | 350 gCO2e/kWh, eGRID2023 U.S. total (770.9 lb/MWh); Groq's region is not published | `--ci-dc` |
| Cloud energy, low | 0.24 Wh per prompt (Google, median Gemini text prompt) | `--cloud-wh` |
| Cloud energy, upper | 83.1 Wh per 1000 output tokens (gpt-oss-120b on 8x A100, one query at a time, [Hugging Face](https://huggingface.co/blog/sasha/gpt-oss-energy)) | `--cloud-wh-per-1k-tokens 83.1` |

Per request: local 0.0003 g (GPU, short tasks) to 0.08 g (2-CPU container, math); cloud 0.084 g with the low estimate, 2.3-9.9 g with the upper bound. Network transfer energy and embodied carbon are not included.

## Discarded runs

- `*_high_idle.csv`: idle power was 47-59 W because something else was using the machine. Rerun with idle 23-25 W; `--max-idle` was added after this.
- `rq2_llama_docker2cpu_busy_slow.csv`: Ollama used its default thread count in the 2-CPU container and decoded at 0.36 tokens/s instead of about 14.5. Rerun with `--threads 2`.
