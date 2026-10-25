"""Send BoolQ (yes/no) and GSM8K (math) questions through the gateway and show
where each one was routed, whether the answer was right, and how long it took.

    python3 demo/demo.py                 # interactive: pick 1-6 or type your own question
    python3 demo/demo.py --all           # run every seeded question and print a score
    python3 demo/demo.py --force local   # always-local baseline (works with both modes)
    python3 demo/demo.py --force cloud   # always-cloud baseline
"""

import argparse
import json
import re
import textwrap
import time
import urllib.error
import urllib.request

ROWS = "https://datasets-server.huggingface.co/rows?dataset={}&config={}&split={}&offset=0&length={}"
SYSTEM = {
    "yesno": "Answer with only yes or no.",
    "math": "Solve the problem. End your reply with 'Answer: <number>'.",
}


def load(dataset, config, split, n):
    with urllib.request.urlopen(ROWS.format(dataset, config, split, n), timeout=30) as r:
        return [row["row"] for row in json.load(r)["rows"]]


def messages(task, question):
    system = [{"role": "system", "content": SYSTEM[task]}] if task in SYSTEM else []
    return system + [{"role": "user", "content": question}]


def seeded(n):
    """Return (task, question, prompt text, gold answer) for n BoolQ and n GSM8K rows."""
    items = []
    for row in load("google/boolq", "default", "validation", n):
        question = row["question"] + "?"
        items.append(("yesno", question, f"Passage: {row['passage']}\nQuestion: {question}", "yes" if row["answer"] else "no"))
    for row in load("openai/gsm8k", "main", "test", n):
        gold = row["answer"].split("####")[-1].strip().replace(",", "")
        items.append(("math", row["question"], row["question"], gold))
    return items


class FormatError(ValueError):
    """The reply does not follow the requested answer format, so it cannot be scored."""


def correct(task, reply, gold):
    if task == "yesno":
        word = re.search(r"\b(yes|no)\b", reply.lower())
        if word is None:
            raise FormatError("no yes/no in reply")
        return word.group(1) == gold
    if "Answer:" not in reply:
        raise FormatError("no 'Answer:' line")
    number = re.search(r"-?\d[\d,]*\.?\d*", reply.rsplit("Answer:", 1)[1])
    if number is None:
        raise FormatError("no number after 'Answer:'")
    return float(number.group().replace(",", "").rstrip(".")) == float(gold)


def verdict(task, reply, gold):
    try:
        return "right" if correct(task, reply, gold) else "WRONG"
    except FormatError as e:
        return f"FORMAT ERROR ({e})"


def ask(gateway, task, prompt, force):
    headers = {"Content-Type": "application/json", "X-Task-Type": task}
    if force:
        headers["X-Force-Tier"] = force
    body = json.dumps({"model": "auto", "messages": messages(task, prompt), "temperature": 0, "max_tokens": 4096}).encode()
    request = urllib.request.Request(gateway + "/v1/chat/completions", body, headers)
    start = time.time()
    try:
        with urllib.request.urlopen(request, timeout=600) as r:
            choice = json.load(r)["choices"][0]
            reply = choice["message"]["content"] or ""
            if choice.get("finish_reason") == "length":
                # Reasoning models (gpt-oss) can spend the whole budget thinking.
                reply += "\n[cut off: hit max_tokens before finishing]"
            return r.headers["X-Route"], r.headers["X-Route-Reason"], reply, time.time() - start
    except urllib.error.HTTPError as e:
        return e.headers.get("X-Route") or "-", e.read().decode().strip(), "", time.time() - start


def run_all(args, items):
    results = []
    for task, _, prompt, gold in items:
        tier, reason, reply, seconds = ask(args.gateway, task, prompt, args.force)
        result = verdict(task, reply, gold)
        results.append(result)
        print(f"{task:5}  -> {tier:5}  {result:5}  {seconds:6.1f}s  gold={gold:<5}  {reason}")
    errors = sum(r.startswith("FORMAT") for r in results)
    print(f"\n{results.count('right')}/{len(items)} correct, {errors} format errors")


def interactive(args, items):
    menu = "\n".join(
        textwrap.fill(f"{i}. [{task}] {' '.join(question.split())}", width=100, initial_indent="  ", subsequent_indent="     ")
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
            print("\n" + textwrap.fill(" ".join(prompt.split("\n")[0].split()), width=100))
            if task == "yesno":
                print(prompt.split("\n")[1])
        else:
            kind = input("Task type: [y]esno, [m]ath, or Enter for other: ").strip().lower()[:1]
            task = {"y": "yesno", "m": "math"}.get(kind, "other")
            prompt = line
        tier, reason, reply, seconds = ask(args.gateway, task, prompt, args.force)
        print(f"\n-> {tier} in {seconds:.1f}s: {reason}\n\n{reply.strip()}")
        if gold is not None:
            print(f"\ngold: {gold}  ({verdict(task, reply, gold)})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default="http://localhost:8080")
    parser.add_argument("--force", choices=["local", "cloud"])
    parser.add_argument("--all", action="store_true", help="run every seeded question and print a score")
    parser.add_argument("-n", type=int, default=3, help="seeded questions per task")
    args = parser.parse_args()
    items = seeded(args.n)
    if args.all:
        run_all(args, items)
    else:
        interactive(args, items)


if __name__ == "__main__":
    main()
