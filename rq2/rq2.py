"""RQ2 analysis: latency, energy and carbon per request, by model, device profile and network.

    python rq2.py rq2_*.csv --out rq2            # writes rq2.md and rq2_*.png

Carbon is C = E x CI (proposal, eq. 1):
    local request:  C = E_device_extra x CI_edge
    cloud request:  C = E_cloud_estimate x CI_dc  +  E_device_extra x CI_edge
E_device_extra is measured (power above idle during the request). The cloud side cannot
be measured, so E_cloud_estimate is a published per-prompt figure (--cloud-wh, default
0.24 Wh, Google's median Gemini text prompt), or scales with output tokens if
--cloud-wh-per-1k-tokens is given. All assumptions are printed in rq2.md.
"""

import argparse
import csv
import glob
import statistics
from collections import defaultdict

TASKS = ("yesno", "classify", "extract", "math")


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def read(patterns):
    rows = []
    paths = []
    for p in patterns:  # Windows cmd does not expand wildcards, so do it here
        paths += sorted(glob.glob(p)) or [p]
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            rows += list(csv.DictReader(f))
    return rows


def med(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def cloud_wh(row, args):
    if args.cloud_wh_per_1k_tokens is not None:
        tokens = num(row.get("output_tokens")) or 0
        return args.cloud_wh_per_1k_tokens * tokens / 1000
    return args.cloud_wh


def summarize(rows, args):
    groups = defaultdict(list)
    for r in rows:
        mode = "busy" if (num(r.get("gap_s")) or 0) < 5 else "isolated"
        groups[(r["run"], r["tier"], r["profile"] + "/" + mode, r["network"], r["task"])].append(r)
    out = []
    for (run, tier, profile, network, task), rs in sorted(groups.items(), key=lambda kv: (kv[0][:4], TASKS.index(kv[0][4]) if kv[0][4] in TASKS else 9)):
        ok = [r for r in rs if r["verdict"] != "ERROR"]
        device_wh = mean([num(r["extra_energy_j"]) for r in ok])
        device_wh = device_wh / 3600 if device_wh is not None else None
        remote_wh = mean([cloud_wh(r, args) for r in ok]) if tier == "cloud" else 0.0
        carbon = None
        if device_wh is not None or tier == "cloud":
            carbon = max(device_wh or 0, 0) * args.ci_edge / 1000 + remote_wh * args.ci_dc / 1000
        out.append({
            "run": run, "tier": tier, "profile": profile, "network": network, "task": task,
            "n": len(rs), "errors": len(rs) - len(ok),
            "score": mean([num(r["score"]) or 0.0 for r in ok]),
            "ttft_s": med([num(r["ttft_s"]) for r in ok]),
            "total_s": med([num(r["total_s"]) for r in ok]),
            "out_tokens": med([num(r["output_tokens"]) for r in ok]),
            "avg_power_w": mean([num(r["avg_power_w"]) for r in ok]),
            "idle_power_w": mean([num(r["idle_power_w"]) for r in ok]),
            "device_wh": device_wh,
            "j_per_token": (device_wh * 3600 / tok) if device_wh is not None and (tok := mean([num(r["output_tokens"]) for r in ok])) else None,
            "cloud_wh": remote_wh if tier == "cloud" else None,
            "carbon_g": carbon,
            "rtt_ms": med([num(r["rtt_ms"]) for r in rs]),
        })
    return out


def fmt(x, digits=3):
    if x is None:
        return "-"
    return f"{x:.{digits}g}" if abs(x) < 1000 else f"{x:.0f}"


def write_md(summary, args, path):
    lines = ["# RQ2 results", "",
             "One row per model, device profile, network and task. Times are medians, energy and carbon are means per request.",
             "Profile suffix: /isolated = 10 s pause after each request, so the energy includes the GPU/CPU winding down "
             "(one request on an otherwise idle device); /busy = requests back to back (marginal energy on a busy device).", "",
             "| model | tier | profile | network | task | n | score | TTFT s | total s | out tokens | avg W | idle W | device Wh | device J/token | cloud Wh (est.) | gCO2e | RTT ms |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        lines.append("| {run} | {tier} | {profile} | {network} | {task} | {n} | {sc} | {ttft} | {total} | {tok} | {pw} | {idle} | {dwh} | {jpt} | {cwh} | {c} | {rtt} |".format(
            **s, sc=fmt(s["score"], 2), ttft=fmt(s["ttft_s"]), total=fmt(s["total_s"]), tok=fmt(s["out_tokens"]),
            pw=fmt(s["avg_power_w"]), idle=fmt(s["idle_power_w"]), dwh=fmt(s["device_wh"]), jpt=fmt(s["j_per_token"]), cwh=fmt(s["cloud_wh"]),
            c=fmt(s["carbon_g"]), rtt=fmt(s["rtt_ms"])))
    cloud = (f"{args.cloud_wh_per_1k_tokens} Wh per 1000 output tokens" if args.cloud_wh_per_1k_tokens is not None
             else f"{args.cloud_wh} Wh per prompt")
    lines += ["", "## Assumptions", "",
              f"- Device energy: measured power above the idle power taken before each run, integrated from the start of a request to the end of the pause after it.",
              f"- Cloud energy: {cloud} (estimate; the provider's data center cannot be measured).",
              f"- Edge grid carbon intensity: {args.ci_edge} gCO2e/kWh ({args.ci_edge_source}).",
              f"- Data-center grid carbon intensity: {args.ci_dc} gCO2e/kWh ({args.ci_dc_source}).",
              "- Device J/token: mean extra device energy divided by mean output tokens (as in Masthan Ali et al., E-Energy '26). "
              "It includes prompt processing, so it is high for tasks with long prompts and 2-6 token answers.",
              "- Network transfer energy is not included."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def plot(summary, prefix):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed, skipping charts")
        return []
    configs = sorted({(s["run"], s["profile"], s["network"]) for s in summary})
    tasks = [t for t in TASKS if any(s["task"] == t for s in summary)]
    index = {(s["run"], s["profile"], s["network"], s["task"]): s for s in summary}
    charts = [("total_s", "Median total time per request (s)", True),
              ("ttft_s", "Median time to first token (s)", True),
              ("device_wh", "Extra device energy per request (Wh)", False),
              ("carbon_g", "Carbon per request (gCO2e)", False)]
    written = []
    width = 0.8 / max(1, len(configs))
    for key, title, log in charts:
        if not any(s[key] is not None for s in summary):
            continue
        fig, ax = plt.subplots(figsize=(max(6, 1.6 * len(tasks) + 0.4 * len(configs)), 4))
        for i, (run, profile, network) in enumerate(configs):
            values = [index.get((run, profile, network, t), {}).get(key) for t in tasks]
            xs = [j + (i - (len(configs) - 1) / 2) * width for j in range(len(tasks))]
            ax.bar(xs, [v if v is not None else 0 for v in values], width, label=f"{run} / {profile} / {network}")
        ax.set_xticks(range(len(tasks)), tasks)
        ax.set_title(title)
        if log:
            ax.set_yscale("log")
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(fontsize=8, frameon=False, loc="upper left", bbox_to_anchor=(1, 1))
        fig.tight_layout()
        path = f"{prefix}_{key}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        written.append(path)
    return written


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="+")
    p.add_argument("--out", default="rq2")
    p.add_argument("--cloud-wh", type=float, default=0.24, help="cloud energy per prompt in Wh")
    p.add_argument("--cloud-wh-per-1k-tokens", type=float, help="instead, cloud Wh per 1000 output tokens")
    p.add_argument("--ci-edge", type=float, default=420, help="gCO2e/kWh where the device runs")
    p.add_argument("--ci-edge-source", default="EPA eGRID2023 rev2, MROW subregion total output CO2e 926.6 lb/MWh (Minnesota)")
    p.add_argument("--ci-dc", type=float, default=350, help="gCO2e/kWh of the data center grid")
    p.add_argument("--ci-dc-source", default="EPA eGRID2023 rev2, U.S. total output CO2e 770.9 lb/MWh, since the provider's region is unknown")
    args = p.parse_args()
    summary = summarize(read(args.csv), args)
    write_md(summary, args, args.out + ".md")
    charts = plot(summary, args.out)
    print(f"wrote {args.out}.md" + (" and " + ", ".join(charts) if charts else ""))


if __name__ == "__main__":
    main()
