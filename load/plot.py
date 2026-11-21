# Plot deadline-miss rate against offered request rate: one panel per arrival pattern and
# task mix, one line per policy, from every CSV that run.py wrote.
#
#   python3 load/plot.py      # writes load/results/miss_rate.png
import collections
import csv
import glob
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
OUT = os.path.join(RESULTS, "miss_rate.png")


def miss_rates(results):
    """{(arrivals, mix): {policy: [(rate, miss rate)]}}, rates sorted."""
    missed = collections.defaultdict(list)
    for path in glob.glob(os.path.join(results, "**", "*.csv"), recursive=True):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                missed[(r["arrivals"], r["mix"], r["policy"], float(r["rate"]))].append(int(r["missed"]))
    panels = collections.defaultdict(lambda: collections.defaultdict(list))
    for (arrivals, mix, policy, rate), flags in sorted(missed.items()):
        panels[(arrivals, mix)][policy].append((rate, sum(flags) / len(flags)))
    return panels


def main():
    panels = miss_rates(RESULTS)
    if not panels:
        raise SystemExit(f"no results under {RESULTS}")
    fig, axes = plt.subplots(1, len(panels), figsize=(4.5 * len(panels), 3.8), sharey=True, squeeze=False)
    for ax, ((arrivals, mix), policies) in zip(axes[0], sorted(panels.items())):
        for policy, points in sorted(policies.items()):
            rates, misses = zip(*points)
            ax.plot(rates, misses, marker="o", label=policy)
        ax.set_title(f"{arrivals} arrivals, {mix} mix")
        ax.set_xlabel("offered rate (requests/s)")
        ax.grid(alpha=0.3)
    axes[0][0].set_ylabel("deadline-miss rate")
    axes[0][0].set_ylim(-0.02, 1.02)
    axes[0][-1].legend()
    fig.tight_layout()
    fig.savefig(OUT, dpi=150)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
