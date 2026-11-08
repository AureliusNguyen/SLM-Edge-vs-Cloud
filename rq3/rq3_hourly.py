"""Carbon that changes by the hour: when does the carbon-best choice (local vs cloud) flip?

Reads the hourly carbon intensity made by get_hourly_ci.py and the RQ2 per-request device
energy, and asks, for every device profile and task: in how many hours of the year would
sending the request to the cloud emit less than running it locally? It also compares the
yearly carbon of a router that looks at the current hour with one that uses a fixed annual
average, and checks how often the energy-best and carbon-best choices disagree.

    python rq3/rq3_hourly.py                      # MISO 2024, Llama, low cloud estimate
    python rq3/rq3_hourly.py --cloud-wh-per-1k-tokens 83.1 --upper
"""
import argparse
import csv
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rq3_sim as sim  # RQ2 cost tables and RQ1 answers


def parse_time(s):
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            pass
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ci-file", default=os.path.join(HERE, "results", "miso_hourly_ci_2024.csv"))
    ap.add_argument("--model", default="llama", choices=list(sim.RQ2_MODEL))
    ap.add_argument("--ci-dc", type=float, default=350, help="data-center grid, gCO2/kWh (kept fixed)")
    ap.add_argument("--cloud-wh", type=float, default=0.24)
    ap.add_argument("--cloud-wh-per-1k-tokens", type=float, default=83.1)
    ap.add_argument("--upper", action="store_true", help="use the upper cloud-energy estimate")
    ap.add_argument("--flat", type=float, default=420, help="the fixed annual value used so far (eGRID MROW)")
    a = ap.parse_args()

    hours = []
    for r in csv.DictReader(open(a.ci_file, encoding="utf-8")):
        t = parse_time(r["local_end"])
        hours.append((t, float(r["ci_g_per_kwh"]), float(r["total_mw"])))
    cis = [c for _, c, _ in hours]
    wmean = sum(c * w for _, c, w in hours) / sum(w for _, _, w in hours)
    q = lambda p: sorted(cis)[int(p * (len(cis) - 1))]
    tag = "upper" if a.upper else "low"
    md = [f"# Hourly carbon intensity and routing ({a.model}, cloud estimate: {tag})", "",
          f"Grid: {os.path.basename(a.ci_file)}, {len(hours)} hours. Generation-weighted mean "
          f"{wmean:.0f} g/kWh; 10th / 50th / 90th percentile {q(.1):.0f} / {q(.5):.0f} / {q(.9):.0f}; "
          f"min {min(cis):.0f}, max {max(cis):.0f}. Until now we used a fixed {a.flat:g} g/kWh.", ""]

    # mean by hour of day
    by_hod = defaultdict(list)
    for t, c, _ in hours:
        if t:
            by_hod[t.hour].append(c)
    md += ["Mean by hour of day (local time, hour ending):", "",
           "| hour | " + " | ".join(str(h) for h in range(24)) + " |", "|" + "---|" * 25,
           "| g/kWh | " + " | ".join(f"{statistics.mean(by_hod[h]):.0f}" if by_hod[h] else "-" for h in range(24)) + " |", ""]

    # break-even per profile and task
    cloud_cost = sim.load_cloud_cost("wifi")
    md += ["## When is the cloud lower-carbon than running locally?", "",
           "Local carbon = device Wh x grid at that hour. Cloud carbon = cloud Wh x "
           f"{a.ci_dc:g} g/kWh (+ the tiny device energy while waiting). The cloud wins in an hour when "
           "the grid is above the break-even intensity.", "",
           "| profile | task | local Wh | cloud Wh | break-even g/kWh | hours cloud is lower-carbon | energy-best |",
           "|---|---|---|---|---|---|---|"]
    flips = {}
    for prof in sim.PROFILES:
        lc = sim.load_local_cost(a.model, prof)
        for task in sim.TASKS:
            lwh = max(lc[task]["device_wh"], 0)
            cwh = cloud_cost[task]["output_tokens"] / 1000 * a.cloud_wh_per_1k_tokens if a.upper else a.cloud_wh
            cdev = max(cloud_cost[task]["device_wh"], 0)
            # local wins if lwh*ci < cwh*ci_dc + cdev*ci  ->  ci*(lwh - cdev) < cwh*ci_dc
            be = cwh * a.ci_dc / (lwh - cdev) * 1 if lwh > cdev else float("inf")
            share = sum(1 for c in cis if c > be) / len(cis)
            flips[(prof, task)] = share
            energy = "local" if lwh < cwh + cdev else "cloud"
            md.append(f"| {prof} | {task} | {lwh:.4f} | {cwh:.3g} | "
                      f"{'never' if be == float('inf') else f'{be:.0f}'} | {share:.0%} | {energy} |")

    # router that looks at the hour vs one that uses the flat value, on the task-rule local tasks
    md += ["", "## Carbon-aware routing over a year", "",
           "A request arrives every hour of the year for each task. 'static' = the task rule (yes/no and "
           "extract local, classify and math cloud). 'hourly' = also send a local task to the cloud in "
           "hours when the cloud is lower-carbon, and keep a cloud task local when local is lower-carbon "
           "(quality ignored, to show the carbon side alone). Error of flat = how far the yearly carbon "
           f"computed with a fixed {a.flat:g} g/kWh is from the hour-by-hour value.", "",
           "| profile | static g/req (hourly grid) | static g/req (flat grid) | error of flat | carbon-only hourly g/req | saving vs static |",
           "|---|---|---|---|---|---|"]
    for prof in sim.PROFILES:
        lc = sim.load_local_cost(a.model, prof)
        st_h, st_f, hr = 0.0, 0.0, 0.0
        n = 0
        for task in sim.TASKS:
            lwh = max(lc[task]["device_wh"], 0)
            cwh = cloud_cost[task]["output_tokens"] / 1000 * a.cloud_wh_per_1k_tokens if a.upper else a.cloud_wh
            cdev = max(cloud_cost[task]["device_wh"], 0)
            for c in cis:
                loc = lwh * c / 1000
                cl = (cwh * a.ci_dc + cdev * c) / 1000
                st_h += loc if task in sim.RULE_LOCAL else cl
                hr += min(loc, cl)
                n += 1
            st_f += len(cis) * ((lwh * a.flat / 1000) if task in sim.RULE_LOCAL else (cwh * a.ci_dc + cdev * a.flat) / 1000)
        md.append(f"| {prof} | {st_h / n:.4f} | {st_f / n:.4f} | {(st_f - st_h) / st_h:+.0%} | {hr / n:.4f} | {1 - hr / st_h:.0%} |")
    md += ["", "Energy-best and carbon-best disagree in an hour when the energy-best column says local but "
           "the cloud is lower-carbon in that hour, i.e. the share in the 'hours cloud is lower-carbon' column "
           "for rows marked local."]

    out = os.path.join(HERE, "results", f"hourly_{a.model}_{tag}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md))
    print("wrote", out)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    hs = list(range(24))
    mean = [statistics.mean(by_hod[h]) if by_hod[h] else float("nan") for h in hs]
    p10 = [sorted(by_hod[h])[len(by_hod[h]) // 10] if by_hod[h] else float("nan") for h in hs]
    p90 = [sorted(by_hod[h])[9 * len(by_hod[h]) // 10] if by_hod[h] else float("nan") for h in hs]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.fill_between(hs, p10, p90, color="#cde2fb", label="10th-90th percentile")
    ax.plot(hs, mean, color="#2a78d6", linewidth=2, label="mean")
    ax.axhline(a.flat, color="#6b6a65", linewidth=1, linestyle="--")
    ax.annotate(f"fixed value used so far ({a.flat:g})", (0.3, a.flat), xytext=(0, 4),
                textcoords="offset points", fontsize=8.5, color="#6b6a65")
    ax.set_xlabel("hour of day (local time)")
    ax.set_ylabel("gCO2 per kWh")
    ax.set_xlim(0, 23)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(True, color="#e4e2dc", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper right", fontsize=8.5)
    ax.set_title(f"Hourly carbon intensity, {os.path.basename(a.ci_file).split('_')[0].upper()} grid",
                 loc="left", fontsize=10.5)
    fig.tight_layout()
    png = os.path.join(HERE, "results", "hourly_ci.png")
    fig.savefig(png, dpi=200)
    print("wrote", png)


if __name__ == "__main__":
    main()
