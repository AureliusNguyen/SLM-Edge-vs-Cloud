# RQ3 summary for the final report: hourly grid carbon, full routing comparison, embodied and network carbon

Files (all in `rq3/results/`):

| file | what it is |
|---|---|
| `miso_hourly_ci_2024.csv` | hourly carbon intensity of the MISO grid, 2024 (8,784 hours) |
| `hourly_ci.png` | mean and 10th–90th percentile by hour of day, vs the fixed 420 we used |
| `hourly_<model>_<low/upper>.md` | break-even grid intensity per profile and task; yearly carbon with hourly vs flat grid |
| `rq3_compare.md` / `.csv` | every policy x both SLMs x 4 device profiles x 2 networks x 2 cloud-energy estimates, with operational (hourly), embodied, network, total, g per correct answer, tCDP |
| `rq3_compare.png` | headline figure: carbon per request split by source, with accuracy, for both SLMs |

Scripts: `rq3/get_hourly_ci.py` (data), `rq3/rq3_hourly.py`, `rq3/rq3_compare.py`.

## 1. Hourly carbon intensity (report Sec 5.3)

**Data.** EIA-930 hourly net generation by fuel for the MISO balancing authority, Jan–Dec 2024
(`EIA930_BALANCE_2024_*.csv`). Intensity per hour = sum(generation x direct CO2 rate of the fuel) /
total generation; coal 2.31, gas 0.96, petroleum 2.46 lb CO2/kWh (EIA FAQ), zero for nuclear, wind,
solar, hydro, geothermal; storage left out. The 2024 fuel mix comes out as coal 26%, gas 40%,
nuclear 14%, wind 15%, solar 2%, hydro 2%.

Note for the method section: EIA changed the column layout on 1 July 2024 (wind, solar and hydro
split into several columns). The first version of `get_hourly_ci.py` would have dropped wind and
solar for the second half of the year and overstated the intensity (mean 493 instead of 445).
The script now sums all columns of each fuel.

**Numbers.**

- Mean over the 8,784 hours: **445 g/kWh** (generation-weighted: 450). 10th / 50th / 90th
  percentile **353 / 448 / 528**; min 247, max 632. The fixed value we used (eGRID MROW, 420) is
  6% below the MISO mean.
- By hour of day (Central time) the mean moves only from **423 (3–4 am) to 472 (8–9 pm)**.
  The spread within any one hour of day across the year is much larger (about 340–550).
- By month: lowest in April (371) and March (381), highest in January (526) and July (496).
  Wind drives most of the variation.

**What it changes.**

- Policies that send any traffic to the cloud: the yearly carbon with hourly intensity differs
  from the flat-420 estimate by **at most 1%**. The cloud call (0.24 Wh at 350 g/kWh = 0.084 g)
  dominates, and its grid is held fixed.
- Always-local: +6% (0.0058 → 0.0062 g per request for Llama on the GPU), just because the MISO
  mean is above 420.
- The carbon-best choice (local vs cloud) **never flips with the hour** on the GPU, CPU or
  full-Docker profiles, for either SLM, with either cloud estimate. The only flip: Llama on
  2-CPU Docker, math task, low cloud estimate. Its local run uses 0.197 Wh, so the cloud is
  lower-carbon whenever the grid is above 429 g/kWh, which is **60% of the hours of 2024**.

Caveats: direct (combustion) CO2 only, like eGRID, not life-cycle; MISO is the balancing
authority, larger than the MROW subregion; imports are not traced; the data-center grid stays
at a flat 350 because Groq's serving location is unknown.

## 2. Full routing comparison (report Sec 6.5)

Three policies were added to the six in `rq3_sim.py`:

- **carbon-aware**: for each task, choose the side with less gCO2e per request, using the fixed
  420 g/kWh. This is the Load-Balancer `CarbonAware` strategy with static per-backend profiles.
- **carbon-aware-hourly**: the same choice, made every hour with that hour's grid intensity.
- **rule+cascade+carbon**: rule+cascade, but a request bound for the SLM goes straight to the
  cloud in hours when the cloud is lower-carbon. This can only raise quality.

Headline (GPU laptop, Wi-Fi, 0.24 Wh per cloud call; carbon = operational with hourly grid +
embodied + network, mid assumptions; accuracy over 400 questions, cross-validated):

| policy | Llama acc | Llama gCO2e/req | Qwen acc | Qwen gCO2e/req | Llama tCDP g·s |
|---|---|---|---|---|---|
| always-local | 0.748 | 0.0088 | 0.578 | 0.0060 | 0.0038 |
| always-cloud | 0.915 | 0.092 | 0.915 | 0.092 | 0.046 |
| task-rule | 0.858 | 0.047 | 0.863 | 0.047 | 0.017 |
| cascade | 0.878 | 0.056 | 0.883 | 0.070 | 0.040 |
| rule+cascade | 0.895 | 0.068 | 0.897 | 0.067 | 0.031 |
| oracle (upper bound) | 0.917 | 0.030 | 0.922 | 0.041 | 0.013 |
| carbon-aware (static or hourly) | 0.748 | 0.0088 | 0.578 | 0.0060 | 0.0038 |
| rule+cascade+carbon | 0.895 | 0.068 | 0.897 | 0.067 | 0.031 |

Findings:

1. **A carbon-only router collapses to always-local.** One local request on the GPU emits
   4–300x less than one cloud call, depending on the task, so a router that minimises gCO2e alone never uses the cloud
   and inherits the SLM's accuracy (0.75 Llama, 0.58 Qwen). Carbon has to be a tie-breaker inside
   a quality gate, not the objective.
2. **Hourly grid data does not change any routing decision on our hardware.** The carbon-aware
   router with the hourly grid makes the same choices as with a fixed value, and rule+cascade+carbon
   is identical to rule+cascade. The one exception is the slowest profile (2-CPU Docker, Llama math):
   there the hourly carbon-aware router sends math to the cloud in 60% of hours, which lowers its
   carbon from 0.059 to 0.048 g and raises accuracy from 0.75 to 0.78. Hourly data would
   matter if the cloud side also had an hourly grid, or if the edge device were much less efficient.
3. **The ranking of the quality-aware policies is the same as in `rq3_sim.py`**: task-rule
   halves the carbon of always-cloud at -6 points accuracy; rule+cascade gets within 2 points of
   the cloud for 74% of its carbon; the oracle shows the confidence signal is the bottleneck.
4. **tCDP** (carbon x delay, Golden et al.) ranks task-rule best among the quality-aware
   policies (0.017 g·s for Llama, 0.016 for Qwen), because it is both the fastest and the second
   lowest in carbon. Cascade is worst after always-cloud, because escalations pay twice in time.
5. Upper cloud-energy estimate (83.1 Wh per 1k output tokens): always-cloud rises to 4.5 g per
   request and the gaps grow. For Llama the order changes: cascade (2.34 g total) beats task-rule
   (3.0 g), because cloud energy now scales with output tokens and cascade keeps about half of the
   long math answers local, while task-rule sends all math to the cloud. For Qwen the order stays
   the same (task-rule 3.0 g, cascade 3.5 g), because its cascade never keeps classify local.

All device profiles, both networks, and the upper estimate are in `rq3_compare.md`.

## 3. Embodied and network carbon (report Sec 7)

All per request, Llama, GPU, Wi-Fi, low cloud estimate. Mid assumption, range low–high in brackets.

| policy | operational | device embodied | cloud embodied | network | total |
|---|---|---|---|---|---|
| always-local | 0.0062 | 0.0026 [0.0008–0.0097] | 0 | 0 | 0.0088 [0.007–0.016] |
| always-cloud | 0.085 | 0.0030 [0.0010–0.011] | 0.0046 [0.0012–0.023] | 0.00018 [0.000004–0.0013] | 0.092 [0.087–0.12] |
| task-rule | 0.043 | 0.0021 | 0.0023 | 0.00009 | 0.047 [0.044–0.063] |

- **Embodied carbon adds 9% to always-cloud and 42% to always-local** (mid). For local inference
  it is the second-largest term: device embodied is 30% of the total. It does not change any
  ranking.
- **Network carbon is under 1%** of a cloud request on Wi-Fi (0.2%) and on the phone hotspot
  (0.9%, up to 0.0067 g at the high end). Requests are small (5–50 kB).

Assumptions (low / mid / high). They are estimates, not measurements, and should be described
that way in the report:

- **Laptop embodied**: 150 / 250 / 350 kgCO2e, typical of manufacturer product carbon footprints
  for 15–16 inch performance laptops; lifetime 5 / 4 / 3 years; active 12 / 8 / 4 hours a day.
  That gives 1.9 / 6.0 / 22 mgCO2e per active second, charged for the request's duration on both
  paths, because the laptop is the client either way. If only local inference is charged (a cloud-only
  user could buy a thin client), the cloud paths drop by about 0.003 g.
- **Cloud embodied**: an 8-GPU inference server at 1,500 / 2,500 / 4,000 kgCO2e, 8 / 6 / 4 kW
  average draw, 6 / 5 / 4 years, 70 / 50 / 30% utilization. That gives 5 / 19 / 95 gCO2e per kWh
  of server energy, multiplied by the cloud Wh. Groq's LPU hardware has no published footprint; this
  is a GPU-server stand-in. Training carbon is excluded (Bashir et al.).
- **Network**: 5 / 20 / 50 kB per cloud call (prompt, streamed reply, HTTP and TLS overhead);
  fixed and Wi-Fi access 0.002 / 0.02 / 0.06 kWh/GB, mobile 0.05 / 0.1 / 0.3 kWh/GB, at the
  edge grid. kWh/GB factors are an average-attribution model; Murillo et al. and El-Zahr & Zilberman
  argue the marginal energy of a small flow is close to zero, so the low end is the more defensible
  one.

## 4. Grid sensitivity (operational, GPU, Wi-Fi, low estimate)

| policy (Llama) | 163 | 364 | 420 | MISO hourly (mean 445) |
|---|---|---|---|---|
| always-local | 0.0023 | 0.0051 | 0.0058 | 0.0062 |
| always-cloud | 0.084 | 0.085 | 0.085 | 0.085 |
| task-rule | 0.042 | 0.042 | 0.043 | 0.043 |
| rule+cascade | 0.062 | 0.062 | 0.062 | 0.062 |

163 = solar-rich state and 364 = Minnesota (Kopczyk & Chandra). Only always-local is sensitive
to the edge grid (2.7x between 163 and 445). Every policy that calls the cloud is dominated by
the cloud term. Qwen rows are in `rq3_compare.md`.
