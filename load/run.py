# Replay a trace against the gateway open-loop: each request is sent at its scheduled
# time whether or not earlier ones have finished, so overload shows up as missed deadlines
# instead of a slower load generator. Latency counts from the scheduled arrival.
#
#   python3 load/run.py load/traces/poisson-uniform-r0.5-s1.json                # task-rule
#   python3 load/run.py load/traces/poisson-uniform-r0.5-s1.json always-cloud
#   python3 load/run.py load/traces/poisson-uniform-r0.5-s1.json always-local
import csv
import http.client
import json
import os
import re
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shuyuan_rq1"))
import rq1_eval

GATEWAY = "http://localhost:8080"
TIMEOUT = 600
MAX_LAG = 0.05
POLICIES = {"task-rule": None, "always-cloud": "cloud", "always-local": "local"}
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def send(gateway, task, prompt, force, timeout):
    """Returns (HTTP status or None, tier, reply, error)."""
    headers = {"Content-Type": "application/json", "X-Task-Type": task}
    if force:
        headers["X-Force-Tier"] = force
    body = {"model": "auto", "messages": rq1_eval.messages(task, prompt), "temperature": 0, "max_tokens": 4096}
    request = urllib.request.Request(gateway + "/v1/chat/completions", json.dumps(body).encode(), headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:
            reply = json.load(r)["choices"][0]["message"]["content"] or ""
            return r.status, r.headers.get("X-Route", ""), re.sub(r"<think>.*?</think>", "", reply, flags=re.S), ""
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("X-Route") or "", "", e.read().decode(errors="replace").strip()[:200]
    except (OSError, http.client.HTTPException, ValueError) as e:
        return None, "", "", f"{type(e).__name__}: {e}"


def run(trace, gateway, force=None, timeout=TIMEOUT, lead=1.0):
    results = [None] * len(trace["requests"])
    start = time.monotonic() + lead

    def worker(i, request):
        dispatched = time.monotonic() - start
        status, tier, reply, error = send(gateway, request["task"], request["prompt"], force, timeout)
        completed = time.monotonic() - start
        results[i] = (request, dispatched, completed, status, tier, reply, error)

    threads = []
    for i, request in enumerate(trace["requests"]):
        delay = start + request["at"] - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        thread = threading.Thread(target=worker, args=(i, request))
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()
    return [row(trace, *result) for result in results]


def row(trace, request, dispatched, completed, status, tier, reply, error):
    latency = completed - request["at"]
    score, verdict = None, ""
    if status == 200:
        score, verdict = rq1_eval.verdict(request["task"], reply, request["gold"])
        score = score or 0.0
    return {
        "arrivals": trace["arrivals"], "mix": trace["mix"], "rate": trace["rate"], "seed": trace["seed"],
        "id": request["id"], "task": request["task"], "tier": tier, "status": status or "",
        "at": request["at"], "dispatched": round(dispatched, 4), "completed": round(completed, 4),
        "latency": round(latency, 4), "deadline": request["deadline"],
        "missed": int(status != 200 or latency > request["deadline"]),
        "score": score, "verdict": verdict, "error": error,
    }


def warm_up(gateway, timeout):
    """Load the local model before the clock starts, so the first requests don't pay for it."""
    status, _, _, error = send(gateway, "yesno", "Is the sky blue?", "local", timeout)
    if status != 200:
        print(f"warm-up failed ({status or error}), continuing", file=sys.stderr)


def summary(rows, policy):
    latencies = sorted(r["latency"] for r in rows)
    lag = max(r["dispatched"] - r["at"] for r in rows)
    failed = sum(r["status"] != 200 for r in rows)
    lines = [
        f"{policy}: {len(rows)} requests, {sum(r['missed'] for r in rows)} missed deadlines, {failed} failed, "
        f"p50 {statistics.median(latencies):.2f} s, p95 {latencies[int(0.95 * (len(latencies) - 1))]:.2f} s, "
        f"max dispatch lag {lag * 1000:.0f} ms"
    ]
    for task in sorted({r["task"] for r in rows}):
        mine = [r for r in rows if r["task"] == task]
        scored = [r["score"] for r in mine if r["score"] is not None]
        local = sum(r["tier"] == "local" for r in mine)
        quality = f"{statistics.mean(scored):.3f}" if scored else "-"
        lines.append(f"  {task:8} n={len(mine):3}  quality {quality}  missed {sum(r['missed'] for r in mine):3}  "
                     f"local {local}/{len(mine)}")
    if lag > MAX_LAG:
        lines.append(f"WARNING: the runner fell {lag * 1000:.0f} ms behind schedule, so this run was not open-loop")
    return "\n".join(lines)


def write_csv(rows, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(trace_path, policy="task-rule"):
    if policy not in POLICIES:
        raise SystemExit(f"policy is one of {', '.join(POLICIES)}")
    with open(trace_path, encoding="utf-8") as f:
        trace = json.load(f)
    warm_up(GATEWAY, TIMEOUT)
    rows = run(trace, GATEWAY, POLICIES[policy])
    for r in rows:
        r["policy"] = policy
    out = os.path.join(RESULTS, policy, os.path.splitext(os.path.basename(trace_path))[0] + ".csv")
    write_csv(rows, out)
    print(summary(rows, policy))
    print(f"wrote {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
