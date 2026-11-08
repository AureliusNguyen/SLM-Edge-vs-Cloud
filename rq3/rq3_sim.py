"""RQ3: compare routing policies offline, using the per-question RQ1 results and the
per-request RQ2 costs.

Every policy is scored on the same 400 questions (100 each of yesno, classify,
extract, math). For each question we know whether the local model and the cloud
model got it right (RQ1), and the local model's mean token log-prob. For each
(model, device profile, network, task) we know the median latency, mean device
energy and token counts (RQ2). A policy decides, per question, where it runs; we
then add up quality, latency, energy, carbon and API cost.

Policies
  always-local   every request on the SLM
  always-cloud   every request on the cloud model
  task-rule      the gateway rule: yesno and extract local, classify and math cloud
  cascade        SLM answers first; if its confidence is below a per-task threshold
                 the request is re-sent to the cloud (pays for both)
  rule+cascade   task-rule, but the local tasks fall back to the cloud when unsure
  oracle         knows which answer is right: local when the SLM is right, else cloud
                 (one call only; an upper bound no real router can reach)

Thresholds are chosen by repeated 2-fold cross-validation: pick the threshold on
one half of the questions, score it on the other half, so no policy is tuned on
the questions it is scored on.

Usage (from the repo root):
  python rq3/rq3_sim.py                      # default scenario grid, writes rq3/results/
  python rq3/rq3_sim.py --model qwen_nothink
"""
import argparse
import csv
import os
import random
import statistics
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RQ1 = os.path.join(ROOT, "shuyuan_rq1", "results")
RQ2 = os.path.join(ROOT, "rq2", "results", "raw")
TASKS = ["yesno", "classify", "extract", "math"]
RULE_LOCAL = {"yesno", "extract"}  # same as gateway/route.go localTasks

# RQ1 run name -> RQ2 model name (RQ2 ran Qwen with thinking off)
RQ2_MODEL = {"llama": "llama", "qwen_nothink": "qwen"}
# RQ2 profile -> raw file suffix (busy = back-to-back requests, our headline numbers)
PROFILES = {"gpu": "gpu_busy", "cpu": "cpu_busy", "docker-full": "dockerfull_busy",
            "docker-2cpu": "docker2cpu_busy"}


def read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------- RQ1: per-question correctness and confidence ----------

def load_rq1(run, judge="gptoss"):
    """Return {task: [(correct 0/1, mean_logprob), ...]} in question order.
    Extract counts as correct when the LLM judge says CORRECT (F1 is too strict for
    paraphrased spans, see shuyuan_rq1/results/judge/judge_summary.md)."""
    rows = read(os.path.join(RQ1, f"{run}.csv"))
    verdicts = [r["judge"] == "CORRECT" for r in read(os.path.join(RQ1, "judge", f"judge_{judge}.csv"))
                if r["run"] == run]
    out, k = defaultdict(list), 0
    for r in rows:
        if r["task"] == "extract":
            ok = 1.0 if verdicts[k] else 0.0
            k += 1
        else:
            ok = float(r["score"]) if r["score"] else 0.0  # format error counts as wrong
        out[r["task"]].append((ok, float(r["mean_logprob"]) if r["mean_logprob"] else -99.0))
    return out


# ---------- RQ2: per-request cost ----------

def cost_table(rows):
    """{task: dict(latency_s, device_wh, prompt_tokens, output_tokens)} from RQ2 rows."""
    by = defaultdict(list)
    for r in rows:
        if not r["error"]:
            by[r["task"]].append(r)
    out = {}
    for t, rs in by.items():
        num = lambda k: [float(x[k]) for x in rs if x[k] not in ("", None)]
        out[t] = {
            "latency_s": statistics.median(num("total_s")),
            "device_wh": statistics.mean(num("extra_energy_j")) / 3600,
            "prompt_tokens": statistics.mean(num("prompt_tokens")),
            "output_tokens": statistics.mean(num("output_tokens")),
        }
    return out


def load_local_cost(model, profile):
    m = RQ2_MODEL[model]
    rows = read(os.path.join(RQ2, f"rq2_{m}_{PROFILES[profile]}.csv"))
    if m == "qwen" and profile == "docker-2cpu":  # math was run separately (5 rows)
        rows += read(os.path.join(RQ2, "rq2_qwen_docker2cpu_math_busy.csv"))
    return cost_table(rows)


def load_cloud_cost(network):
    return cost_table(read(os.path.join(RQ2, f"rq2_cloud_{network}.csv")))


# ---------- one request ----------

class Prices:
    def __init__(self, a):
        self.ci_edge, self.ci_dc = a.ci_edge, a.ci_dc
        self.cloud_wh_low, self.cloud_wh_per_1k = a.cloud_wh, a.cloud_wh_per_1k_tokens
        self.in_price, self.out_price = a.price_in, a.price_out

    def local(self, c):
        wh = max(c["device_wh"], 0.0)
        return {"latency_s": c["latency_s"], "device_wh": wh, "cloud_wh": 0.0,
                "gco2": wh * self.ci_edge / 1000, "usd": 0.0, "cloud_calls": 0}

    def cloud(self, c, upper):
        dev = max(c["device_wh"], 0.0)
        cwh = c["output_tokens"] / 1000 * self.cloud_wh_per_1k if upper else self.cloud_wh_low
        return {"latency_s": c["latency_s"], "device_wh": dev, "cloud_wh": cwh,
                "gco2": dev * self.ci_edge / 1000 + cwh * self.ci_dc / 1000,
                "usd": (c["prompt_tokens"] * self.in_price + c["output_tokens"] * self.out_price) / 1e6,
                "cloud_calls": 1}


def add(a, b):
    return {k: a[k] + b[k] for k in a}


# ---------- thresholds ----------

def pick_threshold(local, cloud, tol):
    """Lowest log-prob threshold (keeps the most requests local) whose cascade accuracy
    stays within tol of always-cloud on these questions. Returns None for 'always cloud'."""
    cloud_acc = statistics.mean(c for c, _ in cloud)
    for thr in sorted({lp for _, lp in local}):
        acc = statistics.mean(l if lp >= thr else c for (l, lp), (c, _) in zip(local, cloud))
        if acc >= cloud_acc - tol:
            return thr
    return None


def folds(n, seed):
    idx = list(range(n))
    random.Random(seed).shuffle(idx)
    return idx[: n // 2], idx[n // 2:]


# ---------- policies ----------

def decide(policy, task, ok_l, lp, thr):
    """Return 'local', 'cloud' or 'cascade-keep' / 'cascade-escalate'."""
    if policy == "always-local":
        return "local"
    if policy == "always-cloud":
        return "cloud"
    if policy == "task-rule":
        return "local" if task in RULE_LOCAL else "cloud"
    if policy in ("cascade", "rule+cascade"):
        if policy == "rule+cascade" and task not in RULE_LOCAL:
            return "cloud"
        if thr is None:
            return "cloud"  # threshold says never trust the SLM on this task
        return "keep" if lp >= thr else "escalate"
    if policy == "oracle":
        return "local" if ok_l else "cloud"
    raise ValueError(policy)


POLICIES = ["always-local", "always-cloud", "task-rule", "cascade", "rule+cascade", "oracle"]


def run_policy(policy, q_local, q_cloud, lc, cc, prices, upper, thresholds, idx_by_task):
    """Score one policy over the given question indices. Returns totals and per-task totals."""
    tot = defaultdict(float)
    per_task = {}
    for task in TASKS:
        tt = defaultdict(float)
        for i in idx_by_task[task]:
            ok_l, lp = q_local[task][i]
            ok_c, _ = q_cloud[task][i]
            d = decide(policy, task, ok_l, lp, thresholds.get(task))
            L, C = prices.local(lc[task]), prices.cloud(cc[task], upper)
            if d == "local" or d == "keep":
                r, ok, loc = L, ok_l, 1
            elif d == "cloud":
                r, ok, loc = C, ok_c, 0
            else:  # escalate: the local answer was produced and thrown away
                r, ok, loc = add(L, C), ok_c, 0
            for k, v in r.items():
                tt[k] += v
            tt["correct"] += ok
            tt["local"] += loc
            tt["n"] += 1
        per_task[task] = dict(tt)
        for k, v in tt.items():
            tot[k] += v
    return dict(tot), per_task


def summarize(t):
    n = t["n"]
    acc = t["correct"] / n
    wh = (t["device_wh"] + t["cloud_wh"]) / n
    g = t["gco2"] / n
    lat = t["latency_s"] / n
    return {
        "accuracy": acc,
        "local_share": t["local"] / n,
        "cloud_calls_per_req": t["cloud_calls"] / n,
        "latency_s": lat,
        "device_wh": t["device_wh"] / n,
        "total_wh": wh,
        "gco2": g,
        "usd_per_1k": t["usd"] / n * 1000,
        "wh_per_correct": wh / acc if acc else float("nan"),
        "tcdp": g * lat,  # carbon-delay product per request, gCO2e*s (Golden et al.)
    }


def evaluate(model, profile, network, upper, prices, tol, reps):
    q_local, q_cloud = load_rq1(model), load_rq1("cloud")
    lc, cc = load_local_cost(model, profile), load_cloud_cost(network)
    results = {p: defaultdict(list) for p in POLICIES}
    per_task_acc = {p: defaultdict(list) for p in POLICIES}
    chosen = defaultdict(list)
    for rep in range(reps):
        splits = {t: folds(len(q_local[t]), seed=1000 * rep + k) for k, t in enumerate(TASKS)}
        for side in (0, 1):
            train = {t: splits[t][side] for t in TASKS}
            test = {t: splits[t][1 - side] for t in TASKS}
            thr = {t: pick_threshold([q_local[t][i] for i in train[t]],
                                     [q_cloud[t][i] for i in train[t]], tol) for t in TASKS}
            for t in TASKS:
                chosen[t].append(thr[t])
            for p in POLICIES:
                tot, pt = run_policy(p, q_local, q_cloud, lc, cc, prices, upper, thr, test)
                for k, v in summarize(tot).items():
                    results[p][k].append(v)
                for t in TASKS:
                    per_task_acc[p][t].append(pt[t]["correct"] / pt[t]["n"])
    avg = {p: {k: statistics.mean(v) for k, v in results[p].items()} for p in POLICIES}
    sd = {p: statistics.pstdev(results[p]["accuracy"]) for p in POLICIES}
    task_acc = {p: {t: statistics.mean(v) for t, v in per_task_acc[p].items()} for p in POLICIES}
    # threshold for deployment: fit on all 100 questions
    full = {t: pick_threshold(q_local[t], q_cloud[t], tol) for t in TASKS}
    never = {t: sum(1 for x in chosen[t] if x is None) / len(chosen[t]) for t in TASKS}
    return avg, sd, task_acc, full, never


# ---------- output ----------

def fmt(x, d=3):
    if x is None:
        return "-"
    if abs(x) >= 100:
        return f"{x:.0f}"
    return f"{x:.{d}g}" if abs(x) < 1 else f"{x:.{d}g}"


def table(avg, sd):
    head = ("| policy | accuracy (±sd) | kept local | cloud calls/req | latency s | total Wh/req "
            "| gCO2e/req | $ per 1k req | Wh per correct | tCDP g·s |")
    lines = [head, "|" + "---|" * 10]
    for p in POLICIES:
        a = avg[p]
        lines.append(
            f"| {p} | {a['accuracy']:.3f} (±{sd[p]:.3f}) | {a['local_share']:.0%} | {a['cloud_calls_per_req']:.2f} "
            f"| {fmt(a['latency_s'])} | {fmt(a['total_wh'])} | {fmt(a['gco2'])} | {a['usd_per_1k']:.3f} "
            f"| {fmt(a['wh_per_correct'])} | {fmt(a['tcdp'])} |")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="llama", choices=list(RQ2_MODEL))
    ap.add_argument("--tol", type=float, default=0.02, help="cascade may lose at most this much accuracy vs cloud")
    ap.add_argument("--reps", type=int, default=50, help="repeats of 2-fold cross-validation")
    ap.add_argument("--ci-edge", type=float, default=420, help="gCO2e/kWh, eGRID2023 MROW")
    ap.add_argument("--ci-dc", type=float, default=350, help="gCO2e/kWh, eGRID2023 U.S. total")
    ap.add_argument("--cloud-wh", type=float, default=0.24, help="cloud Wh per request, low estimate (Google)")
    ap.add_argument("--cloud-wh-per-1k-tokens", type=float, default=83.1,
                    help="cloud Wh per 1k output tokens, upper bound (Hugging Face AI Energy Score, gpt-oss-120b)")
    ap.add_argument("--price-in", type=float, default=0.15, help="USD per 1M input tokens (Groq gpt-oss-120b)")
    ap.add_argument("--price-out", type=float, default=0.60, help="USD per 1M output tokens (Groq gpt-oss-120b)")
    ap.add_argument("--low-battery", type=float, default=0.2,
                    help="share of requests that arrive with low battery (forced to cloud) in the battery scenario")
    ap.add_argument("--out", default=os.path.join(ROOT, "rq3", "results"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    prices = Prices(a)

    md = [f"# RQ3 results: routing policies ({a.model})", "",
          "Offline replay of the RQ1 answers (100 questions per task, 400 total, equal mix) with the RQ2 "
          "per-request costs. Thresholds come from 2-fold cross-validation repeated "
          f"{a.reps} times; numbers are means over the held-out halves. Extract counts as correct when the "
          "gpt-oss-20b judge says CORRECT. Latency is the median per-request time from RQ2 (busy device), "
          "so a cascade that escalates pays local + cloud time and energy.", "",
          f"Assumptions: edge grid {a.ci_edge:g} g/kWh, data-center grid {a.ci_dc:g} g/kWh, "
          f"cloud energy {a.cloud_wh:g} Wh/request (low) or {a.cloud_wh_per_1k_tokens:g} Wh per 1k output tokens "
          f"(upper), Groq price ${a.price_in:g}/${a.price_out:g} per 1M input/output tokens, cascade tolerance "
          f"{a.tol:g}.", ""]
    csv_rows = []

    scenarios = [(prof, net, up) for prof in PROFILES for net in ("wifi", "hotspot") for up in (False, True)]
    headline = None
    for prof, net, up in scenarios:
        avg, sd, task_acc, full, never = evaluate(a.model, prof, net, up, prices, a.tol, a.reps)
        for p in POLICIES:
            csv_rows.append({"model": a.model, "profile": prof, "network": net,
                             "cloud_energy": "upper" if up else "low", "policy": p,
                             **{k: round(v, 6) for k, v in avg[p].items()}, "accuracy_sd": round(sd[p], 4)})
        if (prof, net, up) == ("gpu", "wifi", False):
            headline = (avg, sd, task_acc, full, never)

    avg, sd, task_acc, full, never = headline
    md += ["## Headline: GPU laptop, Wi-Fi, low cloud-energy estimate", ""] + table(avg, sd) + [""]
    md += ["Per-task accuracy:", "", "| policy | " + " | ".join(TASKS) + " |", "|" + "---|" * (len(TASKS) + 1)]
    for p in POLICIES:
        md.append(f"| {p} | " + " | ".join(f"{task_acc[p][t]:.3f}" for t in TASKS) + " |")
    md += ["", "Cascade thresholds (mean token log-prob) fit on all 100 questions, for the gateway; "
           "'cloud' means no threshold met the tolerance, so the task always goes to the cloud. "
           "'never local' is how often that happened across the cross-validation folds.", "",
           "| task | threshold | never local in CV |", "|---|---|---|"]
    for t in TASKS:
        md.append(f"| {t} | {'cloud' if full[t] is None else f'{full[t]:.4f}'} | {never[t]:.0%} |")

    md += ["", "## All scenarios", "",
           "accuracy / gCO2e per request / latency s, per policy. Accuracy does not depend on the scenario "
           "(same answers), only the cost does.", "",
           "| profile | network | cloud energy | " + " | ".join(POLICIES) + " |", "|" + "---|" * (3 + len(POLICIES))]
    by = defaultdict(dict)
    for r in csv_rows:
        by[(r["profile"], r["network"], r["cloud_energy"])][r["policy"]] = r
    for (prof, net, ce), d in by.items():
        md.append(f"| {prof} | {net} | {ce} | " + " | ".join(
            f"{d[p]['accuracy']:.2f} / {fmt(d[p]['gco2'], 2)} / {fmt(d[p]['latency_s'], 2)}" for p in POLICIES) + " |")

    # battery: a share of requests arrive with low battery and are forced to the cloud
    b = a.low_battery
    md += ["", f"## Low battery ({b:.0%} of requests forced to the cloud)", "",
           "Expected value: (1 - share) x policy + share x always-cloud, GPU / Wi-Fi / low estimate.", "",
           "| policy | accuracy | kept local | latency s | gCO2e/req | $ per 1k req |", "|---|---|---|---|---|---|"]
    ac = avg["always-cloud"]
    for p in POLICIES:
        m = {k: (1 - b) * avg[p][k] + b * ac[k] for k in avg[p]}
        md.append(f"| {p} | {m['accuracy']:.3f} | {m['local_share']:.0%} | {fmt(m['latency_s'])} "
                  f"| {fmt(m['gco2'])} | {m['usd_per_1k']:.3f} |")

    # grid sensitivity (Kopczyk & Chandra: MN 364 vs solar-rich state 163 g/kWh)
    md += ["", "## Edge-grid sensitivity (GPU / Wi-Fi / low estimate)", "",
           "gCO2e per request when the device sits on a different grid. 420 = eGRID MROW (ours), "
           "364 = Minnesota state average and 163 = a solar-rich western state (both from Kopczyk & Chandra).", "",
           "| policy | 163 | 364 | 420 |", "|---|---|---|---|"]
    q_l, q_c = load_rq1(a.model), load_rq1("cloud")
    lc, cc = load_local_cost(a.model, "gpu"), load_cloud_cost("wifi")
    all_idx = {t: list(range(len(q_l[t]))) for t in TASKS}
    grid = {}
    for ci in (163, 364, 420):
        a2 = argparse.Namespace(**{**vars(a), "ci_edge": ci})
        pr = Prices(a2)
        grid[ci] = {p: summarize(run_policy(p, q_l, q_c, lc, cc, pr, False, full, all_idx)[0])["gco2"]
                    for p in POLICIES}
    for p in POLICIES:
        md.append(f"| {p} | " + " | ".join(fmt(grid[ci][p]) for ci in (163, 364, 420)) + " |")

    # when do the energy-best and carbon-best choice differ for one request?
    md += ["", "## When energy-best and carbon-best disagree", "",
           f"For one request, local wins on energy when local Wh < cloud Wh, and on carbon when "
           f"local Wh x {a.ci_edge:g} < cloud Wh x {a.ci_dc:g}. With the low estimate "
           f"({a.cloud_wh:g} Wh) the two disagree only when local energy is between "
           f"{a.cloud_wh * a.ci_dc / a.ci_edge:.3f} and {a.cloud_wh:g} Wh.", "",
           "| model | profile | task | local Wh | energy-best | carbon-best |", "|---|---|---|---|---|---|"]
    for prof in PROFILES:
        c = load_local_cost(a.model, prof)
        for t in TASKS:
            wh = max(c[t]["device_wh"], 0)
            e = "local" if wh < a.cloud_wh else "cloud"
            g = "local" if wh * a.ci_edge < a.cloud_wh * a.ci_dc else "cloud"
            flag = " **differ**" if e != g else ""
            md.append(f"| {a.model} | {prof} | {t} | {fmt(wh)} | {e} | {g}{flag} |")

    import json
    with open(os.path.join(a.out, f"thresholds_{a.model}.json"), "w", encoding="utf-8") as f:
        json.dump({"model": a.model, "tol": a.tol, "thresholds": full}, f, indent=2)

    path_md = os.path.join(a.out, f"rq3_{a.model}.md")
    with open(path_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    path_csv = os.path.join(a.out, f"rq3_{a.model}.csv")
    with open(path_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(csv_rows[0]))
        w.writeheader()
        w.writerows(csv_rows)
    print("wrote", path_md, "and", path_csv)


if __name__ == "__main__":
    main()
