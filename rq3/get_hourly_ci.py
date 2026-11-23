"""Download EIA-930 hourly generation by fuel for one balancing authority (default MISO)
and turn it into an hourly carbon intensity, gCO2/kWh.

    python rq3/get_hourly_ci.py                 # MISO, 2024 -> rq3/results/miso_hourly_ci_2024.csv
    python rq3/get_hourly_ci.py --year 2025

Carbon intensity of each hour = sum(generation of fuel x CO2 per kWh of that fuel) / total generation.
CO2 per kWh by fuel: EIA FAQ "How much carbon dioxide is produced per kilowatthour of U.S.
electricity generation?" (2023 data): coal 2.31 lb/kWh, natural gas 0.96, petroleum 2.46.
Nuclear, wind, solar, hydro and geothermal count as zero; battery and other storage are left out (direct emissions only, like eGRID).
"Other" and "unknown" fuels are counted at the natural-gas rate (an assumption; they are a small share).
The six-month files are large (tens of MB each); they are cached in rq3/eia_cache/ (git-ignored).
"""
import argparse
import csv
import io
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/EIA930_BALANCE_{year}_{half}.csv"
LB = 453.592  # grams per pound
EF = {  # gCO2 per kWh
    "coal": 2.31 * LB,
    "natural gas": 0.96 * LB,
    "petroleum": 2.46 * LB,
    "nuclear": 0.0, "wind": 0.0, "solar": 0.0, "hydro": 0.0, "geothermal": 0.0,
    "other": 0.96 * LB, "unknown": 0.96 * LB,
}


def fetch(year, half, cache):
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, f"EIA930_BALANCE_{year}_{half}.csv")
    if not os.path.exists(path):
        url = URL.format(year=year, half=half)
        print("downloading", url, "(can take a minute) ...")
        req = urllib.request.Request(url, headers={"User-Agent": "slm-edge-vs-cloud/1.0"})
        with urllib.request.urlopen(req, timeout=600) as r, open(path + ".part", "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(path + ".part", path)
    return path


def _norm(h):
    """Column name without the (Adjusted)/(Imputed) suffix, typos in EIA's headers smoothed out."""
    h = re.sub(r"\s*\((Adjusted|Imputed)\)\s*$", "", h)
    return re.sub(r"\s+", " ", h.replace("witho ", "with ")).strip()


def _fuel(name):
    """Map one 'Net Generation (MW) from X' column to a fuel in EF, or None (storage, skipped)."""
    n = name.lower()
    if "storage" in n and not any(k in n for k in ("hydro", "pumped", "solar", "wind")):
        return None  # batteries and other storage: net flows, not generation
    for fuel, key in (("coal", "coal"), ("natural gas", "natural gas"), ("nuclear", "nuclear"),
                      ("petroleum", "petroleum"), ("hydro", "hydro"), ("hydro", "pumped"),
                      ("solar", "solar"), ("wind", "wind"), ("geothermal", "geothermal"),
                      ("other", "other fuel"), ("unknown", "unknown fuel")):
        if key in n:
            return fuel
    return None


def fuel_columns(header):
    """Map each fuel to the list of its net-generation columns (EIA's adjusted version when present).
    From July 2024 EIA split some fuels (hydro vs pumped storage, solar and wind with/without battery),
    so a fuel can have several columns; they are summed."""
    cols = {}
    for h in header:
        if not h.startswith("Net Generation (MW) from ") or re.search(r"\((Adjusted|Imputed)\)\s*$", h):
            continue
        fuel = _fuel(h[len("Net Generation (MW) from "):])
        if fuel is None:
            continue
        adj = [a for a in header if a.rstrip().endswith("(Adjusted)") and _norm(a) == _norm(h)]
        cols.setdefault(fuel, []).append((adj[0] if adj else h, h))
    return cols


def num(s):
    s = (s or "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ba", default="MISO", help="balancing authority code in EIA-930")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--cache", default=os.path.join(HERE, "eia_cache"))
    ap.add_argument("--out")
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, "results", f"{a.ba.lower()}_hourly_ci_{a.year}.csv")

    rows = []
    for half in ("Jan_Jun", "Jul_Dec"):
        path = fetch(a.year, half, a.cache)
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            idx = {h: i for i, h in enumerate(header)}
            cols = fuel_columns(header)
            missing = [k for k in ("coal", "natural gas", "nuclear", "wind") if k not in cols]
            if missing:
                raise SystemExit(f"could not find columns for {missing}. Header was:\n" + "\n".join(header))
            ba_col = next(h for h in header if h.lower().startswith("balancing authority"))
            utc_col = next(h for h in header if "utc time" in h.lower())
            loc_col = next(h for h in header if "local time" in h.lower())
            for r in reader:
                if r[idx[ba_col]] != a.ba:
                    continue
                gen = {k: sum(max((num(r[idx[a]]) if num(r[idx[a]]) is not None else num(r[idx[raw]])) or 0.0, 0.0)
                           for a, raw in cs) for k, cs in cols.items()}
                total = sum(gen.values())
                if total <= 0:
                    continue
                ci = sum(gen[k] * EF[k] for k in gen) / total
                rows.append({"utc_end": r[idx[utc_col]], "local_end": r[idx[loc_col]],
                             "total_mw": round(total), "ci_g_per_kwh": round(ci, 1),
                             **{f"share_{k.replace(' ', '_')}": round(gen[k] / total, 4) for k in gen}})
    if not rows:
        raise SystemExit(f"no rows for balancing authority {a.ba}")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        fields = list(dict.fromkeys(k for r in rows for k in r))
        w = csv.DictWriter(f, fieldnames=fields, restval="")
        w.writeheader()
        w.writerows(rows)
    cis = sorted(r["ci_g_per_kwh"] for r in rows)
    mean = sum(r["ci_g_per_kwh"] * r["total_mw"] for r in rows) / sum(r["total_mw"] for r in rows)
    print(f"{len(rows)} hours, generation-weighted mean {mean:.0f} g/kWh, "
          f"10th/50th/90th percentile {cis[len(cis)//10]:.0f}/{cis[len(cis)//2]:.0f}/{cis[9*len(cis)//10]:.0f}")
    print("columns used:", "; ".join(f"{k}=" + " + ".join(a for a, _ in cs) for k, cs in fuel_columns(header).items()))
    print("wrote", out)


if __name__ == "__main__":
    main()
