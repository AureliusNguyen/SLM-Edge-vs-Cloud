# RQ1: local SLMs vs cloud LLM
s own confidence tell us when to send a request to the cloud?

Models: Llama 3.2 3B and Qwen3 1.7B in Ollama (laptop CPU), gpt-oss-120b on Groq.
Datasets: BoolQ (yes/no), AG News (classify), SQuAD (extract), GSM8K (math).

## Files

```
rq1_eval.py        sends the questions through the gateway, scores each answer, writes a CSV
rq1_analysis.py    turns the CSVs into the tables in results/rq1.md and the chart rq1.png
results/           llama.csv, qwen.csv, cloud.csv, rq1.md, rq1.png, figures/
```

Each CSV row is one question: run, task, tier, score, verdict, seconds, mean_logprob, gold, reply, question.

## Scoring

- yesno, classify, math: exact match (math reads the number after `Answer:`)
- extract: best token F1 against the SQuAD answers
- A reply in the wrong format counts as 0 and is marked `FORMAT ERROR`
- Confidence = mean token log-prob of the local reply

## Running it

Needs the gateway (`gateway/`), Ollama, Python 3 and a Groq key in `.env`.

```sh
ollama pull llama3.2:3b
ollama pull qwen3:1.7b

cd gateway && env $(cat ../.env) go run . -local-model llama3.2:3b

python rq1_eval.py --all -n 100 --force local --label llama --csv llama.csv
python rq1_eval.py --all -n 100 --force cloud --label cloud --csv cloud.csv
# restart the gateway with -local-model qwen3:1.7b, then:
python rq1_eval.py --all -n 100 --force local --no-think --label qwen --csv qwen.csv

python rq1_analysis.py llama.csv qwen.csv cloud.csv --out rq1
```

`--no-think` adds `/no_think` so Qwen3 answers without reasoning first. Questions are
downloaded once into `dataset_cache/`. The same `-n` always gives the same questions,
and a smaller `-n` gives a subset of a larger one.

On my laptop (GeForce MX250) Ollama crashed on every request when it tried the GPU, so
I ran CPU-only copies of both models:

```sh
printf 'FROM llama3.2:3b\nPARAMETER num_gpu 0\n' > Modelfile && ollama create llama3.2-cpu -f Modelfile
```

## Results

Llama and cloud: 100 questions per task. Qwen: 30 per task and 5 for math (time ran out).
Median seconds per question in brackets.

| task | llama 3.2 3B | qwen3 1.7B | cloud |
|---|---|---|---|
| yesno (acc.) | 0.78 (4.0 s) | 0.77 (18 s) | 0.94 (0.5 s) |
| classify (acc.) | 0.55 (1.8 s) | 0.87 (16 s) | 0.75 (0.4 s) |
| extract (F1) | 0.83 (1.8 s) | 0.51 (13 s) | 0.88 (0.5 s) |
| math (acc.) | 0.73 (18 s) | 0.60 (70 s) | 0.97 (0.7 s) |

Cascade with llama: keep the local answer when its confidence is above a threshold,
otherwise use the cloud answer. Threshold = keep as much local as possible while staying
within 0.02 of always-cloud.

| task | AUROC | kept local | cascade | always local | always cloud |
|---|---|---|---|---|---|
| yesno | 0.72 | 52% | 0.92 | 0.78 | 0.94 |
| classify | 0.66 | 40% | 0.73 | 0.55 | 0.75 |
| extract | 0.54 | 30% | 0.86 | 0.83 | 0.88 |
| math | 0.83 | 45% | 0.95 | 0.73 | 0.97 |
