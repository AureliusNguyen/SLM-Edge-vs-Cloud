import argparse
import csv
import statistics
from collections import defaultdict

TASKS = ("yesno", "classify", "extract", "math")
GOOD = 0.5


def read(paths):
    runs = {}
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        name = rows[0].get("run") or path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].removesuffix(".csv")
        for r in rows:
            r["score"] = float(r["score"]) if r["score"] not in ("", "None") else 0.0
            r["format_error"] = r["verdict"].startswith("FORMAT")
            r["seconds"] = float(r["seconds"])
            lp = r.get("mean_logprob", "")
            r["mean_logprob"] = float(lp) if lp not in ("", "None") else None
        runs[name] = rows
    return runs


def quality_table(runs):
    lines = ["| task | metric | " + " | ".join(runs) + " |", "|---|---|" + "---|" * len(runs)]
    for task in TASKS:
        cells = []
        for rows in runs.values():
            mine = [r for r in rows if r["task"] == task]
            if not mine:
                cells.append("-")
                continue
            mean = statistics.mean(r["score"] for r in mine)
            errors = sum(r["format_error"] for r in mine)
            median = statistics.median(r["seconds"] for r in mine)
            cells.append(f"{mean:.3f} (n={len(mine)}, {errors} fmt err, {median:.1f}s)")
        if any(c != "-" for c in cells):
            metric = "mean F1" if task == "extract" else "accuracy"
            lines.append(f"| {task} | {metric} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def auroc(pairs):
    pos = [c for c, ok in pairs if ok]
    neg = [c for c, ok in pairs if not ok]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def cloud_run(runs):
    for name, rows in runs.items():
        if name == "cloud" or all(r["tier"] == "cloud" for r in rows):
            return name
    return None


def confidence_section(runs, cloud):
    cloud_score = {}
    if cloud:
        cloud_score = {(r["task"], r["question"]): r["score"] for r in runs[cloud]}
    out = []
    for name, rows in runs.items():
        if name == cloud:
            continue
        with_lp = [r for r in rows if r["mean_logprob"] is not None]
        if not with_lp:
            out.append(f"### {name}\n\nNo log-probs in this run (the backend did not return them).\n")
            continue
        out.append(f"### {name}\n")
        out.append("| task | AUROC | threshold | kept local | local acc. on kept | cascade score | always-local | always-cloud |")
        out.append("|---|---|---|---|---|---|---|---|")
        for task in TASKS:
            mine = [r for r in with_lp if r["task"] == task and (r["task"], r["question"]) in cloud_score]
            if not mine:
                mine_nocloud = [r for r in with_lp if r["task"] == task]
                if mine_nocloud:
                    a = auroc([(r["mean_logprob"], r["score"] >= GOOD) for r in mine_nocloud])
                    out.append(f"| {task} | {fmt(a)} | - | - | - | (no cloud run to compare) | - | - |")
                continue
            a = auroc([(r["mean_logprob"], r["score"] >= GOOD) for r in mine])
            local_mean = statistics.mean(r["score"] for r in mine)
            cloud_mean = statistics.mean(cloud_score[(r["task"], r["question"])] for r in mine)
            best = best_threshold(mine, cloud_score, cloud_mean)
            if best is None:
                out.append(f"| {task} | {fmt(a)} | always cloud | 0% | - | {cloud_mean:.3f} | {local_mean:.3f} | {cloud_mean:.3f} |")
                continue
            t, kept, kept_acc, cascade = best
            out.append(f"| {task} | {fmt(a)} | {t:.3f} | {kept:.0%} | {kept_acc:.3f} | {cascade:.3f} | {local_mean:.3f} | {cloud_mean:.3f} |")
        out.append("")
    out.append(
        "Threshold rule: the lowest log-prob threshold (keeping the most requests local) whose cascade "
        "score stays within 0.02 of always-cloud. AUROC 0.5 means the confidence says nothing about "
        f"correctness, 1.0 means it separates right from wrong perfectly. For extract, F1 >= {GOOD} counts as right."
    )
    return "\n".join(out)


def best_threshold(rows, cloud_score, cloud_mean, tolerance=0.02):
    best = None
    for t in sorted({r["mean_logprob"] for r in rows}):
        kept = [r for r in rows if r["mean_logprob"] >= t]
        cascade = statistics.mean(
            r["score"] if r["mean_logprob"] >= t else cloud_score[(r["task"], r["question"])] for r in rows
        )
        if cascade >= cloud_mean - tolerance:
            share = len(kept) / len(rows)
            if best is None or share > best[1]:
                best = (t, share, statistics.mean(r["score"] for r in kept), cascade)
    return best


def fmt(x):
    return "-" if x is None else f"{x:.2f}"


def plot(runs, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed, skipping the chart (pip install matplotlib)")
        return
    tasks = [t for t in TASKS if any(r["task"] == t for rows in runs.values() for r in rows)]
    width = 0.8 / len(runs)
    fig, ax = plt.subplots(figsize=(7, 4))
    for i, (name, rows) in enumerate(runs.items()):
        values = [statistics.mean([r["score"] for r in rows if r["task"] == t] or [0]) for t in tasks]
        ax.bar([x + i * width for x in range(len(tasks))], values, width, label=name)
    ax.set_xticks([x + width * (len(runs) - 1) / 2 for x in range(len(tasks))])
    ax.set_xticklabels([t + (" (F1)" if t == "extract" else "") for t in tasks])
    ax.set_ylim(0, 1)
    ax.set_ylabel("accuracy / mean F1")
    ax.set_title("RQ1: local SLMs vs cloud LLM by task")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"wrote {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="+", help="CSV files from demo.py --all --csv")
    parser.add_argument("--out", help="write <out>.md and <out>.png")
    args = parser.parse_args()
    runs = read(args.csv)
    cloud = cloud_run(runs)
    report = "\n\n".join([
        "# RQ1 results",
        "## Quality by task\n\nEach cell: score (questions, format errors, median seconds per question). "
        "Format errors count as 0.\n\n" + quality_table(runs),
        "## Confidence signal and cascade\n\n" + confidence_section(runs, cloud),
    ])
    print(report)
    if args.out:
        with open(args.out + ".md", "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"\nwrote {args.out}.md")
        plot(runs, args.out + ".png")


if __name__ == "__main__":
    main()
