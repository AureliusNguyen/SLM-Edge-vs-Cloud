import argparse
import collections
import csv
import json
import os
import re
import string
import textwrap
import time
import urllib.error
import urllib.request

ROWS = "https://datasets-server.huggingface.co/rows?dataset={}&config={}&split={}&offset={}&length={}"
TASKS = ("yesno", "classify", "extract", "math")
AG_LABELS = ["World", "Sports", "Business", "Sci/Tech"]
SYSTEM = {
    "yesno": "Answer with only yes or no.",
    "classify": "Classify the news article into one of these topics: World, Sports, Business, Sci/Tech. "
    "Answer with only the topic.",
    "extract": "Answer the question with a short span copied exactly from the passage. Reply with only the answer.",
    "math": "Solve the problem. End your reply with 'Answer: <number>'.",
}


CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset_cache")


def fetch(dataset, config, split, offset, length):
    name = f"{dataset.replace('/', '_')}_{config}_{split}_{offset}_{length}.json"
    path = os.path.join(CACHE, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(ROWS.format(dataset, config, split, offset, length), timeout=30) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 5:
                raise
            wait = 10 * 2 ** attempt
            print(f"HuggingFace rate limit, retrying in {wait}s ...")
            time.sleep(wait)
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def load(dataset, config, split, n):
    total = fetch(dataset, config, split, 0, 1)["num_rows_total"]
    chunks = min(10, n)
    rows = []
    for i in range(chunks):
        size = n // chunks + (i < n % chunks)
        offset = i * total // chunks
        rows += [row["row"] for row in fetch(dataset, config, split, offset, size)["rows"]]
    return rows


def messages(task, question, no_think=False):
    system = [{"role": "system", "content": SYSTEM[task]}] if task in SYSTEM else []
    return system + [{"role": "user", "content": question + (" /no_think" if no_think else "")}]


def mean_logprob(choice):
    tokens = (choice.get("logprobs") or {}).get("content") or []
    values = [t["logprob"] for t in tokens if t.get("logprob") is not None]
    return sum(values) / len(values) if values else None


def seeded(n, tasks):
    items = []
    if "yesno" in tasks:
        for row in load("google/boolq", "default", "validation", n):
            question = row["question"] + "?"
            items.append(("yesno", question, f"Passage: {row['passage']}\nQuestion: {question}", "yes" if row["answer"] else "no"))
    if "classify" in tasks:
        for row in load("fancyzhx/ag_news", "default", "test", n):
            items.append(("classify", row["text"], f"Article: {row['text']}", AG_LABELS[row["label"]]))
    if "extract" in tasks:
        for row in load("rajpurkar/squad", "plain_text", "validation", n):
            prompt = f"Passage: {row['context']}\nQuestion: {row['question']}"
            items.append(("extract", row["question"], prompt, row["answers"]["text"]))
    if "math" in tasks:
        for row in load("openai/gsm8k", "main", "test", n):
            gold = row["answer"].split("####")[-1].strip().replace(",", "")
            items.append(("math", row["question"], row["question"], gold))
    return items


class FormatError(ValueError):
    pass


TOPIC_WORDS = [
    ("Sci/Tech", r"sci\s*[/&-]?\s*tech|science|technology"),
    ("Business", r"business|econom|financ"),
    ("Sports", r"sports?"),
    ("World", r"world|politics|international"),
]


def topic(reply):
    found = []
    for label, pattern in TOPIC_WORDS:
        m = re.search(r"\b(?:" + pattern + r")", reply.lower())
        if m:
            found.append((m.start(), label))
    if not found:
        raise FormatError("no topic in reply")
    return min(found)[1]


def normalize(text):
    text = "".join(c for c in text.lower() if c not in string.punctuation)
    return " ".join(re.sub(r"\b(a|an|the)\b", " ", text).split())


def f1(prediction, gold):
    pred, ref = normalize(prediction).split(), normalize(gold).split()
    common = sum((collections.Counter(pred) & collections.Counter(ref)).values())
    if common == 0:
        return 0.0
    precision, recall = common / len(pred), common / len(ref)
    return 2 * precision * recall / (precision + recall)


def score(task, reply, gold):
    if task == "yesno":
        word = re.search(r"\b(yes|no)\b", reply.lower())
        if word is None:
            raise FormatError("no yes/no in reply")
        return float(word.group(1) == gold)
    if task == "classify":
        return float(topic(reply) == gold)
    if task == "extract":
        answer = reply.strip().split("\n")[0]
        if not normalize(answer):
            raise FormatError("empty answer")
        return max(f1(answer, g) for g in gold)
    if "Answer:" not in reply:
        raise FormatError("no 'Answer:' line")
    number = re.search(r"-?\d[\d,]*\.?\d*", reply.rsplit("Answer:", 1)[1])
    if number is None:
        raise FormatError("no number after 'Answer:'")
    return float(float(number.group().replace(",", "").rstrip(".")) == float(gold))


def verdict(task, reply, gold):
    try:
        s = score(task, reply, gold)
    except FormatError as e:
        return None, f"FORMAT ERROR ({e})"
    if s == 1:
        return s, "right"
    if s == 0:
        return s, "WRONG"
    return s, f"F1={s:.2f}"


def show_gold(gold):
    return " | ".join(gold) if isinstance(gold, list) else gold


def ask(gateway, task, prompt, force, no_think=False, retries=6):
    for attempt in range(retries):
        result = ask_once(gateway, task, prompt, force, no_think)
        if not result[1].startswith("429 ") or attempt == retries - 1:
            return result
        time.sleep(min(60, 5 * 2 ** attempt))


def ask_once(gateway, task, prompt, force, no_think):
    headers = {"Content-Type": "application/json", "X-Task-Type": task}
    if force:
        headers["X-Force-Tier"] = force
    body = json.dumps({"model": "auto", "messages": messages(task, prompt, no_think), "temperature": 0,
                       "max_tokens": 4096, "logprobs": True}).encode()
    request = urllib.request.Request(gateway + "/v1/chat/completions", body, headers)
    start = time.time()
    try:
        with urllib.request.urlopen(request, timeout=600) as r:
            choice = json.load(r)["choices"][0]
            reply = choice["message"]["content"] or ""
            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.S).strip()
            if choice.get("finish_reason") == "length":
                reply += "\n[cut off: hit max_tokens before finishing]"
            return r.headers["X-Route"], r.headers["X-Route-Reason"], reply, time.time() - start, mean_logprob(choice)
    except urllib.error.HTTPError as e:
        return e.headers.get("X-Route") or "-", f"{e.code} {e.read().decode().strip()}", "", time.time() - start, None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return "-", f"request failed: {e}", "", time.time() - start, None


def run_all(args, items):
    rows = []
    out = writer = None
    if args.csv:
        out = open(args.csv, "w", newline="", encoding="utf-8")
    for i, (task, question, prompt, gold) in enumerate(items, 1):
        tier, reason, reply, seconds, logprob = ask(args.gateway, task, prompt, args.force, args.no_think)
        s, label = verdict(task, reply, gold)
        rows.append({"run": args.label, "task": task, "tier": tier, "forced": args.force or "", "score": s,
                     "verdict": label, "seconds": round(seconds, 2),
                     "mean_logprob": None if logprob is None else round(logprob, 4),
                     "gold": show_gold(gold), "reply": reply.strip(), "question": question, "reason": reason})
        if out:
            if writer is None:
                writer = csv.DictWriter(out, fieldnames=list(rows[0]))
                writer.writeheader()
            writer.writerow(rows[-1])
            out.flush()
        print(f"{i:4}/{len(items)}  {task:8}  -> {tier:5}  {label[:12]:12}  {seconds:6.1f}s  gold={show_gold(gold)[:20]:<20}  {reason}")

    print()
    for task in TASKS:
        mine = [r for r in rows if r["task"] == task]
        if not mine:
            continue
        scored = [r["score"] for r in mine if r["score"] is not None]
        mean = sum(scored) / len(mine)
        errors = len(mine) - len(scored)
        metric = "mean F1" if task == "extract" else "accuracy"
        print(f"{task:8}  {metric} {mean:.2f} over {len(mine)}, {errors} format errors")

    if out:
        out.close()
        print(f"\nwrote {len(rows)} rows to {args.csv}")


def interactive(args, items):
    menu = "\n".join(
        textwrap.fill(f"{i}. [{task}] {' '.join(question.split())}"[:300], width=100, initial_indent="  ", subsequent_indent="     ")
        for i, (task, question, _, _) in enumerate(items, 1)
    )
    print(f"Pick a question, type your own, m for this menu, or q to quit:\n{menu}")
    while True:
        try:
            line = input("\n> ").strip()
        except EOFError:
            return
        if line in ("q", "quit", "exit"):
            return
        if line == "m":
            print(menu)
            continue
        if not line:
            continue
        gold = None
        if line.isdigit() and 1 <= int(line) <= len(items):
            task, _, prompt, gold = items[int(line) - 1]
            first, *rest = prompt.split("\n")
            print("\n" + textwrap.fill(" ".join(first.split()), width=100))
            for extra in rest:
                print(extra)
        else:
            kind = input("Task type: [y]esno, [c]lassify, [e]xtract, [m]ath, or Enter for other: ").strip().lower()[:1]
            task = {"y": "yesno", "c": "classify", "e": "extract", "m": "math"}.get(kind, "other")
            prompt = line
        tier, reason, reply, seconds, logprob = ask(args.gateway, task, prompt, args.force, args.no_think)
        confidence = "" if logprob is None else f", mean log-prob {logprob:.3f}"
        print(f"\n-> {tier} in {seconds:.1f}s{confidence}: {reason}\n\n{reply.strip()}")
        if gold is not None:
            print(f"\ngold: {show_gold(gold)}  ({verdict(task, reply, gold)[1]})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default="http://localhost:8080")
    parser.add_argument("--force", choices=["local", "cloud"])
    parser.add_argument("--all", action="store_true", help="run every seeded question and print a score")
    parser.add_argument("-n", type=int, default=3, help="seeded questions per task")
    parser.add_argument("--tasks", default=",".join(TASKS), help="comma-separated subset of " + ",".join(TASKS))
    parser.add_argument("--csv", help="with --all, also write one row per question to this CSV file")
    parser.add_argument("--label", default="", help="name of this run in the CSV, e.g. llama, qwen, cloud")
    parser.add_argument("--no-think", action="store_true", help="append /no_think so Qwen3 skips its reasoning")
    args = parser.parse_args()
    tasks = args.tasks.split(",")
    unknown = set(tasks) - set(TASKS)
    if unknown:
        parser.error(f"unknown task(s): {', '.join(sorted(unknown))}")
    items = seeded(args.n, tasks)
    if args.all:
        run_all(args, items)
    else:
        interactive(args, items)


if __name__ == "__main__":
    main()
