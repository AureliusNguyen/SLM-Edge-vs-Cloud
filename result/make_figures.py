import csv, re, sys, os
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."); OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
C = {"llama": "#2a6fdb", "phi35": "#e8702a", "gemma2": "#1aa774"}
N = {"llama": "Llama 3.2 3B", "phi35": "Phi-3.5 mini", "gemma2": "Gemma 2 2B"}

# 1) system flow
fig, ax = plt.subplots(figsize=(10, 3.6)); ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 3.6)
def box(x, y, w, h, t, c):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05", fc=c, ec="#555"))
    ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=10.5)
def arrow(x1, y1, x2, y2, t=""):
    ax.annotate("", (x2, y2), (x1, y1), arrowprops=dict(arrowstyle="->", color="#444", lw=1.4))
    if t: ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.12, t, ha="center", fontsize=9, color="#333")
box(0.1, 1.4, 1.6, 0.8, "Request\n+ task type", "#eef")
box(2.4, 1.2, 2.4, 1.2, "Go gateway\npolicy: task-rule /\ncascade / ...", "#ffe9c7")
box(6.0, 2.3, 3.6, 0.9, "Local SLM (Ollama)\nLlama / Qwen / Phi / Gemma", "#d8f3e6")
box(6.0, 0.3, 3.6, 0.9, "Cloud LLM (Groq)\ngpt-oss-120b", "#fde0d6")
arrow(1.75, 1.8, 2.35, 1.8)
arrow(4.85, 2.0, 5.95, 2.7, "yes/no, extract")
arrow(4.85, 1.6, 5.95, 0.8, "classify, math")
ax.annotate("", (7.8, 1.25), (7.8, 2.25), arrowprops=dict(arrowstyle="->", color="#c0392b", lw=1.4, ls="--"))
ax.text(7.9, 1.75, "cascade: low confidence\n-> re-ask the cloud", fontsize=9, color="#c0392b", va="center")
ax.set_title("How a request is routed", loc="left")
fig.savefig(f"{OUT}/02_system_flow.png", dpi=200, bbox_inches="tight"); plt.close(fig)

# 2) three models: accuracy vs carbon
P = ["always-local", "always-cloud", "task-rule", "cascade", "rule+cascade", "oracle"]
M = {"always-local": "o", "always-cloud": "s", "task-rule": "^", "cascade": "D", "rule+cascade": "P", "oracle": "*"}
fig, ax = plt.subplots(figsize=(8, 4.8))
for m in C:
    rows = [r for r in csv.DictReader(open(f"{R}/rq3/results_extra/rq3_{m}.csv", encoding="utf-8"))
            if r["profile"] == "gpu" and r["network"] == "wifi" and r["cloud_energy"] == "low" and r["policy"] in P]
    for r in rows:
        ax.scatter(float(r["gco2"]), float(r["accuracy"]), color=C[m], marker=M[r["policy"]], s=90 if r["policy"] == "oracle" else 55, alpha=.85)
for p in P: ax.scatter([], [], color="#777", marker=M[p], label=p)
for m in C: ax.scatter([], [], color=C[m], marker="o", label=N[m])
ax.set_xscale("log"); ax.set_xlabel("gCO2e per request (log scale)"); ax.set_ylabel("accuracy, 400 questions")
ax.legend(fontsize=8.5, ncol=2, loc="lower right", frameon=False)
ax.set_title("Same policy ranking for all three local models (GPU, Wi-Fi)", loc="left")
ax.grid(alpha=.3); fig.savefig(f"{OUT}/09_three_models_policies.png", dpi=200, bbox_inches="tight"); plt.close(fig)

# 3) network delay
fig, axs = plt.subplots(1, 3, figsize=(12, 3.8), sharey=True)
for ax, m in zip(axs, C):
    md = open(f"{R}/rq3/results_extra/rq3_{m}.md", encoding="utf-8").read()
    sec = md[md.index("## Network delay"):].split("\n## ")[0]
    for line in sec.splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] in ("always-local", "always-cloud", "task-rule", "rule+cascade"):
            ax.plot([0, .1, .3, 1], [float(x) for x in cells[1:5]], marker="o", label=cells[0])
    ax.set_title(N[m]); ax.set_xlabel("extra delay per cloud call, s"); ax.grid(alpha=.3)
axs[0].set_ylabel("mean latency per request, s"); axs[0].legend(fontsize=8.5, frameon=False)
fig.suptitle("Slower network to the cloud: always-local becomes the fastest", x=0.01, ha="left")
fig.tight_layout(); fig.savefig(f"{OUT}/11_network_delay.png", dpi=200, bbox_inches="tight"); plt.close(fig)
print("ok")

# 4) RQ1 quality, all local models (extract scored by the gpt-oss-20b judge)
import numpy as np
T = ["yes/no", "classify", "extract (judge)", "math"]
d = {"Llama 3.2 3B": [.78, .55, .93, .73], "Qwen3 1.7B (no think)": [.78, .36, .95, .22], "Phi-3.5 mini": [.86, .47, .93, .86],
     "Gemma 2 2B": [.81, .69, .97, .57], "Cloud gpt-oss-120b": [.94, .75, 1.0, .97]}  # from shuyuan_rq1/results and judge/
col = ["#2a6fdb", "#9b59b6", "#e8702a", "#1aa774", "#555555"]
fig, ax = plt.subplots(figsize=(10, 4.2)); x = np.arange(4); w = .16
for i, (k, v) in enumerate(d.items()): ax.bar(x + (i - 2) * w, v, w, label=k, color=col[i])
ax.set_xticks(x, T); ax.set_ylim(0, 1.05); ax.set_ylabel("accuracy (400 questions)")
ax.legend(ncol=5, fontsize=9, frameon=False, loc="upper center", bbox_to_anchor=(.5, -.1))
ax.set_title("RQ1: every local model trails the cloud, but on different tasks", loc="left")
fig.savefig(f"{OUT}/04_rq1_quality_all_models.png", dpi=200, bbox_inches="tight"); plt.close(fig)
