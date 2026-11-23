"""Summarize the live injected-delay runs (gateway -cloud-delay, -power lhm,nvidia).

Each run: rq1_eval.py --all -n 25 through the gateway (Llama 3.2 3B on the GPU, Groq cloud),
one policy and one cloud delay. Reads rq3/results/delay/live_<run>.csv (answers, client time)
and gateway_<run>.jsonl (route, measured device energy). Retried 429 answers are dropped from
the gateway log; only the request that answered counts.

    python rq3/delay_summary.py
"""
import csv
import glob
import json
import os
import statistics

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "delay")


def main():
    lines = ["# Live runs with an injected cloud delay", "",
             "Gateway on the GPU laptop (Llama 3.2 3B local, gpt-oss-120b on Groq over Wi-Fi), 25 questions per task, "
             "`-cloud-delay` added to every cloud call. Questions Groq still rate-limited after six tries are left out (count in brackets). Score uses F1 for extract. Device energy is measured in the "
             "gateway (LibreHardwareMonitor + nvidia-smi, above idle); carbon adds 0.24 Wh per cloud call.", "",
             "| policy | cloud delay | n | score | answered locally | escalated | median s | mean s | device Wh/req | gCO2e/req |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for path in sorted(glob.glob(os.path.join(HERE, "live_*.csv")), key=lambda p: ("300" in p, "cascade" in p)):
        run = os.path.basename(path)[5:-4]
        rows = list(csv.DictReader(open(path, encoding="utf-8")))
        failed = sum(r["reason"].startswith("429") for r in rows)
        rows = [r for r in rows if not r["reason"].startswith("429")]  # still rate-limited after 6 tries
        log = [json.loads(l) for l in open(os.path.join(HERE, f"gateway_{run}.jsonl"), encoding="utf-8")]
        ok = [e for e in log if e["status"] == 200]
        policy, delay = run.rsplit("_", 1)
        score = statistics.mean(float(r["score"]) if r["score"] not in ("", "None") else 0.0 for r in rows)
        secs = [float(r["seconds"]) for r in rows]
        local = sum(r["tier"] == "local" for r in rows) / len(rows)
        esc = sum(len(e["tiers_called"] or []) == 2 for e in ok) / len(ok)
        wh = statistics.mean(e["energy_j"] or 0 for e in ok) / 3600
        g = statistics.mean(e["gco2e_measured"] or 0 for e in ok)
        lines.append(f"| {policy.replace('_', '+')} | {delay} | {len(rows)}{f' ({failed} rate-limited)' if failed else ''} | {score:.3f} | {local:.0%} | {esc:.0%} | "
                     f"{statistics.median(secs):.2f} | {statistics.mean(secs):.2f} | {wh:.4f} | {g:.4f} |")
    out = os.path.join(HERE, "delay_summary.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
