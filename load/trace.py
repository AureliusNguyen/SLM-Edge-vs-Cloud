# Build seeded request traces for the load test, one per rate in RATES.
#
#   python3 load/trace.py                  # Poisson arrivals, uniform task mix
#   python3 load/trace.py bursty           # busy and quiet periods
#   python3 load/trace.py poisson zipf     # skewed task mix
#   python3 load/trace.py fixed            # also: uniform
#
# Every rate replays the same questions in the same order; only the timing changes.
# Questions are the rows right after each RQ1 sample, so none were used to fit thresholds.
import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shuyuan_rq1"))
import rq1_eval

RATES = (0.2, 0.5, 1, 2)
REQUESTS = 200
SEED = 1
DEADLINES = {"yesno": 2, "classify": 2, "extract": 2, "math": 10}
ZIPF_S = 1.0
BURST_PERIOD = 30
BUSY, QUIET = 1.8, 0.2
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traces")

ARRIVALS = ("fixed", "uniform", "poisson", "bursty")
MIXES = ("uniform", "zipf")
DATASETS = {
    "yesno": ("google/boolq", "default", "validation"),
    "classify": ("fancyzhx/ag_news", "default", "test"),
    "extract": ("rajpurkar/squad", "plain_text", "validation"),
    "math": ("openai/gsm8k", "main", "test"),
}
RQ1_CHUNKS = 10
RQ1_CHUNK_SIZE = 10


def prompt_and_gold(task, row):
    if task == "yesno":
        return f"Passage: {row['passage']}\nQuestion: {row['question']}?", "yes" if row["answer"] else "no"
    if task == "classify":
        return f"Article: {row['text']}", rq1_eval.AG_LABELS[row["label"]]
    if task == "extract":
        return f"Passage: {row['context']}\nQuestion: {row['question']}", row["answers"]["text"]
    return row["question"], row["answer"].split("####")[-1].strip().replace(",", "")


def fresh_questions(task, count):
    """RQ1 took 10 evenly spaced chunks of 10 rows; take the rows that follow each chunk."""
    dataset, config, split = DATASETS[task]
    total = rq1_eval.fetch(dataset, config, split, 0, 1)["num_rows_total"]
    per_chunk = -(-count // RQ1_CHUNKS)
    if per_chunk > total // RQ1_CHUNKS - RQ1_CHUNK_SIZE:
        raise SystemExit(f"{task}: {count} fresh questions would overlap the RQ1 sample, lower REQUESTS")
    rows = []
    for i in range(RQ1_CHUNKS):
        offset = i * total // RQ1_CHUNKS + RQ1_CHUNK_SIZE
        rows += [r["row"] for r in rq1_eval.fetch(dataset, config, split, offset, per_chunk)["rows"]]
    return [prompt_and_gold(task, row) for row in rows[:count]]


def task_weights(mix):
    """For zipf, tasks are ranked in rq1_eval.TASKS order, most frequent first."""
    if mix == "uniform":
        return [1.0] * len(rq1_eval.TASKS)
    return [1 / rank**ZIPF_S for rank in range(1, len(rq1_eval.TASKS) + 1)]


def build_requests(mix):
    rng = random.Random(SEED)
    sequence = rng.choices(rq1_eval.TASKS, task_weights(mix), k=REQUESTS)
    pools = {}
    for task, count in collections.Counter(sequence).items():
        pools[task] = fresh_questions(task, count)
        rng.shuffle(pools[task])
    built = []
    for i, task in enumerate(sequence):
        prompt, gold = pools[task].pop()
        built.append({"id": i, "task": task, "prompt": prompt, "gold": gold, "deadline": DEADLINES[task]})
    return built


def arrival_times(arrivals, rate):
    """Seconds after the start of the run at which each request is due.

    bursty alternates busy and quiet periods at BUSY and QUIET times the mean rate,
    drawn by thinning a Poisson process at the busy rate.
    """
    rng = random.Random(SEED)
    times, t = [], 0.0
    while len(times) < REQUESTS:
        if arrivals == "fixed":
            t += 1 / rate
        elif arrivals == "uniform":
            t += rng.uniform(0, 2 / rate)
        elif arrivals == "poisson":
            t += rng.expovariate(rate)
        else:
            t += rng.expovariate(BUSY * rate)
            quiet = int(t // BURST_PERIOD) % 2 == 1
            if quiet and rng.random() > QUIET / BUSY:
                continue
        times.append(round(t, 4))
    return times


def main(arrivals="poisson", mix="uniform"):
    if arrivals not in ARRIVALS or mix not in MIXES:
        raise SystemExit(f"arrivals is one of {', '.join(ARRIVALS)}; mix is one of {', '.join(MIXES)}")
    requests = build_requests(mix)
    os.makedirs(OUT, exist_ok=True)
    for rate in RATES:
        for request, at in zip(requests, arrival_times(arrivals, rate)):
            request["at"] = at
        trace = {"arrivals": arrivals, "rate": rate, "mix": mix, "seed": SEED, "requests": requests}
        path = os.path.join(OUT, f"{arrivals}-{mix}-r{rate:g}-s{SEED}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(trace, f)
        print(f"{path}: {REQUESTS} requests over {requests[-1]['at']:.0f} s")


if __name__ == "__main__":
    main(*sys.argv[1:])
