"""LLM-as-a-judge for the extract task (SQuAD), next to token F1.

Token F1 punishes answers that are right but phrased as a full sentence ("The war ended in 1945."
vs gold "1945"). A judge model reads the question, the gold answers and the reply and says
whether the reply is correct (binary, as Masthan Ali et al., E-Energy '26, do for tasks with a
reference answer). Groq retired Llama 3.3 70B, so run_judge.bat uses two judges from different
families, gpt-oss-20b and Qwen3.8 27B, and the summary shows how often they agree. Each may favour
its own family (gpt-oss-120b is the cloud model, Qwen3 1.7B a local one), which two judges expose.

    set GROQ_API_KEY=...
    python judge_extract.py llama.csv qwen_nothink.csv cloud.csv --out judge_extract

Writes <out>.md (summary) and <out>.csv (one row per judged reply). Replies already judged in
<out>.csv are reused, so the script can be stopped and started again.
"""

import argparse
import csv
import glob
import json
import os
import re
import time
import urllib.error
import urllib.request

PROMPT = """You are grading a reading-comprehension answer.
Question: {question}
Reference answer(s): {gold}
Model reply: {reply}

The reply is CORRECT if it gives the same information as one of the reference answers, even if it
is phrased as a full sentence or adds a few harmless words. It is WRONG if it gives a different
answer, misses the key information, or adds a contradicting claim. Reply with only CORRECT or WRONG."""


def judge(args, key, question, gold, reply):
    payload = {"model": args.judge_model, "temperature": 0, "max_tokens": 2000,
               "messages": [{"role": "user", "content": PROMPT.format(question=question, gold=gold, reply=reply)}]}
    if args.reasoning_effort:
        payload["reasoning_effort"] = args.reasoning_effort
    body = json.dumps(payload)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}", "User-Agent": "rq1-judge/1.0"}
    for attempt in range(8):
        request = urllib.request.Request(args.url + "/chat/completions", body.encode(), headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as r:
                text = json.load(r)["choices"][0]["message"]["content"] or ""
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip().strip("*").upper()
            return "CORRECT" if text.startswith("CORRECT") else "WRONG" if text.startswith("WRONG") else "?" + text[:20]
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                raise SystemExit(f"Groq refused the judge model {args.judge_model}: {e.read().decode()[:300]}\n"
                                 "Pick another one from https://console.groq.com/docs/models with --judge-model")
            if e.code not in (429, 500, 502, 503) or attempt == 7:
                raise
            wait = float(e.headers.get("retry-after") or 5 * 2 ** attempt)
            print(f"  rate limited, waiting {wait:.0f}s")
            time.sleep(min(wait, 120))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="+", help="RQ1 CSVs from rq1_eval.py or rq1_direct.py")
    p.add_argument("--out", default="judge_extract")
    p.add_argument("--url", default="https://api.groq.com/openai/v1")
    p.add_argument("--judge-model", default="openai/gpt-oss-20b")
    p.add_argument("--reasoning-effort", help="e.g. low for openai/gpt-oss-20b, none for qwen/qwen3.8-27b")
    p.add_argument("--key-env", default="GROQ_API_KEY")
    p.add_argument("--delay", type=float, default=2.1, help="seconds between calls (Groq free tier: 30 per minute)")
    args = p.parse_args()
    key = os.environ.get(args.key_env)
    if not key:
        raise SystemExit(f"set {args.key_env} first")

    paths = []
    for pattern in args.csv:
        paths += sorted(glob.glob(pattern)) or [pattern]
    done = {}
    if os.path.exists(args.out + ".csv"):
        with open(args.out + ".csv", newline="", encoding="utf-8") as f:
            done = {(r["run"], r["question"], r["reply"]): r for r in csv.DictReader(f)}

    rows = []
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["task"] == "extract":
                    rows.append({"run": r["run"] or os.path.basename(path)[:-4], "question": r["question"],
                                 "gold": r["gold"], "reply": r["reply"], "f1": float(r["score"] or 0)})

    fields = ["run", "question", "gold", "reply", "f1", "judge"]
    with open(args.out + ".csv", "w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        for i, r in enumerate(rows, 1):
            old = done.get((r["run"], r["question"], r["reply"]))
            if old:
                r["judge"] = old["judge"]
            elif not r["reply"].strip():
                r["judge"] = "WRONG"
            else:
                r["judge"] = judge(args, key, r["question"], r["gold"], r["reply"])
                time.sleep(args.delay)
            writer.writerow(r)
            out.flush()
            print(f"{i:4}/{len(rows)}  {r['run']:8} F1={r['f1']:.2f}  judge={r['judge']}")

    lines = ["# Extract task: token F1 vs LLM judge", "",
             f"Judge: {args.judge_model} (temperature 0, reasoning effort {args.reasoning_effort or 'default'}, CORRECT/WRONG against the SQuAD reference answers).", "",
             "| model | n | mean F1 | exact (F1=1) | judge correct | F1<0.5 but judge correct | F1=1 but judge wrong |",
             "|---|---|---|---|---|---|---|"]
    for run in dict.fromkeys(r["run"] for r in rows):
        rs = [r for r in rows if r["run"] == run]
        n = len(rs)
        ok = [r["judge"] == "CORRECT" for r in rs]
        lines.append(f"| {run} | {n} | {sum(r['f1'] for r in rs) / n:.2f} | {sum(r['f1'] == 1 for r in rs) / n:.2f} | "
                     f"{sum(ok) / n:.2f} | {sum(r['f1'] < 0.5 and o for r, o in zip(rs, ok))} | "
                     f"{sum(r['f1'] == 1 and not o for r, o in zip(rs, ok))} |")
    unclear = sum(r["judge"].startswith("?") for r in rows)
    lines += ["", f"Unclear judge replies (counted as wrong): {unclear}.",
              "The last two columns are where F1 and the judge disagree; read a few of them in the CSV to check the judge."]
    with open(args.out + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {args.out}.md and {args.out}.csv")


if __name__ == "__main__":
    main()
