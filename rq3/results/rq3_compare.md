# RQ3 full routing comparison

Made by `rq3/rq3_compare.py`. Offline replay of the RQ1 answers with RQ2 costs, cascade thresholds from 2-fold cross-validation repeated 50 times (same as `rq3_sim.py`). Edge carbon uses the hour-by-hour MISO 2024 grid (8784 hours, mean 445 g/kWh) instead of the fixed 420; the data-center grid stays at 350. 'total' adds embodied and network carbon at the mid assumption; the range in brackets is low to high. All numbers are per request.

## llama: GPU laptop, Wi-Fi, low cloud-energy estimate (0.24 Wh per cloud call)

| policy | accuracy | kept local | latency s | operational g (flat 420) | operational g (hourly) | embodied g | network g | total g [low-high] | g per correct | tCDP g·s | $ per 1k |
|---|---|---|---|---|---|---|---|---|---|---|---|
| always-local | 0.748 | 100% | 0.44 | 0.0058 | 0.0062 | 0.0026 | 0 | 0.0088 [0.007-0.0159] | 0.0118 | 0.0038 | 0.000 |
| always-cloud | 0.915 | 0% | 0.50 | 0.0846 | 0.0847 | 0.0075 | 0.00018 | 0.0924 [0.0868-0.12] | 0.101 | 0.0462 | 0.117 |
| task-rule | 0.858 | 50% | 0.36 | 0.0425 | 0.0425 | 0.0044 | 8.9e-05 | 0.047 [0.0438-0.0625] | 0.0548 | 0.0168 | 0.070 |
| cascade | 0.878 | 48% | 0.70 | 0.0494 | 0.0498 | 0.0065 | 9.2e-05 | 0.0564 [0.0518-0.0777] | 0.0641 | 0.0395 | 0.060 |
| rule+cascade | 0.895 | 27% | 0.45 | 0.062 | 0.062 | 0.006 | 0.00013 | 0.0681 [0.0638-0.0897] | 0.076 | 0.0309 | 0.092 |
| oracle | 0.917 | 75% | 0.45 | 0.0256 | 0.0259 | 0.0038 | 4.5e-05 | 0.0298 [0.0271-0.042] | 0.0325 | 0.0134 | 0.029 |
| carbon-aware | 0.748 | 100% | 0.44 | 0.0058 | 0.0062 | 0.0026 | 0 | 0.0088 [0.007-0.0159] | 0.0118 | 0.0038 | 0.000 |
| carbon-aware-hourly | 0.748 | 100% | 0.44 | 0.0058 | 0.0062 | 0.0026 | 0 | 0.0088 [0.007-0.0159] | 0.0118 | 0.0038 | 0.000 |
| rule+cascade+carbon | 0.895 | 27% | 0.45 | 0.062 | 0.062 | 0.006 | 0.00013 | 0.0681 [0.0638-0.0897] | 0.076 | 0.0309 | 0.092 |

Same, with the upper cloud-energy estimate (83.1 Wh per 1k output tokens):

| policy | accuracy | kept local | latency s | operational g (flat 420) | operational g (hourly) | embodied g | network g | total g [low-high] | g per correct | tCDP g·s | $ per 1k |
|---|---|---|---|---|---|---|---|---|---|---|---|
| always-local | 0.748 | 100% | 0.44 | 0.0058 | 0.0062 | 0.0026 | 0 | 0.0088 [0.007-0.0159] | 0.0118 | 0.0038 | 0.000 |
| always-cloud | 0.915 | 0% | 0.50 | 4.26 | 4.26 | 0.235 | 0.00018 | 4.5 [4.33-5.43] | 4.92 | 2.25 | 0.117 |
| task-rule | 0.858 | 50% | 0.36 | 2.85 | 2.85 | 0.157 | 8.9e-05 | 3 [2.89-3.63] | 3.5 | 1.07 | 0.070 |
| cascade | 0.878 | 48% | 0.70 | 2.22 | 2.22 | 0.124 | 9.2e-05 | 2.34 [2.25-2.83] | 2.66 | 1.64 | 0.060 |
| rule+cascade | 0.895 | 27% | 0.45 | 3.5 | 3.5 | 0.193 | 0.00013 | 3.69 [3.55-4.46] | 4.12 | 1.67 | 0.092 |
| oracle | 0.917 | 75% | 0.45 | 1.08 | 1.08 | 0.0612 | 4.5e-05 | 1.14 [1.1-1.38] | 1.25 | 0.515 | 0.029 |
| carbon-aware | 0.748 | 100% | 0.44 | 0.0058 | 0.0062 | 0.0026 | 0 | 0.0088 [0.007-0.0159] | 0.0118 | 0.0038 | 0.000 |
| carbon-aware-hourly | 0.748 | 100% | 0.44 | 0.0058 | 0.0062 | 0.0026 | 0 | 0.0088 [0.007-0.0159] | 0.0118 | 0.0038 | 0.000 |
| rule+cascade+carbon | 0.895 | 27% | 0.45 | 3.5 | 3.5 | 0.193 | 0.00013 | 3.69 [3.55-4.46] | 4.12 | 1.67 | 0.092 |

## qwen_nothink: GPU laptop, Wi-Fi, low cloud-energy estimate (0.24 Wh per cloud call)

| policy | accuracy | kept local | latency s | operational g (flat 420) | operational g (hourly) | embodied g | network g | total g [low-high] | g per correct | tCDP g·s | $ per 1k |
|---|---|---|---|---|---|---|---|---|---|---|---|
| always-local | 0.578 | 100% | 0.30 | 0.0039 | 0.0042 | 0.0018 | 0 | 0.006 [0.0048-0.0109] | 0.0104 | 0.0018 | 0.000 |
| always-cloud | 0.915 | 0% | 0.50 | 0.0846 | 0.0847 | 0.0075 | 0.00018 | 0.0924 [0.0868-0.12] | 0.101 | 0.0462 | 0.117 |
| task-rule | 0.863 | 50% | 0.35 | 0.0425 | 0.0426 | 0.0043 | 8.9e-05 | 0.047 [0.0438-0.0623] | 0.0545 | 0.0163 | 0.070 |
| cascade | 0.883 | 31% | 0.67 | 0.0621 | 0.0624 | 0.0071 | 0.00012 | 0.0696 [0.0645-0.0938] | 0.0788 | 0.0465 | 0.087 |
| rule+cascade | 0.897 | 28% | 0.43 | 0.0608 | 0.0609 | 0.0059 | 0.00013 | 0.0669 [0.0626-0.0878] | 0.0746 | 0.0292 | 0.090 |
| oracle | 0.922 | 58% | 0.35 | 0.0368 | 0.0369 | 0.004 | 7.5e-05 | 0.041 [0.0381-0.0548] | 0.0444 | 0.0142 | 0.058 |
| carbon-aware | 0.578 | 100% | 0.30 | 0.0039 | 0.0042 | 0.0018 | 0 | 0.006 [0.0048-0.0109] | 0.0104 | 0.0018 | 0.000 |
| carbon-aware-hourly | 0.578 | 100% | 0.30 | 0.0039 | 0.0042 | 0.0018 | 0 | 0.006 [0.0048-0.0109] | 0.0104 | 0.0018 | 0.000 |
| rule+cascade+carbon | 0.897 | 28% | 0.43 | 0.0608 | 0.0609 | 0.0059 | 0.00013 | 0.0669 [0.0626-0.0878] | 0.0746 | 0.0292 | 0.090 |

Same, with the upper cloud-energy estimate (83.1 Wh per 1k output tokens):

| policy | accuracy | kept local | latency s | operational g (flat 420) | operational g (hourly) | embodied g | network g | total g [low-high] | g per correct | tCDP g·s | $ per 1k |
|---|---|---|---|---|---|---|---|---|---|---|---|
| always-local | 0.578 | 100% | 0.30 | 0.0039 | 0.0042 | 0.0018 | 0 | 0.006 [0.0048-0.0109] | 0.0104 | 0.0018 | 0.000 |
| always-cloud | 0.915 | 0% | 0.50 | 4.26 | 4.26 | 0.235 | 0.00018 | 4.5 [4.33-5.43] | 4.92 | 2.25 | 0.117 |
| task-rule | 0.863 | 50% | 0.35 | 2.85 | 2.85 | 0.157 | 8.9e-05 | 3 [2.89-3.63] | 3.48 | 1.04 | 0.070 |
| cascade | 0.883 | 31% | 0.67 | 3.34 | 3.34 | 0.185 | 0.00012 | 3.52 [3.39-4.26] | 3.99 | 2.35 | 0.087 |
| rule+cascade | 0.897 | 28% | 0.43 | 3.46 | 3.46 | 0.19 | 0.00013 | 3.65 [3.51-4.41] | 4.07 | 1.59 | 0.090 |
| oracle | 0.922 | 58% | 0.35 | 2.33 | 2.33 | 0.129 | 7.5e-05 | 2.46 [2.37-2.97] | 2.67 | 0.855 | 0.058 |
| carbon-aware | 0.578 | 100% | 0.30 | 0.0039 | 0.0042 | 0.0018 | 0 | 0.006 [0.0048-0.0109] | 0.0104 | 0.0018 | 0.000 |
| carbon-aware-hourly | 0.578 | 100% | 0.30 | 0.0039 | 0.0042 | 0.0018 | 0 | 0.006 [0.0048-0.0109] | 0.0104 | 0.0018 | 0.000 |
| rule+cascade+carbon | 0.897 | 28% | 0.43 | 3.46 | 3.46 | 0.19 | 0.00013 | 3.65 [3.51-4.41] | 4.07 | 1.59 | 0.090 |

## All device profiles (Wi-Fi, low estimate)

accuracy / total gCO2e (mid) / latency s.

| model | profile | always-local | always-cloud | task-rule | cascade | rule+cascade | oracle | carbon-aware | carbon-aware-hourly | rule+cascade+carbon |
|---|---|---|---|---|---|---|---|---|---|---|
| llama | gpu | 0.75 / 0.0088 / 0.44 | 0.92 / 0.0924 / 0.50 | 0.86 / 0.047 / 0.36 | 0.88 / 0.0564 / 0.70 | 0.90 / 0.0681 / 0.45 | 0.92 / 0.0298 / 0.45 | 0.75 / 0.0088 / 0.44 | 0.75 / 0.0088 / 0.44 | 0.90 / 0.0681 / 0.45 |
| llama | cpu | 0.75 / 0.0271 / 1.89 | 0.92 / 0.0924 / 0.50 | 0.86 / 0.053 / 0.72 | 0.88 / 0.0747 / 2.15 | 0.90 / 0.0742 / 0.81 | 0.92 / 0.0437 / 1.56 | 0.75 / 0.0271 / 1.89 | 0.75 / 0.0271 / 1.89 | 0.90 / 0.0742 / 0.81 |
| llama | docker-full | 0.75 / 0.0319 / 2.19 | 0.92 / 0.0924 / 0.50 | 0.86 / 0.0543 / 0.81 | 0.88 / 0.0795 / 2.45 | 0.90 / 0.0755 / 0.90 | 0.92 / 0.0473 / 1.78 | 0.75 / 0.0319 / 2.19 | 0.75 / 0.0319 / 2.19 | 0.90 / 0.0755 / 0.90 |
| llama | docker-2cpu | 0.75 / 0.0589 / 4.80 | 0.92 / 0.0924 / 0.50 | 0.86 / 0.0621 / 1.77 | 0.88 / 0.106 / 5.06 | 0.90 / 0.0833 / 1.87 | 0.92 / 0.0677 / 3.77 | 0.75 / 0.0589 / 4.80 | 0.78 / 0.0478 / 3.11 | 0.90 / 0.0833 / 1.87 |
| qwen_nothink | gpu | 0.58 / 0.006 / 0.30 | 0.92 / 0.0924 / 0.50 | 0.86 / 0.047 / 0.35 | 0.88 / 0.0696 / 0.67 | 0.90 / 0.0669 / 0.43 | 0.92 / 0.041 / 0.35 | 0.58 / 0.006 / 0.30 | 0.58 / 0.006 / 0.30 | 0.90 / 0.0669 / 0.43 |
| qwen_nothink | cpu | 0.58 / 0.0183 / 1.23 | 0.92 / 0.0924 / 0.50 | 0.86 / 0.0513 / 0.57 | 0.88 / 0.0816 / 1.57 | 0.90 / 0.0711 / 0.66 | 0.92 / 0.0466 / 0.70 | 0.58 / 0.0183 / 1.23 | 0.58 / 0.0183 / 1.23 | 0.90 / 0.0711 / 0.66 |
| qwen_nothink | docker-full | 0.58 / 0.0197 / 1.37 | 0.92 / 0.0924 / 0.50 | 0.86 / 0.0521 / 0.63 | 0.88 / 0.0828 / 1.70 | 0.90 / 0.072 / 0.72 | 0.92 / 0.0474 / 0.78 | 0.58 / 0.0197 / 1.37 | 0.58 / 0.0197 / 1.37 | 0.90 / 0.072 / 0.72 |
| qwen_nothink | docker-2cpu | 0.58 / 0.0329 / 2.55 | 0.92 / 0.0924 / 0.50 | 0.86 / 0.0572 / 1.24 | 0.88 / 0.0955 / 2.83 | 0.90 / 0.0771 / 1.33 | 0.92 / 0.0538 / 1.45 | 0.58 / 0.0329 / 2.55 | 0.58 / 0.0329 / 2.55 | 0.90 / 0.0771 / 1.33 |

## Where the carbon comes from (GPU, Wi-Fi, low estimate, mid assumptions)

| model | policy | edge operational | cloud operational | device embodied | cloud embodied | network | total |
|---|---|---|---|---|---|---|---|
| llama | always-local | 0.0062 (70%) | 0 (0%) | 0.0026 (30%) | 0 (0%) | 0 (0%) | 0.0088 |
| llama | always-cloud | 0.00065 (1%) | 0.084 (91%) | 0.003 (3%) | 0.0046 (5%) | 0.00018 (0%) | 0.0924 |
| llama | task-rule | 0.00049 (1%) | 0.042 (89%) | 0.0021 (5%) | 0.0023 (5%) | 8.9e-05 (0%) | 0.047 |
| llama | rule+cascade | 0.00071 (1%) | 0.0613 (90%) | 0.0027 (4%) | 0.0033 (5%) | 0.00013 (0%) | 0.0681 |
| qwen_nothink | always-local | 0.0042 (70%) | 0 (0%) | 0.0018 (30%) | 0 (0%) | 0 (0%) | 0.006 |
| qwen_nothink | always-cloud | 0.00065 (1%) | 0.084 (91%) | 0.003 (3%) | 0.0046 (5%) | 0.00018 (0%) | 0.0924 |
| qwen_nothink | task-rule | 0.00055 (1%) | 0.042 (89%) | 0.0021 (4%) | 0.0023 (5%) | 8.9e-05 (0%) | 0.047 |
| qwen_nothink | rule+cascade | 0.00079 (1%) | 0.0601 (90%) | 0.0026 (4%) | 0.0033 (5%) | 0.00013 (0%) | 0.0669 |

## Network carbon on the phone hotspot (GPU, low estimate)

| model | policy | network g mid [low-high] | share of total |
|---|---|---|---|
| llama | always-cloud | 0.00089 [0.00011-0.0067] | 0.9% |
| llama | task-rule | 0.00044 [5.6e-05-0.0033] | 0.9% |
| qwen_nothink | always-cloud | 0.00089 [0.00011-0.0067] | 0.9% |
| qwen_nothink | task-rule | 0.00044 [5.6e-05-0.0033] | 0.9% |

## Edge-grid sensitivity (operational carbon, GPU, Wi-Fi, low estimate)

163 = solar-rich state and 364 = Minnesota state average (Kopczyk & Chandra), 420 = eGRID MROW (what we used so far), hourly = MISO 2024 hour by hour (mean 445).

| model | policy | 163 | 364 | 420 | hourly |
|---|---|---|---|---|---|
| llama | always-local | 0.0023 | 0.0051 | 0.0058 | 0.0062 |
| llama | always-cloud | 0.0842 | 0.0845 | 0.0846 | 0.0847 |
| llama | task-rule | 0.0422 | 0.0424 | 0.0425 | 0.0425 |
| llama | cascade | 0.0457 | 0.0486 | 0.0494 | 0.0498 |
| llama | rule+cascade | 0.0616 | 0.0619 | 0.062 | 0.062 |
| llama | oracle | 0.0229 | 0.025 | 0.0256 | 0.0259 |
| qwen_nothink | always-local | 0.0015 | 0.0034 | 0.0039 | 0.0042 |
| qwen_nothink | always-cloud | 0.0842 | 0.0845 | 0.0846 | 0.0847 |
| qwen_nothink | task-rule | 0.0422 | 0.0425 | 0.0425 | 0.0426 |
| qwen_nothink | cascade | 0.0595 | 0.0615 | 0.0621 | 0.0624 |
| qwen_nothink | rule+cascade | 0.0604 | 0.0607 | 0.0608 | 0.0609 |
| qwen_nothink | oracle | 0.036 | 0.0366 | 0.0368 | 0.0369 |

## Hours of 2024 when the cloud is the lower-carbon choice (Wi-Fi)

Only cells above 0% are listed; every other profile and task is lower-carbon locally in every hour.

| model | profile | cloud estimate | task | share of hours | mean grid in those hours |
|---|---|---|---|---|---|
| llama | docker-2cpu | low | math | 60% | 490 |

## Assumptions for embodied and network carbon (low / mid / high)

- Laptop: (150, 250, 350) kgCO2e embodied, (5, 4, 3) years, (12, 8, 4) active hours a day -> 1.90 / 5.95 / 22.20 mgCO2e per active second.
- Cloud server (8-GPU class): (1500, 2500, 4000) kgCO2e embodied, average (8, 6, 4) kW, (6, 5, 4) years, utilization (0.7, 0.5, 0.3) -> 5 / 19 / 95 gCO2e per kWh of server energy.
- Network: (5, 20, 50) kB per cloud call; Wi-Fi/fixed (0.002, 0.02, 0.06) kWh/GB, mobile hotspot (0.05, 0.1, 0.3) kWh/GB, priced at the edge grid.

