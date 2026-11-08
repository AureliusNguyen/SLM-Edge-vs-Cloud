"""Plot accuracy against carbon and latency for each routing policy (from rq3_sim.py output)."""
import csv, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

HERE = os.path.dirname(os.path.abspath(__file__))
model = sys.argv[1] if len(sys.argv) > 1 else "llama"
rows = list(csv.DictReader(open(os.path.join(HERE, "results", f"rq3_{model}.csv"), encoding="utf-8")))
INK, MUTED, GRID = "#2b2b2a", "#6b6a65", "#e4e2dc"
COLORS = {"gpu": "#2a78d6", "cpu": "#eb6834"}  # categorical slots 1, 2
plt.rcParams.update({"font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED})
fig, axes = plt.subplots(1, 2, figsize=(11, 4.0), sharey=True)
for ax, (key, label, log) in zip(axes, [("gco2", "gCO2e per request (log scale)", True),
                                        ("latency_s", "median latency per request, s", False)]):
    pts = [r for r in rows if r["profile"] == "gpu" and r["network"] == "wifi" and r["cloud_energy"] == "low"]
    xs, ys = [float(r[key]) for r in pts], [float(r["accuracy"]) for r in pts]
    ax.scatter(xs, ys, s=70, color=COLORS["gpu"], edgecolor="white", linewidth=2, zorder=3)
    for r, x, y in zip(pts, xs, ys):
        dy = 8 if r["policy"] == "oracle" else (-14 if r["policy"] == "always-cloud" else -4)
        ax.annotate(r["policy"], (x, y), xytext=(7, dy), textcoords="offset points", fontsize=9, color=INK)
    if log:
        ax.set_xscale("log")
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    lo, hi = ax.get_xlim(); ax.set_xlim(lo, hi * (1.6 if log else 1.25))
    ax.set_xlabel(label)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
axes[0].set_ylabel("accuracy on 400 mixed questions")
fig.suptitle(f"Routing policies, {model} on the GPU laptop, Wi-Fi, low cloud-energy estimate (0.24 Wh/request)",
             color=INK, fontsize=11, x=0.01, ha="left")
fig.tight_layout()
out = os.path.join(HERE, "results", f"rq3_{model}.png")
fig.savefig(out, dpi=200)
print("wrote", out)
