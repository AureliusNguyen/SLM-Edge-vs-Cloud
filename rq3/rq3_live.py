"""RQ3 live check: run the router for real on a mixed workload, with power measured,
and compare with what the offline replay (rq3_sim.py) predicts for the same questions.

For every question (yesno, classify, extract, math shuffled together) the router
decides on the spot, calls Ollama and/or Groq, and the device power is logged the same
way as RQ2. Policies:
  task-rule      yesno and extract local, classify and math cloud (the gateway rule)
  rule+cascade   task-rule, but a local answer whose mean log-prob is below the task's
                 threshold is thrown away and the request goes to the cloud
  cascade        every task starts local, low-confidence answers go to the cloud
Thresholds come from rq3/results/thresholds_<label>.json, written by rq3_sim.py.

Example (Windows, LibreHardwareMonitor running, GROQ_API_KEY set):
  python rq3\\rq3_live.py --policies task-rule,rule+cascade -n 25 --power lhm,nvidia --csv rq3\\results\\live_llama_gpu.csv
"""
import argparse
import csv
import json
import os
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "rq2"))
import rq2_measure as m  # power logging, Groq client (also adds shuyuan_rq1 to the path)
import rq1_eval as run_eval

RULE_LOCAL = {"yesno", "extract"}


def ask_local(args, task, prompt):
    """Ollama, non-streaming so we get token log-probs (the cascade's confidence signal)."""
    options = {"temperature": 0, "num_predict": args.max_tokens}
    if args.threads:
        options["num_thread"] = args.threads
    if args.cpu_only:
        options["num_gpu"] = 0
    body = {"model": args.model, "messages": run_eval.messages(task, prompt), "stream": False,
            "options": options, "logprobs": True, "keep_alive": "30m"}
    if args.no_think:
        body["think"] = False
    req = urllib.request.Request(args.ollama + "/api/chat", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        data = json.load(r)
    reply = re.sub(r"<think>.*?</think>", "", data["message"].get("content") or "", flags=re.S).strip()
    lps = [t.get("logprob") for t in data.get("logprobs") or [] if t.get("logprob") is not None]
    return reply, (sum(lps) / len(lps) if lps else None), data.get("eval_count") or 0, data.get("prompt_eval_count") or 0


WAITED = [0.0]  # seconds spent waiting on rate limits during the current request (not counted as latency)


def ask_cloud(args, task, prompt):
    for attempt in range(8):
        try:
            reply, _, info = m.openai_stream(args.cloud_url, os.environ.get(args.key_env), args.cloud_model,
                                             run_eval.messages(task, prompt), {}, args.max_tokens)
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 7:
                raise
            ra = e.headers.get("retry-after")
            wait = min(max(float(ra) if ra else 5 * 2 ** attempt, 1.0), 60.0)
            print(f"  Groq rate limit, waiting {wait:.0f}s (not counted as latency) ...")
            time.sleep(wait)
            WAITED[0] += wait
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.S).strip()
    return reply, info.get("output_tokens") or 0, info.get("prompt_tokens") or 0


def route(args, policy, task, prompt, thr):
    """Run one request under a policy. Returns (tier, reply, local_logprob, cloud_out, cloud_in, path)."""
    if policy == "task-rule" and task not in RULE_LOCAL:
        return ("cloud", *ask_cloud_wrap(args, task, prompt), "cloud")
    if policy == "rule+cascade" and task not in RULE_LOCAL:
        return ("cloud", *ask_cloud_wrap(args, task, prompt), "cloud")
    if policy in ("cascade", "rule+cascade") and thr.get(task) is None:
        return ("cloud", *ask_cloud_wrap(args, task, prompt), "cloud")
    reply, lp, _, _ = ask_local(args, task, prompt)
    if policy == "task-rule" or (lp is not None and lp >= thr[task]):
        return "local", reply, lp, 0, 0, "local"
    creply, cout, cin = ask_cloud(args, task, prompt)
    return "cloud", creply, lp, cout, cin, "local->cloud"


def ask_cloud_wrap(args, task, prompt):
    reply, cout, cin = ask_cloud(args, task, prompt)
    return reply, None, cout, cin


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--policies", default="task-rule,rule+cascade")
    p.add_argument("-n", type=int, default=25, help="questions per task (same first-n questions as RQ1)")
    p.add_argument("--label", default="llama", help="RQ1 run name the thresholds were fit on")
    p.add_argument("--profile", default="gpu")
    p.add_argument("--network", default="wifi")
    p.add_argument("--csv", required=True)
    p.add_argument("--ollama", default="http://127.0.0.1:11434")
    p.add_argument("--model", default="llama3.2:3b")
    p.add_argument("--threads", type=int)
    p.add_argument("--cpu-only", action="store_true")
    p.add_argument("--no-think", action="store_true")
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--cloud-url", default="https://api.groq.com/openai/v1")
    p.add_argument("--cloud-model", default="openai/gpt-oss-120b")
    p.add_argument("--key-env", default="GROQ_API_KEY")
    p.add_argument("--power", default="lhm,nvidia")
    p.add_argument("--lhm-url", default="http://127.0.0.1:8085")
    p.add_argument("--lhm-sensor", default="CPU Package")
    p.add_argument("--interval", type=float, default=0.2)
    p.add_argument("--idle", type=float, default=30)
    p.add_argument("--settle", type=float, default=20)
    p.add_argument("--max-idle", type=float, default=30)
    p.add_argument("--ci-edge", type=float, default=420)
    p.add_argument("--ci-dc", type=float, default=350)
    p.add_argument("--cloud-wh", type=float, default=0.24)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--pace", type=float, default=2.0,
                   help="pause after each cloud call, to stay under Groq's free-tier rate limit (not counted)")
    p.add_argument("--resume", action="store_true",
                   help="keep the finished rows of an existing --csv and only run the missing or failed ones")
    args = p.parse_args()

    if not os.environ.get(args.key_env):
        raise SystemExit(f"{args.key_env} is not set. In cmd: set {args.key_env}=your-key")
    with open(os.path.join(HERE, "results", f"thresholds_{args.label}.json"), encoding="utf-8") as f:
        thr = json.load(f)["thresholds"]
    # Load the same 100 questions per task as RQ1 (cached on disk after the first run), keep n of each.
    every = run_eval.seeded(100, list(run_eval.TASKS))
    items = [x for t in run_eval.TASKS for x in [y for y in every if y[0] == t][:args.n]]
    random.Random(args.seed).shuffle(items)  # mixed workload, same order for every policy
    policies = args.policies.split(",")

    power = m.PowerLog(m.make_sources(args), args.interval)
    power.start()
    try:
        print("warming up the local model ...")
        ask_local(args, "yesno", "Passage: The sky is blue.\nQuestion: is the sky blue?")
        idle_w = m.measure_idle(power, args.idle, args.settle)
        if idle_w is not None and idle_w > args.max_idle:
            raise SystemExit(f"idle power is {idle_w:.1f} W, above --max-idle {args.max_idle} W. Close other programs and retry.")
        print(f"idle power {idle_w and round(idle_w, 2)} W")
        fields = ["policy", "task", "tier", "path", "score", "verdict", "local_logprob", "total_s", "waited_s",
                  "extra_energy_j", "cloud_out_tokens", "cloud_in_tokens", "gold", "reply", "question", "error"]
        kept = []
        if args.resume and os.path.exists(args.csv):
            kept = [r for r in csv.DictReader(open(args.csv, encoding="utf-8")) if r["verdict"] != "ERROR"]
            print(f"resuming: {len(kept)} finished rows kept, failed or missing ones will run")
        done = {(r["policy"], r["question"]) for r in kept}
        with open(args.csv, "w", newline="", encoding="utf-8") as out:
            w = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(kept)
            for pol in policies:
                for i, (task, question, prompt, gold) in enumerate(items, 1):
                    if (pol, question) in done:
                        continue
                    WAITED[0] = 0.0
                    row = {"policy": pol, "task": task, "question": question, "gold": run_eval.show_gold(gold)}
                    t0 = time.time()
                    try:
                        tier, reply, lp, cout, cin, path = route(args, pol, task, prompt, thr)
                        t1 = time.time()
                        row["score"], row["verdict"] = run_eval.verdict(task, reply, gold)
                        row.update(tier=tier, path=path, reply=reply, cloud_out_tokens=cout, cloud_in_tokens=cin,
                                   local_logprob=lp if lp is None else round(lp, 4))
                    except Exception as e:
                        t1 = time.time()
                        row.update(verdict="ERROR", error=str(e)[:300])
                    row["total_s"] = round(t1 - t0 - WAITED[0], 3)
                    row["waited_s"] = round(WAITED[0], 1)
                    power.wait_past(t1)
                    j = power.energy(t0, t1)
                    if j is not None and idle_w is not None:
                        row["extra_energy_j"] = round(j - idle_w * (t1 - t0), 3)
                    w.writerow(row)
                    out.flush()
                    print(f"{pol:13} {i:3}/{len(items)} {task:8} {row.get('path', '-'):13} "
                          f"{row['verdict'][:8]:8} {row['total_s']}s")
                    if row.get("tier") == "cloud" or row["verdict"] == "ERROR":
                        time.sleep(args.pace)  # outside the timed window
    finally:
        power.close()
    summarize(args, policies)


def summarize(args, policies):
    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    lines = [f"# RQ3 live run ({args.label}, {args.profile}, {args.network}, {args.n} questions per task)", "",
             "Measured: accuracy (extract = F1 here, the judge is not re-run), share answered locally, "
             "latency, device energy above idle. Carbon adds the cloud estimate "
             f"({args.cloud_wh} Wh per cloud call, {args.ci_dc:g} g/kWh) to device energy at {args.ci_edge:g} g/kWh.", "",
             "| policy | n | score | answered locally | escalated | median s | mean s | device Wh/req | cloud calls/req | gCO2e/req |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for pol in policies:
        rs = [r for r in rows if r["policy"] == pol and r["verdict"] != "ERROR"]
        if not rs:
            continue
        n = len(rs)
        score = statistics.mean(float(r["score"] or 0) for r in rs)
        local = sum(r["tier"] == "local" for r in rs) / n
        esc = sum(r["path"] == "local->cloud" for r in rs) / n
        secs = [float(r["total_s"]) for r in rs]
        dev = statistics.mean(max(float(r["extra_energy_j"] or 0), 0) for r in rs) / 3600
        calls = sum(r["tier"] == "cloud" for r in rs) / n
        g = dev * args.ci_edge / 1000 + calls * args.cloud_wh * args.ci_dc / 1000
        lines.append(f"| {pol} | {n} | {score:.3f} | {local:.0%} | {esc:.0%} | {statistics.median(secs):.2f} "
                     f"| {statistics.mean(secs):.2f} | {dev:.4f} | {calls:.2f} | {g:.4f} |")
    errors = sum(r["verdict"] == "ERROR" for r in rows)
    if errors:
        lines += ["", f"{errors} requests failed and are left out."]
    path = os.path.splitext(args.csv)[0] + ".md"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("wrote", path)


if __name__ == "__main__":
    main()
