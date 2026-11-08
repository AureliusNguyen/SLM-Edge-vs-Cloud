"""RQ1 rerun that talks to Ollama directly instead of through the gateway.

Ollama ignores the " /no_think" suffix, so the gateway runs of Qwen3 still reasoned
for hundreds of hidden tokens. Here thinking is switched off with Ollama's "think": false.
Same questions, prompts, scoring and CSV columns as rq1_eval.py, so rq1_analysis.py reads the output.

    python rq1_direct.py --model qwen3:1.7b --label qwen --no-think -n 100 --cpu-only --csv qwen_nothink.csv
"""

import argparse
import csv
import json
import re
import time
import urllib.request

import rq1_eval as run_eval


def ask(args, task, prompt):
    options = {"temperature": 0, "num_predict": args.max_tokens}
    if args.cpu_only:
        options["num_gpu"] = 0
    body = {"model": args.model, "messages": run_eval.messages(task, prompt), "stream": False,
            "options": options, "logprobs": True, "keep_alive": "30m"}
    if args.no_think:
        body["think"] = False
    elif args.think:
        body["think"] = True
    request = urllib.request.Request(args.ollama + "/api/chat", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
    start = time.time()
    with urllib.request.urlopen(request, timeout=600) as r:
        data = json.load(r)
    seconds = time.time() - start
    reply = re.sub(r"<think>.*?</think>", "", data["message"].get("content") or "", flags=re.S).strip()
    if data.get("done_reason") == "length":
        reply += "\n[cut off: hit max_tokens before finishing]"
    values = [t.get("logprob") for t in data.get("logprobs") or [] if t.get("logprob") is not None]
    logprob = sum(values) / len(values) if values else None
    return reply, seconds, logprob, data.get("eval_count")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ollama", default="http://127.0.0.1:11434")
    p.add_argument("--model", default="qwen3:1.7b")
    p.add_argument("--label", default="qwen")
    p.add_argument("--no-think", action="store_true", help='send "think": false')
    p.add_argument("--think", action="store_true", help='send "think": true (reasoning on, thoughts dropped from the reply)')
    p.add_argument("--cpu-only", action="store_true", help="keep the model off the GPU, like the original RQ1 runs")
    p.add_argument("-n", type=int, default=100)
    p.add_argument("--tasks", default=",".join(run_eval.TASKS))
    p.add_argument("--max-tokens", type=int, default=4096)
    p.add_argument("--csv", required=True)
    args = p.parse_args()

    items = run_eval.seeded(args.n, args.tasks.split(","))
    ask(args, "yesno", "Passage: The sky is blue.\nQuestion: is the sky blue?")  # load the model first
    fields = ["run", "task", "tier", "forced", "score", "verdict", "seconds", "mean_logprob",
              "gold", "reply", "question", "reason", "output_tokens"]
    totals = {}
    with open(args.csv, "w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        for i, (task, question, prompt, gold) in enumerate(items, 1):
            reply, seconds, logprob, tokens = ask(args, task, prompt)
            s, label = run_eval.verdict(task, reply, gold)
            writer.writerow({"run": args.label, "task": task, "tier": "local", "forced": "local", "score": s,
                             "verdict": label, "seconds": round(seconds, 2),
                             "mean_logprob": None if logprob is None else round(logprob, 4),
                             "gold": run_eval.show_gold(gold), "reply": reply, "question": question,
                             "reason": "direct to Ollama" + (", think off" if args.no_think else ", think on" if args.think else ""),
                             "output_tokens": tokens})
            out.flush()
            totals.setdefault(task, []).append(s)
            print(f"{i:4}/{len(items)}  {task:8} {label[:12]:12} {seconds:6.2f}s  tokens={tokens}")
    print()
    for task, scores in totals.items():
        errors = sum(s is None for s in scores)
        print(f"{task:8} score {sum(s or 0 for s in scores) / len(scores):.2f} over {len(scores)}, {errors} format errors")
    print(f"wrote {args.csv}")


if __name__ == "__main__":
    main()
