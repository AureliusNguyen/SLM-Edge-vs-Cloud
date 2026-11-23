"""RQ3 full comparison: every routing policy, both SLMs, with hour-by-hour grid carbon,
embodied carbon and network carbon added on top of the operational numbers in rq3_sim.py.

Reuses rq3_sim.py (RQ1 answers, RQ2 costs, cross-validated cascade thresholds) and the hourly
MISO carbon intensity in results/miso_hourly_ci_2024.csv (made by get_hourly_ci.py).

Policies: the six in rq3_sim.py plus
  carbon-aware        per task, send each request to whichever side emits less, using the fixed
                      420 g/kWh edge grid (the Load-Balancer CarbonAware strategy with static profiles)
  carbon-aware-hourly the same choice made every hour with that hour's grid intensity
  rule+cascade+carbon rule+cascade, but a request bound for the SLM goes to the cloud instead in hours
                      when the cloud is lower-carbon (quality can only go up)

Carbon per request, in gCO2e:
  edge operational   device Wh x edge grid (hourly MISO, averaged over the 8,784 hours of 2024)
  cloud operational  cloud Wh x 350 g/kWh (data-center grid kept fixed; location unknown)
  device embodied    laptop manufacturing carbon spread over its active seconds, x request time
                     (charged on both paths: the laptop is the client either way)
  cloud embodied     server manufacturing carbon per kWh of server energy, x cloud Wh
  network            bytes per cloud call x access-network kWh/GB x edge grid
Embodied and network use low / mid / high assumptions (see ASSUMPTIONS); the tables show mid and
the range.

    python rq3/rq3_compare.py            # writes results/rq3_compare.{md,csv} and rq3_compare.png
"""
import argparse
import csv
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rq3_sim as sim  # noqa: E402

MODELS = ["llama", "qwen_nothink"]
NETWORKS = ["wifi", "hotspot"]
BASE = [p for p in sim.POLICIES if p != "fit-rule"]  # the six policies compared in the report
EXTRA = ["carbon-aware", "carbon-aware-hourly", "rule+cascade+carbon"]
POLICIES = BASE + EXTRA

# low / mid / high. Sources and reasoning are written out in results/rq3_summary.md.
ASSUMPTIONS = {
    # laptop: embodied kgCO2e, lifetime years, active hours per day
    "laptop_kg": (150, 250, 350),
    "laptop_years": (5, 4, 3),
    "laptop_hours_per_day": (12, 8, 4),
    # cloud server (8-GPU class): embodied kgCO2e, average power kW, lifetime years, utilization
    "server_kg": (1500, 2500, 4000),
    "server_kw": (8, 6, 4),
    "server_years": (6, 5, 4),
    "server_util": (0.7, 0.5, 0.3),
    # network: kB moved per cloud call (prompt, streamed reply, HTTP/TLS), kWh per GB
    "kb_per_call": (5, 20, 50),
    "kwh_per_gb": {"wifi": (0.002, 0.02, 0.06), "hotspot": (0.05, 0.1, 0.3)},
}
LEVELS = ("low", "mid", "high")


def laptop_g_per_s(i):
    a = ASSUMPTIONS
    secs = a["laptop_years"][i] * 365 * a["laptop_hours_per_day"][i] * 3600
    return a["laptop_kg"][i] * 1000 / secs


def server_g_per_wh(i):
    a = ASSUMPTIONS
    kwh = a["server_kw"][i] * a["server_years"][i] * 8760 * a["server_util"][i]
    return a["server_kg"][i] * 1000 / (kwh * 1000)


def network_wh_per_call(net, i):
    a = ASSUMPTIONS
    return a["kb_per_call"][i] * 1e3 / 1e9 * a["kwh_per_gb"][net][i] * 1000


def load_ci(path):
    with open(path, encoding="utf-8") as f:
        return [float(r["ci_g_per_kwh"]) for r in csv.DictReader(f)]


class Hourly:
    """Per task: share of hours when the cloud emits less than local, and the mean grid in those hours."""

    def __init__(self, cis, lc, cc, prices, upper):
        self.cis, self.mean = cis, statistics.mean(cis)
        self.split = {}
        for t in sim.TASKS:
            L, C = prices.local(lc[t]), prices.cloud(cc[t], upper)
            lwh, cdev, cwh = L["device_wh"], C["device_wh"], C["cloud_wh"]
            # local loses in an hour when lwh*ci > cwh*ci_dc + cdev*ci
            hot = [c for c in cis if (lwh - cdev) * c > cwh * prices.ci_dc]
            cold = [c for c in cis if not (lwh - cdev) * c > cwh * prices.ci_dc]
            self.split[t] = (len(hot) / len(cis),
                             statistics.mean(hot) if hot else 0.0,
                             statistics.mean(cold) if cold else 0.0)


def request_cost(side, L, C):
    """Cost dict for one request that ends up 'local', 'cloud' or 'escalate' (local, then cloud)."""
    if side == "local":
        return L
    if side == "cloud":
        return C
    return sim.add(L, C)


def score(policy, model, profile, net, upper, prices, hourly, q_l, q_c, lc, cc, thr, idx):
    """Totals over the given question indices. Carbon is split into components; edge-side energy
    is kept apart from cloud energy so it can be priced with the hourly grid afterwards."""
    tot = defaultdict(float)
    for t in sim.TASKS:
        L, C = prices.local(lc[t]), prices.cloud(cc[t], upper)
        share_hot, ci_hot, ci_cold = hourly.split[t]
        for i in idx[t]:
            ok_l, lp = q_l[t][i]
            ok_c, _ = q_c[t][i]
            if policy in BASE:
                d = sim.decide(policy, t, ok_l, lp, thr.get(t))
                d = {"keep": "local"}.get(d, d)
                mix = [(1.0, d, None)]
            elif policy == "carbon-aware":
                lg = L["device_wh"] * prices.ci_edge
                cg = C["device_wh"] * prices.ci_edge + C["cloud_wh"] * prices.ci_dc
                mix = [(1.0, "local" if lg <= cg else "cloud", None)]
            elif policy == "carbon-aware-hourly":
                mix = [(share_hot, "cloud", ci_hot), (1 - share_hot, "local", ci_cold)]
            elif policy == "rule+cascade+carbon":
                d = sim.decide("rule+cascade", t, ok_l, lp, thr.get(t))
                if d == "cloud":
                    mix = [(1.0, "cloud", None)]
                else:  # bound for the SLM: in hot hours go straight to the cloud
                    mix = [(share_hot, "cloud", ci_hot),
                           (1 - share_hot, "local" if d == "keep" else "escalate", ci_cold)]
            for w, side, ci in mix:
                if w == 0:
                    continue
                r = request_cost(side, L, C)
                ci_e = hourly.mean if ci is None else ci
                tot["n"] += w
                tot["correct"] += w * (ok_l if side == "local" else ok_c)
                tot["local"] += w * (side == "local")
                tot["latency_s"] += w * r["latency_s"]
                tot["device_wh"] += w * r["device_wh"]
                tot["cloud_wh"] += w * r["cloud_wh"]
                tot["cloud_calls"] += w * r["cloud_calls"]
                tot["usd"] += w * r["usd"]
                tot["g_edge_hourly"] += w * r["device_wh"] * ci_e / 1000
                tot["g_edge_flat"] += w * r["device_wh"] * prices.ci_edge / 1000
                tot["g_cloud"] += w * r["cloud_wh"] * prices.ci_dc / 1000
                for k, lev in enumerate(LEVELS):
                    tot[f"g_emb_dev_{lev}"] += w * r["latency_s"] * laptop_g_per_s(k)
                    tot[f"g_emb_cloud_{lev}"] += w * r["cloud_wh"] * server_g_per_wh(k)
                    tot[f"g_net_{lev}"] += w * r["cloud_calls"] * network_wh_per_call(net, k) * ci_e / 1000
    return tot


def summarize(t):
    n = t["n"]
    out = {k: t[k] / n for k in t if k not in ("n", "correct", "local", "usd")}
    out["accuracy"] = t["correct"] / n
    out["local_share"] = t["local"] / n
    out["usd_per_1k"] = t["usd"] / n * 1000
    out["g_operational_flat"] = out["g_edge_flat"] + out["g_cloud"]
    out["g_operational"] = out["g_edge_hourly"] + out["g_cloud"]
    for lev in LEVELS:
        out[f"g_total_{lev}"] = (out["g_operational"] + out[f"g_emb_dev_{lev}"]
                                 + out[f"g_emb_cloud_{lev}"] + out[f"g_net_{lev}"])
    out["g_per_correct"] = out["g_total_mid"] / out["accuracy"]
    out["tcdp_operational"] = out["g_operational"] * out["latency_s"]
    out["tcdp_total"] = out["g_total_mid"] * out["latency_s"]
    return out


def evaluate(model, profile, net, upper, prices, cis, reps, tol):
    q_l, q_c = sim.load_rq1(model), sim.load_rq1("cloud")
    lc, cc = sim.load_local_cost(model, profile), sim.load_cloud_cost(net)
    hourly = Hourly(cis, lc, cc, prices, upper)
    acc = {p: defaultdict(list) for p in POLICIES}
    for rep in range(reps):
        splits = {t: sim.folds(len(q_l[t]), seed=1000 * rep + k) for k, t in enumerate(sim.TASKS)}
        for side in (0, 1):
            train = {t: splits[t][side] for t in sim.TASKS}
            test = {t: splits[t][1 - side] for t in sim.TASKS}
            thr = {t: sim.pick_threshold([q_l[t][i] for i in train[t]], [q_c[t][i] for i in train[t]], tol)
                   for t in sim.TASKS}
            for p in POLICIES:
                s = summarize(score(p, model, profile, net, upper, prices, hourly, q_l, q_c, lc, cc, thr, test))
                for k, v in s.items():
                    acc[p][k].append(v)
    res = {p: {k: statistics.mean(v) for k, v in acc[p].items()} for p in POLICIES}
    for p in POLICIES:
        res[p]["accuracy_sd"] = statistics.pstdev(acc[p]["accuracy"])
    return res, hourly


def g(x):
    if x == 0:
        return "0"
    if abs(x) >= 100:
        return f"{x:.0f}"
    return f"{x:.2g}" if abs(x) < 0.01 else f"{x:.3g}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ci-file", default=os.path.join(HERE, "results", "miso_hourly_ci_2024.csv"))
    ap.add_argument("--reps", type=int, default=50)
    ap.add_argument("--tol", type=float, default=0.02)
    ap.add_argument("--ci-edge", type=float, default=420)
    ap.add_argument("--ci-dc", type=float, default=350)
    ap.add_argument("--cloud-wh", type=float, default=0.24)
    ap.add_argument("--cloud-wh-per-1k-tokens", type=float, default=83.1)
    ap.add_argument("--price-in", type=float, default=0.15)
    ap.add_argument("--price-out", type=float, default=0.60)
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    a = ap.parse_args()
    prices = sim.Prices(a)
    cis = load_ci(a.ci_file)
    ci_mean = statistics.mean(cis)

    rows, res_by, hourly_by = [], {}, {}
    for model in MODELS:
        for prof in sim.PROFILES:
            for net in NETWORKS:
                for up in (False, True):
                    res, hourly = evaluate(model, prof, net, up, prices, cis, a.reps, a.tol)
                    key = (model, prof, net, "upper" if up else "low")
                    res_by[key], hourly_by[key] = res, hourly
                    for p in POLICIES:
                        rows.append({"model": model, "profile": prof, "network": net, "cloud_energy": key[3],
                                     "policy": p, **{k: round(v, 7) for k, v in sorted(res[p].items())}})
                    print("done", key)

    with open(os.path.join(a.out, "rq3_compare.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    md = ["# RQ3 full routing comparison", "",
          f"Made by `rq3/rq3_compare.py`. Offline replay of the RQ1 answers with RQ2 costs, cascade thresholds "
          f"from 2-fold cross-validation repeated {a.reps} times (same as `rq3_sim.py`). Edge carbon uses the "
          f"hour-by-hour MISO 2024 grid ({len(cis)} hours, mean {ci_mean:.0f} g/kWh) instead of the fixed "
          f"{a.ci_edge:g}; the data-center grid stays at {a.ci_dc:g}. 'total' adds embodied and network carbon at "
          "the mid assumption; the range in brackets is low to high. All numbers are per request.", ""]

    def head_table(model, prof="gpu", net="wifi", ce="low"):
        r = res_by[(model, prof, net, ce)]
        lines = ["| policy | accuracy | kept local | latency s | operational g (flat 420) | operational g (hourly) "
                 "| embodied g | network g | total g [low-high] | g per correct | tCDP g·s | $ per 1k |",
                 "|" + "---|" * 12]
        for p in POLICIES:
            x = r[p]
            emb = x["g_emb_dev_mid"] + x["g_emb_cloud_mid"]
            lines.append(
                f"| {p} | {x['accuracy']:.3f} | {x['local_share']:.0%} | {x['latency_s']:.2f} "
                f"| {g(x['g_operational_flat'])} | {g(x['g_operational'])} | {g(emb)} | {g(x['g_net_mid'])} "
                f"| {g(x['g_total_mid'])} [{g(x['g_total_low'])}-{g(x['g_total_high'])}] "
                f"| {g(x['g_per_correct'])} | {g(x['tcdp_total'])} | {x['usd_per_1k']:.3f} |")
        return lines

    for model in MODELS:
        md += [f"## {model}: GPU laptop, Wi-Fi, low cloud-energy estimate (0.24 Wh per cloud call)", ""]
        md += head_table(model) + [""]
        md += [f"Same, with the upper cloud-energy estimate ({a.cloud_wh_per_1k_tokens:g} Wh per 1k output tokens):", ""]
        md += head_table(model, ce="upper") + [""]

    md += ["## All device profiles (Wi-Fi, low estimate)", "",
           "accuracy / total gCO2e (mid) / latency s.", "",
           "| model | profile | " + " | ".join(POLICIES) + " |", "|" + "---|" * (2 + len(POLICIES))]
    for model in MODELS:
        for prof in sim.PROFILES:
            r = res_by[(model, prof, "wifi", "low")]
            md.append(f"| {model} | {prof} | " + " | ".join(
                f"{r[p]['accuracy']:.2f} / {g(r[p]['g_total_mid'])} / {r[p]['latency_s']:.2f}" for p in POLICIES) + " |")

    md += ["", "## Where the carbon comes from (GPU, Wi-Fi, low estimate, mid assumptions)", "",
           "| model | policy | edge operational | cloud operational | device embodied | cloud embodied | network | total |",
           "|---|---|---|---|---|---|---|---|"]
    for model in MODELS:
        r = res_by[(model, "gpu", "wifi", "low")]
        for p in ["always-local", "always-cloud", "task-rule", "rule+cascade"]:
            x = r[p]
            tot = x["g_total_mid"]
            parts = [x["g_edge_hourly"], x["g_cloud"], x["g_emb_dev_mid"], x["g_emb_cloud_mid"], x["g_net_mid"]]
            md.append(f"| {model} | {p} | " + " | ".join(f"{g(v)} ({v / tot:.0%})" for v in parts) + f" | {g(tot)} |")

    md += ["", "## Network carbon on the phone hotspot (GPU, low estimate)", "",
           "| model | policy | network g mid [low-high] | share of total |", "|---|---|---|---|"]
    for model in MODELS:
        r = res_by[(model, "gpu", "hotspot", "low")]
        for p in ["always-cloud", "task-rule"]:
            x = r[p]
            md.append(f"| {model} | {p} | {g(x['g_net_mid'])} [{g(x['g_net_low'])}-{g(x['g_net_high'])}] "
                      f"| {x['g_net_mid'] / x['g_total_mid']:.1%} |")

    # grid sensitivity, operational only, GPU wifi low
    md += ["", "## Edge-grid sensitivity (operational carbon, GPU, Wi-Fi, low estimate)", "",
           "163 = solar-rich state and 364 = Minnesota state average (Kopczyk & Chandra), 420 = eGRID MROW "
           f"(what we used so far), hourly = MISO 2024 hour by hour (mean {ci_mean:.0f}).", "",
           "| model | policy | 163 | 364 | 420 | hourly |", "|---|---|---|---|---|---|"]
    for model in MODELS:
        r = res_by[(model, "gpu", "wifi", "low")]
        for p in BASE:
            x = r[p]
            vals = [x["g_cloud"] + x["device_wh"] * c / 1000 for c in (163, 364, 420)] + [x["g_operational"]]
            md.append(f"| {model} | {p} | " + " | ".join(g(v) for v in vals) + " |")

    # hours when the cloud is the lower-carbon choice
    md += ["", "## Hours of 2024 when the cloud is the lower-carbon choice (Wi-Fi)", "",
           "Only cells above 0% are listed; every other profile and task is lower-carbon locally in every hour.", "",
           "| model | profile | cloud estimate | task | share of hours | mean grid in those hours |", "|---|---|---|---|---|---|"]
    any_hot = False
    for (model, prof, net, ce), h in hourly_by.items():
        if net != "wifi":
            continue
        for t, (s, ch, _) in h.split.items():
            if s > 0:
                any_hot = True
                md.append(f"| {model} | {prof} | {ce} | {t} | {s:.0%} | {ch:.0f} |")
    if not any_hot:
        md.append("| - | - | - | - | 0% | - |")

    md += ["", "## Assumptions for embodied and network carbon (low / mid / high)", "",
           f"- Laptop: {ASSUMPTIONS['laptop_kg']} kgCO2e embodied, {ASSUMPTIONS['laptop_years']} years, "
           f"{ASSUMPTIONS['laptop_hours_per_day']} active hours a day -> "
           + " / ".join(f"{laptop_g_per_s(i) * 1000:.2f}" for i in range(3)) + " mgCO2e per active second.",
           f"- Cloud server (8-GPU class): {ASSUMPTIONS['server_kg']} kgCO2e embodied, average "
           f"{ASSUMPTIONS['server_kw']} kW, {ASSUMPTIONS['server_years']} years, utilization "
           f"{ASSUMPTIONS['server_util']} -> " + " / ".join(f"{server_g_per_wh(i) * 1000:.0f}" for i in range(3))
           + " gCO2e per kWh of server energy.",
           f"- Network: {ASSUMPTIONS['kb_per_call']} kB per cloud call; Wi-Fi/fixed "
           f"{ASSUMPTIONS['kwh_per_gb']['wifi']} kWh/GB, mobile hotspot {ASSUMPTIONS['kwh_per_gb']['hotspot']} kWh/GB, "
           "priced at the edge grid.", ""]

    path = os.path.join(a.out, "rq3_compare.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print("wrote", path)
    plot(res_by, os.path.join(a.out, "rq3_compare.png"))


def plot(res_by, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    INK, MUTED, GRID = "#2b2b2a", "#6b6a65", "#e4e2dc"
    parts = [("g_edge_hourly", "edge operational", "#2a78d6"), ("g_cloud", "cloud operational", "#eb6834"),
             ("g_emb_dev_mid", "device embodied", "#1baf7a"), ("g_emb_cloud_mid", "cloud embodied", "#eda100"),
             ("g_net_mid", "network", "#e87ba4")]
    plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                         "xtick.color": MUTED, "ytick.color": INK})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for ax, model in zip(axes, MODELS):
        r = res_by[(model, "gpu", "wifi", "low")]
        ys = list(range(len(POLICIES)))[::-1]
        for y, p in zip(ys, POLICIES):
            left = 0.0
            for k, _, col in parts:
                v = r[p][k]
                ax.barh(y, v, left=left, height=0.62, color=col, edgecolor="white", linewidth=1)
                left += v
            ax.errorbar(r[p]["g_total_mid"], y, xerr=[[r[p]["g_total_mid"] - r[p]["g_total_low"]],
                                                       [r[p]["g_total_high"] - r[p]["g_total_mid"]]],
                        fmt="none", ecolor=MUTED, elinewidth=1, capsize=3)
            ax.annotate(f"acc {r[p]['accuracy']:.2f}", (r[p]["g_total_high"], y), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=8.5, color=INK)
        ax.set_yticks(ys)
        ax.set_yticklabels(POLICIES)
        ax.set_xlabel("gCO2e per request (bar = mid assumptions, whisker = low-high)")
        ax.set_title(f"{model}, GPU laptop, Wi-Fi, 0.24 Wh per cloud call", loc="left", fontsize=10, color=INK)
        lo, hi = ax.get_xlim()
        ax.set_xlim(0, hi * 1.18)
        ax.grid(True, axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in parts]
    fig.legend(handles, [l for _, l, _ in parts], loc="lower center", ncol=5, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out, dpi=200)
    print("wrote", out)


if __name__ == "__main__":
    main()
