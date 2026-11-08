# RQ1: local SLMs vs cloud LLM


Models: Llama 3.2 3B and Qwen3 1.7B in Ollama (laptop CPU), gpt-oss-120b on Groq.
Datasets: BoolQ (yes/no), AG News (classify), SQuAD (extract), GSM8K (math).

## Files

```
rq1_eval.py        sends the questions through the gateway, scores each answer, writes a CSV
rq1_direct.py      same questions and scoring, but talks to Ollama directly with "think" on or off
rq1_analysis.py    turns the CSVs into the tables in results/rq1.md and the chart rq1.png
judge_extract.py   LLM judge (CORRECT/WRONG) for the extract answers, next to token F1
judge_agree.py     agreement between two judge runs
results/           llama.csv, qwen_nothink.csv, qwen_think.csv, cloud.csv, rq1.md, rq1.png, figures/
results/judge/     judge results and summary
results/old/       the first Qwen run (through the gateway, still thinking; see below)
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
# Qwen3 directly against Ollama, with thinking off and on
python rq1_direct.py --model qwen3:1.7b --label qwen_nothink --no-think -n 100 --cpu-only --csv qwen_nothink.csv
python rq1_direct.py --model qwen3:1.7b --label qwen_think --think -n 100 --csv qwen_think.csv

python rq1_analysis.py llama.csv qwen_nothink.csv qwen_think.csv cloud.csv --out rq1

# LLM judges for extract (Groq key in GROQ_API_KEY)
python judge_extract.py llama.csv cloud.csv qwen_nothink.csv qwen_think.csv --judge-model openai/gpt-oss-20b --reasoning-effort low --out judge_gptoss
python judge_extract.py llama.csv cloud.csv qwen_nothink.csv qwen_think.csv --judge-model qwen/qwen3.8-27b --reasoning-effort none --out judge_qwen
python judge_agree.py judge_gptoss.csv judge_qwen.csv --out judge_agree.md
```

`rq1_eval.py --no-think` adds `/no_think` to the prompt, but Ollama ignores it: the first
Qwen run (now in `results/old/`) still reasoned for hundreds of hidden tokens. Use
`rq1_direct.py`, which sends Ollama's `"think": false` (or `true`). Questions are
downloaded once into `dataset_cache/`. The same `-n` always gives the same questions,
and a smaller `-n` gives a subset of a larger one.

On my laptop (GeForce MX250) Ollama crashed on every request when it tried the GPU, so
I ran CPU-only copies of both models:

```sh
printf 'FROM llama3.2:3b\nPARAMETER num_gpu 0\n' > Modelfile && ollama create llama3.2-cpu -f Modelfile
```

## Results

100 questions per task for every model. Median seconds per question in brackets. Llama and
cloud went through the gateway on a laptop CPU; both Qwen runs went directly to Ollama on a
desktop (think off on CPU, think on on the GPU), so their times are not comparable with Llama's.

| task | llama 3.2 3B | qwen3 1.7B, think off | qwen3 1.7B, think on | cloud |
|---|---|---|---|---|
| yesno (acc.) | 0.78 (4.0 s) | 0.78 (0.5 s) | 0.85 (4.6 s) | 0.94 (0.5 s) |
| classify (acc.) | 0.55 (1.8 s) | 0.36 (0.3 s) | 0.78 (5.7 s) | 0.75 (0.4 s) |
| extract (F1) | 0.83 (1.8 s) | 0.56 (0.5 s) | 0.44 (4.2 s) | 0.88 (0.5 s) |
| math (acc.) | 0.73 (18 s) | 0.22 (3.5 s) | 0.65 (22 s) | 0.97 (0.7 s) |

- Thinking is what makes Qwen good at classify. Without it Qwen calls 32 of 100 Sci/Tech
  articles "World". With it Qwen writes a median 214 tokens per classify answer instead of 2.
- Many Qwen math misses are format errors, not wrong sums: 66 (think off) and 29 (think on)
  replies copy `Answer: <number>` literally or end with `\boxed{}`.

Extract scored by LLM judges (`results/judge/`). Token F1 punishes right answers written as a
sentence, which is how Qwen usually answers. Two judges from different model families graded
each reply against the SQuAD answers:

| extract | F1 | judge gpt-oss-20b | judge qwen3.8-27b | judges agree |
|---|---|---|---|---|
| llama | 0.83 | 0.93 | 0.91 | 98% |
| qwen, think off | 0.55 | 0.95 | 0.93 | 98% |
| qwen, think on | 0.44 | 0.96 | 0.96 | 98% |
| cloud | 0.88 | 1.00 | 0.99 | 99% |

The judges are lenient ("MSPs" accepted for "a small number of MSPs"); spot-check before
quoting. yes/no, classify and math keep 0/1 scoring since each has one right answer.

Cascade with llama: keep the local answer when its confidence is above a threshold,
otherwise use the cloud answer. Threshold = keep as much local as possible while staying
within 0.02 of always-cloud. Full tables, including both Qwen runs, are in `results/rq1.md`.

| task | AUROC | kept local | cascade | always local | always cloud |
|---|---|---|---|---|---|
| yesno | 0.72 | 52% | 0.92 | 0.78 | 0.94 |
| classify | 0.66 | 40% | 0.73 | 0.55 | 0.75 |
| extract | 0.54 | 30% | 0.86 | 0.83 | 0.88 |
| math | 0.83 | 45% | 0.95 | 0.73 | 0.97 |

The charts in `results/figures/` were made from the first Qwen run and still show its numbers.
