"""RQ2: latency and energy of local vs cloud inference, per device profile and network.

Each request is timed (time to first token and total time) while a background thread
samples device power. The extra energy of a request is the power above idle, integrated
over the request.

    # local, native Ollama, full laptop
    python rq2_measure.py --tier local --model llama3.2:3b --profile native --label llama -n 20 --csv rq2_llama_native.csv
    # local, weaker device: Ollama in a Docker container with --cpus 2 --memory 4g on port 11435
    python rq2_measure.py --tier local --model llama3.2:3b --ollama http://127.0.0.1:11435 --profile docker-2cpu ...
    # cloud over Wi-Fi, then again over the phone hotspot
    python rq2_measure.py --tier cloud --profile native --network wifi --label cloud -n 20 --csv rq2_cloud_wifi.csv

Power sources (--power):
    rapl    Linux, reads /sys/class/powercap/intel-rapl:*/energy_uj (needs sudo or a readable file)
    lhm     Windows, LibreHardwareMonitor with Options > Remote Web Server on (default port 8085)
    powermetrics  macOS on Apple silicon, CPU + GPU + ANE power (asks for sudo)
    battery Windows laptop unplugged, whole-laptop power from the battery discharge rate
    tegrastats  NVIDIA Jetson board power
    nvidia  adds GPU power from nvidia-smi (can be combined, e.g. --power rapl,nvidia)
    none    latency only
"""

import argparse
import csv
import glob
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shuyuan_rq1"))
import rq1_eval as run_eval  # same datasets, prompts and scoring as RQ1


# ---------------------------------------------------------------- power sources

class Rapl:
    """Cumulative package energy from the Linux powercap interface."""

    name = "rapl"

    def __init__(self):
        self.files = [f for f in glob.glob("/sys/class/powercap/intel-rapl:*/energy_uj")
                      if f.count(":") == 1]  # packages only, not their subdomains (core, dram)
        if not self.files:
            raise RuntimeError("no /sys/class/powercap/intel-rapl:*/energy_uj (not Linux on bare metal?)")
        self.wrap = [int(open(f.replace("energy_uj", "max_energy_range_uj")).read()) for f in self.files]
        self.last = self.raw()
        self.total = 0.0

    def raw(self):
        try:
            return [int(open(f).read()) for f in self.files]
        except PermissionError:
            raise RuntimeError("cannot read RAPL: run with sudo, or `sudo chmod a+r "
                               "/sys/class/powercap/intel-rapl:*/energy_uj`")

    def joules(self):
        now = self.raw()
        for i, (a, b) in enumerate(zip(self.last, now)):
            self.total += ((b - a) % self.wrap[i]) / 1e6  # the counter wraps around
        self.last = now
        return self.total


class Lhm:
    """Instantaneous CPU package power from LibreHardwareMonitor's web server."""

    name = "lhm"

    def __init__(self, url, sensor):
        self.url = url.rstrip("/") + "/data.json"
        self.sensor = sensor.lower()
        first = None
        for attempt in range(3):  # the first request after LibreHardwareMonitor starts can be slow
            try:
                first = self.watts(timeout=10)
                break
            except OSError as e:
                if attempt == 2:
                    raise RuntimeError(f"LibreHardwareMonitor did not answer at {self.url} ({e}). Is it running as "
                                       "admin with Options > Remote Web Server > Run ticked? Try the URL in a browser.")
                time.sleep(2)
        if first is None:
            raise RuntimeError(f"no power sensor matching '{sensor}' at {self.url}; "
                               "check the sensor name in LibreHardwareMonitor or pass --lhm-sensor")

    def watts(self, timeout=2):
        with urllib.request.urlopen(self.url, timeout=timeout) as r:
            tree = json.load(r)
        found = []

        def walk(node):
            value = str(node.get("Value", ""))
            if node.get("Text", "").lower() == self.sensor and value.endswith(" W"):
                found.append(float(value[:-2].replace(",", ".")))
            for child in node.get("Children", []):
                walk(child)

        walk(tree)
        return sum(found) if found else None


class StreamSource:
    """Runs a command that keeps printing power readings and keeps the latest one."""

    def __init__(self, name, cmd, pattern, scale, hint):
        self.name, self.pattern, self.scale = name, re.compile(pattern), scale
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.latest = None
        threading.Thread(target=self.reader, daemon=True).start()
        deadline = time.time() + 10
        while self.latest is None and time.time() < deadline:
            time.sleep(0.1)
        if self.latest is None:
            raise RuntimeError(f"{name} gave no reading; {hint}")

    def reader(self):
        for line in self.proc.stdout:
            m = self.pattern.search(line)
            if m:
                self.latest = float(m.group(1)) * self.scale

    def watts(self):
        return self.latest


def powermetrics(interval):
    """macOS (Apple silicon): combined CPU + GPU + ANE power."""
    ms = str(max(100, int(interval * 1000)))
    return StreamSource("powermetrics", ["sudo", "-n", "powermetrics", "--samplers", "cpu_power,gpu_power", "-i", ms],
                        r"Combined Power \(CPU \+ GPU \+ ANE\):\s*([\d.]+)\s*mW", 1e-3,
                        "run `sudo -v` first so sudo does not ask again")


def battery():
    """Windows laptop on battery: whole-laptop power from the battery discharge rate (WMI, ~1 s updates)."""
    loop = ("while($true){$b=Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus | Select-Object -First 1;"
            "\"rate $($b.DischargeRate) $($b.PowerOnline)\"; Start-Sleep -Milliseconds 500}")
    src = StreamSource("battery", ["powershell", "-NoProfile", "-Command", loop], r"rate (\d+)", 1e-3,
                       "is this a Windows laptop with a battery?")
    if src.latest == 0:
        print("warning: battery discharge rate is 0, unplug the charger for --power battery")
    return src


def nvidia(interval):
    """NVIDIA GPU power from nvidia-smi's own loop (one process, so sampling stays cheap on Windows)."""
    ms = str(max(100, int(interval * 1000)))
    return StreamSource("nvidia", ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits", "-lms", ms],
                        r"^\s*([\d.]+)\s*$", 1.0, "is nvidia-smi on PATH?")


def tegrastats(interval):
    """NVIDIA Jetson: total board input power (VDD_IN)."""
    ms = str(max(100, int(interval * 1000)))
    return StreamSource("tegrastats", ["tegrastats", "--interval", ms], r"VDD_IN (\d+)mW", 1e-3,
                        "is this a Jetson? try sudo")


class PowerLog:
    """Samples every source in a background thread and keeps (time, cumulative joules).

    Sources that give watts are integrated with the trapezoid rule; RAPL already gives joules.
    """

    def __init__(self, sources, interval):
        self.sources, self.interval = sources, interval
        self.samples = []  # (time, cumulative joules)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None

    def read(self, state):
        total = 0.0
        now = time.time()
        for s in self.sources:
            if hasattr(s, "joules"):
                total += s.joules()
            else:
                w = s.watts() or 0.0
                t0, w0, j0 = state.get(s.name, (now, w, 0.0))
                j = j0 + (now - t0) * (w + w0) / 2
                state[s.name] = (now, w, j)
                total += j
        return now, total

    def run(self):
        state = {}
        while not self.stop.is_set():
            try:
                sample = self.read(state)
                with self.lock:
                    self.samples.append(sample)
            except Exception as e:  # a missed sample is fine, a dead thread is not
                print(f"power sample failed: {e}")
            self.stop.wait(self.interval)

    def start(self):
        if self.sources:
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join()
        for s in self.sources:
            if hasattr(s, "proc"):
                s.proc.terminate()

    def energy(self, t0, t1):
        """Joules used between t0 and t1, interpolated from the samples."""
        with self.lock:
            s = list(self.samples)
        if len(s) < 2 or s[0][0] > t0 or s[-1][0] < t1:
            return None

        def at(t):
            for (ta, ja), (tb, jb) in zip(s, s[1:]):
                if ta <= t <= tb:
                    return ja + (jb - ja) * (t - ta) / (tb - ta) if tb > ta else ja
            return s[-1][1]

        return at(t1) - at(t0)

    def wait_past(self, t):
        """Block until there is a sample after t, so energy(.., t) can be computed."""
        if not self.sources:
            return
        while True:
            with self.lock:
                if self.samples and self.samples[-1][0] >= t:
                    return
            time.sleep(self.interval / 4)


def make_sources(args):
    sources = []
    for name in filter(None, args.power.split(",")):
        if name == "rapl":
            sources.append(Rapl())
        elif name == "lhm":
            sources.append(Lhm(args.lhm_url, args.lhm_sensor))
        elif name == "nvidia":
            sources.append(nvidia(args.interval))
        elif name == "powermetrics":
            sources.append(powermetrics(args.interval))
        elif name == "battery":
            sources.append(battery())
        elif name == "tegrastats":
            sources.append(tegrastats(args.interval))
        elif name != "none":
            raise SystemExit(f"unknown power source {name}")
    return sources


# ---------------------------------------------------------------- inference

def ollama(url, model, msgs, threads, max_tokens, cpu_only=False, no_think=False):
    """Streams from Ollama's native API. Returns (reply, ttft, server timings)."""
    options = {"temperature": 0, "num_predict": max_tokens}
    if threads:
        options["num_thread"] = threads
    if cpu_only:
        options["num_gpu"] = 0  # no layers on the GPU
    payload = {"model": model, "messages": msgs, "stream": True, "options": options, "keep_alive": "30m"}
    if no_think:
        payload["think"] = False  # newer Ollama ignores the /no_think tag; this turns Qwen3's reasoning off
    body = json.dumps(payload).encode()
    request = urllib.request.Request(url.rstrip("/") + "/api/chat", body, {"Content-Type": "application/json"})
    start = time.time()
    ttft, parts, final = None, [], {}
    with urllib.request.urlopen(request, timeout=900) as r:
        for line in r:
            if not line.strip():
                continue
            chunk = json.loads(line)
            if "error" in chunk:
                raise RuntimeError(chunk["error"])
            msg = chunk.get("message") or {}
            text = (msg.get("content") or "") + (msg.get("thinking") or "")
            if text and ttft is None:
                ttft = time.time() - start
            parts.append(msg.get("content") or "")
            if chunk.get("done"):
                final = chunk
    ns = 1e9
    info = {"prompt_tokens": final.get("prompt_eval_count"), "output_tokens": final.get("eval_count"),
            "load_s": round(final.get("load_duration", 0) / ns, 3),
            "prefill_s": round(final.get("prompt_eval_duration", 0) / ns, 3),
            "decode_s": round(final.get("eval_duration", 0) / ns, 3)}
    return "".join(parts), ttft, info


def openai_stream(url, key, model, msgs, headers, max_tokens):
    """OpenAI-compatible chat call (Groq, or the gateway). Uses streaming when the server supports it."""
    body = json.dumps({"model": model, "messages": msgs, "temperature": 0, "max_tokens": max_tokens,
                       "stream": True, "stream_options": {"include_usage": True}}).encode()
    h = {"Content-Type": "application/json", "User-Agent": "rq2-measure/1.0", **headers}  # some APIs block urllib's default agent
    if key:
        h["Authorization"] = "Bearer " + key
    request = urllib.request.Request(url.rstrip("/") + "/chat/completions", body, h)
    start = time.time()
    ttft, parts, usage = None, [], {}
    with urllib.request.urlopen(request, timeout=600) as r:
        if "event-stream" not in (r.headers.get("Content-Type") or ""):  # server ignored stream=True
            data = json.load(r)
            usage = data.get("usage") or {}
            parts.append(data["choices"][0]["message"].get("content") or "")
        else:
            for line in r:
                line = line.decode().strip()
                if not line.startswith("data:") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[5:])
                usage = chunk.get("usage") or (chunk.get("x_groq") or {}).get("usage") or usage
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    text = (delta.get("content") or "") + (delta.get("reasoning") or "")
                    if text and ttft is None:
                        ttft = time.time() - start
                    parts.append(delta.get("content") or "")
    info = {"prompt_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")}
    return "".join(parts), ttft, info


def rtt_ms(url, tries=5):
    """Median TCP connect time to the cloud host, as a simple network measure (no admin rights needed)."""
    u = urllib.parse.urlparse(url)
    port = u.port or (443 if u.scheme == "https" else 80)
    times = []
    for _ in range(tries):
        start = time.time()
        try:
            socket.create_connection((u.hostname, port), timeout=5).close()
            times.append((time.time() - start) * 1000)
        except OSError:
            pass
    return round(statistics.median(times), 1) if times else None


def call(args, task, prompt):
    msgs = run_eval.messages(task, prompt, args.no_think)
    if args.tier == "local":
        return ollama(args.ollama, args.model, msgs, args.threads, args.max_tokens, args.cpu_only, args.no_think)
    if args.cloud_via == "direct":
        return openai_stream(args.cloud_url, os.environ.get(args.key_env), args.cloud_model, msgs, {}, args.max_tokens)
    headers = {"X-Task-Type": task, "X-Force-Tier": "cloud"}
    return openai_stream(args.gateway + "/v1", None, "auto", msgs, headers, args.max_tokens)


# ---------------------------------------------------------------- main loop

def measure_idle(power, seconds, settle):
    if not power.sources or seconds <= 0:
        return None
    if settle > 0:
        print(f"waiting {settle}s for the CPU/GPU to drop to idle power states ...")
        time.sleep(settle)
    print(f"measuring idle power for {seconds}s, keep the machine quiet ...")
    t0 = time.time()
    time.sleep(seconds)
    t1 = time.time()
    power.wait_past(t1)
    joules = power.energy(t0 + power.interval, t1)  # skip the first partial sample
    return joules / (t1 - t0 - power.interval) if joules is not None else None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tier", choices=["local", "cloud"], required=True)
    p.add_argument("--label", default="", help="model name for the tables, e.g. llama, qwen, cloud")
    p.add_argument("--profile", default="native", help="device profile name, e.g. native, docker-full, docker-2cpu")
    p.add_argument("--network", default="wifi", help="network name, e.g. wifi, hotspot (matters for cloud)")
    p.add_argument("-n", type=int, default=20, help="questions per task")
    p.add_argument("--tasks", default=",".join(run_eval.TASKS))
    p.add_argument("--csv", required=True)
    p.add_argument("--no-think", action="store_true")
    p.add_argument("--max-tokens", type=int, default=1024)
    # local
    p.add_argument("--ollama", default="http://127.0.0.1:11434")
    p.add_argument("--model", default="llama3.2:3b")
    p.add_argument("--threads", type=int, help="Ollama num_thread, a simple way to mimic a weaker CPU")
    p.add_argument("--cpu-only", action="store_true", help="keep the model off the GPU (Ollama num_gpu=0)")
    # cloud
    p.add_argument("--cloud-via", choices=["direct", "gateway"], default="direct",
                   help="direct: call the API yourself (streaming, gives TTFT); gateway: go through Leo's gateway")
    p.add_argument("--cloud-url", default="https://api.groq.com/openai/v1")
    p.add_argument("--cloud-model", default="openai/gpt-oss-120b")
    p.add_argument("--key-env", default="GROQ_API_KEY")
    p.add_argument("--gateway", default="http://127.0.0.1:8080")
    # power
    p.add_argument("--power", default="none", help="comma list of rapl, lhm, nvidia, battery, powermetrics, tegrastats, none")
    p.add_argument("--lhm-url", default="http://127.0.0.1:8085")
    p.add_argument("--lhm-sensor", default="CPU Package", help="exact LibreHardwareMonitor sensor name (AMD: 'Package')")
    p.add_argument("--interval", type=float, default=0.2, help="seconds between power samples")
    p.add_argument("--idle", type=float, default=30, help="seconds of idle measurement before the run")
    p.add_argument("--max-idle", type=float, default=30, help="stop if idle power is above this many watts")
    p.add_argument("--settle", type=float, default=20, help="seconds to wait after warm-up before measuring idle")
    p.add_argument("--power-log", help="also save every power sample to this CSV (to see how power ramps up and down)")
    p.add_argument("--gap", type=float, default=10.0,
                   help="pause after each request; its energy above idle is counted. 10 s = isolated request (the GPU "
                        "takes ~5-8 s to return to idle power); 0 = back-to-back requests on a busy device")
    args = p.parse_args()

    items = run_eval.seeded(args.n, args.tasks.split(","))
    power = PowerLog(make_sources(args), args.interval)
    power.start()
    try:
        run(args, items, power)
    finally:
        power.close()
        if args.power_log and power.samples:
            with open(args.power_log, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["time", "cumulative_j", "watts"])
                prev = power.samples[0]
                for t, j in power.samples:
                    watts = (j - prev[1]) / (t - prev[0]) if t > prev[0] else ""
                    w.writerow([round(t, 3), round(j, 3), watts and round(watts, 2)])
                    prev = (t, j)
            print(f"wrote {len(power.samples)} power samples to {args.power_log}")


def run(args, items, power):
    target = args.ollama if args.tier == "local" else (args.cloud_url if args.cloud_via == "direct" else args.gateway)

    if args.tier == "local":  # load the model so the first request does not pay the load time
        print("warming up the local model ...")
        call(args, "yesno", "Passage: The sky is blue.\nQuestion: is the sky blue?")
    idle_w = measure_idle(power, args.idle, args.settle)
    if idle_w is not None and idle_w > args.max_idle:
        raise SystemExit(f"idle power is {idle_w:.1f} W, above --max-idle {args.max_idle} W: something else is using the "
                         "CPU/GPU. Close it (check Task Manager) and run again; the numbers would be wrong otherwise.")
    rtt = rtt_ms(target)
    print(f"idle power {idle_w and round(idle_w, 2)} W, RTT to {target}: {rtt} ms")

    fields = ["run", "tier", "profile", "network", "task", "score", "verdict", "ttft_s", "total_s",
              "prompt_tokens", "output_tokens", "load_s", "prefill_s", "decode_s", "energy_j", "extra_energy_j",
              "avg_power_w", "idle_power_w", "power_source", "rtt_ms", "gap_s", "t_start", "t_end", "gold", "reply", "question", "error"]
    with open(args.csv, "w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=fields)
        w.writeheader()
        for i, (task, question, prompt, gold) in enumerate(items, 1):
            row = {"run": args.label or (args.model if args.tier == "local" else args.cloud_model),
                   "tier": args.tier, "profile": args.profile, "network": args.network, "task": task,
                   "idle_power_w": idle_w and round(idle_w, 3), "rtt_ms": rtt, "gap_s": args.gap,
                   "power_source": "+".join(s.name for s in power.sources) or "none",
                   "gold": run_eval.show_gold(gold), "question": question}
            t0 = time.time()
            row["t_start"] = round(t0, 3)
            try:
                reply, ttft, info = call(args, task, prompt)
                t1 = time.time()
                reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.S).strip()
                row["score"], row["verdict"] = run_eval.verdict(task, reply, gold)
                row.update(info, reply=reply, ttft_s=ttft and round(ttft, 3), total_s=round(t1 - t0, 3))
            except Exception as e:
                t1 = time.time()
                row.update(verdict="ERROR", error=str(e)[:300], total_s=round(t1 - t0, 3))
            row["t_end"] = round(t1, 3)
            time.sleep(args.gap)
            t2 = time.time()
            power.wait_past(t2)
            joules = power.energy(t0, t1)
            if joules is not None:
                row["energy_j"] = round(joules, 3)
                row["avg_power_w"] = round(joules / (t1 - t0), 3)
            # Extra energy uses the request plus the pause after it: power readings lag
            # (nvidia-smi averages over ~1 s), so a short request's energy shows up just after it ends.
            window = power.energy(t0, t2)
            if window is not None and idle_w is not None:
                row["extra_energy_j"] = round(window - idle_w * (t2 - t0), 3)
            w.writerow(row)
            out.flush()
            print(f"{i:4}/{len(items)} {task:8} {row['verdict'][:10]:10} ttft={row.get('ttft_s')}s "
                  f"total={row['total_s']}s extra={row.get('extra_energy_j')} J")
    print(f"wrote {len(items)} rows to {args.csv}")


if __name__ == "__main__":
    main()
