"""Agreement between two judge runs of judge_extract.py.

    python judge_agree.py judge_gptoss.csv judge_qwen.csv --out judge_agree.md
"""
import argparse
import csv


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        return {(r["run"], r["question"], r["reply"]): r for r in csv.DictReader(f)}


p = argparse.ArgumentParser()
p.add_argument("a")
p.add_argument("b")
p.add_argument("--out", default="judge_agree.md")
args = p.parse_args()
a, b = load(args.a), load(args.b)
keys = [k for k in a if k in b]
lines = [f"# Judge agreement: {args.a} vs {args.b}", "",
         "| model | n | judge A correct | judge B correct | both correct | agree | Cohen's kappa |", "|---|---|---|---|---|---|---|"]
for run in dict.fromkeys(k[0] for k in keys):
    ks = [k for k in keys if k[0] == run]
    xa = [a[k]["judge"] == "CORRECT" for k in ks]
    xb = [b[k]["judge"] == "CORRECT" for k in ks]
    n = len(ks)
    agree = sum(x == y for x, y in zip(xa, xb)) / n
    pa, pb = sum(xa) / n, sum(xb) / n
    chance = pa * pb + (1 - pa) * (1 - pb)
    kappa = (agree - chance) / (1 - chance) if chance < 1 else 1.0
    lines.append(f"| {run} | {n} | {pa:.2f} | {pb:.2f} | {sum(x and y for x, y in zip(xa, xb)) / n:.2f} | {agree:.2f} | {kappa:.2f} |")
with open(args.out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))
