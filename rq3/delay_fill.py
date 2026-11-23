"""Re-ask the questions of a live delay run that are missing or were still rate-limited (HTTP 429)
after rq1_eval.py's retries, slowly, through the same gateway, and rewrite the CSV in question order.

    python rq3/delay_fill.py rq3/results/delay/live_rule_cascade_300ms.csv --gateway http://localhost:8081
"""
import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shuyuan_rq1"))
import rq1_eval as ev  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--gateway", default="http://localhost:8081")
    p.add_argument("-n", type=int, default=25)
    p.add_argument("--gap", type=float, default=12, help="seconds between requests (Groq: 8k tokens/min)")
    a = p.parse_args()
    rows = list(csv.DictReader(open(a.csv, encoding="utf-8")))
    label = rows[0]["run"]
    have = {(r["task"], r["question"]): r for r in rows if not r["reason"].startswith("429")}
    out = []
    for task, question, prompt, gold in ev.seeded(a.n, list(ev.TASKS)):
        if (task, question) in have:
            out.append(have[(task, question)])
            continue
        tier, reason, reply, seconds, logprob = ev.ask(a.gateway, task, prompt, None)
        s, verdict = ev.verdict(task, reply, gold)
        print(f"{task:8} -> {tier:5} {verdict[:12]:12} {seconds:5.1f}s {reason[:60]}", flush=True)
        out.append({"run": label, "task": task, "tier": tier, "forced": "", "score": s, "verdict": verdict,
                    "seconds": round(seconds, 2), "mean_logprob": None if logprob is None else round(logprob, 4),
                    "gold": ev.show_gold(gold), "reply": reply.strip(), "question": question, "reason": reason})
        time.sleep(a.gap)
    with open(a.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(out)} rows, {sum(r['reason'].startswith('429') for r in out)} still rate-limited")


if __name__ == "__main__":
    main()
